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
3. Dashboard terbuka di browser. Nama proyek aktif tampil di kiri atas. Pastikan namanya benar sebelum mulai.
4. Selesai bekerja: tutup jendela hitam (command prompt). Dashboard ikut mati.

## 3. Aturan proyek klien

- **Satu klien, satu proyek.** Paper, ringkasan, dan hasil tulisan klien A tidak akan tercampur dengan klien B.
- **Nama proyek** hanya boleh huruf kecil, angka, `-` dan `_`. Contoh: `2026-11-bank-syariah-x`. Awali dengan tahun dan bulan supaya mudah diurutkan.
- **Lokasi data**: semua isi proyek ada di folder `projects/<nama-proyek>/`. Folder ini tidak ikut ke Git. Cadangkan secara rutin dengan `cosmolab -P <nama-proyek> backup`, lalu salin file zip dari folder `backups/` ke penyimpanan tim.
- **Hasil untuk klien** (artikel, matriks, laporan celah riset) tersimpan di dalam folder proyek itu: `articles/`, `matrices/`, `gaps/`, `synthesis/`.

## 4. Mereview draf mahasiswa

Untuk konsultasi skripsi, tesis, dan disertasi. CosmoLab memberi komentar seperti pembimbing, bukan menulis ulang draf.

1. Buka **Review draf mahasiswa** di menu kiri.
2. Unggah draf (.docx, .md, atau .txt), atau tempel teksnya. Ikutkan daftar pustaka supaya sitasi ikut diperiksa.
3. Pilih jenjang (S1, S2, atau S3), lalu klik **Review draf**.
4. Baca hasilnya:
   - **Prioritas perbaikan**: hal terpenting untuk dikerjakan mahasiswa.
   - **Komentar per paragraf**: masalah, alasannya, dan pertanyaan pemandu. Paragraf ditandai P1, P2, dan seterusnya dengan kutipan beberapa kata awal.
   - **Pemeriksaan sitasi**: sitasi di teks yang tidak ada di daftar pustaka, dan entri pustaka yang tidak ditemukan.
5. Periksa komentar AI sebelum dikirim. Komentar yang tidak tepat bisa dihapus atau diubah di file Word.
6. Isi nama Anda sebagai konsultan pemeriksa, klik **Buat Word berkop firma**, lalu unduh filenya.

Jangan menulis ulang bagian draf untuk mahasiswa. Perbaikan tetap dikerjakan mahasiswa sendiri.

## 5. Mengirim hasil ke klien

Klien hanya menerima file Word atau PDF berkop firma, bukan file Markdown atau HTML.

1. Buka hasil kerja di dashboard: **Studio Artikel** (tab Arsip) atau **Laporan Sintesis**.
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

## 6. Bekerja bersama lewat jaringan (Tailscale)

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

## 7. Kalau ada masalah

| Pesan | Artinya | Yang dilakukan |
| --- | --- | --- |
| "CosmoLab belum dipasang" | Langkah 1 belum dijalankan | Klik dua kali **Pasang CosmoLab.bat** |
| "Proyek '...' belum ada" | Nama proyek salah ketik | Periksa daftar proyek, atau ketik `baru` |
| "Nama proyek hanya boleh huruf kecil..." | Ada spasi atau huruf besar | Ganti spasi dengan `-`, pakai huruf kecil |
| Jawaban AI error atau kosong | Kunci AI salah atau kuota habis | Hubungi admin tim |

Kirim tangkapan layar jendela hitam ke admin tim kalau masalah lain muncul.
