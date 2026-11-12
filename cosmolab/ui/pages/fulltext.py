"""Dashboard page: Full-Text Search."""

import html
import streamlit as st
from cosmolab import db
from cosmolab import retrieval as _retrieval
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Full-Text Search."""
    render_hero(
        title="Pencarian Cerdas Korpus (Hybrid Semantic & FTS5)",
        subtitle="Pencarian berbobot multi-dimensi (judul, tesis, premis) dipadukan dengan ekspansi semantik RRF.",
        icon="",
        badges=[
            {"icon": "", "text": "FTS5 BM25 Weighted", "class": "hero-badge-primary"},
            {"icon": "", "text": "Hybrid RRF Semantic", "class": "hero-badge-accent"}
        ]
    )

    with st.container(border=True):
        col_s1, col_s2 = st.columns([3, 1])
        search_query = col_s1.text_input("Ketik Kata Kunci / Pertanyaan Riset:", placeholder="contoh: apakah alam semesta punya awal mula, causality, hilbert, theodicy...")
        limit_count = col_s2.slider("Maksimal Hasil:", min_value=3, max_value=20, value=8)
        use_hybrid = st.checkbox("Gunakan Hybrid Semantic RRF (Paham Bahasa Indonesia & Konsep Abstrak)", value=True)

    if search_query:
        with st.spinner("Mencari paper yang relevan..."):
            if use_hybrid:
                results = _retrieval.hybrid_search(search_query, limit=limit_count, expand_concepts=True)
            else:
                results = db.search(search_query, limit=limit_count)

        if not results:
            st.warning(f"Tidak ada paper yang cocok dengan kata kunci: '{search_query}'")
        else:
            mode_badge = "Hybrid RRF Semantic" if use_hybrid else "Exact Weighted FTS5"
            st.success(f"Ditemukan **{len(results)}** paper relevan via **{mode_badge}**:")
            for r in results:
                with st.container(border=True):
                    st.markdown(f"#### {r.get('title')} ({r.get('year', 'n.d.')})")
                    score_txt = f" | RRF Score: `{r.get('rrf_score')}`" if "rrf_score" in r else ""
                    st.caption(f"Tipe: `{r.get('argument_type') or '-'}` | Stance: `{r.get('supports_or_critiques') or '-'}` | Fakultas: `{r.get('faculty') or '-'}`{score_txt}")
                    if r.get("thesis"):
                        st.info(f"**Tesis Utama:** {r.get('thesis')}")
                    if r.get("key_objection"):
                        st.warning(f"**Objeksi Kunci:** {r.get('key_objection')}")
                    if r.get("snippet"):
                        st.markdown(f"**Kutipan Teks:** ...*{r.get('snippet')}*...")
                    if r.get("file"):
                        try:
                            passages = _retrieval.find_grounded_passages(r["file"], search_query, top_k=1)
                            if passages:
                                psg = passages[0]
                                psg_text = html.escape(psg['verbatim'])
                                st.caption(f"📍 **{psg['page_label']}**: *\"{psg_text}\"*")
                        except Exception:
                            pass
