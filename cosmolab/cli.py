import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path

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

app = typer.Typer(help="cosmolab - multidisciplinary research assistant")
console = Console(force_terminal=True, legacy_windows=False)
project_app = typer.Typer(help="Kelola proyek klien (satu folder data per proyek)")
app.add_typer(project_app, name="project")
sinta_app = typer.Typer(help="Daftar peringkat jurnal SINTA (dicocokkan lewat ISSN)")
app.add_typer(sinta_app, name="sinta")


@app.callback()
def _main(
    project: str = typer.Option(
        None, "--project", "-P",
        envvar="COSMOLAB_PROJECT",
        help="Proyek klien yang dipakai. Tanpa opsi ini, data utama (folder data/) yang dipakai.",
    ),
):
    """cosmolab - multidisciplinary research assistant."""
    try:
        config.use_project(project)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Nama proyek, misalnya 2026-11-klien-a"),
    client: str = typer.Option("", "--client", "-c", help="Nama klien"),
    description: str = typer.Option("", "--description", "-d", help="Ringkasan pekerjaan"),
):
    """Buat proyek klien baru dengan folder data sendiri."""
    try:
        path = config.create_project(name, client=client, description=description)
    except (ValueError, FileExistsError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Proyek dibuat:[/green] {path}")
    console.print(f"[dim]Pakai dengan: cosmolab -P {path.name} harvest \"kata kunci\"  atau  cosmolab -P {path.name} ui[/dim]")


@project_app.command("list")
def project_list():
    """Tampilkan semua proyek klien."""
    projects = config.list_projects()
    if not projects:
        console.print("[yellow]Belum ada proyek. Buat dengan: cosmolab project new <nama>[/yellow]")
        return
    table = Table(title="Proyek Klien", box=ROUNDED)
    table.add_column("Nama", style="cyan")
    table.add_column("Klien")
    table.add_column("Dibuat", style="dim")
    table.add_column("Paper", justify="right")
    for p in projects:
        n_pdf = len(list((Path(p["path"]) / "pdf").glob("*.pdf")))
        table.add_row(p["name"], p.get("client", ""), str(p.get("created", ""))[:10], str(n_pdf))
    console.print(table)


@project_app.command("info")
def project_show():
    """Tampilkan proyek yang sedang aktif dan lokasi datanya."""
    info = config.project_info()
    console.print(f"Proyek aktif: [cyan]{config.PROJECT or '(data utama)'}[/cyan]")
    if info.get("client"):
        console.print(f"Klien: {info['client']}")
    if info.get("description"):
        console.print(f"Ringkasan: {info['description']}")
    console.print(f"Folder data: {config.ROOT}")


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
    auto_extract: bool = typer.Option(True, "--extract/--no-extract", help="Automatically extract text from downloaded PDFs"),
    indonesia: bool = typer.Option(False, "--indonesia", help="Hanya jurnal Indonesia / artikel berbahasa Indonesia (via OpenAlex)"),
):
    """Search arXiv, DOAJ, S2 & OpenAlex and download OA PDFs in parallel with smart deduplication."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Harvesting papers in parallel...", total=None)
        stats = _harvest.harvest(query, max_results=max_results, workers=workers, delay=delay, indonesia=indonesia)
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
    save_obsidian: bool = typer.Option(False, "--save-obsidian", "-s", help="Save synthesis to Obsidian Vault"),
    check: bool = typer.Option(True, "--cek/--no-cek", help="Check every cited claim against the cited papers"),
):
    """Ask research questions across your paper corpus using Agentic Second Brain or Classic RAG."""
    from rich.markdown import Markdown
    if agentic:
        from . import ask_agent
        console.print("[bold cyan]Querying Corpus with Agentic Second Brain...[/bold cyan]")
        res = ask_agent.ask_agentic(question=question, model=model, top_k=top_k)
        console.print(Panel(Markdown(res["answer"]), title="[bold green]Agentic Dialectical Synthesis[/bold green]", border_style="green"))
        citations = res.get("grounded_citations", [])
        if citations:
            from rich.table import Table
            tbl = Table(title="Bukti Verbatim & Nomor Halaman PDF Terverifikasi", border_style="cyan", show_lines=True)
            tbl.add_column("Paper dan Tahun", style="bold white", width=32)
            tbl.add_column("Halaman", style="yellow", justify="center", width=12)
            tbl.add_column("Kutipan Verbatim Asli", style="italic green")
            for c in citations[:6]:
                tbl.add_row(f"{c['paper_title']} ({c['year']})", c["page_label"], f'"{c["verbatim"]}"')
            console.print(tbl)
        if save_obsidian:
            path = _export.export_agent_synthesis_to_obsidian(question, res["answer"], res["referenced_papers"])
            console.print(f"[bold cyan]Saved to Obsidian:[/bold cyan] {path}")
        answer, numbered = res["answer"], res.get("referenced_papers")
    else:
        answer, numbered = _ask.ask(question=question, model=model, top_k=top_k), None
    if check:
        _print_claim_report(answer, model, numbered)


CLAIM_STYLES = {"didukung": "green", "sebagian": "yellow", "tidak_didukung": "red", "sumber_tidak_ada": "red", "belum_dicek": "dim"}


def _print_claim_report(text: str, model: str = None, numbered: list[dict] | None = None):
    from rich.table import Table
    from . import entail

    console.print("[cyan]CEK KLAIM[/cyan] [dim]Mencocokkan setiap kalimat bersitasi dengan isi paper...[/dim]")
    report = entail.check_answer(text, model=model, numbered=numbered)
    if not report["total"]:
        console.print("[dim]Tidak ada kalimat bersitasi untuk dicek.[/dim]")
        return report
    tbl = Table(title="Pemeriksaan klaim", border_style="cyan", show_lines=True)
    tbl.add_column("Status", width=16)
    tbl.add_column("Klaim")
    tbl.add_column("Alasan", style="dim")
    for c in report["claims"]:
        style = CLAIM_STYLES.get(c["verdict"], "white")
        tbl.add_row(f"[{style}]{entail.VERDICT_LABELS[c['verdict']]}[/{style}]", c["text"], c["reason"])
    console.print(tbl)
    flagged = entail.needs_attention(report)
    color = "red" if flagged else "green"
    console.print(f"[{color}]{flagged} dari {report['total']} klaim perlu dicek sebelum dikutip.[/{color}]")
    return report


@app.command("cek-klaim")
def check_claims(
    path: str = typer.Argument(..., help="Markdown or text file to check, e.g. a draft article"),
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
):
    """Check every cited sentence in a draft against the papers it cites."""
    from pathlib import Path

    f = Path(path)
    if not f.exists():
        console.print(f"[red]File tidak ditemukan:[/red] {f}")
        raise typer.Exit(1)
    from . import entail

    report = _print_claim_report(f.read_text(encoding="utf-8"), model)
    if entail.needs_attention(report):
        raise typer.Exit(2)  # non-zero so scripts can stop on unsupported claims


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
def ui(
    port: int = typer.Option(8501, "--port", "-p", help="Port to run web dashboard"),
    team: bool = typer.Option(
        False, "--team",
        help="Buka untuk anggota tim lewat jaringan (Tailscale). Wajib ada COSMOLAB_TEAM_PASSWORD di .env.",
    ),
    host: str = typer.Option(None, "--host", help="Alamat yang dibuka untuk --team (default: IP Tailscale)"),
):
    """Launch interactive local Web Dashboard (Streamlit)."""
    import subprocess
    import sys
    from pathlib import Path
    import os
    web_script = Path(__file__).parent / "web.py"
    env = os.environ.copy()
    # The dashboard runs in its own process, so hand it the active project.
    if config.PROJECT:
        env["COSMOLAB_PROJECT"] = config.PROJECT
    else:
        env.pop("COSMOLAB_PROJECT", None)

    args = [sys.executable, "-m", "streamlit", "run", str(web_script), "--server.port", str(port)]
    address = "localhost"
    if team:
        if len(config.TEAM_PASSWORD) < 10:
            console.print(
                "[red]Mode tim butuh password minimal 10 karakter.[/red] Isi COSMOLAB_TEAM_PASSWORD di .env, "
                "lalu jalankan lagi."
            )
            raise typer.Exit(1)
        address = host or _tailscale_ip()
        if not address:
            console.print(
                "[red]IP Tailscale tidak ditemukan.[/red] Pasang dan login Tailscale dulu (lihat PANDUAN_TIM.md), "
                "atau tentukan alamat sendiri dengan --host."
            )
            raise typer.Exit(1)
        env["COSMOLAB_TEAM_MODE"] = "1"
        args += ["--server.address", address, "--server.headless", "true"]
    else:
        env.pop("COSMOLAB_TEAM_MODE", None)
        args += ["--server.address", "localhost"]

    label = config.PROJECT or "data utama (tanpa proyek)"
    console.print(f"[bold cyan]Launching Cosmolab Web Dashboard on port {port}...[/bold cyan]")
    console.print(f"[dim]Proyek: {label}  |  URL: http://{address}:{port}[/dim]")
    if team:
        console.print("[dim]Mode tim aktif: anggota tim membuka alamat di atas dan memasukkan password tim.[/dim]")
    subprocess.run(args, env=env, cwd=str(config.PROJECT_ROOT))


def _tailscale_ip() -> str:
    """IPv4 address of this machine on the Tailscale network, or '' if unavailable."""
    import shutil
    import subprocess
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    ip = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else ""
    return ip if ip.startswith("100.") else ""


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



def _print_verification(report):
    from . import verify as _verify
    table = Table(title="Pemeriksaan Sitasi", box=ROUNDED, show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Rujukan", max_width=60)
    table.add_column("Status")
    table.add_column("Catatan", max_width=50)
    for i, r in enumerate(report.references, 1):
        color = "green" if r.status in (_verify.OK_CORPUS, _verify.OK_CROSSREF) else "yellow"
        table.add_row(str(i), r.raw[:200], f"[{color}]{_verify.LABELS[r.status]}[/{color}]", r.note)
    for c in report.citations:
        if c.status != _verify.CITE_OK:
            table.add_row("teks", c.text, f"[yellow]{_verify.LABELS[c.status]}[/yellow]", c.note)
    console.print(table)
    if report.ok:
        console.print("[bold green]LULUS: semua sitasi terverifikasi.[/bold green]")
    else:
        console.print(f"[bold yellow]PERLU DICEK: {len(report.blocking)} temuan.[/bold yellow]")


@app.command()
def verify(
    file: str = typer.Argument(..., help="File Markdown (artikel, sintesis, laporan) yang mau diperiksa"),
    offline: bool = typer.Option(False, "--offline", help="Hanya cek ke koleksi proyek, tanpa Crossref"),
):
    """Periksa daftar rujukan dan kutipan di teks sebelum dikirim ke klien."""
    from . import verify as _verify
    from . import deliverables as _deliv
    try:
        path = _deliv.resolve_source(file)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    report = _verify.verify_file(path, online=not offline)
    _print_verification(report)
    console.print(f"[dim]Laporan internal: {_verify.save_report(report)}[/dim]")
    if not report.ok:
        raise typer.Exit(2)


@app.command()
def deliver(
    file: str = typer.Argument(..., help="File Markdown hasil kerja yang mau dikirim ke klien"),
    reviewer: str = typer.Option(..., "--reviewer", "-r", help="Nama peneliti yang memeriksa dokumen"),
    fmt: str = typer.Option("both", "--format", "-f", help="docx, pdf, atau both"),
    title: str = typer.Option(None, "--title", "-t", help="Judul dokumen (default: judul H1 di file)"),
    offline: bool = typer.Option(False, "--offline", help="Hanya cek sitasi ke koleksi proyek, tanpa Crossref"),
    manual_checked: bool = typer.Option(
        False, "--sudah-cek-manual",
        help="Saya sudah memeriksa manual sitasi yang tidak bisa diverifikasi otomatis",
    ),
):
    """Buat dokumen Word/PDF berkop firma untuk klien, setelah sitasi diperiksa."""
    from . import deliverables as _deliv
    formats = {"both": ("docx", "pdf"), "docx": ("docx",), "pdf": ("pdf",)}.get(fmt.lower())
    if not formats:
        console.print("[red]--format harus docx, pdf, atau both[/red]")
        raise typer.Exit(1)
    try:
        path = _deliv.resolve_source(file)
        result = _deliv.deliver(path, reviewer=reviewer, formats=formats, title=title,
                                online=not offline, allow_unverified=manual_checked)
    except _deliv.DeliveryBlocked as e:
        _print_verification(e.report)
        console.print(
            "[red]Dokumen belum dibuat.[/red] Perbaiki sitasi yang ditandai, atau periksa manual lalu "
            "jalankan ulang dengan [bold]--sudah-cek-manual[/bold]."
        )
        raise typer.Exit(2)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    _print_verification(result["report"])
    for f in result["files"]:
        console.print(f"[green]Dibuat:[/green] {f}")
    console.print(f"[dim]Laporan sitasi internal (jangan dikirim ke klien): {result['qa_report']}[/dim]")



@app.command()
def authors(
    no_ai: bool = typer.Option(False, "--no-ai", help="Jangan pakai AI untuk membaca halaman pertama PDF."),
    refresh: bool = typer.Option(False, "--refresh", help="Cari ulang juga paper yang sudah punya penulis (kecuali isian manual)."),
):
    """Lengkapi nama penulis paper lewat DOI, arXiv, OpenAlex, Crossref, lalu PDF."""
    from . import authors as _authors
    from . import db

    def _show(file_name, names, src):
        if names:
            console.print(f"[green]OK[/green]  {file_name[:60]}  [dim]({src})[/dim]  {_authors.display(names)}")
        else:
            console.print(f"[yellow]--[/yellow]  {file_name[:60]}  [dim]tidak ditemukan[/dim]")

    stats = _authors.fill_missing(use_ai=not no_ai, refresh=refresh, progress=_show)
    db.sync_all()
    console.print()
    console.print(
        f"Dicek {stats['checked']} paper: {stats['found']} ketemu, {stats['not_found']} tidak ketemu. "
        f"Sumber: {stats['sources'] or '-'}"
    )


@app.command("dois")
def fill_dois(
    refresh: bool = typer.Option(False, "--refresh", help="Cari ulang juga paper yang sudah punya DOI (kecuali isian manual)."),
    file: str = typer.Option(None, "--file", help="Nama file paper, dipakai bersama --set."),
    set_doi: str = typer.Option(None, "--set", help="Pasang DOI yang sudah dicek manual untuk --file."),
):
    """Lengkapi DOI paper lewat arXiv dan Crossref. DOI yang sudah ada tidak ditimpa."""
    from . import dois as _dois
    from . import db

    if set_doi or file:
        if not (set_doi and file):
            console.print("[red]Pakai --file dan --set bersamaan.[/red]")
            raise typer.Exit(1)
        if not _dois.clean_doi(set_doi):
            console.print(f"[red]DOI tidak valid:[/red] {set_doi}")
            raise typer.Exit(1)
        db.set_doi(file, set_doi)
        console.print(f"[green]OK[/green]  {file}  {_dois.clean_doi(set_doi)}  [dim](manual)[/dim]")
        return

    def _show(file_name, found, src, candidates):
        if found:
            console.print(f"[green]OK[/green]  {file_name[:60]}  [dim]({src})[/dim]  {found}")
        elif candidates:
            console.print(f"[yellow]??[/yellow]  {file_name[:60]}  [dim]perlu dicek manual[/dim]")
        else:
            console.print(f"[yellow]--[/yellow]  {file_name[:60]}  [dim]tidak ditemukan[/dim]")

    stats = _dois.fill_missing(refresh=refresh, progress=_show)
    db.sync_all()
    console.print()
    console.print(
        f"Dicek {stats['checked']} paper: {stats['found']} ketemu, {stats['not_found']} tidak ketemu. "
        f"Sumber: {stats['sources'] or '-'}"
    )
    if stats["candidates"]:
        console.print()
        console.print("[bold]Kandidat yang perlu dicek manual[/bold] (judul mirip, tapi tahun beda atau kemiripan < 95%):")
        for file_name, cands in stats["candidates"].items():
            console.print(f"  {file_name}")
            for c in cands:
                console.print(f"    {c['doi']}  [dim]{c['similarity']:.0%} · {c['year'] or '?'} · {c['journal'][:40]}[/dim]")
                console.print(f"    [dim]{c['title'][:90]}[/dim]")
        console.print()
        console.print('Pasang setelah dicek: cosmolab dois --file "<nama file>" --set <doi>')


@app.command()
def snowball(
    arah: str = typer.Option("both", "--arah", help="backward (rujukan paper koleksi), forward (paper yang mengutip), atau both"),
    file: list[str] = typer.Option(None, "--file", help="Paper koleksi yang ditelusuri (boleh diulang). Kosong = semua."),
    top: int = typer.Option(20, "--top", help="Jumlah kandidat teratas yang ditampilkan"),
    unduh: int = typer.Option(0, "--unduh", help="Unduh N kandidat teratas yang punya versi terbuka"),
):
    """Telusuri sitasi (snowballing): cari paper penting yang dirujuk atau mengutip koleksi."""
    from . import snowball as _snowball

    directions = {"both": (_snowball.BACKWARD, _snowball.FORWARD), "backward": (_snowball.BACKWARD,),
                  "forward": (_snowball.FORWARD,)}.get(arah)
    if not directions:
        console.print("[red]--arah harus backward, forward, atau both.[/red]")
        raise typer.Exit(1)
    corpus = _db.get_all_papers_with_analyses()
    seeds = [p for p in corpus if not file or p["file"] in file or Path(p["file"]).stem in file]
    if not seeds:
        console.print("[red]Tidak ada paper koleksi yang cocok.[/red]")
        raise typer.Exit(1)

    def _show(i, n, seed, direction, count, src):
        console.print(f"[dim]{i}/{n}[/dim]  {_snowball.DIRECTION_LABELS[direction]:16} {count:4} paper  "
                      f"[dim]({src})[/dim]  {(seed.get('title') or '')[:55]}")

    res = _snowball.snowball(seeds, corpus, directions=directions, progress=_show)
    cands = res["candidates"]
    console.print()
    console.print(f"{len(cands)} kandidat baru dari {res['checked']} paper koleksi. Sumber: {res['sources']}")
    table = Table(box=ROUNDED, show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Judul", max_width=58)
    table.add_column("Tahun")
    table.add_column("Terhubung", justify="right")
    table.add_column("Sitasi", justify="right")
    table.add_column("Arah")
    table.add_column("PDF terbuka")
    for i, c in enumerate(cands[:top], 1):
        table.add_row(str(i), c["title"][:120], c["year"], str(c["link_count"]), str(c["citations"]),
                      ", ".join(_snowball.DIRECTION_LABELS[d] for d in c["directions"]),
                      "ya" if c["pdf_url"] else ("lewat DOI" if c["doi"] else "-"))
    console.print(table)

    if unduh:
        picked = [c for c in cands if c["pdf_url"] or c["doi"]][:unduh]
        for c in picked:
            r = _snowball.import_candidate(c)
            if r.get("ok"):
                console.print(f"[green]OK[/green]  {r['title'][:70]}")
            else:
                console.print(f"[yellow]--[/yellow]  {c['title'][:70]}  [dim]{r.get('error', '')}[/dim]")
        _db.sync_all()
        console.print("Jalankan 'cosmolab analyze' untuk menganalisis paper baru.")


@app.command()
def usage(
    all_projects: bool = typer.Option(False, "--all", "-a", help="Ringkasan semua proyek, bukan hanya proyek aktif"),
    month: str = typer.Option(None, "--month", "-m", help="Bulan, format YYYY-MM (default: semua waktu)"),
    by: str = typer.Option("feature", "--by", help="Kelompokkan per: feature, model, atau month"),
):
    """Tampilkan pemakaian token AI dan perkiraan biaya per proyek."""
    from . import usage as _usage
    if not _usage.pricing():
        console.print("[yellow]Harga model belum diisi (COSMOLAB_PRICING di .env). Biaya tidak dihitung.[/yellow]")

    def _table(title, groups, key_label):
        table = Table(title=title, box=ROUNDED)
        table.add_column(key_label, style="cyan")
        table.add_column("Panggilan", justify="right")
        table.add_column("Token input", justify="right")
        table.add_column("Token output", justify="right")
        table.add_column("Perkiraan biaya", justify="right", style="green")
        for g in groups:
            biaya = _usage.format_money(g["cost"]) + (" *" if g["unpriced"] else "")
            table.add_row(str(g["key"]), str(g["calls"]), f"{g['prompt_tokens']:,}", f"{g['completion_tokens']:,}", biaya)
        console.print(table)

    period = f" ({month})" if month else ""
    if all_projects:
        rows = []
        for label, root in _usage.all_roots():
            for r in _usage.load(root, month):
                r["project"] = label
                rows.append(r)
        if not rows:
            console.print("[yellow]Belum ada pemakaian AI yang tercatat.[/yellow]")
            return
        _table(f"Pemakaian AI semua proyek{period}", _usage.summarize(rows, by="project"), "Proyek")
    else:
        rows = _usage.load(config.ROOT, month)
        label = config.PROJECT or "data utama"
        if not rows:
            console.print(f"[yellow]Belum ada pemakaian AI yang tercatat untuk {label}.[/yellow]")
            return
        key_label = {"feature": "Fitur", "model": "Model", "month": "Bulan"}.get(by, by)
        _table(f"Pemakaian AI: {label}{period}", _usage.summarize(rows, by=by), key_label)
    console.print("[dim]* sebagian panggilan memakai model yang belum punya harga di COSMOLAB_PRICING.[/dim]")


@app.command("cek-analisis")
def check_analysis(
    paper: str = typer.Argument(None, help="Paper file name (or part of its title). Leave empty with --semua"),
    all_papers: bool = typer.Option(False, "--semua", help="Check every analysed paper that has not been checked"),
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
):
    """Check a paper's AI analysis (thesis, premises, findings, quotes) against the PDF text."""
    from rich.table import Table
    from . import analysis_check, db, entail

    papers = [p for p in db.get_all_papers_with_analyses() if p.get("thesis")]
    if all_papers:
        targets = [p for p in papers if not analysis_check.load_check(p["file"])]
    elif paper:
        q = paper.lower()
        targets = [p for p in papers if q in p["file"].lower() or q in (p.get("title") or "").lower()][:1]
    else:
        console.print("[red]Sebutkan paper atau pakai --semua.[/red]")
        raise typer.Exit(1)
    if not targets:
        console.print("[yellow]Tidak ada paper yang cocok atau semua sudah dicek.[/yellow]")
        return

    styles = {entail.SUPPORTED: "green", entail.PARTIAL: "yellow", entail.UNSUPPORTED: "red"}
    for p in targets:
        console.print(f"[cyan]CEK[/cyan] {p.get('title') or p['file']}")
        try:
            r = analysis_check.check_paper(p["file"], model=model)
        except Exception as e:
            console.print(f"[red]Gagal:[/red] {e}")
            continue
        if len(targets) == 1:
            t = Table(show_lines=True)
            t.add_column("Bagian", width=14)
            t.add_column("Pernyataan")
            t.add_column("Hasil", width=16)
            t.add_column("Alasan")
            for s in r["statements"]:
                label = s["label"] + (f" {s['index'] + 1}" if s["index"] is not None else "")
                st_ = styles.get(s["verdict"], "white")
                t.add_row(label, s["text"], f"[{st_}]{entail.VERDICT_LABELS[s['verdict']]}[/{st_}]", s["reason"])
            console.print(t)
            for q in r["quotes"]:
                console.print(f"  Kutipan: {analysis_check.QUOTE_LABELS[q['status']]}"
                              + (f", halaman PDF {q['page']}" if q.get("page") else "") + f" - {q['text'][:90]}")
        sc = analysis_check.score(r)
        console.print(f"  {sc['supported']}/{sc['statements']} pernyataan didukung, "
                      f"{sc['quotes_found']}/{sc['quotes']} kutipan ada di PDF.")


