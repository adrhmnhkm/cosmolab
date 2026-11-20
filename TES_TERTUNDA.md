# Tes tertunda

Daftar pengujian yang belum dijalankan. Centang setelah selesai, lalu hapus bagian yang sudah lulus.

## Jurnal Indonesia dan peringkat SINTA (commit 1c8bd9c, 13 Nov 2026)

### Sudah dites

- Tes otomatis: format ISSN dan digit pemeriksa, pembacaan peringkat, tambah/perbarui/hapus jurnal, impor CSV (termasuk baris rusak), pencocokan paper ke peringkat, pencarian ISSN lewat DOI (data palsu), filter OpenAlex mode Indonesia.
- Dashboard tanpa browser: form **Tambah satu jurnal** menyimpan jurnal; semua 13 halaman tampil tanpa error.
- Langsung ke OpenAlex: pencarian "literasi keuangan syariah UMKM" mode Indonesia memberi 8 artikel jurnal Indonesia, semuanya ber-ISSN dan ber-PDF terbuka. Pencarian jurnal dari DOI berhasil.
- CI GitHub lulus di `main` dan `master`.

### Belum dites

Kerjakan di proyek uji sementara supaya data klien tidak tercampur:

```bash
cosmolab project new uji-sinta --client "Uji"
```

Matikan **Langsung analisis** saat panen. Dengan begitu kuota AI tidak terpakai.

- [ ] **Panen sungguhan mode Indonesia.**
  Langkah: Panen Paper → Cari topik → centang **Khusus jurnal Indonesia** → kata kunci bahasa Indonesia, 3–5 paper → Cari & unduh.
  Harus terjadi: PDF terunduh. Di `projects/uji-sinta/metadata.jsonl`, setiap paper baru punya `journal` dan `issn`.

- [ ] **Impor CSV lewat dashboard.**
  Langkah: buat CSV berkolom `nama;issn;eissn;peringkat`, isi dengan ISSN jurnal dari hasil panen di atas, satu baris dengan ISSN salah → Panen Paper → tab Peringkat SINTA → Impor CSV.
  Harus terjadi: pesan "... jurnal baru". Baris rusak disebut nomornya. Tabel daftar jurnal ikut bertambah.

- [ ] **Badge SINTA di Koleksi Paper.**
  Harus terjadi: paper dari jurnal yang ada di daftar menampilkan badge **SINTA n**. Paper lain tanpa badge.

- [ ] **Filter peringkat.**
  Langkah: Koleksi Paper → Filter lain → Peringkat jurnal SINTA → "SINTA 1–2", lalu "Ada di daftar SINTA".
  Harus terjadi: hanya paper yang sesuai yang tersisa. Jumlah di "Menampilkan x dari y" berubah.

- [ ] **Tombol "Cari jurnal paper lewat DOI" pada paper lama.**
  Langkah: buka proyek yang paper-nya dipanen sebelum fitur ini ada → tab Peringkat SINTA → klik tombolnya.
  Harus terjadi: pesan "ISSN dicari untuk n paper, ketemu m". Klik kedua tidak mencari ulang (n = 0). Badge muncul untuk jurnal yang ada di daftar.

- [ ] **Tampilan di browser.**
  Cek tab Peringkat SINTA, badge, dan filter di layar lebar dan sempit. Tidak ada teks terpotong atau tombol bertumpuk.

Selesai: hapus proyek uji (`projects/uji-sinta/`). Kosongkan juga jurnal uji dari `shared/sinta_journals.json` kalau bukan data asli.

## Cek kemiripan pra-submit (13 Nov 2026)

### Sudah dites

- Tes otomatis: pemecahan kalimat, pengecualian teks bertanda petik dan sitasi, tiga label (tanpa sitasi, sitasi ke karya lain, terlalu dekat), sitasi di kalimat berikutnya, skor dan sumber teratas, pengambilan abstrak sumber yang dikutip (data palsu), menyembunyikan temuan, jalankan ulang yang tetap menyimpan temuan tersembunyi, Word tanpa komentar AI.
- Dashboard tanpa browser: review tanpa AI, centang Sembunyikan, buat Word.
- Korpus asli (37 paper, 475 ribu kata): 1,1 detik. Dua kalimat salinan tertangkap dengan label benar, kalimat tulisan sendiri tidak tertandai.
- Ambil abstrak dari OpenAlex lewat DOI: berhasil.

