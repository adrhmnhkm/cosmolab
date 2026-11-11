import re
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from rich.console import Console
from . import config
from .storage import read_meta
from .utils import fire_cb as _fire_cb

console = Console(force_terminal=True, legacy_windows=False)

PAGE_MARKER_RE = re.compile(r"--- \[(?:Halaman|Page)\s+(\d+)\] ---", re.IGNORECASE)
_PAGES_CACHE: dict[str, list[dict]] = {}


def _pdf_to_text(path, include_page_markers: bool = True) -> str:
    """Extract clean, layout-aware text from PDF with header/footer filtering and page markers."""
    doc = fitz.open(path)
    pages_text = []
    for page in doc:
        page_num = page.number + 1
        h = page.rect.height
        # sort=True sorts blocks in true reading order (handling multi-column layouts)
        blocks = page.get_text("blocks", sort=True)
        page_blocks = []
        for b in blocks:
            # b: (x0, y0, x1, y1, text, block_no, block_type)
            if len(b) > 6 and b[6] != 0:  # Skip image blocks
                continue
            text = b[4].strip()
            if not text:
                continue
            # Filter out running header/footer (extreme top or bottom margin if short)
            if (b[1] < 32 or b[3] > h - 32) and len(text.splitlines()) <= 1 and len(text) < 90:
                continue
            page_blocks.append(text)

        if page_blocks:
            body = "\n\n".join(page_blocks)
            if include_page_markers:
                pages_text.append(f"--- [Halaman {page_num}] ---\n{body}")
            else:
                pages_text.append(body)

    doc.close()
    return "\n\n".join(pages_text)


def extract_pages_from_pdf(path: Path | str) -> list[dict]:
    """Extract structured pages with paragraph blocks from a PDF file."""
    path = Path(path)
    if not path.exists():
        return []

    doc = fitz.open(path)
    pages = []
    for page in doc:
        page_num = page.number + 1
        h = page.rect.height
        blocks = page.get_text("blocks", sort=True)
        page_blocks = []
        for b in blocks:
            if len(b) > 6 and b[6] != 0:
                continue
            text = b[4].strip()
            if not text:
                continue
            if (b[1] < 32 or b[3] > h - 32) and len(text.splitlines()) <= 1 and len(text) < 90:
                continue
            page_blocks.append(text)

        if page_blocks:
            body = "\n\n".join(page_blocks)
            paragraphs = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 30]
            pages.append({
                "page": page_num,
                "text": body,
                "paragraphs": paragraphs
            })

    doc.close()
    return pages


def extract_pages_from_text(text: str) -> list[dict]:
    """Extract structured pages from text that contains page markers, with robust fallback."""
    if not text or not text.strip():
        return []

    parts = PAGE_MARKER_RE.split(text)
    if len(parts) <= 1:
        # Fallback for text files extracted before page markers were added
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
        return [{"page": 1, "text": text, "paragraphs": paragraphs}]

    pages = []
    # parts: [preamble, page_num_1, body_1, page_num_2, body_2, ...]
    for i in range(1, len(parts), 2):
        try:
            page_num = int(parts[i])
        except ValueError:
            page_num = (i // 2) + 1
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        paragraphs = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 30]
        pages.append({
            "page": page_num,
            "text": body,
            "paragraphs": paragraphs
        })
    return pages


def get_paper_pages(file_or_stem: str) -> list[dict]:
    """Retrieve structured pages for a paper from PDF (preferred) or extracted text file."""
    stem = Path(file_or_stem).stem
    if stem in _PAGES_CACHE:
        return _PAGES_CACHE[stem]

    # 1. Try reading directly from PDF if available
    pdf_path = config.PDF_DIR / f"{stem}.pdf"
    if not pdf_path.exists() and file_or_stem.endswith(".pdf"):
        pdf_path = config.PDF_DIR / file_or_stem

    if pdf_path.exists():
        try:
            pages = extract_pages_from_pdf(pdf_path)
            if pages:
                _PAGES_CACHE[stem] = pages
                return pages
        except Exception:
            pass

    # 2. Try reading from extracted text file
    txt_path = config.TEXT_DIR / f"{stem}.txt"
    if txt_path.exists():
        try:
            text = txt_path.read_text(encoding="utf-8")
            pages = extract_pages_from_text(text)
            if pages:
                _PAGES_CACHE[stem] = pages
                return pages
        except Exception:
            pass

    return []




def extract_all(force: bool = False, progress_cb: callable = None, files: list[str] = None) -> dict:
    config.ensure_dirs()
    stats = {"ok": 0, "missing": 0, "empty": 0, "corrupt": 0}
    target_set = set(files) if files else None

    for rec in read_meta():
        fname = rec.get("file")
        if target_set and fname not in target_set and Path(fname).stem not in target_set:
            continue

        pdf = config.PDF_DIR / fname
        txt_out = config.TEXT_DIR / (pdf.stem + ".txt")
        if not pdf.exists():
            stats["missing"] += 1
            console.print(f"[red]FAIL  Missing PDF: {rec['file']}[/red]")
            _fire_cb(progress_cb, "extract_missing", f"File PDF hilang: {rec['file']}", {"file": rec["file"]})
            continue
        if not force and txt_out.exists() and txt_out.stat().st_size > 0:
            stats["ok"] += 1
            console.print(f"[dim]SKIP  Already extracted: {pdf.stem}[/dim]")
            continue
        try:
            console.print(f"[cyan]EXTRACT  {pdf.stem}[/cyan]")
            _fire_cb(progress_cb, "extract_start", f"Mengekstrak teks PDF: {pdf.stem[:55]}...", {"file": pdf.name})
            text = _pdf_to_text(pdf)
        except Exception as e:
            console.print(f"[red]CORRUPT  {pdf.name} ({type(e).__name__})[/red]")
            stats["corrupt"] += 1
            _fire_cb(progress_cb, "extract_fail", f"PDF korup/gagal ekstrak: {pdf.name} ({type(e).__name__})", {"file": pdf.name})
            continue
        if not text.strip():
            stats["empty"] += 1
            console.print(f"[yellow]EMPTY  {pdf.name}[/yellow]")
            _fire_cb(progress_cb, "extract_fail", f"PDF tidak memiliki teks terdeteksi: {pdf.name}", {"file": pdf.name})
            continue
        txt_out.write_text(text, encoding="utf-8")
        stats["ok"] += 1
        console.print(f"[green]OK  {pdf.stem}[/green]")
        _fire_cb(progress_cb, "extract_ok", f"Ekstraksi teks sukses ({len(text):,} karakter): {pdf.stem[:50]}", {"file": pdf.name, "chars": len(text)})
    return stats
