"""
cosmolab.review
~~~~~~~~~~~~~~~
Review a student's own draft (skripsi, tesis, disertasi) the way a supervisor
would: comments and guiding questions per paragraph, plus a citation check.

The review never rewrites the student's text. The prompt forbids replacement
sentences, and the report only quotes the opening words of each paragraph so
the student can find it. Fixing the draft stays the student's work.

Steps:
1. Read the draft (.docx, .md, or .txt) into Markdown-like text.
2. Check citations with cosmolab.verify: every in-text citation must be in the
   reference list, and each reference is matched against the project
   collection and Crossref.
3. Ask the LLM for supervisor comments in batches of paragraphs (optional).
4. Compare every sentence with the project collection and the cited works
   (cosmolab.similarity, no AI), and label close matches by citation status.
5. Save the result as JSON and Markdown under <project>/reviews/, and
   optionally as a Word file with the firm letterhead.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from . import config, similarity as _similarity, verify
from .utils import fire_cb

LEVELS = {"s1": "skripsi (S1)", "s2": "tesis (S2)", "s3": "disertasi (S3)"}

CATEGORIES = {
    "argumen": "Argumen",
    "bukti": "Bukti & sitasi",
    "struktur": "Struktur",
    "metodologi": "Metodologi",
    "kejelasan": "Kejelasan bahasa",
}

PENTING, SARAN, CATATAN = "penting", "saran", "catatan"
SEVERITIES = {PENTING: "Penting", SARAN: "Saran", CATATAN: "Catatan"}
_SEVERITY_ORDER = {PENTING: 0, SARAN: 1, CATATAN: 2}

# The consultant's decision on each AI comment. Only accepted or edited
# comments reach the student; the Word file waits until every comment is decided.
PENDING, ACCEPT, EDIT, DROP = "belum", "terima", "edit", "buang"
DECISIONS = {PENDING: "Belum diputuskan", ACCEPT: "Terima", EDIT: "Edit", DROP: "Buang"}

BATCH_CHARS = 12000
MAX_COMMENT_CHARS = 700
MIN_PARAGRAPH_CHARS = 60

FEEDBACK_PROMPT = """Kamu adalah dosen pembimbing yang teliti untuk {level}.
Mahasiswa menyerahkan draf. Tugasmu memberi umpan balik seperti pembimbing, BUKAN menulis ulang.

Aturan wajib:
- Jangan menulis kalimat atau paragraf pengganti. Jangan memberi contoh versi perbaikan.
- Jelaskan masalahnya dan alasannya, lalu beri satu pertanyaan pemandu agar mahasiswa memperbaikinya sendiri.
- Fokus pada hal yang penting untuk jenjang {level}: kekuatan argumen, dukungan bukti dan sitasi,
  alur dan struktur, ketepatan metodologi, dan kejelasan bahasa akademik.
- Paragraf yang sudah baik tidak perlu dikomentari.
- Paling banyak 3 komentar per paragraf. Tulis dalam bahasa Indonesia.
- Setiap komentar WAJIB menyertakan "quote": potongan 5-25 kata yang disalin PERSIS dari paragraf itu
  (huruf dan tanda baca sama), yaitu bagian yang kamu komentari. Jangan memparafrasekan kutipan.
  Kalau tidak ada bagian teks yang bisa dikutip sebagai dasar komentar, jangan tulis komentarnya.

Kategori: argumen, bukti, struktur, metodologi, kejelasan.
Tingkat: penting (harus diperbaiki), saran (sebaiknya diperbaiki), catatan (opsional).

