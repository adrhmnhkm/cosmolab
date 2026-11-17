# Laporan Progres Pengembangan CosmoLab

*Tanggal: 16 November 2026*  
*Cabang (Branch): `master` → `origin/main`*

---

## 1. Ringkasan Aktivitas Terakhir

Pada sesi kerja ini, fokus utama adalah:
1. Menyelamatkan dan merapikan perubahan tertunda di working directory ke dalam commit resmi dan mendorong (*push*) ke remote repository.
2. Melakukan audit komprehensif terhadap 35 fitur aplikasi untuk mengidentifikasi fitur yang stabil, memerlukan perbaikan minor, dan prioritas perbaikan anti-halusinasi (P0 dan P1).
3. Menyelesaikan gap pada paket perbaikan anti-halusinasi **P0-6** pada evaluasi akurasi.
4. Menerapkan perbaikan **P1-6** pada prompt ekstraksi analisis untuk menghentikan halusinasi nomor halaman dan pemaksaan jumlah premis.

---

## 2. Rincian Pekerjaan & Commit

### A. Commit & Push Perubahan Tertunda
* **Commit:** `641cc9e` — *Verify AI quotes against the PDF before saving*
* **Deskripsi:** Menjamin bahwa setiap kutipan (*verbatim quote*) yang dihasilkan AI diverifikasi langsung terhadap teks fisik PDF sebelum analisis disimpan ke disk. Kutipan yang tidak ditemukan dipisahkan ke `quotes_rejected` agar tidak mencemari jawaban RAG atau ekspor dokumen.
* **File Terkait:**
  - [cosmolab/analysis_check.py](file:///d:/Cosmolab/cosmolab/cosmolab/analysis_check.py): Fungsi `verify_quotes()` dan format ringkasan status kutipan.
  - [cosmolab/analyze.py](file:///d:/Cosmolab/cosmolab/cosmolab/analyze.py): Integrasi `_check_quotes()` sebelum penulisan JSON analisis.
  - [cosmolab/ask_agent.py](file:///d:/Cosmolab/cosmolab/cosmolab/ask_agent.py): Menampilkan nomor halaman PDF hasil verifikasi aktual (bukan tebakan AI).
  - [cosmolab/ui/papers.py](file:///d:/Cosmolab/cosmolab/cosmolab/ui/papers.py): Badge verifikasi kutipan di UI dan expander kutipan yang dibuang.
  - [cosmolab/ui/progress.py](file:///d:/Cosmolab/cosmolab/cosmolab/ui/progress.py): Pelaporan proses verifikasi kutipan secara langsung di UI progress box.
  - [tests/test_accuracy_suite.py](file:///d:/Cosmolab/cosmolab/tests/test_accuracy_suite.py): Unit test verifikasi kutipan.
* **Sinkronisasi Remote:** Berhasil mendorong 3 commit akumulatif (`54ba603`, `1540702`, dan `641cc9e`) ke `origin/main`.

---

### B. Audit Fitur Aplikasi CosmoLab
Dilakukan audit menyeluruh terhadap seluruh arsitektur dan modul (35 fitur), mengelompokkan kesehatan sistem:
* **Stabil (17 fitur):** Panen federasi, snowballing, koreksi peneliti, Word/PDF berkop firma, log audit, sistem manajemen proyek, dsb.
* **Minor / Butuh Pengujian UI (9 fitur):** Peringkat SINTA di browser, diagram argumen, matriks literatur, kelengkapan pembanding kemiripan.
* **Perlu Perbaikan Anti-Halusinasi (9 fitur):** Jalur Tanya Agentic, gerbang pemeriksa klaim (`entail`), inspeksi DOI tanpa abstrak, prompt analisis, dan metrik evaluasi.

---

### C. Penyelesaian P0-6: Non-Circular Evaluation
* **Commit:** `a08e8f3` — *Judge eval claims against PDF text only, not AI summary (P0-6)*
* **Masalah:** Pada [cosmolab/evaluate.py](file:///d:/Cosmolab/cosmolab/cosmolab/evaluate.py), pemanggilan fungsi `entail.check_claims` tidak menyertakan parameter `use_analysis=False`. Akibatnya, LLM judge mengevaluasi klaim emas (*gold claims*) menggunakan tesis dan kesimpulan hasil analisis AI itu sendiri (penilaian melingkar/sirkular).
* **Solusi:** Menambahkan `use_analysis=False` secara eksplisit agar evaluasi akurasi benar-benar menguji pencocokan terhadap teks asli paper (verbatim).
* **Hasil Pengujian:** 27/27 unit test lulus di `tests/test_accuracy_suite.py` dan `tests/test_entail.py`.

---

### D. Penerapan P1-6: Anti-Tebakan pada Prompt Analisis
* **Commit:** `836621f` — *Stop guessing page numbers and forcing premise count in analyze prompts (P1-6)*
* **Masalah:** Prompt [cosmolab/analyze.py](file:///d:/Cosmolab/cosmolab/cosmolab/analyze.py) (`PROMPT_EN` dan `PROMPT_ID`) sebelumnya menginstruksikan LLM untuk mengestimasi nomor halaman (misal: `"hlm. 232"`) dan memaksakan rumusan 4–7 premis logis meskipun naskah bersifat murni deskriptif/empiris tanpa silogisme formal. Hal ini menyebabkan fabrikasi angka halaman dan premis semu.
* **Solusi:**
  1. `page_hint`: Diperbarui menjadi nama bab saja (misal: "Hasil dan Pembahasan"). Dilarang keras menebak nomor halaman.
  2. `premises`: Hanya mendaftar premis yang secara eksplisit dinyatakan atau tersirat langsung; maksimal 7; kembalikan daftar kosong (`[]`) jika paper tidak memiliki argumen silogistik terstruktur.
* **Hasil Pengujian:** 21 lulus, 1 dilewati (local data requirement) pada `tests/test_accuracy_suite.py`, `tests/test_pipeline.py`, dan `tests/test_lit_fields.py`.

---

### E. Penerapan P1-4: Deteksi & Penandaan Kalimat Faktual Tanpa Sitasi
* **Commit:** `608f0d4` — *Tag factual sentences without citations as tanpa_sitasi (P1-4)*
* **Masalah:** Pada [cosmolab/entail.py](file:///d:/Cosmolab/cosmolab/cosmolab/entail.py), fungsi `split_claims` sebelumnya langsung mengabaikan kalimat yang tidak memiliki sitasi (`if not cites: continue`). Akibatnya, kalimat faktual liar/halusinasi tanpa sitasi lolos dari evaluasi gatekeeper tanpa peringatan.
* **Solusi:**
  1. Menambahkan verdict baru `NO_CITATION = "tanpa_sitasi"` beserta label dan integrasi ke `needs_attention` serta `BLOCKING`.
  2. Memperbarui `split_claims` untuk menangkap kalimat faktual tanpa sitasi (`citations: []`), mengecualikan `Catatan analis:` (opini analis yang sah), pesan abstain korpus, dan kalimat navigasi/tautan semata.
  3. Memproses verdict `tanpa_sitasi` secara instan tanpa biaya LLM (0 LLM call).
  4. Menyelaraskan tampilan badge pada [cosmolab/ui/claims.py](file:///d:/Cosmolab/cosmolab/cosmolab/ui/claims.py) dan styling CLI pada [cosmolab/cli.py](file:///d:/Cosmolab/cosmolab/cosmolab/cli.py).
* **Hasil Pengujian:** 35/35 unit test lulus di `tests/test_entail.py` dan `tests/test_retrieval_accuracy.py`.

---

### F. Penerapan P1-9: Sintesis Literatur dengan Bukti Verbatim & Audit Klaim Otomatis
* **Commit:** `72394d9` — *Include verbatim passages and auto-check claims in synthesis reports (P1-9)*
* **Masalah:** Pada [cosmolab/synthesize.py](file:///d:/Cosmolab/cosmolab/cosmolab/synthesize.py), payload yang dikirim ke LLM sebelumnya hanya berisi ringkasan JSON hasil analisis AI tanpa passage/teks fisik PDF sama sekali. Prompt juga hanya menyuruh sitasi informal `judul (tahun)`, tanpa verifikasi otomatis terhadap isi laporan yang dihasilkan.
* **Solusi:**
  1. Menyertakan 1-2 passage/kutipan verbatim beserta nomor halaman PDF per paper ke dalam payload LLM (`verbatim_passages`).
  2. Memperbarui prompt sintesis (`SYNTH_PROMPT_EN` & `SYNTH_PROMPT_ID`) dengan aturan sitasi per kalimat faktual `[Judul (Tahun), Hal. X]` dan klausul `Catatan analis:` untuk komentar sintesis.
  3. Menjalankan gerbang audit klaim `entail.check_answer` secara otomatis pada laporan sintesis dan menyematkan bagian ringkasan audit akurasi ke dalam berkas markdown yang disimpan.
  4. Menyelaraskan umpan balik di antarmuka [cosmolab/ui/pages/synthesis.py](file:///d:/Cosmolab/cosmolab/cosmolab/ui/pages/synthesis.py) untuk menampilkan peringatan bila ada klaim yang perlu dicek.
* **Hasil Pengujian:** Unit test baru di [tests/test_synthesize.py](file:///d:/Cosmolab/cosmolab/tests/test_synthesize.py) lulus 100%.

---


---

### G. Perbaikan Kompatibilitas CI Linux (Commit 4bd0d43)
* **Commit:** `4bd0d43` — *Normalize Windows backslashes in home recents for Linux compatibility*
* **Masalah:** Uji GitHub Actions pada runner Ubuntu (`pytest (3.10)` & `pytest (3.12)`) gagal karena `tests/test_home.py` menguji path Windows (`C:\tmp\tesis_adi.docx`). Pada Linux, `pathlib.Path` adalah `PosixPath` yang tidak memperlakukan backslash `\` sebagai pemisah direktori, sehingga `.name` mengembalikan seluruh string path.
* **Solusi:** Normalisasi path dengan `.replace('\\', '/')` sebelum membaca atribut `.name` di `cosmolab/home.py`. Runner CI GitHub Actions kini 100% hijau (*green*).

---

### H. Penerapan P1-8: Perluasan Evaluasi & Benchmark Akurasi
* **Deskripsi:** Memperluas kerangka kerja evaluasi [cosmolab/evaluate.py](file:///d:/Cosmolab/cosmolab/cosmolab/evaluate.py), [cosmolab/cli.py](file:///d:/Cosmolab/cosmolab/cosmolab/cli.py), dan antarmuka akurasi [cosmolab/ui/pages/accuracy.py](file:///d:/Cosmolab/cosmolab/cosmolab/ui/pages/accuracy.py):
  1. **Skenario Uji `abstain`:** Menambahkan tipe soal `abstain` untuk menguji apakah jalur tanya jawab menolak menjawab pertanyaan di luar korpus secara eksplisit ("tidak ditemukan"). Menghitung metrik `abstain_rate` untuk jalur klasik maupun agentic.
  2. **Skenario Uji End-to-End `ask`:** Menambahkan tipe soal `ask` untuk mengeksekusi pertanyaan secara end-to-end pada jalur klasik (`ask.ask`) dan agentic (`ask_agent.ask_agentic`), lalu mengaudit jawaban yang dihasilkan secara otomatis menggunakan `entail.check_answer`. Menghitung rasio klaim yang didukung (*grounded_ratio*), klaim bermasalah (*attention_claims*), dan klaim tanpa rujukan (*uncited_claims*).
  3. **Pemisahan Model Pembuat Draf Soal (`DRAFT_MODEL`):** Menambahkan konfigurasi `DRAFT_MODEL` di [cosmolab/config.py](file:///d:/Cosmolab/cosmolab/cosmolab/config.py) agar pembuatan draf soal uji terpisah dari `JUDGE_MODEL`, serta memberikan peringatan jika model pembuat draf dan model penilai identik untuk mencegah bias evaluasi.
* **Hasil Pengujian:** 16/16 unit test lulus di `tests/test_accuracy_suite.py`, 240/240 lulus di seluruh rangkaian pengujian.

## 3. Matriks Status Anti-Halusinasi (P0 & P1)

| Kode | Area | Target Masalah | Status |
|:---:|---|---|:---:|
| **P0-1** | `ask_agent.py` | Hapus izin LLM mengisi jawaban dari pengetahuan luar | ✅ Selesai |
| **P0-2** | `ask.py`, `ask_agent.py` | Wajibkan sitasi + nomor halaman per kalimat faktual | ✅ Selesai |
| **P0-3** | `ask.py` | Hentikan fallback ke paper acak jika pencarian 0 hasil | ✅ Selesai |
| **P0-4** | `ask_agent.py` | Batasi pasangan dialektis hanya jika jenis argumen valid | ✅ Selesai |
| **P0-5** | `ask_agent.py` | Jangan jadikan passage fallback (abstrak awal) sebagai bukti | ✅ Selesai |
| **P0-6** | `evaluate.py` | Evaluasi klaim murni ke teks PDF, bukan ringkasan AI | ✅ Selesai |
| **P0-7** | `ask_agent.py` | Beri label jujur pada prompt: ringkasan AI belum tentu terverifikasi | ✅ Selesai |
| **P0-8** | `ask_agent.py` | Hapus fallback model hardcoded dan penalaran mentah sebagai jawaban | ✅ Selesai |
| **P0-9** | `inspector.py` | Tanpa abstrak: jangan lakukan inferensi analitik/mengarang | ✅ Selesai |
| **P0-10**| Semua file LLM | Pasang parameter `timeout` di seluruh pemanggilan LLM | ✅ Selesai |
| **P0-11**| `cli.py` | Default perintah `uji jalan` hanya mengevaluasi soal yang sudah direview | ✅ Selesai |
| **P1-1** | `deliverables.py` | Gerbang blokir pembuatan berkas jika terdapat klaim tidak didukung | ✅ Selesai |
| **P1-2** | `config.py`, `entail.py` | Penggunaan `JUDGE_MODEL` terpisah untuk audit klaim | ✅ Selesai |
| **P1-5** | `analyze.py`, `analysis_check.py` | Verifikasi otomatis kutipan AI ke PDF saat analisis | ✅ Selesai |
| **P1-6** | `analyze.py` | Prompt analisis tidak memaksa premis & tidak menebak halaman | ✅ Selesai |
| **P1-7** | `retrieval.py` | Cache LLM pada perankingan ulang paper (`rerank_papers`) | ✅ Selesai |
| **P1-4** | `entail.py` | Penandaan kalimat faktual tanpa sitasi (`tanpa_sitasi`) | ✅ Selesai |
| **P1-9** | `synthesize.py` | Penambahan bukti verbatim & cek klaim otomatis pada sintesis | ✅ Selesai |
| **P1-8** | `evaluate.py` | Penambahan skenario uji abstain, end-to-end `ask`, dan pemisahan `DRAFT_MODEL` | ✅ Selesai |

---

## 4. Rencana Langkah Berikutnya

1. **P2 (Optimalisasi Lanjutan):**
   - **P2-1:** Integrasi dense embedding default aktif (misal `bge-m3`).
   - **P2-2:** Penyesuaian bobot per bagian dokumen (Methods/Results > Intro > References).
   - **P2-3:** Evaluasi cross-encoder rerank lokal.
2. **Sinkronisasi Git Remote:**
   - Melakukan commit dan push pembaruan P1-8 ke `origin/main`.
