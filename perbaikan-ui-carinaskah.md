# Rencana Peningkatan Tampilan Antarmuka (UI/UX) "Cari di Naskah"
**CosmoLab Research Dashboard — Dokumen Spesifikasi Desain & Rencana Implementasi**

Dokumen ini merangkum perbaikan fondasi yang telah berhasil diselesaikan serta spesifikasi peningkatan desain tampilan (*UI/UX Improvements*) untuk fitur **Cari di Naskah** (Full-Text & Passage Search) pada tab Koleksi Paper CosmoLab.

---

## 1. Status & Fondasi yang Telah Diperbaiki

Sebelum peningkatan tampilan diimplementasikan, empat masalah kritis pada mesin pencarian telah berhasil diselesaikan dan terverifikasi penuh:

| Masalah Sebelumnya | Akar Masalah | Solusi yang Diterapkan | Status |
| :--- | :--- | :--- | :---: |
| **Bocor Tag Terminal Konsol** | FTS5 mengirim markup Rich `[b][yellow]` yang dicetak mentah di browser. | Otomatis dikonversi ke elemen `<mark>` HTML berlatar kuning lembut ber-radius 3px. | ✅ Selesai |
| **Kutipan Cadangan Palsu Halaman 1** | Paragraf pembuka Halaman 1 (alamat redaksi/kontak kampus) muncul jika tidak ada kecocokan kuat. | Filter ketat `not psg.get("fallback")` diterapkan sehingga hanya bukti otentik yang tampil. | ✅ Selesai |
| **Kata Ilmiah "Masalah" Terkunci** | Kata `"masalah"` masuk daftar `FILLER` di `passages.py`, membuang query bertema PBL / rumusan masalah. | Kata `"masalah"` dikeluarkan dari `FILLER` dan diakui sebagai topik substantif akademik. | ✅ Selesai |
| **Pencarian Terasa Lambat (5–10 detik)** | Checkbox ekspansi semantik AI aktif secara default, memanggil LLM pada setiap ketikan. | Pencarian teks instan (< 0.05 detik) dijadikan bawaan utama, opsi AI tetap opsional. | ✅ Selesai |

---

## 2. Spesifikasi Rencana Peningkatan Tampilan (UI/UX Improvements)

Untuk memberikan pengalaman riset yang setara dengan alat literatur kelas dunia (seperti Elicit, Consensus, atau Scite.ai), berikut 5 pilar peningkatan tampilan yang direncanakan:

### A. Kartu Hasil dengan Badge Visual Akademik
* **Nomor Urut Peringkat Relevansi (`#1`, `#2`, `#3`):**  
  Badge kontras di sudut kiri atas setiap kartu hasil untuk memperjelas urutan relevansi dokumen.
* **Badges Status & Jenis Penelitian Resmi CosmoLab:**  
  Mengintegrasikan komponen `paper_badges()`:
  - `📊 Kajian Empiris` (Kuantitatif / Kualitatif / Studi Kasus)
  - `🧠 Kajian Argumen` (Kalam / Kontingensi / Sebab Pertama / dsb.)
  - `⭐ SINTA 1–2 / SINTA 3–4` (Peringkat akreditasi jurnal nasional)
  - `✅ Mendukung` / `❌ Mengkritik` / `⚖️ Netral` (Sikap naskah terhadap topik)
* **Tautan Langsung DOI Eksternal:**  
  Jika paper memiliki DOI, sediakan tautan aktif berikon eksternal `[Lihat di Penerbit / DOI ↗](https://doi.org/...)`.

---

### B. Format Sitasi Cepat 1-Klik (*One-Click Academic Citation*)
Peneliti sering kali mencari naskah untuk langsung dikutip ke dalam draf karya tulis mereka. 
Fitur ini menambahkan panel sitasi instan menggunakan modul `cosmolab.citations`:
* **Sitasi Dalam Teks (In-Text APA):**
  > `(Priasti & Suyatno, 2021)`
* **Daftar Pustaka Lengkap (APA 7th Edition):**
  > `Priasti, S. N., & Suyatno. (2021). Penerapan Pendidikan Karakter Gemar Membaca Melalui Program Literasi di Sekolah Dasar. Jurnal Kependidikan, 7(2), 395-407. https://doi.org/10.33394/jk.v7i2.3552`
* **Fitur Salin Cepat:**  
  Menyediakan blok kode satu klik salin (*click-to-copy*) agar peneliti tidak perlu menyusun daftar pustaka secara manual.

---

### C. Desain Box Temuan Paragraf Naskah Modern (*Verified Passage Callout*)
Tampilan kutipan naskah asli diformat menjadi kotak *callout* riset yang elegan:
* **Garis Aksen Emas (*Amber Accent Border*):**  
  Border kiri tebal berwarna amber `#f59e0b` dengan latar abu-abu/kuning transparan lembut.
* **Label Lokasi Fisik Terverifikasi:**  
  Badge pin lokasi dokumen: `📍 Halaman 6` (memastikan nomor halaman fisik PDF, bukan sekadar urutan bab).
