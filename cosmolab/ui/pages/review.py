"""Dashboard page: Review Draf Mahasiswa.

A consultant uploads a student's draft and gets supervisor-style comments and
a citation check. The page never shows rewritten text, only comments and
guiding questions. The consultant accepts, edits, or drops every AI comment;
only accepted and edited comments reach the student's Word file.
"""

import tempfile
from pathlib import Path

import streamlit as st
from cosmolab import review as _review
from cosmolab import verify as _verify
from cosmolab.ui.components import _badge, _e, render_hero, render_table
from cosmolab.ui.context import AppContext

SEVERITY_TONES = {_review.PENTING: "bad", _review.SARAN: "warn", _review.CATATAN: "muted"}
CHOICES = [_review.ACCEPT, _review.EDIT, _review.DROP]


def _run(uploaded, pasted: str, title: str, level: str, online: bool) -> dict:
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix.lower()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"draf{suffix}"
            path.write_bytes(uploaded.getvalue())
            md = _review.read_draft(path)
        name = title or Path(uploaded.name).stem.replace("_", " ")
        source = uploaded.name
    else:
        md, name, source = pasted, title or "Draf", "teks ditempel"
    return _review.review_text(md, title=name, level=level, online=online, source=source)


def _wkey(key: str, stem: str, cid: str, part: str) -> str:
    return f"{key}_{stem}_{cid}_{part}"


# Callbacks reload the review from disk, apply one change, and save. Both tabs
# read from disk too, so they never overwrite each other's decisions.
def _on_decision(key: str, stem: str, cid: str):
    report = _review.load(stem)
    choice = st.session_state.get(_wkey(key, stem, cid, "d"))
    _review.set_decision(report, cid, choice or _review.PENDING)
    _review.save(report)


def _on_edit(key: str, stem: str, cid: str):
    report = _review.load(stem)
    comment = st.session_state.get(_wkey(key, stem, cid, "c"), "")
    question = st.session_state.get(_wkey(key, stem, cid, "q"), "")
    if comment.strip():
        _review.set_decision(report, cid, _review.EDIT, comment=comment, question=question)
        _review.save(report)


def _on_accept_grounded(stem: str):
    report = _review.load(stem)
    _review.accept_grounded(report)
    _review.save(report)


def _sync_widgets(key: str, report: dict):
    """Put the saved decisions into the widgets before they are drawn."""
    stem = report["stem"]
    for c in report["comments"]:
        d = c.get("decision", _review.PENDING)
        st.session_state[_wkey(key, stem, c["id"], "d")] = None if d == _review.PENDING else d
        if d == _review.EDIT:
            st.session_state[_wkey(key, stem, c["id"], "c")] = c.get("edited_comment") or c["comment"]
            st.session_state[_wkey(key, stem, c["id"], "q")] = c.get("edited_question", c["question"])


def _comment_card(key: str, report: dict, c: dict):
    stem = report["stem"]
    st.markdown(
        _badge(_review.SEVERITIES[c["severity"]], SEVERITY_TONES[c["severity"]]) + " "
        + _badge(_review.CATEGORIES[c["category"]], "info") + " "
        + (_badge("Kutipan cocok", "good") if c.get("grounded") else _badge("Kutipan tidak ditemukan, cek manual", "bad")),
        unsafe_allow_html=True,
    )
    if c.get("quote"):
        st.caption(f"Bagian yang dikomentari: “{c['quote']}”")
    st.markdown(_e(c["comment"]))
    if c["question"]:
        st.markdown(f"*Pertanyaan pemandu:* {_e(c['question'])}")
    choice = st.radio("Keputusan konsultan", CHOICES, format_func=_review.DECISIONS.get, horizontal=True,
                      key=_wkey(key, stem, c["id"], "d"), on_change=_on_decision, args=(key, stem, c["id"]))
    if choice == _review.EDIT:
        st.text_area("Komentar untuk mahasiswa", key=_wkey(key, stem, c["id"], "c"),
                     on_change=_on_edit, args=(key, stem, c["id"]))
        st.text_input("Pertanyaan pemandu", key=_wkey(key, stem, c["id"], "q"),
                      on_change=_on_edit, args=(key, stem, c["id"]))
    st.divider()


