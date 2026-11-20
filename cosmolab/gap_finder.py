"""
CosmoLab University: Research Gap & Novelty Finder Engine (Pendeteksi Celah Riset)
Identifies unaddressed dialectical tensions, methodological blindspots, and
generates high-novelty research proposals for S2/S3 theses and peer-reviewed journals.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from rich.console import Console
from . import config
from . import llm as _llm
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
    if fac_obj:
        fac_name = fac_obj.name
    else:
        fac_counts = {}
        for p in papers:
            f_id = p.get("faculty")
            if f_id and f_id not in ("all", "umum", "universal", None):
                fac_counts[f_id] = fac_counts.get(f_id, 0) + 1
        if fac_counts:
            top_f = max(fac_counts, key=fac_counts.get)
            top_obj = _faculties.get_faculty(top_f)
            fac_name = top_obj.name if top_obj else "Sains & Teknologi"
        else:
            fac_name = "Kajian Interdisipliner"

    # Compile structured corpus digest
    corpus_items = []
    for p in papers[:20]:
        title = p.get("title") or "Untitled"
        year = p.get("year") or "n.d."
        thesis = p.get("thesis") or "Tidak ada data tesis"
        try:
            raw = json.loads(p.get("raw_json") or "{}")
        except (TypeError, ValueError):
            raw = {}
        lines = [f"- [{year}] {title}", f"  Tesis: {thesis}"]
        for label, key in (("Tujuan", "research_question"), ("Metode", "research_method"), ("Sampel/data", "sample_data")):
            if raw.get(key):
                lines.append(f"  {label}: {raw[key]}")
        # What authors admit is missing is the best evidence of a research gap.
        for label, key in (("Temuan", "key_findings"), ("Keterbatasan", "limitations"),
                           ("Saran riset lanjutan", "future_research")):
            items = [x for x in (raw.get(key) or []) if isinstance(x, str) and x.strip()]
            if items:
                lines.append(f"  {label}: " + "; ".join(items))
        if p.get("key_objection"):
            lines.append(f"  Keberatan: {p['key_objection']}")
        if p.get("key_defense"):
            lines.append(f"  Tanggapan: {p['key_defense']}")
        corpus_items.append("\n".join(lines))

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
      "thesis_side": "Argumen kubu teori dominan / paradigma konvensional...",
      "antithesis_side": "Argumen kubu kritik / temuan empiris baru...",
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
      "theoretical_framework": "Landasan teori atau kerangka konseptual yang digunakan",
      "expected_novelty": "Nilai kebaruan akademik (novelty) yang membuat riset ini bernilai tinggi"
    }
  ]
}"""

    user_prompt = f"""BIDANG KAJIAN: {fac_name}
FOKUS KHUSUS DARI PENELITI: {custom_focus or 'Eksplorasi holistik seluruh korpus paper yang tersedia'}

RINGKASAN LITERATUR KORPUS ({len(papers)} PAPER):
{corpus_digest}

Silakan analisis korpus di atas dan hasilkan JSON analisis celah riset (Research Gap & Novelty Report) yang mendalam."""

    raw_response = _llm.chat_text(system_prompt, user_prompt, model=model, temperature=0.2, timeout=240.0,
                                  label="Cari celah riset", json_mode=True)

    from .analyze import _parse_response
    try:
        report_data = _parse_response(raw_response)
        if not report_data.get("novel_research_proposals"):
            raise ValueError("Tidak ada usulan proposal dalam jawaban model")
        if not report_data.get("faculty_domain"):
            report_data["faculty_domain"] = fac_name
    except Exception as e:
        console.print(f"[yellow]Peringatan: Gagal membaca JSON celah riset ({e}), menggunakan struktur pemulihan.[/yellow]")
        report_data = {
            "faculty_domain": fac_name,
            "executive_summary": raw_response[:1200] if raw_response else f"Ringkasan tinjauan literatur dan analisis kesenjangan riset pada bidang {fac_name}.",
            "established_consensus": [f"Konsensus primer dan kerangka kerja konseptual yang diakui dalam literatur {fac_name}."],
            "unresolved_tensions": [{
                "issue": f"Perdebatan Paradigma Metodologis ({fac_name})",
                "thesis_side": "Pendekatan Konvensional / Arsitektur Eksisting",
                "antithesis_side": "Kritik Terhadap Batasan Skalabilitas & Efisiensi",
                "why_stuck": "Perbedaan evaluasi eksperimental, variasi dataset, dan kompleksitas komputasi.",
            }],
            "methodological_blindspots": [f"Keterbatasan evaluasi berskala besar dan minimnya pengujian komparatif lintas arsitektur pada riset {fac_name}."],
            "novel_research_proposals": [{
                "title": f"Pengembangan Kerangka Kerja Adaptif di Bidang {fac_name}",
                "target_level": "Tesis S2 / Disertasi S3",
                "gap_addressed": f"Kesenjangan metodologis dan skalabilitas pada literatur {fac_name}",
                "research_questions": [f"Bagaimana efektivitas dan skalabilitas kerangka kerja baru ini dibandingkan metode dasar?"],
                "proposed_hypothesis": "Pendekatan adaptif terintegrasi mampu meningkatkan retensi pengetahuan tanpa degradasi performa.",
                "theoretical_framework": f"Kerangka Konseptual & Teori Kontemporer {fac_name}",
                "expected_novelty": "Peningkatan kebaruan metodologis dan resolusi kesenjangan komputasi empiris",
            }]
        }

    report_data["generated_at"] = datetime.now().isoformat()
    report_data["faculty_id"] = faculty_id
    report_data["model_used"] = model
    return report_data


