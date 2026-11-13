"""Search the full text of the collection. Shown as a tab in Koleksi paper."""

import html
import streamlit as st
from cosmolab import db
from cosmolab import retrieval as _retrieval
from cosmolab.home import METHOD_LABELS
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Old menu entry; the same search is a tab in Koleksi paper."""
    render_hero(title="Cari di Naskah", subtitle="Cari kata atau konsep di teks lengkap semua paper koleksi.")
    render_search()


def render_search():
    with st.container(border=True):
        col_s1, col_s2 = st.columns([3, 1])
        search_query = col_s1.text_input("Kata kunci atau pertanyaan",
                                         placeholder="contoh: literasi keuangan, motivasi belajar, data pribadi")
        limit_count = col_s2.slider("Jumlah hasil", min_value=3, max_value=20, value=8)
        use_hybrid = st.checkbox("Cari juga yang maknanya mirip, tidak harus kata yang sama", value=True)

    if search_query:
        with st.spinner("Mencari paper yang relevan..."):
            if use_hybrid:
                results = _retrieval.hybrid_search(search_query, limit=limit_count, expand_concepts=True)
            else:
                results = db.search(search_query, limit=limit_count)

        if not results:
            st.warning(f"Tidak ada paper yang cocok dengan kata kunci: '{search_query}'")
        else:
            st.success(f"Ditemukan **{len(results)}** paper.")
            for r in results:
                with st.container(border=True):
                    st.markdown(f"#### {r.get('title')} ({r.get('year', 'n.d.')})")
                    st.caption(f"Jenis penelitian: {METHOD_LABELS.get(r.get('argument_type'), r.get('argument_type') or '-')}"
                               f" · Bidang: {r.get('faculty') or '-'}")
                    if r.get("thesis"):
                        st.info(f"**Inti paper:** {r.get('thesis')}")
                    if r.get("snippet"):
                        st.markdown(f"**Cuplikan:** ...*{r.get('snippet')}*...")
                    if r.get("file"):
                        try:
                            passages = _retrieval.find_grounded_passages(r["file"], search_query, top_k=1)
                            if passages:
                                psg = passages[0]
                                psg_text = html.escape(psg['verbatim'])
                                st.caption(f"📍 **{psg['page_label']}**: *\"{psg_text}\"*")
                        except Exception:
                            pass