def _show(stem: str, key: str):
    report = _review.load(stem)
    _sync_widgets(key, report)
    s = report["summary"]
    d = _review.decision_counts(report)
    total = len(report["comments"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Paragraf isi", s["paragraphs"])
    c2.metric("Komentar AI", total)
    c3.metric("Kutipan tidak cocok", s.get("ungrounded", 0))
    c4.metric("Sitasi bermasalah", s["references_flagged"] + s["citations_missing"])

    if report["priorities"]:
        with st.container(border=True):
            st.markdown("##### Prioritas perbaikan")
            for i, p in enumerate(report["priorities"], 1):
                st.markdown(f"{i}. {p}")
    if report["strengths"]:
        with st.container(border=True):
            st.markdown("##### Yang sudah baik")
            for p in report["strengths"]:
                st.markdown(f"- {p}")

    tab_c, tab_s = st.tabs(["Komentar per paragraf", "Pemeriksaan sitasi"])
    with tab_c:
        st.caption(
            "Putuskan setiap komentar AI. Hanya komentar yang diterima atau diedit yang masuk ke dokumen mahasiswa. "
            "“Kutipan tidak ditemukan” berarti AI mengutip kalimat yang tidak ada di paragraf itu: periksa dulu."
        )
        st.progress(1 - d[_review.PENDING] / total if total else 1.0,
                    text=f"{total - d[_review.PENDING]} dari {total} komentar sudah diputuskan "
                         f"({d[_review.ACCEPT]} terima, {d[_review.EDIT]} edit, {d[_review.DROP]} buang)")
        grounded_pending = sum(1 for c in report["comments"]
                               if c.get("grounded") and c.get("decision") == _review.PENDING)
        if grounded_pending:
            st.button(f"Terima {grounded_pending} komentar yang kutipannya cocok", key=f"{key}_{stem}_bulk",
                      on_click=_on_accept_grounded, args=(stem,))

        by_par = {}
        for c in report["comments"]:
            by_par.setdefault(c["paragraph"], []).append(c)
        if not by_par:
            st.info("Tidak ada komentar per paragraf.")
        for p in report["paragraphs"]:
            cs = by_par.get(p["n"])
            if not cs:
                continue
            where = f" · {p['section']}" if p["section"] else ""
            open_n = sum(1 for c in cs if c.get("decision") == _review.PENDING)
            label = f"P{p['n']}{where} · {len(cs)} komentar" + (f" · {open_n} belum diputuskan" if open_n else "")
            with st.expander(label, expanded=bool(open_n)):
                st.caption(f"Paragraf yang diawali: “{p['opening']}”")
                for c in cs:
                    _comment_card(key, report, c)

    with tab_s:
        refs = report["citations"]["references"]
        cites = report["citations"]["citations"]
        rows = [{"Rujukan": r["raw"][:140], "Status": _verify.LABELS.get(r["status"], r["status"]), "Catatan": r.get("note", "")}
                for r in refs]
        rows += [{"Rujukan": f"(teks) {c['text']}", "Status": _verify.LABELS.get(c["status"], c["status"]), "Catatan": c.get("note", "")}
                 for c in cites if c["status"] != _verify.CITE_OK]
        if rows:
            render_table(rows)
        else:
            st.info("Tidak ditemukan sitasi atau daftar pustaka di draf.")

    st.markdown("##### Kirim ke mahasiswa")
    ready = _review.is_ready(report)
    if not ready:
        st.info(f"Masih ada {d[_review.PENDING]} komentar yang belum diputuskan. "
                "Dokumen untuk mahasiswa baru bisa dibuat setelah semua diputuskan.")
    col_d1, col_d2 = st.columns(2, vertical_alignment="bottom")
    col_d1.download_button(
        "Unduh Markdown" if ready else "Unduh versi internal (Markdown)",
        data=_review.report_markdown(report), file_name=f"{stem}.md", mime="text/markdown",
        use_container_width=True, key=f"{key}_{stem}_md",
    )
    reviewer = col_d2.text_input("Nama konsultan pemeriksa (tercantum di Word):", key=f"{key}_{stem}_reviewer")
    if st.button("Buat Word berkop firma", type="primary", use_container_width=True, key=f"{key}_{stem}_docx_btn"):
        try:
            st.session_state[f"{key}_{stem}_docx"] = str(_review.export_docx(report, reviewer))
        except ValueError as e:
            st.warning(str(e))
        except Exception as e:
            st.error(f"Gagal membuat dokumen: {e}")
    docx = st.session_state.get(f"{key}_{stem}_docx")
    if docx and Path(docx).exists():
        st.download_button(f"Unduh Word: {Path(docx).name}", data=Path(docx).read_bytes(), file_name=Path(docx).name,
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           use_container_width=True, key=f"{key}_{stem}_docx_dl")


def render(ctx: AppContext):
    """Review Draf Mahasiswa."""
    render_hero(
        title="Review Draf Mahasiswa",
        subtitle="Umpan balik ala pembimbing untuk draf skripsi, tesis, atau disertasi: komentar dan pertanyaan "
                 "pemandu per paragraf, plus pemeriksaan sitasi. Draf tidak ditulis ulang.",
    )

    tab_new, tab_saved = st.tabs(["Review baru", "Review tersimpan"])
    with tab_new:
        with st.container(border=True):
            uploaded = st.file_uploader("Unggah draf (.docx, .md, .txt)", type=["docx", "md", "txt"])
            pasted = ""
            if uploaded is None:
                pasted = st.text_area("Atau tempel teks draf", height=180,
                                      placeholder="Tempel bab atau bagian draf, termasuk daftar pustaka kalau ada.")
            title = st.text_input("Judul / nama mahasiswa (opsional)")
            col2, col3 = st.columns(2, vertical_alignment="bottom")
            level = col2.selectbox("Jenjang", list(_review.LEVELS), index=1,
                                   format_func=lambda k: _review.LEVELS[k].capitalize())
            online = col3.toggle("Cek sitasi ke Crossref", value=True)
            go = st.button("Review draf", type="primary", use_container_width=True)

        if go and uploaded is None and not pasted.strip():
            st.warning("Unggah file draf atau tempel teksnya dulu.")
        elif go:
            try:
                with st.spinner("Membaca draf dan menyusun komentar. Draf panjang bisa beberapa menit..."):
                    report = _run(uploaded, pasted, title, level, online)
                    _review.save(report)
                st.session_state["review_current"] = report["stem"]
            except Exception as e:
                st.error(f"Review gagal: {e}")

        current = st.session_state.get("review_current")
        if current:
            st.success(f"Review tersimpan: {current}")
            _show(current, key="rv_new")

    with tab_saved:
        saved = _review.load_saved()
        if not saved:
            st.info("Belum ada review tersimpan.")
        else:
            labels = {s["report"]["stem"]: f"{s['report']['title']} · {s['report']['reviewed_at'][:16].replace('T', ' ')}"
                      for s in saved}
            pick = st.selectbox("Pilih review", list(labels), format_func=labels.get)
            _show(pick, key="rv_saved")
