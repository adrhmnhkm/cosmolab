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

# One lazily created OpenAI client per server (Fix 2)
_client_lock = threading.Lock()
_clients: dict[tuple[str, str], OpenAI] = {}


def _get_client() -> OpenAI:
    """Return the shared OpenAI client for the active AI (see config.apply_ai)."""
    key = (config.LLM_BASE_URL, config.LLM_API_KEY)
    if key not in _clients:
        with _client_lock:
            if key not in _clients:
                _clients[key] = OpenAI(base_url=key[0], api_key=key[1])
    return _clients[key]


class Quote(BaseModel):
    text: str
    page_hint: str | None = None


class PaperAnalysis(BaseModel):
    thesis: str | None = None
    argument_type: str | None = None
    research_question: str | None = None
    research_method: str | None = None
    sample_data: str | None = None
    premises: list[str] = []
    conclusion: str | None = None
    supports_or_critiques: str | None = None
    key_findings: list[str] = []
    limitations: list[str] = []
    future_research: list[str] = []
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
7. LITERATURE REVIEW FIELDS (what a consultant needs to compare papers):
   - 'research_question': the research question or aim as the authors state it, in one or two sentences.
   - 'sample_data': who or what was studied: sample size and population, data source, period, location, or the texts and regulations analysed. Null if the paper has no data (purely conceptual).
   - 'limitations': 1-4 limitations the authors acknowledge. If they state none, give at most 2 evident ones and start each with "(not stated by the authors)".
   - 'future_research': 1-3 suggestions for further research made by the authors. Empty list if they make none.
8. OBJECTION AND DEFENSE ('key_objection', 'key_defense'): fill these only for philosophical, theological, or conceptual argument papers. Use null for empirical, legal, and review papers.

