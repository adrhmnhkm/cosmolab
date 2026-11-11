"""
Citation snowballing: find papers linked to the collection by citations.

- Backward: papers that collection papers cite (their reference lists).
  Good for finding seminal or foundational work.
- Forward: newer papers that cite collection papers.
  Good for finding follow-up work and recent debate.

Semantic Scholar is asked first. When it gives nothing (no match, or rate
limited without an API key), OpenAlex is used for that paper instead.

Candidates already in the collection are left out. The rest are ranked by how
many collection papers they are linked to, then by citation count. Nothing is
downloaded until a researcher picks candidates and calls `import_candidate`.
"""

import re
import time
from pathlib import Path

from . import config
from . import authors as _authors
from . import dois as _dois

S2_API = "https://api.semanticscholar.org/graph/v1/paper"
S2_FIELDS = "title,year,externalIds,citationCount,openAccessPdf,authors,venue"
BACKWARD = "backward"
FORWARD = "forward"
DIRECTION_LABELS = {BACKWARD: "dirujuk koleksi", FORWARD: "mengutip koleksi"}


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _http_get(url: str, **kwargs):
    from .harvest import _request_with_retry

    headers = dict(config.HEADERS)
    headers["User-Agent"] = f"CosmoLab/1.0 (mailto:{config.EMAIL})"
    key = config.env_config.get("SEMANTIC_SCHOLAR_API_KEY") if "semanticscholar" in url else None
    if key:
        headers["x-api-key"] = key
    r = _request_with_retry("GET", url, headers=headers, timeout=25, max_retries=2, backoff=2.0, **kwargs)
    return r if r is not None and r.status_code == 200 else None


# ---------------------------------------------------------------------------
# Candidate records
# ---------------------------------------------------------------------------

def _candidate(title, year, doi, arxiv_id, authors, citations, pdf_url, venue, source) -> dict:
    doi = _dois.clean_doi(doi)
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    return {
        "title": (title or "").strip(),
        "year": str(year or ""),
        "doi": doi,
        "arxiv_id": arxiv_id or "",
        "authors": _authors.clean_names(authors or []),
        "citations": int(citations or 0),
        "pdf_url": pdf_url or "",
        "venue": venue or "",
        "source": source,
    }


def _from_s2(paper: dict) -> dict | None:
    if not paper or not paper.get("title"):
        return None
    ext = paper.get("externalIds") or {}
    oa = paper.get("openAccessPdf") or {}
    return _candidate(
        paper.get("title"), paper.get("year"), ext.get("DOI"), ext.get("ArXiv"),
        [a.get("name") for a in paper.get("authors") or []], paper.get("citationCount"),
        oa.get("url"), paper.get("venue"), "semanticscholar",
    )


def _from_openalex(work: dict) -> dict | None:
    if not work or not work.get("title"):
        return None
    loc = work.get("best_oa_location") or {}
    arxiv = ""
    for l in work.get("locations") or []:
        arxiv = _dois.arxiv_id((l or {}).get("landing_page_url")) if "arxiv" in str((l or {}).get("landing_page_url") or "") else ""
        if arxiv:
            break
    venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
    return _candidate(
        work.get("title"), work.get("publication_year"), work.get("doi"), arxiv,
        _authors.from_openalex(work), work.get("cited_by_count"), loc.get("pdf_url"), venue, "openalex",
    )


# ---------------------------------------------------------------------------
# Lookups per seed paper
# ---------------------------------------------------------------------------

def s2_key(seed: dict) -> str:
    """Semantic Scholar paper id for a collection paper: DOI or arXiv id."""
    doi = _dois.clean_doi(seed.get("doi"))
    if doi and not doi.lower().startswith(_dois.ARXIV_DOI_PREFIX.lower()):
        return f"DOI:{doi}"
    aid = seed.get("arxiv_id") or _dois.arxiv_id_of(seed)
    if aid:
        return f"ARXIV:{aid}"
    return f"DOI:{doi}" if doi else ""


