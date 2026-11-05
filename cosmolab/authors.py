"""
Author names for papers in the corpus.

Search results from every source carry author names. They are stored with
each metadata record at harvest time. For papers saved before that, or PDFs
uploaded by hand, `resolve()` looks the authors up in this order:

1. Crossref by DOI, then OpenAlex by DOI
2. arXiv by arXiv id
3. OpenAlex and Crossref by title (only when the title matches closely)
4. The first page of the PDF, read by the AI model (optional), keeping only
   names that appear word for word in that page

Results are kept in <project>/authors.json as {file: {"authors": [...],
"source": "..."}}. A "manual" entry always wins and is never overwritten.
"""

import json
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from . import config

AUTHORS_FILE = "authors.json"
MANUAL = "manual"
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Name lists
# ---------------------------------------------------------------------------

_NOT_A_PERSON = re.compile(
    r"\b(univ\w*|institut\w*|college|school|department|faculty|fakultas|sekolah|ministry|kementerian|"
    r"centre|center|laboratory|lab)\b|@|\d",
    re.I,
)


def clean_names(names) -> list[str]:
    """Trim, drop empties, duplicates and organisation names, keep order."""
    out, seen = [], set()
    for n in names or []:
        n = re.sub(r"\s+", " ", str(n or "")).strip(" ,;")
        if n and _NOT_A_PERSON.search(n):
            continue
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def from_crossref(items) -> list[str]:
    """Crossref/Unpaywall style [{given, family}] or [{name}]."""
    names = []
    for a in items or []:
        if not isinstance(a, dict):
            continue
        full = " ".join(p for p in (a.get("given"), a.get("family")) if p) or a.get("name") or a.get("raw_author_name")
        if full:
            names.append(full)
    return clean_names(names)


def from_openalex(work: dict) -> list[str]:
    return clean_names(
        (a.get("author") or {}).get("display_name") or a.get("raw_author_name")
        for a in (work or {}).get("authorships") or []
    )


def from_named(items) -> list[str]:
    """[{"name": ...}] lists used by DOAJ, Semantic Scholar and CORE."""
    return clean_names(a.get("name") if isinstance(a, dict) else a for a in items or [])


def parse_input(text: str) -> list[str]:
    """Names typed by a researcher: one per line or separated by ';'."""
    parts = re.split(r"[;\n]+", text or "")
    return clean_names(parts)


def display(names: list[str]) -> str:
    """'A', 'A & B', 'A, B & C', or 'A et al.' for more than three."""
    names = clean_names(names)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ", ".join(names[:-1]) + " & " + names[-1]
    return f"{names[0]} et al."


def last_name(name: str) -> str:
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip()
    return name.split()[-1] if name.split() else name


def in_text(names: list[str]) -> str:
    """Short form for in-text citations: 'Ali', 'Ali & Budi', 'Ali et al.'."""
    names = clean_names(names)
    if not names:
        return ""
    if len(names) == 1:
        return last_name(names[0])
    if len(names) == 2:
        return f"{last_name(names[0])} & {last_name(names[1])}"
    return f"{last_name(names[0])} et al."


def as_list(value) -> list[str]:
    """Authors stored as a list, a JSON string, or a plain string."""
    if not value:
        return []
    if isinstance(value, list):
        return clean_names(value)
    text = str(value).strip()
    if text.startswith("["):
        try:
            return clean_names(json.loads(text))
        except json.JSONDecodeError:
            pass
    return clean_names([text])


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def _path(root: Path | None = None) -> Path:
    return Path(root or config.ROOT) / AUTHORS_FILE


def load(root: Path | None = None) -> dict:
    p = _path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_entry(file_name: str, names: list[str], source: str, root: Path | None = None, force: bool = False) -> bool:
    """Store authors for one paper. A manual entry is only replaced by another manual one."""
    names = clean_names(names)
    with _lock:
        data = load(root)
        current = data.get(file_name)
        if current and current.get("source") == MANUAL and source != MANUAL and not force:
            return False
        if names:
            data[file_name] = {"authors": names, "source": source}
        else:
            data.pop(file_name, None)
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def pick(file_name: str, meta_authors, store: dict | None = None) -> tuple[list[str], str]:
    """Final authors for a paper: manual entry, then harvest metadata, then a looked-up entry."""
    store = load() if store is None else store
    entry = store.get(file_name) or {}
    if entry.get("source") == MANUAL and entry.get("authors"):
        return clean_names(entry["authors"]), MANUAL
    meta = as_list(meta_authors)
    if meta:
        return meta, "metadata"
    if entry.get("authors"):
        return clean_names(entry["authors"]), entry.get("source", "")
    return [], ""


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _get(url: str, **kwargs):
    headers = dict(config.HEADERS)
    headers["User-Agent"] = f"CosmoLab/1.0 (mailto:{config.EMAIL})"
    try:
        r = requests.get(url, headers=headers, timeout=15, **kwargs)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def by_doi(doi: str) -> list[str]:
    doi = (doi or "").replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not doi:
        return []
    r = _get(f"{config.CROSSREF_API_URL}/{doi}")
    if r is not None:
        names = from_crossref(r.json().get("message", {}).get("author"))
        if names:
            return names
    r = _get(f"{config.OPENALEX}/doi:{doi}", params={"mailto": config.EMAIL})
    if r is not None:
        return from_openalex(r.json())
    return []


