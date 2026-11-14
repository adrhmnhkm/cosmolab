"""
Claim entailment gatekeeper.

Checks an AI answer (or any draft text) sentence by sentence. Every sentence
that cites a paper, e.g. `[Title (2020), Hal. 4]`, is a claim. For each claim:

1. The citation is matched to a paper in the collection. A citation that
   matches no paper is flagged at once: the source does not exist here.
2. Evidence is gathered from that paper: verbatim passages from its pages that
   best match the claim, plus the thesis and conclusion from its analysis.
3. An LLM judge decides whether the evidence entails the claim:
   supported, partly supported, or not supported.

Nothing is removed from the answer. The report tells the reader which
sentences are safe to cite and which need checking.
"""

import json
import re

from . import config

SUPPORTED = "didukung"
PARTIAL = "sebagian"
UNSUPPORTED = "tidak_didukung"
NO_SOURCE = "sumber_tidak_ada"
UNCHECKED = "belum_dicek"

VERDICT_LABELS = {
    SUPPORTED: "Didukung sumber",
    PARTIAL: "Didukung sebagian",
    UNSUPPORTED: "Tidak ditemukan di sumber",
    NO_SOURCE: "Sumber tidak ada di koleksi",
    UNCHECKED: "Belum bisa dicek",
}

# [anything with a year or n.d.], but not a markdown link [text](url)
_BRACKET = re.compile(r"\[([^\[\]\n]{2,300}?)\](?!\()")
_YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)[a-z]?\b|\bn\.d\.")
_BIBLIO = re.compile(r"^\s*\[\d+\]|\b(?:Phys\.|Rev\.|Found\.|vol\.|pp\.|doi:)\s*\w*\s*\d", re.I)
_PAGE = re.compile(r"\b(?:hal(?:aman)?|p|pp|page)\.?\s*(\d+)", re.I)
# Sentence end, but not after common abbreviations such as "hlm. 3", "Hal. 2", "dkk.", "et al.", "No. 4".
_SENT_SPLIT = re.compile(r"(?<![Hh]lm\.)(?<![Hh]al\.)(?<!dkk\.)(?<! al\.)(?<!No\.)(?<=[.!?…])\s+(?=[\"“'(\[A-Z0-9])")
_BRACKET_ANY = re.compile(r"\[[^\[\]\n]*\]")
_HOLD_OPEN, _HOLD_CLOSE = "\uE000", "\uE001"  # private-use marks, never in real text
_HELD = re.compile(_HOLD_OPEN + r"(\d+)" + _HOLD_CLOSE)
_MD = re.compile(r"(\*\*|__|\*|`|^#+\s*|^>\s*|^\s*(?:[-*+]|\d+[.)])\s+)", re.M)

JUDGE_PROMPT = """Kamu adalah pemeriksa fakta akademik yang ketat (natural language inference).
Untuk setiap klaim, nilai apakah BUKTI yang diberikan mendukung klaim tersebut.

Pilihan verdict:
- "didukung": bukti menyatakan isi klaim secara jelas (boleh dengan kata lain).
- "sebagian": bukti terkait, tetapi klaim lebih luas, lebih kuat, lebih spesifik, atau menambah detail yang tidak ada di bukti.
- "tidak_didukung": bukti tidak menyatakan klaim itu, atau bertentangan dengannya.

Aturan:
- Nilai HANYA berdasarkan bukti yang diberikan, bukan pengetahuanmu sendiri.
- Nama penulis atau judul paper yang disebut di klaim merujuk ke paper sumber itu sendiri. Jangan anggap nama itu sebagai detail yang harus ada di bukti.
- Angka, tahun, nama lain, arah hubungan (naik/turun, mendukung/menolak) harus cocok persis.
- Bagian klaim yang hanya berupa penilaian penulis jawaban (misalnya "ini menunjukkan perdebatan masih terbuka") boleh diabaikan; nilai isi faktual yang dikaitkan ke sumber.
- "reason": satu kalimat Bahasa Indonesia, sebutkan apa yang cocok atau apa yang tidak ada di bukti.
- "evidence": nomor bukti (E1, E2, ...) yang paling relevan, boleh kosong.

Jawab HANYA JSON: {"results": [{"id": 1, "verdict": "...", "reason": "...", "evidence": ["E1"]}]}"""