def _clean_text(s: str) -> str:
    """Remove AI emoji markers and leading symbols if present."""
    if not s:
        return ""
    return re.sub(r"^[🔍📌🏛️✅⚔️⚠️👁️🎯💎\s\-•]+", "", str(s)).strip()


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

    domain = report_data.get("faculty_domain") or "Kajian Interdisipliner"
    today_str = datetime.now().strftime("%d %B %Y")

    # 2. Build Publication-Grade Markdown Document (Firm-Grade Executive Format)
    md_lines = [
        f"# Laporan Telaah Kritis & Celah Riset Akademik: {domain}",
        f"> **Bidang Kajian:** {domain}  \n> **Tanggal Telaah:** {today_str}  \n> **Penyusun:** CosmoLab Research Analytics  \n> **Klasifikasi:** Laporan Telaah Strategis (Executive Advisory)\n",
        "## 1. Ringkasan Eksekutif",
        report_data.get("executive_summary", "").strip(),
        "",
        "## 2. Landasan Konsensus Literatur Ilmiah",
        "Berikut adalah proposisi dan temuan yang telah mencapai konsensus mapan dalam korpus literatur yang dianalisis:",
        "",
    ]
    for idx, c in enumerate(report_data.get("established_consensus", []), 1):
        clean_c = _clean_text(c)
        if clean_c:
            md_lines.append(f"{idx}. {clean_c}")

    md_lines.extend([
        "",
        "## 3. Matriks Perdebatan & Ketegangan Teoretis",
        "Pemetaan kontroversi dan silang pendapat terbuka yang belum mencapai konsensus definitif antar-peneliti:",
        "",
    ])
    for idx, ut in enumerate(report_data.get("unresolved_tensions", []), 1):
        issue_title = _clean_text(ut.get("issue", "Isu Perdebatan"))
        md_lines.append(f"### 3.{idx}. {issue_title}")
        md_lines.append(f"- **Kubu Paradigma Dominan (Tesis):** {_clean_text(ut.get('thesis_side', '-'))}")
        md_lines.append(f"- **Kubu Kritik & Temuan Baru (Antitesis):** {_clean_text(ut.get('antithesis_side', '-'))}")
        md_lines.append(f"- **Analisis Hambatan Resolusi:** {_clean_text(ut.get('why_stuck', '-'))}\n")

    md_lines.extend([
        "## 4. Evaluasi Titik Buta Metodologis & Konseptual",
        "Keterbatasan epistemik dan area kritis yang terabaikan dalam rancangan penelitian literatur terdahulu:",
        "",
    ])
    for idx, b in enumerate(report_data.get("methodological_blindspots", []), 1):
        clean_b = _clean_text(b)
        m_blind = re.match(r"^(?:Titik\s+buta\s+\d+\s*[-—:]\s*)(.*)", clean_b, re.IGNORECASE)
        if m_blind:
            clean_b = m_blind.group(1).strip()
        if clean_b:
            md_lines.append(f"{idx}. {clean_b}")

    md_lines.extend([
        "",
        "## 5. Cetak Biru Usulan Penelitian Lanjutan (High-Novelty Research Blueprints)",
        "Spesifikasi usulan topik riset baru dengan nilai kebaruan tinggi yang dirancang khusus untuk jenjang Tesis S2, Disertasi S3, atau artikel jurnal ilmiah bereputasi internasional:",
        "",
    ])
    for idx, p in enumerate(report_data.get("novel_research_proposals", []), 1):
        p_title = _clean_text(p.get("title", f"Proposal Riset {idx}"))
        target_lvl = _clean_text(p.get("target_level", "Tesis S2 / Disertasi S3"))
        gap_addr = _clean_text(p.get("gap_addressed", "-"))
        hypo = _clean_text(p.get("proposed_hypothesis", "-"))
        theory = _clean_text(p.get("theoretical_framework", "-"))
        novelty = _clean_text(p.get("expected_novelty", "-"))

        md_lines.append(f"### 5.{idx}. {p_title}\n")
        md_lines.append("| Komponen Desain Riset | Deskripsi Rencana Penelitian |")
        md_lines.append("| :--- | :--- |")
        md_lines.append(f"| **Target Jenjang & Luaran** | {target_lvl} |")
        md_lines.append(f"| **Kesenjangan Pustaka Inti (*Gap*)** | {gap_addr} |")
        md_lines.append(f"| **Tesis / Hipotesis Kerja** | {hypo} |")
        md_lines.append(f"| **Kerangka Teoretis Acuan** | {theory} |")
        md_lines.append(f"| **Signifikansi Kebaruan (*Novelty Claim*)** | {novelty} |")
        md_lines.append("")

        rqs = p.get("research_questions") or []
        if rqs:
            md_lines.append("**Rumusan Masalah Utama (*Research Questions*):**")
            for q_idx, q in enumerate(rqs, 1):
                md_lines.append(f"{q_idx}. {_clean_text(q)}")
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
