"""SINTA journal ranks, matched to papers by ISSN.

SINTA (sinta.kemdiktisaintek.go.id) has no public API, and scraping it is not
allowed without permission. CosmoLab therefore keeps a local list that the team
fills in: import a CSV, or add journals one at a time from what the SINTA site
shows. The list is shared by every project. Each entry keeps the date it was
checked, because ranks change at reaccreditation.

A paper with no matching entry gets no label. That means "not in our list",
never "not accredited".
"""

import csv
import json
import os
import re
from datetime import date
from pathlib import Path

import requests

from . import config
from .storage import read_meta

RANKS = (1, 2, 3, 4, 5, 6)
JOURNALS_FILE = "journals.json"  # per project: journal and ISSN found for each paper


def list_path() -> Path:
    raw = config.env_config.get("COSMOLAB_SINTA_FILE") or os.environ.get("COSMOLAB_SINTA_FILE")
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else config.PROJECT_ROOT / p
    return config.PROJECT_ROOT / "shared" / "sinta_journals.json"


# ── ISSN ─────────────────────────────────────────────────────────────────────

def normalize_issn(raw) -> str:
    """'2087 123x' -> '2087-123X'. Returns '' if it is not a valid ISSN (checksum included)."""
    s = re.sub(r"[^0-9Xx]", "", str(raw or "")).upper()
    if len(s) != 8 or "X" in s[:7]:
        return ""
    total = sum(int(d) * w for d, w in zip(s[:7], range(8, 1, -1)))
    check = (11 - total % 11) % 11
    if s[7] != ("X" if check == 10 else str(check)):
        return ""
    return f"{s[:4]}-{s[4:]}"


ISSN_RE = re.compile(r"\d{4}\s*-?\s*\d{3}[\dXx]")


def split_issns(text: str) -> list[str]:
    """Every ISSN-looking string in free text: '2087-1236, 0378 5955' -> two."""
    return ISSN_RE.findall(str(text or ""))


def _issns(values) -> list[str]:
    out = []
    for v in values or []:
        n = normalize_issn(v)
        if n and n not in out:
            out.append(n)
    return out


def parse_rank(raw) -> int | None:
    """'S2', 'SINTA 2', 'Sinta-2', '2' -> 2. Anything else -> None."""
    s = str(raw or "").strip().lower()
    m = re.fullmatch(r"([1-6])", s) or re.search(r"\bs(?:inta)?\s*[-_ ]?\s*([1-6])\b", s)
    return int(m.group(1)) if m else None


# ── The shared list ──────────────────────────────────────────────────────────

def load() -> list[dict]:
    p = list_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("journals", [])
    except (json.JSONDecodeError, OSError):
        return []


def save(entries: list[dict]) -> None:
    p = list_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    entries = sorted(entries, key=lambda e: (e["rank"], e.get("name", "").lower()))
    p.write_text(json.dumps({"journals": entries}, ensure_ascii=False, indent=1), encoding="utf-8")


def index(entries: list[dict] | None = None) -> dict:
    """ISSN -> entry."""
    out = {}
    for e in load() if entries is None else entries:
        for i in e.get("issns", []):
            out[i] = e
    return out


def _upsert(entries: list[dict], name: str, issns: list[str], rank: int, checked: str) -> str:
    """Add or update one journal in entries. Returns 'added' or 'updated'."""
    for e in entries:
        if set(e["issns"]) & set(issns):
            e["issns"] = _issns(e["issns"] + issns)
            e["rank"], e["checked"] = rank, checked
            if name:
                e["name"] = name
            return "updated"
    entries.append({"name": name, "issns": issns, "rank": rank, "checked": checked})
    return "added"


def add(name: str, issns, rank, checked: str | None = None) -> dict:
    """Add or update one journal. Raises ValueError on a bad ISSN or rank."""
    clean = _issns(issns if isinstance(issns, (list, tuple)) else split_issns(issns))
    if not clean:
        raise ValueError("ISSN tidak valid. Contoh yang benar: 2087-1236")
    r = parse_rank(rank)
    if r is None:
        raise ValueError("Peringkat SINTA harus 1 sampai 6.")
    entries = load()
    status = _upsert(entries, (name or "").strip(), clean, r, checked or date.today().isoformat())
    save(entries)
    return {"status": status, "issns": clean, "rank": r}


def remove(issn: str) -> bool:
    n = normalize_issn(issn)
    entries = load()
    kept = [e for e in entries if n not in e["issns"]]
    if len(kept) == len(entries):
        return False
    save(kept)
    return True


