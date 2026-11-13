"""Dashboard page: Review Draf Mahasiswa.

A consultant uploads a student's draft and gets supervisor-style comments and
a citation check. The page never shows rewritten text, only comments and
guiding questions. The consultant accepts, edits, or drops every AI comment;
only accepted and edited comments reach the student's Word file.

The similarity check (no AI) marks sentences that are close to a paper in the
collection or to a cited work. Its findings go to the student unless the
consultant hides them.
"""

import math
import tempfile
import time
from pathlib import Path

import streamlit as st
from cosmolab import config
from cosmolab import team as _team
from cosmolab import review as _review
from cosmolab import similarity as _similarity
from cosmolab import coverage as _coverage
from cosmolab import verify as _verify
from cosmolab.ui.components import _badge, _e, render_hero, render_table
from cosmolab.ui.context import AppContext

SEVERITY_TONES = {_review.PENTING: "bad", _review.SARAN: "warn", _review.CATATAN: "muted"}
SIM_TONES = {_similarity.NO_CITATION: "bad", _similarity.WRONG_SOURCE: "warn", _similarity.TOO_CLOSE: "info"}
CHOICES = [_review.ACCEPT, _review.EDIT, _review.DROP]
PAGE_SIZE = 10
STATUS_FILTERS = {"semua": "Semua", "belum": "Belum diputuskan", "sudah": "Sudah diputuskan"}


def _uploaded_md(uploaded) -> str:
    """The uploaded draft as Markdown. Kept per file so the estimate does not reread it on every click."""
    key = ("_review_draft_md", uploaded.name, uploaded.size)
    cached = st.session_state.get("_review_draft_md")
    if cached and cached[0] == key:
        return cached[1]
    suffix = Path(uploaded.name).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"draf{suffix}"
        path.write_bytes(uploaded.getvalue())
        md = _review.read_draft(path)
    st.session_state["_review_draft_md"] = (key, md)
    return md


def _estimate_caption(uploaded, pasted: str, online: bool, feedback: bool, similarity: bool):
    try:
        md = _uploaded_md(uploaded) if uploaded is not None else pasted
    except Exception as e:
        st.caption(f"Draf belum bisa dibaca: {_e(str(e))}")
        return
    if md.strip():
        st.caption(_e(_review.estimate_text(_review.estimate(md, online=online, feedback=feedback,
                                                               similarity=similarity))))


def _run(uploaded, pasted: str, title: str, level: str, online: bool, feedback: bool, similarity: bool,
         progress_cb=None) -> dict:
    if uploaded is not None:
        md = _uploaded_md(uploaded)
        name = title or Path(uploaded.name).stem.replace("_", " ")
        source = uploaded.name
    else:
        md, name, source = pasted, title or "Draf", "teks ditempel"
    return _review.review_text(md, title=name, level=level, online=online, source=source,
                               feedback=feedback, similarity=similarity, progress_cb=progress_cb)


def _run_with_log(*args) -> dict | None:
    """Run the review inside a status box: progress bar, finished stages with durations, elapsed time."""
    plog = _review.ProgressLog()
    with st.status("Memulai review...", expanded=True) as box:
        bar = st.progress(0.0)
        log = st.empty()

        def lines(extra: str = "") -> str:
            out = [f"- {_e(msg)} · {_review.fmt_duration(sec)}" for msg, sec in plog.finished]
            return "\n".join(out + ([extra] if extra else []))

        def cb(kind, msg, data=None):
            plog.handle(kind, msg, data)
            box.update(label=f"{plog.label} · {_review.fmt_duration(plog.elapsed)} berjalan")
            bar.progress(plog.fraction, text=_e(plog.now))
            log.markdown(lines())

        try:
            report = _run(*args, progress_cb=cb)
            t = time.monotonic()
            _review.save(report)
            plog.finished.append(("Menyimpan hasil", time.monotonic() - t))
        except Exception as e:
            box.update(label=f"Gagal saat: {plog.label}", state="error", expanded=True)
            log.markdown(lines(f"- **Gagal saat {_e(plog.label)}:** {_e(str(e))}"))
            return None
        bar.progress(1.0, text="Selesai")
        log.markdown(lines())
        box.update(label=f"Review selesai dalam {_review.fmt_duration(plog.elapsed)}", state="complete",
                   expanded=False)
    return report


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


