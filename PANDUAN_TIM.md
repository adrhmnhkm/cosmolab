# Panduan Tim CosmoLab

Panduan ini untuk anggota tim yang tidak berlatar IT. Ikuti langkahnya berurutan.

## 1. Pasang sekali di komputer Anda

1. Pasang Python dari <https://www.python.org/downloads/>. Saat memasang, centang **Add python.exe to PATH**.
2. Salin folder CosmoLab ke komputer Anda (minta ke admin tim).
3. Klik dua kali **Pasang CosmoLab.bat**. Tunggu sampai muncul tulisan "Selesai". Ini bisa makan 5–10 menit.
4. Notepad akan terbuka dengan file `.env`. Isi tiga baris ini dengan nilai dari admin tim, lalu simpan:
   - `LLM_API_KEY`: kunci akses AI
   - `LLM_MODEL`: nama model AI
   - `COSMOLAB_EMAIL`: email kantor

File `.env` berisi kunci rahasia. Jangan kirim file ini ke siapa pun, termasuk klien.

## 2. Setiap kali bekerja

1. Klik dua kali **Jalankan CosmoLab.bat**.
2. Muncul daftar proyek klien. Ketik nama proyek yang mau dibuka, lalu tekan Enter.
   - Ketik `baru` untuk membuat proyek baru. Anda akan ditanya nama proyek dan nama klien.
   - Biarkan kosong untuk memakai data utama (koleksi lama, bukan milik klien mana pun).
3. Dashboard terbuka di browser, di halaman **Beranda**. Nama proyek aktif tampil di kiri atas dan di Beranda. Pastikan namanya benar sebelum mulai.
   - **Perlu tindakan** di Beranda berisi pekerjaan yang menunggu: review yang komentarnya belum diputuskan, review yang Word-nya belum dibuat, dan paper yang belum dianalisis. Klik **Buka** untuk langsung ke halamannya.
   - Di bawahnya ada grafik isi koleksi: tahun terbit (berapa persen terbitan 5 tahun terakhir), jenis penelitian (empiris kuantitatif, kualitatif, kajian literatur, dan seterusnya), bidang ilmu, dan asal sumber. Grafik ini ikut filter **Bidang ilmu** di sidebar. Arahkan kursor ke grafik untuk melihat angkanya.
   - **Bidang ilmu** bawaan: Agama & Filsafat, Hukum, Ekonomi & Bisnis, Pendidikan, Psikologi & Sosial, Sains & Teknologi, Kesehatan, Bahasa & Sastra, dan Lintas bidang & metodologi. Bidang paper ditebak dari judul dan isinya. Paper yang tidak cocok dengan bidang mana pun masuk Lintas bidang. Bidang khusus bisa dibuat di **Cari & tambah paper**, tab **Kelola bidang ilmu**.
   - Contoh pertanyaan di **Tanya koleksi** mengikuti bidang yang dipilih di sidebar.
   - Pemilik yang menjalankan dashboard tanpa mode tim juga melihat status setup, semua proyek, dan pemakaian AI bulan ini.
   - Menu di sidebar mengikuti urutan kerja untuk satu klien:
     - **1 · Kumpulkan**: **Cari & tambah paper**. Termasuk tab **Ringkas dari DOI** untuk meringkas satu paper tanpa memasukkannya ke koleksi.
     - **2 · Pahami**: **Koleksi paper** (daftar, matriks literatur, cari di naskah, ekspor daftar pustaka .bib/.ris) dan **Tanya koleksi**.
     - **3 · Hasil untuk klien**: **Tinjauan pustaka & celah riset** dan **Review draf mahasiswa**.
     - **Lainnya**: Tulis artikel, Latihan debat, Periksa akurasi.
   - Analisis AI setiap paper berisi tujuan riset, metode, sampel dan data, temuan, keterbatasan, dan saran riset lanjutan. Matriks literatur di **Koleksi paper** memakai kolom yang sama, dan pencari celah riset memakai keterbatasan serta saran riset lanjutan sebagai bahan. Paper filsafat dan teologi juga mendapat premis, keberatan, dan pembelaan.
   - **Pertanyaan riset** di Beranda: isi topik, pertanyaan riset mahasiswa, dan hipotesisnya (boleh kosong). Setelah itu tekan **Nilai paper**. AI menilai setiap paper yang sudah dianalisis: mendukung, menolak, campuran, atau tidak berkaitan, dengan satu kalimat alasan. Penilaian memakai ringkasan analisis, bukan naskah penuh, jadi murah (8 paper per panggilan AI). Hasilnya tampil sebagai grafik di Beranda, lencana dan alasan di detail paper, dan kolom di matriks literatur. Kalau pertanyaan atau hipotesis diubah, penilaian lama tidak dipakai dan paper perlu dinilai ulang. Penilaian AI ini bahan awal: baca alasannya sebelum dipakai.
   - Paper yang dianalisis sebelum 13 Nov 2026 belum punya tujuan, sampel, keterbatasan, dan saran. Lengkapi di **Cari & tambah paper**, tab **Analisis paper**, bagian **Perlu dilengkapi**. Biaya AI-nya sama dengan analisis baru. Koreksi peneliti pada kalimat yang berubah ditandai usang, jadi periksa ulang paper yang pernah dikoreksi.
