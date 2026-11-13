"""Dashboard page: Cari & tambah paper (menu key "Panen Paper Ilmiah")."""

import html
import json
from datetime import datetime
import streamlit as st
from cosmolab import config
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab import harvest as _harvest
from cosmolab import extract as _extract
from cosmolab import analyze as _analyze
from cosmolab import snowball as _snowball
from cosmolab.ui.components import _e
from cosmolab.ui.components import render_hero
from cosmolab.ui.components import render_table
from cosmolab.ui.context import AppContext
from cosmolab import sinta as _sinta


def _sinta_changed():
    st.session_state.pop("_sinta_ranks", None)


def render_sinta_tab():
    """Shared SINTA journal list: import, add, and look up journals of papers."""
    st.caption(
        "SINTA tidak punya API publik, jadi tim menyimpan daftar peringkat jurnal sendiri. Paper diberi label SINTA "
        "kalau ISSN jurnalnya ada di daftar ini. Paper tanpa label belum tentu tidak terakreditasi: jurnalnya saja "
        "yang belum ada di daftar. Peringkat berubah saat akreditasi ulang, jadi cek ulang di "
        "[sinta.kemdiktisaintek.go.id](https://sinta.kemdiktisaintek.go.id/journals) sebelum dikutip ke klien."
    )
    entries = _sinta.load()

    col_a, col_b = st.columns(2)
    with col_a.container(border=True):
        st.markdown("##### Tambah satu jurnal")
        with st.form("sinta_add_form", clear_on_submit=True):
            name = st.text_input("Nama jurnal")
            issn = st.text_input("ISSN (cetak dan/atau online, pisahkan dengan koma)", placeholder="2087-1236, 2502-3721")
            rank = st.selectbox("Peringkat", _sinta.RANKS, format_func=lambda r: f"SINTA {r}")
            if st.form_submit_button("Simpan", use_container_width=True):
                try:
                    res = _sinta.add(name, issn, rank)
                    _sinta_changed()
                    st.success(f"SINTA {res['rank']} {'ditambahkan' if res['status'] == 'added' else 'diperbarui'}: "
                               f"{', '.join(res['issns'])}")
                    entries = _sinta.load()
                except ValueError as e:
                    st.error(str(e))

    with col_b.container(border=True):
        st.markdown("##### Impor CSV")
        st.caption("Kolom wajib: ISSN (boleh `issn` dan `eissn`) dan peringkat (`peringkat`, `sinta`, atau `akreditasi`). "
                   "Kolom nama jurnal dan tanggal cek opsional.")
        up = st.file_uploader("File CSV", type=["csv"], key="sinta_csv")
        if up is not None and st.button("Impor", key="sinta_import_btn", use_container_width=True):
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sinta.csv"
                path.write_bytes(up.getvalue())
                try:
                    res = _sinta.import_csv(path)
                    _sinta_changed()
                    st.success(f"{res['added']} jurnal baru, {res['updated']} diperbarui.")
                    if res["skipped"]:
                        st.warning(f"Baris dilewati karena ISSN atau peringkat tidak valid: {', '.join(map(str, res['skipped']))}")
                    entries = _sinta.load()
                except (ValueError, UnicodeDecodeError) as e:
                    st.error(f"Impor gagal: {e}")

    with st.container(border=True):
        st.markdown("##### Cocokkan paper proyek ini")
        ranked = _sinta.ranks_by_file()
        st.caption(f"{len(ranked)} paper di proyek ini berlabel SINTA. Paper lama belum menyimpan ISSN jurnalnya; "
                   "tombol ini mencarinya lewat DOI di OpenAlex (sekali per paper).")
        if st.button("Cari jurnal paper lewat DOI", key="sinta_fill_btn", use_container_width=True):
            with st.spinner("Mencari jurnal dan ISSN..."):
                res = _sinta.fill_journals()
            _sinta_changed()
            st.success(f"ISSN dicari untuk {res['checked']} paper, ketemu {res['found']}. "
                       f"Sekarang {len(_sinta.ranks_by_file())} paper berlabel SINTA.")

    st.markdown(f"##### Daftar jurnal ({len(entries)})")
    if entries:
        render_table([{"Peringkat": f"SINTA {e['rank']}", "Nama jurnal": e.get("name", ""),
                       "ISSN": ", ".join(e["issns"]), "Dicek": e.get("checked", "")} for e in entries])
    else:
        st.info("Daftar masih kosong. Tambah jurnal yang sering dipakai klien, atau impor CSV.")


