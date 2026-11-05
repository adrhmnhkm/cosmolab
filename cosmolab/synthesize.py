import json
from datetime import datetime
from openai import OpenAI
from rich.console import Console
from . import config

console = Console(force_terminal=True, legacy_windows=False)


SYNTH_PROMPT_EN = """You are given N structured analyses of academic papers on a shared
research topic. Produce a markdown report with these sections:

1. **Positions map** - group papers by (argument_type x supports_or_critiques).
2. **Recurring premises** - list premises that appear across papers, and where they are contested.
3. **Top objections & replies** - the 5 strongest objections and the best replies found.
4. **Gaps** - what no paper addresses.
5. **Suggested reading order** - for a newcomer.

Cite papers by their `title` (year) inline. Be concrete; avoid filler.
"""

SYNTH_PROMPT_ID = """Kamu diberikan N analisis terstruktur dari paper akademik tentang
satu topik riset. Buat laporan markdown dengan bagian-bagian berikut:

1. **Peta posisi** - kelompokkan paper berdasarkan tipe argumen atau pendekatan riset dan apakah paper tersebut mendukung atau mengkritik argumen. Gunakan tabel dengan kolom: Tipe Argumen | Paper yang Mendukung | Paper yang Mengkritik.
2. **Premis berulang** - daftar premis utama yang muncul di berbagai paper. Untuk setiap premis:
   - Tunjukkan di paper mana muncul
   - Sebutkan bantahan atau kontroversi yang ditemukan
   - PENTING: gunakan terminologi baku bidang terkait secara tepat dan konsisten
3. **5 objeksi terkuat & balasan** - objeksi atau kritik terkuat terhadap argumen, dan respons/balasan terbaik yang ditemukan dalam paper.
4. **Gap** - topik atau pertanyaan yang tidak dibahas oleh paper manapun dalam dataset ini.
5. **Urutan bacaan untuk pemula** - rekomendasi urutan membaca paper.

Kutip paper dengan format `judul` (tahun). Gunakan bahasa presisi, hindari generalisasi berlebihan.
"""

PROMPTS = {
    "en": SYNTH_PROMPT_EN,
    "id": SYNTH_PROMPT_ID,
}


def _load_analyses() -> list:
    out = []
    for p in sorted(config.ANALYSIS_DIR.glob("*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


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


def synthesize(model: str = None, lang: str = "en") -> dict:
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    analyses = _load_analyses()
    if not analyses:
        console.print("[red]FAIL  No analyses found. Run `cosmolab analyze` first.[/red]")
        return {"error": "no analyses found; run `cosmolab analyze` first"}
    
    console.print(f"[cyan]SYNTHESIZE  {len(analyses)} papers ({lang})...[/cyan]")
    
    client = OpenAI(
        api_key=config.NINEROUTER_API_KEY,
        base_url=config.NINEROUTER_BASE_URL,
    )

    # Select prompt based on language
    prompt = PROMPTS.get(lang, PROMPTS["en"])

    payload = []
    for a in analyses:
        m = a.get("_meta", {})
        payload.append({
            "title": m.get("title"), "year": m.get("year"),
            "argument_type": a.get("argument_type"),
            "stance": a.get("supports_or_critiques"),
            "premises": a.get("premises"),
            "key_objection": a.get("key_objection"),
            "key_defense": a.get("key_defense"),
        })
    user_msg = json.dumps(payload, ensure_ascii=False)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    body = resp.choices[0].message.content.strip()
    table = _comparison_table(analyses)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = config.SYNTH_DIR / f"report_{stamp}_{lang}.md"
    report.write_text(
        f"# CosmoLab Corpus - Synthesis\n\n"
        f"_Generated {stamp} - {len(analyses)} papers - model={model} - lang={lang}_\n\n"
        f"{body}\n\n## Comparison table\n\n{table}\n",
        encoding="utf-8",
    )
    console.print(f"[green]OK  Report generated: {report.name}[/green]")
    return {"report": str(report), "n": len(analyses), "lang": lang}
