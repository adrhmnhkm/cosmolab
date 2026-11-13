"""Beranda: key numbers, work waiting, what the collection holds, recent activity.

The owner view (dashboard run without team mode) adds setup status, AI usage,
and every project at a glance.

Colors (checked with the color-blind palette validator against a white card):
teal for the accent and "supports", amber for "critiques", gray for neutral
and de-emphasized marks.
"""

import altair as alt
import pandas as pd
import streamlit as st

from cosmolab import config
from cosmolab import home as _home
from cosmolab import position as _position
from cosmolab import team as _team
from cosmolab import usage as _usage
from cosmolab.ui.components import _badge, _e, render_hero
from cosmolab.ui.context import AppContext

TEAL = "#0E8A72"
TEAL_DARK = "#08594A"
TEAL_LIGHT = "#A6D4C8"
AMBER = "#B87A00"
GRAY = "#CBD5E1"
EMPTY = "#EEF2F1"
INK = "#334155"
DAY_NAMES = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]

START = [
    ("Review draf", "Review Draf Mahasiswa", ":material/rate_review:"),
    ("Cari paper", "Panen Paper Ilmiah", ":material/travel_explore:"),
    ("Tanya koleksi", "Tanya Korpus & Sintesis", ":material/forum:"),
    ("Latihan sidang", "Latihan Sidang", ":material/record_voice_over:"),
]


def _go(target: str, stem: str = ""):
    st.session_state["active_nav_menu"] = target
    if stem:
        st.session_state["review_current"] = stem


def _chart(chart, height: int):
    st.altair_chart(chart.properties(height=height, background="transparent")
                    .configure_view(stroke=None, fill="transparent")
                    .configure_axis(labelColor="#64748B", titleColor="#64748B", gridColor="#E2E8F0",
                                    domain=False, ticks=False, labelFontSize=11),
                    width="stretch")


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _project_header():
    info = config.project_info()
    if config.PROJECT:
        client = f" · {info['client']}" if info.get("client") else ""
        st.info(f"Proyek aktif: **{_e(config.PROJECT)}**{_e(client)}")
    else:
        st.warning("Dashboard ini memakai **data utama**, bukan proyek klien. Hasil kerja untuk klien sebaiknya "
                   "disimpan di proyeknya sendiri supaya tidak tercampur: `cosmolab project new <nama>`, lalu "
                   "`cosmolab -P <nama> ui`.")