@app.command("cek-metadata")
def check_metadata():
    """Check title, year and authors of every paper against Crossref/DataCite, and flag retractions."""
    from rich.table import Table
    from . import metadata

    store = metadata.check_all(progress_cb=lambda d, n, t: console.print(f"[dim]{d}/{n} {t[:70]}[/dim]"))
    t = Table(show_lines=False)
    t.add_column("Paper")
    t.add_column("Status")
    t.add_column("Catatan")
    for r in sorted(store.values(), key=lambda r: (r["status"] == metadata.OK, r.get("title") or "")):
        if r["status"] == metadata.OK and not r.get("notices"):
            continue
        note = "; ".join([f"{d['field']}: {d['ours']} vs {d['crossref']}" for d in r.get("diffs", [])]
                         + [n["label"] for n in r.get("notices", [])])
        t.add_row((r.get("title") or "")[:70], metadata.STATUS_LABELS[r["status"]], note)
    console.print(t)
    ok = sum(1 for r in store.values() if r["status"] == metadata.OK)
    console.print(f"{ok} dari {len(store)} paper cocok.")
    bad = metadata.flagged(store)
    if bad:
        console.print(f"[bold red]{len(bad)} paper ditarik atau bermasalah:[/bold red] "
                      + "; ".join(r.get("title") or r["file"] for r in bad))


