"""
CosmoLab University: Publication-Ready Article & Essayist Engine (Studio Penulis)
Transforms corpus research, dialectical matrices, and philosophical inquiries into
elegantly written, publication-ready long-form articles, essays, and standalone HTML/PDF documents.
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

ARTICLE_STYLES = {
    "essay": {
        "id": "essay",
        "name": "📰 Esai Intelektual Terbuka (Populer & Mengalir)",
        "desc": "Naratif memikat, jelas, minim jargon rumit. Istilah teknis selalu diterangkan dengan bahasa sederhana dan analogi sehari-hari. Sangat ramah bagi pembaca umum, pelajar, dan mahasiswa.",
        "prompt_instructions": """
GAYA PENULISAN: Esai Intelektual Terbuka (Ramah Pembaca Umum, Pelajar, dan Mahasiswa Lintas Disiplin).
PRINSIP KEJERNIHAN BAHASA (PENTING):
1. **Utamakan Bahasa Indonesia yang Terang & Alami:**
   - Pilih padanan bahasa Indonesia sehari-hari untuk istilah teknis bidang apa pun (contoh: "hubungan sebab-akibat" daripada "kausalitas", "kekeliruan cara berpikir" daripada "ilusi kognitif").
   - Hindari istilah serapan yang kaku bila ada kata Indonesia yang lebih jelas.

2. **Aturan Istilah Khusus (First Appearance Rule):**
   - Jika istilah khusus suatu bidang (istilah Arab klasik, hukum, ekonomi, medis, sains, dll.) perlu dimunculkan, WAJIB berikan penjelasan bahasa Indonesia sederhana di dalam kurung pada kemunculan pertama.
   - Pada kalimat dan paragraf berikutnya, GUNAKAN padanan bahasa Indonesianya agar pembaca tidak terbebani menghafal istilah asing berulang kali.

3. **Dilarang Menumpuk Istilah Abstrak:**
   - Jangan menumpuk lebih dari 2 istilah teknis dalam satu kalimat. Pecah menjadi kalimat-kalimat yang lugas dan bernapas lega.
   - Selalu hadirkan contoh konkret atau analogi sehari-hari yang dekat dengan pengalaman pembaca SEBELUM masuk ke kesimpulan teoretis.

4. **Fokus & Pangkas Jargon yang Tidak Relevan:**
   - Jangan memasukkan detail teknis dari bidang lain yang tidak menopang tesis utama. Fokuskan pada inti gagasan.

STRUKTUR ARTIKEL:
1. **Judul Utama & Subjudul yang Jernih**: Menggugah rasa ingin tahu dengan bahasa komunikatif.
2. **Pembuka yang Bersahabat**: Mengawali dengan analogi pengalaman sehari-hari.
3. **Penyelaman Masalah**: Mengurai pokok masalah dan mengapa ia penting.
4. **Dialog Pemikiran & Temuan**: Membahas pandangan para tokoh dan temuan riset secara proporsional dan mudah dipahami.
5. **Renungan Penutup (Epilog)**: Memberi sudut pandang segar dan reflektif tanpa hiperbola.
6. **Daftar Rujukan Terpilih**: Format sitasi ringkas dan rapi.
""",
    },
    "journal_review": {
        "id": "journal_review",
        "name": "🎓 Tinjauan Akademik Jurnal (Peer-Reviewed Paper Style)",
        "desc": "Format akademik formal berstandar jurnal ilmiah bereputasi. Terstruktur dengan Abstrak, Rekonstruksi Argumen, Analisis Kritis, dan Bibliografi.",
        "prompt_instructions": """
GAYA PENULISAN: Review Akademis Standar Jurnal Ilmiah Bereputasi (ikuti konvensi bidangnya: humaniora, sosial, hukum, sains, atau kesehatan).
STRUKTUR ARTIKEL:
1. **Judul Akademis & Abstrak**: Abstrak bilingual/Indonesia (~150 kata) mencakup latar belakang, tesis utama, dan temuan komparatif.
2. **Pendahuluan & Status Quaestionis**: Pemetaan literatur mutakhir mengenai problematika ini.
3. **Rekonstruksi Argumen & Bukti**: Membedah klaim, premis, dan bukti dari masing-masing posisi dengan sitasi eksplisit format (Penulis, Tahun).
4. **Analisis Dialektika & Evaluasi Objeksi**: Menimbang kekuatan argumen kontra dan tanggapan pembela.
5. **Kesimpulan & Rekomendasi Riset**: Posisi sintesis orisinal dan pertanyaan terbuka untuk riset masa depan.
6. **Daftar Pustaka (References)**: Sitasi lengkap berstandar Chicago/APA.
Panjang: Ketat, metodologis, objektif, dan bernas.
""",
    },
    "monograph": {
        "id": "monograph",
        "name": "📖 Monograf / Bab Buku Tematik (Book Chapter Style)",
        "desc": "Kajian tematik ensiklopedis yang mendalam: mengupas akar sejarah gagasan, pergeseran makna, hingga perdebatan mutakhir.",
        "prompt_instructions": """
