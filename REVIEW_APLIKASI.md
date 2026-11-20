# Review aplikasi CosmoLab

Disusun 13 Nov 2026. Bahan review: kode setiap halaman (judul, tab, tombol, isi analisis AI) dan data koleksi saat ini. Halaman belum dicoba satu per satu di browser.

Tujuan: CosmoLab dipakai firma konsultan riset untuk mahasiswa S1, S2, dan S3 di semua bidang ilmu. Layanannya konsultasi, tinjauan pustaka, dan pendampingan riset, **bukan joki skripsi**.

## Temuan utama

1. **Aplikasi masih membawa bentuk asalnya.** CosmoLab berawal sebagai alat debat filsafat dan kosmologi ("CosmoLab University"). Banyak halaman, istilah, dan contoh masih berbau ke sana:
   - Tamu debat Hume dan Al-Ghazali.
   - Kurikulum "Turāth Kalam".
   - Contoh DOI "Kalam & Matematika".
   - Contoh pertanyaan tentang fluktuasi vakum kuantum.

   Konsultan dari bidang ekonomi atau pendidikan akan bingung harus mulai dari mana.
2. **Terlalu banyak menu: 14, beberapa tumpang tindih.**
   - Analisis dari DOI ganda dengan tab "Unggah PDF / DOI" di Cari paper.
   - Cari kata di naskah tumpang tindih dengan Koleksi dan Tanya korpus.
   - Ekspor data terpisah dari Koleksi.
3. **Hasil analisis AI memakai kerangka debat, bukan kerangka tinjauan pustaka.**
   - Setiap paper diberi label "mendukung / mengkritik / campuran" tanpa acuan (mendukung apa?).
   - Paper juga diberi "keberatan utama" dan "pembelaan" serta pohon silogisme.

   Untuk paper empiris (survei, eksperimen, studi kasus), yang dibutuhkan konsultan justru:
   - pertanyaan riset;
   - metode;
   - sampel dan data;
   - temuan;
   - keterbatasan;
   - saran riset lanjutan.
4. **Daftar bidang ilmu berat sebelah.** Enam dari dua belas bidang bawaan adalah topik teologi dan filsafat yang sangat spesifik (Ilahiyyat, Teodisi, Nubuwwat, dan seterusnya). Sementara itu Hukum, Ekonomi, Pendidikan, Psikologi, Sains, dan Kesehatan masing-masing hanya satu bidang.
5. **Istilah teknis dan campur bahasa Inggris.** Contohnya "Hybrid Semantic & FTS5", "RAG", "The Academic Dean", "Smart Paper Inspector", "Seketika", dan "Active Recall". Tim konsultan tidak perlu tahu cara kerja mesinnya.
6. **Risiko posisi "bukan joki".** Halaman **Tulis artikel** membuat AI menulis draf artikel dari koleksi lalu mengirimnya ke klien. Kalau kliennya mahasiswa, ini mudah dibaca sebagai menuliskan karya mereka. Perlu keputusan (lihat bagian Keputusan).

## Alur kerja yang diusulkan untuk satu klien

| Langkah | Yang dikerjakan konsultan | Halaman |
| --- | --- | --- |
| 0. Siapkan | Buat proyek klien, isi topik dan pertanyaan riset mahasiswa | Perintah `cosmolab project new`, nanti dari Beranda |
| 1. Kumpulkan | Cari paper (termasuk jurnal Indonesia dan SINTA), tambahkan PDF dari mahasiswa atau DOI | **Cari & tambah paper** |
| 2. Pahami | Baca ringkasan dan matriks literatur, tanya jawab dengan koleksi | **Koleksi paper**, **Tanya koleksi** |
| 3. Hasil konsultasi | Tinjauan pustaka, celah riset, dan usulan topik untuk dibahas bersama mahasiswa | **Tinjauan pustaka & celah riset** |
| 4. Periksa draf | Komentar pembimbing, cek sitasi, cek kemiripan, lalu Word berkop firma | **Review draf mahasiswa** |
| 5. (Usulan) Latihan sidang | AI berperan sebagai penguji dan bertanya tentang draf mahasiswa | **Latihan sidang**, dari Latihan debat |

Beranda menampilkan alur ini sebagai panduan untuk proyek yang masih kosong.

## Penilaian per halaman

Keterangan usulan:
- **Pertahankan**: halaman tetap ada, dengan perbaikan seperlunya.
- **Gabung**: pindah menjadi tab atau tombol di halaman lain.
- **Sembunyikan**: keluar dari menu, kodenya tetap ada dan bisa dikembalikan.
- **Ubah**: fungsinya diganti.