def _on_hide(key: str, stem: str, fid: str):
    report = _review.load(stem)
    _similarity.set_hidden(report["similarity"], fid, st.session_state.get(_wkey(key, stem, fid, "h"), False))
    report["summary"] = _review.summarize(report)
    _review.save(report)


def _on_rerun_similarity(stem: str, online: bool):
    report = _review.load(stem)
    try:
        _review.save(_review.run_similarity(report, online=online))
    except ValueError as e:
        st.session_state[f"{stem}_sim_error"] = str(e)


def _on_accept_grounded(stem: str):
    report = _review.load(stem)
    _review.accept_grounded(report)
    _review.save(report)


def _sync_comment_widgets(key: str, report: dict, comments: list[dict]):
    """Put the saved decisions into the comment widgets before they are drawn."""
    stem = report["stem"]
    for c in comments:
        d = c.get("decision", _review.PENDING)
        st.session_state[_wkey(key, stem, c["id"], "d")] = None if d == _review.PENDING else d
        if d == _review.EDIT:
            st.session_state[_wkey(key, stem, c["id"], "c")] = c.get("edited_comment") or c["comment"]
            st.session_state[_wkey(key, stem, c["id"], "q")] = c.get("edited_question", c["question"])


def _sync_similarity_widgets(key: str, report: dict):
    stem = report["stem"]
    for f in (report.get("similarity") or {}).get("findings", []):
        st.session_state[_wkey(key, stem, f["id"], "h")] = bool(f.get("hidden"))


def _comment_card(key: str, report: dict, c: dict, par: dict | None = None):
    stem = report["stem"]
    if par:
        where = f" · {_e(par['section'])}" if par.get("section") else ""
        st.markdown(f"**P{par['n']}**{where}")
        st.caption(f"Paragraf yang diawali: “{par['opening']}”")
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


def _reset_page(page_key: str):
    st.session_state[page_key] = 1


def _next_page(page_key: str, pages: int):
    st.session_state[page_key] = min(pages, st.session_state.get(page_key, 1) + 1)


@st.fragment
def _comments_panel(key: str, stem: str):
    """The AI comments, ten per page with filters.

    A fragment: deciding a comment redraws only this list, not the whole page.
    When the review becomes ready (or stops being ready) the whole page is
    redrawn so the Word section below updates.
    """
    report = _review.load(stem)
    comments = report["comments"]
    total = len(comments)
    d = _review.decision_counts(report)

    ready = _review.is_ready(report)
    seen_key = f"{key}_{stem}_ready_seen"
    if st.session_state.get(seen_key, ready) != ready:
        st.session_state[seen_key] = ready
        st.rerun(scope="app")
    st.session_state[seen_key] = ready

    st.progress(1 - d[_review.PENDING] / total if total else 1.0,
                text=f"{total - d[_review.PENDING]} dari {total} komentar sudah diputuskan "
                     f"({d[_review.ACCEPT]} terima, {d[_review.EDIT]} edit, {d[_review.DROP]} buang)")
    if not comments:
        st.info("Tidak ada komentar per paragraf.")
        return
    grounded_pending = sum(1 for c in comments if c.get("grounded") and c.get("decision") == _review.PENDING)
    if grounded_pending:
        st.button(f"Terima {grounded_pending} komentar yang kutipannya cocok", key=f"{key}_{stem}_bulk",
                  on_click=_on_accept_grounded, args=(stem,))

    page_key = f"{key}_{stem}_page"
    col_s, col_t = st.columns(2)
    status = col_s.selectbox("Tampilkan", list(STATUS_FILTERS), format_func=STATUS_FILTERS.get,
                             key=f"{key}_{stem}_fstatus", on_change=_reset_page, args=(page_key,))
    severity = col_t.selectbox("Tingkat", ["semua"] + list(_review.SEVERITIES),
                               format_func=lambda k: "Semua tingkat" if k == "semua" else _review.SEVERITIES[k],
                               key=f"{key}_{stem}_fsev", on_change=_reset_page, args=(page_key,))
    shown = [c for c in comments
             if (status == "semua" or (c.get("decision") == _review.PENDING) == (status == "belum"))
             and (severity == "semua" or c["severity"] == severity)]
    if not shown:
        st.info("Tidak ada komentar dengan filter ini.")
        return

    pages = math.ceil(len(shown) / PAGE_SIZE)
    if st.session_state.get(page_key, 1) > pages:
        st.session_state[page_key] = 1
    page = st.selectbox("Halaman", list(range(1, pages + 1)), key=page_key,
                        format_func=lambda n: f"{n} dari {pages}") if pages > 1 else 1
    start = (page - 1) * PAGE_SIZE
    chunk = shown[start:start + PAGE_SIZE]
    st.caption(f"Komentar {start + 1}–{start + len(chunk)} dari {len(shown)}"
               + ("" if status == "semua" and severity == "semua" else f" (difilter dari {total})"))

    _sync_comment_widgets(key, report, chunk)
    pars = {p["n"]: p for p in report["paragraphs"]}
    for c in chunk:
        with st.container(border=True):
            _comment_card(key, report, c, pars.get(c["paragraph"]))
    if page < pages:
        st.button("Halaman berikutnya", key=f"{key}_{stem}_next", on_click=_next_page, args=(page_key, pages))