def _question_section(ctx: AppContext):
    """The project's research question, and where the papers stand on it."""
    q = _position.load_question()
    st.markdown("#### Pertanyaan riset")
    col_q, col_p = st.columns([3, 2])
    with col_q, st.container(border=True):
        if q["question"]:
            if q["topic"]:
                st.caption(f"Topik: {q['topic']}")
            st.markdown(f"**{q['question']}**")
            if q["hypothesis"]:
                st.markdown(f"Hipotesis: {q['hypothesis']}")
        else:
            st.caption("Belum diisi. Isi pertanyaan riset mahasiswa, lalu AI menilai paper mana yang mendukung, "
                       "menolak, atau tidak berkaitan dengannya.")
        with st.expander("Ubah pertanyaan riset" if q["question"] else "Isi pertanyaan riset"):
            with st.form("home_question_form", border=False):
                topic = st.text_input("Topik", value=q["topic"], placeholder="contoh: Literasi keuangan mahasiswa")
                question = st.text_area("Pertanyaan riset", value=q["question"], height=80,
                                        placeholder="contoh: Apakah literasi keuangan memengaruhi perilaku menabung mahasiswa?")
                hypothesis = st.text_area("Hipotesis (boleh kosong)", value=q["hypothesis"], height=68,
                                          placeholder="contoh: Literasi keuangan berpengaruh positif terhadap perilaku menabung.")
                if q["question"]:
                    st.caption("Kalau pertanyaan atau hipotesis diubah, penilaian posisi yang lama tidak dipakai lagi "
                               "dan paper perlu dinilai ulang.")
                if st.form_submit_button("Simpan", type="primary"):
                    if not question.strip():
                        st.error("Pertanyaan riset belum diisi.")
                    else:
                        _position.save_question(topic, question, hypothesis)
                        st.rerun()

    with col_p, st.container(border=True):
        st.markdown("##### Posisi paper terhadap pertanyaan riset")
        if not q["question"]:
            st.caption("Muncul setelah pertanyaan riset diisi.")
            return
        note = st.session_state.pop("home_judge_note", None)
        if note:
            (st.error if note[0] == "error" else st.success)(note[1])
        rows = _position.counts(ctx.papers)
        todo = _position.pending(ctx.all_papers)
        if rows:
            order = [_position.LABELS[k] for k in _position.ORDER]
            df = pd.DataFrame(rows)
            base = alt.Chart(df).encode(y=alt.Y("Posisi:N", sort=order, title=None, axis=alt.Axis(labelLimit=170)))
            bars = base.mark_bar(cornerRadiusEnd=4, height=16).encode(
                x=alt.X("Paper:Q", title=None, axis=None),
                color=alt.Color("Posisi:N", legend=None,
                                scale=alt.Scale(domain=order, range=[TEAL, TEAL_LIGHT, AMBER, GRAY])),
                tooltip=["Posisi", "Paper"])
            text = base.mark_text(align="left", dx=4, color=INK).encode(x="Paper:Q", text="Paper:Q")
            _chart(bars + text, 28 * len(rows) + 10)
            st.caption("Dinilai AI dari ringkasan analisis tiap paper. Alasannya ada di detail paper di Koleksi.")
        elif not todo:
            st.caption("Belum ada paper yang dianalisis. Posisi dinilai dari hasil analisis paper.")
        if todo:
            st.caption(f"Belum dinilai: {_position.estimate_text(len(todo))}")
            if st.button(f"Nilai {len(todo)} paper", key="home_judge", type="secondary" if rows else "primary",
                         width="stretch"):
                with st.spinner("AI menilai posisi paper..."):
                    res = _position.judge(ctx.all_papers)
                if res["error"]:
                    st.session_state["home_judge_note"] = (
                        "error", f"Berhenti di tengah: {res['error']}. {res['judged']} paper sudah dinilai dan tersimpan.")
                elif res["failed"]:
                    st.session_state["home_judge_note"] = (
                        "error", f"{res['judged']} paper dinilai, {res['failed']} tidak dijawab AI. Tekan tombol lagi.")
                else:
                    st.session_state["home_judge_note"] = ("ok", f"{res['judged']} paper dinilai.")
                st.rerun()


def _open_paper(title: str):
    """Go to Koleksi paper with the list filtered to this title."""
    st.session_state["explorer_filter_q"] = title
    st.session_state["active_nav_menu"] = "Paper Explorer & Korpus"


def _evidence_card(ctx: AppContext):
    """Which papers are strong evidence for the hypothesis, and how to use each group."""
    g = _position.evidence_groups(ctx.papers)
    if not g["tiers"]:
        return
    title = "Seberapa kuat literatur mendukung hipotesis" if g["effect_study"] else "Jenis bukti di koleksi"
    with st.container(border=True):
        st.markdown(f"##### {title}")
        cols = st.columns(len(g["tiers"]))
        for col, tier in zip(cols, g["tiers"]):
            with col:
                st.markdown(f"**{tier['label']} · {len(tier['papers'])}**")
                st.caption(tier["hint"])
                for i, p in enumerate(tier["papers"]):
                    extra = []
                    if p["position"] != _position.SUPPORTS:
                        extra.append(_position.LABELS[p["position"]].lower())
                    if tier["key"] in ("pendukung", "konteks") and p["note"]:
                        extra.append(p["note"])
                    c_text, c_btn = st.columns([9, 1], vertical_alignment="center")
                    note = f" <span style='color:#64748B'>· {_e(', '.join(extra))}</span>" if extra else ""
                    c_text.markdown(f"<div style='font-size:0.85rem;line-height:1.35;margin-bottom:6px'>{_e(p['title'])} "
                                    f"({_e(p['year'])}){note}</div>", unsafe_allow_html=True)
                    c_btn.button("", key=f"ev_{tier['key']}_{i}", icon=":material/open_in_new:", type="tertiary",
                                 on_click=_open_paper, args=(p["title"],), help="Buka di Koleksi paper")
        if g["no_counter"]:
            ask = ("\"Apa ada penelitian yang hasilnya tidak signifikan?\"" if g["effect_study"]
                   else "pandangan yang berlawanan")
            st.warning(f"Belum ada paper yang menolak atau hasilnya campuran. Penguji bisa menanyakan {ask}. "
                       "Cari meta-analisis atau paper tentang kendala dan kritik terhadap topik ini.",
                       icon=":material/warning:")