| Menu sekarang | Fungsinya | Untuk firma | Usulan | Yang membingungkan |
| --- | --- | --- | --- | --- |
| Beranda | Pekerjaan menunggu, isi koleksi, kegiatan | Penting | **Pertahankan** | Kartu "Posisi paper" tanpa acuan. Ganti dengan **Jenis penelitian**, yang datanya sudah ada (konseptual 12, filosofis 8, empiris kuantitatif 7, ...) |
| Cari & unduh paper | Cari di OpenAlex, DOAJ, dll.; telusuri sitasi; unggah PDF; analisis | Inti | **Pertahankan**, ganti nama jadi "Cari & tambah paper" | 6 tab. Tab "Per bidang ilmu" memakai bidang bawaan yang filosofis |
| Analisis dari DOI | Ringkas satu paper dari DOI tanpa memasukkannya ke koleksi | Kecil | **Gabung** ke Cari & tambah paper (tab DOI) | Ganda dengan tab Unggah PDF / DOI. Contoh tombolnya kosmologi |
| Koleksi paper | Daftar paper, filter, matriks literatur | Inti | **Pertahankan** | Filter "Jenis argumen" dan posisi. Matriks perlu kolom gaya tinjauan pustaka (metode, sampel, temuan, keterbatasan) |
| Cari kata di naskah | Pencarian kata di teks lengkap | Sedang | **Gabung** jadi kotak cari di Koleksi | Judulnya "Hybrid Semantic & FTS5" |
| Diagram argumen | Pohon silogisme: tesis, premis, keberatan, pembelaan | Kecil di luar filsafat | **Sembunyikan**. Tampilkan sebagai bagian detail paper filsafat saja | Kerangka debat tidak cocok untuk paper empiris |
| Periksa akurasi | Cek analisis ke PDF, metadata dan retraksi, uji akurasi, log audit | Untuk admin | **Pindah** ke bagian admin | Bukan pekerjaan harian konsultan |
| Tanya Korpus (RAG) | Tanya jawab yang dijawab hanya dari koleksi, dengan rujukan | Inti | **Pertahankan**, ganti nama jadi "Tanya koleksi" | Contoh pertanyaan hanya kosmologi. Perlu contoh umum per bidang |
| Review draf mahasiswa | Komentar pembimbing, cek sitasi, cek kemiripan, Word | Inti | **Pertahankan** | Sudah dirapikan (perbaikan 1–8) |
| Tulis artikel | AI menulis draf artikel dari koleksi | Perlu keputusan | Lihat Keputusan 1 | Risiko posisi "bukan joki" |
| Laporan sintesis | Tinjauan pustaka seluruh koleksi, celah riset, usulan topik | Inti, ini hasil konsultasi | **Pertahankan**, ganti nama jadi "Tinjauan pustaka & celah riset" | Nama "sintesis" kurang jelas |
| Kurikulum belajar | Silabus 4 tingkat "Turāth Kalam" untuk "CosmoLab University" | Tidak terpakai | **Sembunyikan** | Peninggalan versi universitas |
| Latihan debat | Debat dengan tokoh filsafat, kritik tesis | Kecil dalam bentuk sekarang | **Ubah** jadi Latihan sidang (Keputusan 2) | Lawannya Hume, Al-Ghazali, Mackie |
| Ekspor data | .bib, .ris, Obsidian, Anki | .bib dan .ris berguna | **Gabung** .bib/.ris sebagai tombol di Koleksi; sembunyikan Obsidian dan Anki | "CosmoLab University", "Active Recall" |

## Menu yang diusulkan

```
Beranda
1 · Kumpulkan
    Cari & tambah paper        (Panen + DOI)
2 · Pahami
    Koleksi paper              (daftar, matriks, cari di naskah, ekspor .bib/.ris)
    Tanya koleksi
3 · Hasil untuk klien
    Tinjauan pustaka & celah riset
    Review draf mahasiswa
    Latihan sidang             (kalau Keputusan 2 disetujui)
Admin
    Periksa akurasi
    Tulis artikel              (kalau Keputusan 1 memilih untuk konten firma)
```

Dari 14 menu menjadi 7 sampai 9. Menu yang disembunyikan tetap ada di kode, jadi bisa dikembalikan kalau ternyata dibutuhkan.

## Perubahan isi (lebih dari sekadar menu)