4. Selesai bekerja: tutup jendela hitam (command prompt). Dashboard ikut mati.

## 3. Aturan proyek klien

- **Satu klien, satu proyek.** Paper, ringkasan, dan hasil tulisan klien A tidak akan tercampur dengan klien B.
- **Nama proyek** hanya boleh huruf kecil, angka, `-` dan `_`. Contoh: `2026-11-bank-syariah-x`. Awali dengan tahun dan bulan supaya mudah diurutkan.
- **Lokasi data**: semua isi proyek ada di folder `projects/<nama-proyek>/`. Folder ini tidak ikut ke Git. Cadangkan secara rutin dengan `cosmolab -P <nama-proyek> backup`, lalu salin file zip dari folder `backups/` ke penyimpanan tim.
- **Hasil untuk klien** (artikel, matriks, laporan celah riset) tersimpan di dalam folder proyek itu: `articles/`, `matrices/`, `gaps/`, `synthesis/`.

## 4. Jurnal Indonesia dan peringkat SINTA

**Mencari paper dari jurnal Indonesia.** Di **Cari & tambah paper**, tab **Cari topik**, centang **Khusus jurnal Indonesia**. Pakai kata kunci bahasa Indonesia. CosmoLab hanya mengambil jurnal Indonesia atau artikel berbahasa Indonesia yang punya DOI dan naskah terbuka. Jurnal tanpa DOI tidak ikut; cari manual di Garuda kalau perlu.

**Label SINTA.** Paper dari jurnal yang ada di daftar SINTA tim mendapat label **SINTA 1** sampai **SINTA 6**. Di **Koleksi Paper**, buka **Filter lain** untuk menyaring, misalnya hanya SINTA 1–2.

SINTA tidak menyediakan data untuk diambil otomatis, jadi tim mengisi daftarnya sendiri di **Cari & tambah paper**, tab **Peringkat SINTA**:

1. Buka halaman jurnal di <https://sinta.kemdiktisaintek.go.id/journals>. Catat nama, ISSN cetak dan online, serta peringkatnya.
2. Isi di **Tambah satu jurnal**, atau kumpulkan banyak jurnal di Excel lalu simpan sebagai CSV dan **Impor CSV**. Kolom yang dibutuhkan: `nama`, `issn`, `eissn`, `peringkat`.
3. Klik **Cari jurnal paper lewat DOI** supaya paper lama ikut mendapat label.

Paper tanpa label **belum tentu** tidak terakreditasi; mungkin jurnalnya saja yang belum ada di daftar. Peringkat bisa berubah saat akreditasi ulang. Cek ulang di situs SINTA sebelum menyebut peringkat ke klien.

## 5. Mereview draf mahasiswa

Untuk konsultasi skripsi, tesis, dan disertasi. CosmoLab memberi komentar seperti pembimbing, bukan menulis ulang draf.

