"""
CosmoLab citation checker.

Checks a Markdown deliverable (article, answer, report) before it goes to a
client:

1. Every entry in the reference list is looked up, first in the project's own
   corpus, then in Crossref. Wrong years and authors are flagged.
2. Every in-text citation, e.g. (Craig, 1979), Craig (1979) or
   [Title (Year)], must point to an entry in the reference list or the corpus.

AI writers can invent or garble references, so anything not confirmed is
marked for a manual check and blocks delivery until a reviewer signs off.
"""

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests

from . import config
from . import db
from .utils import fire_cb

# Reference statuses
OK_CORPUS = "ok_corpus"
OK_CROSSREF = "ok_crossref"
YEAR_MISMATCH = "year_mismatch"
AUTHOR_MISMATCH = "author_mismatch"
NOT_FOUND = "not_found"
UNPARSED = "unparsed"
SKIPPED = "skipped"  # online lookup turned off and not in corpus

# In-text citation statuses
CITE_OK = "ok"
CITE_NO_REFERENCE = "no_reference"

LABELS = {
    OK_CORPUS: "Terverifikasi (ada di koleksi proyek)",
    OK_CROSSREF: "Terverifikasi (Crossref)",
    YEAR_MISMATCH: "Tahun tidak cocok",
    AUTHOR_MISMATCH: "Penulis tidak cocok",
    NOT_FOUND: "Tidak ditemukan, cek manual",
    UNPARSED: "Format rujukan tidak terbaca",
    SKIPPED: "Belum dicek online",
    CITE_OK: "Ada di daftar rujukan",
    CITE_NO_REFERENCE: "Dikutip di teks, tapi tidak ada di daftar rujukan",
}

BLOCKING_REF = {YEAR_MISMATCH, AUTHOR_MISMATCH, NOT_FOUND, UNPARSED, SKIPPED}
BLOCKING_CITE = {CITE_NO_REFERENCE}

TITLE_MATCH = 0.85
REF_HEADING_RE = re.compile(
    r"^#{1,6}\s*\**\s*(daftar\s+rujukan|daftar\s+pustaka|rujukan|referensi|references|bibliografi|bibliography|works\s+cited|sumber)\b",
    re.IGNORECASE,
)
YEAR = r"(?:1[5-9]|20)\d{2}"
NAME = r"[A-Z][\w'’\-\.]*(?:\s+(?:al-|bin\s+|ibn\s+|van\s+|de\s+)?[A-Z][\w'’\-\.]*){0,3}"
NAMES = NAME + r"(?:\s*(?:&|dan|and)\s*" + NAME + r")?(?:\s+(?:et\s+al\.?|dkk\.?))?"
PAREN_CITE_RE = re.compile(r"\((" + NAMES + r"),?\s+(" + YEAR + r")[a-z]?(?:\s*[,:;][^()]*)?\)")
NARRATIVE_CITE_RE = re.compile(r"\b(" + NAMES + r")\s+\((" + YEAR + r")[a-z]?(?:\s*[,:][^()]*)?\)")
BRACKET_CITE_RE = re.compile(r"\[([^\[\]\n]{3,200}?)\s*\((" + YEAR + r")[a-z]?\)\]")
STOP_NAMES = {"lihat", "see", "cf", "bab", "chapter", "tahun", "abad", "sejak", "pada", "dalam", "the", "in"}


@dataclass
class Reference:
    raw: str
    authors: str = ""
    years: list = field(default_factory=list)
    title: str = ""
    status: str = UNPARSED
    note: str = ""
    doi: str = ""
    matched_title: str = ""


@dataclass
class Citation:
    text: str
    name: str
    year: str
    status: str = CITE_OK
    note: str = ""