def _run_fill(stem: str):
    """Download the cited works with a live log, then rerun the similarity check."""
    report = _review.load(stem)
    with st.status("Mencari teks lengkap sumber yang dikutip...", expanded=True) as box:
        bar = st.progress(0.0)
        log = st.empty()
        lines = []

        def cb(kind, msg, data=None):
            data = data or {}
            if kind == "item" and data.get("total"):
                bar.progress(data["done"] / data["total"], text=f"{data['done']} dari {data['total']} sumber")
            lines.append(msg)
            log.markdown("\n".join(f"- {_e(x)}" for x in lines[-8:]))

        try:
            _review.save(_review.fill_sources(report, progress_cb=cb))
            box.update(label="Selesai. Cek kemiripan dijalankan ulang dengan sumber baru.", state="complete")
        except Exception as e:
            box.update(label=f"Gagal: {e}", state="error")


def _coverage_section(key: str, report: dict):
    stem = report["stem"]
    st.markdown("##### Cakupan sumber yang dikutip")
    summ = _coverage.summary(report)
    if not summ:
        st.caption("Cek kemiripan baru memakai abstrak sumber yang dikutip. Unduh teks lengkapnya (hanya yang legal dan "
                   "terbuka) supaya hasilnya lebih berarti. Draf dengan 50 sumber bisa beberapa menit.")
        if st.button("Lengkapi pembanding dari daftar pustaka", key=f"{key}_{stem}_fill", type="primary"):
            _run_fill(stem)
            st.rerun()
        return

    st.markdown(_coverage.summary_text(summ))
    items = report["coverage"]["items"]
    with st.expander(f"Rincian per sumber ({len(items)})"):
        render_table([{"Sumber": it["raw"][:140], "Jenis": _coverage.KINDS[it["kind"]],
                       "Status": _coverage.STATUS_LABELS[it["status"]]} for it in items])
    if st.button("Cari lagi sumber baru", key=f"{key}_{stem}_fill_again",
                 help="Sumber yang sudah dicari tidak dicari ulang. Paper yang baru ditambahkan ke koleksi ikut dihitung."):
        _run_fill(stem)
        st.rerun()

    missing = [it for it in items if it["status"] == _coverage.MISSING]
    if missing:
        with st.expander(f"Sumber yang perlu dikirim mahasiswa ({len(missing)})"):
            st.caption("Minta mahasiswa mengirim PDF atau foto halaman yang dikutip. Unggah di sini; cek kemiripan "
                       "dijalankan ulang otomatis.")
            for it in missing:
                st.markdown(f"**{_e(_coverage.KINDS[it['kind']])}** · {_e(it['raw'][:220])}")
                up = st.file_uploader("PDF sumber", type=["pdf"], key=_wkey(key, stem, f"src{it['i']}", "up"),
                                      label_visibility="collapsed")
                if up is not None and st.button("Simpan sumber ini", key=_wkey(key, stem, f"src{it['i']}", "save")):
                    with st.spinner("Membaca PDF dan menjalankan ulang cek kemiripan..."):
                        _review.save(_review.add_source_upload(_review.load(stem), it["i"], up.getvalue(), up.name))
                    st.rerun()
                st.divider()