Balas HANYA JSON:
{{"comments": [{{"paragraph": <nomor P>, "quote": "kutipan persis dari paragraf", "category": "...",
   "severity": "...", "comment": "masalah dan alasannya", "question": "pertanyaan pemandu"}}],
 "strengths": ["kekuatan draf, maksimal 3"],
 "priorities": ["hal terpenting yang perlu dikerjakan mahasiswa, maksimal 3"]}}"""


# ---------------------------------------------------------------------------
# Reading the draft
# ---------------------------------------------------------------------------

_REF_WORDS = re.compile(
    r"^\**\s*(daftar\s+rujukan|daftar\s+pustaka|rujukan|referensi|references|bibliografi|bibliography|works\s+cited)\s*\**:?$",
    re.I,
)


def _heading_level(style_name: str) -> int:
    m = re.match(r"(?:heading|judul)\s*(\d)", (style_name or "").strip(), re.I)
    return int(m.group(1)) if m else 0


def docx_to_markdown(path: Path) -> str:
    """Paragraphs of a Word file as Markdown; Word headings become # headings."""
    from docx import Document

    out = []
    for para in Document(str(path)).paragraphs:
        text = para.text.strip()
        if not text:
            continue
        level = _heading_level(para.style.name if para.style is not None else "")
        if level == 0 and para.style is not None and para.style.name.lower() == "title":
            level = 1
        out.append(("#" * level + " " + text) if level else text)
    return "\n\n".join(out)


