# Panduan Komprehensif Arsitektur & Fitur CosmoLab

> **Klasifikasi Dokumen:** Buku Panduan Teknis & Operasional (Technical & Operational Manual)  
> **Sasaran Pengguna:** Peneliti, Konsultan Akademik, Dosen Pembimbing, dan Mahasiswa Pascasarjana  
> **Penyusun:** Tim Riset & Rekayasa Sistem CosmoLab  
> **Status Dokumen:** Rilis Resmi

---

## 1. Pendahuluan & Filosofi Sistem

CosmoLab dikembangkan bukan sekadar sebagai alat bantu penulisan (*writing assistant*) atau antarmuka obrolan AI biasa. CosmoLab adalah **sistem operasi riset terpadu (*end-to-end research platform*)** yang dirancang untuk mengotomatisasi pekerjaan mekanik riset literatur tanpa mengorbankan integritas akademik.

### 1.1 Masalah Pokok Riset Konvensional
1. **Fragmentasi Alat Kerja**: Peneliti harus berpindah-pindah antara Google Scholar (pencarian), Zotero/Mendeley (manajemen sitasi), PDF Viewer (pembacaan manual), Turnitin (uji kemiripan), ChatGPT/Claude (eksplorasi ide), dan Microsoft Word (penyusunan dokumen).
2. **Krisis Halusinasi AI Generatif**: Model bahasa besar (*LLM*) standar sering mengarang rujukan (*phantom citations*), memalsukan nomor halaman, atau mengaburkan perbedaan antara fakta empiris dan klaim spekulatif.
3. **Beban Pembacaan Manual Naskah Panjang**: Menelaah puluhan naskah setebal 20–300 halaman untuk menemukan metodologi riil, ukuran sampel, dan keterbatasan memerlukan ratusan jam kerja manusia.

### 1.2 Solusi CosmoLab
CosmoLab menyatukan seluruh tahapan tersebut ke dalam satu ekosistem tertutup yang diaudit ketat dengan prinsip **Human-in-the-Loop** dan **Strict Grounding** (jawaban wajib diverifikasi terhadap teks naskah fisik).

---

## 2. Peta Arsitektur Tiga Siklus Kerja

Alur kerja CosmoLab dibagi menjadi 3 siklus berurutan:

```
[ Siklus 1: Kumpulkan ] ───> [ Siklus 2: Pahami ] ───> [ Siklus 3: Hasil Klien ]
  • Panen 6 Sumber Repositori  • Ekstraksi C++ Layout-Aware   • Celah Riset & Kebaruan
  • Deteksi Jurnal SINTA 1-6   • Bedah Argumen Terstruktur   • Tinjauan Pustaka Naratif
  • Snowballing Sitasi         • Matriks Literatur Excel     • Review Draf Mahasiswa
  • Bedah DOI & Cek Retraksi   • Tanya Korpus Anti-Halusinasi • Defense Simulator
                               • Ekspor RIS / BibTeX         • Ekspor Word/PDF Berkop
```

---

## 3. Rincian Fitur: Siklus 1 · Kumpulkan (Harvesting & Discovery)

### 3.1 Pencarian & Panen Paper Ilmiah Federasi (*Federated Harvester*)
- **Fungsi Utama**: Mencari dan mengunduh artikel jurnal legal (*open-access*) dari jaringan repositori ilmiah internasional dan nasional dalam satu perintah.
- **Mekanisme Mesin**:
  - Mengirim kueri paralel ke 6 basis data: OpenAlex, Crossref, arXiv, CORE, DOAJ, dan Semantic Scholar.
  - Mengimplementasikan algoritma deduplikasi judul naskah berbasis normalisasi teks dan jarak Levenshtein.
  - Mengotomatisasi penelusuran tautan unduhan PDF legal melalui integrasi API Unpaywall.
- **Mode Khusus Jurnal Indonesia (SINTA Tagging)**:
  - Menyaring publikasi nasional terindeks Garuda/OpenAlex.
  - Memetakan ISSN naskah ke basis data akreditasi nasional untuk melabeli akreditasi **SINTA 1 hingga SINTA 6** secara otomatis.
- **Luaran Konkret**: Naskah PDF tersimpan rapi di direktori proyek lokal lengkap dengan berkas metadata bibliografis terstruktur (`metadata.jsonl`).

### 3.2 Bedah DOI Instan (*DOI Quick Inspector*)
- **Fungsi Utama**: Menarik naskah, memeriksa kredibilitas, dan mengekstrak poin inti sebuah paper hanya dengan memasukkan pengenal digital (*Digital Object Identifier*).
- **Mekanisme Mesin**:
  - Mengakses registri resmi Crossref dan DataCite untuk mengambil metadata kanonikal.
  - Melakukan audit status pencabutan naskah (*retraction status check*) guna mencegah penggunaan pustaka yang telah didiskualifikasi secara akademik.