### Belum dites

- [ ] **Review sungguhan dengan cek Crossref menyala.** Unggah draf .docx asli yang mengutip beberapa artikel ber-DOI. Harus terjadi: angka "abstrak sumber yang dikutip" lebih dari 0, dan sumber dikutip muncul di tabel sumber kalau ada kalimat yang mirip.
- [ ] **Isi file Word.** Buka Word hasil review. Harus terjadi: bagian "Pemeriksaan kemiripan" ada, kalimat tersembunyi tidak muncul, teks sumber tidak muncul, catatan "bukan skor Turnitin" ada.
- [ ] **Korpus besar.** Proyek dengan 200+ paper. Harus terjadi: cek selesai dalam hitungan detik, bukan menit.
- [ ] **Positif palsu bahasa Indonesia.** Draf asli mahasiswa yang ditulis sendiri. Harus terjadi: frasa umum ("hasil penelitian ini menunjukkan bahwa") tidak tertandai.
- [ ] **Tampilan di browser.** Tab Cek kemiripan, badge, dan centang Sembunyikan rapi di layar lebar dan sempit.

## Lengkapi pembanding dan cakupan sumber (13 Nov 2026)

### Sudah dites

- Tes otomatis: jenis sumber (buku, jurnal, skripsi, peraturan, situs), link OJS diubah ke link unduh, status per sumber, sumber yang sudah dicari tidak dicari ulang, status "abstrak saja", unggahan mahasiswa tersimpan dengan judul, tahun, dan penulis dari daftar pustaka, laporan internal berisi daftar permintaan.
- Dashboard tanpa browser: tombol Lengkapi pembanding dan ringkasan cakupan.
- Uji coba tanpa menyimpan pada tesis 56 sumber: 28 bisa diunduh lewat DOI, 2 lewat judul, 3 punya URL (belum dicoba unduh), 23 harus diminta ke mahasiswa (9 buku, 8 jurnal, 4 situs, 2 lainnya).

### Belum dites

- [ ] **Unduh sungguhan di proyek klien.** Buat proyek uji, review tesis yang sama, klik Lengkapi pembanding. Harus terjadi: sekitar 30 PDF masuk ke `projects/<proyek>/pdf/`, ringkasan cakupan berubah, skor kemiripan dihitung ulang.
- [ ] **Unggah sumber dari mahasiswa** lewat daftar "Sumber yang perlu dikirim mahasiswa". Harus terjadi: status jadi "Teks lengkap (dikirim mahasiswa)" dan cek kemiripan jalan ulang.
- [ ] **Batas permintaan API.** Uji coba tadi kena pembatasan (rate limit) Unpaywall/OpenAlex beberapa kali. Pastikan proses tetap selesai dan tidak ada sumber yang salah dicatat "tidak tersedia" hanya karena dibatasi.
- [ ] **Unduh lewat URL OJS** pada 3 sumber yang punya link.

## Peringatan pembanding lemah (13 Nov 2026)

### Sudah dites

- Tes otomatis: tebakan bahasa (Indonesia, Inggris, tidak yakin), sumber berbahasa lain dan sumber sebahasa yang beda topik tidak dihitung, pesan untuk konsultan dan catatan untuk mahasiswa.
- Tesis asli: draf berbahasa Indonesia, 10 paper berbahasa Indonesia di koleksi tapi 0 yang setopik, ditandai lemah. Paruh lain tesis yang sama dikenali setopik (0,73 berbanding paling tinggi 0,20 untuk paper yang tidak setopik).

### Belum dites