Return STRICT JSON matching this schema:
{
  "thesis": str,
  "argument_type": str,
  "research_question": str|null,
  "research_method": str|null,
  "sample_data": str|null,
  "premises": [str],
  "conclusion": str,
  "supports_or_critiques": "supports"|"critiques"|"neutral"|"mixed",
  "key_findings": [str],
  "limitations": [str],
  "future_research": [str],
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
7. ISIAN TINJAUAN PUSTAKA (yang dibutuhkan konsultan untuk membandingkan paper):
   - 'research_question': pertanyaan atau tujuan penelitian seperti dinyatakan penulis, satu atau dua kalimat.
   - 'sample_data': apa atau siapa yang diteliti: jumlah dan populasi sampel, sumber data, periode, lokasi, atau teks dan peraturan yang dianalisis. Null kalau paper tidak memakai data (murni konseptual).
   - 'limitations': 1-4 keterbatasan yang diakui penulis. Kalau penulis tidak menyebut satu pun, beri paling banyak 2 keterbatasan yang jelas dan awali masing-masing dengan "(tidak disebut penulis)".
   - 'future_research': 1-3 saran penelitian lanjutan dari penulis. Daftar kosong kalau tidak ada.
8. KEBERATAN DAN PEMBELAAN ('key_objection', 'key_defense'): isi hanya untuk paper argumen filsafat, teologi, atau konseptual. Isi null untuk paper empiris, hukum, dan kajian literatur.

Kembalikan STRICT JSON dengan skema ini:
{
  "thesis": str,
  "argument_type": str,
  "research_question": str|null,
  "research_method": str|null,
  "sample_data": str|null,
  "premises": [str],
  "conclusion": str,
  "supports_or_critiques": "supports"|"critiques"|"neutral"|"mixed",
  "key_findings": [str],
  "limitations": [str],
  "future_research": [str],
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


# Fields added for literature-review style analysis (13 Nov 2026). Analyses made
# before that lack these keys and are listed as "perlu dilengkapi".
LIT_FIELDS = ("research_question", "sample_data", "limitations", "future_research")


def needs_lit_fields(analysis: dict | None) -> bool:
    """True for an analysis made before the literature-review fields existed."""
    return bool(analysis) and not all(k in analysis for k in LIT_FIELDS)


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

def expected_output_tokens(model: str | None = None) -> int:
    """Typical length of one analysis, from past analyses (same model first), for progress bars."""
    same, other = [], []
    for path in config.ANALYSIS_DIR.glob("*.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8")).get("_meta") or {}
        except (OSError, ValueError):
            continue
        n = meta.get("completion_tokens")
        if isinstance(n, int) and n > 0:
            (same if model and meta.get("model") == model else other).append(n)
    pool = same or other
    return int(sum(pool) / len(pool)) if pool else 2000


def _step(on_step, event: str, **info) -> None:
    """Report one analysis step to a progress display. A display error never stops the analysis."""
    if on_step:
        try:
            on_step(event, info)
        except Exception:
            pass


def _analyze_one(client: OpenAI, text: str, model: str, lang: str = "id", timeout: int = 180, max_retries: int = 3,
                 on_step=None, label: str = "", expected: int | None = None) -> dict:
    """Analyze a single paper with the LLM, with retries and usage tracking.

    The answer is streamed so progress is visible while the AI writes. on_step(event, info) gets:
    "kirim" (request sent), "token" (tokens written so far), "ulang" (retry), "selesai" (answer complete).
    """
    from . import usage as _usage

    prompt = PROMPTS.get(lang, PROMPTS["id"])
    trimmed_text = _trim(text)
    est_input = len(trimmed_text) // 4
    expected = expected or expected_output_tokens(model)
    name = label or "paper"
    last_error = None

    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            console.print(f"[cyan]AI       [/cyan]{name}: kirim ~{est_input:,} token ke {model}"
                          + (f" (percobaan {attempt + 1})" if attempt else ""))
            _step(on_step, "kirim", model=model, input_tokens=est_input, chars=len(trimmed_text),
                  trimmed=len(trimmed_text) < len(text), attempt=attempt + 1)
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": trimmed_text},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                timeout=timeout,
                stream=True,
                stream_options={"include_usage": True},
            )
            parts, written, thought, usage, first_at, last_report = [], 0, 0, None, None, 0.0
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                d = chunk.choices[0].delta if chunk.choices else None
                delta = d.content if d else None
                if not delta:
                    # Reasoning models (deepseek-v4-pro) think before they write; report that too,
                    # so the display does not look stuck.
                    if d is not None and (getattr(d, "reasoning_content", None) or getattr(d, "reasoning", None)):
                        thought += 1
                        now = time.monotonic()
                        if thought == 1:
                            console.print(f"[dim]AI       {name}: AI mulai berpikir setelah {now - t0:.1f} dtk[/dim]")
                        if now - last_report >= 0.25:
                            last_report = now
                            _step(on_step, "pikir", tokens=thought, elapsed=now - t0)
                    continue
                parts.append(delta)
                written += 1
                now = time.monotonic()
                if first_at is None:
                    first_at = now - t0
                    more = f" ({thought:,} token berpikir)" if thought else ""
                    console.print(f"[dim]AI       {name}: AI mulai menulis setelah {first_at:.1f} dtk{more}[/dim]")
                if now - last_report >= 0.25:
                    last_report = now
                    _step(on_step, "token", tokens=written, expected=expected, elapsed=now - t0)
            elapsed = round(time.monotonic() - t0, 2)

            prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
            _usage.record(model=model, prompt_tokens=prompt_tokens or est_input,
                          completion_tokens=completion_tokens or written, feature="analyze")
            _step(on_step, "selesai", tokens=completion_tokens or written, expected=expected, elapsed=elapsed)

            raw = _parse_response("".join(parts))
            result = PaperAnalysis(**raw).model_dump()
            result["_analysis_meta"] = {
                "elapsed_seconds": elapsed,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0) if usage else None,
                "attempt": attempt + 1,
            }
            return result

        except (RateLimitError,) as e:
            last_error = e
            wait = min(2 ** (attempt + 1), 30)
            console.print(f"[yellow]ULANG    {name}: batas pemakaian API, coba lagi dalam {wait} dtk "
                          f"({attempt + 1}/{max_retries}): {str(e)[:80]}[/yellow]")
            _step(on_step, "ulang", attempt=attempt + 1, max=max_retries, wait=wait, error="batas pemakaian API")
            time.sleep(wait)
        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            wait = min(2 ** attempt * 3, 30)
            why = "AI tidak menjawab tepat waktu" if isinstance(e, APITimeoutError) else \
                f"tidak bisa terhubung ke {config.LLM_BASE_URL}"
            console.print(f"[yellow]ULANG    {name}: {why}, coba lagi dalam {wait} dtk ({attempt + 1}/{max_retries})[/yellow]")
            _step(on_step, "ulang", attempt=attempt + 1, max=max_retries, wait=wait, error=why)
            time.sleep(wait)
        except (ValidationError, ValueError) as e:
            # Parse/validation errors won't be fixed by retrying
            console.print(f"[red]GAGAL    {name}: jawaban AI bukan JSON analisis yang sah: {str(e)[:120]}[/red]")
            raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                console.print(f"[yellow]ULANG    {name}: {str(e)[:120]}, coba lagi dalam {wait} dtk "
                              f"({attempt + 1}/{max_retries})[/yellow]")
                _step(on_step, "ulang", attempt=attempt + 1, max=max_retries, wait=wait, error=str(e)[:120])
                time.sleep(wait)

    console.print(f"[red]GAGAL    {name}: AI gagal {max_retries} kali: {last_error}[/red]")
    raise RuntimeError(f"LLM analysis failed after {max_retries} attempts: {last_error}")



