"""Dashboard page: Roadmap Belajar & Kurikulum."""

import streamlit as st
from cosmolab import config
from cosmolab import faculties as _faculties
from cosmolab import curriculum as _curriculum
from cosmolab.ui.components import _e
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Roadmap Belajar & Kurikulum."""
    selected_faculty_id = ctx.selected_faculty_id
    render_hero(
        title="Kurikulum & Silabus Progresif (The Academic Dean)",
        subtitle="Peta jalan intelektual 4-tingkat berbasis perpaduan tradisi Turāth Kalam dan filsafat analitik kontemporer untuk penguasaan sistematis.",
        icon="",
        badges=[
            {"icon": "", "text": "4-Tier Progression", "class": "hero-badge-primary"},
            {"icon": "", "text": "Dynamic AI Dean", "class": "hero-badge-accent"},
            {"icon": "", "text": "Obsidian Export Ready", "class": "hero-badge-model"}
        ]
    )

    tab_road1, tab_road2 = st.tabs(["Roadmap Fakultas Terstruktur", "Generator Silabus AI untuk Topik Bebas"])

    with tab_road1:
        cur_fac_id = selected_faculty_id if selected_faculty_id != "all" else "ilahiyyat"
        cur_fac_obj = _faculties.get_faculty(cur_fac_id)
        
        with st.container(border=True):
            st.markdown(f"### Kurikulum: {cur_fac_obj.name}")
            st.caption(cur_fac_obj.full_desc)

        levels = _curriculum.get_learning_roadmap(cur_fac_id)

        for idx_l, lvl in enumerate(levels):
            with st.container(border=True):
                st.markdown(f"#### **{lvl['title']}**")
                st.info(lvl['description'])
                if not lvl['papers']:
                    st.caption("Belum ada paper di level ini dalam korpus lokal. Gunakan tab 'Panen Paper Ilmiah' untuk menambah paper.")
                else:
                    for p_idx, p in enumerate(lvl['papers'], 1):
                        col_p1, col_p2, col_p3 = st.columns([4, 1, 1])
                        col_p1.markdown(f"**{p_idx}. [{p['year']}] {p['title']}**")
                        col_p1.caption(f"*Tesis:* {p['thesis'][:150]}...")
                        col_p2.write(f"Tipe: `{p['argument_type']}`")
                        col_p3.markdown(f"<span class='stance-pill stance-{_e(p['stance'])}'>{_e(p['stance'])}</span>", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:4px 0; border:none; border-top:1px dashed #E2E8F0;'>", unsafe_allow_html=True)

        with st.expander("Rujukan Standar & Debat Inti Fakultas Ini", expanded=False):
            col_ref1, col_ref2 = st.columns(2)
            with col_ref1:
                st.markdown("#### Naskah Turāth Klasik:")
                for r in cur_fac_obj.classic_references:
                    st.markdown(f"- {r}")
            with col_ref2:
                st.markdown("#### Riset Analitik Modern:")
                for r in cur_fac_obj.modern_references:
                    st.markdown(f"- {r}")

    with tab_road2:
        with st.container(border=True):
            st.markdown("### Generator Silabus AI: Rancang Kurikulum Topik Apa Saja")
            st.caption("Ketik topik dari bidang apa pun yang ingin Anda pelajari secara mendalam. Dekan AI akan menyusun silabus 4 tingkat, bacaan wajib, dilema Sokrates, dan flashcards.")

            col_tp1, col_tp2 = st.columns([2, 1])
            custom_topic = col_tp1.text_input("Judul Topik / Mata Kuliah Baru:", placeholder="contoh: Teori Kausalitas Al-Ghazali vs Hume, Problem of Evil, Argumen Jiwa Ibn Sina...")
            custom_desc = col_tp2.text_input("Fokus Khusus (Opsional):", placeholder="contoh: Komparasi dengan mekanika kuantum")

            if st.button("Susun Silabus Kurikulum Lengkap", type="primary", use_container_width=True):
                if not custom_topic.strip():
                    st.error("Silakan masukkan topik terlebih dahulu.")
                else:
                    with st.spinner("Dekan Akademik AI sedang merancang silabus, memetakan naskah klasik, dan menyusun kartu nalar..."):
                        syllabus_data = _curriculum.generate_ai_syllabus(custom_topic, custom_desc, model=config.LLM_MODEL)
                        st.session_state["active_syllabus"] = syllabus_data

        if "active_syllabus" in st.session_state:
            syl = st.session_state["active_syllabus"]
            with st.container(border=True):
                st.markdown(f"## Silabus: **{syl.get('course_title')}**")
                st.markdown(f"**Domain Bidang:** `{syl.get('faculty_domain', 'Multidisipliner')}`")
                st.info(f"**Visi Pedagogis:**\n\n{syl.get('pedagogical_vision', '')}")

                st.markdown("### Tahapan Belajar 4-Tingkat:")
                for t in syl.get("tiers", []):
                    t_title = t.get('title', f"Level {t.get('tier_num', '-')}")
                    with st.expander(f"**{t_title}**", expanded=True):
                        st.write(t.get("description", ""))
                        if t.get("key_concepts"):
                            st.markdown("**Konsep Kunci:** " + ", ".join([f"`{c}`" for c in t["key_concepts"]]))
                        if t.get("milestone_task"):
                            st.warning(f"**Milestone Uji Nalar:** {t['milestone_task']}")

                col_rb1, col_rb2 = st.columns(2)
                with col_rb1:
                    st.markdown("#### Naskah Klasik Turāth:")
                    for r in syl.get("classic_turath_readings", []):
                        st.markdown(f"- {r}")
                with col_rb2:
                    st.markdown("#### Rujukan Akademik Modern:")
                    for r in syl.get("modern_academic_readings", []):
                        st.markdown(f"- {r}")

                if syl.get("socratic_dilemma"):
                    st.markdown("#### Dilema Sokrates Inti:")
                    st.info(syl["socratic_dilemma"])

                if syl.get("flashcards"):
                    st.markdown(f"#### Kartu Active Recall ({len(syl['flashcards'])} kartu):")
                    for fc in syl["flashcards"]:
                        st.markdown(f"- **Q:** {fc.get('question')}  \n  *A:* {fc.get('answer')}")

                if st.button("Simpan Silabus ke Obsidian Vault", type="primary"):
                    out_p = _curriculum.save_syllabus_to_obsidian(syl)
                    st.success(f"Silabus berhasil disimpan ke Obsidian: `{out_p.name}`")
