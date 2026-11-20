import time
import re
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from rich.console import Console
from . import config
from . import faculties as _faculties
from . import authors as _authors
from . import dois as _dois
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
            entry_id = entry.find("id", ns).text if entry.find("id", ns) is not None else ""
            aid = _dois.arxiv_id(entry_id) or _dois.arxiv_id(pdf_link)
            works.append({
                "id": pdf_link,
                # Journal DOI when the authors listed one, otherwise the DOI arXiv gives every preprint
                "doi": _dois.arxiv_journal_doi(entry) or _dois.arxiv_doi(aid),
                "title": title.replace("\n", " ").strip(),
                "pdf_url": pdf_link,
                "abstract": summary,
                "arxiv_id": aid,
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


def _search_openalex(query: str, max_results: int, extra_filter: str = ""):
    out, cursor = [], "*"
    flt = "is_oa:true,type:article" + (f",{extra_filter}" if extra_filter else "")
    try:
        while len(out) < max_results:
            r = _request_with_retry("GET", config.OPENALEX, params={
                "search": query,
                "filter": flt,
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
                "journal": (bib.get("journal") or {}).get("title", ""),
                "issn": [i.get("id", "") for i in bib.get("identifier", []) if i.get("type") in ("pissn", "eissn")],
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
        if s2_key:
            r = _request_with_retry("GET", url, params=params, headers=headers, timeout=15)
        else:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 429:
                console.print("[dim]Semantic Scholar rate-limit (429). Melanjutkan dengan sumber federasi lainnya...[/dim]")
                return []
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
                "journal": (item.get("container-title") or [""])[0],
                "issn": list(item.get("ISSN") or []),
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


def journal_info(work: dict) -> tuple[str, list[str]]:
    """Journal name and ISSNs of a search result, from any source."""
    if work.get("journal") or work.get("issn"):
        return work.get("journal") or "", [i for i in work.get("issn") or [] if i]
    src = (work.get("primary_location") or {}).get("source") or {}
    issns = list(src.get("issn") or [])
    if src.get("issn_l") and src["issn_l"] not in issns:
        issns.insert(0, src["issn_l"])
    return src.get("display_name") or "", issns


# Indonesian journals: OpenAlex can filter by the journal's country and by the
# article's language. Many Indonesian journals have no country in OpenAlex, so
# both filters are searched and merged.
INDONESIA_FILTERS = ("primary_location.source.country_code:ID", "language:id")


def _search(query: str, max_results: int, indonesia: bool = False):
    """Federated academic search across DOAJ, OpenAlex, Crossref, Semantic Scholar, CORE, and arXiv with relevance filtering.

    indonesia=True searches only OpenAlex, limited to Indonesian journals or
    Indonesian-language articles (the Garuda/SINTA journals that have DOIs).
    """
    portion = max(3, max_results // 3)

    if indonesia:
        source_fns = [(f"openalex-{f}", _search_openalex, query, max_results, f) for f in INDONESIA_FILTERS]
    else:
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
            executor.submit(fn, *args): name
            for name, fn, *args in source_fns
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
    if remaining > 0 and not indonesia:
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


def _resolve_landing_page_pdf(landing_url: str) -> str | None:
    """Extract direct PDF URL from publisher/repository HTML landing page using standard Dublin Core and Highwire Press metadata."""
    if not landing_url or any(h in landing_url for h in BLOCKED_HOSTS):
        return None
    parsed = urlparse(landing_url)
    if parsed.path.lower().endswith(".pdf"):
        return landing_url

    headers = dict(config.HEADERS)
    headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    try:
        r = requests.get(landing_url, headers=headers, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            return None
        content_type = (r.headers.get("Content-Type") or "").lower()
        if "application/pdf" in content_type:
            return r.url
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None

        html = r.text
        # 1. Dublin Core / Highwire Press citation tags (used by 90%+ academic publishers: Springer, OJS, Nature, DOAJ, etc.)
        patterns = [
            r'<meta\s+[^>]*name=["\']citation_pdf_url["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']citation_pdf_url["\']',
            r'<meta\s+[^>]*name=["\']eprints\.document_url["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta\s+[^>]*name=["\']bepress_citation_pdf_url["\'][^>]*content=["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            match = re.search(pat, html, re.I)
            if match:
                pdf_link = match.group(1).strip()
                resolved = urljoin(r.url, pdf_link)
                if not any(h in resolved for h in BLOCKED_HOSTS):
                    return resolved

        # 2. Heuristic: Look for direct link to full text PDF in <a> tag (common in OJS / Garuda)
        link_matches = re.findall(r'<a\s+[^>]*href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html, re.I)
        for link in link_matches:
            link_lower = link.lower()
            if not any(b in link_lower for b in ("guideline", "author", "policy", "cover", "toc", "editorial", "review")):
                resolved = urljoin(r.url, link.strip())
                if not any(h in resolved for h in BLOCKED_HOSTS):
                    return resolved
    except Exception:
        pass
    return None


def _pdf_url(work: dict):
    """Extract PDF URL from work (handles arXiv, DOAJ, Semantic Scholar, CORE, Crossref, and OpenAlex)."""
    source = work.get("source", "openalex")
    
    if source in ("arxiv", "doaj", "semanticscholar", "core", "crossref"):
        if work.get("pdf_url") and not any(h in work.get("pdf_url", "") for h in BLOCKED_HOSTS):
            return work.get("pdf_url")
    
    # OpenAlex: Check direct PDF first
    oa = work.get("best_oa_location") or {}
    
    if oa.get("pdf_url") and not any(host in oa.get("pdf_url", "") for host in BLOCKED_HOSTS):
        return oa["pdf_url"]
    for loc in work.get("locations") or []:
        url = loc.get("pdf_url", "")
        if url and not any(host in url for host in BLOCKED_HOSTS):
            return url
    
    # Try resolving publisher landing page via HTML meta tags
    landing = oa.get("landing_page_url")
    if landing and not any(host in landing for h in BLOCKED_HOSTS):
        resolved = _resolve_landing_page_pdf(landing)
        if resolved:
            return resolved

    # Unpaywall fallback if DOI is available
    doi = (work.get("doi") or "").replace("https://doi.org/", "").strip()
    if doi:
        resolved = _resolve_unpaywall(doi)
        if resolved:
            return resolved
        # Direct DOI landing page resolution fallback
        resolved_doi = _resolve_landing_page_pdf(f"https://doi.org/{doi}")
        if resolved_doi:
            return resolved_doi
            
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
                # 1. Strictly look for direct PDF URLs first
                best_loc = data.get("best_oa_location") or {}
                pdf_url = best_loc.get("url_for_pdf")
                if pdf_url and not any(h in pdf_url for h in BLOCKED_HOSTS):
                    return pdf_url
                for loc in data.get("oa_locations") or []:
                    u = loc.get("url_for_pdf")
                    if u and not any(h in u for h in BLOCKED_HOSTS):
                        return u
                # 2. If no direct PDF URL, try resolving the landing page via meta tags
                landing = best_loc.get("url") or best_loc.get("url_for_landing_page")
                if landing and not any(h in landing for h in BLOCKED_HOSTS):
                    resolved = _resolve_landing_page_pdf(landing)
                    if resolved:
                        return resolved
    except Exception as e:
        console.print(f"[dim]Unpaywall lookup skipped for {clean_doi}: {e}[/dim]")
    return None


def _download(url: str, dest, retries: int = 3, on_bytes=None) -> bool:
    """Download a PDF. on_bytes(done, total) reports progress; total is None when the server does not say."""
    if not url or any(h in url for h in BLOCKED_HOSTS):
        return False

    parsed = urlparse(url)
    headers = dict(config.HEADERS)
    headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=120, stream=True, allow_redirects=True)
            if r.status_code != 200:
                return False
            try:
                total = int(r.headers.get("Content-Length") or 0) or None
            except ValueError:
                total = None
            stream = r.iter_content(chunk_size=8192)
            first = next(stream, b"")

            # Validate that stream starts with PDF magic bytes (within first 1KB)
            if b"%PDF" not in first[:1024]:
                # If server sent HTML, it might be a landing page URL
                if b"<!DOCTYPE" in first[:500] or b"<html" in first[:500] or b"<HTML" in first[:500]:
                    resolved_pdf = _resolve_landing_page_pdf(url)
                    if resolved_pdf and resolved_pdf != url:
                        return _download(resolved_pdf, dest, retries=1, on_bytes=on_bytes)
                return False

            done, last = len(first), 0.0
            with dest.open("wb") as f:
                f.write(first)
                for chunk in stream:
                    f.write(chunk)
                    done += len(chunk)
                    if on_bytes and time.monotonic() - last >= 0.2:
                        last = time.monotonic()
                        try:
                            on_bytes(done, total)
                        except Exception:
                            pass
            if on_bytes:
                try:
                    on_bytes(done, total or done)
                except Exception:
                    pass
            # Ensure file is not truncated/corrupt (at least 1KB)
            if dest.stat().st_size < 1000:
                dest.unlink(missing_ok=True)
                return False
            return True
        except Exception as e:
            if dest.exists():
                dest.unlink(missing_ok=True)
            if attempt < retries - 1:
                time.sleep(3)
            continue
    return False


def _extract_arxiv_id(work: dict) -> str | None:
    """Extract arXiv ID from work metadata (handles both arXiv and OpenAlex)."""
    # Direct arXiv source
    if work.get("source") == "arxiv":
        # Normalize: "1412.5701v1" -> "1412.5701", "quant-ph/0701019v1" -> "quant-ph/0701019"
        arxiv_id = _dois.arxiv_id(work.get("arxiv_id", "")) or _dois.arxiv_id(work.get("pdf_url", ""))
        if arxiv_id:
            return arxiv_id
    
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



def harvest(query: str, max_results: int = 40, workers: int = 4, delay: float = 0.5, faculty: str = None,
            progress_cb: callable = None, indonesia: bool = False) -> dict:
    config.ensure_dirs()
    done = load_done()
    
    # Build existing metadata indices
    metadata = read_meta()
    seen_dois = {m.get("doi") for m in metadata if m.get("doi")}
    seen_arxiv_ids = {_extract_arxiv_id(m) for m in metadata if _extract_arxiv_id(m)}
    existing_titles = [m.get("title", "") for m in metadata]
    
    stats = {"found": 0, "downloaded": 0, "skipped": 0, "no_pdf": 0, "duplicate": 0, "source": {"arxiv": 0, "openalex": 0, "doaj": 0, "semanticscholar": 0, "crossref": 0, "core": 0}}
    to_download = []

    where = "jurnal Indonesia (OpenAlex)" if indonesia else "federasi repositori ilmiah"
    _fire_cb(progress_cb, "search_start", f"Mencari literatur: '{query}' di {where}...", {"query": query})

    for work in _search(query, max_results, indonesia=indonesia):
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
        journal, issns = journal_info(work)

        to_download.append({
            "journal": journal, "issn": issns,
            "wid": wid, "title": title, "year": year, "doi": doi,
            "pdf": pdf, "fname": fname, "dest": dest, "source": source,
            "arxiv_id": arxiv_id,
            "abstract": abstract_text,
            "faculty": item_faculty,
            "authors": work.get("authors") or _authors.from_openalex(work),
            "work": work,
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
        work = item.get("work") or {}

        console.print(f"[cyan]DOWNLOAD  {title[:70]}[/cyan] [dim]({source})[/dim]")
        download_ok = _download(pdf, dest)
        final_pdf_url = pdf

        # Fallback 1: Try alternative locations from OpenAlex
        if not download_ok and work.get("locations"):
            for loc in work.get("locations"):
                alt_url = loc.get("pdf_url")
                if alt_url and alt_url != pdf and not any(h in alt_url for h in BLOCKED_HOSTS):
                    console.print(f"[cyan]LOCATION FALLBACK  {title[:60]}[/cyan]")
                    if _download(alt_url, dest):
                        download_ok = True
                        final_pdf_url = alt_url
                        break

        # Fallback 2: If download failed and paper has DOI, try Unpaywall
        if not download_ok and item.get("doi"):
            unpaywall_url = _resolve_unpaywall(item["doi"])
            if unpaywall_url and unpaywall_url != pdf and unpaywall_url != final_pdf_url:
                console.print(f"[cyan]UNPAYWALL FALLBACK  {title[:60]}[/cyan]")
                if _download(unpaywall_url, dest):
                    download_ok = True
                    final_pdf_url = unpaywall_url

        # Fallback 3: Try DOI landing page meta-resolver
        if not download_ok and item.get("doi"):
            landing_url = f"https://doi.org/{item['doi']}"
            resolved = _resolve_landing_page_pdf(landing_url)
            if resolved and resolved != pdf and resolved != final_pdf_url:
                console.print(f"[cyan]DOI RESOLVER FALLBACK  {title[:60]}[/cyan]")
                if _download(resolved, dest):
                    download_ok = True
                    final_pdf_url = resolved

        # Fallback 4: arXiv title similarity match
        if not download_ok and item.get("title"):
            norm_target = _normalize_title(item["title"])
            try:
                arxiv_candidates = _search_arxiv(item["title"], max_results=3)
                for cand in arxiv_candidates:
                    sim = SequenceMatcher(None, norm_target, _normalize_title(cand.get("title", ""))).ratio()
                    if sim >= 0.85 and cand.get("pdf_url"):
                        console.print(f"[cyan]ARXIV FALLBACK  {cand['title'][:60]}[/cyan]")
                        if _download(cand["pdf_url"], dest):
                            download_ok = True
                            final_pdf_url = cand["pdf_url"]
                            source = "arxiv"
                            break
            except Exception:
                pass

        if download_ok:
            with lock:
                append_meta({
                    "id": wid, "title": title, "year": item["year"], "doi": item["doi"],
                    "url": final_pdf_url, "file": item["fname"],
                    "abstract": item["abstract"],
                    "source": source,
                    "arxiv_id": item["arxiv_id"],
                    "faculty": item.get("faculty") or "",
                    "authors": item.get("authors") or [],
                    **({"journal": item["journal"]} if item.get("journal") else {}),
                    **({"issn": item["issn"]} if item.get("issn") else {}),
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


def import_pdf_url(url: str, title: str, year: str = "", doi: str = "", authors: list | None = None,
                   source: str = "url", faculty: str = None) -> dict:
    """Download one legal PDF from a known URL into the collection and extract its text.

    Used to fill in the works a student's draft cites. Returns {"ok", "file"} or {"error"}.
    """
    config.ensure_dirs()
    fname = f"{year}_{safe_name(title)}.pdf" if year else f"{safe_name(title)}.pdf"
    dest = config.PDF_DIR / fname
    if not dest.exists() and not _download(url, dest):
        return {"error": f"Gagal mengunduh PDF: {url}"}
    append_meta({
        "id": f"{source}:{doi or url}", "title": title, "year": year, "doi": doi, "url": url, "file": fname,
        "abstract": "", "source": source, "arxiv_id": "",
        "faculty": faculty or _faculties.detect_faculty_from_text(title),
        "authors": authors or [],
    })
    from . import extract
    try:
        text = extract._pdf_to_text(dest)
        if text.strip():
            (config.TEXT_DIR / f"{Path(fname).stem}.txt").write_text(text, encoding="utf-8")
    except Exception as e:
        console.print(f"[yellow]WARN  Text extraction failed for {fname}: {e}[/yellow]")
    return {"ok": True, "file": fname, "title": title}


def _mb(n: int | None) -> str:
    return f"{(n or 0) / 1_048_576:.1f} MB"


def _report(on_step, event: str, **info) -> None:
    """Report one import step to a progress display. A display error never stops the import."""
    if on_step:
        try:
            on_step(event, info)
        except Exception:
            pass


def _extract_text(pdf_path, title: str, on_step=None) -> int:
    """Extract a PDF's text to TEXT_DIR, log it, and return the number of pages with text."""
    from . import extract

    _report(on_step, "ekstrak")
    txt_out = config.TEXT_DIR / f"{Path(pdf_path).stem}.txt"
    try:
        text = extract._pdf_to_text(pdf_path)
    except Exception as e:
        console.print(f"[yellow]PERINGATAN {title[:50]}: teks PDF gagal diekstrak: {e}[/yellow]")
        _report(on_step, "ekstrak_gagal", error=str(e)[:120])
        return 0
    if not text.strip():
        console.print(f"[yellow]PERINGATAN {title[:50]}: PDF tidak berisi teks (mungkin hasil scan)[/yellow]")
        _report(on_step, "ekstrak_gagal", error="PDF tidak berisi teks, mungkin hasil scan")
        return 0
    txt_out.write_text(text, encoding="utf-8")
    pages = text.count("--- [Halaman ")
    console.print(f"[cyan]TEKS     [/cyan]{title[:50]}: {pages} halaman, {len(text):,} karakter")
    _report(on_step, "ekstrak_ok", pages=pages, chars=len(text))
    return pages


def import_local_pdf(file_bytes: bytes, filename: str, title: str = "", faculty: str = None,
                     year: str = "", authors: list | None = None, on_step=None) -> dict:
    """Import a manually downloaded PDF (e.g. from PhilPapers, PhilArchive, or personal collection).

    year and authors, when given, are stored as is and no author lookup is run.
    on_step(event, info) reports "simpan", "ekstrak", "ekstrak_ok"/"ekstrak_gagal", "penulis", "beres".
    """
    config.ensure_dirs()
    clean_stem = safe_name(Path(filename).stem)
    dest_name = f"manual_{clean_stem}.pdf"
    dest_path = config.PDF_DIR / dest_name
    console.print(f"[bold cyan]UNGGAH   [/bold cyan]{filename} ({_mb(len(file_bytes))})")
    _report(on_step, "simpan", size=len(file_bytes), file=dest_name)
    dest_path.write_bytes(file_bytes)

    paper_title = title.strip() or Path(filename).stem.replace("_", " ")
    item_faculty = faculty or _faculties.detect_faculty_from_text(paper_title)

    meta_entry = {
        "id": f"manual:{dest_name}",
        "title": paper_title,
        "year": year or "n.d.",
        "doi": "",
        "url": "",
        "file": dest_name,
        "abstract": "",
        "source": "philpapers/manual",
        "arxiv_id": "",
        "faculty": item_faculty,
    }
    if authors:
        meta_entry["authors"] = list(authors)
    append_meta(meta_entry)

    # Extract text immediately
    pages = _extract_text(dest_path, paper_title, on_step)

    if not authors:
        _report(on_step, "penulis")
        try:
            names, src = _authors.resolve(meta_entry, use_ai=True)
            if names:
                _authors.save_entry(dest_name, names, src)
                more = " dkk." if len(names) > 3 else ""
                console.print(f"[cyan]PENULIS  [/cyan]{', '.join(names[:3])}{more} [dim]({src})[/dim]")
            _report(on_step, "penulis_ok", names=names or [], source=src)
        except Exception as e:
            console.print(f"[yellow]PERINGATAN {paper_title[:50]}: nama penulis tidak ditemukan: {e}[/yellow]")
            _report(on_step, "penulis_ok", names=[], source="")

    console.print(f"[green]BERES    [/green]{paper_title[:70]} masuk koleksi [dim]({dest_name})[/dim]")
    _report(on_step, "beres", file=dest_name, title=paper_title, pages=pages)
    return {
        "ok": True,
        "file": dest_name,
        "title": paper_title,
        "faculty": item_faculty,
    }


def import_by_doi(doi: str, faculty: str = None, on_step=None) -> dict:
    """Import an academic paper using DOI (resolves OA fulltext via Unpaywall).

    on_step(event, info) reports "cari", "ketemu", "unduh" (bytes), "ekstrak", "ekstrak_ok"/"ekstrak_gagal", "beres".
    """
    config.ensure_dirs()
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not clean_doi:
        return {"error": "DOI tidak boleh kosong"}

    # 1. Query Unpaywall for OA PDF, fallback to publisher landing page resolver
    console.print(f"[bold cyan]DOI      [/bold cyan]{clean_doi}: cari versi terbuka di Unpaywall")
    _report(on_step, "cari", doi=clean_doi)
    pdf_url = _resolve_unpaywall(clean_doi)
    if not pdf_url:
        pdf_url = _resolve_landing_page_pdf(f"https://doi.org/{clean_doi}")
    if not pdf_url:
        console.print(f"[red]GAGAL    [/red]{clean_doi}: tidak ada versi open access legal")
        return {"error": f"Tidak ditemukan naskah Open Access legal di Unpaywall atau penerbit untuk DOI: {clean_doi}"}
    host = urlparse(pdf_url).netloc or pdf_url

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
    console.print(f"[cyan]KETEMU   [/cyan]{title[:70]} ({year or 'tahun?'}), unduh dari {host}")
    _report(on_step, "ketemu", title=title, year=year, host=host, url=pdf_url)

    def _bytes(done, total):
        _report(on_step, "unduh", done=done, total=total, host=host)

    if _download(pdf_url, dest, on_bytes=_bytes):
        console.print(f"[cyan]UNDUH    [/cyan]{title[:50]}: {_mb(dest.stat().st_size)} tersimpan")
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
        pages = _extract_text(dest, title, on_step)
        console.print(f"[green]BERES    [/green]{title[:70]} masuk koleksi [dim]({fname})[/dim]")
        _report(on_step, "beres", file=fname, title=title, pages=pages)
        return {"ok": True, "title": title, "file": fname, "faculty": item_faculty}
    else:
        console.print(f"[red]GAGAL    [/red]{title[:50]}: PDF tidak bisa diunduh dari {host}")
        return {"error": f"Gagal mengunduh PDF dari URL: {pdf_url}"}