@dataclass
class VerificationReport:
    source: str
    checked_at: str
    references: list
    citations: list
    online: bool

    @property
    def blocking(self) -> list:
        refs = [r for r in self.references if r.status in BLOCKING_REF]
        cites = [c for c in self.citations if c.status in BLOCKING_CITE]
        return refs + cites

    @property
    def ok(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "checked_at": self.checked_at,
            "online": self.online,
            "ok": self.ok,
            "references": [asdict(r) for r in self.references],
            "citations": [asdict(c) for c in self.citations],
        }


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _main_title(text: str) -> str:
    return normalize(re.split(r"[:?.—]|\s-\s", text or "", maxsplit=1)[0])


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    # Same main title, one with a subtitle and one without.
    ma, mb = _main_title(a), _main_title(b)
    if len(ma) > 15 and ma == mb:
        return 1.0
    # Treat a title as matching when one is the other plus a short subtitle,
    # but not when a short title merely sits inside a longer, different one.
    short, long_ = sorted((na, nb), key=len)
    if len(short) > 20 and short in long_ and len(short) / len(long_) >= 0.6:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _strip_md(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*_`]", "", text).strip()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def split_reference_section(md: str) -> tuple[str, list[str]]:
    """Return (body without reference section, list of raw reference entries)."""
    lines = md.splitlines()
    start = None
    for i, line in enumerate(lines):
        if REF_HEADING_RE.match(line.strip()):
            start = i
    if start is None:
        return md, []

    level = len(lines[start]) - len(lines[start].lstrip("#"))
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break

    entries, current = [], []
    for line in lines[start + 1:end]:
        stripped = line.strip()
        item = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)", stripped)
        if item:
            if current:
                entries.append(" ".join(current))
            current = [item.group(1)]
        elif not stripped or stripped.startswith("---"):
            if current:
                entries.append(" ".join(current))
                current = []
        elif current:
            current.append(stripped)
        else:
            current = [stripped]
    if current:
        entries.append(" ".join(current))

    body = "\n".join(lines[:start] + lines[end:])
    return body, [e for e in entries if len(e) > 10]


def parse_reference(raw: str) -> Reference:
    ref = Reference(raw=raw.strip())
    year_m = re.search(r"\((" + YEAR + r")(?:\s*/\s*(" + YEAR + r"))?[a-z]?\)", raw) or re.search(
        r"\b(" + YEAR + r")(?:\s*/\s*(" + YEAR + r"))?[a-z]?\b", raw
    )
    if year_m:
        ref.years = [y for y in year_m.groups() if y]
        ref.authors = _strip_md(raw[: year_m.start()]).strip(" .,(")

    title = ""
    quoted = re.search(r"[\"“]([^\"”]{5,300})[\"”]", raw)
    italic = re.search(r"\*([^*]{5,300})\*", raw)
    if quoted:
        title = quoted.group(1)
    elif italic:
        title = italic.group(1)
    elif year_m:
        after = _strip_md(raw[year_m.end():]).lstrip(" .,")
        title = re.split(r"\.\s", after, maxsplit=1)[0]
    ref.title = _strip_md(title).strip(" .")

    if ref.title and ref.years:
        ref.status = NOT_FOUND
    return ref


def extract_citations(body: str) -> list[Citation]:
    found, seen = [], set()
    for regex in (PAREN_CITE_RE, NARRATIVE_CITE_RE, BRACKET_CITE_RE):
        for m in regex.finditer(body):
            name, year = m.group(1).strip(), m.group(2)
            first = normalize(name).split(" ")[0] if normalize(name) else ""
            if not first or first in STOP_NAMES:
                continue
            key = (normalize(name), year)
            if key in seen:
                continue
            seen.add(key)
            found.append(Citation(text=m.group(0), name=name, year=year))
    return found


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _load_corpus() -> list[dict]:
    try:
        return db.get_all_papers_with_analyses()
    except Exception:
        return []


def match_corpus(ref: Reference, corpus: list[dict]) -> dict | None:
    best, best_score = None, 0.0
    for paper in corpus:
        score = title_similarity(ref.title, paper.get("title") or "")
        if score > best_score:
            best, best_score = paper, score
    return best if best_score >= TITLE_MATCH else None


def _crossref_year(item: dict) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return ""


def lookup_crossref(ref: Reference, timeout: int = 15) -> dict | None:
    params = {"query.bibliographic": _strip_md(ref.raw)[:400], "rows": 5}
    if config.EMAIL and config.EMAIL != "you@example.com":
        params["mailto"] = config.EMAIL
    r = requests.get(config.CROSSREF_API_URL, params=params, headers=config.HEADERS, timeout=timeout)
    r.raise_for_status()
    best, best_score = None, 0.0
    for item in r.json().get("message", {}).get("items", []):
        for t in item.get("title") or []:
            score = title_similarity(ref.title, t)
            if score > best_score:
                best, best_score = item, score
    return best if best_score >= TITLE_MATCH else None


def _author_matches(ref_authors: str, item: dict) -> bool:
    families = [normalize(a.get("family") or a.get("name") or "") for a in item.get("author") or []]
    families = [f for f in families if f]
    if not families or not ref_authors:
        return True  # nothing to compare
    ref_norm = normalize(ref_authors)
    return any(f.split(" ")[-1] in ref_norm for f in families)


def check_reference(ref: Reference, corpus: list[dict], online: bool) -> Reference:
    if ref.status == UNPARSED:
        ref.note = "Tidak bisa membaca tahun atau judul. Periksa format rujukan."
        return ref

    paper = match_corpus(ref, corpus)
    if paper:
        ref.matched_title = paper.get("title") or ""
        ref.doi = paper.get("doi") or ""
        corpus_year = str(paper.get("year") or "")
        if corpus_year and corpus_year not in ref.years:
            ref.status = YEAR_MISMATCH
            ref.note = f"Di koleksi tercatat tahun {corpus_year}."
        else:
            ref.status = OK_CORPUS
        return ref

    if not online:
        ref.status = SKIPPED
        ref.note = "Tidak ada di koleksi. Jalankan pemeriksaan online atau cek manual."
        return ref

    try:
        item = lookup_crossref(ref)
    except Exception as e:
        ref.status = NOT_FOUND
        ref.note = f"Crossref tidak bisa dihubungi ({type(e).__name__}). Cek manual."
        return ref

    if not item:
        ref.status = NOT_FOUND
        ref.note = "Tidak ada di koleksi maupun Crossref. Buku klasik sering begini; cek manual."
        return ref

    ref.matched_title = (item.get("title") or [""])[0]
    ref.doi = item.get("DOI") or ""
    cr_year = _crossref_year(item)
    if cr_year and cr_year not in ref.years:
        ref.status = YEAR_MISMATCH
        ref.note = f"Crossref mencatat tahun {cr_year} ({ref.matched_title[:60]}). Bisa jadi edisi lain; cek manual."
    elif not _author_matches(ref.authors, item):
        names = ", ".join(a.get("family", "") for a in item.get("author", [])[:3])
        ref.status = AUTHOR_MISMATCH
        ref.note = f"Crossref mencatat penulis: {names}."
    else:
        ref.status = OK_CROSSREF
    return ref


def check_citation(cite: Citation, refs: list[Reference], corpus: list[dict]) -> Citation:
    first = normalize(cite.name).split(" ")[0]
    for ref in refs:
        if cite.year in ref.years and first and first in normalize(ref.authors):
            return cite
    # [Title (Year)] style used by Q&A answers: point at a corpus paper.
    for paper in corpus:
        if str(paper.get("year") or "") == cite.year and title_similarity(cite.name, paper.get("title") or "") >= TITLE_MATCH:
            cite.note = "Paper ada di koleksi proyek."
            return cite
    cite.status = CITE_NO_REFERENCE
    cite.note = "Tambahkan ke daftar rujukan atau hapus kutipannya."
    return cite


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_markdown(md: str, source: str = "", online: bool = True, corpus: list[dict] | None = None,
                    progress_cb=None) -> VerificationReport:
    """progress_cb(kind, msg, data) gets an "item" event after every reference entry."""
    corpus = _load_corpus() if corpus is None else corpus
    body, raw_refs = split_reference_section(md)
    refs = [parse_reference(r) for r in raw_refs]
    total = len(refs)

    def step(n):
        fire_cb(progress_cb, "item", f"{n}/{total} entri pustaka", {"done": n, "total": total})

    if online and total > 1:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(check_reference, r, corpus, online) for r in refs]
            for n, _ in enumerate(as_completed(futures), 1):
                step(n)
            refs = [f.result() for f in futures]
    else:
        checked = []
        for n, r in enumerate(refs, 1):
            checked.append(check_reference(r, corpus, online))
            step(n)
        refs = checked

    cites = [check_citation(c, refs, corpus) for c in extract_citations(body)]
    return VerificationReport(
        source=source,
        checked_at=datetime.now().isoformat(timespec="seconds"),
        references=refs,
        citations=cites,
        online=online,
    )


def verify_file(path: Path, online: bool = True) -> VerificationReport:
    path = Path(path)
    return verify_markdown(path.read_text(encoding="utf-8"), source=str(path), online=online)


def report_markdown(report: VerificationReport) -> str:
    verdict = "LULUS: semua sitasi terverifikasi." if report.ok else f"PERLU DICEK: {len(report.blocking)} temuan."
    lines = [
        "# Laporan Pemeriksaan Sitasi (internal, jangan dikirim ke klien)",
        "",
        f"- Dokumen: `{report.source}`",
        f"- Diperiksa: {report.checked_at}",
        f"- Pemeriksaan online (Crossref): {'ya' if report.online else 'tidak'}",
        f"- Hasil: **{verdict}**",
        "",
        "## Daftar rujukan",
        "",
        "| # | Rujukan | Status | Catatan |",
        "| --- | --- | --- | --- |",
    ]
    for i, r in enumerate(report.references, 1):
        doi = f" DOI: {r.doi}" if r.doi else ""
        cell = _strip_md(r.raw).replace("|", "/")[:160]
        lines.append(f"| {i} | {cell} | {LABELS[r.status]} | {(r.note + doi).strip()} |")
    if not report.references:
        lines.append("| - | Tidak ada daftar rujukan | - | - |")
    lines += ["", "## Kutipan di dalam teks", "", "| Kutipan | Status | Catatan |", "| --- | --- | --- |"]
    for c in report.citations:
        lines.append(f"| {c.text.replace('|', '/')} | {LABELS[c.status]} | {c.note} |")
    if not report.citations:
        lines.append("| - | Tidak ada kutipan terdeteksi | - |")
    return "\n".join(lines) + "\n"


def save_report(report: VerificationReport) -> Path:
    qa_dir = config.ROOT / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(report.source).stem or "dokumen"
    md_path = qa_dir / f"{stem}_sitasi.md"
    md_path.write_text(report_markdown(report), encoding="utf-8")
    (qa_dir / f"{stem}_sitasi.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return md_path