def _arxiv_id(rec: dict) -> str:
    candidates = [rec.get("arxiv_id")] + [v for v in (rec.get("id"), rec.get("url")) if "arxiv" in str(v or "").lower()]
    for value in candidates:
        m = re.search(r"(\d{4}\.\d{4,5})", str(value or ""))
        if m:
            return m.group(1)
    return ""


def by_arxiv(arxiv_id: str) -> list[str]:
    if not arxiv_id:
        return []
    r = _get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id})
    if r is None:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    if entry is None:
        return []
    return clean_names(a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns))


def by_title(title: str, min_similarity: float = 0.9) -> tuple[list[str], str]:
    """Search by title and accept only a close title match. Returns (names, source)."""
    from .verify import title_similarity

    if not title or title.lower().startswith("paper doi"):
        return [], ""
    r = _get(config.OPENALEX, params={"search": title, "per_page": 5, "mailto": config.EMAIL})
    if r is not None:
        for work in r.json().get("results", []):
            if title_similarity(title, work.get("title") or "") >= min_similarity:
                names = from_openalex(work)
                if names:
                    return names, "openalex"
    r = _get(config.CROSSREF_API_URL, params={"query.bibliographic": title, "rows": 5, "mailto": config.EMAIL})
    if r is not None:
        for item in r.json().get("message", {}).get("items", []):
            found = (item.get("title") or [""])[0]
            if title_similarity(title, found) >= min_similarity:
                names = from_crossref(item.get("author"))
                if names:
                    return names, "crossref"
    return [], ""


AI_PROMPT = (
    "Below is the first page of an academic paper. List the names of its authors exactly as printed. "
    "Do not include affiliations, emails, editors, or people who are only cited. "
    'Answer with JSON only: {"authors": ["Name One", "Name Two"]}. '
    'If no author names are printed, answer {"authors": []}.'
)


def _first_page(file_name: str) -> str:
    txt = config.TEXT_DIR / f"{Path(file_name).stem}.txt"
    if txt.exists():
        try:
            return txt.read_text(encoding="utf-8")[:3000]
        except OSError:
            return ""
    return ""


def _appears_in(name: str, text: str) -> bool:
    """Every word of the name must be in the page, so the model cannot invent one."""
    words = [w for w in re.findall(r"[^\W\d_]+", name.lower()) if len(w) > 1]
    page = text.lower()
    return bool(words) and all(w in page for w in words)


def by_pdf_ai(file_name: str, model: str | None = None) -> list[str]:
    page = _first_page(file_name)
    if not page.strip():
        return []
    from .analyze import _get_client

    try:
        resp = _get_client().chat.completions.create(
            model=model or config.LLM_MODEL,
            messages=[{"role": "system", "content": AI_PROMPT}, {"role": "user", "content": page}],
            temperature=0,
        )
        text = resp.choices[0].message.content or ""
    except Exception:
        return []
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        names = json.loads(m.group(0)).get("authors") or []
    except (json.JSONDecodeError, AttributeError):
        return []
    return [n for n in clean_names(names) if _appears_in(n, page)][:20]


def resolve(rec: dict, use_ai: bool = True) -> tuple[list[str], str]:
    """Look up authors for one metadata record. Returns (names, source)."""
    names = by_doi(rec.get("doi"))
    if names:
        return names, "doi"
    names = by_arxiv(_arxiv_id(rec))
    if names:
        return names, "arxiv"
    names, src = by_title(rec.get("title") or "")
    if names:
        return names, src
    if use_ai and rec.get("file"):
        names = by_pdf_ai(rec["file"])
        if names:
            return names, "pdf_ai"
    return [], ""


def latest_records() -> dict:
    """Last metadata record per file (later lines win, like db.sync_all)."""
    from .storage import read_meta

    out = {}
    for rec in read_meta():
        if rec.get("file"):
            out[rec["file"]] = {**out.get(rec["file"], {}), **{k: v for k, v in rec.items() if v not in (None, "")}}
    return out


def fill_missing(use_ai: bool = True, refresh: bool = False, progress=None) -> dict:
    """Look up authors for every paper that has none yet. Returns counts per source."""
    store = load()
    stats = {"checked": 0, "found": 0, "not_found": 0, "sources": {}}
    for file_name, rec in latest_records().items():
        current, _ = pick(file_name, rec.get("authors"), store)
        if current and not refresh:
            continue
        if store.get(file_name, {}).get("source") == MANUAL:
            continue
        stats["checked"] += 1
        names, src = resolve(rec, use_ai=use_ai)
        if names:
            save_entry(file_name, names, src)
            stats["found"] += 1
            stats["sources"][src] = stats["sources"].get(src, 0) + 1
        else:
            stats["not_found"] += 1
        if progress:
            progress(file_name, names, src)
    return stats
