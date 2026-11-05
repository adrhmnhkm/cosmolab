import time
import re
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from rich.console import Console
from . import config
from . import faculties as _faculties
from . import authors as _authors
from .utils import fire_cb as _fire_cb
from .storage import safe_name, load_done, save_done, append_meta, read_meta

console = Console(force_terminal=True, legacy_windows=False)

# Configurable blocked hosts (known to return HTML instead of PDF)
BLOCKED_HOSTS: set[str] = {"doiserbia.nb.rs", "dspace.univ-bab.dz"}


def _request_with_retry(method: str, url: str, max_retries: int = 3, backoff: float = 2.0, **kwargs) -> requests.Response | None:
    """HTTP request wrapper with automatic retry on 429 (Too Many Requests) and 5xx errors."""
    kwargs.setdefault("timeout", 30)
    for attempt in range(max_retries):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code == 429 or r.status_code >= 500:
                retry_after = int(r.headers.get("Retry-After", backoff * (2 ** attempt)))
                console.print(f"[yellow]RATE-LIMIT  {r.status_code} from {url[:60]}… retry in {retry_after}s (attempt {attempt+1}/{max_retries})[/yellow]")
                time.sleep(retry_after)
                continue
            return r
        except requests.exceptions.Timeout:
            console.print(f"[yellow]TIMEOUT  {url[:60]}… (attempt {attempt+1}/{max_retries})[/yellow]")
            time.sleep(backoff * (attempt + 1))
        except requests.exceptions.RequestException as e:
            console.print(f"[yellow]REQUEST ERROR  {e} (attempt {attempt+1}/{max_retries})[/yellow]")
            if attempt < max_retries - 1:
                time.sleep(backoff * (attempt + 1))
    return None


def _search_arxiv(query: str, max_results: int):
    """Search arXiv API, return list of dicts with arXiv metadata."""
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending"
    }
    try:
        r = _request_with_retry("GET", url, params=params, headers=config.HEADERS, timeout=30)
        if r is None or r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {"": "http://www.w3.org/2005/Atom"}
        works = []
        for entry in root.findall("entry", ns):
            title = entry.find("title", ns).text if entry.find("title", ns) is not None else ""
            summary = entry.find("summary", ns).text if entry.find("summary", ns) is not None else ""
            pdf_link = None
            for link in entry.findall("link", ns):
                if link.get("title") == "pdf":
                    pdf_link = link.get("href")
            if not pdf_link:
                continue
            works.append({
                "id": pdf_link,
                "title": title.replace("\n", " ").strip(),
                "pdf_url": pdf_link,
                "abstract": summary,
                "arxiv_id": entry.find("id", ns).text if entry.find("id", ns) is not None else "",
                "authors": _authors.clean_names(a.findtext("name", default="", namespaces=ns) for a in entry.findall("author", ns)),
                "published": entry.find("published", ns).text if entry.find("published", ns) is not None else "",
                "publication_year": entry.find("published", ns).text[:4] if entry.find("published", ns) is not None else "",
                "type": "preprint",
                "source": "arxiv",
            })
        return works
    except Exception as e:
        console.print(f"[yellow]WARN  arXiv search error: {e}[/yellow]")
        return []


