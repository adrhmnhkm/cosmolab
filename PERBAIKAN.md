# Rencana perbaikan Review Draf

Disusun 13 Nov 2026 dari uji coba tesis sungguhan: 272 paragraf, 56 entri pustaka, dijalankan tanpa komentar AI. Urutan di bawah adalah urutan pengerjaan yang disarankan.

## 1. Lengkapi pembanding dari daftar pustaka (selesai)

**Masalah.** Saat ini cek kemiripan hanya membandingkan dengan dua hal: paper yang sudah ada di koleksi proyek, dan abstrak sumber yang dikutip. Di uji coba, koleksinya berisi paper kosmologi yang tidak setopik, dan 41 dari 42 abstrak berbahasa Inggris. Hasilnya 0%, padahal tidak ada pembanding yang sebanding.

**Perbaikan.** Tambah tombol **Lengkapi pembanding** di tab Cek kemiripan. Untuk setiap entri daftar pustaka, CosmoLab mencoba sumber berikut berurutan:

1. **Punya DOI:** unduh PDF open access lewat fungsi impor DOI yang sudah ada (`harvest.import_by_doi`, termasuk Unpaywall).
2. **Tanpa DOI:** cari judulnya di OpenAlex, Semantic Scholar, DOAJ, dan CORE. Pakai pencocok judul dari cek sitasi (`verify.title_similarity`). Unduh hanya kalau judulnya cocok dan PDF-nya terbuka.
3. **Ada URL di entri pustaka:** misalnya link OJS atau PDF. Unduh dari URL itu.
4. **Sisanya:** masuk **daftar permintaan ke mahasiswa**, yaitu daftar sumber yang perlu dikirim mahasiswa. Cukup halaman yang dikutip, lalu diunggah lewat Panen Paper → Unggah PDF.

Semua yang terunduh masuk ke proyek klien, lalu cek kemiripan dijalankan ulang dengan teks lengkap.

Hanya sumber legal yang dipakai: open access, repositori resmi, atau kiriman mahasiswa. Shadow library seperti Anna's Archive atau Sci-Hub tidak dipakai.

## 2. Laporan cakupan sumber (selesai)

**Masalah.** Laporan tidak menyebut sumber mana yang benar-benar ikut dibandingkan. Akibatnya, skor rendah terlihat aman.

**Perbaikan.** Tambah tabel per entri pustaka dengan status:
- **Teks lengkap**
- **Abstrak saja**
- **Tidak tersedia**, dengan jenis sumbernya: buku, jurnal tanpa DOI, situs, atau peraturan.

Ringkasannya tampil di dashboard dan di Word. Contoh: "Dibandingkan: 30 teks lengkap, 12 abstrak. Tidak bisa dibandingkan: 14 (8 buku, 4 jurnal tanpa DOI, 2 situs)."

## 3. Peringatan pembanding lemah (selesai)

**Masalah.** Kotak hijau "Tidak ada kalimat yang terlalu mirip" muncul walaupun hampir tidak ada pembanding yang sebahasa dengan draf.

**Perbaikan.**
- Deteksi bahasa draf dan bahasa setiap sumber. Cukup dengan hitungan kata umum, tanpa AI.
- Kalau sumber yang sebahasa sedikit, ganti kotak hijau dengan peringatan. Contoh: "Hanya 1 sumber berbahasa Indonesia. Skor 0% belum berarti aman. Lengkapi pembanding atau tambah paper Indonesia (Panen Paper → Khusus jurnal Indonesia), lalu jalankan ulang."
- Catatan yang sama ikut ke laporan internal.

## 4. Log proses yang informatif (selesai)

**Masalah.** Selama review hanya tampil "Membaca draf dan menyusun komentar...". Untuk tesis panjang, proses ini bisa beberapa menit tanpa kabar.

**Perbaikan.**
- `review_text` melaporkan tahap lewat `progress_cb`, dengan pola yang sama seperti Panen Paper:
  - Membaca draf: jumlah paragraf dan entri pustaka.
  - Cek pustaka ke Crossref: "12/56 entri".
  - Komentar AI: "batch 3/9".
  - Cek kemiripan: "abstrak sumber dikutip 20/47", lalu "membandingkan dengan 37 paper".
  - Menyimpan.
- Di dashboard, spinner diganti kotak proses berisi progress bar, log tahap yang selesai beserta durasinya, dan waktu berjalan. Kalau gagal, tampil di tahap mana gagalnya.
- Tahap yang sama tampil di terminal untuk `cosmolab review`.

## 5. Perkiraan durasi sebelum mulai (selesai)

Setelah draf diunggah, tampilkan jumlah paragraf, jumlah pustaka, dan perkiraan waktu. Contoh: "272 paragraf, 56 pustaka. Perkiraan 5–10 menit dengan komentar AI, 1–2 menit tanpa." Dengan ini konsultan bisa memutuskan apakah Crossref atau komentar AI dimatikan dulu.

## 6. Tampilan review tanpa komentar AI (selesai)

