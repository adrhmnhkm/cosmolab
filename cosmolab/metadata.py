"""
cosmolab.metadata
~~~~~~~~~~~~~~~~~
Verify each paper's bibliographic data against Crossref or DataCite (by DOI), flag
retracted or corrected papers, and export clean BibTeX / RIS built from the
verified record.

Results are kept in <root>/review/metadata.json, keyed by paper file.
"""

from __future__ import annotations

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests

from . import config

OK = "cocok"
DIFF = "beda"
NOT_FOUND = "tidak_ditemukan"
INVALID = "doi_tidak_ada"
NO_DOI = "tanpa_doi"
ERROR = "gagal"
STATUS_LABELS = {
    OK: "Cocok dengan Crossref",
    DIFF: "Ada yang beda",
    NOT_FOUND: "DOI ada, tapi datanya tidak tersedia",
    INVALID: "DOI tidak terdaftar di doi.org",
    NO_DOI: "Belum punya DOI",
    ERROR: "Gagal dicek",
}

RETRACTED = "retraction"
CONCERN = "expression_of_concern"
CORRECTION = "correction"
NOTICE_LABELS = {
    RETRACTED: "Ditarik (retracted)",
    "withdrawal": "Ditarik penulis (withdrawn)",
    "removal": "Dihapus penerbit",
    CONCERN: "Ada peringatan editor",
    CORRECTION: "Ada koreksi",
    "erratum": "Ada erratum",
    "corrigendum": "Ada corrigendum",
}
SERIOUS = {RETRACTED, "withdrawal", "removal", CONCERN}


def store_path() -> Path:
    return config.ROOT / "review" / "metadata.json"


