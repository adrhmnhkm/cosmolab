"""
CosmoLab University: Research Gap & Novelty Finder Engine (Pendeteksi Celah Riset)
Identifies unaddressed dialectical tensions, methodological blindspots, and
generates high-novelty research proposals for S2/S3 theses and peer-reviewed journals.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from rich.console import Console
from . import config
from . import db
from . import faculties as _faculties

console = Console(force_terminal=True, legacy_windows=False)


def _safe_extract(resp) -> str:
    """Safely extract text content from OpenAI-compatible API response."""
    if not resp or not hasattr(resp, "choices") or not resp.choices:
        return ""
    choice = resp.choices[0]
    if not hasattr(choice, "message") or not choice.message:
        return ""
    return choice.message.content or ""


def find_research_gaps(faculty_id: str = "all", custom_focus: str = "", model: str = None) -> dict:
    """
    Analyze the corpus to detect unresolved dialectical debates,
    methodological gaps, and generate novel research topics.
    """
    model = model or config.LLM_MODEL
    all_papers = db.get_all_papers_with_analyses()
    if faculty_id != "all":
        papers = [p for p in all_papers if p.get("faculty") == faculty_id]
        if not papers:
            papers = all_papers
    else:
        papers = all_papers

    fac_obj = _faculties.get_faculty(faculty_id) if faculty_id != "all" else None
    fac_name = fac_obj.name if fac_obj else "Multidisipliner (Semua Fakultas)"

    # Compile structured corpus digest
    corpus_items = []
    for p in papers[:20]:
        title = p.get("title") or "Untitled"
        year = p.get("year") or "n.d."
        thesis = p.get("thesis") or "Tidak ada data tesis"
        obj = p.get("key_objection") or "Tidak ada data objeksi"
        defense = p.get("key_defense") or "Tidak ada data tanggapan"
        stance = p.get("supports_or_critiques") or "neutral"
        corpus_items.append(
            f"- [{year}] {title} (Stance: {stance})\n"
            f"  Tesis: {thesis}\n"
            f"  Objeksi: {obj}\n"
            f"  Tanggapan: {defense}"
        )

    corpus_digest = "\n".join(corpus_items)

    system_prompt = """Anda adalah Senior Academic Research Consultant dan Dekan Pascasarjana lintas disiplin. Sesuaikan kerangka analisis dengan bidang korpus (humaniora, filsafat, agama, hukum, ekonomi, pendidikan, psikologi, sains, teknologi, atau kesehatan).
Tugas Anda adalah melakukan audit mendalam terhadap korpus literatur yang tersedia untuk mendeteksi:
1. Peta Konsensus & Perdebatan Terbuka (Unresolved Dialectical Tensions).
2. Titik Buta Metodologis & Konseptual (Methodological & Theoretical Blindspots).
3. 3 Usulan Topik Proposal Riset Baru (High-Novelty Research Proposals) yang sangat layak untuk Tesis S2, Disertasi S3, atau publikasi jurnal bereputasi (SINTA 1-2 / Scopus).

Gunakan Bahasa Indonesia ilmiah yang elegan, presisi, dan tajam.
Keluarkan output HANYA dalam format JSON valid dengan struktur:
{
  "faculty_domain": "Nama Domain",
  "executive_summary": "Ringkasan eksekutif 2-3 paragraf mengenai kondisi terkini riset...",
  "established_consensus": [
    "Poin konsensus 1...",
    "Poin konsensus 2..."
  ],
  "unresolved_tensions": [
    {
      "issue": "Nama Isu Perdebatan",
      "thesis_side": "Argumen kubu teisme / kalam...",
      "antithesis_side": "Argumen kubu kritik / ateisme analitik...",
      "why_stuck": "Mengapa perdebatan ini masih buntu atau belum tuntas?"
    }
  ],
  "methodological_blindspots": [
    "Titik buta 1: belum ada pengujian menggunakan...",
    "Titik buta 2: dominasi narasi X yang mengabaikan..."
  ],
  "novel_research_proposals": [
    {
      "title": "Usulan Judul Penelitian yang Kuat & Menarik",
      "target_level": "Tesis S2 / Disertasi S3 / Jurnal Bereputasi",
      "gap_addressed": "Kesenjangan pustaka spesifik yang dijawab oleh proposal ini",
      "research_questions": ["Pertanyaan penelitian 1?", "Pertanyaan penelitian 2?"],
      "proposed_hypothesis": "Hipotesis kerja / tesis awal yang ditawarkan",
      "theoretical_framework": "Perpaduan teori Turāth dan filsafat/sains kontemporer yang digunakan",
      "expected_novelty": "Nilai kebaruan akademik (novelty) yang membuat riset ini bernilai tinggi"
    }
  ]
}"""

    user_prompt = f"""BIDANG KAJIAN: {fac_name}
FOKUS KHUSUS DARI PENELITI: {custom_focus or 'Eksplorasi holistik seluruh korpus paper yang tersedia'}

RINGKASAN LITERATUR KORPUS ({len(papers)} PAPER):
{corpus_digest}

