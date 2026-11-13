"""Dashboard page: Latihan sidang (the AI examines the student's own draft)."""

import tempfile
from pathlib import Path

import streamlit as st

from cosmolab import config
from cosmolab import defense as _defense
from cosmolab import review as _review
from cosmolab.ui.components import _badge, _e, render_hero
from cosmolab.ui.context import AppContext

SCORE_TONES = {"kuat": "good", "cukup": "mix", "lemah": "bad"}


def _uploaded_md(uploaded) -> str:
    key = ("_defense_draft_md", uploaded.name, uploaded.size)
    cached = st.session_state.get("_defense_draft_md")
    if cached and cached[0] == key:
        return cached[1]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"draf{Path(uploaded.name).suffix.lower()}"
        path.write_bytes(uploaded.getvalue())
        md = _review.read_draft(path)
    st.session_state["_defense_draft_md"] = (key, md)
    return md


def _new_session():
    reviews = [r["report"] for r in _review.load_saved() if r["report"].get("draft_md")]
    with st.container(border=True):
        sources = ["Unggah draf"] + (["Draf yang sudah direview"] if reviews else [])
        source = st.radio("Sumber draf", sources, horizontal=True, key="defense_source")
        md, title, name = "", "", ""
        if source == "Unggah draf":
            uploaded = st.file_uploader("Unggah draf (.docx, .md, .txt)", type=["docx", "md", "txt"], key="defense_upload")
            if uploaded is not None:
                try:
                    md, name = _uploaded_md(uploaded), uploaded.name
                except Exception as e:
                    st.error(f"Draf belum bisa dibaca: {e}")
        else:
            by_stem = {r["stem"]: r for r in reviews}
            stem = st.selectbox("Review", list(by_stem), key="defense_review",
                                format_func=lambda s: f"{by_stem[s].get('title') or s} ({str(by_stem[s].get('reviewed_at') or '')[:10]})")
            chosen = by_stem[stem]
            md, title, name = chosen["draft_md"], chosen.get("title") or "", chosen.get("source") or ""

        col1, col2, col3 = st.columns([3, 2, 2])
        title = col1.text_input("Judul / nama mahasiswa", value=title, key=f"defense_title_{source}")
        level = col2.selectbox("Jenjang", list(_defense.LEVELS), index=1, key="defense_level",
                               format_func=lambda k: _defense.LEVELS[k].capitalize())
        n = col3.slider("Jumlah pertanyaan", min_value=4, max_value=12, value=8, key="defense_n")
        if md.strip():
            st.caption(_e(_defense.estimate_text(md, n)))
        if st.button("Mulai latihan", type="primary", disabled=not md.strip(), key="defense_start", width="stretch"):
            try:
                with st.spinner("Penguji AI membaca draf dan menyusun pertanyaan..."):
                    session = _defense.start(md, title=title or Path(name).stem, level=level, n=n, source=name)
            except Exception as e:
                st.error(f"Latihan belum bisa dimulai: {e}")
                return
            st.session_state["defense_current"] = session["stem"]
            st.rerun()


def _feedback_block(fb: dict):
    st.markdown(_badge(_defense.SCORES.get(fb["score"], fb["score"]), SCORE_TONES.get(fb["score"], "muted")),
                unsafe_allow_html=True)
    for label, key in (("Sudah baik", "strengths"), ("Belum terjawab", "gaps"), ("Perlu disiapkan", "prepare")):
        if fb.get(key):
            st.markdown(f"**{label}**\n" + "\n".join(f"- {x}" for x in fb[key]))
    if fb.get("follow_up"):
        st.markdown(f"**Pertanyaan lanjutan penguji:** {fb['follow_up']}")


