import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.panel import Panel
from rich.box import DOUBLE, ROUNDED
from rich.syntax import Syntax
from . import harvest as _harvest
from . import extract as _extract
from . import analyze as _analyze
from . import synthesize as _synthesize
from . import db as _db
from . import ask as _ask
from . import export as _export
from . import config

app = typer.Typer(help="cosmolab - personal research pipeline for academic papers")
console = Console(force_terminal=True, legacy_windows=False)


def _print_stats_table(stats: dict, title: str = "Statistics"):
    """Print stats as formatted table."""
    table = Table(title=title, box=DOUBLE, show_lines=True)
    table.add_column("Category", style="cyan")
    table.add_column("Count / Details", style="green", justify="right")
    
    for key, value in stats.items():
        if isinstance(value, dict):
            for k, v in value.items():
                table.add_row(f"{key}.{k}", str(v))
        else:
            table.add_row(key.capitalize() if isinstance(key, str) else str(key), str(value))
    
    console.print(table)


@app.command()
def harvest(
    query: str,
    max_results: int = typer.Option(40, "--max-results", "-n", help="Maximum papers to harvest"),
    workers: int = typer.Option(4, "--workers", "-w", help="Number of parallel download threads"),
    delay: float = typer.Option(0.5, "--delay", "-d", help="Politeness delay between downloads per worker")
):
    """Search arXiv & OpenAlex and download OA PDFs in parallel with smart deduplication."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Harvesting papers in parallel...", total=None)
        stats = _harvest.harvest(query, max_results=max_results, workers=workers, delay=delay)
        progress.update(task, completed=1, description="[green]Harvest complete")
    
    _print_stats_table(stats, title="Harvest Results")
    _db.sync_all()


@app.command()
def extract(force: bool = typer.Option(False, "--force", "-f", help="Re-extract even if text file already exists")):
    """Extract text from all downloaded PDFs with layout-aware block sorting."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Extracting text from PDFs...", total=None)
        stats = _extract.extract_all(force=force)
        progress.update(task, completed=1, description="[green]Extract complete")
    
    _print_stats_table(stats, title="Extraction Results")
    _db.sync_all()


@app.command()
def analyze(
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
    concurrency: int = typer.Option(4, "--concurrency", "-c", help="Number of concurrent LLM analysis workers")
):
    """Run parallel LLM analysis on extracted paper texts using Pydantic structured output."""
    from .storage import read_meta
    meta = read_meta()
    total_texts = len([m for m in meta if (config.TEXT_DIR / (m["file"].replace(".pdf", ".txt"))).exists()])
    
    with Progress() as progress:
        task = progress.add_task(f"[cyan]Analyzing papers with LLM (concurrency={concurrency})...", total=total_texts)
        stats = _analyze.analyze_all(
            model=model,
            concurrency=concurrency,
            progress_cb=lambda: progress.advance(task)
        )
        progress.update(task, completed=total_texts, description="[green]Analysis complete")
    
    _print_stats_table(stats, title="Analysis Results")
    _db.sync_all()


@app.command()
def synthesize(
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
    lang: str = "en"
):
    """Build a comprehensive cross-paper synthesis report (EN or ID)."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Generating synthesis report...", total=None)
        result = _synthesize.synthesize(model=model, lang=lang)
        progress.update(task, completed=1, description="[green]Report generated")
    
    _print_stats_table(result, title="Synthesis Report")


@app.command()
def sync():
    """Sync file system metadata, extracted texts, and analyses into SQLite DB."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Syncing SQLite database and FTS5 index...", total=None)
        stats = _db.sync_all()
        progress.update(task, completed=1, description="[green]Database sync complete")
    
    _print_stats_table(stats, title="Database Sync Status")


