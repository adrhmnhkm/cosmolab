# LAPORAN FITUR TERBARU: ADVANCED RETRIEVAL ENGINE COSMOLAB
**Peningkatan Sistem: Similarity Search, Field Weighting, dan Micro Re-ranking**
*Tanggal Rilis: November 2026*

---

## 1. Latar Belakang & Masalah yang Diselesaikan

Sebelum pembaruan ini, modul pencarian dan RAG di CosmoLab hanya mengandalkan SQLite FTS5 murni (*unweighted keyword prefix match*). Hal tersebut memunculkan tiga kendala utama dalam riset akademik:

1. **Vocabulary & Language Mismatch:**
   Pertanyaan berbahasa Indonesia (contoh: *"apakah alam semesta punya awal mula"*) tidak menghasilkan kecocokan (*0 match*) karena korpus literatur mayoritas berbahasa Inggris. Sistem akhirnya melakukan *fallback* acak ke 5 paper pertama di database (yang sering kali tidak relevan, misalnya paper etika/hukum mahasiswa).
2. **Fenomena "Name-Dropping" & Unweighted Fields:**
   Paper tebal (30–50 halaman) yang sekadar menyebut kata *"kalam"* di catatan kaki mendapatkan skor BM25 lebih tinggi daripada paper pendek yang tesis dan premis formalnya benar-benar membongkar argumen Kalam.
3. **Ketiadaan Re-ranking Silogisme:**
   LLM sering disuapi dokumen dalam jumlah banyak tanpa penyaringan kecocokan premis, menyebabkan pemborosan token dan risiko halusinasi (*Lost in the Middle*).

---

## 2. Arsitektur & Tiga Pilar Solusi

Pembaruan ini menambahkan mesin **Hybrid Retrieval & Re-ranking Pipeline** dengan arsitektur dua tahap (*Two-Stage Retrieval*):

```
                       [ Input Query Peneliti ]
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
[ Exact Keyword Match ]                        [ Concept Expansion ]
  - Filter Stopwords                             - Peta konsep Turats & Analitik
  - Weighted FTS5 BM25                           - Ekstraksi terminologi Inggris
         │                                                 │
  (Top 15 Kandidat)                                 (Top 15 Kandidat)
         │                                                 │
         └────────────────────────┬────────────────────────┘
                                  ▼
                [ Reciprocal Rank Fusion (RRF) ]
                  Peleburan skor peringkat silang
                                  │
                          (Top 10 Kandidat)
                                  │
                                  ▼
                  [ Micro Cross-Attention Re-ranker ]
                    Evaluasi tesis & premis formal
                                  │
                          (Top 3-5 Terpilih)
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
  [ cosmolab ask / agent ]                          [ cosmolab search ]
  Sintesis Dialektis Padat                         Hasil Tabel CLI & Web UI
```

### A. Pilar 1: Field Weighting & Stopwords Filtering (SQLite FTS5)
Skor BM25 kini tidak lagi seragam, melainkan diberi bobot bertingkat sesuai hierarki nilai epistemik:
* **`title` (Bobot: `10.0`)**: Judul mencerminkan fokus utama paper.
* **`thesis` (Bobot: `10.0`)**: Tesis hasil ekstraksi analisis Pydantic.
* **`premises` (Bobot: `8.0`)**: Silogisme formal dan proposisi logis.
* **`abstract` (Bobot: `5.0`)**: Ringkasan argumen utama.
* **`argument_type` (Bobot: `3.0`)**: Klasifikasi disiplin/argumen.
* **`full_text` (Bobot: `1.0`)**: Menghindari bias pada paper tebal.
* **Stopwords Filtering:** Kata tanya dan kata sambung fungsional (*apakah, bagaimana, punya, untuk, what, does, is, etc.*) otomatis dibersihkan agar tidak mendistorsi operator pencarian prefix FTS5.

### B. Pilar 2: Semantic Concept Expansion & Reciprocal Rank Fusion (RRF)
* **Academic Concept Expansion:** Pertanyaan user diperkaya secara konseptual ke dalam istilah jurnal internasional (*contoh: "tak terhingga aktual" ➔ "actual infinite", "cantorian set theory", "hilbert hotel"*).
* **RRF Scoring:** Menggabungkan daftar kandidat harfiah dan konseptual tanpa distorsi skala:
  $$\text{RRF Score}(d) = \frac{1}{60 + \text{Rank}_{\text{raw}}(d)} + \frac{1.2}{60 + \text{Rank}_{\text{expanded}}(d)}$$

### C. Pilar 3: Micro Cross-Attention Re-ranking
* Memanfaatkan model evaluasi cerdas dengan *prompt* micro cross-attention untuk menilai 10 kandidat teratas berdasarkan kecocokan langsung antara pertanyaan dengan `thesis` dan `premises_json`.
* Menyeleksi hanya **3–5 paper yang paling esensial**, sehingga konteks LLM hemat token, cepat, dan tajam.

---

