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
3. Ask the LLM for supervisor comments in batches of paragraphs.
4. Save the result as JSON and Markdown under <project>/reviews/, and
   optionally as a Word file with the firm letterhead.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import config, verify

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

Kategori: argumen, bukti, struktur, metodologi, kejelasan.
Tingkat: penting (harus diperbaiki), saran (sebaiknya diperbaiki), catatan (opsional).

Balas HANYA JSON:
{{"comments": [{{"paragraph": <nomor P>, "category": "...", "severity": "...",
   "comment": "masalah dan alasannya", "question": "pertanyaan pemandu"}}],
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


def _clean_comment(raw: dict, valid: set[int]) -> dict | None:
    try:
        n = int(str(raw.get("paragraph", "")).lstrip("Pp"))
    except ValueError:
        return None
    if n not in valid:
        return None
    comment = str(raw.get("comment") or "").strip()
    if not comment:
        return None
    category = str(raw.get("category") or "").strip().lower()
    severity = str(raw.get("severity") or "").strip().lower()
    return {
        "paragraph": n,
        "category": category if category in CATEGORIES else "argumen",
        "severity": severity if severity in SEVERITIES else SARAN,
        "comment": comment[:MAX_COMMENT_CHARS],
        "question": str(raw.get("question") or "").strip()[:MAX_COMMENT_CHARS],
    }


def llm_feedback(paragraphs: list[dict], level: str = "s2", model: str | None = None, chat=None) -> dict:
    """Supervisor comments for every paragraph batch, merged into one result."""
    from .analyze import _parse_response

    chat = chat or _default_chat
    system = FEEDBACK_PROMPT.format(level=LEVELS.get(level, LEVELS["s2"]))
    comments, strengths, priorities = [], [], []
    for batch in _batches(paragraphs):
        user = "\n\n".join(
            f"P{p['n']}" + (f" [bagian: {p['section']}]" if p["section"] else "") + f"\n{p['text']}" for p in batch
        )
        data = _parse_response(chat([{"role": "system", "content": system}, {"role": "user", "content": user}], model))
        valid = {p["n"] for p in batch}
        for raw in data.get("comments") or []:
            c = _clean_comment(raw if isinstance(raw, dict) else {}, valid)
            if c:
                comments.append(c)
        strengths += [str(s).strip() for s in data.get("strengths") or [] if str(s).strip()]
        priorities += [str(s).strip() for s in data.get("priorities") or [] if str(s).strip()]
    comments.sort(key=lambda c: (c["paragraph"], _SEVERITY_ORDER[c["severity"]]))
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
# Whole review
# ---------------------------------------------------------------------------

def review_text(md: str, title: str = "", level: str = "s2", online: bool = True, model: str | None = None,
                chat=None, source: str = "") -> dict:
    """Run the citation check and the supervisor feedback on a draft."""
    from . import audit

    level = level if level in LEVELS else "s2"
    md = mark_reference_heading(md)
    paragraphs = split_paragraphs(md)
    if not paragraphs:
        raise ValueError("Draf kosong atau tidak ada paragraf isi yang bisa direview.")

    cites = verify.verify_markdown(md, source=source, online=online)
    feedback = llm_feedback(paragraphs, level=level, model=model, chat=chat)

    report = {
        "title": title or Path(source).stem or "Draf",
        "source": source,
        "level": level,
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "model": model or config.LLM_MODEL,
        "paragraphs": [{"n": p["n"], "section": p["section"], "opening": opening(p["text"]), "chars": len(p["text"])}
                       for p in paragraphs],
        "comments": feedback["comments"],
        "strengths": feedback["strengths"],
        "priorities": feedback["priorities"],
        "citations": cites.to_dict(),
    }
    report["summary"] = summarize(report)
    audit.log("review_draf", file=source or report["title"], model=report["model"], level=level,
              comments=len(report["comments"]))
    return report


def review_file(path: Path, level: str = "s2", online: bool = True, model: str | None = None, chat=None) -> dict:
    path = Path(path)
    return review_text(read_draft(path), title=path.stem.replace("_", " "), level=level, online=online,
                       model=model, chat=chat, source=str(path))


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
        "by_severity": by_sev,
        "by_category": by_cat,
        "references": len(refs),
        "references_flagged": sum(1 for r in refs if r["status"] in verify.BLOCKING_REF),
        "citations": len(cites),
        "citations_missing": sum(1 for c in cites if c["status"] in verify.BLOCKING_CITE),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def report_markdown(report: dict) -> str:
    s = report["summary"]
    level = LEVELS.get(report["level"], report["level"])
    lines = [
        f"# Catatan Review Draf: {report['title']}",
        "",
        f"Jenjang: {level}. Direview {report['reviewed_at'][:10]}. "
        f"{s['paragraphs']} paragraf isi, {s['comments']} komentar "
        f"({s['by_severity'][PENTING]} penting, {s['by_severity'][SARAN]} saran, {s['by_severity'][CATATAN]} catatan).",
        "",
        "Catatan ini berisi umpan balik dan pertanyaan pemandu. Perbaikan draf tetap dikerjakan oleh mahasiswa.",
        "",
    ]
    if report["priorities"]:
        lines += ["## Prioritas perbaikan", ""] + [f"{i}. {p}" for i, p in enumerate(report["priorities"], 1)] + [""]
    if report["strengths"]:
        lines += ["## Yang sudah baik", ""] + [f"- {p}" for p in report["strengths"]] + [""]

    lines += ["## Komentar per paragraf", ""]
    by_par: dict[int, list] = {}
    for c in report["comments"]:
        by_par.setdefault(c["paragraph"], []).append(c)
    if not by_par:
        lines += ["Tidak ada komentar per paragraf.", ""]
    for p in report["paragraphs"]:
        cs = by_par.get(p["n"])
        if not cs:
            continue
        where = f" ({p['section']})" if p["section"] else ""
        lines += [f"### P{p['n']}{where}", "", f"Paragraf yang diawali: “{p['opening']}”", ""]
        for c in cs:
            lines.append(f"- **{SEVERITIES[c['severity']]} · {CATEGORIES[c['category']]}.** {c['comment']}")
            if c["question"]:
                lines.append(f"  Pertanyaan pemandu: {c['question']}")
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
    return "\n".join(lines).rstrip() + "\n"


def reviews_dir() -> Path:
    return config.ROOT / "reviews"


def save(report: dict) -> dict:
    out = reviews_dir()
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y%m%d_%H%M%S}_{re.sub(r'[^A-Za-z0-9]+', '_', report['title']).strip('_')[:60] or 'draf'}"
    json_path = out / f"{stem}.json"
    md_path = out / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report_markdown(report), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def export_docx(report: dict, reviewer: str) -> Path:
    """Word file with the firm letterhead, in <project>/deliverables/."""
    from . import deliverables

    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ValueError("Nama konsultan pemeriksa wajib diisi.")
    title, body = deliverables.split_title(report_markdown(report))
    meta = deliverables.default_meta(title, reviewer)
    stem = f"{meta.date:%Y%m%d}_Review_{re.sub(r'[^A-Za-z0-9]+', '_', report['title']).strip('_')[:60]}"
    return deliverables.build_docx(body, meta, config.ROOT / "deliverables" / f"{stem}.docx")


def load_saved(limit: int = 30) -> list[dict]:
    """Saved reviews, newest first: [{"path": md_path, "report": dict}]."""
    out = []
    folder = reviews_dir()
    if not folder.exists():
        return out
    for jp in sorted(folder.glob("*.json"), reverse=True)[:limit]:
        try:
            out.append({"path": jp.with_suffix(".md"), "report": json.loads(jp.read_text(encoding="utf-8"))})
        except (OSError, json.JSONDecodeError):
            continue
    return out
