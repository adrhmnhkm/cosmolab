"""Dashboard page: Pusat Akurasi."""

import json
import streamlit as st
from cosmolab import config
from cosmolab import db
from cosmolab import analysis_check as _acheck
from cosmolab import corrections as _corrections
from cosmolab import metadata as _metadata
from cosmolab import evaluate as _evaluate
from cosmolab import audit as _audit
from cosmolab.ui.components import _e
from cosmolab.ui.components import render_table
from cosmolab.ui.components import render_hero
from cosmolab.ui.components import _badge
from cosmolab.ui.papers import _meta_store
from cosmolab.ui.context import AppContext


def render_accuracy_page(ctx: AppContext):
    render_hero(
        title="Periksa Akurasi",
        subtitle="Cek analisis ke isi PDF, cek metadata dan retraksi, ukur akurasi sistem, dan simpan jejak setiap langkah AI.",
        icon="",
    )
    tab_an, tab_meta, tab_eval, tab_log = st.tabs(["Cek analisis", "Metadata & retraksi", "Uji akurasi", "Log audit"])
    papers = db.get_all_papers_with_analyses()
    analyzed = [p for p in papers if p.get("thesis")]

    with tab_an:
        st.caption("Setiap pernyataan analisis AI (tesis, premis, temuan, kesimpulan) dibandingkan dengan teks PDF. "
                   "Kutipan dicari di PDF tanpa AI. Hasil dan koreksi per paper bisa dibuka di Koleksi paper, bagian detail analisis.")
        rows = []
        for p in analyzed:
            sc = _acheck.score(_acheck.load_check(p["file"]))
            cs = _corrections.summary(p["file"])
            rows.append({
                "Paper": f"{p.get('title') or p['file']} ({p.get('year') or 'n.d.'})",
                "Dicek": (sc.get("time") or "")[:10] if sc.get("checked") else "belum",
                "Didukung": f"{sc['supported']}/{sc['statements']}" if sc.get("checked") else "",
                "Perlu dicek": str(sc.get("flagged", "")) if sc.get("checked") else "",
                "Kutipan ada di PDF": f"{sc['quotes_found']}/{sc['quotes']}" if sc.get("checked") else "",
                "Koreksi peneliti": str(cs["total"] or ""),
                "_file": p["file"],
            })
        unchecked = [r["_file"] for r in rows if r["Dicek"] == "belum"]
        c1, c2 = st.columns([3, 1])
        with c1:
            pick = st.multiselect("Paper yang dicek", options=[r["_file"] for r in rows], default=unchecked[:5],
                                  format_func=lambda f: next(r["Paper"] for r in rows if r["_file"] == f)[:90],
                                  key="acc_pick")
        with c2:
            st.write("")
            go = st.button(f"Cek {len(pick)} paper", type="primary", width="stretch", disabled=not pick, key="acc_go")
        if go:
            bar = st.progress(0.0, text="Mulai...")
            _acheck.check_many(pick, model=config.LLM_MODEL,
                               progress_cb=lambda d, n, f: bar.progress(d / n, text=f"{d}/{n} selesai"))
            st.rerun()
        render_table([{k: v for k, v in r.items() if k != "_file"} for r in rows])

    with tab_meta:
        st.caption("Judul, tahun, dan penulis tiap paper dicocokkan ke Crossref atau DataCite lewat DOI. "
                   "Paper yang ditarik (retracted), ditarik penulis, atau diberi peringatan editor ditandai.")
        store = _meta_store()
        if st.button("Cek semua paper sekarang", type="primary", key="meta_go"):
            bar = st.progress(0.0, text="Mulai...")
            store = _metadata.check_all(progress_cb=lambda d, n, t: bar.progress(d / n, text=f"{d}/{n}: {t[:60]}"))
            st.session_state["_meta_store"] = store
        if store:
            bad = _metadata.flagged(store)
            if bad:
                st.error("Paper ini ditarik atau bermasalah. Jangan dikutip sebagai bukti tanpa membaca pemberitahuannya: "
                         + "; ".join(f"{r.get('title')} ({', '.join(n['label'] for n in r['notices'] if n.get('serious'))})" for r in bad))
            counts = {}
            for r in store.values():
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            tones = {_metadata.OK: "good", _metadata.DIFF: "warn", _metadata.NOT_FOUND: "warn",
                     _metadata.INVALID: "bad", _metadata.NO_DOI: "muted", _metadata.ERROR: "muted"}
            st.markdown("<div class='cl-badges'>" + "".join(
                _badge(f"{n} {_metadata.STATUS_LABELS[s].lower()}", tones.get(s, "muted")) for s, n in counts.items()
            ) + "</div>", unsafe_allow_html=True)
            render_table([{
                "Paper": r.get("title"),
                "DOI": r.get("doi") or "",
                "Status": _metadata.STATUS_LABELS.get(r["status"], r["status"]),
                "Beda": "; ".join(f"{d['field']}: kita {d['ours']}, sumber {d['crossref']}" for d in r.get("diffs", [])),
                "Pemberitahuan": "; ".join(n["label"] for n in r.get("notices", [])),
                "Dicek": (r.get("time") or "")[:10],
            } for r in sorted(store.values(), key=lambda r: (r["status"] == _metadata.OK, r.get("title") or ""))])
        else:
            st.info("Belum pernah dicek.")
        st.markdown("**Ekspor daftar pustaka**")
        st.caption("Memakai data Crossref bila sudah cocok. Entri yang belum terverifikasi atau bermasalah diberi catatan.")
        d1, d2 = st.columns(2)
        d1.download_button("Unduh BibTeX (.bib)", _metadata.to_bibtex(papers, store), "references.bib", "text/plain", width="stretch")
        d2.download_button("Unduh RIS (Zotero, Mendeley)", _metadata.to_ris(papers, store), "references.ris",
                           "application/x-research-info-systems", width="stretch")

    with tab_eval:
        st.caption("Set uji berisi pertanyaan dan klaim dari koleksi sendiri, beserta halaman dan jawaban yang benar. "
                   "Dengan ini akurasi pencarian dan cek klaim bisa diukur, dan setiap perubahan bisa dibandingkan.")
        gold = _evaluate.load_gold()
        reviewed = sum(1 for g in gold if g.get("reviewed"))
        st.markdown(f"Set uji: **{len(gold)} soal**, {reviewed} sudah diperiksa peneliti.")
        g1, g2 = st.columns([1, 3])
        n_new = g1.number_input("Paper baru", min_value=1, max_value=30, value=5, key="ev_n")
        g2.write("")
        if g2.button("Buat draf soal dengan AI", key="ev_draft"):
            bar = st.progress(0.0, text="Mulai...")
            new = _evaluate.draft_gold(n_papers=int(n_new), model=config.LLM_MODEL,
                                       progress_cb=lambda d, n, t: bar.progress(d / n, text=f"{d}/{n}: {t[:60]}"))
            st.success(f"{len(new)} soal baru ditambahkan. Periksa dulu sebelum dipakai sebagai patokan.")
            gold = _evaluate.load_gold()
        if gold:
            st.caption("Centang Diperiksa untuk soal yang sudah benar. Ubah teks atau jawaban bila perlu, lalu simpan.")
            table = [{
                "id": g["id"],
                "Jenis": "Pencarian" if g["kind"] == "retrieval" else "Klaim",
                "Soal": g.get("question") or g.get("claim"),
                "Jawaban benar": f"halaman {', '.join(map(str, g.get('pages') or []))}" if g["kind"] == "retrieval"
                else g.get("expected"),
                "Paper": (g.get("title") or g.get("file"))[:60],
                "Diperiksa": bool(g.get("reviewed")),
                "Hapus": False,
            } for g in gold]
            edited = st.data_editor(
                table, key="ev_editor", width="stretch", hide_index=True,
                disabled=["id", "Jenis", "Paper", "Jawaban benar"],
                column_config={"Soal": st.column_config.TextColumn(width="large")},
            )
            with st.expander("Kutipan sumber tiap soal"):
                for g in gold[:60]:
                    st.markdown(f"**{g['id']}** (hal. {g.get('page')}): {_e((g.get('passage') or '')[:500])}")
            if st.button("Simpan perubahan", key="ev_save"):
                by_id = {g["id"]: g for g in gold}
                out = []
                for row in edited:
                    g = by_id[row["id"]]
                    if row["Hapus"]:
                        continue
                    g["reviewed"] = bool(row["Diperiksa"])
                    g["question" if g["kind"] == "retrieval" else "claim"] = row["Soal"]
                    out.append(g)
                _evaluate.save_gold(out)
                st.success("Tersimpan.")
                st.rerun()

            r1, r2, r3 = st.columns([1, 1, 2])
            only_rev = r1.checkbox("Hanya soal yang diperiksa", value=reviewed > 0, key="ev_rev")
            k = r2.number_input("k (halaman teratas)", min_value=1, max_value=10, value=3, key="ev_k")
            r3.write("")
            if r3.button("Jalankan uji", type="primary", key="ev_run"):
                with st.spinner("Menjalankan uji, sekitar 15-20 detik per soal..."):
                    st.session_state["ev_last"] = _evaluate.run(k=int(k), reviewed_only=only_rev, model=config.LLM_MODEL)
        last = st.session_state.get("ev_last")
        if last:
            m1, m2, m3, m4 = st.columns(4)
            pct = lambda x: "-" if x is None else f"{x * 100:.0f}%"
            m1.metric(f"Halaman benar di {last['settings']['k']} teratas", pct(last["retrieval"]["recall_at_k"]))
            m2.metric("Akurasi cek klaim", pct(last["claims"]["accuracy"]))
            m3.metric("Klaim salah yang tertangkap", pct(last["claims"]["false_caught"]))
            m4.metric("Klaim benar yang lolos", pct(last["claims"]["true_passed"]))
            wrong = [r for r in last["claims"]["rows"] if not r["ok"]]
            if wrong:
                with st.expander(f"{len(wrong)} klaim dinilai keliru oleh pemeriksa"):
                    render_table([{"id": r["id"], "Seharusnya": r["expected"], "Hasil": r["got"], "Alasan": r["reason"]} for r in wrong])
        hist = _evaluate.history()
        if hist:
            st.markdown("**Riwayat uji**")
            pct = lambda x: "" if x is None else f"{x * 100:.0f}%"
            render_table([{"Waktu": h["time"].replace("T", " ")[:16], "k": str(h["k"]), "Halaman benar": pct(h["recall_at_k"]),
                           "MRR": "" if h["mrr"] is None else f"{h['mrr']:.2f}", "Akurasi klaim": pct(h["claim_accuracy"]),
                           "Salah tertangkap": pct(h["false_caught"]), "Benar lolos": pct(h["true_passed"]),
                           "Embedding": h.get("embed_model") or "-"} for h in hist])

    with tab_log:
        rows = _audit.read()
        st.caption("Setiap langkah AI dicatat: waktu, model, versi prompt, dan masukannya. Lampirkan log ini di bagian metode.")
        st.markdown("**Teks untuk bagian metode**")
        st.code(_audit.methods_text(rows), language="text", wrap_lines=True)
        if rows:
            l1, l2 = st.columns(2)
            l1.download_button("Unduh log (CSV)", _audit.to_csv(rows), "cosmolab_audit.csv", "text/csv", width="stretch")
            l2.download_button("Unduh log (JSONL)", "\n".join(json.dumps(r, ensure_ascii=False) for r in reversed(rows)),
                               "cosmolab_audit.jsonl", "application/json", width="stretch")
            render_table([{
                "Waktu": r.get("time", "").replace("T", " "),
                "Langkah": _audit.EVENT_LABELS.get(r.get("event"), r.get("event")),
                "Model": r.get("model") or "",
                "Paper / pertanyaan": r.get("question") or r.get("file") or "",
                "Ringkasan": json.dumps(r.get("summary"), ensure_ascii=False) if r.get("summary") else (r.get("status") or ""),
                "Oleh": r.get("user") or "",
            } for r in rows[:300]])
        else:
            st.info("Belum ada aktivitas yang tercatat.")


def render(ctx: AppContext):
    """Pusat Akurasi."""
    render_accuracy_page(ctx)
