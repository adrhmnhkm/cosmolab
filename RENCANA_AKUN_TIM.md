# Rencana: akun per orang untuk tim

Status: **Tahap 1 selesai 13 Nov 2026** (akun, peran, akses proyek, login, CLI). Tahap 2 belum dikerjakan.

Catatan: alur login diuji otomatis. Uji langsung di browser dengan dua akun asli belum dilakukan (lihat TES_TERTUNDA.md).

## Masalah sekarang

Tim masuk lewat Tailscale dengan **satu password bersama** (`COSMOLAB_TEAM_PASSWORD`). Dari sisi jaringan ini sudah cukup aman, tetapi aplikasi tidak tahu siapa yang sedang memakai:

- Log audit selalu mencatat akun Windows komputer server, bukan nama konsultan.
- Nama konsultan pemeriksa di Word harus diketik manual.
- Pemilik tidak bisa masuk sebagai admin dari dashboard mode tim, sehingga bagian **Khusus pemilik** hanya ada di dashboard lokal.
- Siapa pun yang tahu password bisa membuka semua proyek klien, padahal draf mahasiswa itu rahasia.

## Skenario harian setelah ada akun

1. Konsultan membuka alamat proyek, misalnya `http://100.x.y.z:8501`, lewat Tailscale.
2. Masuk dengan **nama pengguna dan password masing-masing**.
3. Beranda menampilkan "Perlu tindakan" yang dipisah: **punya saya** (review yang ia buat) dan **tim**.
4. Saat membuat Word, nama konsultan pemeriksa terisi otomatis dari akunnya.
5. Log audit mencatat orangnya, misalnya "rina: review draf tesis_x.docx".
6. Admin login dengan akunnya dan melihat bagian Khusus pemilik walaupun dashboard berjalan dalam mode tim.

## Tahap 1: akun per orang

### Akun dan peran

- Daftar akun disimpan di satu file di server, di luar git (misalnya `shared/team_users.json`). Password disimpan sebagai hash scrypt dengan salt, bukan teks asli.
- Dua peran:
  - **admin**: semua fitur, bagian pemilik, semua proyek.
  - **konsultan**: kerja harian, tanpa bagian pemilik dan biaya.

### Akses per proyek

- Setiap proyek punya daftar anggota di `project.json`.
- Konsultan yang bukan anggota proyek ditolak saat login ke dashboard proyek itu. Admin selalu boleh masuk.
- Data utama (bukan proyek klien) hanya untuk admin.

### Perintah admin (CLI)

| Perintah | Fungsi |
| --- | --- |
| `cosmolab team add rina --role konsultan` | Buat akun, cetak password sementara |
| `cosmolab team list` | Daftar akun, peran, dan proyeknya |
| `cosmolab team add-member <proyek> rina` | Beri akses proyek |
| `cosmolab team remove-member <proyek> rina` | Cabut akses proyek |
| `cosmolab team reset rina` | Password sementara baru |
| `cosmolab team remove rina` | Hapus akun |

### Login

- Form nama pengguna dan password, menggantikan form password tim.
- Password sementara wajib diganti saat pertama masuk, minimal 10 karakter.
- Percobaan salah diperlambat, seperti sekarang. Pesan galat tidak membedakan "akun tidak ada" dari "password salah".
- Tombol **Keluar** di sidebar, dan nama akun tampil di sidebar.

### Yang ikut berubah

- `audit.log` memakai nama akun yang login, bukan akun Windows.
- Review menyimpan pembuatnya (`created_by`).
- Nama konsultan pemeriksa di Word terisi otomatis (masih bisa diubah).
- Beranda punya filter "Punya saya / Semua" di Perlu tindakan.
- Bagian Khusus pemilik tampil untuk peran admin, termasuk di mode tim.

### Masa transisi

- Selama belum ada akun yang dibuat, password tim bersama tetap berlaku.
- Begitu akun pertama dibuat, login wajib memakai akun dan password bersama tidak dipakai lagi.
- Dashboard lokal tanpa mode tim tetap tanpa login, karena itu tampilan pemilik.

### Tes

- Tes otomatis untuk hash dan verifikasi password, peran, keanggotaan proyek, ganti password pertama kali, dan login di halaman (AppTest).
- Cek di dashboard uji mode tim dengan dua akun: satu admin, satu konsultan. Pastikan konsultan non-anggota ditolak dan tidak melihat bagian pemilik.
- Perbarui PANDUAN_TIM §7: cara admin membuat akun dan cara anggota tim masuk.

## Tahap 2: nanti, kalau tim bertambah

- **Satu alamat untuk semua proyek.** Selesai 15 Nov 2026: lobi tim (`cosmolab tim`, `cosmolab/lobby.py`). Lobi menyalakan satu dashboard per proyek di port 8502 ke atas (`cosmolab/servers.py`) dan menyerahkan login dengan tiket sekali pakai. Satu proses per proyek tetap dipertahankan karena `config.ROOT` berlaku untuk satu proses.
- **Dua orang membuka review yang sama.** Tampilkan "sedang dibuka oleh X" dan kunci file saat menyimpan, supaya keputusan tidak saling menimpa. Sekarang risikonya kecil karena setiap klik menyimpan satu komentar saja.
- **Login otomatis lewat identitas Tailscale.** `tailscale serve` meneruskan nama dan email pengguna lewat header, jadi tidak perlu password. Syaratnya Streamlit hanya mendengar di `localhost`, supaya header tidak bisa dipalsukan. Layak kalau mengelola password mulai merepotkan.

## Tidak disarankan

- **Login Google atau layanan luar.** Butuh domain publik dan HTTPS. Tailscale ditambah akun per orang sudah cukup untuk firma kecil.
- **Membuka dashboard ke internet tanpa Tailscale.** Draf dan data klien jadi terlalu terbuka.