@app.command("pustaka")
def bibliography(
    format: str = typer.Option("bib", "--format", "-f", help="'bib' (BibTeX) or 'ris'"),
    out: str = typer.Option(None, "--out", "-o", help="Output file"),
):
    """Export the reference list, built from verified metadata where available."""
    from pathlib import Path
    from . import db, metadata

    papers = db.get_all_papers_with_analyses()
    fmt = format.lower().strip()
    text = metadata.to_ris(papers) if fmt == "ris" else metadata.to_bibtex(papers)
    path = Path(out) if out else config.ROOT / ("references.ris" if fmt == "ris" else "references.bib")
    path.write_text(text, encoding="utf-8")
    console.print(f"[green]OK[/green] {len(papers)} entri ditulis ke {path}")


@app.command("uji")
def evaluation(
    action: str = typer.Argument("jalan", help="'buat' to draft test items, 'jalan' to run them, 'riwayat' for past runs"),
    n: int = typer.Option(10, "--n", help="Number of new papers to draft items from (buat)"),
    k: int = typer.Option(3, "--k", help="How many top passages count as a hit (jalan)"),
    reviewed: bool = typer.Option(False, "--diperiksa", help="Use only items a researcher has reviewed"),
    rerank: bool = typer.Option(True, "--rerank/--no-rerank", help="Let the LLM reorder passages"),
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
):
    """Measure retrieval and claim-check accuracy on the evaluation set."""
    from . import evaluate

    pct = lambda x: "-" if x is None else f"{x * 100:.0f}%"
    if action == "buat":
        new = evaluate.draft_gold(n_papers=n, model=model,
                                  progress_cb=lambda d, t, title: console.print(f"[dim]{d}/{t} {title[:70]}[/dim]"))
        console.print(f"[green]{len(new)} soal baru[/green] di {evaluate.gold_path()}. "
                      "Periksa dan set \"reviewed\": true pada soal yang benar.")
        return
    if action == "riwayat":
        for h in evaluate.history():
            console.print(f"{h['time']}  k={h['k']}  halaman benar {pct(h['recall_at_k'])}  "
                          f"akurasi klaim {pct(h['claim_accuracy'])}  embedding {h.get('embed_model') or '-'}")
        return
    r = evaluate.run(k=k, rerank=rerank, reviewed_only=reviewed, model=model)
    console.print(f"Pencarian: {r['retrieval']['n']} soal, halaman benar di {k} teratas {pct(r['retrieval']['recall_at_k'])}, "
                  f"MRR {'-' if r['retrieval']['mrr'] is None else round(r['retrieval']['mrr'], 2)}")
    c = r["claims"]
    console.print(f"Cek klaim: {c['n']} soal, akurasi {pct(c['accuracy'])}, klaim salah tertangkap {pct(c['false_caught'])}, "
                  f"klaim benar lolos {pct(c['true_passed'])}")


