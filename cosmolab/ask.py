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

console = Console(force_terminal=True, legacy_windows=False)

SYSTEM_PROMPT = """You are a rigorous philosophical research assistant specializing in cosmological arguments (Kalam, Contingency, First Cause, Fine-Tuning) and philosophy of science/religion.

Answer the user's question accurately using ONLY the provided corpus context.
Guidelines:
1. Cite papers inline by title and year, e.g. `[Title (Year)]`.
2. Present premises, objections, defenses, and technical concepts precisely.
3. If multiple papers take conflicting positions, contrast their arguments.
4. If the context does not contain enough evidence, explicitly state what is missing.
5. Answer in the same language as the question (use formal Indonesian if asked in Indonesian, English if asked in English).
"""


def ask(question: str, model: str = None, top_k: int = 5) -> str:
    """Query the research corpus using full-text retrieval and LLM synthesis (RAG)."""
    config.ensure_dirs()
    model = model or config.NINEROUTER_MODEL

    # Retrieve relevant papers via FTS5
    results = db.search(question, limit=top_k)

    if not results:
        # If no strict match, fallback to loading top available analyzed papers
        all_papers = db.get_all_papers_with_analyses()
        results = [p for p in all_papers if p.get("thesis")][:top_k]

    if not results:
        console.print("[red]FAIL  No papers found in database. Run `cosmolab harvest` and `cosmolab analyze` first.[/red]")
        return "No papers available in the corpus."

    # Build context from retrieved papers
    context_blocks = []
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

    # Pretty display
    console.print(Panel(Markdown(answer), title=f"[bold green]Corpus Answer[/bold green] - [dim]{model}[/dim]", border_style="green"))
    return answer