1. **Analisis paper bergaya tinjauan pustaka.** Tambahkan ke hasil analisis AI:
   - pertanyaan atau tujuan riset;
   - sampel atau data;
   - keterbatasan;
   - saran riset lanjutan.

   Field "mendukung / mengkritik", "keberatan", dan "pembelaan" hanya dipakai untuk paper filsafat. Kolom matriks literatur di Koleksi mengikuti field baru ini. Paper lama perlu dianalisis ulang secara bertahap (ada biaya AI).
2. **Posisi terhadap hipotesis proyek.** Kalau proyek punya pertanyaan riset atau hipotesis, AI menilai setiap paper terhadapnya: mendukung, menolak, atau tidak berkaitan. Barulah grafik posisi di Beranda bermakna. Ini fitur terpisah setelah nomor 1.
3. **Bidang ilmu umum.** Bidang bawaan disusun ulang mengikuti fakultas umum: Agama & Filsafat (gabungan 6 bidang lama), Hukum, Ekonomi & Bisnis, Pendidikan, Psikologi & Sosial, Sains & Teknologi, Kesehatan, dan Bahasa & Sastra. Paper lama dipetakan otomatis. Bidang kustom tetap bisa dibuat.
4. **Bahasa antarmuka.** Semua judul dan subjudul diganti bahasa Indonesia biasa, tanpa istilah mesin (RAG, FTS5, RRF) dan tanpa gaya promosi ("Seketika", "The Academic Dean").
5. **Contoh per bidang.** Contoh pertanyaan dan contoh DOI disesuaikan dengan bidang yang dipilih, bukan kosmologi untuk semua.

## Keputusan yang perlu diambil pemilik

1. **Tulis artikel.** Pilih salah satu:
   - (a) hanya untuk konten firma sendiri (blog, materi webinar, bahan kelas), dipindah ke Admin, dan pengiriman ke klien dihapus;
   - (b) disembunyikan sepenuhnya;
   - (c) dibiarkan seperti sekarang.

   Saran: (a). Draf artikel yang dikirim ke mahasiswa bertentangan dengan "bukan joki".

   **Diputuskan 13 Nov 2026: (a).** Pengiriman ke klien dihapus dari halaman, menu pindah ke bagian Admin.
2. **Latihan debat menjadi Latihan sidang?** AI berperan sebagai dosen penguji. Ia membaca draf mahasiswa, lalu bertanya tentang metode, teori, dan temuan. Konsultan atau mahasiswa menjawab, dan AI memberi umpan balik. Ini layanan pendampingan yang sah dan berguna menjelang sidang. Saran: ya, sebagai fitur tersendiri setelah menu dirapikan.
3. **Bidang ilmu lama.** Enam bidang filsafat digabung menjadi satu "Agama & Filsafat"? Saran: ya. Koleksi saat ini (37 paper) tetap aman, hanya label bidangnya yang berubah.

## Urutan pengerjaan yang disarankan

1. **Rapikan menu dan nama** (sembunyikan, gabung, ganti nama, bahasa antarmuka), ditambah kartu Jenis penelitian di Beranda. Risikonya kecil, dan dampaknya langsung terasa untuk kebingungan.
   **Selesai 13 Nov 2026.** Tulis artikel dan Latihan debat sementara di bagian Lainnya, menunggu Keputusan 1 dan 2. Contoh pertanyaan per bidang masuk langkah 2.
2. **Bidang ilmu umum dan contoh per bidang.**
   **Selesai 13 Nov 2026.** Keputusan 3 disetujui. Ditambah bidang cadangan "Lintas bidang & metodologi" untuk paper yang tidak cocok ke bidang mana pun.
3. **Analisis paper bergaya tinjauan pustaka** dan kolom matriks literatur.
   **Selesai 13 Nov 2026.** Field baru disimpan di raw_json. 34 paper lama di data utama perlu dilengkapi (biaya AI). Posisi mendukung/mengkritik hanya tampil untuk paper filsafat.
4. **Pertanyaan riset per proyek** dan posisi paper terhadap hipotesis.
   **Selesai 13 Nov 2026.** Disimpan per folder data (research_question.json, positions.json). Penilaian belum dijalankan pada data asli (biaya AI).
5. **Latihan sidang**, kalau disetujui.
   **Selesai 13 Nov 2026.** Keputusan 2 disetujui. Latihan debat keluar dari menu (kodenya tetap ada).
6. Akun per orang untuk tim (lihat RENCANA_AKUN_TIM.md).
   **Tahap 1 selesai 13 Nov 2026.**

Setiap langkah dites dan dicek di dashboard uji, seperti perbaikan sebelumnya.