GAYA PENULISAN: Bab Buku / Monograf Tematik (ikuti tradisi keilmuan bidangnya).
STRUKTUR ARTIKEL:
1. **Pengantar Tematik**: Memposisikan topik dalam peta besar warisan intelektual bidang terkait.
2. **Konteks Sejarah & Sumber Klasik**: Menghadirkan teks atau temuan rintisan di bidang tersebut, dengan istilah teknis yang diulas tuntas dan dijelaskan maknanya.
3. **Transformasi ke Era Modern**: Bagaimana teori, riset, dan praktik mutakhir merespons tema tersebut.
4. **Sintesis Holistik**: Menghubungkan implikasi teoretis, praktis, dan etis dari posisi yang dipilih.
5. **Rujukan & Catatan Akhir**: Glosarium istilah dan bibliografi.
Panjang: Mendalam, berbobot, dan kaya konteks sejarah gagasan.
""",
    },
}


def _estimate_reading_time(text: str) -> int:
    """Estimate reading time in minutes based on 200 words per minute."""
    word_count = len(re.findall(r"\w+", text))
    return max(1, round(word_count / 200))


def generate_article(
    topic: str,
    style: str = "essay",
    custom_instructions: str = "",
    faculty_id: str = None,
    paper_files: list = None,
    model: str = None,
) -> dict:
    """
    Generate a full-length, publication-grade article based on Second Brain literature.
    """
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    style_info = ARTICLE_STYLES.get(style, ARTICLE_STYLES["essay"])

    # 1. Gather relevant literature context from Second Brain
    context_papers = []
    seen = set()

    # If specific papers provided
    if paper_files:
        for f in paper_files:
            summary = db.get_paper_knowledge_summary(f)
            if summary and f not in seen:
                context_papers.append(summary)
                seen.add(f)

    # Search relevant papers via FTS5 if more context needed
    search_res = db.search(topic, limit=8)
    for r in search_res:
        f = r.get("file")
        if f and f not in seen:
            summary = db.get_paper_knowledge_summary(f)
            if summary and summary.get("thesis"):
                context_papers.append(summary)
                seen.add(f)
            if len(context_papers) >= 8:
                break

    # Build literature block
    blocks = []
    for idx, p in enumerate(context_papers, 1):
        year = p.get("year", "n.d.")
        title = p.get("title", "Untitled")
        arg_t = p.get("argument_type", "-")
        stance = p.get("supports_or_critiques", "-")
        b = f"[{idx}] {title} ({year}) | Tipe: {arg_t} | Sikap: {stance}\n"
        if p.get("thesis"):
            b += f"  Tesis: {p['thesis']}\n"
        if p.get("premises"):
            b += f"  Premis: {' | '.join(p['premises'][:3])}\n"
        if p.get("key_objection"):
            b += f"  Objeksi: {p['key_objection']}\n"
        if p.get("key_defense"):
            b += f"  Pertahanan: {p['key_defense']}\n"
        blocks.append(b)

    corpus_context = "\n".join(blocks) if blocks else "(Gunakan basis pengetahuan akademik komprehensifmu di bidang terkait)."

    system_prompt = f"""Kamu adalah "The Master Essayist & Senior Scholar" di CosmoLab University.
Keahlianmu adalah menulis karya tulis ilmiah dan esai akademik lintas bidang yang indah, fasih, tajam, dan siap baca/terbit.
Tulislah dalam BAHASA INDONESIA akademis bermutu sastra tinggi (mengalir, artikulatif, elegan, dan kaya rujukan nalar).

{style_info['prompt_instructions']}

ATURAN WAJIB:
- Jangan gunakan bahasa kaku, berbelit-belit, atau ringkasan poin-poin terputus. Gunakan narasi esai panjang yang mengalir dinamis.
- Jaga kejernihan nalar: Utamakan padanan bahasa Indonesia yang terang dan jelas. Jika menggunakan istilah teknis bidang apa pun, WAJIB sertakan arti/penjelasan singkat di dalam kurung pada kemunculan pertama, lalu gunakan bahasa Indonesianya pada kalimat berikutnya.
- Hindari penumpukan istilah abstrak dalam satu kalimat. Berikan contoh konkret atau analogi sehari-hari sebelum melangkah ke teori filosofis.
- Pangkas istilah teknis yang tidak relevan langsung dengan tesis utama.
- Hubungkan gagasan para pemikir, peneliti, dan praktisi secara organik, membumi, dan mudah dipahami oleh pembaca umum, pelajar, serta mahasiswa.
"""

    user_prompt = f"""TOPIK ARTIKEL YANG HARUS DITULIS:
