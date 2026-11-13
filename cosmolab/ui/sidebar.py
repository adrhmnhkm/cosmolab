"""Sidebar: brand, active project, field filter, menu, and technical info."""

import streamlit as st
from cosmolab import config
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab.ui.components import LOGO_MARK_URI
from cosmolab.ui.context import AppContext


def render_nav_item(label: str, target: str, badge: str = None, icon: str = None):
    is_active = (st.session_state["active_nav_menu"] == target)
    display_title = f"{label}  ·  {badge}" if badge else label
    if st.sidebar.button(
        display_title,
        key=f"nav_btn_{target}",
        type="primary" if is_active else "secondary",
        icon=icon,
        use_container_width=True
    ):
        st.session_state["active_nav_menu"] = target
        st.rerun()


# Kept at column 0: indented lines would turn into a Markdown code block.
BRAND_HTML = """
<div class="sidebar-brand-card">
    <div class="sidebar-brand-title">
        {mark}<span>Cosmo<span class="sidebar-brand-lab">Lab</span></span>
    </div>
    <div class="sidebar-brand-sub">Asisten riset multidisipliner</div>
</div>
"""


def build_sidebar() -> AppContext:
    """Draw the sidebar and return what the pages need."""
    st.sidebar.markdown(BRAND_HTML.format(mark=f'<img class="sidebar-brand-mark" src="{LOGO_MARK_URI}" alt="">' if LOGO_MARK_URI else ""),
        unsafe_allow_html=True)

    # Active client project (set per dashboard process via `cosmolab -P <proyek> ui`)
    _proj = config.project_info()
    if config.PROJECT:
        _client = f" · {_proj['client']}" if _proj.get("client") else ""
        st.sidebar.info(f"Proyek: **{config.PROJECT}**{_client}")
    else:
        st.sidebar.warning("Data utama (bukan proyek klien)")

    # Faculty Filter in Sidebar
    faculty_list = _faculties.list_faculties()
    faculty_options = ["all"] + [f.id for f in faculty_list]
    faculty_labels = {"all": "Semua bidang"}
    for f in faculty_list:
        custom_tag = " [Kustom]" if getattr(f, "is_custom", False) else ""
        faculty_labels[f.id] = f"{f.name}{custom_tag}"

    selected_faculty_id = st.sidebar.selectbox(
        "Bidang ilmu",
        faculty_options,
        format_func=lambda x: faculty_labels.get(x, x),
    )

    # Load DB papers (old philosophy field ids are classified again first)
    db.migrate_faculties()
    all_papers = db.get_all_papers_with_analyses()
    if selected_faculty_id == "all":
        papers = all_papers
    else:
        papers = [p for p in all_papers if p.get("faculty") == selected_faculty_id]

    total_all = len(all_papers)
    total_active = len(papers)
    total_analyzed = len([p for p in papers if p.get("thesis")])

    # One readable progress line instead of two cramped metric cards
    st.sidebar.progress(
        total_analyzed / total_active if total_active else 0.0,
        text=f"{total_analyzed} dari {total_active} paper sudah dianalisis",
    )

    if "active_nav_menu" not in st.session_state:
        st.session_state["active_nav_menu"] = "Beranda"

    render_nav_item("Beranda", "Beranda", icon=":material/home:")
    # Menu follows the work for one client: collect, understand, then deliver.
    # Pages left out of the menu (Diagram argumen, Kurikulum, Ekspor, Bedah DOI,
    # Cari di naskah) still exist in web.PAGES; DOI, search and export now live
    # as tabs inside other pages. See REVIEW_APLIKASI.md.
    st.sidebar.markdown("<div class='nav-cluster-header'>1 · Kumpulkan</div>", unsafe_allow_html=True)
    render_nav_item("Cari & tambah paper", "Panen Paper Ilmiah", icon=":material/travel_explore:")

    st.sidebar.markdown("<div class='nav-cluster-header'>2 · Pahami</div>", unsafe_allow_html=True)
    render_nav_item("Koleksi paper", "Paper Explorer & Korpus", str(total_active), icon=":material/library_books:")
    render_nav_item("Tanya koleksi", "Tanya Korpus & Sintesis", icon=":material/forum:")

    st.sidebar.markdown("<div class='nav-cluster-header'>3 · Hasil untuk klien</div>", unsafe_allow_html=True)
    render_nav_item("Tinjauan pustaka & celah riset", "Laporan Sintesis", icon=":material/summarize:")
    render_nav_item("Review draf mahasiswa", "Review Draf Mahasiswa", icon=":material/rate_review:")

    st.sidebar.markdown("<div class='nav-cluster-header'>Lainnya</div>", unsafe_allow_html=True)
    render_nav_item("Tulis artikel", "Studio Artikel Siap Baca", icon=":material/edit_note:")
    render_nav_item("Latihan debat", "Arena Sparring Nalar", icon=":material/record_voice_over:")
    render_nav_item("Periksa akurasi", "Pusat Akurasi", icon=":material/verified:")

    menu = st.session_state["active_nav_menu"]

    st.sidebar.divider()

    # Technical details live at the bottom, out of the researcher's way
    fac_dist = db.get_faculty_distribution()
    with st.sidebar.expander("Info teknis", expanded=False):
        st.caption(f"Model AI: {config.LLM_MODEL}")
        st.caption("Paper per bidang:")
        for f in faculty_list:
            cnt = fac_dist.get(f.id, 0)
            if cnt:
                st.caption(f"{f.name}: {cnt}")

    return AppContext(menu=menu, all_papers=all_papers, papers=papers, selected_faculty_id=selected_faculty_id, faculty_list=faculty_list, faculty_options=faculty_options, faculty_labels=faculty_labels, total_all=total_all, total_active=total_active, total_analyzed=total_analyzed, fac_dist=fac_dist)