# ---------------------------------------------------------------------------
# Claims and citations
# ---------------------------------------------------------------------------

def _plain(text: str) -> str:
    text = re.sub(r"\[([^\[\]\n]*)\]\([^)\s]*\)", r"\1", text or "")  # [text](url) -> text
    return re.sub(r"\s+", " ", _MD.sub("", text)).strip()


def _is_citation(inner: str) -> bool:
    return bool(_YEAR.search(inner))


def parse_citation(inner: str) -> list[dict]:
    """One bracket can hold several citations separated by ';'."""
    out = []
    for part in re.split(r";\s*", inner):
        part = part.strip()
        m = None
        for m in _YEAR.finditer(part):
            pass
        if not m:
            continue
        year = m.group(1) or ""
        label = part[:m.start()].strip(" ,(-–")
        page = _PAGE.search(part[m.end():])
        out.append({"raw": part, "label": label, "year": year, "page": page.group(1) if page else ""})
    return out


def _drop_citation(m: re.Match, sentence: str) -> str:
    """Remove a citation from the claim text, but keep the cited names when the
    citation is the subject: "[Popescu & Rohrlich (1997)] membantah ..."."""
    if not _is_citation(m.group(1)):
        return m.group(0)
    before = _MD.sub("", sentence[:m.start()]).strip(" *_")
    after = sentence[m.end():].lstrip(" *_")
    last_word = (re.findall(r"[\w&]+", before.lower()) or [""])[-1]
    is_subject = (not before or after[:1].islower()
                  or last_word in {"menurut", "oleh", "dalam", "lihat", "dan", "&", "by", "according", "to", "see"})
    if not is_subject:
        return ""
    return ", ".join(c["label"] for c in parse_citation(m.group(1)) if c["label"])


def split_claims(text: str) -> list[dict]:
    """Sentences that carry at least one citation, with their parsed citations."""
    claims = []
    for line in (text or "").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Hide bracket contents so a period inside "[..., Hal. 2]" does not end a sentence.
        held: list[str] = []
        masked = _BRACKET_ANY.sub(lambda m: held.append(m.group(0)) or f"{_HOLD_OPEN}{len(held) - 1}{_HOLD_CLOSE}", line.strip())
        sentences = [_HELD.sub(lambda m: held[int(m.group(1))], x) for x in _SENT_SPLIT.split(masked)]
        merged: list[str] = []
        for s in sentences:
            # A sentence that is only citations belongs to the sentence before it.
            if merged and not _BRACKET.sub("", s).strip(" .,;"):
                merged[-1] = f"{merged[-1]} {s}"
            else:
                merged.append(s)
        for s in merged:
            cites = []
            for inner in _BRACKET.findall(s):
                if _is_citation(inner):
                    cites += parse_citation(inner)
            if not cites:
                continue
            claim = _plain(_BRACKET.sub(lambda m: _drop_citation(m, s), s))
            claim = re.sub(r"\s+([.,;:])", r"\1", claim).strip()
            # Skip source headers such as "[Popescu (1997)] — Bagian I (Introduction), hlm. 1:"
            words = [w for w in re.findall(r"[^\W\d_]{2,}", _BRACKET.sub("", s))
                     if w.lower() not in {"bagian", "hlm", "hal", "halaman", "bab", "section", "page", "pp"}]
            if len(claim) < 12 or len(words) < 3:
                continue
            claims.append({"text": claim, "sentence": _plain(s), "citations": cites})
    return claims


# ---------------------------------------------------------------------------
# Matching a citation to a collection paper
# ---------------------------------------------------------------------------

def _authors_of(paper: dict) -> list[str]:
    raw = paper.get("authors")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [a for a in re.split(r",|;| and ", raw) if a.strip()]
    return [a for a in (raw or []) if isinstance(a, str)]


