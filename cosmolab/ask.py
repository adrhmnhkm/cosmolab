import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from . import config
from . import db
from . import retrieval

console = Console(force_terminal=True, legacy_windows=False)

SYSTEM_PROMPT = """You are CosmoLab, a rigorous multidisciplinary research assistant. You work across fields (humanities, philosophy, religion, law, economics, education, psychology, science, technology, health) and adapt your terminology and methods to the field of the question.

Answer the user's question accurately using ONLY the provided corpus context.
Guidelines:
1. Cite papers inline by title and year, e.g. `[Title (Year)]`. If exact page numbers are available in the context (e.g. Hal. X), cite the page as well: `[Title (Year), Hal. X]`.
2. Present claims, evidence, methods, objections, and technical concepts precisely, using the standard terms of the relevant field.
3. If multiple papers take conflicting positions, contrast their arguments.
4. When citing verbatim evidence, preserve the exact wording and indicate the page number.
5. If the context does not contain enough evidence, explicitly state what is missing.
6. Answer in the same language as the question (use formal Indonesian if asked in Indonesian, English if asked in English).
"""


def ask(question: str, model: str = None, top_k: int = 5) -> str:
    """Query the research corpus using advanced hybrid retrieval (FTS5 + Conceptual RRF), LLM re-ranking, and page-aware passage grounding."""
    config.ensure_dirs()
    model = model or config.NINEROUTER_MODEL

    # Retrieve candidate papers via Hybrid Search (FTS5 + Semantic Concept RRF)
    console.print("[cyan]RETRIEVING CORPUS[/cyan] [dim](Hybrid FTS5 + Semantic RRF)...[/dim]")
    candidates = retrieval.hybrid_search(question, limit=top_k * 3, expand_concepts=True, model=model)

    # Re-rank candidates using LLM micro cross-attention
    if candidates:
        console.print(f"[cyan]RE-RANKING[/cyan] [dim]Evaluating {len(candidates)} candidates for dialectical precision...[/dim]")
        results = retrieval.rerank_papers(question, candidates, top_k=top_k, model=model)
    else:
        results = []

    if not results:
        # If no match, fallback to loading top available analyzed papers
        all_papers = db.get_all_papers_with_analyses()
        results = [p for p in all_papers if p.get("thesis")][:top_k]

    if not results:
        console.print("[red]FAIL  No papers found in database. Run `cosmolab harvest` and `cosmolab analyze` first.[/red]")
        return "No papers available in the corpus."

    # Build context from retrieved papers, including grounded verbatim passages
    context_blocks = []
    grounded_citations = []
    found = retrieval.grounded_passages_batch([r.get("file") for r in results], question, top_k=2, model=model)
    for i, r in enumerate(results, start=1):
        block = f"### Paper {i}: {r.get('title')} ({r.get('year', 'n.d.')})\n"
        block += f"- File: {r.get('file')}\n"
        if r.get("doi"):
            block += f"- DOI: {r.get('doi')}\n"
        if r.get("argument_type"):
            block += f"- Argument Type: {r.get('argument_type')}\n"
        if r.get("supports_or_critiques"):
            block += f"- Stance: {r.get('supports_or_critiques')}\n"
        if r.get("thesis"):
            block += f"- Thesis: {r.get('thesis')}\n"
        if r.get("premises_json"):
            try:
                premises = json.loads(r["premises_json"])
                block += f"- Premises: {'; '.join(premises)}\n"
            except Exception:
                pass
        if r.get("key_objection"):
            block += f"- Key Objection: {r.get('key_objection')}\n"
        if r.get("key_defense"):
            block += f"- Key Defense: {r.get('key_defense')}\n"
        if r.get("snippet"):
            block += f"- Excerpt: {r.get('snippet')}\n"

        # P1: Page-aware passage grounding
        if r.get("file"):
            try:
                passages = found.get(r["file"]) or []
                if passages:
                    block += "- Bukti Verbatim Teks (Grounding):\n"
                    for psg in passages:
                        block += f"  * [{psg['page_label']}]: \"{psg['verbatim']}\"\n"
                        grounded_citations.append({
                            "title": r.get("title") or r["file"],
                            "year": r.get("year", "n.d."),
                            "page_label": psg["page_label"],
                            "verbatim": psg["verbatim"]
                        })
            except Exception:
                pass

        context_blocks.append(block)

    full_context = "\n\n".join(context_blocks)
    user_prompt = f"Corpus Context:\n{full_context}\n\nUser Question:\n{question}"

    client = OpenAI(
        api_key=config.NINEROUTER_API_KEY,
        base_url=config.NINEROUTER_BASE_URL,
    )

    console.print(f"[cyan]QUERYING CORPUS[/cyan] [dim]({len(results)} relevant papers referenced)...[/dim]")

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        console.print(f"[red]LLM API Error:[/red] {e}")
        console.print("[yellow]Tip: Check your API key, gateway status, or specify another model with --model.[/yellow]")
        return f"Error querying LLM: {e}"

    try:
        from . import audit

        audit.log("tanya", mode="klasik", question=question, model=model,
                  prompt_version=audit.prompt_version(SYSTEM_PROMPT),
                  papers=[r.get("file") for r in results],
                  passages=[f"{g['title'][:60]} | {g['page_label']}" for g in grounded_citations])
    except Exception:
        pass

    # Pretty display
    console.print(Panel(Markdown(answer), title=f"[bold green]Corpus Answer[/bold green] - [dim]{model}[/dim]", border_style="green"))

    if grounded_citations:
        from rich.table import Table
        tbl = Table(title="📑 Bukti Verbatim & Nomor Halaman PDF Terverifikasi", border_style="cyan", show_lines=True)
        tbl.add_column("Paper & Tahun", style="bold white", width=32)
        tbl.add_column("Halaman", style="yellow", justify="center", width=12)
        tbl.add_column("Kutipan Verbatim Asli", style="italic green")
        for gc in grounded_citations[:6]:
            tbl.add_row(f"{gc['title']} ({gc['year']})", gc["page_label"], f'"{gc["verbatim"]}"')
        console.print(tbl)

    return answer
