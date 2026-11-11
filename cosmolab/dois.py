"""
DOIs for papers in the corpus.

Most sources give a DOI at harvest time. For papers saved without one,
`resolve()` looks it up:

1. arXiv papers: the journal DOI that arXiv lists for the paper, otherwise the
   DOI arXiv assigns to every preprint (10.48550/arXiv.<id>)
2. Other papers: a Crossref title search, accepted only when the title matches
   closely and the year is the same. Weaker matches are returned as candidates
   for a researcher to check, never saved automatically.

Results are kept in <project>/dois.json as {file: {"doi": "...", "source": "..."}}.
A DOI from the harvest metadata always wins, and a "manual" entry is never
replaced by a lookup.
"""

import json
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from . import config

DOIS_FILE = "dois.json"
MANUAL = "manual"
ARXIV_DOI_PREFIX = "10.48550/arXiv."
_lock = threading.Lock()

# New style ids (2207.06165) and old style ids (quant-ph/0701019, math.GT/0309136)
_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
_ARXIV_OLD = re.compile(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?")


def clean_doi(value) -> str:
    """Bare DOI in lower-case-insensitive form: '10.xxxx/yyy' (no URL prefix)."""
    doi = str(value or "").strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi if doi.startswith("10.") else ""


def arxiv_id(value) -> str:
    """arXiv id from an id, abs/pdf URL or Atom entry id. Empty when none is found."""
    text = str(value or "")
    if "arxiv" not in text.lower() and not re.fullmatch(r"\s*[\w.\-/]+\s*", text):
        return ""
    m = _ARXIV_OLD.search(text)
    if m:
        return m.group(1)
    m = _ARXIV_NEW.search(text)
    return m.group(1) if m else ""


def arxiv_id_of(rec: dict) -> str:
    for key in ("arxiv_id", "id", "url", "pdf_url", "doi"):
        aid = arxiv_id(rec.get(key)) if (key == "arxiv_id" or "arxiv" in str(rec.get(key) or "").lower()) else ""
        if aid:
            return aid
    return ""


def arxiv_doi(aid: str) -> str:
    return f"{ARXIV_DOI_PREFIX}{aid}" if aid else ""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def _path(root: Path | None = None) -> Path:
    return Path(root or config.ROOT) / DOIS_FILE


def load(root: Path | None = None) -> dict:
    p = _path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_entry(file_name: str, doi: str, source: str, root: Path | None = None, force: bool = False) -> bool:
    """Store a DOI for one paper. A manual entry is only replaced by another manual one."""
    doi = clean_doi(doi)
    with _lock:
        data = load(root)
        current = data.get(file_name)
        if current and current.get("source") == MANUAL and source != MANUAL and not force:
            return False
        if doi:
            data[file_name] = {"doi": doi, "source": source}
        else:
            data.pop(file_name, None)
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def pick(file_name: str, meta_doi, store: dict | None = None) -> tuple[str, str]:
    """Final DOI for a paper: manual entry, then harvest metadata, then a looked-up entry."""
    store = load() if store is None else store
    entry = store.get(file_name) or {}
    if entry.get("source") == MANUAL and entry.get("doi"):
        return entry["doi"], MANUAL
    meta = clean_doi(meta_doi)
    if meta:
        return meta, "metadata"
    if entry.get("doi"):
        return entry["doi"], entry.get("source", "")
    return "", ""


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _get(url: str, **kwargs):
    headers = dict(config.HEADERS)
    headers["User-Agent"] = f"CosmoLab/1.0 (mailto:{config.EMAIL})"
    try:
        r = requests.get(url, headers=headers, timeout=20, **kwargs)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def arxiv_journal_doi(entry) -> str:
    """Journal DOI from an arXiv Atom <entry> element, if the authors listed one."""
    if entry is None:
        return ""
    return clean_doi(entry.findtext("{http://arxiv.org/schemas/atom}doi", default=""))


def by_arxiv(aid: str) -> tuple[str, str]:
    """(doi, source) for an arXiv paper: journal DOI when listed, else the arXiv DOI."""
    if not aid:
        return "", ""
    r = _get("https://export.arxiv.org/api/query", params={"id_list": aid})
    if r is not None:
        try:
            entry = ET.fromstring(r.content).find("{http://www.w3.org/2005/Atom}entry")
            journal = arxiv_journal_doi(entry)
            if journal:
                return journal, "arxiv_journal"
        except ET.ParseError:
            pass
    return arxiv_doi(aid), "arxiv"


def _year_of(item: dict) -> str:
    for key in ("published-print", "published-online", "issued", "published"):
        parts = (item.get(key) or {}).get("date-parts") or [[]]
        if parts and parts[0]:
            return str(parts[0][0])
    return ""


def by_title(title: str, year: str = "", min_similarity: float = 0.95) -> tuple[str, str, list[dict]]:
    """Crossref title search. Returns (doi, source, candidates).

    The DOI is set only when the title similarity is at least `min_similarity`
    and the year matches. Other close results (similarity >= 0.75) are returned
    as candidates for manual checking.
    """
    from .verify import title_similarity

    if not title or title.lower().startswith("paper doi"):
        return "", "", []
    r = _get(config.CROSSREF_API_URL, params={"query.bibliographic": title, "rows": 5, "mailto": config.EMAIL})
    if r is None:
        return "", "", []
    year = str(year or "")[:4]
    candidates = []
    for item in r.json().get("message", {}).get("items", []):
        found = (item.get("title") or [""])[0]
        sim = title_similarity(title, found)
        if sim < 0.75:
            continue
        cand = {"doi": clean_doi(item.get("DOI")), "title": found, "year": _year_of(item),
                "journal": (item.get("container-title") or [""])[0], "similarity": round(sim, 2)}
        if sim >= min_similarity and year and cand["year"] == year:
            return cand["doi"], "crossref", []
        candidates.append(cand)
    return "", "", candidates


def resolve(rec: dict) -> tuple[str, str, list[dict]]:
    """Look up a DOI for one metadata record. Returns (doi, source, candidates)."""
    aid = arxiv_id_of(rec)
    if aid or rec.get("source") == "arxiv":
        doi, src = by_arxiv(aid)
        return doi, src, []
    return by_title(rec.get("title") or "", rec.get("year") or "")


def fill_missing(refresh: bool = False, progress=None) -> dict:
    """Look up DOIs for every paper that has none. Returns counts and candidates to check."""
    from .authors import latest_records

    store = load()
    stats = {"checked": 0, "found": 0, "not_found": 0, "sources": {}, "candidates": {}}
    for file_name, rec in latest_records().items():
        current, _ = pick(file_name, rec.get("doi"), store)
        if current and not refresh:
            continue
        if store.get(file_name, {}).get("source") == MANUAL:
            continue
        stats["checked"] += 1
        doi, src, candidates = resolve(rec)
        if doi:
            save_entry(file_name, doi, src)
            stats["found"] += 1
            stats["sources"][src] = stats["sources"].get(src, 0) + 1
        else:
            stats["not_found"] += 1
            if candidates:
                stats["candidates"][file_name] = candidates
        if progress:
            progress(file_name, doi, src, candidates)
    return stats