def s2_links(seed: dict, direction: str, limit: int = 100) -> list[dict] | None:
    """Linked papers from Semantic Scholar, or None when it could not answer."""
    key = s2_key(seed)
    if not key:
        return None
    endpoint = "references" if direction == BACKWARD else "citations"
    r = _http_get(f"{S2_API}/{key}/{endpoint}", params={"fields": S2_FIELDS, "limit": limit})
    if r is None:
        return None
    field = "citedPaper" if direction == BACKWARD else "citingPaper"
    out = []
    for row in r.json().get("data") or []:
        cand = _from_s2(row.get(field))
        if cand:
            out.append(cand)
    return out


OA_SELECT = "id,doi,title,publication_year,authorships,cited_by_count,best_oa_location,primary_location,locations,referenced_works"


def _openalex_work(seed: dict) -> dict | None:
    doi = _dois.clean_doi(seed.get("doi"))
    if doi:
        r = _http_get(f"{config.OPENALEX}/doi:{doi}", params={"mailto": config.EMAIL})
        if r is not None:
            return r.json()
    title = seed.get("title") or ""
    if title:
        from .verify import title_similarity

        r = _http_get(config.OPENALEX, params={"search": title, "per_page": 3, "mailto": config.EMAIL})
        if r is not None:
            for work in r.json().get("results") or []:
                if title_similarity(title, work.get("title") or "") >= 0.9:
                    return work
    return None


def openalex_links(seed: dict, direction: str, limit: int = 100) -> list[dict]:
    work = _openalex_work(seed)
    if not work:
        return []
    out = []
    if direction == BACKWARD:
        ids = [w.rsplit("/", 1)[-1] for w in (work.get("referenced_works") or [])][:limit]
        for i in range(0, len(ids), 50):
            r = _http_get(config.OPENALEX, params={
                "filter": "openalex_id:" + "|".join(ids[i:i + 50]), "per_page": 50,
                "select": OA_SELECT, "mailto": config.EMAIL})
            if r is not None:
                out += [c for c in (_from_openalex(w) for w in r.json().get("results") or []) if c]
    else:
        wid = (work.get("id") or "").rsplit("/", 1)[-1]
        if wid:
            r = _http_get(config.OPENALEX, params={
                "filter": f"cites:{wid}", "sort": "cited_by_count:desc", "per_page": min(limit, 100),
                "select": OA_SELECT, "mailto": config.EMAIL})
            if r is not None:
                out += [c for c in (_from_openalex(w) for w in r.json().get("results") or []) if c]
    return out


def links_for(seed: dict, direction: str, limit: int = 100) -> tuple[list[dict], str]:
    """(linked papers, source used) for one collection paper."""
    found = s2_links(seed, direction, limit)
    if found:
        return found, "semanticscholar"
    return openalex_links(seed, direction, limit), "openalex"


# ---------------------------------------------------------------------------
# Snowball over the collection
# ---------------------------------------------------------------------------

def _corpus_index(papers: list[dict]) -> tuple[set, set, set]:
    dois, arxiv, titles = set(), set(), set()
    for p in papers:
        d = _dois.clean_doi(p.get("doi")).lower()
        if d:
            dois.add(d)
        a = p.get("arxiv_id") or _dois.arxiv_id_of(p)
        if a:
            arxiv.add(a)
            dois.add((_dois.ARXIV_DOI_PREFIX + a).lower())
        t = _norm_title(p.get("title"))
        if t:
            titles.add(t)
    return dois, arxiv, titles


def _cand_key(c: dict) -> str:
    if c["doi"]:
        return "doi:" + c["doi"].lower()
    if c["arxiv_id"]:
        return "arxiv:" + c["arxiv_id"]
    return "title:" + _norm_title(c["title"])