def _flatten_inverted_abstract(inverted_index: dict) -> str:
    """Convert OpenAlex abstract_inverted_index dict into a plain text string."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    try:
        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)
    except Exception:
        return ""


def _search_openalex(query: str, max_results: int):
    out, cursor = [], "*"
    try:
        while len(out) < max_results:
            r = _request_with_retry("GET", config.OPENALEX, params={
                "search": query,
                "filter": "is_oa:true,type:article",
                "per_page": 25,
                "cursor": cursor,
                "mailto": config.EMAIL,
            }, headers=config.HEADERS, timeout=30)
            if r is None or r.status_code != 200:
                break
            data = r.json()
            for work in data.get("results", []):
                # Flatten inverted abstract to plain text
                abstract = work.get("abstract") or ""
                if not abstract and work.get("abstract_inverted_index"):
                    abstract = _flatten_inverted_abstract(work["abstract_inverted_index"])
                    work["abstract"] = abstract
                out.append(work)
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            time.sleep(1)
    except Exception as e:
        console.print(f"[yellow]WARN  OpenAlex search error: {e}[/yellow]")
    return out[:max_results]


def _search_doaj(query: str, max_results: int):
    """Search DOAJ (Directory of Open Access Journals) for peer-reviewed OA papers."""
    import urllib.parse
    encoded_query = urllib.parse.quote(query)
    url = f"https://doaj.org/api/v2/search/articles/{encoded_query}"
    params = {"pageSize": min(max_results, 30)}
    try:
        r = _request_with_retry("GET", url, params=params, headers=config.HEADERS, timeout=20)
        if r is None or r.status_code != 200:
            return []
        results = r.json().get("results", [])
        works = []
        for it in results:
            bib = it.get("bibjson", {})
            title = bib.get("title", "")
            if not title:
                continue
            year = bib.get("year", "")
            doi = ""
            for id_entry in bib.get("identifier", []):
                if id_entry.get("type") == "doi":
                    doi = id_entry.get("id", "")
                    break
            
            pdf_link = None
            for link in bib.get("link", []):
                if link.get("type") == "fulltext":
                    pdf_link = link.get("url")
                    break

            abstract = bib.get("abstract", "")
            works.append({
                "id": f"doaj:{it.get('id', '')}",
                "authors": _authors.from_named(bib.get("author")),
                "title": title.replace("\n", " ").strip(),
                "pdf_url": pdf_link,
                "abstract": abstract,
                "doi": doi,
                "arxiv_id": "",
                "published": str(year),
                "publication_year": str(year),
                "type": "journal_article",
                "source": "doaj",
            })
        return works
    except Exception:
        return []


def _search_semanticscholar(query: str, max_results: int):
    """Search Semantic Scholar API (AI graph database of 200M+ papers)."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": min(max_results, 25),
        "fields": "paperId,title,year,abstract,openAccessPdf,externalIds,authors"
    }
    headers = dict(config.HEADERS)
    s2_key = config.env_config.get("SEMANTIC_SCHOLAR_API_KEY")
    if s2_key:
        headers["x-api-key"] = s2_key
    try:
        r = _request_with_retry("GET", url, params=params, headers=headers, timeout=15)
        if r is None or r.status_code != 200:
            return []
        data = r.json().get("data", [])
        works = []
        for p in data:
            title = p.get("title")
            if not title:
                continue
            oa_pdf = p.get("openAccessPdf") or {}
            pdf_url = oa_pdf.get("url")
            ext = p.get("externalIds") or {}
            pub_year = str(p.get("year") or "")
            works.append({
                "id": f"s2:{p.get('paperId')}",
                "authors": _authors.from_named(p.get("authors")),
                "title": title.replace("\n", " ").strip(),
                "pdf_url": pdf_url,
                "abstract": p.get("abstract") or "",
                "doi": ext.get("DOI", ""),
                "arxiv_id": ext.get("ArXiv", ""),
                "published": pub_year,
                "publication_year": pub_year,
                "source": "semanticscholar"
            })
        return works
    except Exception:
        return []


def _search_core(query: str, max_results: int):
    """Search CORE API v3 (200M+ open access papers from global university repositories)."""
    if not config.CORE_API_KEY:
        return []
    headers = dict(config.HEADERS)
    headers["Authorization"] = f"Bearer {config.CORE_API_KEY}"
    params = {
        "q": query,
        "limit": min(max_results, 25),
    }
    try:
        r = _request_with_retry("GET", config.CORE_API_URL, params=params, headers=headers, timeout=15)
        if r is None or r.status_code != 200:
            return []
        data = r.json()
        works = []
        for item in data.get("results", []):
            title = item.get("title")
            if not title:
                continue
            pdf_url = item.get("downloadUrl")
            if not pdf_url and item.get("sourceFulltextUrls"):
                for u in item.get("sourceFulltextUrls"):
                    if u.lower().endswith(".pdf"):
                        pdf_url = u
                        break
            year = str(item.get("yearPublished") or "")
            doi = item.get("doi") or ""
            abstract = item.get("abstract") or ""
            works.append({
                "id": f"core:{item.get('id')}",
                "authors": _authors.from_named(item.get("authors")),
                "title": title.replace("\n", " ").strip(),
                "pdf_url": pdf_url,
                "abstract": abstract,
                "doi": doi,
                "arxiv_id": "",
                "published": year,
                "publication_year": year,
                "type": "research_paper",
                "source": "core",
            })
        return works
    except Exception as e:
        console.print(f"[dim]CORE search error: {e}[/dim]")
        return []


