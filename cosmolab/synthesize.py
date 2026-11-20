import json
from datetime import datetime
from openai import OpenAI
from rich.console import Console
from . import config

console = Console(force_terminal=True, legacy_windows=False)


SYNTH_PROMPT_EN = """You are given N structured analyses of academic papers on a shared
research topic, each accompanied by structured metadata and verbatim passages from the original text. Produce a markdown report with these sections:

1. **Positions map** - group papers by (argument_type x supports_or_critiques).
2. **Recurring premises** - list premises that appear across papers, and where they are contested.
3. **Top objections & replies** - the 5 strongest objections and the best replies found.
4. **Gaps** - what no paper addresses.
5. **Suggested reading order** - for a newcomer.

CITATION & GROUNDING RULES:
- EVERY factual sentence must end with an inline citation including page number from the provided verbatim passages, e.g. `[Title (Year), Hal. X]` or `[Title (Year)]`.
- Your own analytical synthesis or commentary must start with "Catatan analis:" and carry no citation.
- Strictly ground claims in the provided analyses and passages; do NOT extrapolate or fabricate claims outside the corpus.
- Be concrete; avoid filler.
"""

SYNTH_PROMPT_ID = """Kamu diberikan N analisis terstruktur dari paper akademik tentang
satu topik riset. Setiap paper memuat analisis terstruktur serta kutipan/passage verbatim dari naskah asli beserta nomor halaman. Buat laporan markdown dengan bagian-bagian berikut:

1. **Peta posisi** - kelompokkan paper berdasarkan tipe argumen atau pendekatan riset dan apakah paper tersebut mendukung atau mengkritik argumen. Gunakan tabel dengan kolom: Tipe Argumen | Paper yang Mendukung | Paper yang Mengkritik.
2. **Premis berulang** - daftar premis utama yang muncul di berbagai paper. Untuk setiap premis:
   - Tunjukkan di paper mana muncul
   - Sebutkan bantahan atau kontroversi yang ditemukan
   - PENTING: gunakan terminologi baku bidang terkait secara tepat dan konsisten
3. **5 objeksi terkuat & balasan** - objeksi atau kritik terkuat terhadap argumen, dan respons/balasan terbaik yang ditemukan dalam paper.
4. **Gap** - topik atau pertanyaan yang tidak dibahas oleh paper manapun dalam dataset ini.
5. **Urutan bacaan untuk pemula** - rekomendasi urutan membaca paper.

ATURAN SITASI & GROUNDING:
- SETIAP kalimat faktual wajib diakhiri sitasi berserta nomor halaman dari passage yang tersedia, contoh: `[Judul (Tahun), Hal. X]` atau `[Judul (Tahun)]`.
- Kalimat penilaian/sintesis dari analis sendiri wajib diawali dengan "Catatan analis:" dan jangan diberi sitasi.
- Berpijak HANYA pada analisis dan kutipan yang disediakan. JANGAN mengarang fakta di luar data.
- Gunakan bahasa presisi, hindari generalisasi berlebihan.
"""

PROMPTS = {
    "en": SYNTH_PROMPT_EN,
    "id": SYNTH_PROMPT_ID,
}


