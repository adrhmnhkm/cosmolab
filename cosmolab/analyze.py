import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from pydantic import BaseModel, ValidationError
from openai import OpenAI
from rich.console import Console
from . import config
from .storage import read_meta, write_json

console = Console(force_terminal=True, legacy_windows=False)


class Quote(BaseModel):
    text: str
    page_hint: str | None = None


class PaperAnalysis(BaseModel):
    thesis: str | None = None
    argument_type: str | None = None
    premises: list[str] = []
    conclusion: str | None = None
    supports_or_critiques: str | None = None
    key_objection: str | None = None
    key_defense: str | None = None
    notable_concepts: list[str] = []
    quotes: list[Quote] = []


PROMPT = """You are analyzing a philosophy paper on the cosmological argument.
Return STRICT JSON matching this schema:
{
  "thesis": str|null,
  "argument_type": "kalam"|"contingency"|"fine-tuning"|"first-cause"|"other"|null,
  "premises": [str],
  "conclusion": str|null,
  "supports_or_critiques": "supports"|"critiques"|"neutral"|"mixed"|null,
  "key_objection": str|null,
  "key_defense": str|null,
  "notable_concepts": [str],
  "quotes": [{"text": str, "page_hint": str|null}]
}
Only use content present in the paper. If unclear, use null.
"""


def _strip_references(text: str) -> str:
    """Remove bibliography/references section if found in the latter half of the text."""
    if len(text) < 100:
        return text
    start_pos = int(len(text) * 0.5)
    ref_match = re.search(
        r'\n\s*(?:[0-9]+\.?\s*)?(?:References|Bibliography|Works Cited|Literature Cited|Referenzen|Referencias|Bibliografía)\b',
        text[start_pos:],
        re.IGNORECASE
    )
    if ref_match:
        return text[:start_pos + ref_match.start()]
    return text


def _trim(text: str, limit: int = 60000) -> str:
    """Clean and intelligently trim text to fit within model context without discarding the core arguments."""
    text = _strip_references(text).strip()
    if len(text) <= limit:
        return text

    # If text is still larger than limit (e.g., long dissertation/book):
    # Allocate: 30% intro/setup, 45% core argument (middle), 25% conclusion
    head_size = int(limit * 0.30)
    core_size = int(limit * 0.45)
    tail_size = limit - head_size - core_size

    mid_start = (len(text) // 2) - (core_size // 2)
    mid_end = mid_start + core_size

    head = text[:head_size].rstrip()
    middle = text[mid_start:mid_end].strip()
    tail = text[-tail_size:].lstrip()

    return f"{head}\n\n[... sections omitted for length ...]\n\n{middle}\n\n[... sections omitted for length ...]\n\n{tail}"


def _parse_response(content: str) -> dict:
    """Parse LLM response, handle empty/invalid JSON."""
    if not content or not content.strip():
        raise ValueError("Empty response")
    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Try extract JSON from markdown/code block
    import re
    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    # Try extract any JSON-like content between { and }
    brace_match = re.search(r'\{.*\}', content, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError("No valid JSON found in response")

def _analyze_one(client: OpenAI, text: str, model: str, timeout: int = 60) -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": _trim(text)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=timeout,
    )
    raw = _parse_response(resp.choices[0].message.content)
    return PaperAnalysis(**raw).model_dump()


def analyze_all(model: str = None, concurrency: int = 4, progress_cb=None) -> dict:
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    client = OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
    )
    stats = {"ok": 0, "skip": 0, "fail": 0}
    lock = threading.Lock()
    tasks_to_run = []

    for rec in read_meta():
        stem = Path(rec["file"]).stem
        txt = config.TEXT_DIR / (stem + ".txt")
        out = config.ANALYSIS_DIR / (stem + ".json")
        if out.exists():
            stats["skip"] += 1
            console.print(f"[dim]SKIP  Already analyzed: {stem}[/dim]")
            if progress_cb:
                progress_cb()
            continue
        if not txt.exists():
            stats["fail"] += 1
            console.print(f"[red]FAIL  No text file: {stem}[/red]")
            if progress_cb:
                progress_cb()
            continue
        tasks_to_run.append((rec, stem, txt, out))

    if not tasks_to_run:
        return stats

    console.print(f"[cyan]RUNNING ANALYSIS[/cyan] [dim]({len(tasks_to_run)} papers in parallel, concurrency={concurrency})...[/dim]")

    def _worker(item):
        rec, stem, txt, out = item
        try:
            console.print(f"[cyan]ANALYZE  {stem}[/cyan]")
            result = _analyze_one(client, txt.read_text(encoding="utf-8"), model)
            result["_meta"] = {
                "paper_file": rec["file"],
                "doi": rec.get("doi"),
                "title": rec.get("title"),
                "year": rec.get("year"),
                "model": model,
                "prompt_version": "v1",
            }
            write_json(out, result)
            console.print(f"[green]OK  Analyzed: {stem}[/green]")
            with lock:
                stats["ok"] += 1
        except (ValidationError, ValueError) as e:
            error_log = config.ANALYSIS_DIR / f"{stem}.error.txt"
            error_log.write_text(f"Error: {e}\nStem: {stem}\n", encoding="utf-8")
            console.print(f"[red]PARSE_ERROR  {stem} - {str(e)[:60]}[/red]")
            with lock:
                stats["fail"] += 1
        except Exception as e:
            error_log = config.ANALYSIS_DIR / f"{stem}.error.txt"
            error_log.write_text(f"API Error: {e}\nStem: {stem}\n", encoding="utf-8")
            console.print(f"[red]API_ERROR  {stem} - {str(e)[:60]}[/red]")
            with lock:
                stats["fail"] += 1
        finally:
            if progress_cb:
                progress_cb()

    max_workers = max(1, min(concurrency, len(tasks_to_run)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker, item) for item in tasks_to_run]
        for f in as_completed(futures):
            pass

    return stats