def _search_crossref(query: str, max_results: int):
    """Search Crossref API (150M+ scholarly works from all major academic publishers)."""
    params = {
        "query": query,
        "rows": min(max_results, 25),
    }
    headers = dict(config.HEADERS)
    headers["User-Agent"] = f"CosmoLabUniversity/1.0 (mailto:{config.EMAIL})"
    try:
        r = _request_with_retry("GET", config.CROSSREF_API_URL, params=params, headers=headers, timeout=15)
        if r is None or r.status_code != 200:
            return []
        items = r.json().get("message", {}).get("items", [])
        works = []
        for item in items:
            titles = item.get("title", [])
            if not titles:
                continue
            title = titles[0]
            doi = item.get("DOI", "")
            
            created_parts = item.get("created", {}).get("date-parts", [[]])[0]
            year = str(created_parts[0]) if created_parts else ""
            
            pdf_url = None
            for l in item.get("link", []):
                if "pdf" in l.get("content-type", "").lower():
                    pdf_url = l.get("URL")
                    break
            
            abstract = item.get("abstract", "")
            works.append({
                "id": f"crossref:{doi or item.get('URL')}",
                "authors": _authors.from_crossref(item.get("author")),
                "title": title.replace("\n", " ").strip(),
                "pdf_url": pdf_url,
                "abstract": abstract,
                "doi": doi,
                "arxiv_id": "",
                "published": year,
                "publication_year": year,
                "type": item.get("type", "journal-article"),
                "source": "crossref",
            })
        return works
    except Exception as e:
        console.print(f"[dim]Crossref search error: {e}[/dim]")
        return []


ACADEMIC_STOPWORDS = {
    'pengaruh', 'terhadap', 'dan', 'di', 'pada', 'ke', 'dari', 'yang', 'untuk', 'dengan',
    'dalam', 'studi', 'analisis', 'the', 'of', 'and', 'in', 'on', 'to', 'for', 'with',
    'a', 'an', 'at', 'by', 'as', 'about', 'between', 'role', 'impact', 'effect', 'study', 'analysis'
}


def _get_query_keywords(query: str) -> list[str]:
    tokens = re.findall(r"\w+", query.lower())
    content = [w for w in tokens if len(w) >= 3 and w not in ACADEMIC_STOPWORDS]
    return content if content else tokens


