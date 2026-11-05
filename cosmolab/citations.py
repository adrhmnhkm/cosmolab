"""
CosmoLab University: Citation & Bibliography Formatter (APA 7th, Chicago 17th, & RIS)
Supports automated academic citation styling for papers, literature reviews, and Zotero/Mendeley ingestion.
"""

import re
from pathlib import Path
from . import config


def _infer_author(paper: dict) -> str:
    """Infer author name from title, metadata, or file name."""
    explicit_author = paper.get("author") or paper.get("authors")
    if explicit_author:
        if isinstance(explicit_author, list):
            return ", ".join(explicit_author)
        return str(explicit_author)

    title = paper.get("title") or ""
    # Check for patterns like "Al-Ghazali on Causality", "Craig's Kalam Argument", "By John Doe"
    by_match = re.search(r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", title)
    if by_match:
        return by_match.group(1)

    # Check for canonical classical names
    canonical_thinkers = [
        ("Al-Ghazali", "Al-Ghazālī, Abū Ḥāmid"),
        ("Ibn Sina", "Ibn Sīnā (Avicenna)"),
        ("Avicenna", "Ibn Sīnā (Avicenna)"),
        ("Ibn Rushd", "Ibn Rushd (Averroës)"),
        ("Averroes", "Ibn Rushd (Averroës)"),
        ("Aquinas", "Aquinas, Thomas"),
        ("Hume", "Hume, David"),
        ("Kant", "Kant, Immanuel"),
        ("Leibniz", "Leibniz, Gottfried Wilhelm"),
        ("Craig", "Craig, William Lane"),
        ("Plantinga", "Plantinga, Alvin"),
        ("Mackie", "Mackie, J. L."),
        ("Swinburne", "Swinburne, Richard"),
        ("Dennett", "Dennett, Daniel"),
    ]
    for key, formal in canonical_thinkers:
        if key.lower() in title.lower():
            return formal

    return "Anonim (CosmoLab Corpus)"


def format_in_text_apa(paper: dict) -> str:
    """Format in-text citation: (Author, Year)."""
    author = _infer_author(paper)
    last_name = author.split(",")[-1].strip() if "," in author else author.split()[-1]
    year = paper.get("year") or "n.d."
    return f"({last_name}, {year})"


def format_apa(paper: dict) -> str:
    """Format reference in APA 7th Edition style."""
    author = _infer_author(paper)
    year = paper.get("year") or "n.d."
    title = paper.get("title") or "Untitled"
    doi = paper.get("doi") or ""
    url = paper.get("url") or ""

    doi_part = f" https://doi.org/{doi}" if doi else (f" {url}" if url else "")
    return f"{author}. ({year}). *{title}*.{doi_part}".strip()


def format_chicago_bib(paper: dict) -> str:
    """Format bibliographic entry in Chicago 17th Manual of Style."""
    author = _infer_author(paper)
    year = paper.get("year") or "n.d."
    title = paper.get("title") or "Untitled"
    doi = paper.get("doi") or ""
    url = paper.get("url") or ""

    loc = f" https://doi.org/{doi}." if doi else (f" {url}." if url else ".")
    return f"{author}. {year}. \"{title}.\"{loc}".strip()


def format_chicago_note(paper: dict, page: str = "") -> str:
    """Format Chicago 17th Footnote / Full Note."""
    author = _infer_author(paper)
    clean_author = author.replace(",", "")
    year = paper.get("year") or "n.d."
    title = paper.get("title") or "Untitled"
    page_part = f", {page}" if page else ""
    return f"{clean_author}, \"{title}\" ({year}){page_part}."


def export_ris(papers: list[dict], out_path: Path | None = None) -> Path:
    """
    Export papers to standard Research Information Systems (RIS) format
    directly importable by Zotero, Mendeley, and EndNote.
    """
    config.ensure_dirs()
    out_path = out_path or (config.ROOT / "references.ris")

    entries = []
    for p in papers:
        title = p.get("title") or "Untitled"
        year = str(p.get("year") or "")
        author = _infer_author(p)
        doi = p.get("doi") or ""
        url = p.get("url") or ""
        abstract = p.get("abstract") or p.get("thesis") or ""

        lines = [
            "TY  - JOUR",
            f"TI  - {title}",
            f"AU  - {author}",
        ]
        if year:
            lines.append(f"PY  - {year}")
        if doi:
            lines.append(f"DO  - {doi}")
        if url:
            lines.append(f"UR  - {url}")
        if abstract:
            clean_abs = " ".join(str(abstract).split())
            lines.append(f"AB  - {clean_abs}")
        lines.append("ER  - ")
        entries.append("\n".join(lines))

    out_path.write_text("\n\n".join(entries), encoding="utf-8")
    return out_path