def render_snowball_tab(ctx: AppContext):
    """Citation snowballing: papers cited by, or citing, the collection."""
    faculty_labels = ctx.faculty_labels
    faculty_list = ctx.faculty_list
    papers = db.get_all_papers_with_analyses()
    with st.container(border=True):
        st.caption(
            "Cari paper penting lewat jejak sitasi koleksi: rujukan yang dikutip paper koleksi (biasanya karya induk), "
            "dan paper baru yang mengutip koleksi. Data dari Semantic Scholar, cadangan OpenAlex."
        )
        if not papers:
            st.info("Koleksi masih kosong. Cari atau unggah paper dulu.")
            return
        labels = {p["file"]: f"{p.get('title') or p['file']} ({p.get('year') or 'n.d.'})" for p in papers}
        col_s1, col_s2 = st.columns([3, 2])
        with col_s1:
            picked = st.multiselect("Paper koleksi yang ditelusuri", list(labels), format_func=lambda f: labels[f],
                                    placeholder="Kosong = semua paper koleksi", key="sb_seeds")
        with col_s2:
            arah = st.radio("Arah", ["Keduanya", "Rujukan paper koleksi", "Paper yang mengutip koleksi"],
                            key="sb_arah")
        seeds = [p for p in papers if p["file"] in picked] if picked else papers
        directions = {"Keduanya": (_snowball.BACKWARD, _snowball.FORWARD),
                      "Rujukan paper koleksi": (_snowball.BACKWARD,),
                      "Paper yang mengutip koleksi": (_snowball.FORWARD,)}[arah]
        n_steps = len(seeds) * len(directions)
        secs = round(n_steps * 1.6)
        eta = f"{max(secs, 5)} detik" if secs < 60 else f"{round(secs / 60)} menit"
        st.caption(f"{len(seeds)} paper, {n_steps} penelusuran, sekitar {eta}.")
        if st.button("Telusuri sitasi", type="primary", width="stretch", key="btn_snowball"):
            bar = st.progress(0.0, text="Mulai menelusuri...")

            def _prog(i, n, seed, direction, count, src):
                bar.progress(i / n, text=f"{i}/{n} · {_snowball.DIRECTION_LABELS[direction]} · "
                                         f"{(seed.get('title') or '')[:50]} · {count} paper")

            res = _snowball.snowball(seeds, papers, directions=directions, progress=_prog)
            bar.empty()
            st.session_state["sb_result"] = res

    res = st.session_state.get("sb_result")
    if not res:
        return
    cands = res["candidates"]
    if not cands:
        st.info("Tidak ada kandidat baru. Semua paper yang terhubung sudah ada di koleksi.")
        return

    import pandas as pd

    st.markdown(f"##### {len(cands)} kandidat baru")
    st.caption("Diurutkan dari yang terhubung ke paling banyak paper koleksi, lalu jumlah sitasinya. "
               "Centang paper yang mau diunduh.")
    rows = [{
        "Pilih": False,
        "Judul": c["title"],
        "Tahun": c["year"],
        "Terhubung ke": c["link_count"],
        "Sitasi": c["citations"],
        "Arah": ", ".join(_snowball.DIRECTION_LABELS[d] for d in c["directions"]),
        "Versi terbuka": "PDF tersedia" if c["pdf_url"] else ("Cek lewat DOI" if c["doi"] else "Tidak ada"),
        "DOI": c["doi"],
    } for c in cands[:200]]
    edited = st.data_editor(
        pd.DataFrame(rows), hide_index=True, width="stretch", height=440, key="sb_table",
        disabled=["Judul", "Tahun", "Terhubung ke", "Sitasi", "Arah", "Versi terbuka", "DOI"],
        column_config={
            "Pilih": st.column_config.CheckboxColumn(width="small"),
            "Judul": st.column_config.TextColumn(width="large"),
            "Terhubung ke": st.column_config.NumberColumn(help="Jumlah paper koleksi yang terhubung", format="%d paper"),
        },
    )
    chosen = [cands[i] for i in edited.index[edited["Pilih"]].tolist()]
    col_u1, col_u2, col_u3 = st.columns([3, 2, 3])
    with col_u1:
        sb_fac = st.selectbox("Simpan ke bidang", ["auto"] + [f.id for f in faculty_list],
                              format_func=lambda x: "Deteksi otomatis" if x == "auto" else faculty_labels.get(x, x),
                              key="sb_fac")
    with col_u2:
        sb_an = st.checkbox("Langsung analisis", value=False, key="sb_auto_an")
    with col_u3:
        go = st.button(f"Unduh terpilih ({len(chosen)})", type="primary", disabled=not chosen,
                       width="stretch", key="btn_sb_import")
    if go:
        done, failed = [], []
        with st.spinner("Mengunduh paper terpilih..."):
            for c in chosen:
                r = _snowball.import_candidate(c, faculty=None if sb_fac == "auto" else sb_fac)
                (done if r.get("ok") else failed).append((c, r))
        if sb_an and done:
            with st.spinner(f"Menganalisis {len(done)} paper..."):
                _analyze.analyze_all(model=config.LLM_MODEL, lang="id", force=True, files=[r["file"] for _, r in done])
        db.sync_all()
        if done:
            st.success(f"{len(done)} paper masuk koleksi: " + "; ".join(r["title"][:60] for _, r in done))
        for c, r in failed:
            st.warning(f"Gagal: {c['title'][:70]}. {r.get('error', '')}")
        st.session_state["sb_result"] = None


