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
from . import writer as _writer
from . import inspector as _inspector
from . import retrieval as _retrieval
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
    delay: float = typer.Option(0.5, "--delay", "-d", help="Politeness delay between downloads per worker"),
    auto_extract: bool = typer.Option(True, "--extract/--no-extract", help="Automatically extract text from downloaded PDFs")
):
    """Search arXiv, DOAJ, S2 & OpenAlex and download OA PDFs in parallel with smart deduplication."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Harvesting papers in parallel...", total=None)
        stats = _harvest.harvest(query, max_results=max_results, workers=workers, delay=delay)
        progress.update(task, completed=1, description="[green]Harvest complete")
    
    _print_stats_table(stats, title="Harvest Results")
    
    if auto_extract and stats.get("downloaded", 0) > 0:
        with Progress() as progress:
            ext_task = progress.add_task("[cyan]Auto-extracting text from PDFs...", total=None)
            ext_stats = _extract.extract_all()
            progress.update(ext_task, completed=1, description="[green]Extract complete")
        _print_stats_table(ext_stats, title="Auto-Extraction Results")

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
    concurrency: int = typer.Option(4, "--concurrency", "-c", help="Number of concurrent LLM analysis workers"),
    lang: str = typer.Option("id", "--lang", "-l", help="Output analysis language: 'id' or 'en'"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-analysis even if JSON already exists")
):
    """Run parallel LLM analysis on extracted paper texts using Pydantic structured output."""
    from .storage import read_meta
    meta = read_meta()
    total_texts = len([m for m in meta if (config.TEXT_DIR / (m["file"].replace(".pdf", ".txt"))).exists()])
    
    with Progress() as progress:
        task = progress.add_task(f"[cyan]Analyzing papers with LLM ({lang.upper()}, concurrency={concurrency})...", total=total_texts)
        stats = _analyze.analyze_all(
            model=model,
            concurrency=concurrency,
            lang=lang,
            force=force,
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
def search(
    query: str,
    limit: int = typer.Option(5, "--limit", "-l", help="Number of papers to return"),
    hybrid: bool = typer.Option(True, "--hybrid/--exact", help="Use hybrid semantic expansion + RRF ranking instead of exact FTS only")
):
    """Search papers using Weighted FTS5 or Hybrid Semantic Concept Retrieval (RRF)."""
    if hybrid:
        results = _retrieval.hybrid_search(query, limit=limit, expand_concepts=True)
    else:
        results = _db.search(query, limit=limit)

    if not results:
        console.print(f"[yellow]No papers found matching: '{query}'[/yellow]")
        return

    mode_title = "Hybrid RRF Semantic" if hybrid else "Exact Weighted FTS5"
    table = Table(title=f"Search Results: '{query}' ({len(results)} found via {mode_title})", box=ROUNDED, show_lines=True)
    table.add_column("Title / Year", style="cyan", max_width=45)
    table.add_column("Type / Stance", style="magenta", justify="center")
    table.add_column("Score / Key Details", style="dim", max_width=60)

    for r in results:
        title_str = f"[bold]{r.get('title')}[/bold]\n({r.get('year', 'n.d.')}) [dim]{r.get('doi') or ''}[/dim]"
        type_str = f"{r.get('argument_type') or '-'}\n[bold]{r.get('supports_or_critiques') or '-'}[/bold]"
        score_info = f"[cyan]RRF:[/cyan] {r['rrf_score']}\n" if "rrf_score" in r else ""
        snippet_str = r.get("key_objection") or r.get("thesis") or r.get("snippet") or "-"
        table.add_row(title_str, type_str, f"{score_info}{snippet_str}")

    console.print(table)


@app.command()
def ask(
    question: str,
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
    top_k: int = typer.Option(6, "--top-k", "-k", help="Number of relevant papers to retrieve"),
    agentic: bool = typer.Option(True, "--agentic/--classic", help="Use Agentic Second Brain reasoning instead of Naive RAG"),
    save_obsidian: bool = typer.Option(False, "--save-obsidian", "-s", help="Save synthesis to Obsidian Vault")
):
    """Ask research questions across your paper corpus using Agentic Second Brain or Classic RAG."""
    from rich.markdown import Markdown
    if agentic:
        from . import ask_agent
        console.print("[bold cyan]Querying Corpus with Agentic Second Brain...[/bold cyan]")
        res = ask_agent.ask_agentic(question=question, model=model, top_k=top_k)
        console.print(Panel(Markdown(res["answer"]), title="[bold green]Agentic Dialectical Synthesis[/bold green]", border_style="green"))
        if save_obsidian:
            path = _export.export_agent_synthesis_to_obsidian(question, res["answer"], res["referenced_papers"])
            console.print(f"[bold cyan]Saved to Obsidian:[/bold cyan] {path}")
    else:
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


@app.command()
def article(
    topic: str,
    style: str = typer.Option("essay", "--style", "-s", help="Article style: 'essay', 'journal_review', or 'monograph'"),
    instructions: str = typer.Option("", "--instructions", "-i", help="Specific authoring perspective or focus"),
    save: bool = typer.Option(True, "--save/--no-save", help="Automatically save to Markdown and Standalone HTML"),
):
    """Generate a publication-ready long-form article/essay from Second Brain corpus."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Writing publication-ready article...", total=None)
        art = _writer.generate_article(topic=topic, style=style, custom_instructions=instructions)
        progress.update(task, completed=1, description="[green]Article writing complete")

    console.print(Panel(art["content_md"][:1500] + "\n\n... (lanjutan di file tersimpan)", title=f"Preview: {art['title']}", border_style="green"))
    console.print(f"[dim]Estimasi Waktu Baca: ~{art.get('reading_time_min', 5)} menit | Gaya: {art.get('style_name')}[/dim]")

    if save:
        paths = _writer.save_article(art)
        console.print(f"[bold green]OK  Disimpan:[/bold green] {paths['md_path']} dan {paths['html_path']}")