* **Penyorotan Kata Kunci Otomatis (*Dual Highlighting*):**  
  Kata kunci pencarian yang muncul di dalam kutipan naskah fisik otomatis tersorot `<mark>` kuning tajam sehingga mata peneliti langsung tertuju pada kalimat kunci.
* **Pembeda Konteks Tambahan:**  
  Jika kata kunci juga muncul di bagian bab lain dalam paper, sistem menyajikan cuplikan konteks sekunder di bawahnya.

---

### D. Tombol Lipat Bedah Riset (*Inline Methodology & Findings*)
* Peneliti tidak perlu berpindah bolak-balik antara tab *"Cari di Naskah"* dan tab *"Daftar Paper"*.
* Di bagian bawah setiap kartu hasil, disediakan ekspander lipat:  
  **`📖 Lihat Intisari Riset & Metodologi Lengkap`**
* Saat dibuka, ekspander akan menampilkan:
  1. **Tujuan Riset:** Rumusan masalah utama yang diteliti.
  2. **Metode & Sampel:** Desain penelitian, instrumen, dan subjek/populasi data.
  3. **Temuan Kunci (*Key Findings*):** Poin-poin hasil empiris atau premis argumen.
  4. **Keterbatasan & Saran:** Batasan studi untuk ide riset lanjutan.

---

### E. Statistik Pencarian & Indikator Cakupan (*Search Stats & Scoping Bar*)
* Di bagian atas daftar hasil, tampilkan bar ringkasan informatif:  
  `⚡ Ditemukan 2 paper yang memuat kata kunci "masalah" (Pencarian selesai dalam 0.03 detik)`
* Menampilkan pill status cakupan yang aktif:  
  `🏛️ Lingkup: Bidang Tarbiyah & Pendidikan` atau `🌐 Seluruh Koleksi Paper`.

---

## 3. Wireframe Perbandingan Visual (Sebelum vs Sesudah)

````carousel
### Tampilan Awal (Sebelum Perbaikan)
```text
[ Container ]
Judul Paper (2021)
Jenis penelitian: - · Bidang: umum
Inti paper: Paper membahas karakter.
Cuplikan: ...MODEL PEMBELAJARAN BERBASIS [b][yellow]MASALAH[/yellow][/b]...
📍 Halaman 1: "Al Qalam: Jurnal Ilmiah Keagamaan P-ISSN: 1907-4174..." (Kutipan palsu)
```
<!-- slide -->
### Tampilan Baru (Rencana Peningkatan Penuh)
```text
[ Container #1 ]
┌────────────────────────────────────────────────────────────────────────┐
│ #1  Pendidikan Karakter Sekolah Dasar Berbasis Qur'anic Habit (2023)    │
│ [📊 Kajian Empiris] [⭐ SINTA 2] [🏛️ Tarbiyah] [DOI ↗]                 │
│ ✍️ Penulis: Silvia Nur Priasti, Suyatno                                │
├────────────────────────────────────────────────────────────────────────┤
│ 💡 Inti Paper:                                                         │
│ Pendidikan karakter di Sekolah Alam dibangun melalui Qur'anic Habit... │
├────────────────────────────────────────────────────────────────────────┤
│ 📍 Temuan Otentik Naskah (Halaman 7):                                  │
│ "... penerapkan pendidikan <mark>karakter</mark> gemar membaca         │
│  melalui pembiasaan harian terbukti meningkatkan motivasi ..."         │
├────────────────────────────────────────────────────────────────────────┤
│ 📋 Sitasi Cepat (APA 7th):                                            │
│ Priasti, S. N., & Suyatno. (2023). Pendidikan Karakter... [Salin]      │
├────────────────────────────────────────────────────────────────────────┤
│ ▶ 📖 Lihat Intisari Riset, Sampel & Temuan Lengkap (Expander)         │
└────────────────────────────────────────────────────────────────────────┘
```
````

---

## 4. Rencana Teknis Modifikasi File

File yang akan dimodifikasi saat implementasi dijalankan:
1. **[cosmolab/ui/pages/fulltext.py](file:///d:/Cosmolab/cosmolab/cosmolab/ui/pages/fulltext.py):**
   - Menambahkan integrasi `paper_badges()` dari `cosmolab.ui.papers`.
   - Menambahkan pemanggil `format_apa()` dan `format_in_text_apa()` dari `cosmolab.citations`.
   - Menambahkan expander detail metodologi menggunakan komponen `render_analysis_detail()`.
   - Mengatur styling CSS card callout container.
2. **Backward Compatibility:**
   - Menjaga seluruh 240 unit test tetap 100% lulus.
   - Tidak ada ketergantungan paket eksternal baru (hanya memanfaatkan modul yang sudah ada di CosmoLab).

---
*Dokumen ini dibuat sebagai acuan desain antarmuka sebelum tahap pengkodean dijalankan.*
