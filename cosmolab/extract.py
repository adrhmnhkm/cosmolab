try:
    import pymupdf as fitz
except ImportError:
    import fitz

from rich.console import Console
from . import config
from .storage import read_meta
from .utils import fire_cb as _fire_cb

console = Console(force_terminal=True, legacy_windows=False)


def _pdf_to_text(path) -> str:
    """Extract clean, layout-aware text from PDF with header/footer filtering."""
    doc = fitz.open(path)
    all_blocks = []
    for page in doc:
        h = page.rect.height
        # sort=True sorts blocks in true reading order (handling multi-column layouts)
        blocks = page.get_text("blocks", sort=True)
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
            all_blocks.append(text)
    doc.close()
    return "\n\n".join(all_blocks)




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