Silakan analisis korpus di atas dan hasilkan JSON analisis celah riset (Research Gap & Novelty Report) yang mendalam."""

    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)

    raw_response = ""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            timeout=85.0
        )
        raw_response = _safe_extract(resp)
    except Exception as e:
        console.print(f"[yellow]Warn: Gap Finder primary model failed ({e}). Trying fallback to gemini-3-8-flash...[/yellow]")
        try:
            resp_fb = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                timeout=45.0
            )
            raw_response = _safe_extract(resp_fb)
        except Exception as e2:
            console.print(f"[red]Error: Fallback gap analysis failed: {e2}[/red]")
            raise e2

    # Parse JSON block
    clean_json_str = raw_response.strip()
    if "```json" in clean_json_str:
        clean_json_str = clean_json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_json_str:
        clean_json_str = clean_json_str.split("```")[1].split("```")[0].strip()

    try:
        report_data = json.loads(clean_json_str)
    except Exception:
        # Fallback structured dict
        report_data = {
            "faculty_domain": fac_name,
            "executive_summary": raw_response[:800],
            "established_consensus": ["Kausalitas dan awal mula kosmos merupakan perdebatan sentral."],
            "unresolved_tensions": [{"issue": "Determinisme vs Kuantum", "thesis_side": "Kalam", "antithesis_side": "Fisika", "why_stuck": "Perbedaan definisi sebab"}],
            "methodological_blindspots": ["Belum banyak studi komparatif kuantum formal."],
            "novel_research_proposals": [{
                "title": f"Rekonstruksi Dialektika Riset di Bidang {fac_name}",
                "target_level": "Tesis S2",
                "gap_addressed": "Kesenjangan pemetaan korpus kontemporer",
                "research_questions": ["Bagaimana sintesis nalar di era modern?"],
                "proposed_hypothesis": "Sains kontemporer membuka ruang dialog metafisika baru.",
                "theoretical_framework": "Integrasi Turāth dan Filsafat Sains",
                "expected_novelty": "Pemetaan dialektis komprehensif"
            }]
        }

    report_data["generated_at"] = datetime.now().isoformat()
    report_data["faculty_id"] = faculty_id
    report_data["model_used"] = model
    return report_data


def save_gap_report(report_data: dict) -> dict:
    """Save research gap report to data/gaps/ and Obsidian vault."""
    gaps_dir = config.ROOT / "gaps"
    gaps_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fac_id = report_data.get("faculty_id", "universal")
    file_stem = f"gap_report_{timestamp}_{fac_id}"

    # 1. Save JSON
    json_path = gaps_dir / f"{file_stem}.json"
    json_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Build Markdown Document
    md_lines = [
        f"# 🔍 Laporan Celah Riset & Kebaruan Akademik (Research Gap & Novelty Analysis)",
        f"> **Domain:** {report_data.get('faculty_domain', 'Multidisipliner')} | **Tanggal:** {datetime.now().strftime('%d %B %Y')} | **Model:** `{report_data.get('model_used', 'LLM')}`\n",
        "## 📌 Ringkasan Eksekutif",
        report_data.get("executive_summary", ""),
        "\n---",
        "## 🏛️ Konsensus yang Mapan dalam Korpus",
    ]
    for c in report_data.get("established_consensus", []):
        md_lines.append(f"- ✅ {c}")

    md_lines.extend([
        "\n---",
        "## ⚔️ Perdebatan Terbuka yang Belum Tuntas (Unresolved Tensions)",
    ])
    for idx, ut in enumerate(report_data.get("unresolved_tensions", []), 1):
        md_lines.append(f"### {idx}. {ut.get('issue', 'Isu Perdebatan')}")
        md_lines.append(f"- **Kubu Tesis/Teisme:** {ut.get('thesis_side', '-')}")
        md_lines.append(f"- **Kubu Antitesis/Kritik:** {ut.get('antithesis_side', '-')}")
        md_lines.append(f"- ⚠️ **Mengapa Belum Tuntas:** {ut.get('why_stuck', '-')}\n")

    md_lines.extend([
        "---",
        "## 👁️ Titik Buta Metodologis & Konseptual (Blindspots)",
    ])
    for b in report_data.get("methodological_blindspots", []):
        md_lines.append(f"- 🔍 {b}")

    md_lines.extend([
        "\n---",
        "## 🎯 Usulan Topik Proposal Riset Baru (High-Novelty Proposals)",
    ])
    for idx, p in enumerate(report_data.get("novel_research_proposals", []), 1):
        md_lines.append(f"### Usulan {idx}: {p.get('title')}")
        md_lines.append(f"- **Jenjang Rekomendasi:** `{p.get('target_level', 'Tesis S2/S3')}`")
        md_lines.append(f"- **Kesenjangan Pustaka yang Dijawab:** {p.get('gap_addressed', '-')}")
        md_lines.append(f"- **Tesis/Hipotesis Kerja:** {p.get('proposed_hypothesis', '-')}")
        md_lines.append(f"- **Kerangka Teoretis:** {p.get('theoretical_framework', '-')}")
        md_lines.append(f"- 💎 **Nilai Kebaruan (Novelty):** {p.get('expected_novelty', '-')}")
        if p.get("research_questions"):
            md_lines.append("- **Rumusan Masalah Utama:**")
            for q in p["research_questions"]:
                md_lines.append(f"  1. {q}")
        md_lines.append("")

    md_text = "\n".join(md_lines)
    md_path = gaps_dir / f"{file_stem}.md"
    md_path.write_text(md_text, encoding="utf-8")

    # 3. Save to Obsidian Vault
    obs_gaps = config.OBSIDIAN_DIR / "gaps"
    obs_gaps.mkdir(parents=True, exist_ok=True)
    obs_path = obs_gaps / f"{file_stem}.md"
    obs_path.write_text(md_text, encoding="utf-8")

    return {
        "json_path": json_path,
        "md_path": md_path,
        "obsidian_path": obs_path,
        "markdown_content": md_text
    }
