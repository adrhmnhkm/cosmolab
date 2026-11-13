"""Dashboard page: Tulis artikel, for the firm's own content (blog, webinar, class material).

Not for client work: writing a student's text for them is what the firm does not do,
so this page has no client delivery and is open to the owner and admins only.
"""

import streamlit as st
from cosmolab import config
from cosmolab import home as _home
from cosmolab import writer as _writer
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def render(ctx: AppContext):
    """Studio Artikel Siap Baca."""
    all_papers = ctx.all_papers
    selected_faculty_id = ctx.selected_faculty_id
    render_hero(
        title="Tulis Artikel",
        subtitle="AI menulis draf artikel dari paper di koleksi untuk konten firma sendiri: blog, materi webinar, "
                 "atau bahan kelas.",
        icon="",
    )
    if not _home.is_owner():
        st.info("Halaman ini khusus admin. Tulis artikel hanya dipakai untuk konten firma, bukan untuk pekerjaan klien.")
        return
    st.warning("Hanya untuk konten firma. Jangan dipakai untuk menulis skripsi, tesis, disertasi, atau artikel atas nama "
               "mahasiswa. Untuk klien, pakai Tinjauan pustaka, Review draf, dan Latihan sidang.")

    tab_art1, tab_art2 = st.tabs(["Tulis baru", "Artikel tersimpan"])

    with tab_art1:
        topic_presets = {
            "agama_filsafat": "Moderasi beragama di ruang digital: apa kata penelitian terbaru",
            "hukum": "Perlindungan data pribadi setelah UU PDP: yang perlu diketahui peneliti",
            "ekonomi": "Lima temuan riset tentang literasi keuangan generasi muda",
            "pendidikan": "Pembelajaran berbasis proyek: apa kata bukti penelitian",
            "psikologi_sosial": "Kesehatan mental mahasiswa tingkat akhir: ringkasan riset untuk webinar",
            "sains_teknologi": "Kecerdasan buatan di pendidikan tinggi: peluang dan risikonya",
            "kesehatan": "Pencegahan stunting: intervensi yang terbukti berhasil",
            "bahasa_sastra": "Alih kode di media sosial: pengantar untuk kelas metodologi",
        }
        default_preset = topic_presets.get(selected_faculty_id, "")

        with st.container(border=True):
            col_a1, col_a2 = st.columns([3, 2])
            article_topic = col_a1.text_input("Topik atau judul artikel", value=default_preset, placeholder="contoh: Dampak kebijakan zakat produktif terhadap UMKM")
            
            style_keys = list(_writer.ARTICLE_STYLES.keys())
            article_style = col_a2.selectbox(
                "Jenis tulisan",
                style_keys,
                format_func=lambda x: _writer.ARTICLE_STYLES[x]["name"]
            )
            st.caption(f"*{_writer.ARTICLE_STYLES[article_style]['desc']}*")

            col_src1, col_src2 = st.columns(2)
            with col_src1:
                ref_mode = st.radio("Paper rujukan", ["Otomatis Cari dari Second Brain", "Pilih Paper Tertentu dari Database"],
                                    format_func=lambda x: "Pilih otomatis" if x.startswith("Otomatis") else "Saya pilih sendiri", horizontal=True)
            
            specific_papers = None
            if ref_mode == "Pilih Paper Tertentu dari Database":
                with col_src2:
                    paper_options = [p["file"] for p in all_papers if p.get("thesis")]
                    _paper_titles = {p["file"]: p.get("title") or p["file"] for p in all_papers}
                    specific_papers = st.multiselect("Paper yang dipakai", paper_options, default=paper_options[:3] if len(paper_options) >= 3 else paper_options,
                                                     format_func=lambda f: _paper_titles.get(f, f))

            col_cp1, col_cp2 = st.columns([3, 2])
            custom_prompt = col_cp1.text_input("Instruksi tambahan (opsional)", placeholder="contoh: Jelaskan istilah teknis saat pertama kali muncul...")
            model_choice = col_cp2.selectbox(
                "Kecepatan",
                ["gemini-3-8-flash", "deepseek-v4-pro"],
                format_func=lambda x: "Cepat (±15 detik)" if "gemini" in x else "Mendalam (±90 detik)"
            )

            write_btn = st.button("Tulis artikel", type="primary", use_container_width=True)

        if write_btn:
            if not article_topic.strip():
                st.error("Silakan masukkan topik artikel terlebih dahulu.")
            else:
                with st.spinner("Menulis artikel dari paper di koleksi..."):
                    art_result = _writer.generate_article(
                        topic=article_topic,
                        style=article_style,
                        custom_instructions=custom_prompt,
                        faculty_id=selected_faculty_id,
                        paper_files=specific_papers,
                        model=model_choice
                    )
                    st.session_state["current_article"] = art_result
                    saved_files = _writer.save_article(art_result)
                    st.session_state["saved_article_paths"] = saved_files

        if "current_article" in st.session_state:
            curr = st.session_state["current_article"]
            saved = st.session_state.get("saved_article_paths", {})
            html_content = _writer.format_article_html(curr)

            # Action Toolbar inside a border container
            with st.container(border=True):
                st.success(f"Draf selesai: sekitar {curr.get('reading_time_min', 5)} menit baca. "
                           "Periksa isi dan rujukannya sebelum diterbitkan.")
                col_tb3, col_tb4 = st.columns(2)
                
                with col_tb3:
                    st.download_button(
                        "Unduh draf (.md)",
                        data=curr["content_md"],
                        file_name=f"{curr.get('title', 'Artikel')[:40]}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                with col_tb4:
                    st.download_button(
                        "Unduh draf (.html)",
                        data=html_content,
                        file_name=f"{curr.get('title', 'Artikel')[:40]}.html",
                        mime="text/html",
                        use_container_width=True
                    )

            if saved.get("md_path"):
                st.caption(f"Tersimpan sebagai `{saved['md_path'].name}`")

            # Elegant Reader View
            st.markdown("#### Pratinjau")
            if hasattr(st, "iframe"):
                st.iframe(html_content, height=650)
            else:
                st.components.v1.html(html_content, height=650, scrolling=True)

            if curr.get("referenced_papers"):
                with st.expander("Paper yang dipakai"):
                    for rp in curr["referenced_papers"]:
                        st.markdown(f"- **[{rp.get('year', 'n.d.')}] {rp.get('title')}** | {rp.get('supports_or_critiques')}")

    with tab_art2:
        articles_dir = config.ROOT / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)
        md_articles = sorted(list(articles_dir.glob("*.md")), reverse=True)

        if not md_articles:
            st.info("Belum ada artikel. Tulis artikel baru di tab sebelah.")
        else:
            selected_art_file = st.selectbox("Pilih artikel", [a.name for a in md_articles])
            art_path = articles_dir / selected_art_file
            art_text = art_path.read_text(encoding="utf-8")
            
            html_partner = articles_dir / f"{art_path.stem}.html"
            html_partner_data = html_partner.read_text(encoding="utf-8") if html_partner.exists() else _writer.format_article_html({"title": art_path.stem, "content_md": art_text})

            col_ar1, col_ar2 = st.columns(2)
            with col_ar1:
                st.download_button("Unduh .md", data=art_text, file_name=selected_art_file, mime="text/markdown",
                                   use_container_width=True, on_click="ignore")
            with col_ar2:
                st.download_button("Unduh .html", data=html_partner_data, file_name=f"{art_path.stem}.html",
                                   mime="text/html", use_container_width=True, on_click="ignore")

            st.markdown("#### Pratinjau")
            if hasattr(st, "iframe"):
                st.iframe(html_partner_data, height=650)
            else:
                st.markdown(art_text)