- **Luaran Konkret**: Naskah PDF otomatis diunduh dan ringkasan eksekutif instan ditampilkan.

### 3.3 Pelacak Jejaring Sitasi (*Citation Snowballing Engine*)
- **Fungsi Utama**: Mengembangkan korpus literatur secara cerdas melalui pemetaan graf sitasi dua arah dari satu naskah kunci (*seminal paper*).
- **Mekanisme Mesin**:
  - **Backward Snowballing**: Menelusuri seluruh daftar rujukan yang dikutip oleh naskah target untuk menemukan akar fondasi teoretis.
  - **Forward Snowballing**: Menelusuri seluruh publikasi baru yang mengutip naskah target di tahun-tahun berikutnya untuk memetakan perkembangan riset mutakhir.
- **Luaran Konkret**: Rekomendasi naskah yang terbukti relevan secara saintifik tanpa perlu menebak kata kunci pencarian baru.

---

## 4. Rincian Fitur: Siklus 2 · Pahami (Deep Understanding & Grounding)

### 4.1 Ekstraksi Naskah Sadar Tata Letak (*Layout-Aware PDF Engine*)
- **Fungsi Utama**: Mengekstrak teks digital dari PDF dengan mempertahankan urutan baca logis pada format multi-kolom serta menapis elemen pengganggu.
- **Mekanisme Mesin**:
  - Menggunakan engine berkinerja tinggi C++ (PyMuPDF) yang mampu memproses ratusan halaman naskah dalam hitungan detik.
  - Menghapus otomatis header, footer kampus, dan nomor halaman running yang merusak keutuhan kalimat.
  - Menyematkan penanda halaman fisik kanonikal: `--- [Halaman X] ---` untuk mendukung audit rujukan hingga ke tingkat halaman.
- **Luaran Konkret**: Berkas teks bersih yang terstruktur dan siap diproses oleh modul pemahaman bahasa alami.

### 4.2 Bedah Argumen Terstruktur (*Structured Paper Decomposition*)
- **Fungsi Utama**: Membaca naskah secara komprehensif dan mengekstrak komponen riset secara sistematis ke dalam skema Pydantic tervalidasi.
- **Komponen Ekstraksi**:
  1. *Tesis Utama*: Pernyataan sentral atau argumen inti penulis.
  2. *Rumusan Masalah Riil*: Pertanyaan penelitian spesifik yang dijawab.
  3. *Pendekatan Metodologis*: Klasifikasi metode konkret (misal: eksperimental, kuasi-eksperimen, yuridis normatif, regresi panel).
  4. *Populasi & Sampel Data*: Objek empiris, ukuran sampel, dan konteks pengujian.
  5. *Premis & Alur Silogisme*: Rantai argumen logis penulis.
  6. *Temuan Inti Bab Pembahasan*: Data substantif hasil analisis (bukan ringkasan abstrak).
  7. *Kutipan Langsung (Verbatim)*: Bukti tekstual beserta indikasi bab naskah.
  8. *Keterbatasan yang Diakui*: Kelemahan yang dinyatakan secara jujur oleh penulis.
  9. *Saran Riset Lanjutan*: Rekomendasi eksplisit untuk penelitian di masa depan.
- **Luaran Konkret**: Kartu profil naskah terstandarisasi yang dapat ditelaah dan diedit manual oleh peneliti.

### 4.3 Matriks Literatur Komparatif (*Synthesis Matrix*)
- **Fungsi Utama**: Mengompilasi seluruh paper yang telah dibedah ke dalam satu tabel matriks komparatif lintas variabel.
- **Mekanisme Mesin**: Memetakan data terstruktur dari basis data relasional lokal ke dalam bentuk tabel matriks multi-kolom.
- **Luaran Konkret**: Lembar kerja analitis yang dapat diunduh dalam format **CSV/Excel**, berfungsi sebagai fondasi utama penulisan Bab 2 skripsi/tesis/disertasi.

### 4.4 Tanya Koleksi & RAG Terverifikasi (*Grounded Corpus Q&A*)
- **Fungsi Utama**: Asisten konsultasi interaktif yang menjawab pertanyaan peneliti berdasarkan seluruh paper di dalam korpus tanpa risiko halusinasi.
- **Mekanisme Mesin**:
  - **Pencarian Hibrida**: Mengombinasikan BM25 (pencocokan leksikal SQLite FTS5), model representasi vektor rapat (*dense embeddings*), dan *LLM Cross-Encoder Reranking*.
  - **Entailment Gatekeeper**: Setiap kalimat jawaban diuji secara independen terhadap kutipan naskah fisik menggunakan model pemeriksa terpisah (*Judge Model*).
