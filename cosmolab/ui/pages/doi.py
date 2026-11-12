"""Dashboard page: Bedah DOI Seketika."""

import streamlit as st
from cosmolab import db
from cosmolab import inspector as _inspector
from cosmolab.ui.components import _e
from cosmolab.ui.components import _safe_url
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Bedah DOI Seketika."""
    render_hero(
        title="Bedah DOI Seketika (Smart Paper Inspector)",
        subtitle="Masukkan <b>DOI artikel ilmiah</b> apa saja dari Elsevier, Springer, Nature, Wiley, atau jurnal mana pun. Sistem seketika mengekstrak <b>Latar Belakang, Metodologi, Temuan Kunci, Kesimpulan</b>, serta <b>Celah Riset untuk Skripsi/Tesis</b>.",
        icon="",
        badges=[
            {"icon": "", "text": "AMRC Breakdown", "class": "hero-badge-primary"},
            {"icon": "", "text": "Elsevier Style Highlights", "class": "hero-badge-accent"},
            {"icon": "", "text": "Research Gap Finder", "class": "hero-badge-model"}
        ]
    )

    if "inspector_doi_input" not in st.session_state:
        st.session_state["inspector_doi_input"] = ""

    st.markdown("##### Coba Contoh DOI Cepat:")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    if col_ex1.button("Elsevier (Kognisi & Memori)", use_container_width=True):
        st.session_state["inspector_doi_input"] = "10.1016/j.concog.2020.102980"
        st.rerun()
    if col_ex2.button("Springer (Kalam & Matematika)", use_container_width=True):
        st.session_state["inspector_doi_input"] = "10.1007/s00283-022-10224-8"
        st.rerun()
    if col_ex3.button("Oxford Mind (Kausalitas)", use_container_width=True):
        st.session_state["inspector_doi_input"] = "10.1093/mind/fzv156"
        st.rerun()

    doi_val = st.text_input(
        "Masukkan DOI atau URL Paper Ilmiah:",
        value=st.session_state["inspector_doi_input"],
        placeholder="Contoh: 10.1016/j.concog.2020.102980 atau https://doi.org/10.1007/...",
        help="Mendukung format DOI murni (10.xxxx/...) atau link https://doi.org/...",
    )

    col_btn1, col_btn2 = st.columns([1, 3])
    run_inspect = col_btn1.button("Bedah Paper Sekarang", type="primary", use_container_width=True)

    if run_inspect and doi_val.strip():
        with st.spinner("Menghubungi Crossref, Semantic Scholar, OpenAlex & membedah dengan AI..."):
            res = _inspector.inspect_paper(doi_val.strip())
            st.session_state["last_inspection_res"] = res

    if "last_inspection_res" in st.session_state and st.session_state["last_inspection_res"]:
        res = st.session_state["last_inspection_res"]
        if not res.get("success"):
            st.error(f"{res.get('error')}")
        else:
            a = res.get("analysis", {})

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
            if col_act1.button("Simpan Hasil Bedah ke Disk", use_container_width=True):
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
                        "ilahiyyat"
                    ))
                    con.commit()
                    con.close()
                    st.success("Berhasil ditambahkan ke Database Korpus CosmoLab!")
                except Exception as e:
                    st.error(f"Gagal menyimpan ke DB: {e}")