**Masalah.** Kalau komentar AI dimatikan, tab "Komentar per paragraf" tetap menjadi tab pertama dan berisi hal yang tidak berguna:
- petunjuk keputusan,
- progress bar "0 dari 0",
- pesan "Tidak ada komentar".

**Perbaikan.** Sembunyikan tab Komentar, dan jadikan Cek kemiripan tab pertama.

## 7. Peringatan saat memakai data utama (selesai)

**Masalah.** Review tesis di uji coba tersimpan di `data/`, bukan di proyek klien. Akibatnya pembandingnya koleksi kosmologi, dan review klien tercampur dengan data utama.

**Perbaikan.** Kalau tidak ada proyek aktif, halaman Review Draf menampilkan peringatan: "Anda memakai data utama. Buat proyek untuk klien ini supaya review dan pembandingnya terpisah."

## 8. Dashboard tidak memuat halaman versi baru (selesai)

**Masalah.** Setelah pembaruan, halaman Review Draf masih versi lama sampai dashboard dijalankan ulang. Penyebabnya: `web.py` hanya memuat ulang modul inti, tidak termasuk modul halaman di `cosmolab/ui/`.

**Perbaikan.** Tambahkan modul `cosmolab.ui` ke daftar yang dimuat ulang. Atau, minimal, tulis di PANDUAN_TIM bahwa dashboard perlu dijalankan ulang setelah pembaruan.

## 9. Optimasi Panen Paper & Pengunduhan Multi-Tier (selesai)

**Masalah.** Panen literatur sering gagal unduh (~50% gagal) dan proses pencarian membeku hingga 14 detik akibat rate-limit (HTTP 429) pada Semantic Scholar API tanpa API key. Selain itu, Unpaywall dan OpenAlex sering mengembalikan link halaman HTML (landing page) saat file PDF langsung tidak tersedia, menyebabkan crawler gagal membaca byte PDF (`not first.startswith(b"%PDF")`).

**Perbaikan.**
- **5-Tier Cascading Fallback:** Alur pengunduhan bertingkat (Direct OA PDF -> Multi-location OpenAlex -> Unpaywall PDF-only -> HTML Dublin Core Meta-Resolver -> arXiv preprint fallback).
- **Dublin Core & Highwire Press Meta-Resolver:** Otomatis mengekstrak `<meta name="citation_pdf_url" content="...">` dari landing page jurnal ilmiah (Springer, DOAJ, ScienceEditor, OJS).
- **Anti-Stall Rate Limit:** Menangani HTTP 429 Semantic Scholar secara langsung tanpa freeze 14 detik jika `SEMANTIC_SCHOLAR_API_KEY` belum dipasang.
- **Resilient PDF Validation:** Pengecekan magic byte `b"%PDF"` pada 1024 byte awal untuk mentolerir BOM atau spasi pembuka.

## 10. Ringkasan Bahasa Awam / Plain-Language Summary untuk Klien (selesai)

**Masalah.** Hasil pembedahan dan tesis naskah akademik dari LLM sering kali sangat teknis (jargon filosofis/metodologis tebal), sehingga klien non-spesialis atau praktisi kesulitan menangkap implikasi praktis atau inti manfaat paper secara cepat.

**Perbaikan.**
- **Ekstensi Skema & Prompt (`plain_summary`):** Menambahkan field `plain_summary` pada pydantic model `PaperAnalysis` di `cosmolab/analyze.py`, lengkap dengan instruksi prompt (ID & EN) agar AI memformulasikan intisari naskah dalam bahasa awam (2–3 kalimat lugas tanpa jargon teknis, fokus pada relevansi dunia nyata/klien).
- **Kompatibilitas Mundur Penuh:** Analisis lama yang belum memiliki field ini tetap terbaca normal tanpa error skema di SQLite `raw_json`.
- **Integrasi UI Kartu & Detail:** 
  - Pada daftar kartu `explorer.py`, menampilkan callout hijau ramah (`paper-card-plain`) tepat di bawah tesis.
  - Pada detail bedah paper (`cosmolab/ui/papers.py`), menampilkan blok `💡 Intisari Bahasa Awam (Untuk Klien / Praktisi)` di bagian paling atas sebelum kisi fakta teknis.
- **Ekspor Markdown/Obsidian:** Format Obsidian pada `cosmolab/export.py` menyertakan heading intisari bahasa awam bila tersedia.

## Ditunda

- **Deteksi lintas bahasa** dengan embedding (`EMBED_MODEL`), untuk draf Indonesia hasil terjemahan dari sumber Inggris. Pertimbangkan setelah nomor 1–3 jalan, terutama kalau banyak sumber mahasiswa berbahasa Inggris. Ada biaya API kecil, dan hasilnya lebih banyak positif palsu.

## Tidak dikerjakan

- **Mengakali GPTZero atau Turnitin.** Bertentangan dengan layanan konsultasi yang bukan joki.
- **Sambungan ke shadow library** (Anna's Archive, Sci-Hub, LibGen). Melanggar hak cipta, dan berisiko hukum serta reputasi bagi firma.