def _kpi_row(ctx: AppContext, activity: list[dict], owner: bool):
    k = _home.kpis(ctx.papers)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Paper di koleksi", k["papers"], delta=f"+{k['new_this_month']} bulan ini" if k["new_this_month"] else None,
              chart_data=_home.paper_growth(ctx.papers), chart_type="area", border=True,
              help="Garis: jumlah paper selama 30 hari terakhir.")
    pct = round(100 * k["analyzed"] / k["papers"]) if k["papers"] else 0
    c2.metric("Sudah dianalisis", f"{pct}%", delta=f"{k['analyzed']} dari {k['papers']} paper", delta_color="off",
              delta_arrow="off", border=True)
    c3.metric("Komentar belum diputuskan", k["pending"],
              delta=f"di {k['reviews_open']} review" if k["reviews_open"] else "semua beres",
              delta_color="off", delta_arrow="off", border=True)
    if owner:
        days = _home.usage_days()
        tokens = sum(d["Token"] for d in days)
        rows = _home.usage_by_feature()
        cost = sum(u["cost"] for u in rows)
        value = _usage.format_money(cost) if _usage.pricing() else f"{tokens / 1_000_000:.1f} jt token"
        c4.metric("AI 30 hari terakhir", value, chart_data=[d["Token"] for d in days], chart_type="bar", border=True,
                  help="Batang: token AI per hari, semua proyek." + ("" if _usage.pricing() else
                                                                      " Tarif belum diisi, jadi yang tampil token."))
    else:
        weeks = _home.weekly_activity(activity)
        c4.metric("Kegiatan minggu ini", weeks[-1] if weeks else 0, chart_data=weeks or None, chart_type="bar",
                  border=True, help="Batang: kegiatan per minggu, 12 minggu terakhir.")


def _todo_section(ctx: AppContext):
    with st.container(border=True):
        st.markdown("##### Perlu tindakan")
        items = _home.todo(ctx.all_papers)
        me = _team.current_username()
        if me and any(it["kind"] == "review" for it in items):
            if st.radio("Tampilkan", ["Semua", "Punya saya"], horizontal=True, key="home_todo_scope",
                        label_visibility="collapsed") == "Punya saya":
                items = [it for it in items if it["kind"] == "review" and it.get("created_by") == me]
        if not items:
            st.success("Tidak ada pekerjaan tertunda.")
            return
        for i, it in enumerate(items):
            col_t, col_p, col_b = st.columns([3, 2, 1], vertical_alignment="center")
            if it["kind"] == "review":
                tags = " ".join(_badge(x, "warn" if "belum" in x or "lemah" in x else "info")
                                for x in it["issues"] if "komentar belum diputuskan" not in x)
                col_t.markdown(f"**{_e(it['title'])}**" + (f"<br>{tags}" if tags else ""), unsafe_allow_html=True)
                if it["total"]:
                    col_p.progress(it["decided"] / it["total"], text=f"{it['decided']}/{it['total']} komentar diputuskan")
                else:
                    col_p.caption("Tanpa komentar AI")
                col_b.button("Buka", key=f"home_todo_{i}", on_click=_go, args=("Review Draf Mahasiswa", it["stem"]),
                             width="stretch")
            else:
                n = len(ctx.all_papers)
                done = n - int(it["title"].split()[0])
                col_t.markdown(f"**{_e(it['title'])}**")
                col_p.progress(done / n if n else 0.0, text=f"{done}/{n} paper dianalisis")
                col_b.button("Buka", key=f"home_todo_{i}", on_click=_go, args=("Paper Explorer & Korpus",),
                             width="stretch")


def _start_section():
    with st.container(border=True):
        st.markdown("##### Mulai kerja baru")
        for row in (START[:2], START[2:]):
            cols = st.columns(2)
            for col, (label, target, icon) in zip(cols, row):
                col.button(label, key=f"home_start_{target}", icon=icon, on_click=_go, args=(target,), width="stretch")