- **Luaran Konkret**: Jawaban analitis yang dilengkapi sitasi presisi hingga nomor halaman naskah fisik (misal: `[Nama Paper, Hlm. 12-14]`).

### 4.5 Ekspor Manajemen Referensi (*Reference Manager Integration*)
- **Fungsi Utama**: Menghasilkan berkas pustaka siap impor untuk perangkat lunak sitasi standar industri.
- **Luaran Konkret**:
  - Berkas **`references.ris`**: Kompatibel langsung dengan **Zotero, Mendeley, dan EndNote**.
  - Berkas **`references.bib`**: Siap digunakan untuk kompilasi dokumen **LaTeX / Overleaf**.

---

## 5. Rincian Fitur: Siklus 3 · Hasil untuk Klien (Executive Deliverables)

### 5.1 Pendeteksi Celah Riset & Kebaruan (*Research Gap & Novelty Finder*)
- **Fungsi Utama**: Mengaudit seluruh korpus naskah untuk menemukan kebuntuan teoretis, keterbatasan metodologi, dan merumuskan usulan penelitian baru bernilai jual tinggi.
- **Struktur Dokumen Analisis**:
  1. *Ringkasan Eksekutif (State of the Art)*: Tinjauan padat tentang krisis paradigma terkini.
  2. *Peta Konsensus Mapan*: Temuan-temuan yang telah disepakati oleh literatur internasional.
  3. *Matriks Perdebatan Terbuka (Unresolved Dialectical Tensions)*: Perbandingan kubu teori dominan (tesis) melawan kubu kritik empiris baru (antitesis), disertai analisis akar kebuntuan resolusi.
  4. *Evaluasi Titik Buta Metodologis (Blindspots)*: Keterbatasan sistemik yang diabaikan oleh peneliti-peneliti terdahulu.
  5. *Cetak Biru Proposal Riset Baru*: Tiga paket usulan riset orisinal lengkap dengan tabel spesifikasi (Target Jenjang S2/S3/Scopus, Celah Pustaka, Hipotesis Kerja, Landasan Teori, Rumusan Masalah, dan Nilai Kebaruan).
- **Luaran Konkret**: Dokumen cetak biru penelitian yang siap dipresentasikan kepada promotor atau dewan riset.

### 5.2 Tinjauan Pustaka Naratif (*State-of-the-Art Review Synthesizer*)
- **Fungsi Utama**: Menyusun esai akademik terpadu yang merajut dialektika antar-penulis menjadi draf narasi bab kajian pustaka yang utuh.
- **Mekanisme Mesin**: Mengelompokkan literatur berdasarkan kesamaan tema, memperhadapkan perbedaan temuan, dan memastikan setiap klaim memiliki rujukan yang terverifikasi.
- **Luaran Konkret**: Naskah tinjauan pustaka naratif siap pakai untuk draf Bab 2 naskah akademik.

### 5.3 Review Draf Mahasiswa (*Student Draft Reviewer*)
- **Fungsi Utama**: Bertindak sebagai tim dosen pembimbing independen yang mengoreksi naskah mahasiswa paragraf demi paragraf.
- **Mekanisme Mesin**:
  - Membaca naskah format Word (`.docx`) atau Markdown.
  - Membagi naskah ke dalam batch paragraf terkelola (12.000 karakter per batch) untuk memastikan ketelitian ulasan.
  - Memberikan komentar terperinci mengenai kelogisan kalimat, validitas klaim data, dan kelengkapan rujukan.
  - **Prinsip Human-in-the-Loop**: Konsultan dapat memilih opsi *Terima*, *Edit*, atau *Buang* pada setiap catatan AI sebelum dokumen diekspor.
- **Luaran Konkret**: Laporan tinjauan evaluatif berformat Word (.docx) berkop resmi yang berisi komentar inline terstruktur.

### 5.4 Cek Kemiripan Pra-Submit (*Pre-Submission Similarity Check*)
- **Fungsi Utama**: Mendeteksi dini potensi plagiarisme atau parafrasa yang terlalu dekat dengan literatur sebelum naskah diuji pada sistem anti-plagiarisme institusi.
- **Mekanisme Mesin**: Membandingkan setiap kalimat draf terhadap teks lengkap korpus naskah lokal serta abstrak rujukan yang dikutip.
- **Luaran Konkret**: Indikasi kalimat bermasalah (tanpa sitasi, sitasi keliru, atau kemiripan leksikal tinggi) sehingga mahasiswa dapat melakukan parafrasa ulang secara mandiri.