NAME_COLS = ("nama", "name", "jurnal", "journal", "title", "judul")
RANK_COLS = ("peringkat", "rank", "sinta", "akreditasi", "accreditation", "grade")
DATE_COLS = ("dicek", "checked", "tanggal", "date")


def _pick(headers: list[str], names: tuple) -> str | None:
    for h in headers:
        if h.strip().lower() in names:
            return h
    for h in headers:
        if any(n in h.strip().lower() for n in names) and "issn" not in h.lower():
            return h
    return None


def import_csv(path) -> dict:
    """Import journals from a CSV with columns for name, ISSN(s) and rank.

    Column names are matched loosely: any column with 'issn' in its name is an
    ISSN column; rank can be 'peringkat', 'sinta', 'akreditasi', ...
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    except (csv.Error, IndexError):
        dialect = csv.excel
    rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    headers = list(rows[0].keys()) if rows else []
    issn_cols = [h for h in headers if "issn" in h.lower()]
    rank_col, name_col, date_col = _pick(headers, RANK_COLS), _pick(headers, NAME_COLS), _pick(headers, DATE_COLS)
    if not issn_cols or not rank_col:
        raise ValueError("CSV perlu kolom ISSN dan kolom peringkat (misalnya 'issn', 'eissn', 'peringkat').")

    entries = load()
    stats = {"added": 0, "updated": 0, "skipped": []}
    today = date.today().isoformat()
    for n, row in enumerate(rows, start=2):
        issns = _issns(split_issns(" ".join(row.get(c) or "" for c in issn_cols)))
        rank = parse_rank(row.get(rank_col))
        if not issns or rank is None:
            stats["skipped"].append(n)
            continue
        checked = (row.get(date_col) or "").strip() if date_col else ""
        stats[_upsert(entries, (row.get(name_col) or "").strip() if name_col else "", issns, rank, checked or today)] += 1
    save(entries)
    return stats


# ── Papers ───────────────────────────────────────────────────────────────────

def _journals_path() -> Path:
    return config.ROOT / JOURNALS_FILE


def _load_journals() -> dict:
    p = _journals_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def journals_by_file() -> dict:
    """file -> {'journal', 'issn'} from harvest metadata plus looked-up journals."""
    out = {}
    for rec in read_meta():
        if rec.get("file") and rec.get("issn"):
            out[rec["file"]] = {"journal": rec.get("journal", ""), "issn": _issns(rec["issn"])}
    for f, j in _load_journals().items():
        out.setdefault(f, {"journal": j.get("journal", ""), "issn": _issns(j.get("issn"))})
    return out


def rank_for(issns, idx: dict | None = None) -> dict | None:
    idx = index() if idx is None else idx
    for i in _issns(issns):
        if i in idx:
            return idx[i]
    return None


def label(entry: dict) -> str:
    return f"SINTA {entry['rank']}"


def _openalex_journal(doi: str) -> dict | None:
    r = requests.get(f"{config.OPENALEX}/doi:{doi}", params={"select": "primary_location", "mailto": config.EMAIL},
                     headers=config.HEADERS, timeout=20)
    if r.status_code != 200:
        return None
    src = ((r.json().get("primary_location") or {}).get("source")) or {}
    issns = _issns([src.get("issn_l")] + list(src.get("issn") or []))
    return {"journal": src.get("display_name") or "", "issn": issns} if issns else None


def fill_journals(fetch=None, limit: int | None = None) -> dict:
    """Look up the journal and ISSN of papers that have a DOI but no ISSN yet.

    Results are saved per project in journals.json. fetch(doi) -> dict | None
    can be swapped in tests.
    """
    fetch = fetch or _openalex_journal
    known = journals_by_file()
    cache = _load_journals()
    todo = {}
    for rec in read_meta():
        f, doi = rec.get("file"), (rec.get("doi") or "").replace("https://doi.org/", "").strip()
        if f and doi and f not in known and f not in cache:
            todo[f] = doi
    stats = {"checked": 0, "found": 0}
    for f, doi in list(todo.items())[:limit]:
        stats["checked"] += 1
        try:
            info = fetch(doi)
        except requests.RequestException:
            info = None
        cache[f] = info or {"journal": "", "issn": []}  # remember misses too, so they are not asked again
        stats["found"] += bool(info)
    if stats["checked"]:
        _journals_path().parent.mkdir(parents=True, exist_ok=True)
        _journals_path().write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return stats


def ranks_by_file() -> dict:
    """file -> SINTA entry, for papers whose journal is in the list."""
    idx = index()
    if not idx:
        return {}
    out = {}
    for f, j in journals_by_file().items():
        e = rank_for(j["issn"], idx)
        if e:
            out[f] = e
    return out