def mark_reference_heading(md: str) -> str:
    """Turn a plain 'DAFTAR PUSTAKA' line into a heading so verify finds the list."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#") and _REF_WORDS.match(line.strip()):
            lines[i] = "## " + line.strip().strip("*").strip().rstrip(":")
    return "\n".join(lines)


def read_draft(path: Path) -> str:
    path = Path(path)
    if path.suffix.lower() == ".docx":
        md = docx_to_markdown(path)
    elif path.suffix.lower() in (".md", ".txt", ".markdown"):
        md = path.read_text(encoding="utf-8")
    else:
        raise ValueError("Format draf harus .docx, .md, atau .txt")
    return mark_reference_heading(md)


def split_paragraphs(md: str) -> list[dict]:
    """Body paragraphs (no headings, no reference list), numbered P1, P2, ...

    Each paragraph keeps the heading it sits under, so comments can say where it is.
    """
    body, _refs = verify.split_reference_section(md)
    paragraphs, section = [], ""
    for block in re.split(r"\n\s*\n", body):
        text = block.strip()
        if not text:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", text)
        if m and "\n" not in text:
            section = m.group(2).strip()
            continue
        text = re.sub(r"\s*\n\s*", " ", text)
        if len(text) < MIN_PARAGRAPH_CHARS:
            continue
        paragraphs.append({"n": len(paragraphs) + 1, "section": section, "text": text})
    return paragraphs


def opening(text: str, words: int = 12) -> str:
    """First few words of a paragraph, so the student can find it. Not the full text."""
    parts = text.split()
    return " ".join(parts[:words]) + (" ..." if len(parts) > words else "")


# ---------------------------------------------------------------------------
# LLM feedback
# ---------------------------------------------------------------------------

def _default_chat(messages: list[dict], model: str | None = None) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=model or config.LLM_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=180,
    )
    return resp.choices[0].message.content or ""


def _batches(paragraphs: list[dict], limit: int = BATCH_CHARS) -> list[list[dict]]:
    out, cur, size = [], [], 0
    for p in paragraphs:
        if cur and size + len(p["text"]) > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += len(p["text"])
    if cur:
        out.append(cur)
    return out


_QUOTE_CHARS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'",
                               "–": "-", "—": "-", " ": " "})


def _norm(text: str) -> str:
    text = (text or "").translate(_QUOTE_CHARS).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_found(quote: str, paragraph: str) -> bool:
    """True when the quote really appears in the paragraph.

    Case, punctuation and spacing are ignored. Anything else, such as a
    paraphrase or words from another paragraph, does not count.
    """
    q = _norm(quote)
    return len(q.split()) >= 3 and q in _norm(paragraph)


def _clean_comment(raw: dict, texts: dict[int, str]) -> dict | None:
    try:
        n = int(str(raw.get("paragraph", "")).lstrip("Pp"))
    except ValueError:
        return None
    if n not in texts:
        return None
    comment = str(raw.get("comment") or "").strip()
    if not comment:
        return None
    category = str(raw.get("category") or "").strip().lower()
    severity = str(raw.get("severity") or "").strip().lower()
    quote = re.sub(r"\s+", " ", str(raw.get("quote") or "")).strip().strip('"“”')[:300]
    return {
        "paragraph": n,
        "quote": quote,
        "grounded": quote_found(quote, texts[n]),
        "category": category if category in CATEGORIES else "argumen",
        "severity": severity if severity in SEVERITIES else SARAN,
        "comment": comment[:MAX_COMMENT_CHARS],
        "question": str(raw.get("question") or "").strip()[:MAX_COMMENT_CHARS],
        "decision": PENDING,
    }


def llm_feedback(paragraphs: list[dict], level: str = "s2", model: str | None = None, chat=None,
                 progress_cb=None) -> dict:
    """Supervisor comments for every paragraph batch, merged into one result."""
    from .analyze import _parse_response

    chat = chat or _default_chat
    system = FEEDBACK_PROMPT.format(level=LEVELS.get(level, LEVELS["s2"]))
    comments, strengths, priorities = [], [], []
    batches = list(_batches(paragraphs))
    for b, batch in enumerate(batches, 1):
        fire_cb(progress_cb, "item", f"batch {b}/{len(batches)}", {"done": b - 1, "total": len(batches)})
        user = "\n\n".join(
            f"P{p['n']}" + (f" [bagian: {p['section']}]" if p["section"] else "") + f"\n{p['text']}" for p in batch
        )
        data = _parse_response(chat([{"role": "system", "content": system}, {"role": "user", "content": user}], model))
        texts = {p["n"]: p["text"] for p in batch}
        for raw in data.get("comments") or []:
            c = _clean_comment(raw if isinstance(raw, dict) else {}, texts)
            if c:
                comments.append(c)
        strengths += [str(s).strip() for s in data.get("strengths") or [] if str(s).strip()]
        priorities += [str(s).strip() for s in data.get("priorities") or [] if str(s).strip()]
    comments.sort(key=lambda c: (c["paragraph"], _SEVERITY_ORDER[c["severity"]]))
    for i, c in enumerate(comments, 1):
        c["id"] = f"k{i}"
    return {"comments": comments, "strengths": _dedupe(strengths)[:5], "priorities": _dedupe(priorities)[:5]}


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = it.lower()
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s} dtk" if s < 60 else f"{s // 60}:{s % 60:02d} mnt"


class _Stages:
    """Sends review stages to a progress callback.

    Events: ("stage", label, {stage, n, of}) when a stage starts, ("item", msg,
    {done, total, ...}) inside it, and ("stage_done", summary, {stage, seconds}).
    """

    def __init__(self, cb, keys: list[str]):
        self.cb, self.keys, self.key, self.t0 = cb, keys, "", 0.0

    def _pos(self) -> dict:
        return {"stage": self.key, "n": self.keys.index(self.key) + 1, "of": len(self.keys)}

    def start(self, key: str, label: str):
        self.key, self.t0 = key, time.monotonic()
        fire_cb(self.cb, "stage", label, self._pos())

    def item(self, kind: str, msg: str, data: dict | None = None):
        fire_cb(self.cb, "item", msg, {**(data or {}), **self._pos()})

    def done(self, summary: str):
        fire_cb(self.cb, "stage_done", summary, {**self._pos(), "seconds": round(time.monotonic() - self.t0, 1)})


class ProgressLog:
    """Folds review progress events into what a progress display shows.

    Feed it every event (handle), then read label (current stage), now (latest
    step), fraction (0..1 for the whole review), finished ([(summary, seconds)])
    and elapsed. When a stage fails, label still names it.
    """

    def __init__(self):
        self.t0 = time.monotonic()
        self.label, self.now = "Memulai", ""
        self.n, self.of, self.frac = 0, 1, 0.0
        self.finished: list[tuple[str, float]] = []

    def handle(self, kind: str, msg: str, data: dict | None = None):
        data = data or {}
        if kind == "stage":
            self.label = self.now = msg
            self.n, self.of, self.frac = data.get("n", self.n + 1), data.get("of", self.of), 0.0
        elif kind == "item":
            self.now = msg
            if data.get("total"):
                self.frac = max(self.frac, min(1.0, data["done"] / data["total"]))
        elif kind == "stage_done":
            self.finished.append((msg, float(data.get("seconds", 0.0))))
            self.frac = 1.0

    @property
    def fraction(self) -> float:
        return 0.0 if not self.n else min(1.0, (self.n - 1 + self.frac) / max(1, self.of))

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0


# ---------------------------------------------------------------------------
# Whole review
# ---------------------------------------------------------------------------

def review_text(md: str, title: str = "", level: str = "s2", online: bool = True, model: str | None = None,
                chat=None, source: str = "", feedback: bool = True, similarity: bool = True,
                progress_cb=None) -> dict:
    """Run the citation check, the supervisor feedback, and the similarity check on a draft.

    feedback=False skips the AI comments (no AI cost); similarity=False skips the
    similarity check. At least one of the two must run. progress_cb gets the
    stage events described in _Stages; ProgressLog turns them into a display.
    """
    if not (feedback or similarity):
        raise ValueError("Pilih minimal satu: komentar pembimbing atau cek kemiripan.")
    from . import audit

    stages = _Stages(progress_cb, ["baca", "sitasi"] + (["komentar"] if feedback else [])
                     + (["kemiripan"] if similarity else []))
    stages.start("baca", "Membaca draf")
    level = level if level in LEVELS else "s2"
    md = mark_reference_heading(md)
    paragraphs = split_paragraphs(md)
    if not paragraphs:
        raise ValueError("Draf kosong atau tidak ada paragraf isi yang bisa direview.")
    n_refs = len(verify.split_reference_section(md)[1])
    stages.done(f"Membaca draf: {len(paragraphs)} paragraf, {n_refs} entri pustaka")

    stages.start("sitasi", "Cek daftar pustaka ke Crossref" if online else "Cek daftar pustaka (tanpa Crossref)")
    cites = verify.verify_markdown(md, source=source, online=online, progress_cb=stages.item)
    stages.done(f"Cek daftar pustaka: {len(cites.references)} entri, {len(cites.citations)} sitasi dalam teks")

    if feedback:
        stages.start("komentar", f"Komentar AI ({len(list(_batches(paragraphs)))} batch)")
        fb = llm_feedback(paragraphs, level=level, model=model, chat=chat, progress_cb=stages.item)
        stages.done(f"Komentar AI: {len(fb['comments'])} komentar")
    else:
        fb = {"comments": [], "strengths": [], "priorities": []}

    report = {
        "title": title or Path(source).stem or "Draf",
        "source": source,
        "level": level,
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "model": (model or config.LLM_MODEL) if feedback else "",
        "feedback": feedback,
        "paragraphs": [{"n": p["n"], "section": p["section"], "opening": opening(p["text"]), "chars": len(p["text"])}
                       for p in paragraphs],
        "comments": fb["comments"],
        "strengths": fb["strengths"],
        "priorities": fb["priorities"],
        "citations": cites.to_dict(),
        # Kept so the similarity check can run again later. Internal only.
        "draft_md": md,
    }
    report["similarity"] = None
    if similarity:
        stages.start("kemiripan", "Cek kemiripan")
        sim = _similarity.check(paragraphs, report["citations"], online=online, progress_cb=stages.item)
        report["similarity"] = sim
        stages.done(f"Cek kemiripan: {sim['score']}%, {len(sim['findings'])} kalimat ditandai, "
                    f"{sim['sources']['korpus']} paper koleksi dan {sim['sources']['dikutip']} abstrak")
    report["summary"] = summarize(report)
    audit.log("review_draf", file=source or report["title"], model=report["model"], level=level,
              comments=len(report["comments"]), similarity=report["summary"]["similarity_score"])
    return report


def run_similarity(report: dict, online: bool = True, progress_cb=None) -> dict:
    """Run (or rerun) the similarity check on a saved review. Hidden findings stay hidden."""
    md = report.get("draft_md")
    if not md:
        raise ValueError("Review ini dibuat sebelum cek kemiripan ada. Unggah ulang drafnya untuk menjalankan cek.")
    from . import coverage

    old = report.get("similarity") or {}
    hidden = {(f["sentence"], f["source"]["title"]) for f in old.get("findings", []) if f.get("hidden")}
    sim = _similarity.check(split_paragraphs(md), report["citations"], online=online, progress_cb=progress_cb)
    for f in sim["findings"]:
        f["hidden"] = (f["sentence"], f["source"]["title"]) in hidden
    report["similarity"] = sim
    coverage.apply_abstracts(report)
    report["summary"] = summarize(report)
    return report


def fill_sources(report: dict, online: bool = True, progress_cb=None) -> dict:
    """Download the cited works that are legally available, then rerun the similarity check."""
    from . import coverage

    if not report.get("draft_md"):
        raise ValueError("Review ini dibuat sebelum cek kemiripan ada. Unggah ulang drafnya.")
    coverage.fill(report, progress_cb=progress_cb)
    return run_similarity(report, online=online, progress_cb=progress_cb)


def add_source_upload(report: dict, index: int, file_bytes: bytes, filename: str) -> dict:
    """A file the student sent for one cited work, then rerun the similarity check."""
    from . import coverage

    coverage.add_upload(report, index, file_bytes, filename)
    return run_similarity(report) if report.get("similarity") else report


def review_file(path: Path, level: str = "s2", online: bool = True, model: str | None = None, chat=None,
                feedback: bool = True, similarity: bool = True, progress_cb=None) -> dict:
    path = Path(path)
    return review_text(read_draft(path), title=path.stem.replace("_", " "), level=level, online=online,
                       model=model, chat=chat, source=str(path), feedback=feedback, similarity=similarity,
                       progress_cb=progress_cb)


def summarize(report: dict) -> dict:
    by_sev = {s: 0 for s in SEVERITIES}
    by_cat = {c: 0 for c in CATEGORIES}
    for c in report["comments"]:
        by_sev[c["severity"]] += 1
        by_cat[c["category"]] += 1
    refs = report["citations"]["references"]
    cites = report["citations"]["citations"]
    return {
        "paragraphs": len(report["paragraphs"]),
        "comments": len(report["comments"]),
        "ungrounded": sum(1 for c in report["comments"] if not c.get("grounded")),
        "by_severity": by_sev,
        "by_category": by_cat,
        "references": len(refs),
        "references_flagged": sum(1 for r in refs if r["status"] in verify.BLOCKING_REF),
        "citations": len(cites),
        "citations_missing": sum(1 for c in cites if c["status"] in verify.BLOCKING_CITE),
        "similarity_score": (report.get("similarity") or {}).get("score"),
        "similarity_findings": len(_similarity.visible(report.get("similarity"))),
    }


# ---------------------------------------------------------------------------
# Consultant decisions
# ---------------------------------------------------------------------------

def _comment(report: dict, cid: str) -> dict:
    for c in report["comments"]:
        if c.get("id") == cid:
            return c
    raise KeyError(f"Komentar {cid} tidak ada")


def set_decision(report: dict, cid: str, decision: str, comment: str | None = None, question: str | None = None) -> dict:
    """Record the consultant's decision on one comment. Edit keeps the AI text alongside the new text."""
    if decision not in DECISIONS:
        raise ValueError(f"Keputusan tidak dikenal: {decision}")
    c = _comment(report, cid)
    c["decision"] = decision
    if decision == EDIT:
        new_comment = (comment if comment is not None else c.get("edited_comment") or c["comment"]).strip()
        if not new_comment:
            raise ValueError("Komentar hasil edit tidak boleh kosong.")
        c["edited_comment"] = new_comment[:MAX_COMMENT_CHARS * 2]
        c["edited_question"] = (question if question is not None else c.get("edited_question", c["question"])).strip()
    return c