def _surnames(paper: dict) -> set[str]:
    out = set()
    for name in _authors_of(paper):
        parts = [p for p in re.split(r"[\s.]+", name.lower()) if len(p) > 2]
        if parts:
            out.add(parts[-1])
    return out


def _score(cite: dict, paper: dict) -> float:
    from .verify import title_similarity

    year = str(paper.get("year") or "")[:4]
    if cite["year"] and year and cite["year"] != year:
        return 0.0
    label = (cite["label"] or "").lower()
    if not label:
        return 0.0
    title = (paper.get("title") or "").lower()
    best = title_similarity(label, title)
    if len(label) >= 12 and (label in title or title.startswith(label.rstrip(". "))):
        best = max(best, 0.9)
    words = set(re.findall(r"[a-zà-ÿ]{3,}", label))
    if words & _surnames(paper):
        best = max(best, 0.85)
    return best


def match_paper(cite: dict, papers: list[dict], min_score: float = 0.6) -> dict | None:
    scored = [(s, p) for p in papers if (s := _score(cite, p)) >= min_score]
    if not scored:
        return None
    return max(scored, key=lambda sp: sp[0])[1]


# ---------------------------------------------------------------------------
# Evidence and judging
# ---------------------------------------------------------------------------

TERMS_PROMPT = """Untuk setiap klaim, tulis kata kunci pencarian dalam BAHASA INGGRIS (6-12 kata) yang kemungkinan muncul di teks asli paper yang mendukung klaim itu: istilah teknis, nama, angka. Bila klaim menyebut istilah Arab, hukum, atau istilah lokal, sertakan juga istilah aslinya.
Jawab HANYA JSON: {"results": [{"id": 1, "terms": "..."}]}"""


def _llm_terms(items: list[dict], model: str = None) -> dict[int, str]:
    """English search terms per claim, so Indonesian claims can find passages in English papers."""
    from openai import OpenAI
    from .analyze import _parse_response

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=model or config.LLM_MODEL,
        messages=[{"role": "system", "content": TERMS_PROMPT},
                  {"role": "user", "content": "\n".join(f"KLAIM {it['id']}: {it['text']}" for it in items)}],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=60,
    )
    data = _parse_response(resp.choices[0].message.content or "")
    return {int(r["id"]): str(r.get("terms") or "") for r in data.get("results") or [] if str(r.get("id", "")).isdigit()}


def gather_evidence(claim: str, paper: dict, max_passages: int = 3, extra_query: str = "",
                    use_analysis: bool = True) -> list[dict]:
    """Verbatim passages for the claim (and for its English search terms), plus the analysis summary.

    use_analysis=False leaves out the AI analysis, so only the paper's own text counts as evidence.
    """
    from . import retrieval

    title = paper.get("title") or paper.get("file") or ""
    # Author names only find the paper's own bibliography lines, so leave them out of the search.
    names = _surnames(paper)
    extra_query = " ".join(w for w in (extra_query or "").split() if w.lower().strip(",.") not in names)
    ev, seen = [], set()
    for query in [claim, extra_query]:
        if not query:
            continue
        try:
            passages = retrieval.find_grounded_passages(paper["file"], query, top_k=max_passages + 2, max_length=700)
        except Exception:
            passages = []
        kept = 0
        for psg in passages:
            text = psg.get("verbatim", "")
            # "fallback" = the paper's opening, returned when nothing matched: not evidence for the claim.
            if kept >= max_passages or not text or psg.get("fallback") or _BIBLIO.search(text):
                continue
            kept += 1
            if text not in seen:
                seen.add(text)
                ev.append({"paper": title, "page_label": psg.get("page_label", ""), "text": text})
    for field, label in (("thesis", "Tesis (analisis)"), ("conclusion", "Kesimpulan (analisis)")):
        if use_analysis and paper.get(field):
            ev.append({"paper": title, "page_label": label, "text": paper[field]})
    return ev