@app.command("log")
def audit_log(
    limit: int = typer.Option(30, "--n", help="Entries to show"),
    csv_out: str = typer.Option(None, "--csv", help="Write the whole log to this CSV file"),
):
    """Show the audit log of AI steps, or export it for a methods section."""
    from pathlib import Path
    from . import audit

    rows = audit.read()
    if csv_out:
        Path(csv_out).write_text(audit.to_csv(rows), encoding="utf-8")
        console.print(f"[green]OK[/green] {len(rows)} entri ditulis ke {csv_out}")
    for r in rows[:limit]:
        what = r.get("question") or r.get("file") or ""
        console.print(f"{r['time']}  {audit.EVENT_LABELS.get(r['event'], r['event']):<22} {r.get('model') or '':<18} {what[:70]}")
    console.print()
    console.print(audit.methods_text(rows))


@app.command("review")
def review_draft(
    path: str = typer.Argument(..., help="Draf mahasiswa: .docx, .md, atau .txt"),
    jenjang: str = typer.Option("s2", "--jenjang", "-j", help="s1 (skripsi), s2 (tesis), atau s3 (disertasi)"),
    offline: bool = typer.Option(False, "--offline", help="Jangan cek daftar pustaka ke Crossref"),
    model: str = typer.Option(config.LLM_MODEL, "--model", "-m", help="LLM model name"),
    tanpa_komentar: bool = typer.Option(False, "--tanpa-komentar", help="Lewati komentar AI (tanpa biaya AI): sitasi dan kemiripan saja"),
    tanpa_kemiripan: bool = typer.Option(False, "--tanpa-kemiripan", help="Lewati cek kemiripan"),
):
    """Review draf mahasiswa: komentar ala pembimbing, cek sitasi, dan cek kemiripan. Draf tidak ditulis ulang.

    Komentar AI harus diputuskan konsultan (terima, edit, buang) di dashboard sebelum Word dibuat.
    """
    from . import review as _review

    if jenjang not in _review.LEVELS:
        console.print("[red]--jenjang harus s1, s2, atau s3.[/red]")
        raise typer.Exit(1)
    plog = _review.ProgressLog()
    try:
        est = _review.estimate(_review.read_draft(Path(path)), online=not offline, feedback=not tanpa_komentar,
                               similarity=not tanpa_kemiripan)
        console.print(_review.estimate_text(est), highlight=False)
        with Progress(console=console) as progress:
            task = progress.add_task("[cyan]Mereview draf...", total=1.0)

            def on_progress(kind, msg, data=None):
                plog.handle(kind, msg, data)
                if kind == "stage_done":
                    progress.console.print(f"  [green]selesai[/green] {msg} ({_review.fmt_duration(plog.finished[-1][1])})")
                now = f" · {plog.now}" if plog.now != plog.label else ""
                progress.update(task, completed=plog.fraction, description=f"[cyan]{plog.label}{now}")

            report = _review.review_file(Path(path), level=jenjang, online=not offline, model=model,
                                         feedback=not tanpa_komentar, similarity=not tanpa_kemiripan,
                                         progress_cb=on_progress)
            progress.update(task, completed=1.0,
                            description=f"[green]Review selesai dalam {_review.fmt_duration(plog.elapsed)}")
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Gagal saat {plog.label}: {e}[/red]")
        raise typer.Exit(1)
    paths = _review.save(report)
    s = report["summary"]
    sev = s["by_severity"]
    console.print(f"{s['paragraphs']} paragraf, {s['comments']} komentar AI, {s['ungrounded']} kutipannya tidak cocok "
                  f"({sev[_review.PENTING]} penting, {sev[_review.SARAN]} saran, {sev[_review.CATATAN]} catatan). "
                  f"Sitasi: {s['references_flagged']} entri pustaka perlu dicek, "
                  f"{s['citations_missing']} sitasi tidak ada di daftar pustaka.")
    if report.get("similarity"):
        sim = report["similarity"]
        console.print(f"Kemiripan (perkiraan, bukan Turnitin): {sim['score']}%, {len(sim['findings'])} kalimat ditandai, "
                      f"dibandingkan dengan {sim['sources']['korpus']} paper koleksi dan "
                      f"{sim['sources']['dikutip']} abstrak sumber yang dikutip.")
    for i, p in enumerate(report["priorities"], 1):
        console.print(f"  {i}. {p}")
    console.print(f"[green]OK[/green] {paths['md']} (versi internal)")
    console.print("Putuskan setiap komentar di dashboard (Review draf mahasiswa > Review tersimpan), lalu buat Word.")