def accept_grounded(report: dict) -> int:
    """Accept every undecided comment whose quote was found in the draft. Returns how many."""
    n = 0
    for c in report["comments"]:
        if c.get("decision", PENDING) == PENDING and c.get("grounded"):
            c["decision"] = ACCEPT
            n += 1
    return n


def decision_counts(report: dict) -> dict:
    counts = {d: 0 for d in DECISIONS}
    for c in report["comments"]:
        counts[c.get("decision", PENDING)] += 1
    return counts


def is_ready(report: dict) -> bool:
    return decision_counts(report)[PENDING] == 0


def final_comments(report: dict) -> list[dict]:
    """Comments the student will see, with the consultant's edits applied."""
    out = []
    for c in report["comments"]:
        d = c.get("decision", PENDING)
        if d == ACCEPT:
            out.append(c)
        elif d == EDIT:
            out.append({**c, "comment": c.get("edited_comment") or c["comment"],
                        "question": c.get("edited_question", c["question"])})
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def report_markdown(report: dict, final: bool | None = None) -> str:
    """Markdown of the review.

    final=True: only accepted and edited comments, for the student.
    final=False: every AI comment with its decision and quote check, for internal use.
    Default: final once every comment is decided.
    """
    final = is_ready(report) if final is None else final
    s = report["summary"]
    shown = final_comments(report) if final else report["comments"]
    by_sev = {k: sum(1 for c in shown if c["severity"] == k) for k in SEVERITIES}
    level = LEVELS.get(report["level"], report["level"])
    lines = [
        f"# Catatan Review Draf: {report['title']}",
        "",
        f"Jenjang: {level}. Direview {report['reviewed_at'][:10]}. "
        f"{s['paragraphs']} paragraf isi"
        + (f", {len(shown)} komentar ({by_sev[PENTING]} penting, {by_sev[SARAN]} saran, {by_sev[CATATAN]} catatan)."
           if report.get("feedback", True) else ". Pemeriksaan sitasi dan kemiripan saja."),
        "",
        "Catatan ini berisi umpan balik dan pertanyaan pemandu. Perbaikan draf tetap dikerjakan oleh mahasiswa.",
        "",
    ]
    if not final:
        d = decision_counts(report)
        lines += [
            f"> Versi internal, belum final: {d[PENDING]} komentar belum diputuskan konsultan "
            f"({d[ACCEPT]} diterima, {d[EDIT]} diedit, {d[DROP]} dibuang). "
            f"{s.get('ungrounded', 0)} komentar AI kutipannya tidak ditemukan di draf.",
            "",
        ]
    if report["priorities"]:
        lines += ["## Prioritas perbaikan", ""] + [f"{i}. {p}" for i, p in enumerate(report["priorities"], 1)] + [""]
    if report["strengths"]:
        lines += ["## Yang sudah baik", ""] + [f"- {p}" for p in report["strengths"]] + [""]

    with_feedback = report.get("feedback", True)
    if with_feedback:
        lines += ["## Komentar per paragraf", ""]
    by_par: dict[int, list] = {}
    for c in shown:
        by_par.setdefault(c["paragraph"], []).append(c)
    if not by_par and with_feedback:
        lines += ["Tidak ada komentar per paragraf.", ""]
    for p in report["paragraphs"]:
        cs = by_par.get(p["n"])
        if not cs:
            continue
        where = f" ({p['section']})" if p["section"] else ""
        lines += [f"### P{p['n']}{where}", "", f"Paragraf yang diawali: “{p['opening']}”", ""]
        for c in cs:
            lines.append(f"- **{SEVERITIES[c['severity']]} · {CATEGORIES[c['category']]}.** {c['comment']}")
            if c.get("quote"):
                lines.append(f"  Bagian yang dikomentari: “{c['quote']}”")
            if c["question"]:
                lines.append(f"  Pertanyaan pemandu: {c['question']}")
            if not final:
                check = "kutipan cocok" if c.get("grounded") else "KUTIPAN TIDAK DITEMUKAN, cek manual"
                lines.append(f"  [{DECISIONS[c.get('decision', PENDING)]} · {check}]")
        lines.append("")

    lines += ["## Pemeriksaan sitasi", ""]
    refs = report["citations"]["references"]
    cites = report["citations"]["citations"]
    if not refs and not cites:
        lines += ["Tidak ditemukan sitasi atau daftar pustaka di draf.", ""]
    else:
        lines += [f"{s['references']} entri daftar pustaka, {s['references_flagged']} perlu dicek. "
                  f"{s['citations']} sitasi di teks, {s['citations_missing']} tidak ada di daftar pustaka.", ""]
        flagged = [r for r in refs if r["status"] in verify.BLOCKING_REF]
        if flagged:
            lines += ["Entri daftar pustaka yang perlu dicek:", ""]
            lines += [f"- {verify.LABELS.get(r['status'], r['status'])}: {r['raw'][:200]}"
                      + (f" ({r['note']})" if r.get("note") else "") for r in flagged]
            lines.append("")
        missing = [c for c in cites if c["status"] in verify.BLOCKING_CITE]
        if missing:
            lines += ["Sitasi di teks yang tidak ada di daftar pustaka:", ""]
            lines += [f"- {c['name']}, {c['year']}" for c in missing]
            lines.append("")
    lines += similarity_markdown(report.get("similarity"), final, report)
    return "\n".join(lines).rstrip() + "\n"