### 5.5 Simulator Latihan Sidang (*Defense Simulator & Sparring AI*)
- **Fungsi Utama**: Melatih kesiapan mental dan argumentasi mahasiswa sebelum menghadapi sidang proposal, tesis, atau disertasi terbuka.
- **Mekanisme Mesin**:
  - AI mengambil persona Dewan Penguji Ujian Pascasarjana (Ketua Sidang, Penguji Ahli Metodologi, dan Penguji Teori).
  - Sistem mendeteksi titik rawan dalam naskah mahasiswa (kelemahan metodologi, ambiguitas operasional, generalisasi berlebihan) dan mengajukan pertanyaan-pertanyaan kritis yang menantang.
- **Luaran Konkret**: Sesi simulasi tanya jawab dialektis interaktif dengan catatan evaluasi performa pertahanan naskah.

### 5.6 Pembuat Dokumen Berkop Resmi (*Executive Client Deliverables*)
- **Fungsi Utama**: Mengompilasi laporan analisis ke dalam dokumen formal Microsoft Word (`.docx`) dan Adobe PDF (`.pdf`) berstandar firma konsultan internasional.
- **Standar Format Dokumen**:
  - Halaman sampul eksekutif (*executive cover page*) dengan logo firma, identitas klien, kode proyek, tanggal terbit, dan nama penelaah resmi.
  - Tipografi formal berpalet *Navy-Slate* (`#1E3A8A` / `#0F172A`) dengan spasi proporsional dan penomoran halaman otomatis.
  - Penyajian data celah riset dalam bentuk tabel matriks spesifikasi terstruktur.
  - Lembar pengesahan transparansi (*disclosure statement*) yang menegaskan bahwa naskah telah diaudit oleh peneliti manusia.
  - **Pembersihan Bersih**: Bebas total dari karakter informal (*AI slop*), emoji percakapan, atau identitas teknis model LLM.

---

## 6. Tabel Matriks Ringkasan Fitur CosmoLab

| Modul Fitur | Siklus | Format Masukan | Format Luaran | Pemanfaatan Utama |
| :--- | :--- | :--- | :--- | :--- |
| **Panen Paper Federasi** | Kumpulkan | Kata kunci / Topik | PDF & Metadata | Mengumpulkan korpus riset legal otomatis |
| **Bedah DOI Instan** | Kumpulkan | Nomor DOI / URL | PDF & Ringkasan | Verifikasi cepat dan unduh paper spesifik |
| **Citation Snowballing** | Kumpulkan | ID Paper Kunci | Daftar Paper Terkait | Menemukan jejaring literatur yang terlewat |
| **Ekstraksi Sadar Tata Letak** | Pahami | PDF Naskah | Teks & Marker Hlm | Menyiapkan data bersih untuk analisis |
| **Bedah Naskah Otomatis** | Pahami | Teks Naskah | JSON Variabel Riset | Ekstraksi metode, sampel, premis, limitasi |
| **Matriks Literatur** | Pahami | Korpus Naskah | Tabel CSV / Excel | Sintesis komparatif variabel untuk Bab 2 |
| **Tanya Koleksi (RAG)** | Pahami | Pertanyaan Peneliti | Jawaban + Halaman | Tanya jawab anti-halusinasi terverifikasi |
| **Manajemen Referensi** | Pahami | Metadata Korpus | `.ris` & `.bib` | Impor 1-klik ke Zotero/Mendeley/LaTeX |
| **Celah Riset & Kebaruan** | Hasil Klien | Korpus Naskah | Word, PDF, Markdown | Cetak biru proposal tesis/disertasi/Scopus |
| **Tinjauan Pustaka Naratif** | Hasil Klien | Korpus Naskah | Markdown & Word | Esai naratif bab telaah pustaka |
| **Review Draf Mahasiswa** | Hasil Klien | Word (.docx) / MD | Word Berkomentar | Bimbingan koreksi naskah per paragraf |
| **Cek Kemiripan Pra-Submit** | Hasil Klien | Word (.docx) / MD | Laporan Indikasi | Pra-skrining plagiarisme & parafrasa |
| **Simulator Latihan Sidang** | Hasil Klien | Draf Naskah | Sesi Ujian Interaktif | Simulasi tanya jawab dewan penguji |
| **Dokumen Klien Berkop** | Hasil Klien | Markdown Analisis | Word (.docx) & PDF | Laporan resmi siap kirim ke klien |

---

## 7. Penutup & Integritas Ilmiah

CosmoLab dibangun di atas komitmen etik yang tegas: **membantu proses berpikir dan mempercepat penelusuran pustaka, bukan menggantikan integritas peneliti**. Seluruh sistem dirancang agar peneliti memegang kendali penuh atas verifikasi naskah, memastikan tidak ada klaim fiktif yang lolos, dan menghasilkan karya akademik yang dapat dipertanggungjawabkan di hadapan dewan penguji universitas maupun komunitas ilmiah global.