def _compute_relevance(title: str, abstract: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    text_title = (title or "").lower()
    text_full = f"{text_title} {(abstract or '').lower()}"

    score = 0.0
    matches = 0
    for kw in keywords:
        if kw in text_title:
            score += 4.0
            matches += 1
        elif kw in text_full:
            score += 1.0
            matches += 1

    if matches == 0:
        return 0.0

    coverage = matches / len(keywords)
    return score * (1.0 + coverage)


def _search(query: str, max_results: int):
    """Federated academic search across DOAJ, OpenAlex, Crossref, Semantic Scholar, CORE, and arXiv with relevance filtering."""
    portion = max(3, max_results // 3)

    # Parallel API calls to all sources for faster federated search
    source_fns = [
        ("doaj", _search_doaj, query, portion),
        ("crossref", _search_crossref, query, portion),
        ("core", _search_core, query, portion),
        ("semanticscholar", _search_semanticscholar, query, portion),
        ("arxiv", _search_arxiv, query, portion),
    ]

    collected = []
    with ThreadPoolExecutor(max_workers=len(source_fns)) as executor:
        futures = {
            executor.submit(fn, q, n): name
            for name, fn, q, n in source_fns
        }
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                results = future.result()
                collected.extend(results)
            except Exception as e:
                console.print(f"[yellow]WARN  {source_name} search error: {e}[/yellow]")

    # OpenAlex as filler if quota not reached
    remaining = (max_results * 2) - len(collected)
    if remaining > 0:
        openalex_works = _search_openalex(query, remaining)
        collected += openalex_works

    keywords = _get_query_keywords(query)
    valid = []
    seen_titles = set()
    for w in collected:
        title = w.get("title") or ""
        norm_t = _normalize_title(title)
        if norm_t in seen_titles:
            continue
        seen_titles.add(norm_t)

        abstract = str(w.get("abstract") or "")
        rel = _compute_relevance(title, abstract, keywords)
        if rel > 0:
            w["_rel_score"] = rel
            valid.append(w)

    valid.sort(key=lambda x: x.get("_rel_score", 0), reverse=True)
    return valid[:max_results]


def _pdf_url(work: dict):
    """Extract PDF URL from work (handles arXiv, DOAJ, Semantic Scholar, CORE, Crossref, and OpenAlex)."""
    source = work.get("source", "openalex")
    
    if source in ("arxiv", "doaj", "semanticscholar", "core", "crossref"):
        if work.get("pdf_url"):
            return work.get("pdf_url")
    
    # OpenAlex
    oa = work.get("best_oa_location") or {}
    
    if oa.get("pdf_url") and not any(host in oa.get("pdf_url", "") for host in BLOCKED_HOSTS):
        return oa["pdf_url"]
    for loc in work.get("locations") or []:
        url = loc.get("pdf_url", "")
        if url and not any(host in url for host in BLOCKED_HOSTS):
            return url
    
    # Unpaywall fallback if DOI is available
    doi = (work.get("doi") or "").replace("https://doi.org/", "").strip()
    if doi:
        resolved = _resolve_unpaywall(doi)
        if resolved:
            return resolved
            
    return None


def _resolve_unpaywall(doi: str) -> str | None:
    """Query Unpaywall API using DOI to retrieve an open-access PDF URL if primary source fails."""
    if not doi:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    url = f"{config.UNPAYWALL}/{clean_doi}"
    try:
        r = _request_with_retry("GET", url, params={"email": config.EMAIL}, headers=config.HEADERS, timeout=12)
        if r is not None and r.status_code == 200:
            data = r.json()
            if data.get("is_oa"):
                best_loc = data.get("best_oa_location") or {}
                pdf_url = best_loc.get("url_for_pdf") or best_loc.get("url")
                if pdf_url and not any(h in pdf_url for h in BLOCKED_HOSTS):
                    return pdf_url
                for loc in data.get("oa_locations") or []:
                    u = loc.get("url_for_pdf") or loc.get("url")
                    if u and not any(h in u for h in BLOCKED_HOSTS):
                        return u
    except Exception as e:
        console.print(f"[dim]Unpaywall lookup skipped for {clean_doi}: {e}[/dim]")
    return None


def _download(url: str, dest, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=config.HEADERS, timeout=120, stream=True)
            if r.status_code != 200:
                return False
            stream = r.iter_content(chunk_size=8192)
            first = next(stream, b"")
            if not first.startswith(b"%PDF"):
                return False
            with dest.open("wb") as f:
                f.write(first)
                for chunk in stream:
                    f.write(chunk)
            # Ensure file is not truncated/corrupt (at least 1KB)
            if dest.stat().st_size < 1000:
                dest.unlink(missing_ok=True)
                return False
            return True
        except Exception as e:
            if dest.exists():
                dest.unlink(missing_ok=True)
            print(f"  err (attempt {attempt+1}/{retries}):", e)
            if attempt < retries - 1:
                time.sleep(5)
            continue
    return False


def _extract_arxiv_id(work: dict) -> str | None:
    """Extract arXiv ID from work metadata (handles both arXiv and OpenAlex)."""
    # Direct arXiv source
    if work.get("source") == "arxiv":
        arxiv_id = work.get("arxiv_id", "")
        if arxiv_id:
            # Normalize: extract just the ID (e.g., "1412.5701v1" -> "1412.5701")
            match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", arxiv_id)
            return match.group(1) if match else None
    
    # OpenAlex may have arXiv in URL or doi
    url = work.get("id", "") or work.get("pdf_url", "")
    if "arxiv.org" in url:
        match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", url)
        return match.group(1) if match else None
    
    doi = work.get("doi", "")
    if doi and "arxiv" in doi.lower():
        match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", doi)
        return match.group(1) if match else None
    
    return None


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching."""
    if not title:
        return ""
    # Lowercase, remove punctuation, collapse whitespace
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _title_is_duplicate(new_title: str, existing_titles: list, threshold: float = 0.85) -> bool:
    """Check if title is similar to any existing title."""
    if not new_title:
        return False
    new_norm = _normalize_title(new_title)
    for existing in existing_titles:
        existing_norm = _normalize_title(existing)
        if not existing_norm:
            continue
        ratio = SequenceMatcher(None, new_norm, existing_norm).ratio()
        if ratio >= threshold:
            return True
    return False



def harvest(query: str, max_results: int = 40, workers: int = 4, delay: float = 0.5, faculty: str = None, progress_cb: callable = None) -> dict:
    config.ensure_dirs()
    done = load_done()
    
    # Build existing metadata indices
    metadata = read_meta()
    seen_dois = {m.get("doi") for m in metadata if m.get("doi")}
    seen_arxiv_ids = {_extract_arxiv_id(m) for m in metadata if _extract_arxiv_id(m)}
    existing_titles = [m.get("title", "") for m in metadata]
    
    stats = {"found": 0, "downloaded": 0, "skipped": 0, "no_pdf": 0, "duplicate": 0, "source": {"arxiv": 0, "openalex": 0, "doaj": 0, "semanticscholar": 0, "crossref": 0, "core": 0}}
    to_download = []

    _fire_cb(progress_cb, "search_start", f"Mencari literatur: '{query}' di federasi repositori ilmiah...", {"query": query})

    for work in _search(query, max_results):
        stats["found"] += 1
        wid = work["id"]
        title = work.get("title") or "untitled"
        source = work.get("source", "openalex")
        stats["source"][source] = stats["source"].get(source, 0) + 1
        
        # Check 1: work ID
        if wid in done:
            stats["skipped"] += 1
            console.print(f"[yellow]SKIP  Already done: {title[:60]}[/yellow]")
            _fire_cb(progress_cb, "skip", f"Dilewati (sudah tersimpan): {title[:60]}", {"title": title})
            continue
        
        # Check 2: DOI
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        if doi and doi in seen_dois:
            stats["duplicate"] += 1
            done.add(wid)
            save_done(done)
            console.print(f"[yellow]DUPLICATE  (DOI): {title[:60]}[/yellow]")
            _fire_cb(progress_cb, "duplicate", f"Dilewati (duplikat DOI): {title[:60]}", {"title": title})
            continue
        
        # Check 3: arXiv ID
        arxiv_id = _extract_arxiv_id(work)
        if arxiv_id and arxiv_id in seen_arxiv_ids:
            stats["duplicate"] += 1
            done.add(wid)
            save_done(done)
            console.print(f"[yellow]DUPLICATE  (arXiv): {title[:60]}[/yellow]")
            _fire_cb(progress_cb, "duplicate", f"Dilewati (duplikat arXiv): {title[:60]}", {"title": title})
            continue
        
        # Check 4: Title fuzzy match
        if _title_is_duplicate(title, existing_titles, threshold=0.85):
            stats["duplicate"] += 1
            done.add(wid)
            save_done(done)
            console.print(f"[yellow]DUPLICATE  (title): {title[:60]}[/yellow]")
            _fire_cb(progress_cb, "duplicate", f"Dilewati (judul mirip): {title[:60]}", {"title": title})
            continue
        
        # Check PDF URL
        pdf = _pdf_url(work)
        if not pdf:
            stats["no_pdf"] += 1
            console.print(f"[red]NO_PDF  {title[:60]}[/red]")
            _fire_cb(progress_cb, "no_pdf", f"Tidak ada naskah Open Access PDF: {title[:60]}", {"title": title})
            continue
        
        year = work.get("publication_year") or ""
        fname = f"{year}_{safe_name(title)}.pdf"
        dest = config.PDF_DIR / fname

        abstract_text = work.get("abstract") or ""
        # Flatten OpenAlex inverted abstract index if it slipped through
        if not abstract_text and work.get("abstract_inverted_index"):
            abstract_text = _flatten_inverted_abstract(work["abstract_inverted_index"])
        elif isinstance(abstract_text, dict):
            abstract_text = _flatten_inverted_abstract(abstract_text)
        abstract_text = str(abstract_text)
        item_faculty = faculty or _faculties.detect_faculty_from_text(title, abstract_text)

        to_download.append({
            "wid": wid, "title": title, "year": year, "doi": doi,
            "pdf": pdf, "fname": fname, "dest": dest, "source": source,
            "arxiv_id": arxiv_id,
            "abstract": abstract_text,
            "faculty": item_faculty,
            "authors": work.get("authors") or _authors.from_openalex(work),
        })
        existing_titles.append(title)
        if arxiv_id:
            seen_arxiv_ids.add(arxiv_id)

        _fire_cb(progress_cb, "paper_found", f"Menemukan naskah: {title[:65]} ({source})", {"title": title, "source": source, "doi": doi})

    if not to_download:
        _fire_cb(progress_cb, "no_new", "Tidak ada paper baru yang perlu diunduh.", {"stats": stats})
        return stats

    console.print(f"[cyan]DOWNLOADING[/cyan] [dim]({len(to_download)} papers, workers={workers})...[/dim]")
    _fire_cb(progress_cb, "download_batch_start", f"Memulai pengunduhan {len(to_download)} file PDF legal...", {"count": len(to_download)})
    lock = threading.Lock()

    def _download_worker(item):
        pdf = item["pdf"]
        dest = item["dest"]
        title = item["title"]
        source = item["source"]
        wid = item["wid"]

        console.print(f"[cyan]DOWNLOAD  {title[:70]}[/cyan] [dim]({source})[/dim]")
        download_ok = _download(pdf, dest)
        final_pdf_url = pdf

        # If download failed and paper has DOI, try Unpaywall fallback
        if not download_ok and item.get("doi"):
            unpaywall_url = _resolve_unpaywall(item["doi"])
            if unpaywall_url and unpaywall_url != pdf:
                console.print(f"[cyan]UNPAYWALL FALLBACK  {title[:60]}[/cyan]")
                if _download(unpaywall_url, dest):
                    download_ok = True
                    final_pdf_url = unpaywall_url

        if download_ok:
            with lock:
                append_meta({
                    "id": wid, "title": title, "year": item["year"], "doi": item["doi"],
                    "url": final_pdf_url, "file": item["fname"],
                    "abstract": item["abstract"],
                    "source": source,
                    "arxiv_id": item["arxiv_id"],
                    "faculty": item.get("faculty", "ilahiyyat"),
                    "authors": item.get("authors") or [],
                })
                done.add(wid)
                save_done(done)
                stats["downloaded"] += 1
            console.print(f"[green]OK  Downloaded: {title[:60]}[/green]")
        else:
            console.print(f"[red]FAIL  Download failed: {title[:60]}[/red]")
        time.sleep(delay)
        return {"ok": download_ok, "title": title, "file": item["fname"], "source": source, "wid": wid}

    max_workers = max(1, min(workers, len(to_download)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_download_worker, item) for item in to_download]
        for f in as_completed(futures):
            res_item = f.result()
            if res_item and res_item.get("ok"):
                _fire_cb(progress_cb, "download_ok", f"Berhasil diunduh: {res_item['title'][:55]}", res_item)
            elif res_item and not res_item.get("ok"):
                _fire_cb(progress_cb, "download_fail", f"Gagal mengunduh file PDF: {res_item['title'][:55]}", res_item)

    return stats


def harvest_faculty(faculty_id: str, max_results_per_query: int = 10, workers: int = 4, delay: float = 0.5, progress_cb: callable = None) -> dict:
    """Harvest papers using default curated academic queries of a specific faculty."""
    fac = _faculties.get_faculty(faculty_id)
    if not fac:
        console.print(f"[red]Faculty {faculty_id} not found.[/red]")
        return {"error": f"Faculty {faculty_id} not found"}

    console.print(f"[bold cyan]Harvesting Faculty:[/bold cyan] {fac.name} ({fac.icon})")
    _fire_cb(progress_cb, "faculty_start", f"Memulai panen kurikulum fakultas: {fac.icon} {fac.name} ({len(fac.default_queries)} query)", {"faculty": fac.name})
    aggregated = {
        "found": 0, "downloaded": 0, "skipped": 0, "no_pdf": 0, "duplicate": 0,
        "source": {"arxiv": 0, "openalex": 0, "doaj": 0, "semanticscholar": 0, "crossref": 0, "core": 0}
    }

    for idx_q, q in enumerate(fac.default_queries, 1):
        console.print(f"[yellow]Harvesting Query ({idx_q}/{len(fac.default_queries)}):[/yellow] '{q}'")
        _fire_cb(progress_cb, "query_step", f"Query ({idx_q}/{len(fac.default_queries)}): '{q}'", {"query": q, "step": idx_q, "total": len(fac.default_queries)})
        res = harvest(query=q, max_results=max_results_per_query, workers=workers, delay=delay, faculty=faculty_id, progress_cb=progress_cb)
        for k in ("found", "downloaded", "skipped", "no_pdf", "duplicate"):
            aggregated[k] += res.get(k, 0)
        for src, cnt in res.get("source", {}).items():
            aggregated["source"][src] = aggregated["source"].get(src, 0) + cnt

    return aggregated


def import_local_pdf(file_bytes: bytes, filename: str, title: str = "", faculty: str = None) -> dict:
    """Import a manually downloaded PDF (e.g. from PhilPapers, PhilArchive, or personal collection)."""
    config.ensure_dirs()
    clean_stem = safe_name(Path(filename).stem)
    dest_name = f"manual_{clean_stem}.pdf"
    dest_path = config.PDF_DIR / dest_name
    dest_path.write_bytes(file_bytes)

    paper_title = title.strip() or Path(filename).stem.replace("_", " ")
    item_faculty = faculty or _faculties.detect_faculty_from_text(paper_title)

    meta_entry = {
        "id": f"manual:{dest_name}",
        "title": paper_title,
        "year": "n.d.",
        "doi": "",
        "url": "",
        "file": dest_name,
        "abstract": "",
        "source": "philpapers/manual",
        "arxiv_id": "",
        "faculty": item_faculty,
    }
    append_meta(meta_entry)
    
    # Extract text immediately
    from . import extract
    txt_out = config.TEXT_DIR / f"{Path(dest_name).stem}.txt"
    try:
        text = extract._pdf_to_text(dest_path)
        if text.strip():
            txt_out.write_text(text, encoding="utf-8")
    except Exception as e:
        console.print(f"[yellow]WARN  Text extraction failed for {dest_name}: {e}[/yellow]")

    try:
        names, src = _authors.resolve(meta_entry, use_ai=True)
        if names:
            _authors.save_entry(dest_name, names, src)
    except Exception as e:
        console.print(f"[yellow]WARN  Author lookup failed for {dest_name}: {e}[/yellow]")

    return {
        "ok": True,
        "file": dest_name,
        "title": paper_title,
        "faculty": item_faculty,
    }


def import_by_doi(doi: str, faculty: str = None) -> dict:
    """Import an academic paper using DOI (resolves OA fulltext via Unpaywall)."""
    config.ensure_dirs()
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not clean_doi:
        return {"error": "DOI tidak boleh kosong"}

    # 1. Query Unpaywall for OA PDF
    pdf_url = _resolve_unpaywall(clean_doi)
    if not pdf_url:
        return {"error": f"Tidak ditemukan naskah Open Access legal di Unpaywall untuk DOI: {clean_doi}"}

    # 2. Get metadata
    title = f"Paper DOI {clean_doi}"
    year = ""
    doi_authors = []
    try:
        r = _request_with_retry("GET", f"{config.UNPAYWALL}/{clean_doi}", params={"email": config.EMAIL}, headers=config.HEADERS, timeout=12)
        if r is not None and r.status_code == 200:
            data = r.json()
            title = data.get("title") or title
            year = str(data.get("year") or "")
            doi_authors = _authors.from_crossref(data.get("z_authors"))
    except Exception:
        pass

    fname = f"{year}_{safe_name(title)}.pdf" if year else f"{safe_name(title)}.pdf"
    dest = config.PDF_DIR / fname

    if _download(pdf_url, dest):
        item_faculty = faculty or _faculties.detect_faculty_from_text(title)
        append_meta({
            "id": f"doi:{clean_doi}",
            "title": title,
            "year": year,
            "doi": clean_doi,
            "url": pdf_url,
            "file": fname,
            "abstract": "",
            "source": "unpaywall/doi",
            "arxiv_id": "",
            "faculty": item_faculty,
            "authors": doi_authors or _authors.by_doi(clean_doi),
        })
        from . import extract
        txt_out = config.TEXT_DIR / f"{Path(fname).stem}.txt"
        try:
            text = extract._pdf_to_text(dest)
            if text.strip():
                txt_out.write_text(text, encoding="utf-8")
        except Exception:
            pass
        return {"ok": True, "title": title, "file": fname, "faculty": item_faculty}
    else:
        return {"error": f"Gagal mengunduh PDF dari URL: {pdf_url}"}


