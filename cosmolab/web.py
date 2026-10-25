import json
import subprocess
import sys
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from cosmolab import config
from cosmolab import db
from cosmolab import export
from cosmolab import ask as _ask
from cosmolab import harvest as _harvest
from cosmolab import extract as _extract
from cosmolab import analyze as _analyze
from cosmolab import synthesize as _synthesize

# Page Configuration
st.set_page_config(
    page_title="Cosmolab Research Engine",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F3F4F6;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        border: 1px solid #E5E7EB;
    }
    .stance-supports {
        color: #047857;
        font-weight: bold;
    }
    .stance-critiques {
        color: #B91C1C;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def render_mermaid(code: str, height: int = 450):
    """Render Mermaid diagram inside Streamlit."""
    html_code = f"""
    <div style="background: #ffffff; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0;">
      <pre class="mermaid" style="display: flex; justify-content: center;">
{code}
      </pre>
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    components.html(html_code, height=height, scrolling=True)


# Sidebar - Metrics & Navigation
st.sidebar.markdown("## 🌌 **Cosmolab Engine**")
st.sidebar.caption(f"Model Aktif: **{config.LLM_MODEL}**")

# Load DB data
papers = db.get_all_papers_with_analyses()
total_papers = len(papers)
total_analyzed = len([p for p in papers if p.get("thesis")])
total_texts = len(list(config.TEXT_DIR.glob("*.txt")))

col_s1, col_s2 = st.sidebar.columns(2)
col_s1.metric("Total Paper", total_papers)
col_s2.metric("Dianalisis", total_analyzed)

menu = st.sidebar.radio(
    "Navigasi Modul:",
    [
        "📚 Paper Explorer",
        "💬 Tanya Korpus (RAG)",
        "🔍 Full-Text Search",
        "🕸️ Diagram Argumen",
        "⚡ Panen Paper Baru",
        "📑 Laporan Sintesis",
        "📤 Ekspor Data"
    ]
)

st.sidebar.divider()
st.sidebar.info("💡 **Cosmolab** mengintegrasikan arXiv, DOAJ, OpenAlex & DeepSeek untuk riset terstruktur.")

# -------------------------------------------------------------
# Module 1: Paper Explorer
# -------------------------------------------------------------
if menu == "📚 Paper Explorer":
    st.markdown('<div class="main-header">📚 Penjelajah Paper & Rekonstruksi Logika</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Daftar seluruh paper yang telah berhasil dipanen dan dianalisis secara terstruktur.</div>', unsafe_allow_html=True)

    if not papers:
        st.warning("Belum ada paper di database. Buka tab '⚡ Panen Paper Baru' untuk mengunduh paper.")
    else:
        col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
        filter_q = col_f1.text_input("Saring Judul / Penulis:", placeholder="Ketik kata kunci judul...")
        arg_types = ["Semua"] + sorted(list({p.get("argument_type") for p in papers if p.get("argument_type")}))
        filter_type = col_f2.selectbox("Tipe Argumen:", arg_types)
        stances = ["Semua", "supports", "critiques", "mixed", "neutral"]
        filter_stance = col_f3.selectbox("Posisi / Stance:", stances)

        # Filter papers
        filtered = papers
        if filter_q:
            filtered = [p for p in filtered if filter_q.lower() in (p.get("title") or "").lower()]
        if filter_type != "Semua":
            filtered = [p for p in filtered if p.get("argument_type") == filter_type]
        if filter_stance != "Semua":
            filtered = [p for p in filtered if p.get("supports_or_critiques") == filter_stance]

        st.caption(f"Menampilkan **{len(filtered)}** dari {len(papers)} paper:")

        for idx, p in enumerate(filtered, start=1):
            title = p.get("title") or "Untitled"
            year = p.get("year") or "n.d."
            arg_t = p.get("argument_type") or "unclassified"
            stn = p.get("supports_or_critiques") or "-"
            source = p.get("source") or "web"

            with st.expander(f"**{idx}. [{year}] {title}** ({arg_t.upper()} | {stn})"):
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.write(f"**Tahun**: {year}")
                col_m1.write(f"**Sumber**: `{source}`")
                col_m2.write(f"**Tipe Argumen**: `{arg_t}`")
                col_m2.write(f"**Stance**: `{stn}`")
                col_m3.write(f"**DOI**: {p.get('doi') or 'N/A'}")
                if p.get("url"):
                    col_m3.markdown(f"[🔗 Link PDF Asli]({p.get('url')})")

                st.divider()

                # Thesis
                if p.get("thesis"):
                    st.markdown("#### 🎯 Tesis Utama")
                    st.info(p.get("thesis"))

                # Premises
                if p.get("premises_json"):
                    try:
                        premises = json.loads(p["premises_json"])
                        if premises:
                            st.markdown("#### 📐 Rekonstruksi Premis")
                            for p_num, prem in enumerate(premises, 1):
                                st.markdown(f"- **P{p_num}:** {prem}")
                    except Exception:
                        pass

                # Conclusion
                if p.get("conclusion"):
                    st.markdown(f"**Kesimpulan:** `{p.get('conclusion')}`")

                # Objection & Defense
                col_o1, col_o2 = st.columns(2)
                if p.get("key_objection"):
                    col_o1.markdown("#### ⚠️ Objeksi Terkuat")
                    col_o1.warning(p.get("key_objection"))
                if p.get("key_defense"):
                    col_o2.markdown("#### 🛡️ Tanggapan / Pertahanan")
                    col_o2.success(p.get("key_defense"))

                # Quotes
                if p.get("quotes_json"):
                    try:
                        quotes = json.loads(p["quotes_json"])
                        if quotes:
                            st.markdown("#### 💬 Kutipan Kunci dari Paper")
                            for q in quotes:
                                st.markdown(f"> *\"{q.get('text', '')}\"* — **Hal. {q.get('page_hint', 'N/A')}**")
                    except Exception:
                        pass

# -------------------------------------------------------------
# Module 2: Tanya Korpus (RAG)
# -------------------------------------------------------------
elif menu == "💬 Tanya Korpus (RAG)":
    st.markdown('<div class="main-header">💬 Tanya Korpus Riset (RAG Assistant)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ajukan pertanyaan penelitian. DeepSeek akan memeriksa seluruh korpus paper dan menjawab dengan sitasi akurat.</div>', unsafe_allow_html=True)

    # Pre-set prompt suggestions
    suggestions = [
        "Bagaimana para peneliti dalam paper ini membantah klaim bahwa fenomena kuantum membatalkan hukum kausalitas?",
        "Apa saja argumen matematika yang diajukan mengenai ketakterhinggaan aktual?",
        "Apa perbedaan mendasar antara indeterminisme dalam mekanika kuantum dengan konsep takdir/sebab dalam Kalām?",
        "Apa keberatan filosofis terkuat terhadap premis bahwa alam semesta mulai ada?"
    ]

    selected_sug = st.selectbox("Pilih Contoh Pertanyaan Cepat:", ["(Ketik sendiri...)"] + suggestions)

    user_q = st.text_area(
        "Pertanyaan Anda:",
        value=selected_sug if selected_sug != "(Ketik sendiri...)" else "",
        placeholder="Ketik pertanyaan penelitian Anda di sini...",
        height=100
    )

    col_r1, col_r2 = st.columns([1, 4])
    k_val = col_r1.slider("Jumlah Paper Rujukan:", min_value=2, max_value=8, value=5)

    if st.button("🚀 Ajukan Pertanyaan ke Korpus", type="primary"):
        if not user_q.strip():
            st.error("Silakan masukkan pertanyaan terlebih dahulu.")
        else:
            with st.spinner("DeepSeek sedang menelusuri korpus paper dan menyusun sintesis..."):
                try:
                    answer = _ask.ask(question=user_q, model=config.LLM_MODEL, top_k=k_val)
                    st.markdown("### 📝 Jawaban Korpus:")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"Gagal memproses pertanyaan: {e}")

# -------------------------------------------------------------
# Module 3: Full-Text Search
# -------------------------------------------------------------
elif menu == "🔍 Full-Text Search":
    st.markdown('<div class="main-header">🔍 Pencarian Teks Penuh (SQLite FTS5)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Pencarian instan berbobot BM25 pada judul, abstrak, premis, dan isi teks seluruh paper.</div>', unsafe_allow_html=True)

    search_query = st.text_input("Ketik Kata Kunci Pencarian:", placeholder="contoh: kalam, indeterminism, hilbert, causality...")
    limit_count = st.slider("Maksimal Hasil:", min_value=3, max_value=20, value=8)

    if search_query:
        results = db.search(search_query, limit=limit_count)
        if not results:
            st.warning(f"Tidak ada paper yang cocok dengan kata kunci: '{search_query}'")
        else:
            st.success(f"Ditemukan **{len(results)}** paper relevan:")
            for r in results:
                st.markdown(f"#### 📄 {r.get('title')} ({r.get('year', 'n.d.')})")
                st.caption(f"Tipe: `{r.get('argument_type') or '-'}` | Stance: `{r.get('supports_or_critiques') or '-'}` | DOI: {r.get('doi') or 'N/A'}")
                if r.get("key_objection"):
                    st.markdown(f"**Objeksi Kunci:** {r.get('key_objection')}")
                if r.get("snippet"):
                    st.markdown(f"**Snippet Teks:** ...{r.get('snippet')}...")
                st.divider()

# -------------------------------------------------------------
# Module 4: Diagram Argumen
# -------------------------------------------------------------
elif menu == "🕸️ Diagram Argumen":
    st.markdown('<div class="main-header">🕸️ Visualisasi Pohon Argumen (Mermaid)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Visualisasi alur silogisme: Tesis ➔ Premis ➔ Kesimpulan ➔ Objeksi ➔ Tanggapan.</div>', unsafe_allow_html=True)

    paper_choices = [p["file"] for p in papers if p.get("thesis")]
    if not paper_choices:
        st.warning("Belum ada paper yang selesai dianalisis.")
    else:
        selected_file = st.selectbox("Pilih Paper untuk Divisualisasikan:", paper_choices)
        stem = Path(selected_file).stem
        mermaid_code = export.generate_mermaid_graph(stem)

        st.markdown(f"### Diagram Logika: *{stem}*")
        render_mermaid(mermaid_code)

        with st.expander("Lihat Kode Sumber Mermaid"):
            st.code(mermaid_code, language="mermaid")

# -------------------------------------------------------------
# Module 5: Panen Paper Baru
# -------------------------------------------------------------
elif menu == "⚡ Panen Paper Baru":
    st.markdown('<div class="main-header">⚡ Panen Paper Akademik Baru</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Pencarian multi-sumber konkuren di <b>arXiv, DOAJ, Semantic Scholar, dan OpenAlex</b>.</div>', unsafe_allow_html=True)

    col_h1, col_h2 = st.columns([3, 1])
    h_query = col_h1.text_input("Topik / Kata Kunci Paper:", value="kalam cosmological argument quantum causality")
    h_max = col_h2.number_input("Jumlah Paper Maksimal:", min_value=5, max_value=60, value=20)

    if st.button("📥 Mulai Panen Paralel", type="primary"):
        with st.spinner(f"Sedang mencari di 4 sumber dan mengunduh PDF secara paralel..."):
            try:
                stats = _harvest.harvest(h_query, max_results=h_max, workers=4, delay=0.5)
                st.success(f"Panen selesai! Berhasil mengunduh: {stats.get('downloaded', 0)} paper baru.")
                st.json(stats)
                db.sync_all()
            except Exception as e:
                st.error(f"Gagal saat panen: {e}")

# -------------------------------------------------------------
# Module 6: Laporan Sintesis
# -------------------------------------------------------------
elif menu == "📑 Laporan Sintesis":
    st.markdown('<div class="main-header">📑 Laporan Sintesis Lintas Paper</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Hasilkan atau baca laporan tinjauan pustaka komparatif (Literature Review).</div>', unsafe_allow_html=True)

    col_s1, col_s2 = st.columns([1, 2])
    lang_choice = col_s1.selectbox("Bahasa Laporan:", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English")
    
    if col_s2.button("✨ Buat Laporan Sintesis Baru dengan DeepSeek"):
        with st.spinner("DeepSeek sedang menyusun laporan sintesis lintas korpus..."):
            res = _synthesize.synthesize(model=config.LLM_MODEL, lang=lang_choice)
            st.success(f"Laporan berhasil dibuat!")

    st.divider()
    st.markdown("### 📂 Laporan yang Sudah Tersedia:")
    reports = sorted(list(config.SYNTH_DIR.glob("*.md")), reverse=True)
    if not reports:
        st.info("Belum ada laporan sintesis.")
    else:
        selected_rep = st.selectbox("Pilih Laporan untuk Dibaca:", [r.name for r in reports])
        rep_file = config.SYNTH_DIR / selected_rep
        st.markdown(rep_file.read_text(encoding="utf-8"))

# -------------------------------------------------------------
# Module 7: Ekspor Data
# -------------------------------------------------------------
elif menu == "📤 Ekspor Data":
    st.markdown('<div class="main-header">📤 Ekspor ke Reference Manager & Catatan Riset</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Simpan korpus riset ke format Zotero/Mendeley (BibTeX) atau Obsidian Vault.</div>', unsafe_allow_html=True)

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        st.markdown("### 🗃️ Ekspor ke BibTeX (.bib)")
        st.write("Format standar untuk diimpor ke **Zotero, Mendeley, atau dokumen LaTeX**.")
        if st.button("Generate references.bib"):
            bib_path = export.export_bibtex()
            st.success(f"Berhasil diekspor ke: `{bib_path}`")
            st.download_button(
                "⬇️ Unduh File references.bib",
                data=bib_path.read_text(encoding="utf-8"),
                file_name="references.bib",
                mime="text/plain"
            )

    with col_e2:
        st.markdown("### 💎 Ekspor ke Obsidian Vault")
        st.write("Menghasilkan catatan Markdown dengan `[[wikilinks]]`, tag hierarkis, dan indeks matriks.")
        if st.button("Generate Obsidian Vault"):
            vault_path = export.export_obsidian()
            st.success(f"Berhasil diekspor ke folder: `{vault_path}`")
            st.info("Buka Obsidian, lalu pilih **Open folder as vault** dan arahkan ke folder `data/obsidian`.")
