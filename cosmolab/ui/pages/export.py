"""Dashboard page: Ekspor Data & Flashcards."""

import streamlit as st
from cosmolab import db
from cosmolab import export
from cosmolab import citations as _citations
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render_citation_export():
    """Reference files for Zotero, Mendeley and LaTeX. Shown as a tab in Koleksi paper."""
    st.caption("Daftar pustaka seluruh koleksi untuk diimpor ke Zotero, Mendeley, atau LaTeX.")
    col_b, col_r = st.columns(2)
    with col_b, st.container(border=True):
        st.markdown("**BibTeX (.bib)**: Zotero dan LaTeX")
        if st.button("Buat file .bib", key="koleksi_bib", width="stretch"):
            st.session_state["koleksi_bib"] = export.export_bibtex().read_text(encoding="utf-8")
        if st.session_state.get("koleksi_bib"):
            st.download_button("Unduh references.bib", data=st.session_state["koleksi_bib"], file_name="references.bib",
                               mime="text/plain", width="stretch", on_click="ignore")
    with col_r, st.container(border=True):
        st.markdown("**RIS (.ris)**: Zotero dan Mendeley")
        if st.button("Buat file .ris", key="koleksi_ris", width="stretch"):
            path = _citations.export_ris(db.get_all_papers_with_analyses())
            st.session_state["koleksi_ris"] = path.read_text(encoding="utf-8")
        if st.session_state.get("koleksi_ris"):
            st.download_button("Unduh references.ris", data=st.session_state["koleksi_ris"], file_name="references.ris",
                               mime="text/plain", width="stretch", on_click="ignore")


def render(ctx: AppContext):
    """Old menu entry (no longer in the menu): every export, including Obsidian and Anki."""
    render_hero(
        title="Ekspor Data",
        subtitle="Daftar pustaka untuk Zotero dan Mendeley, catatan untuk Obsidian, dan kartu hafalan untuk Anki.",
    )

    col_e1, col_e2, col_e3, col_e4 = st.columns(4)

    with col_e1:
        with st.container(border=True):
            st.markdown("### Ekspor BibTeX")
            st.write("Format standar untuk **LaTeX & Zotero**.")
            if st.button("Generate .bib", use_container_width=True):
                bib_path = export.export_bibtex()
                st.success(f"Berhasil!")
                st.download_button(
                    "Unduh .bib",
                    data=bib_path.read_text(encoding="utf-8"),
                    file_name="references.bib",
                    mime="text/plain",
                    use_container_width=True
                )

    with col_e2:
        with st.container(border=True):
            st.markdown("### Ekspor RIS")
            st.write("Format standar untuk **Zotero & Mendeley**.")
            if st.button("Generate .ris", use_container_width=True):
                all_p = db.get_all_papers_with_analyses()
                ris_path = _citations.export_ris(all_p)
                st.success(f"Berhasil!")
                st.download_button(
                    "Unduh .ris",
                    data=ris_path.read_text(encoding="utf-8"),
                    file_name="references.ris",
                    mime="text/plain",
                    use_container_width=True
                )

    with col_e3:
        with st.container(border=True):
            st.markdown("### Ekspor Obsidian")
            st.write("Catatan Markdown berformat `[[wikilinks]]`.")
            if st.button("Generate Vault", use_container_width=True):
                vault_path = export.export_obsidian()
                st.success(f"Berhasil!")
                st.info("Buka Obsidian, lalu pilih **Open folder as vault** ke `data/obsidian`.")

    with col_e4:
        with st.container(border=True):
            st.markdown("### Active Recall")
            st.write("Flashcards Spaced Repetition untuk **Anki**.")
            if st.button("Generate Cards", use_container_width=True):
                fc_path = export.export_flashcards_to_obsidian()
                st.success(f"Berhasil!")
                st.download_button(
                    "Unduh Cards.md",
                    data=fc_path.read_text(encoding="utf-8"),
                    file_name="Cosmology_Active_Recall_Cards.md",
                    mime="text/plain",
                    use_container_width=True
                )
