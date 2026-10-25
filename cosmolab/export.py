import json
import re
from pathlib import Path
from rich.console import Console
from . import config
from . import db

console = Console(force_terminal=True, legacy_windows=False)


def _safe_cite_key(title: str, year: str) -> str:
    """Generate a clean BibTeX citation key."""
    clean_title = re.sub(r"[^\w]", "", title.title())[:20]
    return f"{clean_title}{year or 'nd'}"


def export_bibtex(out_path: Path | None = None) -> Path:
    """Export all harvested papers to a BibTeX (.bib) file."""
    config.ensure_dirs()
    out_path = out_path or (config.ROOT / "references.bib")
    papers = db.get_all_papers_with_analyses()

    entries = []
    for p in papers:
        title = p.get("title") or "Untitled"
        year = p.get("year") or ""
        doi = p.get("doi") or ""
        url = p.get("url") or ""
        arxiv_id = p.get("arxiv_id") or ""
        cite_key = _safe_cite_key(title, year)

        entry_type = "article"
        fields = [f"  title = {{{title}}}"]
        if year:
            fields.append(f"  year = {{{year}}}")
        if doi:
            fields.append(f"  doi = {{{doi}}}")
        if url:
            fields.append(f"  url = {{{url}}}")
        if arxiv_id:
            fields.append(f"  eprint = {{{arxiv_id}}}")
            fields.append("  archivePrefix = {arXiv}")

        entry_str = f"@{entry_type}{{{cite_key},\n" + ",\n".join(fields) + "\n}"
        entries.append(entry_str)

    out_path.write_text("\n\n".join(entries), encoding="utf-8")
    console.print(f"[green]OK  BibTeX exported to: {out_path}[/green] ({len(papers)} entries)")
    return out_path


def export_obsidian(vault_dir: Path | None = None) -> Path:
    """Export research corpus to an Obsidian-ready markdown vault."""
    config.ensure_dirs()
    vault = vault_dir or config.OBSIDIAN_DIR
    vault.mkdir(parents=True, exist_ok=True)

    papers = db.get_all_papers_with_analyses()
    index_rows = ["| Paper Note | Year | Type | Stance | Key Objection |",
                  "|---|---|---|---|---|"]

    for p in papers:
        title = p.get("title") or "Untitled"
        year = p.get("year") or "n.d."
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:80].strip()
        note_name = f"{year} - {safe_title}.md"
        note_file = vault / note_name
        link_name = f"{year} - {safe_title}"

        arg_type = p.get("argument_type") or "unclassified"
        stance = p.get("supports_or_critiques") or "neutral"
        thesis = p.get("thesis") or "Tidak dinyatakan secara eksplisit."
        conclusion = p.get("conclusion") or "-"
        key_obj = p.get("key_objection") or "-"
        key_def = p.get("key_defense") or "-"

        # Parse JSON fields
        premises = []
        if p.get("premises_json"):
            try:
                premises = json.loads(p["premises_json"])
            except Exception:
                pass

        concepts = []
        if p.get("notable_concepts_json"):
            try:
                concepts = json.loads(p["notable_concepts_json"])
            except Exception:
                pass

        quotes = []
        if p.get("quotes_json"):
            try:
                quotes = json.loads(p["quotes_json"])
            except Exception:
                pass

        tags = ["research", "cosmology", f"arg/{arg_type}", f"stance/{stance}"]
        for c in concepts[:4]:
            tag_clean = re.sub(r"[^\w]", "_", c.lower()).strip("_")
            if tag_clean:
                tags.append(f"concept/{tag_clean}")

        # Build Markdown content
        premises_md = "\n".join(f"- {prem}" for prem in premises) if premises else "- Belum dianalisis."
        quotes_md = ""
        if quotes:
            quotes_md = "\n\n### Kutipan Kunci\n" + "\n\n".join(
                f"> \"{q.get('text', '')}\"\n> — *Halaman: {q.get('page_hint', 'N/A')}*" for q in quotes
            )

        content = f"""---
title: "{title}"
year: {year}
doi: "{p.get('doi') or ''}"
arxiv_id: "{p.get('arxiv_id') or ''}"
argument_type: "{arg_type}"
stance: "{stance}"
tags: [{', '.join(tags)}]
---

# {title}

[[_Index|⬅ Kembali ke Indeks Corpus]]

## Metadata
- **Tahun**: {year}
- **Tipe Argumen**: `{arg_type}`
- **Posisi/Stance**: `{stance}`
- **DOI**: {p.get('doi') or 'N/A'}
- **Source**: {p.get('source') or 'N/A'}

---

## 🎯 Tesis Utama
> {thesis}

## 📐 Rekonstruksi Premis & Kesimpulan
{premises_md}

**Kesimpulan**:
> {conclusion}

---

## ⚔️ Objeksi & Tanggapan
- **Objeksi Terkuat**: {key_obj}
- **Tanggapan/Pertahanan**: {key_def}
{quotes_md}

---
*Dianalisis secara otomatis oleh Cosmolab Pipeline.*
"""
        note_file.write_text(content, encoding="utf-8")

        # Add to index table
        clean_obj = key_obj[:60].replace("|", "/")
        index_rows.append(f"| [[{link_name}]] | {year} | {arg_type} | {stance} | {clean_obj} |")

    # Generate _Index.md
    index_content = f"""---
title: "Cosmological Argument Research Corpus"
tags: [index, cosmology, corpus]
---

# 🌌 Indeks Corpus Argumen Kosmologis

Total Paper Terindeks: **{len(papers)}**

## Peta Komparatif

{chr(10).join(index_rows)}

---
*Vault dibuat otomatis oleh Cosmolab.*
"""
    (vault / "_Index.md").write_text(index_content, encoding="utf-8")
    console.print(f"[green]OK  Obsidian Vault generated at: {vault}[/green] ({len(papers)} notes)")
    return vault


def generate_mermaid_graph(file_stem: str) -> str:
    """Generate a Mermaid flowchart diagram for a given paper analysis."""
    p_data = None
    for p in db.get_all_papers_with_analyses():
        if file_stem.lower() in p["file"].lower():
            p_data = p
            break

    if not p_data or not p_data.get("thesis"):
        return "graph TD\n  None[Tidak ada analisis untuk paper ini]"

    title = (p_data.get("title") or file_stem)[:45].replace('"', "'")
    thesis = (p_data.get("thesis") or "")[:60].replace('"', "'")
    conclusion = (p_data.get("conclusion") or "Kesimpulan")[:60].replace('"', "'")
    objection = (p_data.get("key_objection") or "Objeksi")[:60].replace('"', "'")
    defense = (p_data.get("key_defense") or "Tanggapan")[:60].replace('"', "'")

    premises = []
    if p_data.get("premises_json"):
        try:
            premises = json.loads(p_data["premises_json"])
        except Exception:
            pass

    lines = ["graph TD", f'  Paper["{title}"] --> Thesis["Tesis: {thesis}"]']
    for idx, prem in enumerate(premises[:5], start=1):
        clean_prem = prem[:50].replace('"', "'")
        lines.append(f'  P{idx}["Premis {idx}: {clean_prem}"] --> Conclusion["Kesimpulan: {conclusion}"]')
        lines.append(f'  Thesis --> P{idx}')

    if objection and objection != "-":
        lines.append(f'  Objection["[!] Objeksi: {objection}"] -.->|Kritik| Conclusion')
        if defense and defense != "-":
            lines.append(f'  Defense["[*] Tanggapan: {defense}"] -->|Menjawab| Objection')

    return "\n".join(lines)
