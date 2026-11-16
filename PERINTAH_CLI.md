# Daftar perintah CLI CosmoLab

Semua perintah dijalankan dari folder CosmoLab (`D:\Cosmolab\cosmolab`).

## Cara menulis perintah

Pilih salah satu cara berikut.

1. **Venv aktif.** Jalankan `.venv\Scripts\activate`. Setelah itu cukup ketik `cosmolab <perintah>`.
2. **Tanpa mengaktifkan venv.** Ketik `.venv\Scripts\cosmolab <perintah>`.
3. **Cara yang dipakai file .bat.** Ketik `.venv\Scripts\python -m cosmolab.cli <perintah>`.

Contoh di bawah memakai cara 1.

### Memilih proyek klien

Tambahkan `-P <nama-proyek>` **sebelum** nama perintah:

```bash
cosmolab -P 2026-11-rina-pbl status
```

Tanpa `-P`, CosmoLab memakai data utama di folder `data/`. Cara lain: isi `COSMOLAB_PROJECT` di environment.

### Bantuan

```bash
cosmolab --help
```

```bash
cosmolab <perintah> --help
```

---

## 1. Menyalakan aplikasi

| Perintah | Fungsi |
| --- | --- |
| `cosmolab ui` | Buka dashboard di komputer ini (http://localhost:8501). |
| `cosmolab -P <proyek> ui` | Buka dashboard untuk satu proyek klien. |
| `cosmolab ui --port 8502` | Pakai port lain, misalnya kalau 8501 sedang dipakai. |
| `cosmolab ui --team` | Buka satu dashboard untuk tim lewat Tailscale. Wajib ada `COSMOLAB_TEAM_PASSWORD` di `.env`. |
| `cosmolab ui --team --host <alamat>` | Sama seperti di atas, dengan alamat selain IP Tailscale. |
| `cosmolab tim` | **Server tim.** Lobi untuk login, memilih proyek, dan membuat proyek dari browser. |
| `cosmolab tim --port 8501 --host <alamat>` | Lobi tim dengan port atau alamat lain. |
| `cosmolab ai` | Tampilkan AI yang sedang dipakai semua fitur. |
| `cosmolab ai api` / `cosmolab ai utama` | Ganti AI untuk semua fitur, semua proyek, dashboard, dan tim: API berbayar, atau AI di `.env` (biasanya AI lokal). Sama dengan pilihan "AI yang dipakai" di sidebar. |

Pintasan tanpa terminal:

- `Pasang CosmoLab.bat`: pasang pertama kali.
- `Jalankan CosmoLab.bat`: pilih proyek, lalu jalankan `ui`.
- `Jalankan Server Tim.bat`: jalankan `tim`.

Untuk mematikan server, tekan `Ctrl+C` atau tutup jendela terminalnya.

## 2. Proyek klien

| Perintah | Fungsi |
| --- | --- |
| `cosmolab project new <nama> --client "<klien>" --description "<ringkasan>"` | Buat proyek baru di `projects/<nama>/`. |
| `cosmolab project list` | Tampilkan semua proyek. |
| `cosmolab -P <proyek> project info` | Tampilkan proyek aktif dan lokasi datanya. |

Contoh nama proyek: `2026-11-klien-a`.

## 3. Akun tim

Akun tim dipakai saat dashboard berjalan dalam mode tim (`ui --team` atau `tim`).

| Perintah | Fungsi |
| --- | --- |
| `cosmolab team add <username> --role konsultan --name "<Nama Lengkap>"` | Buat akun dan cetak password sementaranya. Pilihan `--role`: `admin` atau `konsultan`. |
| `cosmolab team list` | Daftar akun, peran, dan proyeknya. |
| `cosmolab team add-member <proyek> <username>` | Beri satu akun akses ke satu proyek. |
| `cosmolab team remove-member <proyek> <username>` | Cabut akses satu akun dari satu proyek. |
| `cosmolab team reset <username>` | Buat password sementara baru. |
| `cosmolab team remove <username>` | Hapus akun dan cabut semua akses proyeknya. |
| `cosmolab team owner <username>` | Jadikan admin ini pemilik. Hanya pemilik yang boleh membuat, mereset, dan menghapus admin di lobi. |

## 4. Kumpulkan paper

| Perintah | Fungsi |
| --- | --- |
| `cosmolab harvest "<kata kunci>"` | Cari dan unduh paper open access dari banyak sumber. Teks PDF langsung diekstrak. |
| `cosmolab harvest "<kata kunci>" --max-results 40` | Batasi jumlah paper (bawaan 40). |
| `cosmolab harvest "<kata kunci>" --indonesia` | Hanya jurnal Indonesia atau artikel berbahasa Indonesia. |
| `cosmolab harvest "<kata kunci>" --no-extract` | Unduh saja, tanpa ekstrak teks. |
| `cosmolab snowball --arah both --top 20 --unduh 5` | Cari paper yang dirujuk (`backward`) atau yang mengutip (`forward`) koleksi. `--unduh N` mengunduh N kandidat teratas yang terbuka. |
| `cosmolab snowball --file <nama-file-paper>` | Telusuri hanya satu paper. Opsi ini boleh diulang. |
| `cosmolab inspect <DOI>` | Ringkas satu paper dari DOI: abstrak, metode, hasil, kesimpulan, celah. |
| `cosmolab doi <DOI>` | Sama dengan `inspect`. |

## 5. Olah paper

| Perintah | Fungsi |
| --- | --- |
| `cosmolab extract` | Ambil teks dari PDF yang belum diekstrak. |
| `cosmolab extract --force` | Ekstrak ulang semua PDF. |
| `cosmolab analyze` | Analisis paper dengan AI: tujuan, metode, sampel, temuan, keterbatasan. |
| `cosmolab analyze --force --lang id` | Analisis ulang semua paper, hasil dalam bahasa Indonesia. |
| `cosmolab analyze --model <nama-model> --concurrency 4` | Pilih model AI dan jumlah proses sekaligus. |
| `cosmolab embed` | Siapkan indeks pencarian makna sekarang, supaya pertanyaan pertama tidak lambat. |
| `cosmolab sync` | Sinkronkan ulang database dan indeks pencarian dengan isi folder. |
| `cosmolab status` | Lihat jumlah paper di setiap tahap. |

## 6. Rapikan data paper

| Perintah | Fungsi |
| --- | --- |
| `cosmolab authors` | Lengkapi nama penulis. |
| `cosmolab authors --no-ai` | Sama, tanpa AI. |
| `cosmolab authors --refresh` | Cari ulang juga paper yang sudah punya penulis. Isian manual tidak ditimpa. |
| `cosmolab dois` | Lengkapi DOI. DOI yang sudah ada tidak ditimpa. |
| `cosmolab dois --file <nama-file-paper> --set <DOI>` | Pasang DOI yang sudah dicek manual. |
| `cosmolab cek-metadata` | Cek judul, tahun, dan penulis ke Crossref/DataCite. Paper yang ditarik (retraksi) ditandai. |

## 7. Jurnal SINTA

Daftar SINTA dipakai bersama oleh semua proyek dan disimpan di `shared/`.

| Perintah | Fungsi |
| --- | --- |
| `cosmolab sinta import <file.csv>` | Impor daftar jurnal dari CSV berkolom ISSN dan peringkat. |
| `cosmolab sinta add --issn <ISSN> -r 2 --nama "<Nama Jurnal>"` | Tambah atau perbarui satu jurnal. Peringkat 1 sampai 6. Beberapa ISSN dipisah koma. |
| `cosmolab sinta list` | Tampilkan daftar jurnal SINTA. |
| `cosmolab sinta cek` | Cari jurnal dan ISSN paper proyek lewat DOI, lalu hitung yang berlabel SINTA. |
| `cosmolab sinta cek --limit 50` | Sama, dibatasi 50 paper. |

## 8. Cari dan tanya koleksi

| Perintah | Fungsi |
| --- | --- |
| `cosmolab search "<kata kunci>"` | Cari paper di koleksi. Bawaan 5 hasil. Ubah dengan `--limit`. |
| `cosmolab search "<kata kunci>" --exact` | Cari kata yang persis sama saja. |
| `cosmolab ask "<pertanyaan>"` | Tanya koleksi. Jawaban bersitasi, dan setiap klaim dicek otomatis. |
| `cosmolab ask "<pertanyaan>" --top-k 6 --no-cek` | Atur jumlah paper yang dibaca, dan lewati cek klaim. |
| `cosmolab ask "<pertanyaan>" --classic` | Pakai cara jawab yang lebih sederhana. |
| `cosmolab ask "<pertanyaan>" --save-obsidian` | Simpan jawaban ke catatan Obsidian. |
| `cosmolab jejak "<pertanyaan>"` | Tampilkan langkah demi langkah cara sumber dipilih untuk pertanyaan itu. |
| `cosmolab jejak "<pertanyaan>" --jawab` | Lanjutkan sampai jawaban AI dan cek klaim. |

## 9. Hasil untuk klien

| Perintah | Fungsi |
| --- | --- |
| `cosmolab review <draf.docx> --jenjang s1` | Review draf mahasiswa: komentar pembimbing, cek sitasi, cek kemiripan. Jenjang: `s1`, `s2` (bawaan), atau `s3`. Draf bisa `.docx`, `.md`, atau `.txt`. |
| `cosmolab review <draf.docx> --tanpa-komentar` | Cek sitasi dan kemiripan saja, tanpa biaya AI. |
| `cosmolab review <draf.docx> --tanpa-kemiripan` | Lewati cek kemiripan. |
| `cosmolab review <draf.docx> --offline` | Jangan cek daftar pustaka ke Crossref. |
| `cosmolab synthesize --lang id` | Laporan sintesis lintas paper dalam bahasa Indonesia. Bawaan `en`. |
| `cosmolab graph "<nama paper>"` | Diagram alur argumen satu paper (Mermaid). |
| `cosmolab verify <file.md>` | Periksa daftar rujukan dan kutipan sebelum dikirim. `--offline`: cek ke koleksi saja. |
| `cosmolab deliver <file.md> --reviewer "<Nama Konsultan>"` | Buat Word dan PDF berkop firma setelah sitasi diperiksa. |

Opsi tambahan `deliver`:

- `--format docx`, `pdf`, atau `both` (bawaan).
- `--title "<judul>"`: bawaannya judul H1 di file.
- `--offline`: cek sitasi ke koleksi proyek saja.
- `--sudah-cek-manual`: sitasi yang tidak bisa dicek otomatis sudah diperiksa manual.
- `--klaim-sudah-dicek`: klaim yang tidak didukung sumber sudah diperiksa manual.

Hasil review masih harus diputuskan konsultan di dashboard (menu **Review draf mahasiswa**) sebelum dikirim.

## 10. Khusus admin: konten firma

| Perintah | Fungsi |
| --- | --- |
| `cosmolab article "<topik>" --style essay` | Tulis artikel untuk konten firma (blog, webinar). Gaya: `essay`, `journal_review`, `monograph`. Bukan untuk pekerjaan klien. |
| `cosmolab article "<topik>" --instructions "<fokus>" --no-save` | Beri arahan sudut pandang, dan jangan simpan otomatis. |

## 11. Cek akurasi

| Perintah | Fungsi |
| --- | --- |
| `cosmolab cek-klaim <file.md>` | Cek setiap kalimat bersitasi terhadap paper yang dirujuk. |
| `cosmolab cek-analisis "<nama paper>"` | Bandingkan analisis AI satu paper dengan teks PDF-nya. |
| `cosmolab cek-analisis --semua` | Cek semua paper yang belum dicek. |
| `cosmolab uji buat --n 10` | Buat soal uji dari 10 paper baru. |
| `cosmolab uji jalan` | Jalankan uji akurasi pencarian dan pemeriksa klaim. Bawaannya hanya soal yang sudah diperiksa peneliti. |
| `cosmolab uji jalan --semua-soal --batas 20` | Pakai semua soal, paling banyak 20 per jenis. |
| `cosmolab uji riwayat` | Bandingkan hasil uji sebelumnya. |

## 12. Ekspor, biaya, dan cadangan

| Perintah | Fungsi |
| --- | --- |
| `cosmolab export --format obsidian` | Ekspor koleksi ke catatan Obsidian. |
| `cosmolab export --format bibtex --out <file.bib>` | Ekspor ke BibTeX. |
| `cosmolab pustaka --format ris --out <file.ris>` | Daftar pustaka untuk Mendeley/Zotero, dari metadata yang sudah dicek. Format: `bib` (bawaan) atau `ris`. |
| `cosmolab usage` | Pemakaian token AI dan perkiraan biaya proyek aktif, per fitur. |
| `cosmolab usage --all --month 2026-11 --by model` | Semua proyek, bulan November 2026, dikelompokkan per model. `--by`: `feature`, `model`, atau `month`. |
| `cosmolab log` | 30 catatan audit terakhir. Ubah jumlahnya dengan `--n 100`. |
| `cosmolab log --csv audit.csv` | Simpan seluruh log audit ke CSV. |
| `cosmolab backup` | Cadangkan data proyek ke `backups/<proyek>_<waktu>.zip`. |
| `cosmolab backup --tanpa-pdf` | Cadangan tanpa PDF, ukurannya jauh lebih kecil. |
| `cosmolab backup --out <folder> --dengan-cache` | Simpan ke folder lain dan ikutkan cache AI. |

---

## Alur cepat untuk satu klien

Jalankan berurutan:

```bash
cosmolab project new 2026-11-klien-a --client "Nama Klien"
```

```bash
cosmolab -P 2026-11-klien-a harvest "project based learning critical thinking" --max-results 40
```

```bash
cosmolab -P 2026-11-klien-a harvest "pembelajaran berbasis proyek berpikir kritis" --indonesia
```

```bash
cosmolab -P 2026-11-klien-a analyze --lang id
```

```bash
cosmolab -P 2026-11-klien-a review draf_klien.docx --jenjang s1
```

```bash
cosmolab -P 2026-11-klien-a ui
```

Langkah terakhir membuka dashboard. Di sana konsultan memutuskan komentar review, lalu membuat Word berkop firma.

Opsi `--model` di banyak perintah memilih model AI. Kalau dikosongkan, model diambil dari `.env`.
