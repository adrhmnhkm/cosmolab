"""
CosmoLab University: Literature Review Matrix Generator (Matriks Sintesis Literatur)
Compiles peer-reviewed corpus research into professional comparative matrices
for state-of-the-art mapping, thesis defense prep, and academic journal publishing.
"""

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from . import config
from . import db
from . import faculties as _faculties
from . import citations
from . import position as _position

# Same keys as analyze.LIT_FIELDS (not imported: analyze pulls in the LLM client).
LIT_KEYS = ("research_question", "sample_data", "limitations", "future_research")


def build_literature_matrix(faculty_id: str = "all") -> list[dict]:
    """
    Extract structured comparative analysis matrix for all papers
    or papers within a specific academic faculty.
    """
    all_papers = db.get_all_papers_with_analyses()
    if faculty_id != "all":
        papers = [p for p in all_papers if p.get("faculty") == faculty_id]
    else:
        papers = all_papers

    positions = _position.load_positions()
    matrix = []
    for idx, p in enumerate(papers, 1):
        p_fac_id = p.get("faculty") or "umum"
        fac_obj = _faculties.get_faculty(p_fac_id)
        fac_label = f"{fac_obj.icon} {fac_obj.name}" if fac_obj else p_fac_id.title()

        # Parse premises into a clean single string
        premises_text = "-"
        if p.get("premises_json"):
            try:
                prems = json.loads(p["premises_json"])
                if prems:
                    premises_text = " | ".join(f"P{i}: {prem}" for i, prem in enumerate(prems, 1))
            except Exception:
                pass

        # Formatting stance label
        stance_raw = p.get("supports_or_critiques") or "neutral"
        stance_map = {
            "supports": "🟢 Mendukung",
            "critiques": "🔴 Mengkritik",
            "mixed": "🟡 Campuran",
            "neutral": "⚪ Netral",
        }
        stance_str = stance_map.get(stance_raw, stance_raw.title())

        try:
            raw = json.loads(p.get("raw_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            raw = {}

        def _joined(key):
            items = [x for x in (raw.get(key) or []) if isinstance(x, str) and x.strip()]
            return " | ".join(items) if items else "-"

        apa_cite = citations.format_apa(p)
        in_text = citations.format_in_text_apa(p)

        row = {
            "no": idx,
            "title": p.get("title") or "Untitled",
            "year": str(p.get("year") or "n.d."),
            "author": citations._infer_author(p),
            "faculty": fac_label,
            "faculty_id": p_fac_id,
            "argument_type": (p.get("argument_type") or "-").title(),
            "stance": stance_str,
            "stance_raw": stance_raw,
            "thesis": p.get("thesis") or "Tidak dinyatakan eksplisit",
            "premises": premises_text,
            "conclusion": p.get("conclusion") or "-",
            "research_question": raw.get("research_question") or "-",
            "method": raw.get("research_method") or "-",
            "sample": raw.get("sample_data") or "-",
            "findings": _joined("key_findings"),
            "limitations": _joined("limitations"),
            "future_research": _joined("future_research"),
            "position": _position.LABELS.get((positions.get(p.get("file") or "") or {}).get("position"), "-"),
            "position_reason": (positions.get(p.get("file") or "") or {}).get("reason") or "-",
            "analyzed": bool(p.get("thesis")),
            "old_analysis": bool(p.get("thesis")) and not all(k in raw for k in LIT_KEYS),
            "key_objection": p.get("key_objection") or "-",
            "key_defense": p.get("key_defense") or "-",
            "doi": p.get("doi") or "",
            "url": p.get("url") or "",
            "file": p.get("file") or "",
            "citation_apa": apa_cite,
            "in_text": in_text,
        }
        matrix.append(row)

    return matrix


def export_matrix_csv(matrix: list[dict], out_path: Path | None = None) -> Path:
    """
    Export matrix to Excel-compatible CSV file using UTF-8-SIG encoding.
    """
    matrix_dir = config.ROOT / "matrices"
    matrix_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_path or (matrix_dir / f"matriks_sintesis_literatur_{timestamp}.csv")

    headers = [
        "No", "Penulis", "Tahun", "Judul", "Bidang", "Jenis penelitian",
        "Tujuan riset", "Metode", "Sampel dan data", "Temuan", "Keterbatasan", "Saran riset lanjutan",
        "Posisi terhadap pertanyaan riset", "Alasan posisi", "Kesimpulan", "Inti paper", "Premis", "Keberatan", "Pembelaan",
        "Sitasi APA", "DOI", "Tautan",
    ]

    with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in matrix:
            writer.writerow([
                r["no"], r["author"], r["year"], r["title"], r["faculty"], r["argument_type"],
                r["research_question"], r["method"], r["sample"], r["findings"], r["limitations"], r["future_research"],
                r["position"], r["position_reason"], r["conclusion"], r["thesis"], r["premises"], r["key_objection"], r["key_defense"],
                r["citation_apa"], r["doi"], r["url"],
            ])

    return out_path


def export_matrix_markdown(matrix: list[dict], out_path: Path | None = None) -> Path:
    """
    Export matrix as a clean GFM Markdown document ready for Obsidian / Notion.
    """
    matrix_dir = config.ROOT / "matrices"
    matrix_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_path or (matrix_dir / f"matriks_sintesis_literatur_{timestamp}.md")

    def cell(text: str, limit: int = 160) -> str:
        text = str(text or "-").replace("|", "/").replace("\n", " ")
        return text if len(text) <= limit else text[:limit] + "..."

    md_lines = [
        "# Matriks Literatur",
        f"Dibuat CosmoLab pada {datetime.now().strftime('%d %B %Y')}. Jumlah paper: **{len(matrix)}**.\n",
        "| No | Penulis & Tahun | Judul | Tujuan riset | Metode | Sampel dan data | Temuan | Keterbatasan |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in matrix:
        md_lines.append(
            f"| {r['no']} | {cell(r['author'], 60)} ({r['year']}) | **{cell(r['title'], 120)}** | {cell(r['research_question'])} "
            f"| {cell(r['method'], 80)} | {cell(r['sample'], 120)} | {cell(r['findings'], 200)} | {cell(r['limitations'])} |"
        )

    out_path.write_text("\n".join(md_lines), encoding="utf-8")
    return out_path


def export_matrix_obsidian(matrix: list[dict], faculty_name: str = "Semua Fakultas") -> Path:
    """Export matrix directly to the Obsidian Vault under `matrices/`."""
    obs_dir = config.OBSIDIAN_DIR / "matrices"
    obs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_fac = re.sub(r"[^\w]", "_", faculty_name)
    out_path = obs_dir / f"Matriks_Sintesis_{safe_fac}_{timestamp}.md"

    md_content = export_matrix_markdown(matrix, out_path)
    return out_path


def calculate_recency_compliance(matrix: list[dict], threshold_years: int = 5) -> dict:
    """
    Audit literature recency against university thesis / Scopus standard (5-Year Rule).
    Standard guideline: at least 75-80% of secondary literature must be from the last 5 years.
    """
    current_year = datetime.now().year
    cutoff_year = current_year - threshold_years

    total = len(matrix)
    if total == 0:
        return {
            "total": 0,
            "recent_count": 0,
            "cutoff_year": cutoff_year,
            "percentage": 0.0,
            "turath_count": 0,
            "compliant": False,
            "status_label": "⚪ Belum Ada Literatur",
            "message": "Belum ada paper yang dianalisis di fakultas ini."
        }

    recent_count = 0
    turath_count = 0

    for r in matrix:
        try:
            yr_int = int(r.get("year", 0))
            if yr_int >= cutoff_year:
                recent_count += 1
            elif yr_int < 1960:
                turath_count += 1
        except Exception:
            pass

    pct = round((recent_count / total) * 100, 1)
    is_compliant = pct >= 75.0

    if is_compliant:
        status_label = f"🟢 Lulus Standar Kebaruan ({pct}% Terbit {cutoff_year}–{current_year})"
        msg = f"Korpus memenuhi standar ketat Dikti, akreditasi SINTA, dan jurnal bereputasi (minimal 75-80% terbit dalam 5 tahun terakhir)."
    elif pct >= 50.0:
        status_label = f"🟡 Pustaka Campuran Moderat ({pct}% Terbit {cutoff_year}–{current_year})"
        msg = f"Tersedia {recent_count} paper kontemporer dan beberapa naskah seminal/klasik. Disarankan menambah 2–4 paper terbitan {cutoff_year}+ untuk proposal S3/Scopus."
    else:
        status_label = f"🟠 Dominan Pustaka Klasik / Historis ({pct}% Terbit {cutoff_year}–{current_year})"
        msg = f"Korpus ini kaya akan sumber klasik/historis. Gunakan menu 'Cari & tambah paper' untuk memperkaya rujukan jurnal mutakhir (5 tahun terakhir)."

    return {
        "total": total,
        "recent_count": recent_count,
        "cutoff_year": cutoff_year,
        "percentage": pct,
        "turath_count": turath_count,
        "compliant": is_compliant,
        "status_label": status_label,
        "message": msg
    }

