"""Dashboard page: Koleksi paper (menu key "Paper Explorer & Korpus")."""

import streamlit as st
from cosmolab import config
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab import analyze as _analyze
from cosmolab import authors as _authors
from cosmolab import matrix as _matrix
from cosmolab import citations as _citations
from cosmolab.ui.components import _e
from cosmolab.ui.components import _EMOJI_RE
from cosmolab.ui.components import render_table
from cosmolab.ui.components import render_hero
from cosmolab.ui.components import _badge
from cosmolab.ui.papers import STANCE_LABELS
from cosmolab.ui.papers import TYPE_LABELS
from cosmolab.ui.papers import paper_badges
from cosmolab.ui.papers import sinta_ranks
from cosmolab.ui.papers import render_analysis_detail
from cosmolab.ui.papers import render_analysis_review
from cosmolab.ui.context import AppContext


# Highest rank number to keep (1 is best); 0 = no filter.
SINTA_FILTERS = {0: "Semua", 2: "SINTA 1–2", 4: "SINTA 1–4", 6: "Ada di daftar SINTA"}


def render(ctx: AppContext):
    """Paper Explorer & Korpus."""
    faculty_labels = ctx.faculty_labels
    faculty_list = ctx.faculty_list
    papers = ctx.papers
    selected_faculty_id = ctx.selected_faculty_id
    active_fac_name = faculty_labels.get(selected_faculty_id, "Universal")
    render_hero(
        title="Koleksi Paper",
        subtitle=f"Bidang: <b>{active_fac_name}</b>. Telusuri paper, lihat hasil analisis AI, dan ambil format sitasinya.",
        icon="",
    )

    tab_pe1, tab_pe2, tab_pe3, tab_pe4 = st.tabs([
        "Daftar paper",
        "Matriks literatur",
        "Cari di naskah",
        "Ekspor daftar pustaka",
    ])

    with tab_pe1:
        if not papers:
            st.warning(f"Belum ada paper di fakultas ini. Buka menu 'Cari & tambah paper' untuk mengunduh literatur bidang {active_fac_name}.")
        else:
            with st.container(border=True):
                col_f1, col_f2 = st.columns([3, 2])
                filter_q = col_f1.text_input("Cari judul", placeholder="Ketik kata kunci...")
                filter_status = col_f2.selectbox("Status", ["Semua Status", "Belum Dianalisis", "Sudah Dianalisis"],
                                                 format_func=lambda x: {"Semua Status": "Semua paper", "Belum Dianalisis": "Belum dianalisis", "Sudah Dianalisis": "Sudah dianalisis"}[x])

                with st.expander("Filter lain", expanded=False):
                    arg_types = ["Semua"] + sorted(list({p.get("argument_type") for p in papers if p.get("argument_type")}))
                    filter_type = st.selectbox("Jenis penelitian", arg_types, format_func=lambda x: TYPE_LABELS.get(x, x))
                    stance_keys = ["Semua", "supports", "critiques", "mixed", "neutral"]
                    filter_stance = st.pills(
                        "Sikap penulis",
                        stance_keys,
                        default="Semua",
                        format_func=lambda x: "Semua" if x == "Semua" else STANCE_LABELS.get(x, x),
                    )
                    filter_sinta = st.selectbox("Peringkat jurnal SINTA", list(SINTA_FILTERS), format_func=SINTA_FILTERS.get,
                                                help="Dicocokkan lewat ISSN dengan daftar SINTA tim (menu Cari & tambah paper, tab Peringkat SINTA).")

            filtered = papers
            if filter_q:
                filtered = [p for p in filtered if filter_q.lower() in (p.get("title") or "").lower()]
            if filter_type != "Semua":
                filtered = [p for p in filtered if p.get("argument_type") == filter_type]
            if filter_stance and filter_stance != "Semua":
                filtered = [p for p in filtered if p.get("supports_or_critiques") == filter_stance]
            if filter_sinta:
                ranks = sinta_ranks()
                filtered = [p for p in filtered if (ranks.get(p.get("file") or "") or {}).get("rank", 99) <= filter_sinta]
            if filter_status == "Belum Dianalisis":
                filtered = [p for p in filtered if not p.get("thesis")]
            elif filter_status == "Sudah Dianalisis":
                filtered = [p for p in filtered if p.get("thesis")]

            # Unanalyzed alert & batch analyze banner
            unanalyzed_scope = [p for p in papers if not p.get("thesis")]
            if unanalyzed_scope:
                with st.container(border=True):
                    col_ub1, col_ub2 = st.columns([3, 2])
                    col_ub1.markdown(f"**{len(unanalyzed_scope)} paper belum dianalisis.**")
                    col_ub1.caption("AI mengekstrak tesis, metodologi, temuan, dan kutipan dengan nomor halaman.")
                    if col_ub2.button(f"Analisis semua ({len(unanalyzed_scope)})", type="primary", key="btn_batch_analyze_all", use_container_width=True):
                        with st.spinner(f"Sedang membedah {len(unanalyzed_scope)} naskah dengan AI ({config.LLM_MODEL})..."):
                            target_f = [p["file"] for p in unanalyzed_scope]
                            _analyze.analyze_all(model=config.LLM_MODEL, concurrency=4, lang="id", files=target_f)
                            db.sync_all()
                            st.success(f"Pembedahan {len(unanalyzed_scope)} naskah selesai!")
                            st.rerun()

            no_author = [p for p in papers if not _authors.as_list(p.get("authors"))]
            if no_author:
                col_na1, col_na2 = st.columns([3, 2])
                col_na1.caption(f"{len(no_author)} paper belum punya nama penulis. CosmoLab mencarinya lewat DOI, arXiv, OpenAlex, dan Crossref, lalu halaman pertama PDF.")
                if col_na2.button(f"Lengkapi penulis ({len(no_author)})", key="btn_fill_authors", use_container_width=True):
                    with st.spinner("Mencari nama penulis..."):
                        _stats = _authors.fill_missing(use_ai=True)
                        db.sync_all()
                    st.success(f"{_stats['found']} dari {_stats['checked']} paper sekarang punya nama penulis.")
                    st.rerun()

            st.markdown(
                f"<div class='cl-legend'><span>Menampilkan {len(filtered)} dari {len(papers)} paper.</span>"
                + _badge("Mendukung", "good") + _badge("Mengkritik", "bad") + _badge("Campuran", "mix") + _badge("Kajian empiris", "info")
                + _badge("Kajian argumen", "teal") + _badge("Perlu dicek", "warn") + "</div>",
                unsafe_allow_html=True,
            )

            for idx, p in enumerate(filtered, start=1):
                title = p.get("title") or "Untitled"
                year = p.get("year") or "n.d."
                arg_t = p.get("argument_type") or "unclassified"
                stn = p.get("supports_or_critiques") or "neutral"
                source = p.get("source") or "web"
                p_faculty = p.get("faculty") or "ilahiyyat"
                fac_info = _faculties.get_faculty(p_faculty)
                fac_icon = fac_info.icon if fac_info else ""
                fac_name = fac_info.name if fac_info else p_faculty

                stance_str = STANCE_LABELS.get(stn, stn)
                type_str = TYPE_LABELS.get(arg_t, arg_t)

                p_authors = _authors.as_list(p.get("authors"))
                meta_bits = ([_authors.display(p_authors)] if p_authors else []) + [str(year), fac_name]

                with st.container(border=True):
                    st.markdown(
                        f"<div class='paper-card-title'>{idx}. {_e(title)}</div>"
                        f"<div class='paper-card-meta'>{_e(' · '.join(meta_bits))}</div>"
                        + paper_badges(p),
                        unsafe_allow_html=True,
                    )

                    if p.get("thesis"):
                        st.markdown(f"<div class='paper-card-thesis'>{_e(p.get('thesis'))}</div>", unsafe_allow_html=True)

                    col_a1, col_a2, col_a3 = st.columns([3, 2, 2])
                    with col_a1:
                        if not p.get("thesis"):
                            st.caption("AI membaca naskah utuh, sekitar 1 menit per paper.")
                    with col_a2:
                        if not p.get("thesis"):
                            if st.button("Analisis", key=f"btn_an_single_{idx}_{p.get('file')}", type="primary", use_container_width=True):
                                with st.spinner(f"Menganalisis '{title[:35]}...'"):
                                    try:
                                        _analyze.analyze_single_paper(p.get("file"), model=config.LLM_MODEL, lang="id")
                                        db.sync_all()
                                        st.success("Analisis selesai.")
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Analisis gagal: {err}")
                    with col_a3:
                        if p.get("url"):
                            st.link_button("Buka sumber", p["url"], use_container_width=True)

                    # Logic expander
                    with st.expander("Lihat detail analisis", expanded=False):
                        render_analysis_detail(p)
                        if p.get("thesis") and st.toggle("Cek ke PDF & koreksi peneliti", key=f"rv_on_{idx}_{p.get('file')}"):
                            render_analysis_review(p, f"{idx}_{p.get('file')}")

                        # Citations
                        apa_ref = _citations.format_apa(p)
                        chicago_ref = _citations.format_chicago_bib(p)
                        in_text_ref = _citations.format_in_text_apa(p)
                        with st.expander("Format Sitasi Akademik Standar (APA 7th & Chicago 17th)"):
                            st.markdown(f"**APA 7th Reference:**")
                            st.code(apa_ref, language="text")
                            st.markdown(f"**Chicago 17th Bibliography:**")
                            st.code(chicago_ref, language="text")
                            st.markdown(f"**Sitasi Dalam Teks (In-Text APA):** `{in_text_ref}`")

                        # Authors: researcher can correct them; manual names are never overwritten
                        with st.expander("Ubah penulis"):
                            src = p.get("authors_source") or ""
                            src_label = {"manual": "diisi peneliti", "metadata": "dari sumber unduhan", "doi": "dari DOI",
                                         "arxiv": "dari arXiv", "openalex": "dari OpenAlex", "crossref": "dari Crossref",
                                         "pdf_ai": "dibaca AI dari halaman pertama PDF, mohon dicek"}.get(src, "belum ada")
                            st.caption(f"Sumber: {src_label}")
                            new_authors = st.text_area("Satu nama per baris", value=chr(10).join(p_authors),
                                                       key=f"authors_edit_{p.get('file')}", height=100)
                            if st.button("Simpan penulis", key=f"btn_save_authors_{p.get('file')}"):
                                db.set_authors(p.get("file"), _authors.parse_input(new_authors))
                                st.success("Penulis disimpan.")
                                st.rerun()

                        # Faculty reallocation
                        with st.expander("Ubah Pemetaan Fakultas untuk Paper Ini"):
                            col_re1, col_re2 = st.columns([3, 1])
                            new_fac = col_re1.selectbox(
                                "Pindahkan ke Fakultas:",
                                [f.id for f in faculty_list],
                                index=[f.id for f in faculty_list].index(p_faculty) if p_faculty in [f.id for f in faculty_list] else 0,
                                format_func=lambda x: faculty_labels.get(x, x),
                                key=f"fac_change_{p.get('file')}"
                            )
                            if col_re2.button("Simpan", key=f"btn_save_fac_{p.get('file')}", use_container_width=True):
                                db.update_paper_faculty(p.get("file"), new_fac)
                                st.success(f"Fakultas diperbarui ke: {faculty_labels.get(new_fac)}")
                                st.rerun()

                        # Re-analyze on demand
                        if p.get("thesis"):
                            with st.expander("Bedah Ulang Naskah Ini (Deep Scan v3)"):
                                st.caption("Jalankan ulang analisis AI jika ingin memperbarui hasil bedah naskah dengan prompt v3 terbaru (metodologi riset & kutipan dari bab pembahasan).")
                                if st.button("Jalankan Ulang Analisis AI", key=f"btn_re_an_{idx}_{p.get('file')}", use_container_width=True):
                                    with st.spinner(f"Menganalisis ulang '{title[:35]}...' dengan AI ({config.LLM_MODEL})..."):
                                        try:
                                            _analyze.analyze_single_paper(p.get("file"), model=config.LLM_MODEL, lang="id", force=True)
                                            db.sync_all()
                                            st.success("Pembedahan ulang naskah selesai!")
                                            st.rerun()
                                        except Exception as err:
                                            st.error(f"Gagal membedah ulang: {err}")

    with tab_pe3:
        from cosmolab.ui.pages import fulltext as _fulltext

        _fulltext.render_search()

    with tab_pe4:
        from cosmolab.ui.pages import export as _export

        _export.render_citation_export()

    with tab_pe2:
        st.caption("Ringkasan semua paper dalam satu tabel: penulis, tahun, inti paper, premis, dan keberatan.")

        matrix_data = _matrix.build_literature_matrix(selected_faculty_id)

        if not matrix_data:
            st.info("Belum ada paper untuk ditampilkan dalam matriks.")
        else:
            col_m_tb1, col_m_tb2, col_m_tb3 = st.columns(3)
            
            csv_file = _matrix.export_matrix_csv(matrix_data)
            csv_bytes = csv_file.read_bytes()
            
            md_file = _matrix.export_matrix_markdown(matrix_data)
            md_text = md_file.read_text(encoding="utf-8")

            with col_m_tb1:
                st.download_button(
                    "Unduh CSV",
                    data=csv_bytes,
                    file_name=csv_file.name,
                    mime="text/csv",
                    use_container_width=True
                )
            with col_m_tb2:
                st.download_button(
                    "Unduh Markdown",
                    data=md_text,
                    file_name=md_file.name,
                    mime="text/markdown",
                    use_container_width=True
                )
            with col_m_tb3:
                if st.button("Simpan ke Obsidian", key="btn_save_matrix_obsidian", use_container_width=True):
                    obs_out = _matrix.export_matrix_obsidian(matrix_data, faculty_labels.get(selected_faculty_id, "Semua Fakultas"))
                    st.success(f"Tersimpan di Obsidian: `{obs_out.name}`")

            # Audit Kebaruan Pustaka (Standar Dikti / Scopus 5 Tahun Terakhir)
            recency = _matrix.calculate_recency_compliance(matrix_data, threshold_years=5)
            with st.container(border=True):
                col_rc1, col_rc2, col_rc3 = st.columns([3, 3, 4])
                col_rc1.metric("Terbit 5 tahun terakhir", f"{recency['percentage']}%", border=False)
                col_rc2.metric(f"Sejak {recency['cutoff_year']}", f"{recency['recent_count']} / {recency['total']}", border=False)
                with col_rc3:
                    st.markdown(f"**Kebaruan pustaka:** {_EMOJI_RE.sub('', str(recency['status_label'])).strip()}")
                    st.caption(recency['message'])

            display_rows = []
            for r in matrix_data:
                display_rows.append({
                    "No": r["no"],
                    "Penulis & Tahun": f"{r['author']} ({r['year']})",
                    "Judul": r["title"],
                    "Fakultas": r["faculty"],
                    "Sikap": r["stance"],
                    "Tesis": r["thesis"],
                    "Premis Inti": r["premises"],
                    "Objeksi": r["key_objection"],
                })
            with st.container(border=True):
                render_table(display_rows, height=520)