def _load_analyses() -> list:
    out = []
    for p in sorted(config.ANALYSIS_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "_stem" not in data:
                data["_stem"] = p.stem
            out.append(data)
        except Exception:
            continue
    return out


def _extract_passages_for_analysis(a: dict, file_name: str, max_passages: int = 2) -> list[dict]:
    passages = []
    for q in a.get("quotes") or []:
        if isinstance(q, dict) and q.get("text"):
            pg = q.get("page")
            pg_label = f"Hal. {pg}" if pg else (q.get("page_hint") or "")
            passages.append({"page": pg or 1, "page_label": pg_label, "verbatim": q["text"]})
            if len(passages) >= max_passages:
                break

    if len(passages) < max_passages and file_name:
        try:
            from . import retrieval

            m = a.get("_meta", {})
            query = a.get("thesis") or a.get("research_question") or m.get("title") or ""
            if query:
                extra = retrieval.find_grounded_passages(file_name, query, top_k=max_passages - len(passages))
                for psg in extra:
                    if not psg.get("fallback") and psg.get("verbatim"):
                        passages.append({
                            "page": psg.get("page", 1),
                            "page_label": psg.get("page_label", f"Hal. {psg.get('page', 1)}"),
                            "verbatim": psg.get("verbatim", ""),
                        })
        except Exception:
            pass

    return passages


def _comparison_table(analyses: list) -> str:
    rows = ["| Title | Year | Type | Stance | Key objection |",
            "|---|---|---|---|---|"]
    for a in analyses:
        m = a.get("_meta", {})
        rows.append("| {t} | {y} | {ty} | {s} | {o} |".format(
            t=(m.get("title") or "")[:60].replace("|", "/"),
            y=m.get("year") or "",
            ty=a.get("argument_type") or "-",
            s=a.get("supports_or_critiques") or "-",
            o=(a.get("key_objection") or "-")[:80].replace("|", "/"),
        ))
    return "\n".join(rows)


def synthesize(
    model: str = None,
    lang: str = "en",
    check_claims: bool = True,
    judge=None,
    evidence_fn=None,
) -> dict:
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    analyses = _load_analyses()
    if not analyses:
        console.print("[red]FAIL  No analyses found. Run `cosmolab analyze` first.[/red]")
        return {"error": "no analyses found; run `cosmolab analyze` first"}

    console.print(f"[cyan]SYNTHESIZE  {len(analyses)} papers ({lang})...[/cyan]")

    client = OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
    )

    # Select prompt based on language
    prompt = PROMPTS.get(lang, PROMPTS["en"])

    payload = []
    papers_for_check = []
    for a in analyses:
        m = a.get("_meta", {})
        stem = a.get("_stem", "")
        file_name = m.get("file") or (f"{stem}.pdf" if stem else "")
        passages = _extract_passages_for_analysis(a, file_name, max_passages=2)
        payload.append({
            "title": m.get("title") or file_name,
            "year": m.get("year"),
            "argument_type": a.get("argument_type"),
            "research_question": a.get("research_question"),
            "method": a.get("research_method"),
            "sample_data": a.get("sample_data"),
            "key_findings": a.get("key_findings"),
            "limitations": a.get("limitations"),
            "future_research": a.get("future_research"),
            "stance": a.get("supports_or_critiques"),
            "premises": a.get("premises"),
            "key_objection": a.get("key_objection"),
            "key_defense": a.get("key_defense"),
            "verbatim_passages": passages,
        })
        papers_for_check.append({
            "file": file_name,
            "title": m.get("title") or file_name,
            "year": str(m.get("year") or ""),
            "authors": m.get("authors") or "",
            "thesis": a.get("thesis") or "",
            "conclusion": a.get("conclusion") or "",
        })

    user_msg = json.dumps(payload, ensure_ascii=False)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        timeout=180.0,
        stream=True,
    )
    if hasattr(resp, "choices"):
        body = (resp.choices[0].message.content or "").strip()
    else:
        parts = []
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        body = "".join(parts).strip()

    claims_report = None
    if check_claims:
        try:
            from . import entail

            console.print("[cyan]AUDIT  Memeriksa klaim pada laporan sintesis terhadap naskah sumber...[/cyan]")
            claims_report = entail.check_answer(
                body,
                papers=papers_for_check,
                model=config.JUDGE_MODEL,
                judge=judge,
                evidence_fn=evidence_fn,
            )
            flagged = entail.needs_attention(claims_report)
            total = claims_report.get("total", 0)
            if flagged:
                console.print(f"[yellow]WARN  Pemeriksaan klaim: {flagged} dari {total} klaim perlu dicek sebelum dikutip.[/yellow]")
            else:
                console.print(f"[green]OK  Pemeriksaan klaim: seluruh {total} klaim terverifikasi.[/green]")
        except Exception as e:
            console.print(f"[dim]Pemeriksaan klaim sintesis dilewati: {e}[/dim]")
            claims_report = None

    claim_section = ""
    if claims_report and claims_report.get("total"):
        from . import entail

        s = claims_report.get("summary", {})
        total = claims_report.get("total", 0)
        flagged = entail.needs_attention(claims_report)
        status_lines = [
            f"- **Total klaim diperiksa:** {total}",
        ]
        for v in [entail.SUPPORTED, entail.PARTIAL, entail.UNSUPPORTED, entail.NO_SOURCE, entail.NO_CITATION, entail.UNCHECKED]:
            if s.get(v):
                status_lines.append(f"- **{entail.VERDICT_LABELS.get(v, v)}:** {s[v]}")
        note = (
            f"> [!WARNING]\n> Terdapat {flagged} klaim yang perlu dicek sebelum dijadikan rujukan resmi.\n"
            if flagged else
            "> [!NOTE]\n> Semua klaim pada laporan ini terverifikasi terhadap teks sumber.\n"
        )
        claim_section = f"\n## Pemeriksaan Klaim (Audit Akurasi)\n\n{note}\n" + "\n".join(status_lines) + "\n"

    table = _comparison_table(analyses)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = config.SYNTH_DIR / f"report_{stamp}_{lang}.md"
    report.write_text(
        f"# CosmoLab Corpus - Synthesis\n\n"
        f"_Generated {stamp} - {len(analyses)} papers - model={model} - lang={lang}_\n\n"
        f"{body}\n\n"
        f"{claim_section}\n"
        f"## Comparison table\n\n{table}\n",
        encoding="utf-8",
    )
    console.print(f"[green]OK  Report generated: {report.name}[/green]")
    out = {"report": str(report), "n": len(analyses), "lang": lang}
    if claims_report:
        from . import entail

        out["claims_report"] = claims_report
        out["claims_total"] = claims_report.get("total", 0)
        out["claims_flagged"] = entail.needs_attention(claims_report)
    return out