@app.command("backup")
def backup(
    out: str = typer.Option(None, "--out", "-o", help="Folder tujuan. Default: backups/ di folder CosmoLab."),
    tanpa_pdf: bool = typer.Option(False, "--tanpa-pdf", help="Jangan ikutkan PDF (zip jauh lebih kecil)."),
    dengan_cache: bool = typer.Option(False, "--dengan-cache", help="Ikutkan cache AI (biasanya tidak perlu)."),
):
    """Cadangkan data proyek aktif (atau data/) ke satu file zip."""
    from . import backup as _backup

    try:
        res = _backup.make_backup(Path(out) if out else None, include_pdf=not tanpa_pdf, include_cache=dengan_cache)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]OK[/green] {res['files']} file, {res['size'] / 1_048_576:.1f} MB: {res['path']}")


@sinta_app.command("import")
def sinta_import(path: str = typer.Argument(..., help="File CSV berkolom ISSN dan peringkat")):
    """Impor daftar jurnal SINTA dari CSV."""
    from . import sinta as _sinta

    try:
        res = _sinta.import_csv(path)
    except (ValueError, OSError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]OK[/green] {res['added']} jurnal baru, {res['updated']} diperbarui.")
    if res["skipped"]:
        console.print(f"[yellow]Baris dilewati (ISSN/peringkat tidak valid): {', '.join(map(str, res['skipped']))}[/yellow]")
    console.print(f"Tersimpan di {_sinta.list_path()}")