def _similarity_tab(key: str, report: dict):
    stem, sim = report["stem"], report.get("similarity")
    err = st.session_state.pop(f"{stem}_sim_error", None)
    if err:
        st.warning(err)
    if not sim:
        if report.get("draft_md"):
            st.info("Cek kemiripan belum dijalankan untuk review ini.")
            st.button("Jalankan cek kemiripan", key=f"{key}_{stem}_sim_run", on_click=_on_rerun_similarity,
                      args=(stem, True), type="primary")
        else:
            st.info("Review ini dibuat sebelum cek kemiripan ada. Unggah ulang drafnya untuk menjalankan cek.")
        return

    src = sim["sources"]
    st.caption(_similarity.CAVEAT)
    st.markdown(f"**Perkiraan kemiripan: {sim['score']}%** dari {sim['words']} kata. Pembanding: {src['korpus']} paper "
                f"di koleksi proyek dan {src['dikutip']} abstrak sumber yang dikutip"
                + (f" ({src['dikutip_gagal']} sumber dikutip tidak punya abstrak)." if src.get("dikutip_gagal") else "."))
    if sim.get("weak"):
        st.warning(_similarity.weak_message(sim))
    if sim.get("top_sources"):
        render_table([{"Sumber": _similarity.source_label(t), "Asal": "Koleksi" if t["kind"] == "korpus" else "Dikutip",
                       "Porsi draf": f"{t['pct']}%"} for t in sim["top_sources"]])
    st.button("Jalankan ulang (misalnya setelah menambah paper)", key=f"{key}_{stem}_sim_rerun",
              on_click=_on_rerun_similarity, args=(stem, True))

    _coverage_section(key, report)

    if not sim["findings"]:
        if not sim.get("weak"):
            st.success("Tidak ada kalimat yang terlalu mirip dengan sumber pembanding.")
        return
    st.caption("Temuan masuk ke dokumen mahasiswa. Centang **Sembunyikan** kalau temuan keliru, misalnya kalimat "
               "definisi baku atau kutipan yang tanda petiknya hilang saat dokumen diunggah.")
    for label, title in _similarity.LABELS.items():
        group = [f for f in sim["findings"] if f["label"] == label]
        if not group:
            continue
        with st.expander(f"{title} ({len(group)})", expanded=label == _similarity.NO_CITATION):
            st.caption(_similarity.ADVICE[label])
            for f in group:
                st.markdown(_badge(f"P{f['paragraph']} · mirip {f['match_pct']}%", SIM_TONES[label]),
                            unsafe_allow_html=True)
                st.markdown(f"“{_e(f['sentence'])}”")
                st.caption(f"Sumber: {_similarity.source_label(f['source'])}"
                           + (f" · Dikutip sebagai: {f['cited_as']}" if f.get("cited_as") else ""))
                if f.get("source_excerpt"):
                    st.caption(f"Teks sumber: “{f['source_excerpt']}”")
                st.checkbox("Sembunyikan dari dokumen mahasiswa", key=_wkey(key, stem, f["id"], "h"),
                            on_change=_on_hide, args=(key, stem, f["id"]))
                st.divider()


