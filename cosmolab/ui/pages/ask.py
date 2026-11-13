"""Dashboard page: Tanya Korpus & Sintesis."""

import html
import streamlit as st
from cosmolab import config
from cosmolab import export
from cosmolab import ask as _ask
from cosmolab import ask_agent as _ask_agent
from cosmolab.ui.components import render_hero
from cosmolab.ui.claims import run_claim_check
from cosmolab.ui.claims import render_claim_report
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Tanya Korpus & Sintesis."""
    faculty_labels = ctx.faculty_labels
    selected_faculty_id = ctx.selected_faculty_id
    active_fac_name = faculty_labels.get(selected_faculty_id, "Universal")
    render_hero(
        title="Tanya Koleksi",
        subtitle=f"Ajukan pertanyaan riset. AI menjawab hanya dari paper di koleksi (bidang: <b>{active_fac_name}</b>) dan menyebutkan rujukannya.",
        icon="",
    )

    fac_suggestions = {
        "ilahiyyat": [
            "Bagaimana para peneliti membantah klaim bahwa fluktuasi vakum kuantum membatalkan hukum kausalitas?",
            "Apa bantahan matematika terhadap keberatan Hilbert's Hotel pada ketakterhinggaan waktu lampau?",
            "Mengapa hipotesis Multiverse dianggap tidak menyelesaikan persoalan fine-tuning kosmos?"
        ],
        "epistemologi": [
            "Bagaimana Al-Ghazali dalam Al-Munqidh menyelesaikan keraguan terhadap pancaindra dan akal?",
            "Apa perbedaan epistemologis antara silogisme Burhani dengan Jadal dalam pembuktian akidah?",
            "Bagaimana Reformed Epistemology Alvin Plantinga membela rasionalitas iman tanpa bukti deduktif?"
        ],
        "kausalitas": [
            "Apa perbedaan mendasar antara doktrin Okasionalisme Al-Ghazali dengan Skeptisisme David Hume tentang sebab-akibat?",
            "Bagaimana teori Kasb mazhab Asy'ari menjelaskan kebebasan memilih di bawah kedaulatan mutlak takdir?",
            "Apakah indeterminisme fisika kuantum membuka ruang logis bagi tindakan Ilahi (Divine Action) di alam semesta?"
        ],
        "teodisi": [
            "Bagaimana pembelaan Alvin Plantinga (Free Will Defense) menghadapi argumen logis kejahatan dari J.L. Mackie?",
            "Apa respon teisme analitik terhadap problem penderitaan tanpa faedah (Gratuitous Evil) William Rowe?",
            "Apa makna doktrin Al-Ghazali 'Laysa fi al-imkan abda' mimma kan' dalam konteks teodisi?"
        ],
        "falsafah_jiwa": [
            "Bagaimana Argumen Manusia Terbang (The Flying Man) Ibn Sina membuktikan eksistensi jiwa immaterial?",
            "Mengapa 'The Hard Problem of Consciousness' menjadi batu sandungan bagi materialisme dan fisikalisme?",
            "Dapatkah kecerdasan buatan (AI) memiliki kesadaran sejati (qualia) menurut filsafat pikiran Islam?"
        ],
        "nubuwwat": [
            "Bagaimana tradisi teologi Islam merespons kritik probabilitas David Hume mengenai mukjizat?",
            "Apa distingsi logis antara hal yang mustahil secara akal (Mustahil Aqli) vs mustahil secara kebiasaan (Mustahil 'Adi)?",
            "Bagaimana hermeneutika Ibn Rushd (Fasl al-Maqal) menyelesaikan pertentangan teks wahyu dengan akal demonstratif?"
        ],
    }

    generic_suggestions = [
        "Apa temuan utama paper-paper di koleksi ini, dan di mana mereka saling bertentangan?",
        "Metodologi apa saja yang dipakai, dan apa kelemahan masing-masing?",
        "Pertanyaan apa yang belum dijawab oleh paper-paper ini?",
    ]
    active_sug_list = fac_suggestions.get(selected_faculty_id, generic_suggestions)
    
    with st.container(border=True):
        selected_sug = st.selectbox("Contoh pertanyaan (opsional)", ["(Ketik pertanyaan sendiri...)"] + active_sug_list)

        user_q = st.text_area(
            "Pertanyaan Anda",
            value=selected_sug if selected_sug != "(Ketik pertanyaan sendiri...)" else "",
            placeholder="Ketik pertanyaan riset Anda di sini...",
            height=95
        )

        col_r1, col_r2 = st.columns([1, 2])
        k_val = col_r1.slider("Jumlah paper yang dibaca", min_value=2, max_value=8, value=6)
        rag_mode = col_r2.radio(
            "Jenis jawaban",
            ["Agentic", "Classic"],
            format_func=lambda x: "Mendalam: bandingkan pendapat pro dan kontra" if x == "Agentic" else "Cepat: jawaban ringkas",
            horizontal=True
        )

        check_claims = st.checkbox(
            "Periksa setiap klaim terhadap isi paper", value=True,
            help="Setiap kalimat yang menyebut sumber dicek: apakah isi paper itu benar-benar mendukungnya. Menambah sekitar 10–30 detik.",
        )

        ask_btn = st.button("Tanyakan", type="primary", use_container_width=True)

    if ask_btn:
        if not user_q.strip():
            st.error("Silakan masukkan pertanyaan terlebih dahulu.")
        else:
            if "Agentic" in rag_mode:
                with st.spinner("Membaca paper dan membandingkan pendapat. Biasanya 30–90 detik..."):
                    try:
                        res = _ask_agent.ask_agentic(question=user_q, model=config.LLM_MODEL, top_k=k_val)
                        st.session_state.pop("classic_answer", None)
                        st.session_state["agentic_answer"] = {
                            "q": user_q,
                            "res": res,
                            "claims": run_claim_check(res.get("answer", ""), res.get("referenced_papers")) if check_claims else None,
                        }
                    except Exception as e:
                        st.error(f"Gagal memproses pertanyaan: {e}")
            else:
                with st.spinner("Membaca paper. Biasanya 10–30 detik..."):
                    try:
                        answer = _ask.ask(question=user_q, model=config.LLM_MODEL, top_k=k_val)
                        st.session_state.pop("agentic_answer", None)
                        st.session_state["classic_answer"] = {
                            "q": user_q,
                            "answer": answer,
                            "claims": run_claim_check(answer) if check_claims else None,
                        }
                    except Exception as e:
                        st.error(f"Gagal memproses pertanyaan: {e}")

    if "agentic_answer" in st.session_state:
        ans_data = st.session_state["agentic_answer"]
        res = ans_data["res"]

        with st.expander("Langkah kerja AI", expanded=False):
            for idx, step in enumerate(res.get("thought_steps", []), 1):
                st.markdown(f"**Langkah {idx}:** {step}")

        with st.chat_message("assistant", avatar=":material/balance:"):
            st.markdown(res.get("answer", ""))

        render_claim_report(ans_data.get("claims"))

        ref_papers = res.get("referenced_papers", [])
        if ref_papers:
            with st.expander(f"Paper yang dipakai ({len(ref_papers)})", expanded=False):
                for p in ref_papers:
                    st.markdown(f"- **[{p.get('year', 'n.d.')}] {p.get('title')}** | Sikap: `{p.get('supports_or_critiques')}`")
                    if p.get("thesis"):
                        st.caption(f"  *Tesis:* {p.get('thesis')}")

        grounded_cits = res.get("grounded_citations", [])
        if grounded_cits:
            with st.expander(f"Bukti Verbatim dan Halaman PDF Terverifikasi ({len(grounded_cits)})", expanded=True):
                st.caption("Kutipan langsung dari naskah PDF asli yang diverifikasi oleh sistem Page-Aware Grounding:")
                for gc in grounded_cits:
                    st.markdown(
                        f'''<div style="background-color: rgba(28, 100, 242, 0.05); border-left: 4px solid #1c64f2; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;">
                            <div style="font-size: 0.85rem; font-weight: 600; color: #1c64f2; margin-bottom: 3px;">
                                📄 {html.escape(gc.get('paper_title', ''))} ({gc.get('year', '')}) &mdash; <span style="background: #e1effe; color: #1e429f; padding: 1px 6px; border-radius: 4px;">{gc.get('page_label', '')}</span>
                            </div>
                            <div style="font-size: 0.88rem; font-style: italic; color: #374151;">
                                &ldquo;{html.escape(gc.get('verbatim', ''))}&rdquo;
                            </div>
                        </div>''',
                        unsafe_allow_html=True
                    )

        if st.button("Simpan jawaban ke catatan Obsidian", key="btn_save_agent_obsidian"):
            saved_path = export.export_agent_synthesis_to_obsidian(ans_data["q"], res.get("answer", ""), ref_papers)
            st.success(f"Berhasil disimpan ke Obsidian: `{saved_path.name}`")

    elif "classic_answer" in st.session_state:
        ans_data = st.session_state["classic_answer"]
        with st.chat_message("assistant", avatar=":material/description:"):
            st.markdown(ans_data["answer"])
        render_claim_report(ans_data.get("claims"))
