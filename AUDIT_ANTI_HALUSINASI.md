# Audit Anti-Halusinasi RAG — CosmoLab

Tanggal: 13 Nov 2026. Basis: file di folder lokal `D:\Cosmolab\cosmolab` (bukan GitHub), dicek ulang terhadap `master` @ 9da881c. Dari dua commit terakhir, hanya config.py (`LLM_CONCURRENCY`) dan verify.py (regex nama sitasi) yang menyentuh file audit; temuan tidak berubah, nomor baris config.py sudah disesuaikan. Audit baca-saja; tidak ada kode yang diubah.
Tidak diaudit: writer.py, review.py, defense.py, gap_finder.py, curriculum.py. Tidak ada `cosmolab/api.py` di repo.

---

## 1. Ringkasan

1. Skor kasar **~40%**: dari 15 teknik yang dinilai, 2 SUDAH, 8 SETENGAH, 2 BELUM, 3 BOCOR (SUDAH = 1, SETENGAH = 0,5).
2. Bocor terbesar ada di **jalur default**, yaitu `ask` agentic (default di CLI `cli.py:333` dan opsi pertama di UI `ui/pages/ask.py:90`). Prompt-nya menyuruh model *"lengkapi dengan penalaran akademik yang objektif"* (`ask_agent.py:29`).
3. Bocor kedua: kalau retrieval lemah, kedua jalur tetap menyuapkan paper yang **tidak relevan** dan memberinya label "Terverifikasi" (`ask.py:49-53`, `ask_agent.py:120-150`, `retrieval.py:299-313`). Model lalu menjawab dengan sitasi asli yang salah konteks.
4. Gatekeeper `entail.py` hanya **melapor**, tidak menghapus apa pun (`entail.py:14`). Ia hanya mengecek kalimat yang bersitasi, ikut memakai ringkasan AI sebagai bukti, dan dinilai oleh model yang sama. `deliver` juga tidak memakainya sebagai gerbang.
5. `inspect`/`doi` tanpa abstrak menyuruh LLM *"inferensi analitik dari judul dan venue"* (`inspector.py:307`). Kalau parse gagal, ia mengisi isi generik palsu tetapi tetap `success: True` (`inspector.py:342-355`).

---

## 2. Tabel teknik