def analyze_all(model: str = None, concurrency: int = 4, lang: str = "id", force: bool = False, progress_cb=None,
                files: list[str] = None, on_step=None) -> dict:
    """Analyze many papers in parallel.

    on_step(event, info), for a live progress display: "rencana" (how many papers), then per paper
    "mulai", the steps of _analyze_one ("kirim", "token", "ulang", "selesai"), and "beres" or "gagal".
    Every info dict of a paper carries its "stem" and "title".
    """
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
            console.print(f"[dim]LEWATI   {stem}: sudah dianalisis ({lang})[/dim]")
            continue
        if not txt.exists():
            stats["fail"] += 1
            console.print(f"[red]GAGAL    {stem}: teks PDF belum ada, jalankan extract dulu[/red]")
            continue
        tasks_to_run.append((rec, stem, txt, out))

    _step(on_step, "rencana", total=len(tasks_to_run), skipped=stats["skip"], failed=stats["fail"], model=model)
    if not tasks_to_run:
        console.print(f"[dim]ANALISIS tidak ada paper baru ({stats['skip']} sudah dianalisis, {stats['fail']} tanpa teks)[/dim]")
        return stats

    expected = expected_output_tokens(model)
    console.print(f"[bold cyan]ANALISIS {len(tasks_to_run)} paper[/bold cyan] dengan {model} "
                  f"({concurrency} sekaligus, bahasa {lang.upper()})")

    def _worker(item):
        rec, stem, txt, out = item
        paper_title = rec.get("title") or stem
        try:
            text = txt.read_text(encoding="utf-8")
            console.print(f"[cyan]MULAI    [/cyan]{paper_title[:70]} [dim]({len(text):,} karakter)[/dim]")
            _step(on_step, "mulai", stem=stem, title=paper_title, chars=len(text))
            paper_step = (lambda ev, info: on_step(ev, {**info, "stem": stem, "title": paper_title})) if on_step else None
            result = _analyze_one(client, text, model, lang=lang, on_step=paper_step, label=paper_title[:50],
                                  expected=expected)
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
            try:
                from . import audit

                audit.log("analisis", file=rec["file"], model=model, lang=lang,
                          prompt_version=audit.prompt_version(PROMPTS.get(lang, PROMPT_ID)),
                          tokens=analysis_meta.get("total_tokens"))
            except Exception:
                pass
            console.print(f"[green]BERES    [/green]{paper_title[:70]} [dim]({analysis_meta.get('elapsed_seconds', '?')} dtk, "
                          f"{analysis_meta.get('total_tokens') or '?'} token)[/dim]")
            _step(on_step, "beres", stem=stem, title=paper_title, elapsed=analysis_meta.get("elapsed_seconds"),
                  tokens=analysis_meta.get("total_tokens"))
            with lock:
                stats["ok"] += 1
            return {"ok": True, "title": paper_title, "stem": stem, "result": result}
        except (ValidationError, ValueError) as e:
            error_log = config.ANALYSIS_DIR / f"{stem}.error.txt"
            error_log.write_text(f"Error: {e}\nStem: {stem}\n", encoding="utf-8")
            console.print(f"[red]GAGAL    {paper_title[:70]}: jawaban AI tidak bisa dibaca ({str(e)[:80]})[/red]")
            _step(on_step, "gagal", stem=stem, title=paper_title, error=f"jawaban AI tidak bisa dibaca: {str(e)[:80]}")
            with lock:
                stats["fail"] += 1
            return {"ok": False, "title": paper_title, "stem": stem, "error": f"Parse Error: {str(e)[:60]}"}
        except Exception as e:
            error_log = config.ANALYSIS_DIR / f"{stem}.error.txt"
            error_log.write_text(f"API Error: {e}\nStem: {stem}\n", encoding="utf-8")
            console.print(f"[red]GAGAL    {paper_title[:70]}: {str(e)[:120]}[/red]")
            _step(on_step, "gagal", stem=stem, title=paper_title, error=str(e)[:120])
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

    console.print(f"[bold]SELESAI  [/bold]{stats['ok']} dianalisis, {stats['skip']} dilewati, {stats['fail']} gagal")
    return stats