@app.command()
def search(query: str, limit: int = 5):
    """Full-text search (FTS5) across paper titles, abstracts, extracted texts, and premises."""
    results = _db.search(query, limit=limit)
    if not results:
        console.print(f"[yellow]No papers found matching: '{query}'[/yellow]")
        return

    table = Table(title=f"Search Results for: '{query}' ({len(results)} found)", box=ROUNDED, show_lines=True)
    table.add_column("Title / Year", style="cyan", max_width=45)
    table.add_column("Type / Stance", style="magenta", justify="center")
    table.add_column("Key Objection / Snippet", style="dim", max_width=60)

    for r in results:
        title_str = f"[bold]{r.get('title')}[/bold]\n({r.get('year', 'n.d.')}) [dim]{r.get('doi') or ''}[/dim]"
        type_str = f"{r.get('argument_type') or '-'}\n[bold]{r.get('supports_or_critiques') or '-'}[/bold]"
        snippet_str = r.get("key_objection") or r.get("snippet") or "-"
        table.add_row(title_str, type_str, snippet_str)

    console.print(table)


@app.command()
def ask(
    question: str,
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of relevant papers to retrieve")
):
    """Ask research questions across your paper corpus using RAG (Retrieval-Augmented Generation)."""
    _ask.ask(question=question, model=model, top_k=top_k)


@app.command()
def export(
    format: str = typer.Option("obsidian", "--format", "-f", help="Export format: 'obsidian' or 'bibtex'"),
    out: str = typer.Option(None, "--out", "-o", help="Custom output directory or file path")
):
    """Export corpus to Obsidian Vault markdown notes or BibTeX bibliography."""
    from pathlib import Path
    fmt = format.lower().strip()
    if fmt == "bibtex":
        out_path = Path(out) if out else None
        res = _export.export_bibtex(out_path=out_path)
        console.print(f"[bold green]BibTeX export completed:[/bold green] {res}")
    elif fmt == "obsidian":
        out_dir = Path(out) if out else None
        res = _export.export_obsidian(vault_dir=out_dir)
        console.print(f"[bold green]Obsidian Vault exported to:[/bold green] {res}")
    else:
        console.print(f"[red]Unknown format '{format}'. Use 'obsidian' or 'bibtex'.[/red]")


@app.command()
def graph(paper: str):
    """Generate and display Mermaid argument flowchart for a specific paper."""
    mermaid_str = _export.generate_mermaid_graph(paper)
    console.print(Panel(
        Syntax(mermaid_str, "mermaid", theme="monokai", line_numbers=True),
        title=f"Mermaid Argument Graph: {paper}",
        border_style="cyan"
    ))


@app.command()
def ui(port: int = typer.Option(8501, "--port", "-p", help="Port to run web dashboard")):
    """Launch interactive local Web Dashboard (Streamlit)."""
    import subprocess
    import sys
    from pathlib import Path
    web_script = Path(__file__).parent / "web.py"
    console.print(f"[bold cyan]Launching Cosmolab Web Dashboard on port {port}...[/bold cyan]")
    console.print(f"[dim]URL: http://localhost:{port}[/dim]")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(web_script), "--server.port", str(port)])


@app.command()
def status():
    """Show comprehensive pipeline and database counts."""
    from . import config
    from .storage import read_meta
    meta = read_meta()

    db_papers = 0
    db_analyses = 0
    if config.DB_FILE.exists():
        try:
            con = _db.get_connection()
            db_papers = con.execute("SELECT count(*) FROM papers").fetchone()[0]
            db_analyses = con.execute("SELECT count(*) FROM analyses").fetchone()[0]
            con.close()
        except Exception:
            pass

    stats = {
        "Metadata Papers": len(meta),
        "PDF Files": len(list(config.PDF_DIR.glob("*.pdf"))),
        "Extracted Texts": len(list(config.TEXT_DIR.glob("*.txt"))),
        "Analysis JSONs": len(list(config.ANALYSIS_DIR.glob("*.json"))),
        "Synthesis Reports": len(list(config.SYNTH_DIR.glob("*.md"))),
        "Database Indexed Papers": db_papers,
        "Database Indexed Analyses": db_analyses,
    }
    _print_stats_table(stats, title="Cosmolab Pipeline & DB Status")


if __name__ == "__main__":
    app()
