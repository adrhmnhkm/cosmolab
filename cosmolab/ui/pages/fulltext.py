"""Search the full text of the collection. Shown as a tab in Koleksi paper."""

import html
import re
import time
import streamlit as st
from cosmolab import authors as _authors
from cosmolab import citations as _citations
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab import retrieval as _retrieval
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext
from cosmolab.ui.papers import paper_badges, render_analysis_detail

MARK_STYLE = (
    "background-color: #fef08a; color: #713f12; padding: 1px 4px; "
    "border-radius: 3px; font-weight: 600;"
)


def _format_snippet(snippet: str) -> str:
    """Format FTS snippet for web display, replacing Rich BBCode with styled HTML marks."""
    if not snippet:
        return ""
    s = snippet.replace(
        "[b][yellow]",
        f"<mark style='{MARK_STYLE}'>",
    ).replace("[/yellow][/b]", "</mark>")
    s = s.replace("[b]", "<b>").replace("[/b]", "</b>")
    s = s.replace("[yellow]", "").replace("[/yellow]", "")
    # Remove any stray unclosed tags
    s = re.sub(r"\[/?[a-zA-Z]+\]", "", s)
    return s


def _highlight_terms(text: str, query: str) -> str:
    """Highlight query terms inside a passage text using HTML <mark> tags."""
    if not text or not query:
        return html.escape(text or "")
    escaped_text = html.escape(text)
    clean_q = "".join(c if c.isalnum() or c in (" ", "-", "_") else " " for c in query).strip()
    terms = [re.escape(w) for w in clean_q.split() if len(w) >= 3 and w.lower() not in db.STOP_WORDS]
    if not terms:
        terms = [re.escape(w) for w in clean_q.split() if len(w) >= 3]
    if not terms:
        return escaped_text

    pattern = re.compile(r"(" + "|".join(terms) + r")", re.IGNORECASE)
    mark_tpl = f"<mark style='{MARK_STYLE}'>\\1</mark>"
    return pattern.sub(mark_tpl, escaped_text)


def render(ctx: AppContext):
    """Old menu entry; the same search is a tab in Koleksi paper."""
    render_hero(title="Cari di Naskah", subtitle="Cari kata atau konsep di teks lengkap semua paper koleksi.")
    render_search(faculty=ctx.selected_faculty_id)


