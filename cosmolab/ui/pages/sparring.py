"""Dashboard page: Arena Sparring Nalar."""

import streamlit as st
from cosmolab import config
from cosmolab import sparring as _sparring
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Arena Sparring Nalar."""
    selected_faculty_id = ctx.selected_faculty_id
    render_hero(
        title="Arena Sparring & Pelatihan Nalar Kritis",
        subtitle="Uji ketahanan tesis dan silogisme Anda berhadapan langsung dengan para raksasa pemikiran: Hume, Al-Ghazali, Ibn Sina, Mackie, Dennett, dan The Ruthless Critic.",
        icon="",
        badges=[
            {"icon": "", "text": "Intellectual Duel", "class": "hero-badge-primary"},
            {"icon": "", "text": "Enthymeme Detection", "class": "hero-badge-accent"},
            {"icon": "", "text": "Socratic Method", "class": "hero-badge-model"}
        ]
    )

    spar_tab1, spar_tab2 = st.tabs(["Sparring dengan Lawan Debat Filosofis", "The Ruthless Critic (Devil's Advocate Tesis Mandiri)"])

    with spar_tab1:
        personas = _sparring.list_personas()
        
        with st.container(border=True):
            col_pers, col_dil = st.columns([1, 2])
            
            with col_pers:
                selected_persona_id = st.selectbox(
                    "Pilih Lawan Tanding:",
                    [p["id"] for p in personas],
                    format_func=lambda x: f"{_sparring.get_persona(x)['icon']} {_sparring.get_persona(x)['name']}"
                )
                cur_persona = _sparring.get_persona(selected_persona_id)
                st.markdown(f"""
                <div class="persona-card">
                    <div class="persona-header">{cur_persona['icon']} {cur_persona['name']}</div>
                    <div class="persona-title">{cur_persona['title']}</div>
                    <div class="persona-desc">{cur_persona['desc']}</div>
                </div>
                """, unsafe_allow_html=True)

            with col_dil:
                dilemmas = _sparring.get_dilemmas_by_faculty(selected_faculty_id)
                dilemma_options = ["(Ketik Dilema Bebas Sendiri)"] + [d["topic"] for d in dilemmas]
                chosen_dilemma_title = st.selectbox("Pilih Kasus Dilema:", dilemma_options)
                
                if chosen_dilemma_title == "(Ketik Dilema Bebas Sendiri)":
                    dilemma_text = st.text_area("Tuliskan Konteks / Dilema Bebas:", value="Apakah konsep keniscayaan kausalitas itu nyata atau sekadar kebiasaan indrawi?", height=85)
                else:
                    matched_d = next(d for d in dilemmas if d["topic"] == chosen_dilemma_title)
                    dilemma_text = matched_d["dilemma"]
                    st.info(dilemma_text)

            user_statement = st.text_area(
                "Tuliskan Argumen / Jawaban Anda untuk Menghadapi Lawan Tanding:",
                height=130,
                placeholder="Ketik penalaran logis, premis, atau sanggahan Anda di sini..."
            )

            launch_duel = st.button("Luncurkan Sparring Nalar!", type="primary", use_container_width=True)

        if launch_duel:
            if not user_statement.strip():
                st.error("Silakan tuliskan argumen Anda terlebih dahulu.")
            else:
                with st.spinner(f"{cur_persona['name']} sedang menganalisis titik lemah logika Anda..."):
                    res = _sparring.spar_with_persona(
                        user_argument=user_statement,
                        persona_id=selected_persona_id,
                        dilemma_context=dilemma_text,
                        faculty_id=selected_faculty_id,
                        model=config.LLM_MODEL
                    )
                    st.session_state["last_spar_result"] = {
                        "user_arg": user_statement,
                        "persona": cur_persona,
                        "res": res
                    }

        if "last_spar_result" in st.session_state:
            spar_data = st.session_state["last_spar_result"]
            p_obj = spar_data["persona"]
            r_obj = spar_data["res"]

            st.markdown("### Arena Duel Pemikiran:")
            
            with st.chat_message("user"):
                st.markdown(f"**Tesis / Argumen Anda:**\n\n{spar_data['user_arg']}")

            with st.chat_message("assistant", avatar=":material/person:"):
                st.markdown(f"#### {p_obj['icon']} Respons {p_obj['name']} ({p_obj['title']}):")
                st.markdown(r_obj.get("feedback", ""))

            if r_obj.get("referenced_papers"):
                with st.expander("Rujukan Paper Korpus yang Digunakan"):
                    for p in r_obj["referenced_papers"]:
                        st.markdown(f"- **[{p.get('year', 'n.d.')}] {p.get('title')}** | Sikap: `{p.get('supports_or_critiques')}`")

    with spar_tab2:
        with st.container(border=True):
            st.markdown("### The Ruthless Critic: Stress-Test Tesis Mandiri")
            st.caption("AI akan membongkar premis tersembunyi (*enthymeme*), menyerang celah logika, dan memberikan rekomendasi pembenahan tesis agar *bulletproof*.")

            default_arg = "Saya berpendapat bahwa mekanika kuantum tidak membatalkan premis kausalitas Kalam, karena fluktuasi vakum kuantum tetap memerlukan ruang hampa yang berenergi sebagai sebab materialnya, bukan ketiadaan mutlak."
            user_arg = st.text_area("Tuliskan Draf Tesis / Argumen Anda:", value=default_arg, height=110)

            run_critic = st.button("Bedah & Serang Tesis Saya!", type="primary", use_container_width=True)

        if run_critic:
            if not user_arg.strip():
                st.error("Silakan masukkan tesis terlebih dahulu.")
            else:
                with st.spinner("The Ruthless Critic sedang mencari paper lawan di korpus dan membedah struktur logika Anda..."):
                    critique_res = _sparring.criticize_argument(user_arg, model=config.LLM_MODEL)
                    st.session_state["critic_result"] = critique_res

        if "critic_result" in st.session_state:
            with st.chat_message("assistant", avatar=":material/sports_kabaddi:"):
                st.markdown(st.session_state["critic_result"].get("feedback", ""))
