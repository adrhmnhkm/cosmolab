import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from rich.console import Console
from . import config
from .storage import safe_name, load_done, save_done, append_meta, read_meta

console = Console(force_terminal=True, legacy_windows=False)


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
    r = requests.get(url, params=params, headers=config.HEADERS, timeout=30)
    if r.status_code != 200:
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
            "published": entry.find("published", ns).text if entry.find("published", ns) is not None else "",
            "publication_year": entry.find("published", ns).text[:4] if entry.find("published", ns) is not None else "",
            "type": "preprint",
            "source": "arxiv",
        })
    return works


def _search_openalex(query: str, max_results: int):
    out, cursor = [], "*"
    while len(out) < max_results:
        r = requests.get(config.OPENALEX, params={
            "search": query,
            "filter": "is_oa:true,type:article",
            "per_page": 25,
            "cursor": cursor,
            "mailto": config.EMAIL,
        }, headers=config.HEADERS, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        out.extend(data.get("results", []))
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(1)
    return out[:max_results]


def _search(query: str, max_results: int):
    """Search arXiv first, then OpenAlex as fallback."""
    arxiv_works = _search_arxiv(query, max_results // 2)
    remaining = max_results - len(arxiv_works)
    
    if remaining > 0:
        openalex_works = _search_openalex(query, remaining)
    else:
        openalex_works = []
    
    return arxiv_works + openalex_works


def _pdf_url(work: dict):
    """Extract PDF URL from work (handles both arXiv and OpenAlex)."""
    source = work.get("source", "openalex")
    
    if source == "arxiv":
        return work.get("pdf_url")
    
    # OpenAlex
    oa = work.get("best_oa_location") or {}
    blocked = {"doiserbia.nb.rs", "dspace.univ-bab.dz"}
    
    if oa.get("pdf_url") and not any(host in oa.get("pdf_url", "") for host in blocked):
        return oa["pdf_url"]
    for loc in work.get("locations") or []:
        url = loc.get("pdf_url", "")
        if url and not any(host in url for host in blocked):
            return url
    return None


def _download(url: str, dest, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=config.HEADERS, timeout=120, stream=True)
            if r.status_code != 200:
                return False
            first = next(r.iter_content(4), b"")
            if first != b"%PDF":
                return False
            with dest.open("wb") as f:
                f.write(first)
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception as e:
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


def harvest(query: str, max_results: int = 40, workers: int = 4, delay: float = 0.5) -> dict:
    config.ensure_dirs()
    done = load_done()
    
    # Build existing metadata indices
    metadata = read_meta()
    seen_dois = {m.get("doi") for m in metadata if m.get("doi")}
    seen_arxiv_ids = {_extract_arxiv_id(m) for m in metadata if _extract_arxiv_id(m)}
    existing_titles = [m.get("title", "") for m in metadata]
    
    stats = {"found": 0, "downloaded": 0, "skipped": 0, "no_pdf": 0, "duplicate": 0, "source": {"arxiv": 0, "openalex": 0}}
    to_download = []

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
            continue
        
        # Check 2: DOI
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        if doi and doi in seen_dois:
            stats["duplicate"] += 1
            done.add(wid)
            save_done(done)
            console.print(f"[yellow]DUPLICATE  (DOI): {title[:60]}[/yellow]")
            continue
        
        # Check 3: arXiv ID
        arxiv_id = _extract_arxiv_id(work)
        if arxiv_id and arxiv_id in seen_arxiv_ids:
            stats["duplicate"] += 1
            done.add(wid)
            save_done(done)
            console.print(f"[yellow]DUPLICATE  (arXiv): {title[:60]}[/yellow]")
            continue
        
        # Check 4: Title fuzzy match
        if _title_is_duplicate(title, existing_titles, threshold=0.85):
            stats["duplicate"] += 1
            done.add(wid)
            save_done(done)
            console.print(f"[yellow]DUPLICATE  (title): {title[:60]}[/yellow]")
            continue
        
        # Check PDF URL
        pdf = _pdf_url(work)
        if not pdf:
            stats["no_pdf"] += 1
            console.print(f"[red]NO_PDF  {title[:60]}[/red]")
            continue
        
        year = work.get("publication_year") or ""
        fname = f"{year}_{safe_name(title)}.pdf"
        dest = config.PDF_DIR / fname

        to_download.append({
            "wid": wid, "title": title, "year": year, "doi": doi,
            "pdf": pdf, "fname": fname, "dest": dest, "source": source,
            "arxiv_id": arxiv_id,
            "abstract": work.get("abstract_inverted_index") or work.get("abstract")
        })
        existing_titles.append(title)
        if arxiv_id:
            seen_arxiv_ids.add(arxiv_id)

    if not to_download:
        return stats

    console.print(f"[cyan]DOWNLOADING[/cyan] [dim]({len(to_download)} papers, workers={workers})...[/dim]")
    lock = threading.Lock()

    def _download_worker(item):
        pdf = item["pdf"]
        dest = item["dest"]
        title = item["title"]
        source = item["source"]
        wid = item["wid"]

        console.print(f"[cyan]DOWNLOAD  {title[:70]}[/cyan] [dim]({source})[/dim]")
        if _download(pdf, dest):
            with lock:
                append_meta({
                    "id": wid, "title": title, "year": item["year"], "doi": item["doi"],
                    "url": pdf, "file": item["fname"],
                    "abstract": item["abstract"],
                    "source": source,
                    "arxiv_id": item["arxiv_id"],
                })
                done.add(wid)
                save_done(done)
                stats["downloaded"] += 1
            console.print(f"[green]OK  Downloaded: {title[:60]}[/green]")
        else:
            console.print(f"[red]FAIL  Download failed: {title[:60]}[/red]")
        time.sleep(delay)

    max_workers = max(1, min(workers, len(to_download)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_download_worker, item) for item in to_download]
        for f in as_completed(futures):
            pass

    return stats
