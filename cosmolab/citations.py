"""
CosmoLab University: Citation & Bibliography Formatter (APA 7th, Chicago 17th, & RIS)
Supports automated academic citation styling for papers, literature reviews, and Zotero/Mendeley ingestion.
"""

import re
from pathlib import Path
from . import config
from . import authors as _authors


def _infer_author(paper: dict) -> str:
    """Infer author name from title, metadata, or file name."""
    names = _authors.as_list(paper.get("authors")) or _authors.as_list(paper.get("author"))
    if names:
        return _authors.display(names)

    title = paper.get("title") or ""
    # Check for patterns like "By John Doe", "Craig's Kalam Argument", "Dewey on Education"
    by_match = re.search(r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", title)
    if by_match:
        return by_match.group(1)

    possessive_match = re.search(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)(?:'s|’s)\s+", title)
    if possessive_match:
        return possessive_match.group(1)

    # Check for canonical thinkers and foundational scholars across disciplines
    canonical_thinkers = [
        # Filsafat & Teologi Klasik/Modern
        ("Al-Ghazali", "Al-Ghazālī, Abū Ḥāmid"),
        ("Ghazali", "Al-Ghazālī, Abū Ḥāmid"),
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
        # Pendidikan & Pedagogi
        ("Dewey", "Dewey, John"),
        ("Vygotsky", "Vygotsky, Lev"),
        ("Piaget", "Piaget, Jean"),
        ("Freire", "Freire, Paulo"),
        ("Bruner", "Bruner, Jerome"),
        # Ekonomi, Bisnis & Manajemen
        ("Keynesian", "Keynes, John Maynard"),
        ("Keynes", "Keynes, John Maynard"),
        ("Adam Smith", "Smith, Adam"),
        ("Schumpeter", "Schumpeter, Joseph"),
        ("Friedman", "Friedman, Milton"),
        ("Hayek", "Hayek, Friedrich"),
        ("Porter", "Porter, Michael E."),
        # Sosiologi, Hukum & Kebijakan
        ("Weber", "Weber, Max"),
        ("Durkheim", "Durkheim, Émile"),
        ("Foucault", "Foucault, Michel"),
        ("Habermas", "Habermas, Jürgen"),
        ("Bourdieu", "Bourdieu, Pierre"),
        ("Rawls", "Rawls, John"),
        # Psikologi & Perilaku
        ("Kahneman", "Kahneman, Daniel"),
        ("Bandura", "Bandura, Albert"),
        ("Skinner", "Skinner, B. F."),
        # Sains & Komputasi
        ("Turing", "Turing, Alan"),
        ("Shannon", "Shannon, Claude"),
        ("Einstein", "Einstein, Albert"),
        ("Newton", "Newton, Isaac"),
        ("Darwin", "Darwin, Charles"),
    ]
    for key, formal in canonical_thinkers:
        if re.search(r"\b" + re.escape(key) + r"\b", title, re.IGNORECASE):
            return formal

    return "Anonim"


def format_in_text_apa(paper: dict) -> str:
    """Format in-text citation: (Author, Year)."""
    names = _authors.as_list(paper.get("authors"))
    if names:
        short = _authors.in_text(names)
    else:
        author = _infer_author(paper)
        short = author.split(",")[0].strip() if "," in author else author.split()[-1]
    year = paper.get("year") or "n.d."
    return f"({short}, {year})"


def format_apa(paper: dict) -> str:
    """Format reference in APA 7th Edition style."""
    author = _infer_author(paper)
    year = paper.get("year") or "n.d."
    title = paper.get("title") or "Untitled"
    doi = paper.get("doi") or ""
    url = paper.get("url") or ""

    doi_part = f" https://doi.org/{doi}" if doi else (f" {url}" if url else "")
    return f"{author.rstrip('.')}. ({year}). *{title}*.{doi_part}".strip()


def format_chicago_bib(paper: dict) -> str:
    """Format bibliographic entry in Chicago 17th Manual of Style."""
    author = _infer_author(paper)
    year = paper.get("year") or "n.d."
    title = paper.get("title") or "Untitled"
    doi = paper.get("doi") or ""
    url = paper.get("url") or ""

    loc = f" https://doi.org/{doi}." if doi else (f" {url}." if url else ".")
    return f"{author.rstrip('.')}. {year}. \"{title}.\"{loc}".strip()


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
        author_lines = [f"AU  - {n}" for n in _authors.as_list(p.get("authors"))] or [f"AU  - {_infer_author(p)}"]
        doi = p.get("doi") or ""
        url = p.get("url") or ""
        abstract = p.get("abstract") or p.get("thesis") or ""

        lines = [
            "TY  - JOUR",
            f"TI  - {title}",
            *author_lines,
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
