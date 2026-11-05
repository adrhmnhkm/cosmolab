import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from pydantic import BaseModel, ValidationError
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError
from rich.console import Console
from . import config
from .storage import read_meta, write_json
from .utils import fire_cb

console = Console(force_terminal=True, legacy_windows=False)

# Lazy singleton OpenAI client (Fix 2)
_client_lock = threading.Lock()
_client_instance: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a module-level singleton OpenAI client, created lazily on first use."""
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = OpenAI(
                    api_key=config.LLM_API_KEY,
                    base_url=config.LLM_BASE_URL,
                )
    return _client_instance


class Quote(BaseModel):
    text: str
    page_hint: str | None = None


class PaperAnalysis(BaseModel):
    thesis: str | None = None
    argument_type: str | None = None
    research_method: str | None = None
    premises: list[str] = []
    conclusion: str | None = None
    supports_or_critiques: str | None = None
    key_findings: list[str] = []
    key_objection: str | None = None
    key_defense: str | None = None
    notable_concepts: list[str] = []
    quotes: list[Quote] = []


PROMPT_EN = """You are a senior academic research analyst tasked with deeply dissecting the full paper body (not just the abstract or introduction, but Methodology, Empirical Findings, Discussion, and Conclusions).

CRITICAL INSTRUCTIONS — FULL-TEXT CORPUS DISSECTION:
1. DO NOT RELY MERELY ON THE ABSTRACT! Scan through all major sections: Introduction, Literature Review, Methodology, Results/Findings & Discussion, and Conclusions.
2. REPRESENTATIVE QUOTES ('quotes'):
   - Extract 4 to 6 verbatim key quotes directly from the text.
   - STRICTLY PROHIBITED from taking all quotes from the abstract!
   - Proportional distribution:
     * 1 quote from Introduction / Research Problem
     * 2-3 quotes from Results & Discussion (empirical data, findings, arguments, or solution mechanisms)
     * 1 quote from Conclusion / Recommendations
   - Preserve original language of the text.
   - Provide 'page_hint' indicating section name / approximate page (e.g., "Results & Discussion, p. 235").
3. RESEARCH METHODOLOGY ('research_method'):
   - Identify concrete research methodology (e.g., "Structured Literature Review", "Quantitative Multiple Linear Regression", "Normative Juridical", "Empirical Case Study", etc.).
4. CORE FINDINGS ('key_findings'):
   - List 3-5 concrete empirical/substantive findings from the Results & Discussion section.
5. LOGICAL PREMISES ('premises'):
   - Formulate 4-7 structured premises in English reflecting the logical derivation of the thesis.
6. ARGUMENT TYPE:
   - Select closest match: "empiris_kuantitatif"|"kualitatif_studi_kasus"|"yuridis_normatif"|"kajian_literatur"|"filosofis_rasional"|"konseptual_teoretis"|"komparatif"|"other".

Return STRICT JSON matching this schema:
{
  "thesis": str,
  "argument_type": str,
  "research_method": str|null,
  "premises": [str],
  "conclusion": str,
  "supports_or_critiques": "supports"|"critiques"|"neutral"|"mixed",
  "key_findings": [str],
  "key_objection": str|null,
  "key_defense": str|null,
  "notable_concepts": [str],
  "quotes": [{"text": str, "page_hint": str|null}]
}
"""

PROMPT_ID = """Kamu adalah analis riset akademik senior yang bertugas membedah naskah ilmiah secara komprehensif dari seluruh isi batang tubuh naskah (Pendahuluan, Metodologi, Hasil & Pembahasan, hingga Kesimpulan).

PENTING — PRINSIP ANALISIS MENYELURUH (DEEP CORPUS EXTRACTION):
1. JANGAN HANYA MEMBACA ABSTRAK! Jelajahi seluruh bagian teks: Pendahuluan, Landasan Teori, Metode Penelitian, Hasil & Pembahasan (Findings & Discussion), hingga Kesimpulan.
2. EKSTRAKSI KUTIPAN (QUOTES) DARI BERBAGAI BAGIAN:
   - Ambil 4 hingga 6 kutipan penting langsung (verbatim) dari teks naskah.
   - DILARANG KERAS mengutip semuanya dari abstrak! Abstrak hanyalah ringkasan awal.
   - Wajib mengambil kutipan secara proporsional dari:
     * Bagian Pendahuluan / Latar Belakang (masalah riset yang diangkat)
     * Bagian Hasil dan Pembahasan (data empiris, temuan faktual, kutipan wawancara/statistik, analisis regulasi, atau solusi teknis)
     * Bagian Kesimpulan / Rekomendasi (implikasi akhir)
   - Gunakan BAHASA ASLI teks tempat kalimat itu berada (jika naskah berbahasa Indonesia, kutip kalimat Bahasa Indonesianya; jika berbahasa Inggris, kutip kalimat Bahasa Inggrisnya). JANGAN membatasi kutipan hanya pada bahasa Inggris!
   - Cantumkan 'page_hint' dengan nama bab dan estimasi halaman (contoh: "Pendahuluan, hlm. 232", "Hasil dan Pembahasan, hlm. 235", "Kesimpulan").
