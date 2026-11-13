"""Summarize one paper from its DOI without adding it. Shown as a tab in Cari & tambah paper."""

import streamlit as st
from cosmolab import faculties as _faculties
from cosmolab import db
from cosmolab import inspector as _inspector
from cosmolab.ui.components import _e
from cosmolab.ui.components import _safe_url
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


# One well-known paper per field (DOIs checked on Crossref).
EXAMPLE_DOIS = [
    ("Ekonomi", "10.2307/1914185"),                     # Kahneman & Tversky, Prospect Theory
    ("Pendidikan", "10.1080/0969595980050102"),         # Black & Wiliam, Assessment and Classroom Learning
    ("Kesehatan", "10.1371/journal.pmed.0020124"),      # Ioannidis, Why Most Published Research Findings Are False
    ("Sains & teknologi", "10.1038/nature14539"),       # LeCun, Bengio & Hinton, Deep learning
    ("Bahasa", "10.1093/applin/1.1.1"),                 # Canale & Swain, communicative approaches
    ("Metodologi", "10.1177/1609406917733847"),         # Nowell et al., Thematic Analysis
]


def render(ctx: AppContext):
    """Old menu entry; the same tool is a tab in Cari & tambah paper."""
    render_hero(title="Ringkas Paper dari DOI",
                subtitle="Ringkasan satu paper dari DOI-nya, tanpa memasukkannya ke koleksi.")
    render_body()