## 3. Rincian Modul yang Diperbarui

| Modul | Status | Deskripsi Perubahan |
| :--- | :---: | :--- |
| [`cosmolab/retrieval.py`](file:///d:/Cosmolab/cosmolab/cosmolab/retrieval.py) | **BARU** | Mesin utama: `expand_academic_query()`, `hybrid_search()`, dan `rerank_papers()`. Dilengkapi *heuristic domain map fallback* (0 latency). |
| [`cosmolab/db.py`](file:///d:/Cosmolab/cosmolab/cosmolab/db.py) | **UPDATED** | Implementasi bobot kolom `bm25(papers_fts, 0.0, 10.0, 5.0, 1.0, 10.0, 3.0, 8.0)` dan penyaringan `STOP_WORDS`. |
| [`cosmolab/cli.py`](file:///d:/Cosmolab/cosmolab/cosmolab/cli.py) | **UPDATED** | Perintah `cosmolab search` kini default memakai mode `--hybrid` (RRF Semantic), dengan opsi `--exact` untuk pencarian FTS5 harfiah. |
| [`cosmolab/ask.py`](file:///d:/Cosmolab/cosmolab/cosmolab/ask.py) | **UPDATED** | RAG query corpus kini menggunakan `retrieval.hybrid_search` + `retrieval.rerank_papers` sebelum sintesis LLM. |
| [`cosmolab/ask_agent.py`](file:///d:/Cosmolab/cosmolab/cosmolab/ask_agent.py) | **UPDATED** | Penjelajahan *Second Brain* dan pemilihan kubu dialektika (proponents & opponents) divalidasi lewat re-ranking semantik. |
| [`cosmolab/web.py`](file:///d:/Cosmolab/cosmolab/cosmolab/web.py) | **UPDATED** | Tab *Full-Text Search* di Web UI dilengkapi toggle *Hybrid Semantic RRF* dan menampilkan kolom *RRF Score*. |
| [`tests/test_retrieval.py`](file:///d:/Cosmolab/cosmolab/tests/test_retrieval.py) | **BARU** | Unit test suite untuk validasi weighted FTS5, query expansion fallback, RRF fusion, dan batas re-ranker. |

---

## 4. Bukti Hasil Uji Nyata (Sebelum vs Sesudah)

**Studi Kasus:** Pengujian query riset Bahasa Indonesia:
```bash
cosmolab search "apakah alam semesta punya awal mula" --limit 3
```

### Hasil Sebelum Pembaruan:
1. ❌ *Perlindungan Data Pribadi Mahasiswa dalam Penggunaan Teknologi Informasi...* (Meleset akibat stopwords Bahasa Indonesia).
2. ❌ *Causality and Nonlocality as Axioms for Quantum Mechanics*
3. ❌ *New remarks on the Cosmological Argument*

### Hasil Sesudah Pembaruan (Hybrid RRF):
1. ✅ **Craig’s Kalam Cosmological Argument and the Classical Kalam of the Mutakallimun (2025)** — `RRF: 0.03555` *(Kubu Pro)*
2. ✅ **Compatibilidad del Argumento Cosmológico Kalam con la Ciencia Contemporánea (2023)** — `RRF: 0.03518` *(Kubu Kontra)*
3. ✅ **Understanding The Cosmological and Teleological Arguments For God's Existence (2025)** — `RRF: 0.03498` *(Sintesis)*

---

## 5. Cara Penggunaan

### 1. Pencarian Cerdas via CLI (Default: Hybrid RRF)
```bash
# Otomatis mengekspansi konsep Bahasa Indonesia ke literatur berbahasa Inggris
cosmolab search "apakah alam semesta punya awal mula" --limit 5

# Pencarian harfiah/kata kunci persis (Exact Weighted FTS5)
cosmolab search "kalam infinity" --exact --limit 5
```

### 2. Tanya Jawab Riset / RAG (Otomatis Re-Ranked)
```bash
# Menggunakan mode RAG klasik yang telah diperkuat hybrid re-ranking
cosmolab ask "Apa kritik matematika terhadap tak terhingga aktual pada argumen Kalam?" --classic

# Menggunakan mode Agentic Second Brain dialektis
cosmolab ask "Bagaimana perdebatan kosmologi kuantum mengenai awal mula waktu?"
```

### 3. Penggunaan via Web Dashboard (Streamlit UI)
Jalankan dashboard lokal:
```bash
cosmolab ui
```
Buka menu **🔍 Full-Text Search**, centang opsi:
> ☑️ **Gunakan Hybrid Semantic RRF (Paham Bahasa Indonesia & Konsep Abstrak)**

---

## 6. Hasil Validasi & Pengujian

Semua unit test suite berhasil dilewati dengan sempurna (*100% PASS*):
* `tests/test_retrieval.py`: **4/4 passed**
* Seluruh test suite pipeline CosmoLab: **34/34 passed**
* Zero breaking changes terhadap database lama (`cosmolab.db`).