3. METODOLOGI RISET ('research_method'):
   - Identifikasi pendekatan metodologi konkret yang digunakan (misal: "Kajian Literatur Terstruktur", "Kuantitatif Regresi Linier Berganda", "Yuridis Normatif", "Eksperimental", "Studi Kasus Kualitatif", dll).
4. TEMUAN INTI ('key_findings'):
   - Sebutkan 3-5 poin temuan substantif dari bab Hasil dan Pembahasan (bukan sekadar pengulangan abstrak).
5. PREMIS & ALUR LOGIS ('premises'):
   - Rumuskan 4-7 premis logis dalam Bahasa Indonesia yang mencerminkan alur pembuktian lengkap dari data dan analisis di pembahasan.
6. ARGUMENT TYPE:
   - Pilih salah satu: "empiris_kuantitatif", "kualitatif_studi_kasus", "yuridis_normatif", "kajian_literatur", "filosofis_rasional", "konseptual_teoretis", "komparatif", atau "other".

Kembalikan STRICT JSON dengan skema ini:
{
  "thesis": str,
  "argument_type": str,
  "research_method": str|null,
  "premises": [str],
  "conclusion": str,
  "supports_or_critiques": "supports"|"critiques"|"neutral"|"mixed",
  "key_findings": [str],
  "key_objection": str|null,
  "key_defense": str|null,
  "notable_concepts": [str],
  "quotes": [{"text": str, "page_hint": str|null}]
}
"""

PROMPTS = {
    "en": PROMPT_EN,
    "id": PROMPT_ID,
}


def _strip_references(text: str) -> str:
    """Remove bibliography/references section if found in the latter portion of the text."""
    if len(text) < 100:
        return text
    # Search from 40% onward to catch references in shorter documents
    start_pos = int(len(text) * 0.4)
    ref_match = re.search(
        r'\n\s*(?:[0-9]+\.?\s*)?(?:References|Bibliography|Works Cited|Literature Cited'
        r'|Referenzen|Referencias|Bibliografía'
        r'|Daftar Pustaka|Referensi|Kepustakaan)\b',
        text[start_pos:],
        re.IGNORECASE
    )
    if ref_match:
        return text[:start_pos + ref_match.start()]
    return text


def _snap_to_paragraph(text: str, pos: int, direction: str = "backward") -> int:
    """Find the nearest paragraph boundary (double newline) to avoid cutting mid-sentence."""
    if direction == "backward":
        idx = text.rfind("\n\n", max(0, pos - 500), pos)
        return idx + 2 if idx != -1 else pos
    else:  # forward
        idx = text.find("\n\n", pos, min(len(text), pos + 500))
        return idx if idx != -1 else pos


def _trim(text: str, limit: int = 60000) -> str:
    """Clean and intelligently trim text to fit within model context, snapping to paragraph boundaries."""
    text = _strip_references(text).strip()
    if len(text) <= limit:
        return text

    # If text is still larger than limit (e.g., long dissertation/book):
    # Allocate: 30% intro/setup, 45% core argument (middle), 25% conclusion
    head_size = int(limit * 0.30)
    core_size = int(limit * 0.45)
    tail_size = limit - head_size - core_size

    # Snap to paragraph boundaries to avoid cutting mid-sentence
    head_end = _snap_to_paragraph(text, head_size, "backward")
    head = text[:head_end].rstrip()

    mid_start_raw = (len(text) // 2) - (core_size // 2)
    mid_start = _snap_to_paragraph(text, mid_start_raw, "forward")
    mid_end_raw = mid_start + core_size
    mid_end = _snap_to_paragraph(text, mid_end_raw, "backward")
    middle = text[mid_start:mid_end].strip()

    tail_start_raw = len(text) - tail_size
    tail_start = _snap_to_paragraph(text, tail_start_raw, "forward")
    tail = text[tail_start:].lstrip()

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

def _analyze_one(client: OpenAI, text: str, model: str, lang: str = "id", timeout: int = 180, max_retries: int = 3) -> dict:
    """Analyze a single paper with LLM, with retry logic and usage tracking."""
    prompt = PROMPTS.get(lang, PROMPTS["id"])
    trimmed_text = _trim(text)
    last_error = None

    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": trimmed_text},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                timeout=timeout,
            )
            elapsed = round(time.monotonic() - t0, 2)

            raw = _parse_response(resp.choices[0].message.content)
            result = PaperAnalysis(**raw).model_dump()

            # Attach usage and timing metadata (Fix 7)
            usage = resp.usage
            result["_analysis_meta"] = {
                "elapsed_seconds": elapsed,
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
                "total_tokens": usage.total_tokens if usage else None,
                "attempt": attempt + 1,
            }
            return result

        except (RateLimitError,) as e:
            last_error = e
            wait = min(2 ** (attempt + 1), 30)
            console.print(f"[yellow]RATE-LIMIT  Retry in {wait}s (attempt {attempt+1}/{max_retries}): {str(e)[:60]}[/yellow]")
            time.sleep(wait)
        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            wait = min(2 ** attempt * 3, 30)
            console.print(f"[yellow]API-RETRY  {type(e).__name__} — retry in {wait}s (attempt {attempt+1}/{max_retries})[/yellow]")
            time.sleep(wait)
        except (ValidationError, ValueError) as e:
            # Parse/validation errors won't be fixed by retrying
            raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                console.print(f"[yellow]LLM-ERROR  {str(e)[:60]} — retry in {wait}s (attempt {attempt+1}/{max_retries})[/yellow]")
                time.sleep(wait)

    raise RuntimeError(f"LLM analysis failed after {max_retries} attempts: {last_error}")



def analyze_all(model: str = None, concurrency: int = 4, lang: str = "id", force: bool = False, progress_cb=None, files: list[str] = None) -> dict:
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    client = _get_client()
    stats = {"ok": 0, "skip": 0, "fail": 0}
    lock = threading.Lock()
    tasks_to_run = []
    target_set = set(files) if files else None

    for rec in read_meta():
        fname = rec.get("file")
        stem = Path(fname).stem
        if target_set and fname not in target_set and stem not in target_set:
            continue

        txt = config.TEXT_DIR / (stem + ".txt")
        out = config.ANALYSIS_DIR / (stem + ".json")
        
        # Check if paper was already analyzed in the requested language
        already_analyzed = False
        if out.exists():
            try:
                curr_data = json.loads(out.read_text(encoding="utf-8"))
                if curr_data.get("_meta", {}).get("lang") == lang:
                    already_analyzed = True
            except Exception:
                pass

        if not force and already_analyzed:
            stats["skip"] += 1
            console.print(f"[dim]SKIP  Already analyzed ({lang}): {stem}[/dim]")
            continue
        if not txt.exists():
            stats["fail"] += 1
            console.print(f"[red]FAIL  No text file: {stem}[/red]")
            continue
        tasks_to_run.append((rec, stem, txt, out))

    if not tasks_to_run:
        return stats

    console.print(f"[cyan]RUNNING ANALYSIS ({lang.upper()})[/cyan] [dim]({len(tasks_to_run)} papers in parallel, concurrency={concurrency})...[/dim]")

    def _worker(item):
        rec, stem, txt, out = item
        paper_title = rec.get("title") or stem
        try:
            console.print(f"[cyan]ANALYZE  {stem}[/cyan]")
            result = _analyze_one(client, txt.read_text(encoding="utf-8"), model, lang=lang)
            analysis_meta = result.pop("_analysis_meta", {})
            result["_meta"] = {
                "paper_file": rec["file"],
                "doi": rec.get("doi"),
                "title": rec.get("title"),
                "year": rec.get("year"),
                "model": model,
                "lang": lang,
                "prompt_version": "v3",
                "elapsed_seconds": analysis_meta.get("elapsed_seconds"),
                "prompt_tokens": analysis_meta.get("prompt_tokens"),
                "completion_tokens": analysis_meta.get("completion_tokens"),
                "total_tokens": analysis_meta.get("total_tokens"),
            }
            write_json(out, result)
            elapsed_str = f" ({analysis_meta.get('elapsed_seconds', '?')}s, {analysis_meta.get('total_tokens', '?')} tok)"
            console.print(f"[green]OK  Analyzed: {stem}{elapsed_str}[/green]")
            with lock:
                stats["ok"] += 1
            return {"ok": True, "title": paper_title, "stem": stem, "result": result}
        except (ValidationError, ValueError) as e:
            error_log = config.ANALYSIS_DIR / f"{stem}.error.txt"
            error_log.write_text(f"Error: {e}\nStem: {stem}\n", encoding="utf-8")
            console.print(f"[red]PARSE_ERROR  {stem} - {str(e)[:60]}[/red]")
            with lock:
                stats["fail"] += 1
            return {"ok": False, "title": paper_title, "stem": stem, "error": f"Parse Error: {str(e)[:60]}"}
        except Exception as e:
            error_log = config.ANALYSIS_DIR / f"{stem}.error.txt"
            error_log.write_text(f"API Error: {e}\nStem: {stem}\n", encoding="utf-8")
            console.print(f"[red]API_ERROR  {stem} - {str(e)[:60]}[/red]")
            with lock:
                stats["fail"] += 1
            return {"ok": False, "title": paper_title, "stem": stem, "error": f"API Error: {str(e)[:60]}"}

    max_workers = max(1, min(concurrency, len(tasks_to_run)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker, item) for item in tasks_to_run]
        for f in as_completed(futures):
            res_item = f.result()
            if res_item and res_item.get("ok"):
                fire_cb(progress_cb, "analyze_ok", f"Analisis selesai: {res_item['title'][:55]} (Tesis, premis, metodologi & kutipan siap)", res_item)
            elif res_item and not res_item.get("ok"):
                fire_cb(progress_cb, "analyze_fail", f"Gagal analisis: {res_item['title'][:40]} ({res_item.get('error', '')})", res_item)

    return stats


def analyze_single_paper(paper_file_or_stem: str, model: str = None, lang: str = "id", force: bool = True) -> dict:
    """
    Analyze or re-analyze a single paper on demand.
    Extracts text automatically from PDF if missing, runs LLM full-body dissection,
    saves analysis JSON, and syncs only this paper to SQLite database.
    """
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    client = _get_client()

    clean_file = Path(paper_file_or_stem).name
    stem = Path(paper_file_or_stem).stem
    txt_path = config.TEXT_DIR / f"{stem}.txt"
    pdf_path = config.PDF_DIR / (clean_file if clean_file.endswith(".pdf") else f"{stem}.pdf")
    out_path = config.ANALYSIS_DIR / f"{stem}.json"

    # 1. Ensure text exists
    if not txt_path.exists() or txt_path.stat().st_size == 0:
        if pdf_path.exists():
            from . import extract
            text = extract._pdf_to_text(pdf_path)
            if not text.strip():
                raise ValueError(f"Tidak dapat mengekstrak teks dari berkas PDF: {pdf_path.name}")
            txt_path.write_text(text, encoding="utf-8")
        else:
            raise FileNotFoundError(f"Berkas naskah PDF atau teks tidak ditemukan: {stem}")

    full_text = txt_path.read_text(encoding="utf-8")
    result = _analyze_one(client, full_text, model, lang=lang)

    # Find metadata record if available
    metadata = read_meta()
    rec = next((m for m in metadata if Path(m.get("file", "")).stem == stem), {})
    file_key = rec.get("file") or f"{stem}.pdf"

    # Merge analysis timing into _meta
    analysis_meta = result.pop("_analysis_meta", {})
    result["_meta"] = {
        "paper_file": file_key,
        "doi": rec.get("doi"),
        "title": rec.get("title") or stem.replace("_", " "),
        "year": rec.get("year"),
        "model": model,
        "lang": lang,
        "prompt_version": "v3",
        "elapsed_seconds": analysis_meta.get("elapsed_seconds"),
        "prompt_tokens": analysis_meta.get("prompt_tokens"),
        "completion_tokens": analysis_meta.get("completion_tokens"),
        "total_tokens": analysis_meta.get("total_tokens"),
    }

    write_json(out_path, result)

    # Sync only this paper to database (Fix 6: O(1) instead of O(N))
    from . import db
    db.sync_one(file_key)

    return result