1. Buka **Review draf mahasiswa** di menu kiri.
2. Unggah draf (.docx, .md, atau .txt), atau tempel teksnya. Ikutkan daftar pustaka supaya sitasi ikut diperiksa.
3. Pilih jenjang (S1, S2, atau S3), lalu klik **Review draf**.
   - Di atas tombol tampil ukuran draf dan perkiraan waktu, dengan dan tanpa komentar AI. Draf panjang dengan komentar AI bisa 5–15 menit.
   - Matikan **Komentar pembimbing (AI)** kalau hanya perlu cek sitasi dan kemiripan. Cara ini tidak memakai kuota AI.
   - Selama review berjalan, kotak proses menampilkan tahap yang sedang dikerjakan, tahap yang sudah selesai beserta durasinya, dan waktu berjalan. Kalau gagal, kotak itu menyebut tahap tempat review berhenti.
   - **Cek kemiripan** menyala secara bawaan.
4. Baca hasilnya:
   - **Prioritas perbaikan**: hal terpenting untuk dikerjakan mahasiswa.
   - **Komentar per paragraf**: masalah, alasannya, pertanyaan pemandu, dan bagian kalimat yang dikomentari. Paragraf ditandai P1, P2, dan seterusnya dengan kutipan beberapa kata awal.
   - **Pemeriksaan sitasi**: sitasi di teks yang tidak ada di daftar pustaka, dan entri pustaka yang tidak ditemukan.
   - **Cek kemiripan**: kalimat yang terlalu mirip dengan paper di koleksi proyek atau abstrak sumber yang dikutip.
     Labelnya: **tanpa sitasi** (paling penting), **sitasi ke karya lain**, dan **sitasi benar tapi terlalu mirip sumber**.
     Skornya perkiraan, bukan skor Turnitin, karena Turnitin memakai basis data yang jauh lebih besar. Jangan menjanjikan skor Turnitin ke klien.
     Temuan ikut ke dokumen mahasiswa. Centang **Sembunyikan** kalau temuannya keliru, misalnya definisi baku.
     Klik **Lengkapi pembanding dari daftar pustaka** supaya sumber yang dikutip dibandingkan dengan teks lengkapnya, bukan hanya abstrak.
     CosmoLab mengunduh yang legal dan terbuka. Sisanya (biasanya buku) tercantum di **Sumber yang perlu dikirim mahasiswa**:
     minta PDF atau foto halaman yang dikutip ke mahasiswa, lalu unggah di situ. Jangan memakai situs unduhan bajakan.
     Kalimat yang mengutip sumber yang tidak tersedia tidak ikut terperiksa; laporan menyebutkan jumlahnya.
     Peringatan **Pembanding lemah** berarti sumber yang sebahasa dan setopik dengan draf masih kurang dari 5.
     Skor rendah dalam keadaan ini belum berarti aman: lengkapi pembanding atau panen paper setopik dulu.
5. Putuskan setiap komentar AI: **Terima**, **Edit** (ubah kata-katanya), atau **Buang**.
   - Komentar tampil 10 per halaman. Pilih **Belum diputuskan** di kolom **Tampilkan** untuk melihat yang tersisa saja, atau saring per **Tingkat** (penting, saran, catatan).
   - Label **Kutipan cocok**: kalimat yang dikomentari AI memang ada di paragraf itu.
   - Label **Kutipan tidak ditemukan, cek manual**: AI mengutip kalimat yang tidak ada di paragraf itu. Baca paragrafnya dulu. Kemungkinan besar komentarnya keliru.
   - Tombol **Terima ... komentar yang kutipannya cocok** menerima sekaligus semua komentar berlabel kutipan cocok. Tetap baca sekilas sebelum menekannya.
6. Setelah semua komentar diputuskan, isi nama Anda sebagai konsultan pemeriksa, klik **Buat Word berkop firma**, lalu unduh filenya. Dokumen hanya berisi komentar yang diterima atau diedit, ditambah temuan kemiripan yang tidak disembunyikan.

Keputusan tersimpan otomatis. Review bisa dilanjutkan nanti dari tab **Review tersimpan**.

Jangan menulis ulang bagian draf untuk mahasiswa. Perbaikan tetap dikerjakan mahasiswa sendiri.

## 6. Mengirim hasil ke klien

Klien hanya menerima file Word atau PDF berkop firma, bukan file Markdown atau HTML.

