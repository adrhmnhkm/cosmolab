"""Beranda: work waiting, start buttons, project summary, recent activity.

The owner view (dashboard run without team mode) adds setup status, every
project at a glance, and AI usage this month.
"""

import streamlit as st

from cosmolab import config
from cosmolab import home as _home
from cosmolab import usage as _usage
from cosmolab.ui.components import _e, render_hero, render_table
from cosmolab.ui.context import AppContext

START = [
    ("Review draf mahasiswa", "Review Draf Mahasiswa", ":material/rate_review:"),
    ("Cari & unduh paper", "Panen Paper Ilmiah", ":material/travel_explore:"),
    ("Tanya korpus", "Tanya Korpus & Sintesis", ":material/forum:"),
    ("Tulis artikel", "Studio Artikel Siap Baca", ":material/edit_note:"),
]


def _go(target: str, stem: str = ""):
    st.session_state["active_nav_menu"] = target
    if stem:
        st.session_state["review_current"] = stem


def _project_header():
    info = config.project_info()
    if config.PROJECT:
        client = f" · {info['client']}" if info.get("client") else ""
        st.info(f"Proyek aktif: **{_e(config.PROJECT)}**{_e(client)}")
    else:
        st.warning("Dashboard ini memakai **data utama**, bukan proyek klien. Hasil kerja untuk klien sebaiknya "
                   "disimpan di proyeknya sendiri supaya tidak tercampur: `cosmolab project new <nama>`, lalu "
                   "`cosmolab -P <nama> ui`.")


def _todo_section(ctx: AppContext):
    st.markdown("##### Perlu tindakan")
    items = _home.todo(ctx.all_papers)
    if not items:
        st.success("Tidak ada pekerjaan tertunda.")
        return
    with st.container(border=True):
        for i, it in enumerate(items):
            col_t, col_b = st.columns([5, 1], vertical_alignment="center")
            if it["kind"] == "review":
                col_t.markdown(f"**Review: {_e(it['title'])}**  \n{_e(it['detail'])}")
                col_b.button("Buka", key=f"home_todo_{i}", on_click=_go, args=("Review Draf Mahasiswa", it["stem"]),
                             use_container_width=True)
            else:
                col_t.markdown(f"**{_e(it['title'])}**  \n{_e(it['detail'])}")
                col_b.button("Buka", key=f"home_todo_{i}", on_click=_go, args=("Paper Explorer & Korpus",),
                             use_container_width=True)


def _start_section():
    st.markdown("##### Mulai kerja baru")
    cols = st.columns(len(START))
    for col, (label, target, icon) in zip(cols, START):
        col.button(label, key=f"home_start_{target}", icon=icon, on_click=_go, args=(target,),
                   use_container_width=True)


def _summary_section(ctx: AppContext):
    st.markdown("##### Ringkasan proyek")
    s = _home.summary(ctx.all_papers)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Paper", s["papers"])
    c2.metric("Sudah dianalisis", s["analyzed"])
    c3.metric("Review draf", s["reviews"])
    c4.metric("Paper berperingkat SINTA", s["sinta"])


def _recent_section(owner: bool):
    st.markdown("##### Aktivitas terbaru")
    rows = _home.recent(5, _usage.all_roots() if owner else None)
    if not rows:
        st.caption("Belum ada aktivitas tercatat.")
        return
    for r in rows:
        where = f" · {_e(r['_root'])}" if owner and r.get("_root") else ""
        st.markdown(f"- {_e(_home.when(r.get('time', '')))} · {_e(_home.describe(r))}{where}")


def _owner_section():
    st.divider()
    st.markdown("#### Khusus pemilik")
    st.caption("Bagian ini hanya tampil di dashboard yang dijalankan tanpa mode tim.")

    st.markdown("##### Status setup")
    checks = _home.setup_checks()
    with st.container(border=True):
        for c in checks:
            mark = ":green[Siap]" if c["ok"] else ":orange[Belum]"
            st.markdown(f"**{_e(c['label'])}** · {mark}  \n{_e(c['detail'])}")

    st.markdown("##### Semua proyek")
    render_table(_home.projects_overview())

    st.markdown("##### Pemakaian AI bulan ini")
    usage = _home.usage_by_feature()
    if not usage:
        st.caption("Belum ada pemakaian AI bulan ini.")
        return
    priced = bool(_usage.pricing())
    render_table([{"Fitur": _home.feature_label(u["key"]), "Panggilan": u["calls"], "Token": f"{u['total_tokens']:,}",
                   "Biaya": _usage.format_money(u["cost"]) if priced else "-"} for u in usage])
    total = sum(u["total_tokens"] for u in usage)
    cost = _usage.format_money(sum(u["cost"] for u in usage)) if priced else "tarif belum diisi"
    st.caption(f"Total: {total:,} token · {cost}")


def render(ctx: AppContext):
    """Beranda."""
    render_hero(title="Beranda", subtitle="Pekerjaan yang menunggu, cara cepat memulai, dan ringkasan proyek.")
    _project_header()
    _todo_section(ctx)
    _start_section()
    _summary_section(ctx)
    _recent_section(_home.is_owner())
    if _home.is_owner():
        _owner_section()