def similarity_markdown(sim: dict | None, final: bool, report: dict | None = None) -> list[str]:
    """Report section for the similarity check. final=True leaves out hidden findings and source excerpts."""
    if not sim:
        return []
    shown = _similarity.visible(sim) if final else sim["findings"]
    src = sim["sources"]
    lines = [
        "## Pemeriksaan kemiripan", "",
        f"Perkiraan kemiripan: **{sim['score']}%** dari {sim['words']} kata. "
        f"Dibandingkan dengan {src['korpus']} paper di koleksi proyek dan {src['dikutip']} abstrak sumber yang dikutip.",
        "", _similarity.CAVEAT, "",
    ]
    if sim.get("weak"):
        lines += [("> " + _similarity.weak_note_student(sim)) if final else ("> " + _similarity.weak_message(sim)), ""]
    from . import coverage

    cov = coverage.summary(report or {})
    if cov:
        lines += [coverage.summary_text(cov) + " Kalimat yang mengutip sumber yang tidak bisa dibandingkan "
                  "tidak ikut terperiksa.", ""]
        if not final and cov["missing"]:
            lines += ["Sumber yang perlu diminta ke mahasiswa (cukup halaman yang dikutip):", ""]
            lines += [f"- [{coverage.KINDS[it['kind']]}] {it['raw'][:200]}"
                      for it in report["coverage"]["items"] if it["status"] == coverage.MISSING]
            lines.append("")
    if not final and src.get("dikutip_gagal"):
        lines += [f"> {src['dikutip_gagal']} sumber yang dikutip tidak punya abstrak di OpenAlex, "
                  "jadi tidak ikut dibandingkan.", ""]
    if not shown:
        return lines + ["Tidak ada kalimat yang terlalu mirip dengan sumber pembanding.", ""]
    if sim.get("top_sources"):
        lines += ["Sumber dengan kemiripan terbesar:", ""]
        lines += [f"- {t['pct']}% · {_similarity.source_label(t)}" for t in sim["top_sources"][:5]]
        lines.append("")
    for label, title in _similarity.LABELS.items():
        group = [f for f in shown if f["label"] == label]
        if not group:
            continue
        lines += [f"### {title} ({len(group)})", "", _similarity.ADVICE[label], ""]
        for f in group:
            lines.append(f"- P{f['paragraph']}: “{f['sentence']}”")
            lines.append(f"  Mirip {f['match_pct']}% dengan: {_similarity.source_label(f['source'])}"
                         + (f". Dikutip sebagai: {f['cited_as']}" if f.get("cited_as") else ""))
            if not final:
                if f.get("source_excerpt"):
                    lines.append(f"  Teks sumber: “{f['source_excerpt']}”")
                if f.get("hidden"):
                    lines.append("  [Disembunyikan dari dokumen mahasiswa]")
        lines.append("")
    return lines


