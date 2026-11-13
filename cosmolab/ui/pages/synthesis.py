"""Dashboard page: Laporan Sintesis."""

import streamlit as st
from cosmolab import config
from cosmolab import synthesize as _synthesize
from cosmolab import gap_finder as _gap_finder
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
                st.success("Laporan selesai.")

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
            gap_model = col_gap2.selectbox("Kecepatan", ["deepseek-v4-pro", "gemini-3-8-flash"], format_func=lambda x: "Mendalam" if "deepseek" in x else "Cepat")

            btn_find_gap = st.button("Cari celah riset", type="primary", use_container_width=True)

        if btn_find_gap:
            with st.spinner("Membaca koleksi dan mencari celah riset. Bisa beberapa menit..."):
                gap_report = _gap_finder.find_research_gaps(
                    faculty_id=selected_faculty_id,
                    custom_focus=gap_focus,
                    model=gap_model
                )
                st.session_state["current_gap_report"] = gap_report
                saved_gap = _gap_finder.save_gap_report(gap_report)
                st.session_state["saved_gap_paths"] = saved_gap

        if "current_gap_report" in st.session_state:
            rep = st.session_state["current_gap_report"]
            saved_paths = st.session_state.get("saved_gap_paths", {})

            with st.container(border=True):
                st.markdown(f"#### Bidang: {rep.get('faculty_domain')}")
                st.info(f"**Ringkasan:**\n\n{rep.get('executive_summary', '')}")

                col_gp1, col_gp2 = st.columns(2)
                with col_gp1:
                    st.markdown("**Yang sudah disepakati**")
                    for c in rep.get("established_consensus", []):
                        st.markdown(f"- {c}")
                with col_gp2:
                    st.markdown("**Kelemahan metodologi**")
                    for b in rep.get("methodological_blindspots", []):
                        st.markdown(f"- {b}")

                st.markdown("---")
                st.markdown("#### Perdebatan yang belum selesai")
                for idx_ut, ut in enumerate(rep.get("unresolved_tensions", []), 1):
                    with st.expander(f"{idx_ut}. {ut.get('issue', 'Isu perdebatan')}", expanded=False):
                        st.write(f"**Pihak yang mendukung:** {ut.get('thesis_side')}")
                        st.write(f"**Pihak yang mengkritik:** {ut.get('antithesis_side')}")
                        st.warning(f"**Mengapa belum selesai:** {ut.get('why_stuck')}")

                st.markdown("---")
                st.markdown("#### Usulan topik riset baru")
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

                if saved_paths.get("md_path"):
                    col_g_dl1, col_g_dl2 = st.columns(2)
                    with col_g_dl1:
                        st.download_button(
                            "Unduh laporan celah riset (.md)",
                            data=saved_paths["markdown_content"],
                            file_name=saved_paths["md_path"].name,
                            mime="text/markdown",
                            use_container_width=True
                        )
                    with col_g_dl2:
                        st.caption(f"Tersimpan sebagai `{saved_paths['md_path'].name}`")