def merge(seed_links: list[tuple[dict, str, list[dict]]], corpus: list[dict]) -> list[dict]:
    """Combine links from many seeds into ranked candidates, dropping papers already collected.

    seed_links: [(seed paper, direction, linked candidates), ...]
    """
    dois, arxiv, titles = _corpus_index(corpus)
    merged: dict[str, dict] = {}
    for seed, direction, cands in seed_links:
        seed_title = seed.get("title") or seed.get("file") or ""
        for c in cands:
            if not c.get("title"):
                continue
            if (c["doi"] and c["doi"].lower() in dois) or (c["arxiv_id"] and c["arxiv_id"] in arxiv) \
                    or _norm_title(c["title"]) in titles:
                continue
            key = _cand_key(c)
            m = merged.get(key)
            if m is None:
                m = merged[key] = {**c, "linked_from": [], "directions": []}
            else:
                for f in ("doi", "arxiv_id", "pdf_url", "venue", "year"):
                    m[f] = m[f] or c[f]
                m["authors"] = m["authors"] or c["authors"]
                m["citations"] = max(m["citations"], c["citations"])
            if seed_title not in m["linked_from"]:
                m["linked_from"].append(seed_title)
            if direction not in m["directions"]:
                m["directions"].append(direction)
    out = list(merged.values())
    for m in out:
        m["link_count"] = len(m["linked_from"])
    out.sort(key=lambda m: (-m["link_count"], -m["citations"], m["title"]))
    return out


def snowball(seeds: list[dict], corpus: list[dict], directions=(BACKWARD, FORWARD), limit: int = 100,
             progress=None, pause: float = 1.0) -> dict:
    """Run backward and/or forward snowballing for the given collection papers.

    Returns {"candidates": [...], "sources": {"semanticscholar": n, "openalex": n}, "checked": n}.
    """
    seed_links, sources = [], {}
    steps = [(s, d) for s in seeds for d in directions]
    for i, (seed, direction) in enumerate(steps, 1):
        cands, src = links_for(seed, direction, limit)
        sources[src] = sources.get(src, 0) + 1
        seed_links.append((seed, direction, cands))
        if progress:
            progress(i, len(steps), seed, direction, len(cands), src)
        if pause and i < len(steps):
            time.sleep(pause)  # Semantic Scholar allows about one request per second without a key
    return {"candidates": merge(seed_links, corpus), "sources": sources, "checked": len(seeds)}


# ---------------------------------------------------------------------------
# Import a picked candidate
# ---------------------------------------------------------------------------

def import_candidate(cand: dict, faculty: str = None) -> dict:
    """Download a candidate's open-access PDF and add it to the collection."""
    from . import faculties as _faculties
    from .harvest import _download, import_by_doi
    from .storage import append_meta, safe_name

    config.ensure_dirs()
    pdf_url = cand.get("pdf_url") or ""
    if not pdf_url:
        if cand.get("doi"):
            return import_by_doi(cand["doi"], faculty=faculty)
        return {"error": "Tidak ada versi terbuka (open access) untuk paper ini."}

    title = cand.get("title") or "untitled"
    year = cand.get("year") or ""
    fname = f"{year}_{safe_name(title)}.pdf" if year else f"{safe_name(title)}.pdf"
    dest = config.PDF_DIR / fname
    if not _download(pdf_url, dest):
        if cand.get("doi"):
            return import_by_doi(cand["doi"], faculty=faculty)
        return {"error": f"Gagal mengunduh PDF dari {pdf_url}"}

    item_faculty = faculty or _faculties.detect_faculty_from_text(title)
    append_meta({
        "id": f"snowball:{_cand_key(cand)}",
        "title": title,
        "year": year,
        "doi": cand.get("doi") or _dois.arxiv_doi(cand.get("arxiv_id")),
        "url": pdf_url,
        "file": fname,
        "abstract": "",
        "source": f"snowball/{cand.get('source', '')}",
        "arxiv_id": cand.get("arxiv_id") or "",
        "faculty": item_faculty,
        "authors": cand.get("authors") or [],
    })
    from . import extract

    try:
        text = extract._pdf_to_text(dest)
        if text.strip():
            (config.TEXT_DIR / f"{Path(fname).stem}.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "title": title, "file": fname, "faculty": item_faculty}