def _years_chart(papers: list[dict]):
    with st.container(border=True):
        st.markdown("##### Tahun terbit")
        data = _home.year_counts(papers)
        if not data["rows"]:
            st.caption("Belum ada paper dengan tahun terbit.")
            return
        st.caption(f"**{round(100 * data['recent_share'])}%** terbit dalam {_home.RECENT_YEARS} tahun terakhir "
                   f"(batang hijau)." + (f" {data['unknown']} paper tanpa tahun." if data["unknown"] else ""))
        df = pd.DataFrame(data["rows"])
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("Tahun:O", title=None, axis=alt.Axis(labelAngle=0, labelOverlap=True)),
            y=alt.Y("Paper:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            color=alt.condition("datum.Baru", alt.value(TEAL), alt.value(GRAY)),
            tooltip=[alt.Tooltip("Tahun:O"), alt.Tooltip("Paper:Q", title="Paper")],
        )
        _chart(chart, 210)


def _ranked_chart(title: str, rows: list[dict], empty: str):
    with st.container(border=True):
        st.markdown(f"##### {title}")
        if not rows:
            st.caption(empty)
            return
        df = pd.DataFrame(rows)
        base = alt.Chart(df).encode(y=alt.Y("Nama:N", sort="-x", title=None, axis=alt.Axis(labelLimit=170)))
        bars = base.mark_bar(cornerRadiusEnd=4, color=TEAL, height=16).encode(
            x=alt.X("Paper:Q", title=None, axis=None), tooltip=["Nama", "Paper"])
        text = base.mark_text(align="left", dx=4, color=INK).encode(x="Paper:Q", text="Paper:Q")
        _chart(bars + text, 28 * len(rows) + 10)


def _activity_section(activity: list[dict], owner: bool):
    col_h, col_r = st.columns([3, 2])
    with col_h, st.container(border=True):
        st.markdown("##### Aktivitas 12 minggu terakhir")
        total = sum(d["Kegiatan"] for d in activity)
        st.caption(f"{total} kegiatan tercatat. Makin gelap kotaknya, makin banyak kegiatan hari itu.")
        df = pd.DataFrame(activity)
        df["Nama hari"] = df["Hari"].map(lambda i: DAY_NAMES[i])
        peak = max(1, int(df["Kegiatan"].max()))
        chart = alt.Chart(df).mark_rect(cornerRadius=3, stroke="white", strokeWidth=2).encode(
            x=alt.X("Minggu:O", axis=None),
            y=alt.Y("Nama hari:O", sort=DAY_NAMES, title=None),
            color=alt.condition("datum.Kegiatan == 0", alt.value(EMPTY),
                                alt.Color("Kegiatan:Q", scale=alt.Scale(domain=[1, peak], range=[TEAL_LIGHT, TEAL_DARK]),
                                          legend=None)),
            tooltip=[alt.Tooltip("Tanggal:T", format="%d %b %Y"), "Kegiatan"],
        )
        _chart(chart, 170)
    with col_r, st.container(border=True):
        st.markdown("##### Terbaru")
        rows = _home.recent(5, _usage.all_roots() if owner else None)
        if not rows:
            st.caption("Belum ada aktivitas tercatat.")
        for r in rows:
            where = f" · {_e(r['_root'])}" if owner and r.get("_root") else ""
            st.markdown(f"<span style='color:#64748B'>{_e(_home.when(r.get('time', '')))}</span>  \n"
                        f"{_e(_home.describe(r))}{where}", unsafe_allow_html=True)


