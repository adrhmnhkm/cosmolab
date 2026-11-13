"""
cosmolab.coverage
~~~~~~~~~~~~~~~~~
Fill in the works a student's draft cites, so the similarity check compares
against their full text instead of only abstracts.

For every entry in the draft's reference list, in order:
1. already in the project collection (matched by DOI or title): nothing to do;
2. has a DOI: download the open-access PDF (Unpaywall);
3. no DOI or no open copy: search the title on OpenAlex, Semantic Scholar,
   DOAJ and CORE and download a legal open PDF when the title matches;
4. the entry has a URL (often an OJS article page): download from there;
5. otherwise: ask the student for it. Books are rarely open; the student can
   send the pages they cited.

Only legal sources are used: open access copies, official repositories, and
files the student sends. No shadow libraries.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from . import verify
from .utils import fire_cb as _fire_cb

# Per-reference status
IN_COLLECTION = "koleksi"      # full text was already in the project
DOWNLOADED = "diunduh"         # full text downloaded now
UPLOADED = "dikirim"           # full text uploaded by the consultant / student
ABSTRACT = "abstrak"           # only the abstract could be compared
MISSING = "tidak_tersedia"     # nothing to compare: ask the student

STATUS_LABELS = {
    IN_COLLECTION: "Teks lengkap (sudah di koleksi)",
    DOWNLOADED: "Teks lengkap (diunduh otomatis)",
    UPLOADED: "Teks lengkap (dikirim mahasiswa)",
    ABSTRACT: "Abstrak saja",
    MISSING: "Tidak tersedia, minta ke mahasiswa",
}
FULL_TEXT = {IN_COLLECTION, DOWNLOADED, UPLOADED}

KINDS = {"buku": "Buku", "jurnal": "Artikel jurnal", "skripsi": "Skripsi/tesis", "peraturan": "Peraturan",
         "situs": "Situs web", "lainnya": "Lainnya"}

_URL_RE = re.compile(r"https?://[^\s<>\")\]]+")
_OJS_VIEW_RE = re.compile(r"(/article/)view(/\d+/\d+)")


def guess_kind(raw: str) -> str:
    low = raw.lower()
    if re.search(r"\b(undang-undang|peraturan|keputusan menteri|perpres|permen\w*|uu no|pp no)\b", low):
        return "peraturan"
    if re.search(r"\b(skripsi|tesis|disertasi|thesis|dissertation)\b", low):
        return "skripsi"
    if re.search(r"\d+\s*\(\s*\d+\s*\)|\bvol\.?\s*\d|\bjurnal\b|\bjournal\b|\bno\.\s*\d", low):
        return "jurnal"
    if re.search(r"\b(press|penerbit|publisher|publishing|pustaka|rajawali|erlangga|alfabeta|kencana|"
                 r"routledge|springer|wiley|sage|edisi|edition|ed\.)\b", low):
        return "buku"
    if _URL_RE.search(raw):
        return "situs"
    return "lainnya"


def entry_url(raw: str) -> str:
    """A downloadable URL in a reference entry. OJS article pages point at their download link."""
    m = _URL_RE.search(raw or "")
    if not m:
        return ""
    url = m.group(0).rstrip(".,;")
    if "doi.org/" in url:
        return ""  # DOIs are handled separately
    return _OJS_VIEW_RE.sub(r"\1download\2", url)


def _in_collection(ref: dict, corpus: list[dict]) -> dict | None:
    doi = (ref.get("doi") or "").lower()
    for p in corpus:
        if doi and (p.get("doi") or "").lower() == doi:
            return p
    if ref.get("title"):
        for p in corpus:
            if verify.title_similarity(ref["title"], p.get("title") or "") >= verify.TITLE_MATCH:
                return p
    return None


def _year(ref: dict) -> str:
    return (ref.get("years") or [""])[0]


def _authors_of(ref: dict) -> list[str]:
    return [ref["authors"]] if ref.get("authors") else []


def _by_doi(ref: dict) -> dict | None:
    from . import harvest

    url = harvest._resolve_unpaywall(ref["doi"])
    if not url:
        return None
    res = harvest.import_pdf_url(url, ref.get("matched_title") or ref.get("title") or ref["doi"], _year(ref),
                                 doi=ref["doi"], authors=_authors_of(ref), source="pembanding/doi")
    return res if res.get("ok") else None


def _by_title(ref: dict) -> dict | None:
    from . import harvest

    title = ref.get("title") or ""
    if len(title) < 15:
        return None
    for search in (harvest._search_openalex, harvest._search_semanticscholar, harvest._search_doaj, harvest._search_core):
        try:
            works = search(title, 5)
        except Exception:
            continue
        for w in works:
            if verify.title_similarity(title, w.get("title") or "") < verify.TITLE_MATCH:
                continue
            url = harvest._pdf_url(w)
            if not url:
                continue
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            res = harvest.import_pdf_url(url, w.get("title") or title, str(w.get("publication_year") or _year(ref)),
                                         doi=doi, authors=_authors_of(ref), source=f"pembanding/{w.get('source', 'openalex')}")
            if res.get("ok"):
                return res
    return None


def _by_url(ref: dict) -> dict | None:
    from . import harvest

    url = entry_url(ref.get("raw") or "")
    if not url:
        return None
    res = harvest.import_pdf_url(url, ref.get("title") or url, _year(ref), authors=_authors_of(ref),
                                 source="pembanding/url")
    return res if res.get("ok") else None


def _fetch_one(ref: dict, steps) -> tuple[str, str]:
    """Try each legal source in turn. Returns (status, file)."""
    for step in steps:
        try:
            res = step(ref)
        except Exception:
            res = None
        if res:
            return DOWNLOADED, res["file"]
    return MISSING, ""


DEFAULT_STEPS = (_by_doi, _by_title, _by_url)


def fill(report: dict, corpus: list[dict] | None = None, steps=DEFAULT_STEPS, workers: int = 4,
         progress_cb=None) -> dict:
    """Fill in the cited works for a review and record per-reference coverage in report["coverage"].

    References already tried before are not downloaded again; only their
    collection match is refreshed (the student may have sent a file since).
    """
    from . import db, similarity

    if corpus is None:
        corpus = similarity.corpus_sources()
    refs = report["citations"]["references"]
    old = {it["raw"]: it for it in (report.get("coverage") or {}).get("items", [])}
    items, todo = [], []
    for i, ref in enumerate(refs):
        prev = old.get(ref["raw"], {})
        item = {"i": i, "raw": ref["raw"], "title": ref.get("title") or "", "doi": ref.get("doi") or "",
                "kind": guess_kind(ref["raw"]), "status": MISSING, "file": "", "tried": prev.get("tried", False)}
        hit = _in_collection(ref, corpus)
        if hit:
            item["status"] = prev["status"] if prev.get("status") in FULL_TEXT else IN_COLLECTION
            item["file"] = hit.get("file") or ""
        elif not item["tried"]:
            todo.append((item, ref))
        items.append(item)

    _fire_cb(progress_cb, "start", f"{len(todo)} sumber dicari ({len(refs) - len(todo)} sudah dicek sebelumnya).",
             {"total": len(todo)})
    new_files = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_fetch_one, ref, steps): item for item, ref in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            item = futures[fut]
            item["status"], item["file"] = fut.result()
            item["tried"] = True
            if item["file"]:
                new_files.append(item["file"])
            _fire_cb(progress_cb, "item", f"{n}/{len(todo)} · {STATUS_LABELS[item['status']]}: {item['raw'][:80]}",
                     {"done": n, "total": len(todo)})
    for f in new_files:
        db.sync_one(f)

    report["coverage"] = {"checked_at": datetime.now().isoformat(timespec="seconds"), "items": items}
    return report


def add_upload(report: dict, index: int, file_bytes: bytes, filename: str) -> dict:
    """Store a file the student sent for one reference and mark it covered."""
    from . import db, harvest

    ref = report["citations"]["references"][index]
    res = harvest.import_local_pdf(file_bytes, filename, title=ref.get("title") or ref["raw"][:120],
                                   year=_year(ref), authors=_authors_of(ref))
    db.sync_one(res["file"])
    for it in (report.get("coverage") or {}).get("items", []):
        if it["i"] == index:
            it.update(status=UPLOADED, file=res["file"], tried=True)
    return report


def apply_abstracts(report: dict) -> dict:
    """Mark references whose abstract the similarity check used. Call after the check."""
    cov, sim = report.get("coverage"), report.get("similarity") or {}
    if not cov:
        return report
    dois = set(sim.get("cited_dois") or [])
    for it in cov["items"]:
        if it["status"] == MISSING and it["doi"] and it["doi"].lower() in dois:
            it["status"] = ABSTRACT
        elif it["status"] == ABSTRACT and it["doi"].lower() not in dois:
            it["status"] = MISSING
    return report


def summary(report: dict) -> dict | None:
    cov = report.get("coverage")
    if not cov:
        return None
    items = cov["items"]
    missing = [it for it in items if it["status"] == MISSING]
    by_kind = {}
    for it in missing:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    return {
        "total": len(items),
        "full_text": sum(1 for it in items if it["status"] in FULL_TEXT),
        "abstract": sum(1 for it in items if it["status"] == ABSTRACT),
        "missing": len(missing),
        "missing_by_kind": by_kind,
    }


def summary_text(s: dict) -> str:
    kinds = ", ".join(f"{n} {KINDS[k].lower()}" for k, n in sorted(s["missing_by_kind"].items(), key=lambda kv: -kv[1]))
    return (f"Dari {s['total']} sumber di daftar pustaka: {s['full_text']} dibandingkan dengan teks lengkap, "
            f"{s['abstract']} dengan abstrak saja, {s['missing']} tidak bisa dibandingkan"
            + (f" ({kinds})." if kinds else "."))
