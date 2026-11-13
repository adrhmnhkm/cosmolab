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

    matrix = []
    for idx, p in enumerate(papers, 1):
        p_fac_id = p.get("faculty") or "ilahiyyat"
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
        "No",
        "Penulis",
        "Tahun",
        "Judul Paper",
        "Fakultas",
        "Sikap (Stance)",
        "Tipe Argumen",
        "Tesis Utama",
        "Rekonstruksi Premis",
        "Kesimpulan Logis",
        "Objeksi Terkuat",
        "Pertahanan Penulis",
        "Sitasi APA",
        "DOI",
        "Tautan PDF"
    ]

    with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in matrix:
            writer.writerow([
                r["no"],
                r["author"],
                r["year"],
                r["title"],
                r["faculty"],
                r["stance"],
                r["argument_type"],
                r["thesis"],
                r["premises"],
                r["conclusion"],
                r["key_objection"],
                r["key_defense"],
                r["citation_apa"],
                r["doi"],
                r["url"]
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

    md_lines = [
        f"# 📊 Matriks Sintesis Literatur (State of the Art Mapping)",
        f"> *Dihasilkan secara otomatis oleh CosmoLab University Dialectical Engine pada {datetime.now().strftime('%d %B %Y')}*\n",
        f"Total Literatur Dianalisis: **{len(matrix)} paper**\n",
        "| No | Penulis & Tahun | Judul Paper | Fakultas | Sikap | Tesis Utama | Premis Inti | Objeksi Terkuat |",
        "|---|---|---|---|---|---|---|---|"
    ]

    for r in matrix:
        safe_title = r['title'].replace("|", "/")
        safe_thesis = r['thesis'].replace("|", "/").replace("\n", " ")[:150] + "..." if len(r['thesis']) > 150 else r['thesis']
        safe_prems = r['premises'].replace("|", "/").replace("\n", " ")[:120] + "..." if len(r['premises']) > 120 else r['premises']
        safe_obj = r['key_objection'].replace("|", "/").replace("\n", " ")[:120] + "..." if len(r['key_objection']) > 120 else r['key_objection']
        
        md_lines.append(
            f"| {r['no']} | {r['author']} ({r['year']}) | **{safe_title}** | {r['faculty']} | {r['stance']} | {safe_thesis} | {safe_prems} | {safe_obj} |"
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