def _llm_judge(items: list[dict], model: str = None) -> dict[int, dict]:
    from openai import OpenAI
    from .analyze import _parse_response

    blocks = []
    for it in items:
        ev = "\n".join(f"  E{i}. [{e['paper']} | {e['page_label']}] {e['text']}" for i, e in enumerate(it["evidence"], 1))
        blocks.append(f"KLAIM {it['id']}: {it['text']}\nBUKTI:\n{ev or '  (tidak ada)'}")
    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=model or config.LLM_MODEL,
        messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": "\n\n".join(blocks)}],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=120,
    )
    content = resp.choices[0].message.content or ""
    try:
        rows = _parse_response(content).get("results") or []
    except ValueError:
        # A reply cut off by the context limit still holds the claims judged before the cut.
        rows = _complete_results(content)
        if not rows:
            raise ValueError("Jawaban AI tidak terbaca (terpotong atau bukan JSON)")
    return {int(r.get("id")): r for r in rows if isinstance(r, dict) and str(r.get("id", "")).isdigit()}


def _complete_results(content: str) -> list[dict]:
    """The whole objects in a "results" list whose closing part is missing."""
    start = content.find("[", content.find('"results"'))
    if start < 0:
        return []
    dec, rows, i = json.JSONDecoder(), [], start + 1
    while True:
        i = content.find("{", i)
        if i < 0:
            return rows
        try:
            obj, i = dec.raw_decode(content, i)
        except json.JSONDecodeError:
            return rows
        rows.append(obj)


def _normalize_verdict(v: str) -> str:
    v = (v or "").strip().lower().replace(" ", "_")
    if v in (SUPPORTED, PARTIAL, UNSUPPORTED):
        return v
    if v.startswith("tidak") or v in ("unsupported", "contradicted", "refuted"):
        return UNSUPPORTED
    if v.startswith("sebagian") or v in ("partial", "partially_supported"):
        return PARTIAL
    if v.startswith("didukung") or v in ("supported", "entailed"):
        return SUPPORTED
    return UNCHECKED


_PAPER_NO = re.compile(r"^(?:paper|makalah|sumber)\s*(\d+)$", re.I)


def _resolve(cite: dict, papers: list[dict], numbered: list[dict] | None) -> dict | None:
    """Collection paper for one citation. "[Paper 2 (2008)]" refers to the order of `numbered`."""
    m = _PAPER_NO.match((cite.get("label") or "").strip())
    if m and numbered:
        n = int(m.group(1))
        if 1 <= n <= len(numbered):
            ref = numbered[n - 1]
            return next((p for p in papers if p.get("file") == ref.get("file")), ref)
        return None
    return match_paper(cite, papers)


# Claims per judge call. Each brings up to ~6 passages; ten of them overflow a local
# model's 8k context and the reply gets cut off mid-JSON.
JUDGE_BATCH = 4


def _try_judge(judge, batch: list[dict], model) -> tuple[dict, str]:
    try:
        return judge(batch, model) or {}, ""
    except Exception as e:
        return {}, str(e)[:120]


