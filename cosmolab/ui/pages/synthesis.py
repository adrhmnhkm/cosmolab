"""Dashboard page: Laporan Sintesis."""

import streamlit as st
from cosmolab import config
from cosmolab import synthesize as _synthesize
from cosmolab import gap_finder as _gap_finder
from cosmolab.ui.components import active_ai
from cosmolab.ui.components import render_hero
from cosmolab.ui.components import render_client_delivery
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Laporan Sintesis."""
    selected_faculty_id = ctx.selected_faculty_id
    render_hero(
        title="Tinjauan Pustaka & Celah Riset",
        subtitle="Tinjauan pustaka dari seluruh koleksi, serta celah riset dan usulan topik baru.",
        icon="",
    )

    tab_synth1, tab_synth2 = st.tabs([
        "Tinjauan pustaka",
        "Celah riset & kebaruan"
    ])

    with tab_synth1:
        with st.container(border=True):
            col_s1, col_s2 = st.columns([1, 1])
            lang_choice = col_s1.selectbox("Bahasa", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English")
            
            col_s2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            gen_synth = col_s2.button("Buat tinjauan pustaka baru", type="primary", use_container_width=True)

        if gen_synth:
            with st.spinner("Menyusun tinjauan pustaka dari seluruh koleksi. Bisa beberapa menit..."):
                res = _synthesize.synthesize(model=config.LLM_MODEL, lang=lang_choice)
                if res.get("error"):
                    st.error(res["error"])
                elif res.get("claims_flagged", 0) > 0:
                    st.warning(f"Laporan selesai dengan catatan: {res['claims_flagged']} dari {res.get('claims_total', 0)} klaim perlu dicek.")
                else:
                    st.success("Laporan selesai dan seluruh klaim terverifikasi.")

        st.markdown("#### Laporan tersimpan")
        reports = sorted(list(config.SYNTH_DIR.glob("*.md")), reverse=True)
        if not reports:
            st.info("Belum ada laporan. Klik **Buat tinjauan pustaka baru**.")
        else:
            with st.container(border=True):
                selected_rep = st.selectbox("Pilih laporan", [r.name for r in reports])
                rep_file = config.SYNTH_DIR / selected_rep
                with st.container(height=600):
                    st.markdown(rep_file.read_text(encoding="utf-8"))
            render_client_delivery(rep_file, key=f"synth_{rep_file.stem}")

    with tab_synth2:
        with st.container(border=True):
            st.caption("AI membaca seluruh koleksi, lalu mencari perdebatan yang belum selesai, kelemahan metodologi, dan menyusun 3 usulan topik riset baru.")

            col_gap1, col_gap2 = st.columns([2, 1])
            gap_focus = col_gap1.text_input("Fokus (opsional)", placeholder="contoh: dampak terhadap UMKM di daerah")
            col_gap2.caption(f"AI: {active_ai()['label']}. Ganti di sidebar.")

            btn_find_gap = st.button("Cari celah riset", type="primary", use_container_width=True)

        if btn_find_gap:
            with st.spinner("Membaca koleksi dan mencari celah riset. Bisa beberapa menit..."):
                gap_report = _gap_finder.find_research_gaps(
                    faculty_id=selected_faculty_id,
                    custom_focus=gap_focus,
                )
                saved_gap = _gap_finder.save_gap_report(gap_report)
                st.session_state["current_gap_report"] = gap_report
                st.session_state["saved_gap_paths"] = saved_gap
                st.session_state["selected_gap_report_file"] = saved_gap["json_path"].name
                st.rerun()

        # Check existing saved gap reports in config.ROOT / "gaps"
        gaps_dir = config.ROOT / "gaps"
        saved_gap_files = sorted(list(gaps_dir.glob("*.json")), reverse=True) if gaps_dir.exists() else []

        selected_rep_json = None
        if saved_gap_files:
            st.markdown("#### Laporan Celah Riset Tersimpan")
            file_options = [f.name for f in saved_gap_files]
            
            current_choice = st.session_state.get("selected_gap_report_file")
            default_idx = file_options.index(current_choice) if current_choice in file_options else 0

            chosen_file_name = st.selectbox(
                "Pilih laporan celah riset",
                file_options,
                index=default_idx,
                key="gap_report_selector",
                format_func=lambda x: f"📄 {x.replace('gap_report_', '').replace('.json', '')}"
            )
            st.session_state["selected_gap_report_file"] = chosen_file_name
            selected_rep_json = gaps_dir / chosen_file_name

        rep = None
        md_file = None
        if selected_rep_json and selected_rep_json.exists():
            try:
                import json
                rep = json.loads(selected_rep_json.read_text(encoding="utf-8"))
                candidate_md = selected_rep_json.with_suffix(".md")
                if candidate_md.exists():
                    md_file = candidate_md
            except Exception as e:
                st.error(f"Gagal memuat laporan: {e}")
        elif "current_gap_report" in st.session_state:
            rep = st.session_state["current_gap_report"]
            saved_paths = st.session_state.get("saved_gap_paths", {})
            md_file = saved_paths.get("md_path")

        if rep:
            with st.container(border=True):
                st.markdown(f"#### Bidang: {rep.get('faculty_domain')}")
                st.info(f"**Ringkasan Eksekutif:**\n\n{rep.get('executive_summary', '')}")

                col_gp1, col_gp2 = st.columns(2)
                with col_gp1:
                    st.markdown("**Yang sudah disepakati dalam literatur**")
                    for c in rep.get("established_consensus", []):
                        st.markdown(f"- {c}")
                with col_gp2:
                    st.markdown("**Kelemahan & titik buta metodologi**")
                    for b in rep.get("methodological_blindspots", []):
                        st.markdown(f"- {b}")

                st.markdown("---")
                st.markdown("#### Perdebatan terbuka yang belum selesai (Unresolved Tensions)")
                for idx_ut, ut in enumerate(rep.get("unresolved_tensions", []), 1):
                    with st.expander(f"{idx_ut}. {ut.get('issue', 'Isu perdebatan')}", expanded=False):
                        st.write(f"**Pihak yang mendukung (Tesis):** {ut.get('thesis_side')}")
                        st.write(f"**Pihak yang mengkritik (Antitesis):** {ut.get('antithesis_side')}")
                        st.warning(f"**Mengapa belum selesai:** {ut.get('why_stuck')}")

                st.markdown("---")
                st.markdown("#### 🎯 Usulan Topik Proposal Riset Baru (High-Novelty Proposals)")
                for idx_p, prop in enumerate(rep.get("novel_research_proposals", []), 1):
                    with st.container(border=True):
                        st.markdown(f"**Usulan {idx_p}: {prop.get('title')}**")
                        col_pr1, col_pr2 = st.columns([1, 1])
                        col_pr1.caption(f"Jenjang: {prop.get('target_level', 'Tesis S2/S3')}")
                        col_pr2.caption(f"Kerangka teori: {prop.get('theoretical_framework', '-')}")
                        
                        st.write(f"**Celah yang dijawab:** {prop.get('gap_addressed')}")
                        st.write(f"**Hipotesis:** {prop.get('proposed_hypothesis')}")
                        st.write(f"**Kebaruan:** {prop.get('expected_novelty')}")
                        
                        if prop.get("research_questions"):
                            st.markdown("**Rumusan masalah:**")
                            for q in prop["research_questions"]:
                                st.markdown(f"- {q}")

                # Download Buttons & Deliverables
                if md_file and md_file.exists():
                    st.markdown("---")
                    st.markdown("##### 📥 Unduh Hasil Analisis (.md / Pustaka)")
                    col_g_dl1, col_g_dl2 = st.columns(2)
                    with col_g_dl1:
                        st.download_button(
                            "Unduh laporan celah riset (.md)",
                            data=md_file.read_text(encoding="utf-8"),
                            file_name=md_file.name,
                            mime="text/markdown",
                            use_container_width=True,
                            key=f"dl_md_{md_file.stem}"
                        )
                    with col_g_dl2:
                        st.caption(f"File markdown sumber: `{md_file.name}`")

                    # Check references files in config.ROOT
                    bib_p = config.ROOT / "references.bib"
                    ris_p = config.ROOT / "references.ris"
                    if bib_p.exists() or ris_p.exists():
                        col_ref1, col_ref2 = st.columns(2)
                        if bib_p.exists():
                            col_ref1.download_button(
                                "Unduh references.bib (LaTeX)",
                                data=bib_p.read_text(encoding="utf-8"),
                                file_name="references.bib",
                                mime="text/plain",
                                use_container_width=True,
                                key=f"dl_bib_{md_file.stem}"
                            )
                        if ris_p.exists():
                            col_ref2.download_button(
                                "Unduh references.ris (Zotero/Mendeley)",
                                data=ris_p.read_text(encoding="utf-8"),
                                file_name="references.ris",
                                mime="text/plain",
                                use_container_width=True,
                                key=f"dl_ris_{md_file.stem}"
                            )

                    # Check if ready-made Word/PDF exist in <project>/deliverables/
                    deliv_dir = config.ROOT / "deliverables"
                    if deliv_dir.exists():
                        docxs = sorted(list(deliv_dir.glob("*.docx")), key=lambda p: p.stat().st_mtime, reverse=True)
                        pdfs = sorted(list(deliv_dir.glob("*.pdf")), key=lambda p: p.stat().st_mtime, reverse=True)
                        if docxs or pdfs:
                            st.markdown("##### 📄 Berkas Resmi Klien Tersedia (Word / PDF Berkop)")
                            col_d1, col_d2 = st.columns(2)
                            if docxs:
                                d_file = docxs[0]
                                col_d1.download_button(
                                    f"Unduh DOCX: {d_file.name}",
                                    data=d_file.read_bytes(),
                                    file_name=d_file.name,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True,
                                    key=f"dl_docx_{md_file.stem}"
                                )
                            if pdfs:
                                p_file = pdfs[0]
                                col_d2.download_button(
                                    f"Unduh PDF: {p_file.name}",
                                    data=p_file.read_bytes(),
                                    file_name=p_file.name,
                                    mime="application/pdf",
                                    use_container_width=True,
                                    key=f"dl_pdf_{md_file.stem}"
                                )

                    # Render client delivery widget for fresh verification & export
                    render_client_delivery(md_file, key=f"gap_{md_file.stem}")
        elif not saved_gap_files:
            st.info("Belum ada laporan celah riset. Klik tombol **Cari celah riset** di atas.")
