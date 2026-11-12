"""Dashboard page: Diagram Argumen."""

from pathlib import Path
import streamlit as st
from cosmolab import export
from cosmolab.ui.components import render_hero
from cosmolab.ui.components import render_mermaid
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Diagram Argumen."""
    papers = ctx.papers
    render_hero(
        title="Visualisasi Pohon Argumen (Mermaid)",
        subtitle="Visualisasi alur silogisme formal secara grafis: Tesis → Premis → Kesimpulan → Objeksi → Pertahanan.",
        icon="",
        badges=[
            {"icon": "", "text": "Formal Syllogism Graph", "class": "hero-badge-primary"},
            {"icon": "", "text": "Counter-Argument Topology", "class": "hero-badge-accent"}
        ]
    )

    paper_choices = [p["file"] for p in papers if p.get("thesis")]
    if not paper_choices:
        st.warning("Belum ada paper yang selesai dianalisis di fakultas ini.")
    else:
        with st.container(border=True):
            selected_file = st.selectbox("Pilih Paper untuk Divisualisasikan:", paper_choices)
        
        stem = Path(selected_file).stem
        mermaid_code = export.generate_mermaid_graph(stem)

        st.markdown(f"### Diagram Logika: *{stem}*")
        render_mermaid(mermaid_code)

        with st.expander("Lihat Kode Sumber Mermaid"):
            st.code(mermaid_code, language="mermaid")