@app.command()
def inspect(
    doi: str = typer.Argument(..., help="DOI of the paper (e.g. 10.1016/j.concog.2020.102980 or full URL)"),
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save inspection breakdown to Markdown/JSON"),
):
    """Instant Paper Breakdown: Input any DOI -> get Abstract, Method, Result, Conclusion & Gaps."""
    from rich.markdown import Markdown

    with Progress() as progress:
        task = progress.add_task(f"[cyan]Bedah DOI '{doi}' via Crossref/S2/OpenAlex & AI...", total=None)
        res = _inspector.inspect_paper(doi, model=model)
        progress.update(task, completed=1, description="[green]Bedah paper selesai!")

    if not res.get("success"):
        console.print(f"[bold red]Error:[/bold red] {res.get('error')}")
        return

    a = res.get("analysis", {})

    # 1. Header Information
    oa_str = "[bold green]🟢 Open Access[/bold green]" if res.get("is_oa") else "[bold yellow]🔒 Paywalled / Berbayar[/bold yellow]"
    header_md = f"""# {res.get('title')}
**Penulis:** {', '.join(res.get('authors', [])) or 'Anonim'}  
**Jurnal / Venue:** [bold cyan]{res.get('venue') or res.get('publisher') or 'N/A'}[/bold cyan] ({res.get('year')})  
**DOI:** [{res.get('doi')}](https://doi.org/{res.get('doi')}) | **Sitasi:** {res.get('citation_count')} | **Status:** {oa_str}
"""
    console.print(Panel(Markdown(header_md), border_style="cyan"))

    # 2. One Sentence Takeaway
    if a.get("one_sentence_takeaway"):
        console.print(Panel(f"[bold italic]\"{a.get('one_sentence_takeaway')}\"[/bold italic]", title="[bold yellow]💡 Intisari 1 Kalimat[/bold yellow]", border_style="yellow"))

    # 3. Elsevier Style Highlights
    if a.get("highlights"):
        hl_lines = "\n".join(f"[bold green]•[/bold green] {h}" for h in a.get("highlights"))
        console.print(Panel(hl_lines, title="[bold green]⚡ Research Highlights (Elsevier Style)[/bold green]", border_style="green"))

    # 4. AMRC Breakdown Table/Panels
    console.print(Panel(a.get("problem_statement", "-"), title="[bold blue]📋 1. Latar Belakang & Masalah (Context)[/bold blue]", border_style="blue"))
    console.print(Panel(a.get("methodology", "-"), title="[bold magenta]🔬 2. Metodologi (Methodology)[/bold magenta]", border_style="magenta"))
    
    kf_lines = "\n".join(f"[cyan]•[/cyan] {k}" for k in a.get("key_findings", [])) if isinstance(a.get("key_findings"), list) else str(a.get("key_findings", "-"))
    console.print(Panel(kf_lines, title="[bold cyan]📊 3. Temuan Kunci (Key Results)[/bold cyan]", border_style="cyan"))
    
    console.print(Panel(a.get("conclusion", "-"), title="[bold green]🎯 4. Kesimpulan & Implikasi (Conclusion)[/bold green]", border_style="green"))

    # 5. Research Gaps for Thesis
    if a.get("research_gaps"):
        gap_lines = "\n".join(f"[red]•[/red] {g}" for g in a.get("research_gaps")) if isinstance(a.get("research_gaps"), list) else str(a.get("research_gaps"))
        console.print(Panel(gap_lines, title="[bold red]🔍 5. Celah Riset & Ide Penelitian Lanjutan (Research Gaps)[/bold red]", border_style="red"))

    # 6. Citations
    cite_text = f"[bold]APA 7th:[/bold]\n{res.get('apa_citation')}\n\n[bold]BibTeX:[/bold]\n{res.get('bibtex')}"
    console.print(Panel(cite_text, title="[dim]📝 Format Sitasi Siap Pakai[/dim]", border_style="dim"))

    if save:
        saved_path = _inspector.save_inspection(res)
        console.print(f"[bold green]OK Hasil bedah disimpan:[/bold green] {saved_path}")


@app.command()
def doi(
    doi: str = typer.Argument(..., help="DOI of the paper (alias for inspect)"),
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
):
    """Alias for 'cosmolab inspect'."""
    inspect(doi=doi, model=model, save=True)


if __name__ == "__main__":
    app()