def render(ctx: AppContext):
    """Panen Paper Ilmiah."""
    all_papers = ctx.all_papers
    faculty_labels = ctx.faculty_labels
    faculty_list = ctx.faculty_list
    selected_faculty_id = ctx.selected_faculty_id
    render_hero(
        title="Cari & Tambah Paper",
        subtitle="Cari paper di 6 basis data akademik. CosmoLab hanya mengunduh naskah yang legal dan terbuka (open access).",
        icon="",
    )

    # Visual Ribbon of Connected Sources
    st.markdown("""
    <div style="font-size:0.8rem; color:#64748B; margin-bottom:10px;">
        Sumber: arXiv · DOAJ · Semantic Scholar · Crossref · OpenAlex · CORE
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Sumber tambahan: CORE (opsional)", expanded=False):
        core_key = getattr(config, "CORE_API_KEY", "")
        if core_key:
            st.success(f"**CORE API Terhubung.** Kunci API terdeteksi di lingkungan sistem.")
        else:
            st.info(
                "**CORE API Key (Opsional):** CORE mengagregasi naskah tesis dan preprint dari ribuan repositori universitas dunia. "
                "Untuk mengaktifkannya, daftarkan email Anda di [core.ac.uk/services/api](https://core.ac.uk/services/api) (gratis), lalu tambahkan `CORE_API_KEY=...` ke file `.env`."
            )

    badge_config = {
        "search_start": ("#3B82F6", "MENCARI"),
        "faculty_start": ("#6366F1", "BIDANG"),
        "query_step": ("#3B82F6", "KATA KUNCI"),
        "paper_found": ("#06B6D4", "DITEMUKAN"),
        "download_start": ("#F59E0B", "MENGUNDUH"),
        "download_ok": ("#10B981", "TERUNDUH"),
        "download_retry": ("#F97316", "COBA LAGI"),
        "download_fail": ("#EF4444", "GAGAL"),
        "skip": ("#94A3B8", "DILEWATI"),
        "duplicate": ("#94A3B8", "SUDAH ADA"),
        "no_pdf": ("#F43F5E", "TIDAK ADA PDF TERBUKA"),
        "extract_start": ("#0EA5E9", "MEMBACA TEKS"),
        "extract_ok": ("#10B981", "TEKS SIAP"),
        "extract_skip": ("#94A3B8", "TEKS SUDAH ADA"),
        "extract_fail": ("#EF4444", "TEKS GAGAL"),
        "analyze_start": ("#8B5CF6", "MENGANALISIS"),
        "analyze_ok": ("#10B981", "TERANALISIS"),
        "analyze_skip": ("#94A3B8", "SUDAH DIANALISIS"),
        "analyze_fail": ("#EF4444", "AI GAGAL"),
    }

    def run_live_harvest_process(harvest_callable, auto_analyze: bool = True):
        console_box = st.container(border=True)
        with console_box:
            st.markdown("#### Proses berjalan")
            status_box = st.empty()
            progress_bar = st.progress(0.05, text="Menginisialisasi koneksi repositori global...")
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            m_found = col_m1.empty()
            m_downloaded = col_m2.empty()
            m_extracted = col_m3.empty()
            m_analyzed = col_m4.empty()

            m_found.metric("Ditemukan", 0, border=True)
            m_downloaded.metric("Diunduh", 0, border=True)
            m_extracted.metric("Teks Siap", 0, border=True)
            m_analyzed.metric("Dianalisis AI", 0, border=True)

            st.markdown("<div style='font-size:0.82rem; font-weight:700; color:#64748B; margin-top:8px; margin-bottom:4px;'>LIVE HARVEST ACTIVITY STREAM:</div>", unsafe_allow_html=True)
            terminal_box = st.empty()

        logs = []
        counters = {"found": 0, "downloaded": 0, "extracted": 0, "analyzed": 0}
        new_papers = []

        def _ui_cb(event_type: str, message: str, data: dict = None):
            now_t = datetime.now().strftime("%H:%M:%S")
            color, b_label = badge_config.get(event_type, ("#64748B", "INFO"))

            # Update metrics
            if event_type == "paper_found":
                counters["found"] += 1
                m_found.metric("Ditemukan", counters["found"], border=True)
                progress_bar.progress(min(0.35, 0.05 + counters["found"] * 0.02), text=f"Menemukan literatur ({counters['found']} naskah)...")
            elif event_type == "download_ok":
                counters["downloaded"] += 1
                m_downloaded.metric("Diunduh", counters["downloaded"], border=True)
                progress_bar.progress(min(0.65, 0.35 + counters["downloaded"] * 0.05), text=f"Mengunduh PDF legal ({counters['downloaded']} file siap)...")
                if data and data.get("title"):
                    new_papers.append(data)
            elif event_type == "extract_ok":
                counters["extracted"] += 1
                m_extracted.metric("Teks Siap", counters["extracted"], border=True)
                progress_bar.progress(min(0.80, 0.65 + counters["extracted"] * 0.03), text=f"Mengekstrak teks naskah ({counters['extracted']} selesai)...")
            elif event_type == "analyze_ok":
                counters["analyzed"] += 1
                m_analyzed.metric("Dianalisis AI", counters["analyzed"], border=True)
                progress_bar.progress(min(0.95, 0.80 + counters["analyzed"] * 0.03), text=f"Membedah naskah utuh ({counters['analyzed']} selesai)...")

            safe_msg = html.escape(message)
            line_html = (
                f"<div style='font-family:\"JetBrains Mono\", monospace; font-size:0.78rem; line-height:1.45; margin-bottom:3px;'>"
                f"<span style='color:#64748B;'>[{now_t}]</span> "
                f"<span style='background:{color}22; color:{color}; border:1px solid {color}44; padding:1px 5px; border-radius:3px; font-weight:700;'>{b_label}</span> "
                f"<span style='color:#CBD5E1;'>{safe_msg}</span>"
                f"</div>"
            )
            logs.append(line_html)
            
            terminal_view = f"""
            <div style='background:#0B0F19; border-radius:6px; padding:10px 12px; height:240px; overflow-y:auto; border:1px solid #1E293B;'>
                {''.join(logs[-25:])}
            </div>
            """
            terminal_box.markdown(terminal_view, unsafe_allow_html=True)

        try:
            status_box.info("**Sedang menjalankan pencarian & pengunduhan naskah...**")
            harvest_stats = harvest_callable(_ui_cb)

            target_files = [p['file'] for p in new_papers if p.get('file')]

            # Step 2: Extraction
            status_box.info("**Mengekstrak teks lengkap dari berkas PDF baru...**")
            try:
                ext_stats = _extract.extract_all(progress_cb=_ui_cb, files=target_files if target_files else None)
            except TypeError:
                ext_stats = _extract.extract_all()

            # Step 3: Analysis
            if auto_analyze and counters["downloaded"] > 0:
                status_box.info(f"**AI ({config.LLM_MODEL}) sedang membedah naskah utuh (Metodologi, Temuan Pembahasan & Kesimpulan)...**")
                try:
                    an_stats = _analyze.analyze_all(model=config.LLM_MODEL, concurrency=4, lang="id", progress_cb=_ui_cb, files=target_files if target_files else None)
                except TypeError:
                    an_stats = _analyze.analyze_all(model=config.LLM_MODEL, concurrency=4, lang="id")

            # Sync DB
            db.sync_all()

            progress_bar.progress(1.0, text="Seluruh tahapan panen, ekstraksi, dan analisis berhasil diselesaikan!")
            status_box.success(
                f"**Panen Berhasil Diselesaikan!** Ditemukan: {counters['found']} | Berhasil Diunduh: **{counters['downloaded']} paper** | "
                f"Teks Siap: **{counters['extracted']}** | Dianalisis AI: **{counters['analyzed']}**."
            )

            if new_papers:
                with st.expander(f"Naskah yang Baru Saja Berhasil Diunduh ({len(new_papers)} Paper)", expanded=True):
                    for p_idx, np in enumerate(new_papers[:8], 1):
                        st.markdown(f"**{p_idx}. {_e(np.get('title'))}** &nbsp; <span style='font-size:0.75rem; color:#64748B;'>`{_e(np.get('file', ''))}`</span>", unsafe_allow_html=True)

        except Exception as e:
            status_box.error(f"Terjadi kesalahan saat proses panen: {e}")

    def run_live_analyze_process(target_files: list[str], model: str, lang: str, workers: int):
        console_box = st.container(border=True)
        with console_box:
            st.markdown("#### Proses analisis berjalan")
            status_box = st.empty()
            progress_bar = st.progress(0.05, text="Memulai pembedahan naskah...")
            col_m1, col_m2 = st.columns(2)
            m_extracted = col_m1.empty()
            m_analyzed = col_m2.empty()
            m_extracted.metric("Teks Disiapkan", 0, border=True)
            m_analyzed.metric("Dianalisis AI", 0, border=True)
            terminal_box = st.empty()

        logs = []
        counters = {"extracted": 0, "analyzed": 0}
        total = len(target_files)

        def _an_cb(event_type: str, message: str, data: dict = None):
            now_t = datetime.now().strftime("%H:%M:%S")
            color, b_label = badge_config.get(event_type, ("#8B5CF6", "AI"))
            if event_type == "extract_ok":
                counters["extracted"] += 1
                m_extracted.metric("Teks Disiapkan", counters["extracted"], border=True)
            elif event_type == "analyze_ok":
                counters["analyzed"] += 1
                m_analyzed.metric("Dianalisis AI", counters["analyzed"], border=True)
                progress_bar.progress(min(1.0, counters["analyzed"] / max(1, total)), text=f"Pembedahan AI: {counters['analyzed']}/{total} paper...")

            safe_msg = html.escape(message)
            line_html = (
                f"<div style='font-family:\"JetBrains Mono\", monospace; font-size:0.78rem; line-height:1.45; margin-bottom:3px;'>"
                f"<span style='color:#64748B;'>[{now_t}]</span> "
                f"<span style='background:{color}22; color:{color}; border:1px solid {color}44; padding:1px 5px; border-radius:3px; font-weight:700;'>{b_label}</span> "
                f"<span style='color:#CBD5E1;'>{safe_msg}</span>"
                f"</div>"
            )
            logs.append(line_html)
            terminal_box.markdown(f"<div style='background:#0B0F19; border-radius:6px; padding:10px 12px; height:220px; overflow-y:auto; border:1px solid #1E293B;'>{''.join(logs[-25:])}</div>", unsafe_allow_html=True)

        try:
            status_box.info(f"Menyiapkan teks naskah untuk {total} berkas...")
            _extract.extract_all(progress_cb=_an_cb, files=target_files)
            status_box.info(f"Membedah {total} naskah dengan AI ({model})...")
            _analyze.analyze_all(model=model, concurrency=workers, lang=lang, force=True, progress_cb=_an_cb, files=target_files)
            db.sync_all()
            progress_bar.progress(1.0, text="Seluruh naskah berhasil dibedah!")
            status_box.success(f"Pembedahan selesai! {counters['analyzed']} paper berhasil dianalisis.")
        except Exception as e:
            status_box.error(f"Terjadi kesalahan: {e}")

    tab_h2, tab_h6, tab_h1, tab_h4, tab_h8, tab_h5, tab_h3, tab_h7 = st.tabs([
        "Cari topik",
        "Telusuri sitasi",
        "Per bidang ilmu",
        "Unggah PDF / DOI",
        "Ringkas dari DOI",
        "Analisis paper",
        "Kelola bidang ilmu",
        "Peringkat SINTA",
    ])

    with tab_h8:
        from cosmolab.ui.pages import doi as _doi_page

        _doi_page.render_body()

    with tab_h7:
        render_sinta_tab()

    with tab_h1:
        with st.container(border=True):
            col_cat, col_fac = st.columns([1, 2])
            cat_filter = col_cat.selectbox(
                "Kategori",
                ["Semua Kategori", "Bidang umum", "Kustom Peneliti"],
                key="h_cat_filter"
            )

            filtered_faculties = faculty_list
            if cat_filter != "Semua Kategori":
                filtered_faculties = [f for f in faculty_list if getattr(f, "category", "") == cat_filter]
                if not filtered_faculties:
                    filtered_faculties = faculty_list

            target_fac_id = col_fac.selectbox(
                "Bidang ilmu",
                [f.id for f in filtered_faculties],
                format_func=lambda x: faculty_labels.get(x, x),
                key="h_fac_select"
            )
            target_fac_obj = _faculties.get_faculty(target_fac_id)
            
            st.markdown(
                f"### {_e(target_fac_obj.name)} "
                f"<span style='background:#EEF2FF; color:#4338CA; border:1px solid #C7D2FE; padding:3px 10px; border-radius:9999px; font-size:0.8rem; font-weight:600;'>{_e(getattr(target_fac_obj, 'category', 'Umum'))}</span>",
                unsafe_allow_html=True
            )
            st.caption(target_fac_obj.full_desc or target_fac_obj.short_desc)
            
            st.markdown(f"**Kata kunci yang dicari:** {', '.join([f'`{q}`' for q in target_fac_obj.default_queries])}")
            
            col_hp1, col_hp2 = st.columns([1, 1])
            h_max_per_q = int(col_hp1.number_input("Paper per kata kunci", min_value=2, max_value=25, value=6, key="hp_max"))
            col_hp2.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
            auto_an_fac = col_hp2.checkbox("Langsung analisis setelah diunduh", value=True, key="hp_auto")

            harvest_fac_btn = st.button("Cari & unduh", type="primary", key="btn_harvest_fac", use_container_width=True)

        if harvest_fac_btn:
            run_live_harvest_process(
                lambda cb: _harvest.harvest_faculty(target_fac_id, max_results_per_query=h_max_per_q, workers=4, delay=0.5, progress_cb=cb),
                auto_analyze=auto_an_fac
            )

    with tab_h2:
        with st.container(border=True):
            st.caption("Kata kunci bahasa Inggris memberi hasil paling banyak.")
            
            col_c1, col_c2 = st.columns([3, 1])
            custom_q = col_c1.text_input("Topik atau kata kunci", placeholder="contoh: green accounting, blended learning, islamic microfinance")
            custom_max = int(col_c2.number_input("Jumlah paper", min_value=3, max_value=60, value=10, key="c_max"))
            only_id = st.checkbox(
                "Khusus jurnal Indonesia", key="c_indonesia",
                help="Cari hanya di jurnal Indonesia atau artikel berbahasa Indonesia (jurnal Garuda/SINTA yang punya DOI), "
                     "lewat OpenAlex. Pakai kata kunci bahasa Indonesia.",
            )

            # Options include all registered faculties + option to create ad-hoc
            fac_dropdown_keys = [f.id for f in faculty_list] + ["_new_faculty_on_the_fly_"]
            def _format_fac_choice(k):
                if k == "_new_faculty_on_the_fly_":
                    return "Bidang baru..."
                return faculty_labels.get(k, k)

            col_cf1, col_cf2 = st.columns([2, 1])
            chosen_fac_key = col_cf1.selectbox("Simpan ke bidang", fac_dropdown_keys, format_func=_format_fac_choice, key="c_fac_select",
                                              index=fac_dropdown_keys.index(selected_faculty_id) if selected_faculty_id in fac_dropdown_keys else 0)
            col_cf2.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
            auto_an_cust = col_cf2.checkbox("Langsung analisis", value=True, key="c_auto")

            effective_fac_id = chosen_fac_key
            if chosen_fac_key == "_new_faculty_on_the_fly_":
                col_nf1, col_nf2 = st.columns([3, 1])
                new_fac_name = col_nf1.text_input("Nama bidang baru", placeholder="contoh: Teknik Arsitektur & Perkotaan", key="nf_name_input")
                new_fac_icon = col_nf2.text_input("Ikon", value="", key="nf_icon_input")

            harvest_cust_btn = st.button("Cari & unduh", type="primary", key="btn_harvest_cust", use_container_width=True)

        if harvest_cust_btn and not custom_q.strip():
            st.error("Isi topik atau kata kunci dulu.")
        elif harvest_cust_btn:
            if chosen_fac_key == "_new_faculty_on_the_fly_":
                if not new_fac_name.strip():
                    st.error("Isi nama bidang baru dulu.")
                    st.stop()
                # Create and register the new faculty permanently
                saved_new_fac = _faculties.save_custom_faculty(
                    name=new_fac_name.strip(),
                    icon=new_fac_icon.strip() or "",
                    default_queries=[custom_q],
                    short_desc=f"Fokus riset {new_fac_name.strip()}",
                    category="Kustom Peneliti"
                )
                effective_fac_id = saved_new_fac.id
                st.success(f"Bidang '{saved_new_fac.name}' tersimpan.")

            run_live_harvest_process(
                lambda cb: _harvest.harvest(custom_q, max_results=custom_max, workers=4, delay=0.5, faculty=effective_fac_id, progress_cb=cb,
                                            indonesia=only_id),
                auto_analyze=auto_an_cust
            )

    with tab_h3:
        with st.container(border=True):
            st.caption("Buat bidang ilmu sendiri untuk riset klien, misalnya Manajemen Rumah Sakit atau Hukum Lingkungan. Bidang ini langsung muncul di semua pilihan bidang.")

            col_cf_form1, col_cf_form2 = st.columns([3, 1])
            new_dept_name = col_cf_form1.text_input("Nama bidang ilmu", placeholder="Contoh: Manajemen Rumah Sakit & Layanan Kesehatan", key="reg_fac_name")
            new_dept_icon = col_cf_form2.text_input("Ikon", value="", key="reg_fac_icon")

            col_cf_meta1, col_cf_meta2 = st.columns(2)
            new_dept_category = col_cf_meta1.selectbox("Kategori", ["Kustom Peneliti", "Bidang umum"], key="reg_fac_cat")
            new_dept_short = col_cf_meta2.text_input("Deskripsi singkat", placeholder="Contoh: Mutu faskes, akreditasi RS, kepuasan pasien BPJS", key="reg_fac_short")

            new_dept_queries = st.text_area(
                "Kata kunci pencarian (satu per baris)",
                placeholder="hospital administration quality\nbpjs kesehatan patient satisfaction\nlean hospital management clinical governance\nelectronic medical record healthcare adoption",
                key="reg_fac_queries",
                height=110
            )

            if st.button("Simpan bidang ilmu", type="primary", key="btn_save_custom_fac", use_container_width=True):
                if not new_dept_name.strip():
                    st.error("Nama Fakultas/Prodi wajib diisi.")
                elif not new_dept_queries.strip():
                    st.error("Harap masukkan minimal 1 kata kunci panen.")
                else:
                    raw_queries = [q.strip() for line in new_dept_queries.split("\n") for q in line.split(",") if q.strip()]
                    saved_fac = _faculties.save_custom_faculty(
                        name=new_dept_name.strip(),
                        icon=new_dept_icon.strip() or "",
                        default_queries=raw_queries,
                        short_desc=new_dept_short.strip(),
                        category=new_dept_category,
                    )
                    st.success(f"Berhasil mendaftarkan fakultas baru: **{saved_fac.name}** dengan {len(raw_queries)} query terkurasi!")
                    st.rerun()

        st.markdown("#### Bidang ilmu buatan tim")
        custom_list = [f for f in faculty_list if getattr(f, "is_custom", False)]
        if not custom_list:
            st.info("Belum ada. Isi formulir di atas untuk membuat bidang ilmu baru.")
        else:
            for cfac in custom_list:
                cfac_papers = [p for p in all_papers if p.get("faculty") == cfac.id]
                with st.container(border=True):
                    col_info, col_act = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"**{cfac.name}**")
                        st.caption(cfac.short_desc or "Tidak ada deskripsi.")
                        st.markdown(f"**Query Terdaftar:** {', '.join([f'`{q}`' for q in cfac.default_queries])}")
                        st.markdown(f"<span style='font-size:0.8rem; color:#64748B;'>Paper di Database: <b>{len(cfac_papers)} paper</b></span>", unsafe_allow_html=True)

                    with col_act:
                        if st.button("Cari & unduh", key=f"btn_harvest_cf_{cfac.id}", use_container_width=True):
                            run_live_harvest_process(
                                lambda cb: _harvest.harvest_faculty(cfac.id, max_results_per_query=5, workers=4, delay=0.5, progress_cb=cb),
                                auto_analyze=True
                            )

                        if st.button("Hapus bidang", key=f"btn_del_cf_{cfac.id}", use_container_width=True):
                            _faculties.delete_custom_faculty(cfac.id)
                            st.warning(f"Bidang '{cfac.name}' dihapus.")
                            st.rerun()

    with tab_h6:
        render_snowball_tab(ctx)

    with tab_h4:
        with st.container(border=True):
            st.caption("Pakai ini untuk paper yang tidak ketemu lewat pencarian: PDF yang Anda punya, atau paper yang Anda tahu DOI-nya.")

            col_m_up, col_m_doi = st.columns(2)

            with col_m_up:
                st.markdown("#### Unggah PDF")
                uploaded_pdf = st.file_uploader("File PDF", type=["pdf"], key="manual_pdf_upload")
                manual_title = st.text_input("Judul (opsional)", placeholder="Jika kosong, memakai nama file", key="manual_title_input")
                manual_fac = st.selectbox("Simpan ke bidang", [f.id for f in faculty_list], format_func=lambda x: faculty_labels.get(x, x), key="manual_fac_select")
                auto_an_upload = st.checkbox("Langsung analisis", value=True, key="manual_auto_an")

                if st.button("Unggah", type="primary", key="btn_import_pdf", use_container_width=True):
                    if not uploaded_pdf:
                        st.error("Pilih file PDF dulu.")
                    else:
                        with st.spinner("Menyimpan PDF dan mengekstrak teks..."):
                            res = _harvest.import_local_pdf(
                                file_bytes=uploaded_pdf.read(),
                                filename=uploaded_pdf.name,
                                title=manual_title,
                                faculty=manual_fac
                            )
                            st.success(f"Berhasil mengimpor: {res['title']}!")

                        if auto_an_upload:
                            with st.spinner("Menganalisis paper ini..."):
                                _analyze.analyze_single_paper(res["file"], model=config.LLM_MODEL, lang="id")
                                st.success("Analisis selesai.")

                        db.sync_all()
                        st.rerun()

            with col_m_doi:
                st.markdown("#### Dari DOI")
                input_doi = st.text_input("DOI atau link DOI", placeholder="contoh: 10.1007/s11153-021-09800-4", key="manual_doi_input")
                doi_fac = st.selectbox("Simpan ke bidang", [f.id for f in faculty_list], format_func=lambda x: faculty_labels.get(x, x), key="doi_fac_select")
                auto_an_doi = st.checkbox("Langsung analisis", value=True, key="doi_auto_an")
                st.caption("Hanya berhasil kalau paper punya versi terbuka (open access).")

                if st.button("Cari & unduh", type="primary", key="btn_import_doi", use_container_width=True):
                    if not input_doi.strip():
                        st.error("Isi DOI dulu.")
                    else:
                        with st.spinner("Mencari versi terbuka paper ini..."):
                            doi_res = _harvest.import_by_doi(doi=input_doi, faculty=doi_fac)
                            if "error" in doi_res:
                                st.error(doi_res["error"])
                            else:
                                st.success(f"Berhasil mengunduh: {doi_res['title']}!")
                                if auto_an_doi:
                                    with st.spinner("Menganalisis paper ini..."):
                                        _analyze.analyze_single_paper(doi_res["file"], model=config.LLM_MODEL, lang="id")
                                        st.success("Analisis selesai.")
                                db.sync_all()
                                st.rerun()

    with tab_h5:
        st.caption("Analisis paper yang belum dianalisis, atau ulangi analisis paper tertentu.")

        unanalyzed_all = [p for p in all_papers if not p.get("thesis")]
        analyzed_all = [p for p in all_papers if p.get("thesis")]

        st.progress(len(analyzed_all) / len(all_papers) if all_papers else 0.0,
                    text=f"{len(analyzed_all)} dari {len(all_papers)} paper sudah dianalisis")

        def _raw(p):
            try:
                return json.loads(p.get("raw_json") or "{}")
            except (TypeError, ValueError):
                return {}

        incomplete_all = [p for p in analyzed_all if _analyze.needs_lit_fields(_raw(p))]

        tab_sub1, tab_sub_lit, tab_sub2 = st.tabs([
            f"Belum dianalisis ({len(unanalyzed_all)})",
            f"Perlu dilengkapi ({len(incomplete_all)})",
            "Analisis ulang"
        ])

        with tab_sub_lit:
            if not incomplete_all:
                st.success("Semua analisis sudah memuat tujuan riset, sampel, keterbatasan, dan saran riset lanjutan.")
            else:
                with st.container(border=True):
                    st.caption("Paper ini dianalisis dengan versi lama. Analisis ulang menambahkan tujuan riset, sampel dan "
                               "data, keterbatasan, dan saran riset lanjutan. Setiap paper dianalisis penuh lagi, jadi "
                               "biaya AI sama dengan analisis baru, sekitar 1 menit per paper. Koreksi peneliti pada kalimat "
                               "yang berubah ditandai usang dan tidak dipakai lagi, jadi periksa ulang paper yang pernah dikoreksi.")
                    col_l1, col_l2 = st.columns([2, 1])
                    lit_lang = col_l1.selectbox("Bahasa hasil", ["id", "en"], key="lit_lang_opt",
                                                format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English")
                    lit_workers = col_l2.slider("Paper sekaligus", min_value=1, max_value=6, value=3, key="lit_workers_opt")
                    lit_map = {p.get("file"): f"{p.get('title') or p.get('file')} ({p.get('year', 'n.d.')})"
                               for p in incomplete_all}
                    lit_chosen = st.multiselect("Pilih paper (kosongkan untuk semua)", options=list(lit_map),
                                                format_func=lambda x: lit_map.get(x, x), key="lit_chosen_targets")
                    lit_targets = lit_chosen or list(lit_map)
                    if st.button(f"Lengkapi {len(lit_targets)} paper", type="primary", key="btn_run_lit_batch",
                                 use_container_width=True):
                        run_live_analyze_process(target_files=lit_targets, model=config.LLM_MODEL, lang=lit_lang,
                                                 workers=lit_workers)
                        st.rerun()

        with tab_sub1:
            if not unanalyzed_all:
                st.success("Semua paper sudah dianalisis.")
            else:
                with st.container(border=True):
                    st.caption("AI membaca naskah utuh lalu mengekstrak tesis, metodologi, temuan, dan kutipan dengan nomor halaman. Sekitar 1 menit per paper.")

                    col_opt1, col_opt2, col_opt3 = st.columns([2, 1, 1])
                    studio_model = col_opt1.selectbox("Model AI", [config.LLM_MODEL, "gemini-3-8-flash", "gemini-2.5-flash"], index=0, key="studio_model_opt")
                    studio_workers = col_opt2.slider("Paper sekaligus", min_value=1, max_value=6, value=4, key="studio_workers_opt")
                    studio_lang = col_opt3.selectbox("Bahasa hasil", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English", key="studio_lang_opt")

                    # Multi-select options
                    unanalyzed_dict = {p.get("file"): f"{p.get('title') or p.get('file')} ({p.get('year', 'n.d.')})" for p in unanalyzed_all}
                    chosen_targets = st.multiselect(
                        "Pilih paper (kosongkan untuk semua)",
                        options=list(unanalyzed_dict.keys()),
                        format_func=lambda x: unanalyzed_dict.get(x, x),
                        key="studio_chosen_targets"
                    )

                    target_files = chosen_targets if chosen_targets else list(unanalyzed_dict.keys())
                    btn_text = f"Analisis {len(target_files)} paper terpilih" if chosen_targets else f"Analisis semua ({len(unanalyzed_all)})"

                    if st.button(btn_text, type="primary", key="btn_run_studio_batch", use_container_width=True):
                        run_live_analyze_process(
                            target_files=target_files,
                            model=studio_model,
                            lang=studio_lang,
                            workers=studio_workers
                        )
                        st.rerun()

                st.markdown("##### Daftar paper")
                for u_idx, up in enumerate(unanalyzed_all, 1):
                    with st.container(border=True):
                        col_ui1, col_ui2 = st.columns([3, 1])
                        u_fac = _faculties.get_faculty(up.get("faculty") or "umum")
                        u_icon = u_fac.icon if u_fac else ""
                        u_fname = u_fac.name if u_fac else (up.get("faculty") or "Umum")
                        with col_ui1:
                            st.markdown(f"**{u_idx}. {up.get('title') or up.get('file')}**")
                            st.caption(f"{u_fname} · {up.get('year', 'n.d.')}")
                        with col_ui2:
                            if st.button("Analisis", key=f"btn_single_studio_{u_idx}_{up.get('file')}", use_container_width=True):
                                with st.spinner(f"Menganalisis '{(up.get('title') or '')[:30]}...'"):
                                    try:
                                        _analyze.analyze_single_paper(up.get("file"), model=studio_model, lang=studio_lang)
                                        db.sync_all()
                                        st.success("Analisis berhasil!")
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Gagal analisis: {err}")

        with tab_sub2:
            with st.container(border=True):
                st.caption("Pilih paper untuk dianalisis ulang, misalnya kalau hasil sebelumnya kurang lengkap.")

                all_file_map = {p.get("file"): f"[{'' if p.get('thesis') else ''}] {p.get('title') or p.get('file')} ({p.get('year', 'n.d.')})" for p in all_papers}
                chosen_file = st.selectbox(
                    "Paper",
                    options=list(all_file_map.keys()),
                    format_func=lambda x: all_file_map.get(x, x),
                    key="studio_single_chosen"
                )

                if chosen_file:
                    target_rec = next((p for p in all_papers if p.get("file") == chosen_file), None)
                    if target_rec:
                        if target_rec.get("thesis"):
                            st.info(f"**Tesis saat ini:** {target_rec.get('thesis')}")
                        else:
                            st.caption("Paper ini belum dianalisis.")

                        col_re1, col_re2 = st.columns(2)
                        re_model = col_re1.selectbox("Model LLM:", [config.LLM_MODEL, "gemini-3-8-flash", "gemini-2.5-flash"], key="re_model_single")
                        re_lang = col_re2.selectbox("Bahasa Analisis:", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English", key="re_lang_single")

                        if st.button("Analisis ulang", type="primary", key="btn_exec_single_re", use_container_width=True):
                            with st.spinner(f"Menganalisis naskah '{chosen_file}' dengan {re_model}..."):
                                try:
                                    _analyze.analyze_single_paper(chosen_file, model=re_model, lang=re_lang, force=True)
                                    db.sync_all()
                                    st.success(f"Pembedahan ulang selesai untuk: {chosen_file}")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"Gagal analisis: {err}")