@sinta_app.command("add")
def sinta_add(
    issn: str = typer.Option(..., "--issn", help="ISSN cetak dan/atau online, pisahkan dengan koma"),
    peringkat: str = typer.Option(..., "--peringkat", "-r", help="1 sampai 6"),
    nama: str = typer.Option("", "--nama", help="Nama jurnal"),
):
    """Tambah atau perbarui satu jurnal."""
    from . import sinta as _sinta

    try:
        res = _sinta.add(nama, issn, peringkat)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    word = "ditambahkan" if res["status"] == "added" else "diperbarui"
    console.print(f"[green]OK[/green] SINTA {res['rank']} {word}: {', '.join(res['issns'])}")


@sinta_app.command("list")
def sinta_list():
    """Tampilkan daftar jurnal SINTA yang tersimpan."""
    from . import sinta as _sinta

    entries = _sinta.load()
    if not entries:
        console.print("Daftar masih kosong. Isi dengan: cosmolab sinta import <file.csv>")
        return
    table = Table(title=f"{len(entries)} jurnal SINTA")
    for col in ("Peringkat", "Nama", "ISSN", "Dicek"):
        table.add_column(col)
    for e in entries:
        table.add_row(f"SINTA {e['rank']}", e.get("name", ""), ", ".join(e["issns"]), e.get("checked", ""))
    console.print(table)


@sinta_app.command("cek")
def sinta_cek(limit: int = typer.Option(None, "--limit", help="Batasi jumlah paper yang dicari")):
    """Cari jurnal & ISSN paper proyek aktif lewat DOI (OpenAlex), lalu hitung yang berlabel SINTA."""
    from . import sinta as _sinta

    res = _sinta.fill_journals(limit=limit)
    ranked = _sinta.ranks_by_file()
    console.print(f"ISSN dicari untuk {res['checked']} paper, ketemu {res['found']}.")
    console.print(f"{len(ranked)} paper ada di daftar SINTA.")


if __name__ == "__main__":
    app()