- [ ] **Koleksi yang benar-benar setopik.** Proyek dengan 10+ paper Indonesia yang setopik dengan draf. Harus terjadi: tidak ada peringatan lemah. Kalau peringatan tetap muncul, ambang `TOPIC_MIN_SHARE` (0,3) di `similarity.py` perlu diturunkan.
- [ ] **Draf berbahasa Inggris** dengan sumber berbahasa Inggris. Harus terjadi: bahasa terdeteksi Inggris, peringatan sesuai jumlah sumber.

## Log proses review (13 Nov 2026)

### Sudah dites

- Tes otomatis: urutan tahap (baca, sitasi, komentar, kemiripan), setiap tahap ditutup dengan ringkasan dan durasi, progress bar sampai 100%, tahap yang gagal tetap tercatat.
- CLI `cosmolab review --offline --tanpa-komentar` pada tesis asli (272 paragraf, 56 entri): tahap dan durasi tampil di terminal.

### Belum dites

- [ ] **Kotak proses di dashboard** dengan tesis panjang, Crossref dan komentar AI menyala. Harus terjadi: label berganti per tahap ("12/56 entri pustaka", "batch 3/9"), daftar tahap selesai bertambah, kotak tertutup dengan "Review selesai dalam ...". Restart server dulu.
- [ ] **Review gagal di tengah**, misalnya kunci API AI salah. Harus terjadi: kotak merah "Gagal saat Komentar AI ..." dengan pesan galatnya.

## Perkiraan durasi review (13 Nov 2026)

### Sudah dites

- Tes otomatis: jumlah paragraf, entri pustaka, dan batch; urutan kalimat saat komentar AI dimatikan; catatan Crossref untuk daftar pustaka panjang; keterangan perkiraan tampil di halaman Review sebelum tombol diklik.
- Tesis asli (272 paragraf, 56 entri, 12 batch): "5–15 menit dengan komentar AI; 1–3 menit tanpa komentar AI".

### Belum dites

- [ ] **Bandingkan perkiraan dengan waktu sebenarnya.** Jalankan review tesis panjang dengan komentar AI dan Crossref, lalu lihat durasi di kotak proses. Kalau meleset jauh, ubah angka `SEC_PER_BATCH` (komentar AI) atau `SEC_PER_REF_ONLINE` (Crossref) di `cosmolab/review.py`. Angka sekarang masih tebakan.
- [ ] **Unggah file .docx** di dashboard: keterangan perkiraan muncul setelah file dipilih, dan berubah saat Crossref atau komentar AI dimatikan.

## Daftar komentar AI yang panjang (13 Nov 2026)

Laporan pengguna: dengan 66 komentar, halaman terlalu panjang, tombol keputusan terasa tidak berfungsi, dan unduhan versi internal gagal.

Sebabnya: tombol keputusan sebenarnya menyimpan. Tetapi setiap klik menggambar ulang seluruh halaman (66 kartu), dan kartu yang baru diputuskan langsung terlipat sehingga hilang dari pandangan. Tombol unduh memicu gambar ulang yang sama, dan file unduhan bisa sudah diganti sebelum sempat diambil.

### Sudah dites

- Dashboard uji (proyek `uji-coba`, salinan review 66 komentar): klik Terima tampil dalam 1 detik, kartu tetap di tempat, progres bertambah. Pindah ke halaman berikutnya juga berjalan.
- Tes otomatis: 10 komentar per halaman, keputusan tersimpan, halaman berikutnya, filter "Sudah diputuskan".

### Belum dites

- [ ] **Unduh versi internal (Markdown)** dan **Unduh Word** di browser sungguhan. Isi file harus mengikuti keputusan terbaru walaupun halaman belum dimuat ulang. Tidak saya klik karena akan menyimpan file ke komputer.
- [ ] Setelah komentar terakhir diputuskan, bagian **Kirim ke mahasiswa** harus berubah sendiri (pesan "Masih ada ... komentar" hilang).

## Beranda (13 Nov 2026)

### Sudah dites