def _owner_section():
    st.divider()
    st.markdown("#### Khusus pemilik")
    st.caption("Bagian ini tampil di dashboard tanpa mode tim, dan untuk akun admin di mode tim.")

    col_s, col_u = st.columns([2, 3])
    with col_s, st.container(border=True):
        st.markdown("##### Status setup")
        checks = _home.setup_checks()
        ready = sum(1 for c in checks if c["ok"])
        st.progress(ready / len(checks), text=f"{ready} dari {len(checks)} siap")
        for c in checks:
            st.markdown(_badge("Siap" if c["ok"] else "Belum", "good" if c["ok"] else "warn")
                        + f" **{_e(c['label'])}**", unsafe_allow_html=True)
            if not c["ok"]:
                st.caption(c["detail"])
    with col_u, st.container(border=True):
        st.markdown("##### Token AI per hari, 30 hari terakhir")
        days = _home.usage_days()
        if not any(d["Token"] for d in days):
            st.caption("Belum ada pemakaian AI.")
        else:
            df = pd.DataFrame(days)
            chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, color=TEAL).encode(
                x=alt.X("yearmonthdate(Tanggal):T", title=None, axis=alt.Axis(format="%d %b", labelOverlap=True)),
                y=alt.Y("Token:Q", title=None, axis=alt.Axis(format="~s")),
                tooltip=[alt.Tooltip("Tanggal:T", format="%d %b %Y"), alt.Tooltip("Token:Q", format=",")],
            )
            _chart(chart, 190)
        usage = _home.usage_by_feature()
        if usage:
            st.markdown("**Per fitur, bulan ini**")
            priced = bool(_usage.pricing())
            rows = [{"Nama": _home.feature_label(u["key"]), "Paper": u["total_tokens"]} for u in usage[:6]]
            df = pd.DataFrame(rows)
            base = alt.Chart(df).encode(y=alt.Y("Nama:N", sort="-x", title=None, axis=alt.Axis(labelLimit=190)))
            bars = base.mark_bar(cornerRadiusEnd=4, color=TEAL, height=14).encode(
                x=alt.X("Paper:Q", title=None, axis=None), tooltip=[alt.Tooltip("Nama", title="Fitur"),
                                                                     alt.Tooltip("Paper:Q", title="Token", format=",")])
            text = base.mark_text(align="left", dx=4, color=INK).encode(x="Paper:Q", text=alt.Text("Paper:Q", format=".2s"))
            _chart(bars + text, 26 * len(rows) + 10)
            total = sum(u["total_tokens"] for u in usage)
            cost = _usage.format_money(sum(u["cost"] for u in usage)) if priced else "tarif belum diisi"
            st.caption(f"Total bulan ini: {total:,} token · {cost}")

    with st.container(border=True):
        st.markdown("##### Semua proyek")
        rows = _home.projects_overview()
        for r in rows:
            r["Dianalisis (%)"] = round(100 * r["Dianalisis"] / r["Paper"]) if r["Paper"] else 0
        st.dataframe(
            pd.DataFrame(rows)[["Proyek", "Paper", "Dianalisis (%)", "Review draf", "Komentar belum diputuskan",
                                "Token AI bulan ini", "Biaya AI bulan ini"]],
            hide_index=True, width="stretch",
            column_config={
                "Dianalisis (%)": st.column_config.ProgressColumn("Dianalisis", min_value=0, max_value=100,
                                                                  format="%d%%"),
                "Token AI bulan ini": st.column_config.NumberColumn(format="compact"),
            },
        )


def render(ctx: AppContext):
    """Beranda."""
    owner = _home.is_owner()
    render_hero(title="Beranda", subtitle="Pekerjaan yang menunggu, isi koleksi, dan kegiatan tim dalam satu layar.")
    _project_header()
    activity = _home.activity_days(_usage.all_roots() if owner else None)
    _kpi_row(ctx, activity, owner)

    col_t, col_s = st.columns([3, 2])
    with col_t:
        _todo_section(ctx)
    with col_s:
        _start_section()

    _question_section(ctx)
    _evidence_card(ctx)

    st.markdown("#### Isi koleksi")
    if ctx.selected_faculty_id != "all":
        st.caption(f"Bidang: {_e(ctx.faculty_labels.get(ctx.selected_faculty_id, ''))} (ubah di sidebar).")
    col_y, col_p = st.columns([3, 2])
    with col_y:
        _years_chart(ctx.papers)
    with col_p:
        _ranked_chart("Jenis penelitian", _home.method_counts(ctx.papers), "Belum ada paper yang dianalisis.")
    col_f, col_src = st.columns(2)
    with col_f:
        _ranked_chart("Bidang ilmu", _home.faculty_counts(ctx.papers, ctx.faculty_labels), "Belum ada paper.")
    with col_src:
        _ranked_chart("Asal sumber", _home.source_counts(ctx.papers), "Belum ada paper.")

    st.markdown("#### Kegiatan")
    _activity_section(activity, owner)
    if owner:
        _owner_section()
