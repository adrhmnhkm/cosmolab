"""
CosmoLab Fast DOI Inspector & Smart Paper Breakdown (AMRC Engine)
Resolves academic papers by DOI via Crossref, Semantic Scholar, OpenAlex, and Unpaywall,
then uses LLM to generate structured Abstract, Method, Result, Conclusion,
Elsevier-style Research Highlights, and Research Gaps.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from openai import OpenAI
from rich.console import Console
from . import config
from . import db

console = Console(force_terminal=True, legacy_windows=False)

# None = follow the active project (config.ROOT).
INSPECTOR_DIR = None


def _inspector_dir() -> Path:
    return INSPECTOR_DIR or (config.ROOT / "inspections")


def ensure_inspector_dir():
    _inspector_dir().mkdir(parents=True, exist_ok=True)


def normalize_doi(raw: str) -> str:
    """
    Extract and clean a pure DOI string from URLs, prefixes, or raw text.
    Examples:
      - 'https://doi.org/10.1016/j.concog.2020.102980' -> '10.1016/j.concog.2020.102980'
      - 'doi: 10.1007/s00283-022-10224-8' -> '10.1007/s00283-022-10224-8'
    """
    if not raw:
        return ""
    cleaned = raw.strip()
    match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", cleaned)
    if match:
        doi = match.group(0).rstrip("./; ")
        return doi
    return cleaned.replace("https://doi.org/", "").replace("http://dx.doi.org/", "").strip()


def _reconstruct_openalex_abstract(inverted_index: dict) -> str:
    """Reconstruct linear abstract text from OpenAlex inverted index."""
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    pos_map = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            pos_map[pos] = word
    sorted_words = [pos_map[i] for i in sorted(pos_map.keys())]
    return " ".join(sorted_words)


def _clean_abstract(raw: str) -> str:
    """Remove HTML/JATS XML tags from abstract."""
    if not raw:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(cleaned.split())


def fetch_doi_metadata(doi: str) -> Dict[str, Any]:
    """
    Fetch comprehensive paper metadata and abstract from Crossref, Semantic Scholar,
    OpenAlex, and Unpaywall.
    """
    doi = normalize_doi(doi)
    if not doi:
        return {"error": "Format DOI tidak valid"}

    headers = {
        "User-Agent": f"CosmoLab/1.0 (mailto:{config.EMAIL})",
        "Accept": "application/json",
    }

    result = {
        "doi": doi,
        "title": "",
        "authors": [],
        "year": "n.d.",
        "venue": "",
        "publisher": "",
        "abstract": "",
        "citation_count": 0,
        "is_oa": False,
        "pdf_url": "",
        "url": f"https://doi.org/{doi}",
        "sources": [],
    }

    # 1. Query Crossref API
    try:
        cr_url = f"https://api.crossref.org/works/{doi}"
        r = requests.get(cr_url, headers=headers, timeout=12)
        if r.status_code == 200:
            msg = r.json().get("message", {})
            titles = msg.get("title", [])
            if titles:
                result["title"] = titles[0]
            
            # Authors
            authors = []
            for a in msg.get("author", []):
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                if not name and a.get("name"):
                    name = a.get("name")
                if name:
                    authors.append(name)
            result["authors"] = authors

            # Year
            issued = msg.get("issued", {}).get("date-parts", [[None]])[0]
            if issued and issued[0]:
                result["year"] = str(issued[0])

            # Container / Venue
            containers = msg.get("container-title", [])
            if containers:
                result["venue"] = containers[0]
            result["publisher"] = msg.get("publisher", "")
            result["citation_count"] = msg.get("is-referenced-by-count", 0)

            # Abstract if present in Crossref
            if msg.get("abstract"):
                result["abstract"] = _clean_abstract(msg["abstract"])

            result["sources"].append("Crossref")
    except Exception:
        pass

    # 2. Query Semantic Scholar (S2)
    try:
        s2_url = f"https://api.semanticscholar.org/graph/v1/paper/{doi}?fields=title,abstract,authors,year,venue,citationCount,openAccessPdf,tldr"
        r = requests.get(s2_url, headers={"User-Agent": "CosmoLab/1.0"}, timeout=12)
        if r.status_code == 404:
            s2_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,abstract,authors,year,venue,citationCount,openAccessPdf,tldr"
            r = requests.get(s2_url, headers={"User-Agent": "CosmoLab/1.0"}, timeout=12)

        if r.status_code == 200:
            s2_data = r.json()
            if not result["title"] and s2_data.get("title"):
                result["title"] = s2_data["title"]
            if not result["abstract"] and s2_data.get("abstract"):
                result["abstract"] = s2_data["abstract"]
            if not result["authors"] and s2_data.get("authors"):
                result["authors"] = [a.get("name") for a in s2_data["authors"] if a.get("name")]
            if result["year"] == "n.d." and s2_data.get("year"):
                result["year"] = str(s2_data["year"])
            if not result["venue"] and s2_data.get("venue"):
                result["venue"] = s2_data["venue"]
            if s2_data.get("citationCount"):
                result["citation_count"] = max(result["citation_count"], s2_data["citationCount"])
            
            oa = s2_data.get("openAccessPdf")
            if oa and isinstance(oa, dict) and oa.get("url"):
                result["is_oa"] = True
                result["pdf_url"] = oa["url"]

            result["sources"].append("Semantic Scholar")
    except Exception:
        pass

    # 3. Query OpenAlex API (if abstract still missing or to enrich)
    if not result["abstract"] or not result["title"]:
        try:
            oa_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
            r = requests.get(oa_url, headers=headers, timeout=12)
            if r.status_code == 200:
                oa_data = r.json()
                if not result["title"] and oa_data.get("title"):
                    result["title"] = oa_data["title"]
                if not result["abstract"] and oa_data.get("abstract_inverted_index"):
                    result["abstract"] = _reconstruct_openalex_abstract(oa_data["abstract_inverted_index"])
                if not result["authors"] and oa_data.get("authorships"):
                    result["authors"] = [
                        auth.get("author", {}).get("display_name", "")
                        for auth in oa_data["authorships"]
                        if auth.get("author", {}).get("display_name")
                    ]
                if result["year"] == "n.d." and oa_data.get("publication_year"):
                    result["year"] = str(oa_data["publication_year"])
                if oa_data.get("open_access", {}).get("is_oa"):
                    result["is_oa"] = True
                    oa_pdf = oa_data.get("open_access", {}).get("oa_url")
                    if oa_pdf and not result["pdf_url"]:
                        result["pdf_url"] = oa_pdf

                result["sources"].append("OpenAlex")
        except Exception:
            pass

    # 4. Check Unpaywall for OA PDF (if still unknown)
    if not result["is_oa"]:
        try:
            upw_url = f"https://api.unpaywall.org/v2/{doi}?email={config.EMAIL}"
            r = requests.get(upw_url, timeout=10)
            if r.status_code == 200:
                upw = r.json()
                if upw.get("is_oa"):
                    result["is_oa"] = True
                    loc = upw.get("best_oa_location") or {}
                    if loc.get("url_for_pdf"):
                        result["pdf_url"] = loc["url_for_pdf"]
        except Exception:
            pass

    return result


def _generate_bibtex(meta: Dict[str, Any]) -> str:
    """Generate clean BibTeX entry."""
    first_author = meta["authors"][0].split()[-1].lower() if meta["authors"] else "unknown"
    year = meta.get("year", "2024")
    cite_key = f"{first_author}{year}"
    authors_str = " and ".join(meta["authors"]) if meta["authors"] else "Unknown"
    
    return f"""@article{{{cite_key},
  title = {{{meta.get('title', 'Untitled')}}},
  author = {{{authors_str}}},
  journal = {{{meta.get('venue') or meta.get('publisher') or 'Academic Journal'}}},
  year = {{{year}}},
  doi = {{{meta.get('doi')}}},
  url = {{https://doi.org/{meta.get('doi')}}}
}}"""


def _generate_apa(meta: Dict[str, Any]) -> str:
    """Generate APA 7th style citation string."""
    authors = meta.get("authors", [])
    if len(authors) == 1:
        auth_str = authors[0]
    elif len(authors) == 2:
        auth_str = f"{authors[0]}, & {authors[1]}"
    elif len(authors) > 2:
        auth_str = f"{authors[0]} et al."
    else:
        auth_str = "Anonim"

    year = meta.get("year", "n.d.")
    title = meta.get("title", "Untitled")
    venue = meta.get("venue") or meta.get("publisher") or "Jurnal Ilmiah"
    doi = meta.get("doi", "")
    return f"{auth_str} ({year}). {title}. *{venue}*. https://doi.org/{doi}"


INSPECTION_SYSTEM_PROMPT = """Kamu adalah Asisten Peneliti Senior & Analis Paper Akademik (seperti Elsevier ScienceDirect Insights & Scopus AI).
Tugasmu adalah membedah dan mengekstrak isi artikel ilmiah dari judul, venue, dan abstrak yang diberikan menjadi struktur analisis AMRC (Abstract, Method, Result, Conclusion) yang sangat informatif, lugas, dan berbobot tinggi.

PANDUAN OUTPUT JSON (WAJIB FORMAT JSON VALID):
Berikan respons HANYA dalam format JSON valid dengan field berikut:
{
  "problem_statement": "Latar belakang masalah dan urgensi mengapa riset ini dilakukan (2-3 kalimat)",
  "methodology": "Desain riset, metode, instrumen, teori, atau model yang digunakan penulis (2-3 kalimat)",
  "key_findings": [
    "Poin temuan kunci / hasil 1 yang spesifik",
    "Poin temuan kunci / hasil 2 yang spesifik",
    "Poin temuan kunci / hasil 3 (jika ada)"
  ],
  "conclusion": "Kesimpulan akhir dan implikasi riset bagi perkembangan ilmu pengetahuan (2-3 kalimat)",
  "research_gaps": [
    "Celah riset atau limitasi 1 yang belum terjawab dan bisa diteliti lebih lanjut",
    "Ide topik/judul skripsi/tesis turunan yang sangat potensial dari paper ini"
  ],
  "highlights": [
    "Butir ringkas 1 ala Research Highlights Elsevier (maks 15 kata)",
    "Butir ringkas 2 ala Research Highlights Elsevier (maks 15 kata)",
    "Butir ringkas 3 ala Research Highlights Elsevier (maks 15 kata)"
  ],
  "one_sentence_takeaway": "Intisari paling berharga dari paper ini dalam 1 kalimat padat."
}

ATURAN:
- Gunakan Bahasa Indonesia akademis yang jernih, mengalir, dan mudah dipahami oleh mahasiswa dan dosen.
- Isi hanya dari abstrak dan metadata yang diberikan. Jangan menebak dari judul, bidang, atau nama jurnal.
- Field yang tidak ada di abstrak isi null (atau [] untuk daftar).
- Pastikan JSON valid tanpa tanda markdown pembungkus di luar JSON.
"""


class _Skip(Exception):
    """No abstract: skip the AI call."""


def inspect_paper(doi: str, model: str = None) -> Dict[str, Any]:
    """
    Complete end-to-end DOI inspection:
    1. Fetch metadata from Crossref / Semantic Scholar / OpenAlex
    2. Run LLM structured extraction (AMRC + Highlights + Gaps)
    3. Generate APA citation & BibTeX
    """
    model = model or config.LLM_MODEL
    clean_doi = normalize_doi(doi)

    meta = fetch_doi_metadata(clean_doi)
    if not meta.get("title"):
        return {
            "success": False,
            "error": f"DOI '{doi}' tidak ditemukan di Crossref, OpenAlex, maupun Semantic Scholar.",
            "doi": clean_doi,
        }

    # Prepare context for LLM
    authors_str = ", ".join(meta["authors"]) if meta["authors"] else "Unknown"
    abstract_text = meta.get("abstract") or ""

    prompt_user = f"""DATA ARTIKEL ILMIAH:
Judul: {meta['title']}
Penulis: {authors_str}
Tahun: {meta['year']}
Jurnal / Venue: {meta['venue']} (Penerbit: {meta.get('publisher')})
DOI: {meta['doi']}
Abstrak:
{abstract_text}
"""

    client = OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
    )

    analysis_data = {}
    note = ""
    if not abstract_text.strip():
        # Without an abstract the AI could only guess from the title and journal.
        note = "Abstrak tidak tersedia di indeks terbuka, jadi analisis AI tidak dibuat. Baca naskah lengkapnya."
    try:
        if note:
            raise _Skip()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": INSPECTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_user},
            ],
            temperature=0.2,
            timeout=120.0,
        )
        raw_content = resp.choices[0].message.content or ""
        
        # Strip potential markdown code fences ```json ... ```
        clean_json = re.sub(r"^```json\s*", "", raw_content.strip())
        clean_json = re.sub(r"\s*```$", "", clean_json.strip())
        analysis_data = json.loads(clean_json)
    except _Skip:
        analysis_data = {}
    except Exception as e:
        # No generic stand-in text: it would read like an analysis of this paper.
        analysis_data = {}
        note = f"Analisis AI gagal ({e}). Metadata dan sitasi di bawah tetap benar."

    # Combine into comprehensive result
    combined = {
        "success": True,
        "doi": meta["doi"],
        "title": meta["title"],
        "authors": meta["authors"],
        "year": meta["year"],
        "venue": meta["venue"],
        "publisher": meta["publisher"],
        "citation_count": meta["citation_count"],
        "is_oa": meta["is_oa"],
        "pdf_url": meta["pdf_url"],
        "url": meta["url"],
        "abstract": meta["abstract"],
        "apa_citation": _generate_apa(meta),
        "bibtex": _generate_bibtex(meta),
        "analysis": analysis_data,
        "analysis_note": note,
        "inspected_at": datetime.now().isoformat(),
    }

    return combined


def save_inspection(inspection_data: Dict[str, Any]) -> Path:
    """Save inspection result to markdown and JSON in data/inspections/."""
    ensure_inspector_dir()
    doi_slug = re.sub(r"[^a-zA-Z0-9]", "_", inspection_data.get("doi", "unknown"))
    time_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{time_prefix}_{doi_slug}"

    json_path = _inspector_dir() / f"{base_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(inspection_data, f, indent=2, ensure_ascii=False)

    # Format Markdown
    a = inspection_data.get("analysis", {})
    hf_str = "\n".join(f"- {h}" for h in a.get("highlights", []))
    kf_str = "\n".join(f"- {f}" for f in a.get("key_findings", []))
    rg_str = "\n".join(f"- {g}" for g in a.get("research_gaps", []))
    auth_str = ", ".join(inspection_data.get("authors", []))

    md_content = f"""# {inspection_data.get('title')}

**Penulis:** {auth_str}  
**Tahun:** {inspection_data.get('year')} | **Jurnal:** {inspection_data.get('venue')}  
**DOI:** [{inspection_data.get('doi')}]({inspection_data.get('url')}) | **Sitasi:** {inspection_data.get('citation_count')}  
**Status Akses:** {'🟢 Open Access' if inspection_data.get('is_oa') else '🔒 Paywalled / Berbayar'}

---

### 💡 Intisari 1 Kalimat
> {a.get('one_sentence_takeaway', '-')}

### ⚡ Research Highlights (Elsevier Style)
{hf_str}

### 📋 Latar Belakang & Masalah
{a.get('problem_statement', '-')}

### 🔬 Metodologi
{a.get('methodology', '-')}

### 📊 Temuan Kunci (Key Results)
{kf_str}

### 🎯 Kesimpulan & Implikasi
{a.get('conclusion', '-')}

### 🔍 Celah Riset & Ide Penelitian Lanjutan (Research Gaps)
{rg_str}

---

### 📝 Sitasi Standar
**APA 7th:**  
`{inspection_data.get('apa_citation')}`

**BibTeX:**
```bibtex
{inspection_data.get('bibtex')}
```
"""
    md_path = _inspector_dir() / f"{base_name}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return md_path