def _judge_claims(claims: list[dict], model, judge, evidence_fn, use_analysis: bool = True) -> list[dict]:
    """Gather evidence for claims that already have "id", "text" and "matched" papers, then judge them."""
    judge = judge or _llm_judge
    terms = {}
    if evidence_fn is None:
        try:
            terms = _llm_terms([c for c in claims if c["matched"]], model) if any(c["matched"] for c in claims) else {}
        except Exception:
            terms = {}  # fall back to searching with the claim text only

    results, to_judge = [], []
    for c in claims:
        i, matched = c["id"], c["matched"]
        evidence = []
        for p in matched:
            evidence += (evidence_fn(c["text"], p) if evidence_fn
                         else gather_evidence(c["text"], p, extra_query=terms.get(i, ""), use_analysis=use_analysis))
        row = {
            "id": i, "text": c["text"], "sentence": c.get("sentence", c["text"]),
            "citations": [x["raw"] for x in c.get("citations", [])],
            "papers": [{"file": p.get("file"), "title": p.get("title"), "year": p.get("year")} for p in matched],
            "evidence": evidence, "verdict": UNCHECKED, "reason": "", "evidence_used": [],
        }
        if not matched:
            row["verdict"] = NO_SOURCE
            row["reason"] = "Sitasi ini tidak cocok dengan paper mana pun di koleksi. Bisa jadi sumbernya dikarang atau salah tulis."
        else:
            to_judge.append(row)
        results.append(row)

    for start in range(0, len(to_judge), JUDGE_BATCH):
        batch = to_judge[start:start + JUDGE_BATCH]
        verdicts, error = _try_judge(judge, batch, model)
        missing = [row for row in batch if row["id"] not in verdicts]
        # A cut-off or unreadable reply: ask again for each claim it left out, one at a time.
        if missing and len(batch) > 1:
            for row in missing:
                one, err = _try_judge(judge, [row], model)
                verdicts.update(one)
                error = err or error
        for row in batch:
            v = verdicts.get(row["id"])
            if not v:
                row["reason"] = f"Pemeriksa AI gagal dijalankan: {error or 'klaim ini tidak ada di jawaban AI'}"
                continue
            row["verdict"] = _normalize_verdict(v.get("verdict"))
            row["reason"] = (v.get("reason") or "").strip()
            used = []
            for ref in v.get("evidence") or []:
                m = re.search(r"\d+", str(ref))
                if m and 1 <= int(m.group()) <= len(row["evidence"]):
                    used.append(int(m.group()) - 1)
            row["evidence_used"] = used
    return results


def check_claims(items: list[dict], model: str = None, judge=None, evidence_fn=None,
                 use_analysis: bool = True) -> list[dict]:
    """Check standalone claims against one known paper each.

    items: [{"text": "...", "paper": {...collection paper...}}]. Used by the
    analysis verifier and the evaluation set, where the source is already known.
    use_analysis=False judges against the paper's own text only.
    """
    claims = [{"id": i, "text": it["text"], "matched": [it["paper"]] if it.get("paper") else []}
              for i, it in enumerate(items, 1)]
    return _judge_claims(claims, model, judge, evidence_fn, use_analysis)


def check_answer(text: str, papers: list[dict] | None = None, model: str = None, max_claims: int = 20,
                 judge=None, evidence_fn=None, numbered: list[dict] | None = None) -> dict:
    """Check every cited claim in `text` against the collection.

    `numbered` is the ordered list of papers the answer was written from, so
    citations like "[Paper 2 (2008)]" can be resolved.
    Returns {"claims": [...], "summary": {verdict: count}, "total": n, "skipped": n}.
    `judge` and `evidence_fn` can be swapped out in tests.
    """
    if papers is None:
        from . import db

        papers = db.get_all_papers_with_analyses()

    all_claims = split_claims(text)
    claims = all_claims[:max_claims]
    for i, c in enumerate(claims, 1):
        c["id"] = i
        c["matched"] = []
        for cite in c["citations"]:
            p = _resolve(cite, papers, numbered)
            if p and p not in c["matched"]:
                c["matched"].append(p)

    # Only the paper's own text counts: the AI analysis would let the AI confirm itself.
    results = _judge_claims(claims, model, judge, evidence_fn, use_analysis=False)

    summary = {}
    for row in results:
        summary[row["verdict"]] = summary.get(row["verdict"], 0) + 1
    if judge is None and evidence_fn is None:
        try:
            from . import audit

            audit.log("cek_klaim", model=model or config.LLM_MODEL,
                      prompt_version=audit.prompt_version(JUDGE_PROMPT, TERMS_PROMPT), summary=summary,
                      flagged=[r["text"][:160] for r in results if r["verdict"] in (UNSUPPORTED, NO_SOURCE)])
        except Exception:
            pass
    return {"claims": results, "summary": summary, "total": len(results), "skipped": len(all_claims) - len(claims)}


def needs_attention(report: dict) -> int:
    s = report.get("summary") or {}
    return s.get(UNSUPPORTED, 0) + s.get(NO_SOURCE, 0) + s.get(PARTIAL, 0)