def render_body():
    st.caption("Masukkan DOI artikel dari penerbit mana pun. AI meringkas latar belakang, metode, temuan, kesimpulan, "
               "dan celah riset. Paper tidak masuk koleksi kecuali Anda menyimpannya.")

    if "inspector_doi_input" not in st.session_state:
        st.session_state["inspector_doi_input"] = ""

    st.markdown("##### Contoh DOI")
    cols = st.columns(3)
    for i, (label, doi) in enumerate(EXAMPLE_DOIS):
        if cols[i % 3].button(label, key=f"doi_example_{i}", use_container_width=True):
            st.session_state["inspector_doi_input"] = doi
            st.rerun()

    doi_val = st.text_input(
        "DOI atau URL paper",
        value=st.session_state["inspector_doi_input"],
        placeholder="Contoh: 10.2307/1914185 atau https://doi.org/10.2307/1914185",
        help="Mendukung format DOI murni (10.xxxx/...) atau link https://doi.org/...",
    )

    col_btn1, col_btn2 = st.columns([1, 3])
    run_inspect = col_btn1.button("Ringkas paper", type="primary", use_container_width=True)

    if run_inspect and doi_val.strip():
        with st.spinner("Menghubungi Crossref, Semantic Scholar, OpenAlex & membedah dengan AI..."):
            res = _inspector.inspect_paper(doi_val.strip())
            st.session_state["last_inspection_res"] = res

    if "last_inspection_res" in st.session_state and st.session_state["last_inspection_res"]:
        res = st.session_state["last_inspection_res"]
        if not res.get("success"):
            st.error(f"{res.get('error')}")
        else:
            a = res.get("analysis") or {}

            st.markdown("---")
            # Header Card
            pdf_link_html = f" • <a href='{_safe_url(res.get('pdf_url'))}' target='_blank' style='background:#10B981; color:white; padding:3px 8px; border-radius:6px; text-decoration:none; font-weight:600; font-size:0.8rem;'>Unduh PDF Terbuka (Legal)</a>" if res.get("pdf_url") else ""
            oa_badge = "<span style='background:#DCFCE7; color:#166534; padding:3px 8px; border-radius:6px; font-weight:600; font-size:0.85rem;'>Open Access (Tersedia Naskah Terbuka)</span>" if res.get("is_oa") else "<span style='background:#FEF3C7; color:#92400E; padding:3px 8px; border-radius:6px; font-weight:600; font-size:0.85rem;'>Paywalled / Berbayar</span>"
            
            st.markdown(f"""
            <div style="background:white; border:1px solid #E2E8F0; border-radius:12px; padding:20px; margin-bottom:18px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:6px;">
                    <b>{_e(res.get('venue') or res.get('publisher') or 'Jurnal Ilmiah')}</b> • Tahun {_e(res.get('year'))} • {oa_badge}{pdf_link_html} • <b>{_e(res.get('citation_count'))}</b> Sitasi
                </div>
                <h3 style="margin-top:0; color:#0F172A; font-weight:700;">{_e(res.get('title'))}</h3>
                <div style="color:#475569; font-size:0.92rem; margin-bottom:10px;">
                    <b>Penulis:</b> {_e(', '.join(res.get('authors', [])) or 'Anonim')}
                </div>
                <div>
                    <a href="{_safe_url(res.get('url'))}" target="_blank" style="text-decoration:none; color:#2563EB; font-weight:600;">https://doi.org/{_e(res.get('doi'))}</a>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if res.get("analysis_note"):
                st.warning(res["analysis_note"])

            # One-Sentence Takeaway
            if a.get("one_sentence_takeaway"):
                st.info(f"**Intisari 1 Kalimat:** \"{a.get('one_sentence_takeaway')}\"")

            # Elsevier-Style Highlights
            if a.get("highlights"):
                st.markdown("##### Research Highlights (Gaya Elsevier ScienceDirect)")
                hl_html = "".join(f"<li style='margin-bottom:6px; color:#1E293B;'>{_e(h)}</li>" for h in a.get("highlights"))
                st.markdown(f"""
                <div style="background:#F8FAFC; border-left:4px solid #10B981; padding:12px 18px; border-radius:0 8px 8px 0; margin-bottom:20px;">
                    <ul style="margin:0; padding-left:20px;">{hl_html}</ul>
                </div>
                """, unsafe_allow_html=True)

            # AMRC Quadrants / Tabs
            tab_prob, tab_meth, tab_res, tab_conc, tab_gap = st.tabs([
                "Latar Belakang & Masalah",
                "Metodologi",
                "Temuan Kunci (Result)",
                "Kesimpulan & Implikasi",
                "Celah Riset (Untuk Skripsi/Tesis)"
            ])

            with tab_prob:
                st.markdown(f"**Urgensi & Masalah yang Diteliti:**\n\n{a.get('problem_statement', '-')}")
                if res.get("abstract"):
                    with st.expander("Teks Asli Abstrak dari Penerbit", expanded=False):
                        st.write(res.get("abstract"))

            with tab_meth:
                st.markdown(f"**Desain Riset & Pendekatan Ilmiah:**\n\n{a.get('methodology', '-')}")

            with tab_res:
                st.markdown("**Temuan Signifikan:**")
                kfs = a.get("key_findings", [])
                if isinstance(kfs, list):
                    for f in kfs:
                        st.markdown(f"- {f}")
                else:
                    st.write(kfs)

            with tab_conc:
                st.markdown(f"**Kesimpulan Akhir & Dampak Riset:**\n\n{a.get('conclusion', '-')}")

            with tab_gap:
                st.markdown("**Celah Riset & Ide Penelitian Turunan (Cocok untuk Judul Skripsi/Tesis Baru):**")
                gaps = a.get("research_gaps", [])
                if isinstance(gaps, list):
                    for g in gaps:
                        st.markdown(f"- {g}")
                else:
                    st.write(gaps)

            # Citation Section
            st.markdown("---")
            st.markdown("##### Format Sitasi & Rujukan")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("**Format APA 7th:**")
                st.code(res.get("apa_citation", ""), language="markdown")
            with col_c2:
                st.markdown("**Format BibTeX (Mendeley / Zotero / LaTeX):**")
                st.code(res.get("bibtex", ""), language="bibtex")

            # Actions
            col_act1, col_act2 = st.columns(2)
            if col_act1.button("Simpan ringkasan", use_container_width=True):
                saved_path = _inspector.save_inspection(res)
                st.success(f"Berhasil disimpan di: `{saved_path}`")
            
            if col_act2.button("Masukkan Metadata ke Database CosmoLab", use_container_width=True):
                try:
                    con = db.get_connection()
                    con.execute("""
                        INSERT OR REPLACE INTO papers (file, id, title, year, doi, url, source, abstract, faculty)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"doi_{res['doi'].replace('/', '_')}.pdf",
                        res["doi"],
                        res["title"],
                        str(res["year"]),
                        res["doi"],
                        res["url"],
                        "doi_inspector",
                        res.get("abstract", ""),
                        _faculties.detect_faculty_from_text(res.get("title") or "", res.get("abstract") or ""),
                    ))
                    con.commit()
                    con.close()
                    st.success("Berhasil ditambahkan ke Database Korpus CosmoLab!")
                except Exception as e:
                    st.error(f"Gagal menyimpan ke DB: {e}")