def _show(stem: str, key: str):
    report = _review.load(stem)
    _sync_similarity_widgets(key, report)
    s = report["summary"]
    d = _review.decision_counts(report)
    total = len(report["comments"])

    sim = report.get("similarity")
    with_ai = report.get("feedback", True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Paragraf isi", s["paragraphs"])
    c2.metric("Komentar AI", total if with_ai else "-")
    c3.metric("Kutipan tidak cocok", s.get("ungrounded", 0) if with_ai else "-")
    cc = _review.citation_counts(report)  # computed here too: older saved reports lack these keys
    c4.metric("Sitasi bermasalah", cc["citations_problem"],
              delta=f"{cc['references_manual']} perlu cek manual" if cc["references_manual"] else None,
              delta_color="off",
              help="Bermasalah: dikutip tapi tidak ada di daftar pustaka, atau tahun/penulis tidak cocok. "
                   "Cek manual: tidak ditemukan di koleksi maupun Crossref. Sering terjadi pada buku dan jurnal lokal; "
                   "belum tentu salah.")
    c5.metric("Kemiripan (perkiraan)", f"{sim['score']}%" if sim else "-",
              help="Dibandingkan dengan koleksi proyek dan abstrak sumber yang dikutip. Bukan skor Turnitin.")

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

    tab_c, tab_s, tab_m = st.tabs(["Komentar per paragraf", "Pemeriksaan sitasi", "Cek kemiripan"])
    with tab_m:
        _similarity_tab(key, report)
    with tab_c:
        if not with_ai:
            st.info("Review ini dijalankan tanpa komentar AI: hanya pemeriksaan sitasi dan kemiripan.")
        st.caption(
            "Putuskan setiap komentar AI. Hanya komentar yang diterima atau diedit yang masuk ke dokumen mahasiswa. "
            "“Kutipan tidak ditemukan” berarti AI mengutip kalimat yang tidak ada di paragraf itu: periksa dulu."
        )
        st.session_state[f"{key}_{stem}_ready_seen"] = _review.is_ready(report)
        _comments_panel(key, stem)

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
        data=lambda: _review.report_markdown(_review.load(stem)), file_name=f"{stem}.md", mime="text/markdown",
        use_container_width=True, key=f"{key}_{stem}_md", on_click="ignore",
    )
    if f"{key}_{stem}_reviewer" not in st.session_state:
        st.session_state[f"{key}_{stem}_reviewer"] = _team.current_name()  # the logged-in account; can be changed
    reviewer = col_d2.text_input("Nama konsultan pemeriksa (tercantum di Word):", key=f"{key}_{stem}_reviewer")
    if st.button("Buat Word berkop firma", type="primary", use_container_width=True, key=f"{key}_{stem}_docx_btn"):
        try:
            st.session_state[f"{key}_{stem}_docx"] = str(_review.export_docx(_review.load(stem), reviewer))
        except ValueError as e:
            st.warning(str(e))
        except Exception as e:
            st.error(f"Gagal membuat dokumen: {e}")
    docx = st.session_state.get(f"{key}_{stem}_docx")
    if docx and Path(docx).exists():
        st.download_button(f"Unduh Word: {Path(docx).name}", data=Path(docx).read_bytes(), file_name=Path(docx).name,
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           use_container_width=True, key=f"{key}_{stem}_docx_dl", on_click="ignore")


def render(ctx: AppContext):
    """Review Draf Mahasiswa."""
    render_hero(
        title="Review Draf Mahasiswa",
        subtitle="Umpan balik ala pembimbing untuk draf skripsi, tesis, atau disertasi: komentar dan pertanyaan "
                 "pemandu per paragraf, plus pemeriksaan sitasi. Draf tidak ditulis ulang.",
    )
    if not config.PROJECT:
        st.warning("Anda memakai data utama. Buat proyek untuk klien ini supaya review dan pembanding kemiripannya "
                   "terpisah: `cosmolab project new <nama>`, lalu `cosmolab -P <nama> ui`.")

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
            col4, col5 = st.columns(2)
            feedback = col4.checkbox("Komentar pembimbing (AI)", value=True,
                                     help="Matikan untuk pemeriksaan sitasi dan kemiripan saja, tanpa biaya AI.")
            sim_on = col5.checkbox("Cek kemiripan", value=True,
                                   help="Bandingkan setiap kalimat dengan koleksi proyek dan abstrak sumber yang dikutip.")
            _estimate_caption(uploaded, pasted, online, feedback, sim_on)
            go = st.button("Review draf", type="primary", use_container_width=True)

        if go and uploaded is None and not pasted.strip():
            st.warning("Unggah file draf atau tempel teksnya dulu.")
        elif go and not (feedback or sim_on):
            st.warning("Pilih minimal satu: komentar pembimbing atau cek kemiripan.")
        elif go:
            report = _run_with_log(uploaded, pasted, title, level, online, feedback, sim_on)
            if report:
                st.session_state["review_current"] = report["stem"]

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