def analyze_single_paper(paper_file_or_stem: str, model: str = None, lang: str = "id", force: bool = True,
                         on_step=None) -> dict:
    """
    Analyze or re-analyze a single paper on demand.
    Extracts text automatically from PDF if missing, runs LLM full-body dissection,
    saves analysis JSON, and syncs only this paper to SQLite database.

    on_step(event, info), for a live progress display: "baca" (text ready), the steps of
    _analyze_one ("kirim", "token", "ulang", "selesai"), then "simpan" and "beres".
    """
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    client = _get_client()

    clean_file = Path(paper_file_or_stem).name
    stem = Path(paper_file_or_stem).stem
    txt_path = config.TEXT_DIR / f"{stem}.txt"
    pdf_path = config.PDF_DIR / (clean_file if clean_file.endswith(".pdf") else f"{stem}.pdf")
    out_path = config.ANALYSIS_DIR / f"{stem}.json"

    rec = next((m for m in read_meta() if Path(m.get("file", "")).stem == stem), {})
    title = rec.get("title") or stem.replace("_", " ")
    console.print(f"[bold cyan]ANALISIS [/bold cyan]{title[:80]} dengan {model}")

    # 1. Ensure text exists
    if not txt_path.exists() or txt_path.stat().st_size == 0:
        if pdf_path.exists():
            from . import extract
            console.print(f"[cyan]TEKS     [/cyan]{title[:50]}: teks belum ada, ekstrak dari PDF")
            text = extract._pdf_to_text(pdf_path)
            if not text.strip():
                raise ValueError(f"Tidak dapat mengekstrak teks dari berkas PDF: {pdf_path.name}")
            txt_path.write_text(text, encoding="utf-8")
        else:
            raise FileNotFoundError(f"Berkas naskah PDF atau teks tidak ditemukan: {stem}")

    full_text = txt_path.read_text(encoding="utf-8")
    pages = full_text.count("--- [Halaman ")
    console.print(f"[cyan]TEKS     [/cyan]{title[:50]}: {len(full_text):,} karakter" + (f", {pages} halaman" if pages else ""))
    _step(on_step, "baca", chars=len(full_text), pages=pages, title=title)
    result = _analyze_one(client, full_text, model, lang=lang, on_step=on_step, label=title[:50])

    _step(on_step, "simpan", title=title)
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
    try:
        from . import audit

        audit.log("analisis", file=file_key, model=model, lang=lang,
                  prompt_version=audit.prompt_version(PROMPTS.get(lang, PROMPT_ID)),
                  tokens=analysis_meta.get("total_tokens"))
    except Exception:
        pass

    # Sync only this paper to database (Fix 6: O(1) instead of O(N))
    from . import db
    db.sync_one(file_key)
    console.print(f"[green]BERES    [/green]{title[:70]} [dim]({analysis_meta.get('elapsed_seconds', '?')} dtk, "
                  f"{analysis_meta.get('total_tokens') or '?'} token)[/dim]")
    _step(on_step, "beres", title=title, elapsed=analysis_meta.get("elapsed_seconds"),
          tokens=analysis_meta.get("total_tokens"))

    return result