1. Buka hasil kerja di dashboard: **Tulis artikel** (tab Arsip) atau **Tinjauan pustaka & celah riset**.
2. Di bagian **Kirim ke Klien**, klik **Periksa Sitasi**. CosmoLab mencocokkan setiap rujukan dengan koleksi proyek dan Crossref.
3. Baca tabel hasilnya:
   - **Terverifikasi**: aman.
   - **Tahun tidak cocok** atau **Penulis tidak cocok**: AI kemungkinan salah tulis. Perbaiki di teks, atau pastikan edisinya memang berbeda.
   - **Tidak ditemukan, cek manual**: sering terjadi pada buku klasik. Cari sendiri di katalog perpustakaan atau Google Scholar. Kalau tidak ada, hapus rujukannya.
   - **Dikutip di teks, tapi tidak ada di daftar rujukan**: tambahkan rujukannya atau hapus kutipannya.
4. Kalau masih ada temuan, centang **Saya sudah memeriksa manual...** hanya setelah Anda benar-benar mengeceknya.
5. Isi nama Anda sebagai peneliti pemeriksa. Nama ini tercantum di dokumen.
6. Klik **Buat Word & PDF**, lalu unduh filenya.

File klien tersimpan di `projects/<proyek>/deliverables/`. Laporan pemeriksaan sitasi tersimpan di `projects/<proyek>/qa/`. Laporan itu untuk internal; jangan dikirim ke klien.

Kop firma (nama, tagline, alamat, kontak, logo) diatur di file `.env` oleh admin tim.

## 7. Bekerja bersama lewat jaringan (Tailscale)

CosmoLab tidak dibuka ke internet. Tim mengaksesnya lewat **Tailscale**, jaringan pribadi yang hanya bisa dimasuki akun yang diundang admin. Gratis untuk tim kecil.

### Untuk admin (sekali saja)

1. Pilih satu komputer kantor sebagai **server**: komputer yang menyala selama jam kerja dan menyimpan folder CosmoLab beserta `projects/`.
2. Pasang Tailscale di komputer server dari <https://tailscale.com/download>, lalu login dengan akun firma.
3. Di halaman admin Tailscale, undang email setiap anggota tim.
4. Buka `.env` di komputer server dan isi `COSMOLAB_TEAM_PASSWORD` dengan password minimal 10 karakter. Bagikan password ini ke tim lewat jalur aman, misalnya langsung atau pengelola password. Jangan lewat grup chat.
5. Isi `COSMOLAB_PRICING` dengan tarif model AI yang dipakai supaya biaya per proyek terhitung.

### Menyalakan server

1. Di komputer server, klik dua kali **Jalankan Server Tim.bat**.
2. Pilih proyek dan port. Satu proyek memakai satu port: misalnya klien A di `8501`, klien B di `8502`.
3. Jendela akan menampilkan alamat seperti `http://100.x.y.z:8501`. Kirim alamat ini ke anggota tim.
4. Kalau Windows bertanya soal firewall, izinkan untuk **Private networks** saja.

### Untuk anggota tim

1. Pasang Tailscale di laptop Anda dan login dengan email yang diundang admin.
2. Buka alamat dari admin di browser, lalu masukkan password tim.
3. Anggota tim tidak perlu memasang Python atau CosmoLab.

### Biaya AI per proyek

- Pemakaian AI bulan ini tampil di sidebar dashboard.
- Rekap per fitur untuk satu proyek: `cosmolab -P <proyek> usage`
- Rekap semua proyek untuk bulan tertentu: `cosmolab usage --all --month 2026-11`

## 8. Kalau ada masalah

| Pesan | Artinya | Yang dilakukan |
| --- | --- | --- |
| "CosmoLab belum dipasang" | Langkah 1 belum dijalankan | Klik dua kali **Pasang CosmoLab.bat** |
| "Proyek '...' belum ada" | Nama proyek salah ketik | Periksa daftar proyek, atau ketik `baru` |
| "Nama proyek hanya boleh huruf kecil..." | Ada spasi atau huruf besar | Ganti spasi dengan `-`, pakai huruf kecil |
| Jawaban AI error atau kosong | Kunci AI salah atau kuota habis | Hubungi admin tim |

Kirim tangkapan layar jendela hitam ke admin tim kalau masalah lain muncul.