def load_store() -> dict:
    try:
        return json.loads(store_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_store(store: dict) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------- lookups

def _headers() -> dict:
    return {"User-Agent": f"CosmoLab/1.0 (mailto:{config.EMAIL})"}


def fetch_crossref(doi: str, timeout: int = 20) -> dict | None:
    """Crossref record for a DOI, or None when Crossref does not know it."""
    r = requests.get(f"{config.CROSSREF_API_URL}/{requests.utils.quote(doi, safe='/:()')}",
                     headers=_headers(), timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("message") or None


def fetch_datacite(doi: str, timeout: int = 20) -> dict | None:
    """DataCite record (arXiv, Zenodo, datasets), converted to Crossref's field names."""
    r = requests.get(f"https://api.datacite.org/dois/{requests.utils.quote(doi, safe='/:()')}",
                     headers=_headers(), timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    a = (r.json().get("data") or {}).get("attributes") or {}
    authors = []
    for c in a.get("creators") or []:
        if c.get("givenName") or c.get("familyName"):
            authors.append({"given": c.get("givenName"), "family": c.get("familyName")})
        elif c.get("name"):
            authors.append({"name": c["name"]})
    year = a.get("publicationYear")
    kind = ((a.get("types") or {}).get("citeproc") or "").replace("article", "posted-content")
    return {
        "title": [t.get("title") for t in a.get("titles") or [] if t.get("title")][:1],
        "author": authors,
        "issued": {"date-parts": [[int(year)]]} if str(year or "").isdigit() else {},
        "publisher": a.get("publisher") or "",
        "container-title": [],
        "type": kind,
        "DOI": a.get("doi") or doi,
        "_source": "datacite",
    }


def doi_registered(doi: str, timeout: int = 15) -> bool | None:
    """Ask doi.org whether the DOI exists at all. None when the check itself fails."""
    try:
        r = requests.get(f"https://doi.org/api/handles/{requests.utils.quote(doi, safe='/:()')}",
                         headers=_headers(), timeout=timeout)
        code = r.json().get("responseCode")
    except Exception:
        return None
    return {1: True, 100: False}.get(code)


def lookup(doi: str) -> tuple[dict | None, str]:
    """(record, source). Tries Crossref, then DataCite. source is "" when neither has it."""
    if not doi.lower().startswith("10.48550/"):
        item = fetch_crossref(doi)
        if item:
            return item, "crossref"
    item = fetch_datacite(doi)
    if item:
        return item, "datacite"
    return None, ""


def fetch_openalex_retracted(doi: str, timeout: int = 20) -> bool | None:
    try:
        r = requests.get(f"{config.OPENALEX}/doi:{doi}", params={"select": "is_retracted"},
                         headers=_headers(), timeout=timeout)
        if r.status_code != 200:
            return None
        return bool(r.json().get("is_retracted"))
    except requests.RequestException:
        return None


# --------------------------------------------------------------- comparing

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _title_sim(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b or (len(a) > 20 and (a in b or b in a)):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _year(item: dict) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return ""


def _authors(item: dict) -> list[str]:
    out = []
    for a in item.get("author") or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name") or ""
        if name:
            out.append(name)
    return out


def _surname(name: str) -> str:
    parts = _norm(name).split()
    return parts[-1] if parts else ""


def _paper_authors(paper: dict) -> list[str]:
    raw = paper.get("authors")
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []


def notices(item: dict) -> list[dict]:
    """Retraction, correction and concern notices attached to a Crossref record."""
    out = []
    for u in item.get("updated-by") or []:
        kind = (u.get("type") or "").lower().replace(" ", "_").replace("-", "_")
        date = ((u.get("updated") or {}).get("date-parts") or [[None]])[0]
        out.append({"type": kind, "label": NOTICE_LABELS.get(kind, u.get("label") or kind),
                    "doi": u.get("DOI"), "year": str(date[0]) if date and date[0] else "",
                    "serious": kind in SERIOUS})
    return out


def compare(paper: dict, item: dict) -> dict:
    """Field-by-field comparison of the collection record with Crossref."""
    cr_title = (item.get("title") or [""])[0]
    cr_year = _year(item)
    cr_authors = _authors(item)
    mine = _paper_authors(paper)
    diffs = []

    sim = _title_sim(paper.get("title") or "", cr_title)
    if sim < 0.85:
        diffs.append({"field": "judul", "ours": paper.get("title"), "crossref": cr_title})
    if paper.get("year") and cr_year and str(paper["year"])[:4] != cr_year:
        diffs.append({"field": "tahun", "ours": paper.get("year"), "crossref": cr_year})
    if mine and cr_authors:
        ours = {_surname(a) for a in mine}
        theirs = {_surname(a) for a in cr_authors}
        if not (ours & theirs):
            diffs.append({"field": "penulis", "ours": ", ".join(mine[:4]), "crossref": ", ".join(cr_authors[:4])})

    return {
        "title_similarity": round(sim, 2),
        "diffs": diffs,
        "crossref": {
            "title": cr_title,
            "year": cr_year,
            "authors": cr_authors,
            "journal": (item.get("container-title") or [""])[0],
            "volume": item.get("volume") or "",
            "issue": item.get("issue") or "",
            "pages": item.get("page") or "",
            "publisher": item.get("publisher") or "",
            "type": item.get("type") or "",
            "doi": item.get("DOI") or "",
        },
    }


def check_paper(paper: dict, fetch=None, retracted_fn=None, registered_fn=None) -> dict:
    """Check one collection paper. The lookup functions can be swapped in tests.

    fetch(doi) returns a Crossref-style record or None.
    """
    fetch = fetch or (lambda d: lookup(d)[0])
    retracted_fn = retracted_fn or fetch_openalex_retracted
    registered_fn = registered_fn or doi_registered
    doi = (paper.get("doi") or "").strip()
    base = {"file": paper.get("file"), "title": paper.get("title"), "doi": doi,
            "time": datetime.now().isoformat(timespec="seconds"), "notices": [], "diffs": []}
    if not doi:
        return {**base, "status": NO_DOI}
    try:
        item = fetch(doi)
    except Exception as e:
        return {**base, "status": ERROR, "error": str(e)[:160]}
    if not item:
        return {**base, "status": INVALID if registered_fn(doi) is False else NOT_FOUND}

    cmp_ = compare(paper, item)
    found = notices(item)
    if not any(n["type"] == RETRACTED for n in found):
        if retracted_fn(doi):
            found.append({"type": RETRACTED, "label": NOTICE_LABELS[RETRACTED], "doi": "", "year": "",
                          "serious": True, "source": "openalex"})
    # Crossref marks retracted titles like "RETRACTED: ..." too.
    if cmp_["crossref"]["title"].upper().startswith("RETRACTED") and not any(n["type"] == RETRACTED for n in found):
        found.append({"type": RETRACTED, "label": NOTICE_LABELS[RETRACTED], "doi": "", "year": "", "serious": True})

    return {**base, "status": DIFF if cmp_["diffs"] else OK, "diffs": cmp_["diffs"],
            "source": item.get("_source", "crossref"),
            "title_similarity": cmp_["title_similarity"], "crossref": cmp_["crossref"], "notices": found}


def check_all(papers: list[dict] | None = None, progress_cb=None, workers: int = 4) -> dict:
    """Check every paper (or the given ones) and save the results. Returns the store."""
    from . import db

    papers = papers if papers is not None else db.get_all_papers_with_analyses()
    store = load_store()
    done = 0

    def one(p):
        return p.get("file"), check_paper(p)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f, res in pool.map(one, papers):
            store[f] = res
            done += 1
            if progress_cb:
                progress_cb(done, len(papers), res.get("title") or f)
    save_store(store)
    try:
        from . import audit

        counts = {}
        for p in papers:
            s = store.get(p.get("file"), {}).get("status")
            counts[s] = counts.get(s, 0) + 1
        audit.log("cek_metadata", summary=counts,
                  retracted=[f for f, r in store.items() if any(n.get("serious") for n in r.get("notices", []))])
    except Exception:
        pass
    return store


def flagged(store: dict | None = None) -> list[dict]:
    """Papers with a serious notice (retracted, withdrawn, concern)."""
    store = load_store() if store is None else store
    return [r for r in store.values() if any(n.get("serious") for n in r.get("notices") or [])]


# --------------------------------------------------------------- export

def _bib_escape(text: str) -> str:
    return (text or "").replace("\\", "").replace("{", "").replace("}", "").replace("&", r"\&").replace("%", r"\%")


def _cite_key(authors: list[str], year: str, title: str, used: set) -> str:
    sur = re.sub(r"[^a-z]", "", _surname(authors[0])) if authors else ""
    word = next((w for w in _norm(title).split() if len(w) > 3), "paper")
    key = f"{sur or 'anon'}{year or 'nd'}{word}"
    base, n = key, 2
    while key in used:
        key = f"{base}{chr(ord('a') + n - 2)}"
        n += 1
    used.add(key)
    return key


def _record(paper: dict, meta: dict | None) -> dict:
    """Best available record: verified Crossref data when it matched, else our own."""
    cr = (meta or {}).get("crossref") or {}
    verified = (meta or {}).get("status") == OK
    use_cr = verified and cr
    return {
        "title": (cr.get("title") if use_cr else None) or paper.get("title") or "Untitled",
        "year": (cr.get("year") if use_cr else None) or str(paper.get("year") or ""),
        "authors": (cr.get("authors") if use_cr else None) or _paper_authors(paper),
        "journal": cr.get("journal") if use_cr else "",
        "volume": cr.get("volume") if use_cr else "",
        "issue": cr.get("issue") if use_cr else "",
        "pages": cr.get("pages") if use_cr else "",
        "publisher": cr.get("publisher") if use_cr else "",
        "doi": (cr.get("doi") if use_cr else None) or paper.get("doi") or "",
        "url": paper.get("url") or "",
        "arxiv": paper.get("arxiv_id") or "",
        "type": cr.get("type") if use_cr else "",
        "verified": bool(use_cr),
        "notices": (meta or {}).get("notices") or [],
    }


def to_bibtex(papers: list[dict], store: dict | None = None) -> str:
    store = load_store() if store is None else store
    used, entries = set(), []
    for p in papers:
        r = _record(p, store.get(p.get("file")))
        kind = {"journal-article": "article", "proceedings-article": "inproceedings", "book-chapter": "incollection",
                "book": "book", "posted-content": "misc"}.get(r["type"], "article" if r["journal"] else "misc")
        fields = [("title", "{" + _bib_escape(r["title"]) + "}")]
        if r["authors"]:
            fields.append(("author", " and ".join(_bib_escape(a) for a in r["authors"])))
        for k in ("year", "volume", "pages", "publisher", "doi", "url"):
            if r[k]:
                fields.append((k, _bib_escape(r[k]).replace("--", "-").replace("-", "--") if k == "pages" else _bib_escape(r[k])))
        if r["journal"]:
            fields.append(("journal" if kind == "article" else "booktitle", _bib_escape(r["journal"])))
        if r["issue"]:
            fields.append(("number", _bib_escape(r["issue"])))
        if r["arxiv"]:
            fields += [("eprint", r["arxiv"]), ("archivePrefix", "arXiv")]
        notes = [n["label"] for n in r["notices"] if n.get("serious")]
        if notes:
            fields.append(("note", "PERHATIAN: " + "; ".join(notes)))
        elif not r["verified"]:
            fields.append(("note", "Metadata belum diverifikasi ke Crossref"))
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
        entries.append(f"@{kind}{{{_cite_key(r['authors'], r['year'], r['title'], used)},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"


def to_ris(papers: list[dict], store: dict | None = None) -> str:
    store = load_store() if store is None else store
    out = []
    for p in papers:
        r = _record(p, store.get(p.get("file")))
        lines = [f"TY  - {'JOUR' if r['journal'] else 'GEN'}", f"TI  - {r['title']}"]
        lines += [f"AU  - {a}" for a in r["authors"]]
        for tag, key in (("PY", "year"), ("JO", "journal"), ("VL", "volume"), ("IS", "issue"),
                         ("PB", "publisher"), ("DO", "doi"), ("UR", "url")):
            if r[key]:
                lines.append(f"{tag}  - {r[key]}")
        if r["pages"]:
            sp, _, ep = r["pages"].partition("-")
            lines.append(f"SP  - {sp}")
            if ep:
                lines.append(f"EP  - {ep}")
        notes = [n["label"] for n in r["notices"] if n.get("serious")]
        if notes:
            lines.append("N1  - PERHATIAN: " + "; ".join(notes))
        elif not r["verified"]:
            lines.append("N1  - Metadata belum diverifikasi ke Crossref")
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"
