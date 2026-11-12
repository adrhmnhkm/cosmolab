"""Dashboard page: Review Draf Mahasiswa.

A consultant uploads a student's draft and gets supervisor-style comments and
a citation check. The page never shows rewritten text, only comments and
guiding questions.
"""

import tempfile
from pathlib import Path

import streamlit as st
from cosmolab import review as _review
from cosmolab import verify as _verify
from cosmolab.ui.components import _badge, _e, render_hero, render_table
from cosmolab.ui.context import AppContext

SEVERITY_TONES = {_review.PENTING: "bad", _review.SARAN: "warn", _review.CATATAN: "muted"}


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


def _show(report: dict, md_path: Path | None, key: str):
    s = report["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Paragraf isi", s["paragraphs"])
    c2.metric("Komentar penting", s["by_severity"][_review.PENTING])
    c3.metric("Saran & catatan", s["by_severity"][_review.SARAN] + s["by_severity"][_review.CATATAN])
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
            worst = min(cs, key=lambda c: list(_review.SEVERITIES).index(c["severity"]))["severity"]
            with st.expander(f"P{p['n']}{where} · {len(cs)} komentar", expanded=worst == _review.PENTING):
                st.caption(f"Paragraf yang diawali: “{p['opening']}”")
                for c in cs:
                    st.markdown(
                        _badge(_review.SEVERITIES[c["severity"]], SEVERITY_TONES[c["severity"]]) + " "
                        + _badge(_review.CATEGORIES[c["category"]], "info"),
                        unsafe_allow_html=True,
                    )
                    st.markdown(_e(c["comment"]))
                    if c["question"]:
                        st.markdown(f"*Pertanyaan pemandu:* {_e(c['question'])}")

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

    st.markdown("##### Unduh catatan review")
    md_text = _review.report_markdown(report)
    col_d1, col_d2 = st.columns(2)
    col_d1.download_button("Unduh Markdown", data=md_text, file_name=(md_path.name if md_path else "review.md"),
                           mime="text/markdown", use_container_width=True, key=f"{key}_md")
    reviewer = col_d2.text_input("Nama konsultan pemeriksa (tercantum di Word):", key=f"{key}_reviewer")
    if col_d2.button("Buat Word berkop firma", disabled=not reviewer.strip(), use_container_width=True,
                    key=f"{key}_docx_btn"):
        try:
            st.session_state[f"{key}_docx"] = str(_review.export_docx(report, reviewer))
        except Exception as e:
            st.error(f"Gagal membuat dokumen: {e}")
    docx = st.session_state.get(f"{key}_docx")
    if docx and Path(docx).exists():
        st.download_button(f"Unduh Word: {Path(docx).name}", data=Path(docx).read_bytes(), file_name=Path(docx).name,
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           use_container_width=True, key=f"{key}_docx_dl")


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
                    paths = _review.save(report)
                st.session_state["review_current"] = {"report": report, "md": str(paths["md"])}
                st.session_state.pop("rv_new_docx", None)
            except Exception as e:
                st.error(f"Review gagal: {e}")

        current = st.session_state.get("review_current")
        if current:
            st.success(f"Review tersimpan: {Path(current['md']).name}")
            _show(current["report"], Path(current["md"]), key="rv_new")

    with tab_saved:
        saved = _review.load_saved()
        if not saved:
            st.info("Belum ada review tersimpan.")
        else:
            labels = {i: f"{s['report']['title']} · {s['report']['reviewed_at'][:16].replace('T', ' ')}"
                      for i, s in enumerate(saved)}
            pick = st.selectbox("Pilih review", list(labels), format_func=labels.get)
            _show(saved[pick]["report"], saved[pick]["path"], key=f"rv_saved_{pick}")