def reviews_dir() -> Path:
    return config.ROOT / "reviews"


def save(report: dict) -> dict:
    """Write the review to reviews/<stem>.json and .md. Saving again overwrites the same files."""
    out = reviews_dir()
    out.mkdir(parents=True, exist_ok=True)
    if not report.get("stem"):
        report["stem"] = (f"{datetime.now():%Y%m%d_%H%M%S}_"
                          f"{re.sub(r'[^A-Za-z0-9]+', '_', report['title']).strip('_')[:60] or 'draf'}")
    json_path = out / f"{report['stem']}.json"
    md_path = out / f"{report['stem']}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report_markdown(report), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def export_docx(report: dict, reviewer: str) -> Path:
    """Word file with the firm letterhead, in <project>/deliverables/.

    Only comments the consultant accepted or edited go in. Refuses while any
    comment is still undecided.
    """
    from . import audit, deliverables

    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ValueError("Nama konsultan pemeriksa wajib diisi.")
    pending = decision_counts(report)[PENDING]
    if pending:
        raise ValueError(f"Masih ada {pending} komentar yang belum diputuskan (terima, edit, atau buang).")
    title, body = deliverables.split_title(report_markdown(report, final=True))
    meta = deliverables.default_meta(title, reviewer)
    stem = f"{meta.date:%Y%m%d}_Review_{re.sub(r'[^A-Za-z0-9]+', '_', report['title']).strip('_')[:60]}"
    path = deliverables.build_docx(body, meta, config.ROOT / "deliverables" / f"{stem}.docx")
    d = decision_counts(report)
    audit.log("review_draf_kirim", file=report.get("source") or report["title"], reviewer=reviewer,
              accepted=d[ACCEPT], edited=d[EDIT], dropped=d[DROP],
              ungrounded=report["summary"].get("ungrounded", 0))
    return path


def _normalize(report: dict, stem: str) -> dict:
    report.setdefault("stem", stem)
    for i, c in enumerate(report.get("comments") or [], 1):  # reviews saved before decisions existed
        c.setdefault("id", f"k{i}")
        c.setdefault("decision", PENDING)
        c.setdefault("quote", "")
        c.setdefault("grounded", False)
    return report


def load(stem: str) -> dict:
    """One saved review by its stem (file name without extension)."""
    path = reviews_dir() / f"{Path(stem).name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Review {stem} tidak ditemukan")
    return _normalize(json.loads(path.read_text(encoding="utf-8")), path.stem)


def load_saved(limit: int = 30) -> list[dict]:
    """Saved reviews, newest first: [{"path": md_path, "report": dict}]."""
    out = []
    folder = reviews_dir()
    if not folder.exists():
        return out
    for jp in sorted(folder.glob("*.json"), reverse=True)[:limit]:
        try:
            report = json.loads(jp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"path": jp.with_suffix(".md"), "report": _normalize(report, jp.stem)})
    return out