- Tes otomatis: daftar Perlu tindakan (komentar belum diputuskan, Word belum dibuat, pembanding lemah, sumber yang perlu diminta, paper belum dianalisis), review yang Word-nya sudah dibuat tidak muncul lagi, umur backup, ringkasan semua proyek, mode pemilik dan mode tim.
- Dashboard uji (proyek `uji-coba`): Beranda tampil sebagai halaman pertama, dengan review 66 komentar di Perlu tindakan, aktivitas terbaru, dan status setup.

### Belum dites

- [x] **Tombol Buka** di Perlu tindakan membuka review yang benar di halaman Review draf (dicek di dashboard uji).
- [ ] **Tabel Semua proyek dan Pemakaian AI** dilihat langsung (di tes, isinya hanya dicek lewat Python karena tangkapan layar gagal).
- [ ] **Mode tim** (`cosmolab ui --team`): bagian "Khusus pemilik" tidak tampil.
- [ ] Review yang Word-nya dibuat **sebelum** pembaruan ini tetap muncul sebagai "siap, Word belum dibuat", karena catatan Word baru disimpan mulai sekarang. Buat ulang Word-nya, atau abaikan.

## Muat ulang halaman tanpa restart (13 Nov 2026)

Laporan pengguna: setelah pembaruan Beranda, dashboard yang sedang jalan gagal dengan `AttributeError: module 'cosmolab.ui.pages' has no attribute 'home'`.

### Sudah dites

- Tes otomatis: halaman yang ditambahkan setelah server menyala ikut termuat.
- Dashboard uji: teks Beranda diubah selagi server menyala, dan perubahannya tampil setelah satu klik, tanpa restart.

### Belum dites

- [ ] Dashboard utama yang menampilkan galat tadi: cukup muat ulang tab browser, tanpa restart. Kalau galat masih muncul, restart sekali. Server yang sudah berjalan masih memakai `web.py` lama yang belum punya fitur muat ulang ini.

## Beranda visual (13 Nov 2026)

### Sudah dites

- Tes otomatis: data grafik (tahun terbit dan persentase 5 tahun terakhir, posisi paper, peringkat dengan "Lainnya", angka utama, pertumbuhan koleksi, kalender aktivitas, kegiatan per minggu), dan review yang Word-nya dibuat sebelum pencatatan baru dianggap selesai lewat log audit.
- Dashboard cek dengan data asli, layar 1440 px: semua grafik tampil. Review tesis yang sudah dikirim tidak lagi muncul di Perlu tindakan.
- Layar HP (375 px): kolom bertumpuk, tidak ada geser ke samping.
- Palet warna lolos validator buta warna (teal #0E8A72 dan amber #B87A00 di atas putih).

### Belum dites

- [ ] **Tooltip** di setiap grafik (arahkan kursor) belum dicoba satu per satu.
- [ ] **Filter Bidang ilmu** di sidebar mengubah grafik isi koleksi.
- [ ] **Mode tim**: kartu keempat menjadi "Kegiatan minggu ini" dan bagian pemilik tersembunyi.

## Akun tim (13 Nov 2026)

### Sudah dites

- Tes otomatis: hash password (tidak tersimpan sebagai teks), login benar dan salah, wajib ganti password sementara, peran admin dan konsultan, akses per proyek, data utama khusus admin, hapus akun, nama akun di log audit dan di review, bagian pemilik untuk admin.
- Tes otomatis halaman login: password bersama selama belum ada akun, login akun, form ganti password, konsultan non-anggota ditolak, akses dicabut lalu kembali ke form login, nama akun di sidebar.

### Belum dites

- [ ] **Uji langsung di browser lewat Tailscale** dengan dua akun asli (satu admin, satu konsultan).
- [ ] **Tombol Keluar** di sidebar.
- [ ] **Perlambatan setelah 5 kali salah password.**
- [ ] **Nama konsultan terisi otomatis di Word** dari akun yang login.
- [ ] **Filter "Punya saya"** di Perlu tindakan.
- [ ] **Jalankan Server Tim.bat** setelah ada akun (pesan di jendela server).
- [ ] Analisis paper berjalan di thread terpisah: pastikan log auditnya tetap mencatat nama akun, bukan akun Windows.