"{topic}"

FAKULTAS/DOMAIN: {faculty_id or 'Multidisipliner'}
INSTRUKSI KHUSUS PENGGUNA: {custom_instructions or 'Tulis dengan kedalaman analisis maksimal dan narasi yang memikat.'}

DATA LITERATUR KORPUS (Rujukan Pendukung):
{corpus_context}

Tuliskan artikel siap baca yang utuh dan lengkap sekarang:"""

    def _safe_extract(res_obj) -> str:
        if not res_obj:
            return ""
        choices = getattr(res_obj, "choices", None)
        if not choices or len(choices) == 0:
            return ""
        choice = choices[0]
        if not choice:
            return ""
        message = getattr(choice, "message", None)
        if not message:
            return ""
        return (getattr(message, "content", "") or "").strip()

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=75.0)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
        )
        content = _safe_extract(resp)
        if not content or "上游错误" in content:
            console.print("[yellow]Primary model returned empty/error. Switching to gemini-3-8-flash fallback...[/yellow]")
            fb = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.35,
            )
            content = _safe_extract(fb)
    except Exception as e:
        console.print(f"[red]Error writing article with {model}: {e}. Trying gemini-3-8-flash fallback...[/red]")
        try:
            fb = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.35,
            )
            content = _safe_extract(fb)
        except Exception as e2:
            content = f"# Gagal Menyusun Artikel\n\nTerjadi kesalahan: {e2}"

    reading_time = _estimate_reading_time(content)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Extract title from content if first line is markdown header
    lines = content.splitlines()
    article_title = topic
    for line in lines:
        if line.startswith("# "):
            article_title = line.replace("# ", "").strip()
            break

    result = {
        "title": article_title,
        "topic": topic,
        "style": style,
        "style_name": style_info["name"],
        "content_md": content,
        "reading_time_min": reading_time,
        "created_at": now_str,
        "referenced_papers": context_papers,
    }

    return result


def format_article_html(article_dict: dict) -> str:
    """
    Format markdown article into a beautiful, standalone HTML reading experience
    with academic serif typography, KaTeX math support, and print-ready PDF styling.
    """
    try:
        from markdown_it import MarkdownIt
        md_parser = MarkdownIt("commonmark", {"html": False})  # AI text must not inject raw HTML
        html_body = md_parser.render(article_dict.get("content_md", ""))
    except Exception:
        import html
        html_body = f"<pre>{html.escape(article_dict.get('content_md', ''))}</pre>"
    
    import html as _html
    title = _html.escape(article_dict.get("title", "Artikel CosmoLab University"))
    style_name = article_dict.get("style_name", "Esai Ilmiah")
    reading_time = article_dict.get("reading_time_min", 5)
    created_at = article_dict.get("created_at", "")

    html_template = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — CosmoLab University</title>
    <!-- Fonts: Merriweather & Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Merriweather:ital,wght@0,300;0,400;0,700;1,300;1,400&family=Amiri:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <!-- KaTeX for LaTeX Math -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body);"></script>

    <style>
        :root {{
            --primary: #1E3A8A;
            --accent: #B45309;
            --bg: #FAFAF9;
            --surface: #FFFFFF;
            --text: #1C1917;
            --text-muted: #57534E;
            --border: #E7E5E4;
            --code-bg: #F5F5F4;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #121212;
                --surface: #1E1E1E;
                --text: #E5E5E5;
                --text-muted: #A3A3A3;
                --border: #2E2E2E;
                --code-bg: #262626;
            }}
        }}

        body {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 1.15rem;
            line-height: 1.85;
            color: var(--text);
            background-color: var(--bg);
            margin: 0;
            padding: 0;
            text-rendering: optimizeLegibility;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{
            max-width: 820px;
            margin: 0 auto;
            padding: 60px 24px;
            background: var(--surface);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
            border-radius: 8px;
            margin-top: 40px;
            margin-bottom: 60px;
        }}

        .article-header {{
            border-bottom: 2px solid var(--border);
            padding-bottom: 24px;
            margin-bottom: 36px;
            text-align: center;
        }}

        .univ-badge {{
            display: inline-block;
            font-family: 'Inter', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: var(--primary);
            background: #EEF2FF;
            padding: 4px 14px;
            border-radius: 20px;
            margin-bottom: 16px;
        }}

        .meta-info {{
            font-family: 'Inter', sans-serif;
            font-size: 0.92rem;
            color: var(--text-muted);
            margin-top: 14px;
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Inter', sans-serif;
            color: var(--text);
            font-weight: 700;
            line-height: 1.35;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }}

        h1 {{ font-size: 2.3rem; margin-top: 0.5rem; }}
        h2 {{ font-size: 1.65rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
        h3 {{ font-size: 1.35rem; }}

        p {{
            margin-bottom: 1.6rem;
            text-align: justify;
        }}

        blockquote {{
            border-left: 4px solid var(--accent);
            padding: 12px 24px;
            margin: 28px 0;
            background-color: var(--code-bg);
            border-radius: 0 8px 8px 0;
            font-style: italic;
            color: var(--text);
        }}

        blockquote p {{
            margin: 0;
        }}

        .arabic {{
            font-family: 'Amiri', serif;
            font-size: 1.35rem;
            direction: rtl;
            line-height: 2.2;
        }}

        code {{
            font-family: monospace;
            background-color: var(--code-bg);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
        }}

        pre {{
            background-color: var(--code-bg);
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 24px 0;
            font-family: 'Inter', sans-serif;
            font-size: 0.95rem;
        }}

        th, td {{
            border: 1px solid var(--border);
            padding: 10px 14px;
            text-align: left;
        }}

        th {{
            background-color: var(--code-bg);
            font-weight: 600;
        }}

        .article-footer {{
            margin-top: 60px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            font-family: 'Inter', sans-serif;
            font-size: 0.88rem;
            color: var(--text-muted);
            text-align: center;
        }}

        /* Print styles for Clean PDF Export */
        @media print {{
            body {{
                background: white;
                color: black;
                font-size: 11pt;
                line-height: 1.6;
            }}
            .container {{
                box-shadow: none;
                margin: 0;
                padding: 0;
                max-width: 100%;
            }}
            .no-print {{
                display: none;
            }}
            a {{
                text-decoration: none;
                color: black;
            }}
        }}

        .print-btn {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #1E3A8A;
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 50px;
            font-family: 'Inter', sans-serif;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(0,0,0,0.2);
            transition: all 0.2s;
        }}

        .print-btn:hover {{
            background: #1E40AF;
            transform: translateY(-2px);
        }}
    </style>
</head>
<body>

    <button class="print-btn no-print" onclick="window.print()">🖨️ Cetak / Simpan PDF</button>

    <div class="container">
        <header class="article-header">
            <span class="univ-badge">🏛️ CosmoLab University Publishing</span>
            <div class="meta-info">
                <span>Format: <b>{style_name}</b></span>
                <span>⏱️ Waktu Baca: <b>~{reading_time} menit</b></span>
                <span>📅 {created_at}</span>
            </div>
        </header>

        <article>
            {html_body}
        </article>

        <footer class="article-footer">
            <p>Diterbitkan secara otomatis oleh <b>CosmoLab University Studio</b> — Knowledge Engine untuk Riset Multidisipliner.</p>
        </footer>
    </div>

</body>
</html>
"""
    return html_template