| # | Teknik | Status | Bukti (file:baris + kutipan) | Risiko kalau dibiarkan |
|---|---|---|---|---|
| 1 | Chunking | SETENGAH | `passages.py:41-43` `MIN_CHARS = 40` / `MAX_CHARS = 900` / `WINDOW = 600`, overlap 1 kalimat `:98`. Chunk hanya `{"page": p["page"], "text": text}` `:83,95`, tanpa DOI/judul/tahun (metadata ditempel per paper di `ask.py:64-66`). Halaman = indeks fisik PDF `extract.py:62` `page_num = page.number + 1`; teks tanpa penanda halaman jadi semua `"page": 1` `extract.py:98` | "Hal. 5" adalah halaman PDF ke-5, bukan nomor halaman jurnal. Klien bisa mengutip halaman yang salah. Paper lama tanpa penanda halaman selalu "Halaman 1". |
| 2 | Embedding / vector search | SETENGAH | `config.py:191` `EMBED_MODEL = _env("EMBED_MODEL")` kosong secara default, `.env.example:46` `EMBED_MODEL=` → hanya BM25. Cache disk ada: `passages.py:188` `config.ROOT / "embeddings" / f"{safe}.{tag}.json"`, dengan validasi sha1 `:196-201`. Dense hanya **di dalam satu paper**; pencarian paper di level korpus (`db.search`) tidak memakai vektor. | Pertanyaan bahasa Indonesia ke paper bahasa Inggris bergantung penuh pada ekspansi LLM + rerank LLM. |
| 3 | Hybrid search + RRF | SETENGAH | `retrieval.py:98` `raw_results = db.search(query, ...)`, `:109` `db.search(concept_query, ...)`, `:112` `k = 60.0`, `:120` `1.0 / (k + rank)`, `:126` `1.2 / (k + rank)`. Jadi "hybrid" di level paper = FTS5 + FTS5 atas kata hasil ekspansi LLM (leksikal + leksikal), **bukan** sparse + dense. RRF sungguhan BM25 + cosine hanya di `passages.py:44,264,267` (`RRF_K = 60.0`). Query FTS dirangkai dengan `OR` prefix `db.py:490`. | Dengan OR + prefix, retrieval hampir tidak pernah kosong. Paper yang hanya kebetulan berbagi satu kata ikut masuk, sehingga sistem jarang bisa bilang "tidak ada". |
| 4 | Re-ranking | SETENGAH | Paper: `retrieval.py:139` `rerank_papers`, LLM, `temperature=0.0` `:193`, tanpa cache dan tanpa timeout `:190-195`. Ia menilai **tesis/premis buatan AI**, bukan teks paper `:164-176`. Kandidat yang dibuang LLM diisi balik `:209-212`. Passage: `passages.py:344` `rerank`, LLM `temperature=0` `timeout=60` `:301-302`, cache `llmcache` `:335-340`, di-skip saat `confident(hits)` `:351`, default aktif `config.py:197`. Tidak ada cross-encoder. | Perintah rerank "Filter out papers that merely mention terms" tidak ditegakkan karena slot kosong diisi lagi. Satu LLM call tanpa batas waktu di setiap `ask`. |
| 5 | Weighting 0,4 sim + 0,4 question + 0,2 section; methods/results = 1,0, intro = 0,3, references = 0 | BELUM | **TIDAK DITEMUKAN.** Bobot yang sebenarnya dipakai: RRF 1,0 vs 1,2 (`retrieval.py:120,126`); term query 1,0 vs ekspansi `EXTRA_WEIGHT = 0.35` (`passages.py:45,236-237`); bonus frasa `bm[i] *= 1 + 0.25 * min(hits, 3)` (`passages.py:248`); bobot kolom FTS `bm25(papers_fts, 0.0, 10.0, 5.0, 1.0, 10.0, 3.0, 8.0)` dengan thesis 10 dan premises 8 (`db.py:500`). `rerank_boost` hanya flag `True` tanpa skor (`retrieval.py:205`). Daftar pustaka hanya dibuang saat `analyze` (`analyze.py:169-184`) dan di bukti `entail` (`entail.py:246` `_BIBLIO`), tidak di jalur `ask`. | Ranking paper didominasi field buatan LLM (thesis, premises) dengan bobot 10 dan 8. Passage dari daftar pustaka atau abstrak bisa naik sebagai "bukti". |
| 6 | Prompt `ask` klasik | SUDAH (prompt) | `ask.py:22` `Answer the user's question accurately using ONLY the provided corpus context.`; `ask.py:28` `If the context does not contain enough evidence, explicitly state what is missing.`; `temperature=0.2` `ask.py:122`. Tanpa `max_tokens` dan tanpa `timeout`. | Prompt-nya baik, tetapi isi "corpus context" sebagian besar ringkasan AI (`ask.py:71-84`) dan bisa berupa paper fallback yang tidak relevan (lihat #8). |
| 7 | Prompt agentic | BOCOR | `ask_agent.py:29` `bila korpus terbatas, katakan terus terang lalu lengkapi dengan penalaran akademik yang objektif.`; `:16` `...berdasarkan ... literatur yang ada dalam korpus, serta tradisi keilmuan utama di bidang tersebut.`; `:31` `Penilaianmu sendiri jangan diberi sitasi.`; header konteks `:217` `KORPUS SECOND BRAIN (Struktur Logika Terverifikasi)`. Struktur wajib 6 bagian (pro, objeksi, pembelaan) `:19-24`. | Model diberi izin eksplisit memakai pengetahuannya sendiri. Kalimat tanpa sitasi lolos dari `entail` (yang hanya mengecek kalimat bersitasi). Struktur 6 bagian memaksa model mengisi "objeksi" dan "pembelaan" walau korpus tidak memuatnya. |
| 8 | Fallback saat retrieval kosong | BOCOR | Klasik `ask.py:50-52` `# If no match, fallback to loading top available analyzed papers` → `results = [p for p in all_papers if p.get("thesis")][:top_k]`. Agentic `ask_agent.py:120-121` `if needs_contrast or len(referenced_papers) < 3: pairs = db.get_dialectical_pairs(argument_type=arg_type)`; dengan `arg_type=None` filter topik hilang (`db.py:556`) sehingga paper apa saja yang punya stance ikut masuk. `ask_agent.py:147-150` fallback ke semua paper. Passage: `retrieval.py:299` `# Nothing matched: fall back to the opening of the paper` dengan `"score": 1.0` dan `"fallback": True`. Flag itu **diabaikan** oleh `ask.py:90-93` dan `ask_agent.py:188-200` (dilabel "Bukti Verbatim Terverifikasi"). Hanya `evaluate.py:159` yang memfilternya. | Pertanyaan di luar korpus tetap dijawab percaya diri dengan sitasi ke paper yang benar-benar ada tetapi tidak relevan. `entail` bisa meloloskannya karena tesis AI ikut dipakai sebagai bukti (#12). |
| 9 | Sitasi per klaim | SETENGAH | Klasik `ask.py:24` `Cite papers inline by title and year ... If exact page numbers are available ... cite the page as well` (halaman opsional). Agentic `ask_agent.py:30` `[Penulis (Tahun)]` tanpa halaman, plus 1-3 kutipan di bagian akhir `:24`. Synthesize `synthesize.py:19` `Cite papers by their title (year) inline` dan `:34` `judul (tahun)`. DOI tidak diwajibkan di jalur mana pun. | Tidak ada kewajiban sitasi DOI + halaman per kalimat. Synthesize tidak punya halaman sama sekali karena hanya menerima JSON analisis AI, tanpa passage. |
| 10 | Output terstruktur | SETENGAH (analyze) / BOCOR (inspect) | Analyze: pydantic `analyze.py:39-54`, `research_question`/`sample_data`/`research_method` boleh null `:40-44`, prompt `:128` `Null kalau paper tidak memakai data`. Tetapi `thesis` dan `conclusion` wajib `str` `:87,93`. `limitations`: `beri paling banyak 2 keterbatasan yang jelas dan awali ... "(tidak disebut penulis)"` `:129`. `premises`: `Rumuskan 4-7 premis` `:123`. `page_hint` `dengan nama bab dan estimasi halaman` `:117`. Teks dipotong ke 60.000 karakter, bagian tengah dibuang `:197-223`. Field "instrumen": **TIDAK ADA**. Cek kutipan vs PDF ada (`analysis_check.py:95` `find_quote`, tanpa LLM), tetapi hanya lewat `cosmolab cek-analisis` (`cli.py:878`), tidak otomatis. Inspect: `inspector.py:257-278` semua field wajib tanpa opsi null; `:282` `kamu boleh melakukan inferensi metodologis yang rasional`; `:307` `(Abstrak ... tidak tersedia ... Lakukan inferensi analitik dari judul dan venue jurnal)`; `:342-350` isi generik palsu saat gagal, lalu `"success": True` `:355`. | Jumlah premis yang dipaksa dan halaman yang ditebak ikut masuk konteks `ask` sebagai "Struktur Logika Terverifikasi". `inspect` tanpa abstrak menghasilkan ringkasan karangan yang tampak resmi. |
| 11 | Metadata dari harvester | SUDAH | `harvest.py:45` `_search_arxiv`, `:108` `_search_openalex`, `:139` `_search_doaj`, `:190` `_search_semanticscholar`. `grep` `OpenAI\|chat.completions` di harvest.py, metadata.py, extract.py: 0 hasil. `analyze.py:361-365` menyalin `doi/title/year` dari record harvest. Inspect: Crossref → S2 → OpenAlex → Unpaywall `inspector.py:101-211`. | Kecil: placeholder `'Academic Journal'` (`inspector.py:228`), `"Jurnal Ilmiah"` dan `"Anonim"` (`:245,249`), serta `meta.get("year", "2024")` (`:221`) bisa masuk BibTeX/APA tanpa tanda. |
| 12 | Gatekeeper klaim (`entail.py`) | SETENGAH (lapor saja) | `entail.py:14` `Nothing is removed from the answer.` Benar: tidak ada kode yang menghapus atau menandai kalimat di jawaban. Hanya kalimat bersitasi yang jadi klaim `:135-136` `if not cites: continue`. Maksimal 20 klaim `:372,387`. Bukti memasukkan ringkasan AI `:252-254` `("thesis", "Tesis (analisis)")` karena `use_analysis=True` default di `check_answer` `:396`. Sitasi tak cocok → `sumber_tidak_ada` `:329-331` (bagus). Judge gagal → `belum_dicek`, tidak memblokir `:340-343`. Default aktif di CLI `cli.py:335` dan UI `ui/pages/ask.py:95-96`. | Kalimat tanpa sitasi tidak pernah dicek. Klaim yang cocok dengan tesis buatan AI dinilai "didukung" walau PDF tidak memuatnya (penilaian melingkar). |
| 13 | Devil's advocate sebagai checker | BELUM | `sparring.py` hanya dipanggil dari `ui/pages/sparring.py:72,119`. Tidak dipanggil di `verify`, `deliver`, atau `ask`. `sparring.py:360` `(Tidak ada paper spesifik yang cocok langsung, gunakan basis pengetahuan filosofismu).` | Hanya generator argumen. Kalau tidak ada paper, ia malah bebas memakai pengetahuan model. |
| 14 | Evaluasi (`uji`) | SETENGAH | `evaluate.py:34-35` gold di `<ROOT>/eval/gold.jsonl` (per proyek). Metrik `recall_at_k`, `mrr`, `accuracy`, `false_caught`, `true_passed` `:182-215`. Draft `"reviewed": False` `:129`, tetapi CLI `--diperiksa` default `False` `cli.py:977`, jadi soal yang belum direview ikut dihitung. Gold dibuat oleh model yang sama dengan judge `:85-87`. Retrieval diuji **di dalam file yang sudah diketahui** `:157`, jadi `hybrid_search`/`rerank_papers`/`ask` tidak teruji. Tidak ada soal "tidak ada jawabannya di korpus". | Angka uji bisa tampak bagus padahal jalur `ask` end-to-end dan perilaku menolak menjawab tidak pernah diukur. |
| 15 | Timeout ekspansi + fallback | BOCOR | `retrieval.py:57-62` `expand_academic_query`: `client.chat.completions.create(... temperature=0.1, max_tokens=150)` **tanpa `timeout`** (ada cache `:44-47`). `rerank_papers` tanpa timeout `:190-195`. Panggilan utama tanpa timeout: `ask.py:116-123`, `ask_agent.py:220-227`, `synthesize.py:101-108`, `inspector.py:326-333`. Default SDK OpenAI: 600 detik, 2 retry. `hybrid_search` sudah menghitung `raw_results` di `:98` lalu menunggu ekspansi `:104`; tidak ada batas waktu yang mengembalikan `raw_results`. `hybrid:false` hanya di `cosmolab search --exact` → `db.search` (`cli.py:300,306`); `ask` selalu `expand_concepts=True` (`ask.py:40`, `ask_agent.py:107`). | Gateway lambat membuat `ask` menggantung sampai ±10 menit per panggilan. Ditambah fallback model tersembunyi (#17), jawaban bisa datang dari model lain tanpa disadari. |

---

## 3. Top 5 bocor halusinasi (paling berbahaya dulu)

**1. Jalur default (agentic) diberi izin mengisi dengan pengetahuan sendiri, dan isian itu lolos dari pemeriksa.**
- `ask_agent.py:29`: `"bila korpus terbatas, katakan terus terang lalu lengkapi dengan penalaran akademik yang objektif."`
- `ask_agent.py:16`: `"... serta tradisi keilmuan utama di bidang tersebut."`
- `ask_agent.py:31`: `"Penilaianmu sendiri jangan diberi sitasi."` + `entail.py:135-136` `if not cites: continue`.
- Default: `cli.py:333` `agentic: bool = typer.Option(True, ...)`; UI `ui/pages/ask.py:90` `["Agentic", "Classic"]`.
- Akibat: paragraf "Sintesis & Kesimpulan" dan "Objeksi" bisa berasal dari pengetahuan model, tanpa sitasi, sehingga tidak pernah diperiksa.

**2. Paper dan passage tidak relevan disuapkan sebagai "bukti terverifikasi".**
- `ask.py:51-52`: `all_papers = db.get_all_papers_with_analyses()` / `results = [p for p in all_papers if p.get("thesis")][:top_k]`
- `ask_agent.py:120-121`: `if needs_contrast or len(referenced_papers) < 3:` / `pairs = db.get_dialectical_pairs(argument_type=arg_type)` (`arg_type=None` → semua topik, `db.py:556`).
- `retrieval.py:299-312`: `# Nothing matched: fall back to the opening of the paper` … `"score": 1.0, ... "fallback": True`. Flag itu diabaikan di `ask_agent.py:200` `"- Bukti Verbatim Terverifikasi: ..."`.
- Akibat: pertanyaan di luar korpus dijawab dengan sitasi ke paper asli yang salah konteks. Ini jenis halusinasi paling sulit dideteksi manusia.

**3. `inspect` / `doi` mengarang analisis saat abstrak tidak ada atau JSON gagal.**
- `inspector.py:307`: `"(Abstrak teks penuh tidak tersedia di indeks terbuka. Lakukan inferensi analitik dari judul dan venue jurnal)."`
- `inspector.py:282`: `"kamu boleh melakukan inferensi metodologis yang rasional berdasarkan bidang ilmunya."`
- `inspector.py:344-345`: `"methodology": "Analisis teoritis/empiris sesuai bidang studi pada venue terkait."`, `"key_findings": ["Temuan artikel dapat dirujuk langsung pada naskah lengkap."]`, lalu `"success": True` (`:355`).
- Akibat: "Metodologi", "Temuan Kunci", dan "Research Gaps" untuk DOI tertentu bisa 100% karangan, lalu disimpan sebagai `.md` yang tampak resmi.

**4. Gatekeeper tidak menggerbang: lapor saja, bukti melingkar, model sama, dan `deliver` tidak memakainya.**
- `entail.py:14`: `"Nothing is removed from the answer."`
- `entail.py:252-254`: `for field, label in (("thesis", "Tesis (analisis)"), ("conclusion", "Kesimpulan (analisis)")):` → ringkasan AI dihitung sebagai bukti (default `use_analysis=True`).
- `entail.py:268`: `model=model or config.LLM_MODEL`, model yang sama dengan generator.
- `deliverables.py:432`: `if not report.ok and not allow_unverified: raise DeliveryBlocked(report)`. `report` dari `verify` hanya mengecek **keberadaan rujukan** (Crossref/korpus), bukan isi klaim.
- Akibat: dokumen klien bisa lolos `deliver` dengan klaim `tidak_didukung` di dalamnya.

**5. Ringkasan AI disajikan sebagai fakta korpus, plus model cadangan tersembunyi.**
- `ask_agent.py:217`: `"KORPUS SECOND BRAIN (Struktur Logika Terverifikasi):"`, padahal isinya tesis/premis/objeksi buatan `analyze` yang tidak dicek otomatis.
- `analyze.py:123` `Rumuskan 4-7 premis`, `:117` `estimasi halaman`, `:129` keterbatasan karangan berlabel.
- `ask_agent.py:240,258`: `model="gemini-3-8-flash"` hard-coded; `:249-250` `if not content and reasoning: content = reasoning.strip()` (rantai penalaran mentah dijadikan jawaban).
- Akibat: kesalahan saat analisis ikut menular ke setiap jawaban. Jawaban bisa datang dari model lain atau dari "draft pikiran" model tanpa diketahui pengguna.

---

## 4. Daftar perbaikan (BELUM diterapkan)

### P0 — wajib, murah, paling berpengaruh (ubah prompt atau logika, 0 LLM call tambahan)

**P0-1. Cabut izin "lengkapi dengan penalaran"** — `ask_agent.py:16,29`
```diff
-... berdasarkan argumen, data, dan literatur yang ada dalam korpus, serta tradisi keilmuan utama di bidang tersebut.
+... HANYA berdasarkan argumen, data, dan kutipan yang ada dalam KORPUS di bawah.
-- Berpijak pada literatur yang ada dalam korpus, dan bila korpus terbatas, katakan terus terang lalu lengkapi dengan penalaran akademik yang objektif.
+- Pakai HANYA isi korpus. Bila korpus tidak memuat jawabannya, tulis "Tidak ditemukan di korpus ini: <apa yang hilang>" dan JANGAN mengisi dari pengetahuanmu sendiri.
+- Bagian 3-4 (objeksi/pembelaan) boleh ditulis "Tidak ada di korpus" bila memang tidak ada.
```

**P0-2. Wajibkan sitasi + halaman per kalimat faktual** — `ask.py:24`, `ask_agent.py:30-31`
```diff
-- Setiap kalimat yang diberi sitasi harus benar-benar dinyatakan oleh paper itu. Penilaianmu sendiri jangan diberi sitasi.
+- SETIAP kalimat faktual wajib diakhiri sitasi [Penulis (Tahun), Hal. X] dengan halaman dari "Bukti Verbatim". Kalimat penilaianmu sendiri awali dengan "Catatan analis:".
```

**P0-3. Hentikan fallback paper tidak relevan** — `ask.py:49-53`, `ask_agent.py:147-150`
```diff
-    if not results:
-        # If no match, fallback to loading top available analyzed papers
-        all_papers = db.get_all_papers_with_analyses()
-        results = [p for p in all_papers if p.get("thesis")][:top_k]
+    if not results:
+        return "Tidak ditemukan di korpus ini untuk pertanyaan tersebut."
```

**P0-4. Batasi penambahan pasangan dialektis** — `ask_agent.py:120`
```diff
-    if needs_contrast or len(referenced_papers) < 3:
+    if needs_contrast and arg_type:
```

**P0-5. Jangan pakai passage fallback (abstrak) sebagai bukti** — `ask.py:90`, `ask_agent.py:188`, `entail.py:244`
```diff
-                passages = found.get(r["file"]) or []
+                passages = [p for p in (found.get(r["file"]) or []) if not p.get("fallback")]
```
Lalu buang paper yang tidak punya passage non-fallback dari konteks. Ini sekaligus menjadi ambang relevansi gratis.

**P0-6. Bukti `entail` hanya teks PDF** — `entail.py:396`
```diff
-    results = _judge_claims(claims, model, judge, evidence_fn)
+    results = _judge_claims(claims, model, judge, evidence_fn, use_analysis=False)
```

**P0-7. Jujur soal header konteks** — `ask_agent.py:217`
```diff
-    user_prompt = f"KORPUS SECOND BRAIN (Struktur Logika Terverifikasi):\n..."
+    user_prompt = f"KORPUS (ringkasan AI belum diverifikasi; hanya 'Bukti Verbatim' yang teks asli):\n..."
```

**P0-8. Hapus model cadangan tersembunyi dan reasoning-as-answer** — `ask_agent.py:237-250,254-265`
```diff
-        if not content and reasoning:
-            content = reasoning.strip()
+        # reasoning bukan jawaban; biarkan kosong → pesan gagal
```
Kalau fallback tetap dibutuhkan, pindahkan ke `config.FALLBACK_MODEL` dan tampilkan nama model di jawaban.

**P0-9. `inspect` tanpa abstrak: jangan berinferensi** — `inspector.py:307,342-355`
```diff
-    abstract_text = meta.get("abstract") or "(Abstrak ... Lakukan inferensi analitik dari judul dan venue jurnal)."
+    if not meta.get("abstract"):
+        return {**meta_only, "success": True, "analysis": None,
+                "note": "Abstrak tidak tersedia; analisis tidak dibuat."}
...
-        analysis_data = { "problem_statement": ..., "methodology": "Analisis teoritis/empiris ..." }
+        return {"success": False, "error": f"Analisis gagal: {e}", "doi": clean_doi}
```
Ganti juga `inspector.py:282` menjadi `"Field yang tidak ada di abstrak isi null."`.

**P0-10. Timeout di semua LLM call** — `retrieval.py:57`, `retrieval.py:190`, `ask.py:116`, `ask_agent.py:220`, `synthesize.py:101`, `inspector.py:326`
```diff
         resp = client.chat.completions.create(
             model=model,
             ...
-            max_tokens=150,
+            max_tokens=150,
+            timeout=20,
         )
```
Panggilan utama: `timeout=120`. Pada `hybrid_search`, kalau ekspansi gagal atau timeout, kembalikan `raw_results[:limit]` (exception sudah ditangkap di `retrieval.py:72`, jadi cukup tambahkan timeout).

**P0-11. `uji jalan` default hanya soal yang sudah direview** — `cli.py:977`
```diff
-    reviewed: bool = typer.Option(False, "--diperiksa", ...)
+    reviewed: bool = typer.Option(True, "--diperiksa/--semua-soal", ...)
```

### P1 — penting (sedikit kode, sebagian menambah biaya)

- **P1-1. `deliver` menggerbang isi klaim** — `deliverables.py:432`. Jalankan `entail.check_answer(md, use_analysis=False)` dan blokir bila `needs_attention > 0`, kecuali `--sudah-cek-manual`. Biaya: +1 batch judge per 10 klaim per dokumen.
- **P1-2. Model judge terpisah** — `config.py` setelah `:149`: `JUDGE_MODEL = _env("COSMOLAB_JUDGE_MODEL") or LLM_MODEL`; pakai di `entail.py:268`. Tolak judge lokal (Qwen) dengan peringatan. Biaya: 0.
- **P1-3. Tandai kalimat tak didukung di jawaban** — `ui/claims.py` dan `cli.py:367`. Coret atau beri label merah pada kalimat `tidak_didukung` / `sumber_tidak_ada` di teks jawaban. Ini menjawab #12 tanpa LLM call tambahan.
- **P1-4. Kalimat tanpa sitasi ikut ditandai** — `entail.py:135`. Kalimat faktual tanpa sitasi di bagian non-"Catatan analis" diberi verdict baru `tanpa_sitasi` (regex, 0 LLM).
- **P1-5. Cek kutipan otomatis setelah analyze** — `analyze.py:374`. Panggil `analysis_check.check_quotes(result, extract.get_paper_pages(...))` (tanpa LLM) dan buang kutipan yang tidak ditemukan. Biaya: 0 LLM.
- **P1-6. Prompt analyze anti-tebak** — `analyze.py:117,123,129`:
```diff
-   - Cantumkan 'page_hint' dengan nama bab dan estimasi halaman
+   - 'page_hint': nama bab saja; null bila tidak yakin. JANGAN menebak nomor halaman.
-   - Rumuskan 4-7 premis logis
+   - Rumuskan paling banyak 7 premis yang eksplisit di teks; daftar kosong bila tidak ada.
-   Kalau penulis tidak menyebut satu pun, beri paling banyak 2 keterbatasan yang jelas dan awali ...
+   Kalau penulis tidak menyebut satu pun, kembalikan daftar kosong.
```
Biaya: analisis ulang korpus.
- **P1-7. `rerank_papers` jangan isi balik kandidat yang dibuang, dan tambahkan cache** — `retrieval.py:209-212`: hapus loop pengisian; bungkus dengan `llmcache` seperti `passages.py:335`.
- **P1-8. Perluas `uji`** — `evaluate.py`: (a) jenis soal `abstain` (pertanyaan yang jawabannya tidak ada di korpus; benar bila jawaban memuat "tidak ditemukan"); (b) jenis soal `ask` end-to-end yang dijalankan lewat `ask` dan `ask_agentic`, lalu dinilai dengan `entail`; (c) `draft_gold` memakai model berbeda dari judge.
- **P1-9. Synthesize diberi bukti verbatim dan pemeriksaan** — `synthesize.py:86-100`. Sertakan 1-2 passage per paper dan jalankan `entail.check_answer` atas laporan. Biaya: +1 judge batch per laporan.

### P2 — optimasi (lebih mahal)

- **P2-1. Embedding default aktif** (mis. `EMBED_MODEL=local:BAAI/bge-m3` via fastembed) dan vektor juga di level paper untuk `hybrid_search`. Biaya: compute lokal + dependensi.
- **P2-2. Weighting per section** — `passages.chunk_pages`: deteksi heading (Methods/Results/Discussion → 1,0; Introduction → 0,3; References → 0) lalu kalikan ke skor fused. Kode sedang, 0 LLM.
- **P2-3. Cross-encoder rerank** (mis. `bge-reranker-v2-m3`) untuk menggantikan rerank LLM di `passages.rerank` dan `rerank_papers`. Mengurangi LLM call, tetapi menambah model lokal.
- **P2-4. Nomor halaman tercetak** — `extract.py:62`. Deteksi angka halaman di header/footer dan simpan `printed_page` di samping indeks PDF.
- **P2-5. Kurangi bobot field AI di FTS** — `db.py:500`: turunkan thesis 10 → 3 dan premises 8 → 2 supaya teks asli yang lebih menentukan.

---

## 5. Pertanyaan yang belum bisa dijawab dari kode saja

| Pertanyaan | Bisa dijawab `uji`? | Cara tes |
|---|---|---|
| Seberapa sering judge menangkap klaim palsu, dan seberapa sering klaim benar lolos? | Ya | `false_caught`, `true_passed` dari `uji jalan --diperiksa` |
| Apakah halaman yang ditemukan memang halaman yang benar? | Ya (di dalam paper yang sudah diketahui) | `recall_at_k`, `MRR` |
| Apakah rerank LLM benar-benar membantu? | Ya | jalankan dengan `--rerank` lalu `--no-rerank`, bandingkan di `uji riwayat` |
| Apakah EMBED_MODEL menaikkan recall? | Ya | jalankan sebelum dan sesudah mengisi `EMBED_MODEL`; kolom `embedding` di `uji riwayat` |
| Seberapa besar efek `use_analysis=True` (bukti melingkar) pada akurasi judge? | **Tidak** (tidak ada flag CLI; perlu ubah kode atau panggil `evaluate.run` dari Python) | bandingkan `entail.check_claims(..., use_analysis=False)` vs `True` atas gold yang sama |
| Apakah DeepSeek v4 Pro benar-benar menolak menjawab pertanyaan di luar korpus? | **Tidak** (`uji` tidak menguji `ask`) | manual: 5-10 pertanyaan yang pasti tidak ada di korpus, jalankan `cosmolab ask "<q>" --classic` dan `cosmolab ask "<q>" --agentic`, lalu hitung berapa yang tidak berkata "tidak ditemukan" |
| Seberapa sering jalur agentic menulis kalimat tanpa sitasi? | **Tidak** | manual: hitung kalimat tanpa `[..(Tahun)..]` di 10 jawaban agentic |
| Apakah retrieval level korpus (`hybrid_search` + `rerank_papers`) memilih paper yang benar? | **Tidak** (`uji` mulai dari file yang sudah diketahui) | butuh jenis soal baru (P1-8) |
| Model apa yang sebenarnya melayani `gemini-3-8-flash` di gateway, dan seberapa sering fallback terjadi? | **Tidak** | `cosmolab log` lalu cari langkah "Mencoba fallback model" di `thought_steps`; cek dasbor gateway |
| Kalau `LLM_MODEL` di `.env` diarahkan ke Qwen 3.5 9B lokal, jalur apa yang ikut berubah? | Dari kode: **semua** (ask, agentic, rerank, ekspansi, analyze, entail judge, synthesize, uji draft) karena semuanya memakai `config.LLM_MODEL` (`config.py:144-149`). Tidak ada `JUDGE_MODEL` atau model draft terpisah; string "qwen" tidak ditemukan di kode. | jalankan `uji jalan` sekali dengan `--model <qwen>` untuk melihat penurunan akurasi judge |

Urutan tes yang disarankan:

```bash
cosmolab uji buat --n 20
```
Buka `<ROOT>/eval/gold.jsonl` (per proyek: `projects/<nama>/eval/gold.jsonl`). Periksa setiap soal, lalu set `"reviewed": true` hanya pada soal yang benar.

```bash
cosmolab uji jalan --diperiksa --k 3
```
```bash
cosmolab uji jalan --diperiksa --k 3 --no-rerank
```
```bash
cosmolab uji riwayat
```

Ambang yang wajar sebelum hasil dipakai untuk klien: `false_caught` ≥ 90%, `true_passed` ≥ 80%, `recall@3` ≥ 70%. Ulangi tes yang sama setelah setiap perbaikan P0 dan bandingkan lewat `uji riwayat`.

---

## Lampiran: alur data dan model per jalur

**Alur:** harvest (API arXiv/OpenAlex/DOAJ/S2, tanpa LLM) → extract (PyMuPDF, halaman = indeks PDF) → analyze (LLM, teks ≤ 60k karakter, JSON, **tidak dicek otomatis**) → sync (SQLite FTS5, ikut mengindeks field AI) → search (`hybrid_search`: FTS + ekspansi LLM + RRF) → ask klasik / agentic (rerank LLM → passage BM25 ± dense ± rerank LLM → LLM jawab) → cek klaim `entail` (lapor saja) → synthesize (LLM atas JSON analisis saja, tanpa passage, tanpa cek) → verify (keberadaan rujukan di korpus/Crossref) → deliver (gerbang = verify + nama reviewer wajib).

**Titik LLM bisa menjawab tanpa konteks yang relevan:**
1. `ask` klasik: fallback paper teratas (`ask.py:50-52`).
2. `ask` agentic: izin "lengkapi dengan penalaran" (`ask_agent.py:29`) + pasangan dialektis lintas topik (`:120`) + fallback (`:147-150`).
3. Passage fallback abstrak berlabel terverifikasi (`retrieval.py:299`).
4. `inspect`/`doi` tanpa abstrak (`inspector.py:307`) dan fallback palsu (`:342-350`).
5. `sparring` tanpa paper (`sparring.py:360`).
6. `synthesize` bagian "Gaps — what no paper addresses" (`synthesize.py:16,31`), yang mengundang pengetahuan luar karena model hanya melihat ringkasan.

**Titik manusia wajib cek:** `deliver --reviewer` (`deliverables.py:425-426`), bisa dilewati dengan `--sudah-cek-manual` (`cli.py:675-678`). Tabel `entail` hanya bersifat saran. `cek-analisis` manual dan opsional.

**Model per jalur:**

| Jalur | Model | Bukti |
|---|---|---|
| ask klasik | `config.NINEROUTER_MODEL` (= `LLM_MODEL`, default `deepseek-v4-pro`) | `ask.py:36`, `config.py:144-154` |
| ask agentic | `LLM_MODEL`, **fallback hard-coded `gemini-3-8-flash`** | `ask_agent.py:91,240,258` |
| ekspansi + rerank paper + rerank passage | `LLM_MODEL` (atau `--model` yang diteruskan) | `retrieval.py:40,155`, `passages.py:297` |
| entail judge + terms | `LLM_MODEL`, sama dengan generator | `entail.py:212,268` |
| synthesize | `LLM_MODEL` | `synthesize.py:67` |
| analyze | `LLM_MODEL` | `analyze.py:313,423` |
| sparring, gap_finder, curriculum | `LLM_MODEL` + fallback `gemini-3-8-flash` | `sparring.py:383`, `gap_finder.py:141`, `curriculum.py:336,348` |
| Qwen 3.5 9B lokal | **TIDAK DITEMUKAN** di kode; hanya bisa lewat `LLM_MODEL`/`LLM_BASE_URL` global | `config.py:132-149`, `config.py:174-175` (komentar llama.cpp) |