def render_search(faculty: str | None = None):
    fac_info = _faculties.get_faculty(faculty) if faculty and faculty != "all" else None
    fac_name = fac_info.name if fac_info else None

    with st.container(border=True):
        col_s1, col_s2 = st.columns([3, 1])
        search_query = col_s1.text_input(
            "Kata kunci atau pertanyaan",
            placeholder="contoh: literasi keuangan, motivasi belajar, data pribadi",
            key="fulltext_search_q",
        )
        limit_count = col_s2.slider("Jumlah hasil", min_value=3, max_value=20, value=8, key="fulltext_limit")

        col_opt1, col_opt2 = st.columns([2, 2])
        use_hybrid = col_opt1.checkbox(
            "Cari juga yang maknanya mirip (pencarian konseptual AI)",
            value=False,
            help="Aktifkan bila ingin mencari sinonim atau konsep terkait secara semantik. "
                 "Nonaktifkan untuk pencarian kata langsung yang instan (<0.05 detik).",
            key="fulltext_hybrid",
        )

        filter_faculty = None
        if fac_name:
            scope_choice = col_opt2.radio(
                "Cakupan bidang:",
                [f"Bidang saat ini ({fac_name})", "Semua bidang paper"],
                horizontal=True,
                key="fulltext_scope",
            )
            if scope_choice.startswith("Bidang saat ini"):
                filter_faculty = faculty

    if search_query:
        spinner_msg = "Menganalisis konsep semantik dengan AI..." if use_hybrid else "Mencari di naskah paper..."
        t_start = time.perf_counter()
        with st.spinner(spinner_msg):
            if use_hybrid:
                results = _retrieval.hybrid_search(
                    search_query, limit=limit_count, expand_concepts=True, faculty=filter_faculty
                )
            else:
                results = db.search(search_query, limit=limit_count, faculty=filter_faculty)
        elapsed = time.perf_counter() - t_start
        elapsed_str = f"{elapsed:.2f} detik" if elapsed >= 0.01 else "<0.01 detik"

        if not results:
            st.warning(f"Tidak ada paper yang cocok dengan kata kunci: '{search_query}'")
            if filter_faculty:
                st.caption(
                    "💡 **Tips:** Paper mungkin berada di bidang lain. Coba pilih *'Semua bidang paper'* pada pilihan cakupan di atas."
                )
            elif not use_hybrid:
                st.caption(
                    "💡 **Tips:** Coba centang *'Cari juga yang maknanya mirip'* di atas untuk mencari sinonim atau konsep terkait secara semantik."
                )
        else:
            fac_label = f" pada bidang **{fac_name}**" if filter_faculty else " (lintas bidang)"
            st.success(
                f"⚡ **Ditemukan {len(results)} paper**{fac_label} yang memuat kata kunci *'{html.escape(search_query)}'* "
                f"— *Pencarian selesai dalam {elapsed_str}*"
            )

            for idx, r in enumerate(results, start=1):
                with st.container(border=True):
                    # 1. Rank & Title Header
                    rank_badge = (
                        f"<span style='background: #2563eb; color: #ffffff; padding: 2px 8px; "
                        f"border-radius: 6px; font-size: 0.82em; font-weight: 700; margin-right: 8px;'>#{idx}</span>"
                    )
                    title_text = html.escape(str(r.get("title") or "Tanpa Judul"))
                    year_text = html.escape(str(r.get("year") or "n.d."))
                    st.markdown(f"#### {rank_badge} {title_text} ({year_text})", unsafe_allow_html=True)

                    # 2. Official CosmoLab Badges (Analysis Status, Stance, Study Type, SINTA, Crossref)
                    st.markdown(paper_badges(r), unsafe_allow_html=True)

                    # 3. Authors, Faculty, and DOI/URL Link
                    authors_list = _authors.as_list(r.get("authors"))
                    authors_display = (
                        ", ".join(authors_list[:3]) + (" dkk." if len(authors_list) > 3 else "")
                        if authors_list
                        else "Anonim"
                    )

                    meta_items = [f"✍️ **Penulis:** {html.escape(authors_display)}"]
                    if r.get("faculty"):
                        f_obj = _faculties.get_faculty(r.get("faculty"))
                        fac_disp = f"{f_obj.icon} {f_obj.name}" if f_obj else str(r.get("faculty"))
                        meta_items.append(f"🏛️ **Bidang:** {html.escape(fac_disp)}")

                    doi = r.get("doi")
                    url = r.get("url")
                    if doi:
                        doi_clean = str(doi).strip()
                        doi_url = f"https://doi.org/{doi_clean}" if not doi_clean.startswith("http") else doi_clean
                        meta_items.append(f"[🔗 Lihat di Penerbit / DOI ↗]({doi_url})")
                    elif url:
                        meta_items.append(f"[🔗 Tautan Sumber ↗]({url})")

                    st.caption(" · ".join(meta_items))

                    # 4. AI Thesis (Inti Paper)
                    if r.get("thesis"):
                        st.info(f"💡 **Inti Paper:** {r.get('thesis')}")

                    # 5. Verified Physical Passage Callout
                    has_grounded = False
                    if r.get("file"):
                        try:
                            passages = _retrieval.find_grounded_passages(r["file"], search_query, top_k=1)
                            # Only display grounded passage if it is an authentic match, NOT the fallback opener
                            if passages and not passages[0].get("fallback"):
                                psg = passages[0]
                                highlighted_passage = _highlight_terms(psg["verbatim"], search_query)
                                st.markdown(
                                    f"<div style='margin-top: 8px; margin-bottom: 8px; padding: 10px 14px; "
                                    f"background-color: rgba(245, 158, 11, 0.08); border-left: 4px solid #f59e0b; "
                                    f"border-radius: 4px; font-size: 0.92em; line-height: 1.6;'>"
                                    f"<div style='font-weight: 700; color: #b45309; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;'>"
                                    f"<span>📍</span> <span>Temuan Otentik Naskah ({psg['page_label']}):</span>"
                                    f"</div>"
                                    f"<div style='font-style: italic; color: inherit;'>\"{highlighted_passage}\"</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                has_grounded = True
                        except Exception:
                            pass

                    # 6. FTS Snippet
                    if r.get("snippet"):
                        cleaned_snippet = _format_snippet(r.get("snippet"))
                        snippet_label = "Cuplikan tambahan:" if has_grounded else "Cuplikan naskah:"
                        st.markdown(
                            f"**{snippet_label}** <span style='line-height: 1.6;'>...{cleaned_snippet}...</span>",
                            unsafe_allow_html=True,
                        )

                    # 7. One-Click Citation (APA 7th & In-Text)
                    with st.expander("📋 Sitasi Cepat (APA 7th & In-Text)", expanded=False):
                        col_c1, col_c2 = st.columns([1, 2])
                        with col_c1:
                            st.caption("**Sitasi dalam teks (In-Text APA):**")
                            st.code(_citations.format_in_text_apa(r), language="text")
                        with col_c2:
                            st.caption("**Daftar pustaka (APA 7th Edition):**")
                            st.code(_citations.format_apa(r), language="text")

                    # 8. Detailed Methodology & Findings (Inline Bedah Riset)
                    with st.expander("📖 Lihat Intisari Riset, Sampel & Temuan Lengkap", expanded=False):
                        render_analysis_detail(r)