def save_article(article_dict: dict) -> dict:
    """Save article in both Markdown (.md) and Standalone HTML (.html) formats."""
    config.ensure_dirs()
    articles_dir = config.ROOT / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    title = article_dict.get("title", "Artikel_Cosmolab")
    safe_title = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in title).strip()
    safe_title = safe_title.replace(" ", "_")[:60]
    date_prefix = datetime.now().strftime("%Y%m%d")
    base_name = f"{date_prefix}_{safe_title}"

    # 1. Save Markdown
    md_path = articles_dir / f"{base_name}.md"
    md_path.write_text(article_dict["content_md"], encoding="utf-8")

    # 2. Save Standalone HTML
    html_content = format_article_html(article_dict)
    html_path = articles_dir / f"{base_name}.html"
    html_path.write_text(html_content, encoding="utf-8")

    # Also save to Obsidian articles subfolder if desired
    obsidian_articles_dir = config.OBSIDIAN_DIR / "articles"
    obsidian_articles_dir.mkdir(parents=True, exist_ok=True)
    obsidian_path = obsidian_articles_dir / f"{base_name}.md"
    obsidian_path.write_text(article_dict["content_md"], encoding="utf-8")

    console.print(f"[green]OK  Article saved to: {md_path} and {html_path}[/green]")

    return {
        "md_path": md_path,
        "html_path": html_path,
        "obsidian_path": obsidian_path,
    }