@st.fragment
def _question_card(stem: str, qid: str, number: int):
    session = _defense.load(stem)
    q = next(x for x in session["questions"] if x["id"] == qid)
    with st.container(border=True):
        area = _defense.AREAS.get(q["area"], q["area"])
        section = q.get("section") or ""
        where = f" · bagian {section}" if section and section.lower() != area.lower() else ""
        st.caption(f"Pertanyaan {number} · {area}{where}")
        st.markdown(f"**{q['question']}**")
        st.markdown(f"> {q['quote']}")
        if q.get("looks_for"):
            with st.expander("Yang dilihat penguji"):
                st.write(q["looks_for"])
        key = f"defense_{stem}_{qid}_answer"
        if key not in st.session_state:
            st.session_state[key] = q.get("answer") or ""
        st.text_area("Jawaban", key=key, height=140,
                     placeholder="Jawab seperti di depan penguji. Mahasiswa menjawab dengan kata-katanya sendiri.")
        label = "Minta umpan balik lagi" if q.get("feedback") else "Minta umpan balik"
        if st.button(label, key=f"defense_{stem}_{qid}_send"):
            try:
                with st.spinner("Penguji AI menilai jawaban..."):
                    q = _defense.answer(session, qid, st.session_state[key])
            except Exception as e:
                st.error(str(e))
            else:
                st.rerun(scope="app")  # the progress line at the top counts answered questions
        if q.get("feedback"):
            _feedback_block(q["feedback"])


def _show(stem: str):
    try:
        session = _defense.load(stem)
    except FileNotFoundError:
        st.info("Latihan ini tidak ditemukan.")
        return
    p = _defense.progress(session)
    st.markdown(f"#### {_e(session.get('title') or 'Draf')}")
    st.progress(p["answered"] / p["total"] if p["total"] else 0.0,
                text=f"{p['answered']} dari {p['total']} pertanyaan dijawab · kuat {p['kuat']}, cukup {p['cukup']}, "
                     f"perlu diperkuat {p['lemah']}")
    if session.get("dropped"):
        st.caption(f"{session['dropped']} pertanyaan AI dibuang karena kutipannya tidak ada di draf.")
    st.download_button("Unduh catatan latihan (.md)", data=lambda: _defense.session_markdown(_defense.load(stem)),
                       file_name=f"latihan_sidang_{stem}.md", mime="text/markdown", on_click="ignore",
                       key=f"defense_{stem}_download")
    for i, q in enumerate(session["questions"], 1):
        _question_card(stem, q["id"], i)


def render(ctx: AppContext):
    """Latihan Sidang."""
    render_hero(
        title="Latihan Sidang",
        subtitle="AI berperan sebagai dosen penguji: membaca draf mahasiswa, bertanya, lalu menilai jawabannya. "
                 "Jawaban tidak dituliskan AI; mahasiswa menyusunnya sendiri.",
    )
    if not config.PROJECT:
        st.warning("Anda memakai data utama. Buat proyek untuk klien ini supaya latihannya tersimpan terpisah: "
                   "`cosmolab project new <nama>`, lalu `cosmolab -P <nama> ui`.")
    saved = _defense.load_saved()
    tab_new, tab_saved = st.tabs(["Latihan baru", f"Latihan tersimpan ({len(saved)})"])
    with tab_new:
        _new_session()
        current = st.session_state.get("defense_current")
        if current:
            _show(current)
    with tab_saved:
        if not saved:
            st.info("Belum ada latihan tersimpan.")
            return
        by_stem = {s["stem"]: s for s in saved}

        def _label(stem):
            s = by_stem[stem]
            p = _defense.progress(s)
            return f"{s.get('title') or stem} ({str(s.get('created') or '')[:10]}, {p['answered']}/{p['total']} dijawab)"

        stem = st.selectbox("Latihan", list(by_stem), format_func=_label, key="defense_saved_pick")
        if st.button("Buka di tab Latihan baru", key="defense_open_saved"):
            st.session_state["defense_current"] = stem
            st.rerun()
        s = by_stem[stem]
        for i, q in enumerate(s["questions"], 1):
            fb = q.get("feedback")
            mark = _defense.SCORES.get(fb["score"], "") if fb else "belum dijawab"
            st.markdown(f"{i}. {q['question']} *({mark})*")
