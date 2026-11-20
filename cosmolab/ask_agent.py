import json
import re
from openai import OpenAI
from rich.console import Console
from . import config
from . import db
from . import faculties as _faculties
from . import retrieval

console = Console(force_terminal=True, legacy_windows=False)

AGENTIC_SYSTEM_PROMPT = """Kamu adalah CosmoLab, Asisten Peneliti Akademik Senior multidisipliner berbasis "Agentic Second Brain".
Kamu bekerja lintas bidang: humaniora, filsafat, agama, hukum, ekonomi, pendidikan, psikologi, sosial, sains, teknologi, dan kesehatan.
Kenali bidang pertanyaan, lalu pakai kerangka teori, metode, dan istilah baku bidang tersebut.

TUGAS UTAMA:
Jawablah pertanyaan pengguna dengan melakukan SINTESIS DIALEKTIS yang membandingkan kubu pendukung (proponents) dan kubu pengkritik (opponents) HANYA berdasarkan argumen, data, dan kutipan yang ada dalam KORPUS di bawah.

PANDUAN STRUKTUR JAWABAN:
1. 🎯 **Intisari / Tesis Jawaban**: Ringkasan konseptual padat yang langsung menjawab inti pertanyaan.
2. 🟢 **Rekonstruksi Argumen Pendukung**: Tesis, premis, dan bukti yang diajukan para pendukung, disertai sitasi eksplisit format `[Penulis (Tahun)]`.
3. 🔴 **Objeksi Kritis & Serangan Balik**: Tunjukkan dengan tepat premis, data, atau metode mana yang diserang oleh kubu pengkritik.
4. 🛡️ **Tanggapan & Pertahanan Dialektis**: Bagaimana pembela argumen merespons keberatan tersebut.
5. ⚖️ **Sintesis & Kesimpulan Akademik**: Penilaian objektif mengenai status perdebatan dalam literatur.
6. 💬 **Kutipan Kunci & Petunjuk Halaman**: Cantumkan 1-3 kutipan verbatim beserta rujukan dari korpus.

ATURAN KETAT:
- Gunakan BAHASA INDONESIA akademis yang lugas, elegan, dan berbobot ilmiah.
- Pertahankan istilah teknis baku bidang terkait (istilah Arab klasik, hukum, ekonomi, medis, sains, dll.) dan jelaskan singkat pada kemunculan pertama.
- Pakai HANYA isi korpus. Bila korpus tidak memuat jawabannya, tulis "Tidak ditemukan di korpus ini: <apa yang hilang>" dan JANGAN mengisi dari pengetahuanmu sendiri.
- Bagian 3-4 (objeksi/pembelaan) boleh ditulis "Tidak ada di korpus" bila memang tidak ada.
- Sitasi memakai nama belakang penulis dan tahun, misalnya `[Popescu & Rohrlich (1997)]`. Bila penulis tidak diketahui, pakai judul singkat dan tahun. JANGAN menulis "Paper 1" atau nomor urut korpus sebagai sitasi.
- HANYA kutip naskah yang terdaftar dalam korpus. Jika naskah di korpus adalah survei/kajian literatur yang membahas karya pihak ketiga (misalnya MEND, ROME, dll.), tetap cantumkan sitasi paper korpus tempat kamu membacanya, BUKAN paper luar yang tidak ada di daftar korpus.
- SETIAP kalimat faktual wajib diakhiri sitasi, dengan halaman bila ada di "Bukti Verbatim", misalnya `[Popescu (1997), Hal. 4]`. Kalimat itu harus benar-benar dinyatakan oleh paper itu.
- Ringkasan paper di korpus dibuat AI dan belum diverifikasi; hanya "Bukti Verbatim" yang teks asli paper. Utamakan Bukti Verbatim.
- Kalimat penilaianmu sendiri awali dengan "Catatan analis:" dan jangan diberi sitasi.
"""


def _has_word(text: str, terms) -> bool:
    """True when one of the terms appears as whole words in text."""
    return any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text) for t in terms)


def _detect_query_intent(question: str) -> dict:
    """Analyze the user's question to determine argument type, faculty domain, and whether dialectical contrast is needed."""
    q_lower = question.lower()
    
    # Detect faculty domain dynamically using the full faculty registry (core & custom)
    detected_fac = _faculties.detect_faculty_from_text(question)
    faculty = detected_fac if detected_fac not in ("umum", "unclassified") else "umum"

    # Detect specific argument/study type across disciplines.
    # Whole words only to prevent accidental false matches.
    arg_type = None
    if _has_word(q_lower, ("kalam", "mulai ada", "begin to exist", "temporal", "huduts")):
        arg_type = "kalam"
    elif _has_word(q_lower, ("fine-tuning", "penyetelan", "konstanta", "multiverse")):
        arg_type = "fine-tuning"
    elif _has_word(q_lower, ("contingency", "kontingensi", "leibniz", "alasan cukup", "psr", "imkan")):
        arg_type = "contingency"
    elif _has_word(q_lower, ("first cause", "sebab pertama", "aquinas")):
        arg_type = "first-cause"
    elif _has_word(q_lower, ("kuantitatif", "regresi", "pengaruh", "korelasi", "survei", "angket", "eksperimen", "statistik")):
        arg_type = "empiris_kuantitatif"
    elif _has_word(q_lower, ("kualitatif", "studi kasus", "wawancara", "etnografi", "fenomenologi")):
        arg_type = "kualitatif_studi_kasus"
    elif _has_word(q_lower, ("kajian literatur", "tinjauan pustaka", "literature review", "slr", "meta-analisis")):
        arg_type = "kajian_literatur"
    elif _has_word(q_lower, ("yuridis", "normatif", "pasal", "peraturan", "undang-undang")):
        arg_type = "yuridis_normatif"
    elif _has_word(q_lower, ("komparatif", "studi komparatif", "perbandingan metode")):
        arg_type = "komparatif"

    # Detect if contrast / objection / synthesis is requested
    is_synth = retrieval.is_synthesis_query(question)
    needs_contrast = is_synth or _has_word(q_lower, (
        "bantah", "membantah", "bantahan", "kritik", "mengkritik", "kritikan", "sanggah", "sanggahan",
        "objeksi", "keberatan", "lawan", "kontra", "debat", "perdebatan", "bandingkan", "membandingkan",
        "apakah benar", "kelemahan", "vs", "versus", "bertentang", "bertentangan", "pertentangan",
        "kontradiksi", "berlawanan", "silang pendapat",
    ))

    return {
        "faculty": faculty,
        "argument_type": arg_type,
        "needs_contrast": needs_contrast,
        "is_synthesis": is_synth,
    }



def ask_agentic(question: str, model: str = None, top_k: int = 6) -> dict:
    """
    Agentic Second Brain query engine:
    1. Reason: Analyzes intent and plans retrieval strategy.
    2. Act: Traverses structured Second Brain knowledge (theses, premises, objections, stances).
    3. Synthesize: Formulates a dialectical comparative synthesis with verifiable citations.
    
    Returns a dict with:
      - 'answer': Markdown formatted response
      - 'thought_steps': List of reasoning steps taken by the agent
      - 'referenced_papers': List of paper metadata dicts used
    """
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    thought_steps = []

    # Step 1: Reason about question intent
    intent = _detect_query_intent(question)
    arg_type = intent["argument_type"]
    needs_contrast = intent["needs_contrast"]

    step1_msg = f"Menganalisis fokus riset: Topik '{arg_type.upper() if arg_type else 'Umum'}' | Mode: {'Dialektis Pro vs Kontra' if needs_contrast else 'Eksplorasi Konseptual'}."
    thought_steps.append(step1_msg)
    console.print(f"[cyan]AGENT STEP 1[/cyan] [dim]{step1_msg}[/dim]")

    # Step 2: Traverse Second Brain via Advanced Hybrid Retrieval & Re-ranking
    referenced_papers = []
    
    # Retrieve candidates via Hybrid Search (FTS5 + Semantic Concept Expansion)
    candidates = retrieval.hybrid_search(question, limit=top_k * 3, expand_concepts=True, model=model)
    ranked_candidates = retrieval.rerank_papers(question, candidates, top_k=top_k, model=model)
    seen_files = set()

    for r in ranked_candidates:
        f = r.get("file")
        if f and f not in seen_files:
            summary = db.get_paper_knowledge_summary(f)
            if summary and summary.get("thesis"):
                referenced_papers.append(summary)
                seen_files.add(f)

    # Add the opposing side only when the question asks for it and names a known argument;
    # otherwise papers unrelated to the question would be fed in as sources.
    if needs_contrast and arg_type:
        pairs = db.get_dialectical_pairs(argument_type=arg_type)
        # Add opposing papers if not already present
        for opp in pairs["opponents"]:
            f = opp.get("file")
            if f and f not in seen_files:
                summary = db.get_paper_knowledge_summary(f)
                if summary:
                    referenced_papers.append(summary)
                    seen_files.add(f)
                if len(referenced_papers) >= top_k:
                    break

        for pro in pairs["proponents"]:
            f = pro.get("file")
            if f and f not in seen_files and len(referenced_papers) < top_k + 2:
                summary = db.get_paper_knowledge_summary(f)
                if summary:
                    referenced_papers.append(summary)
                    seen_files.add(f)

    # For general synthesis or dialectical queries across collection, augment with active papers
    if intent.get("is_synthesis") and (not referenced_papers or len(referenced_papers) < top_k):
        all_known = db.get_all_papers_with_analyses()
        for p in all_known:
            f = p.get("file")
            if f and f not in seen_files:
                summary = db.get_paper_knowledge_summary(f)
                if summary and summary.get("thesis"):
                    referenced_papers.append(summary)
                    seen_files.add(f)
            if len(referenced_papers) >= top_k:
                break

    pro_count = len([p for p in referenced_papers if p.get("supports_or_critiques") == "supports"])
    contra_count = len([p for p in referenced_papers if p.get("supports_or_critiques") == "critiques"])
    step2_msg = f"Menjelajahi Second Brain: Menemukan {len(referenced_papers)} paper terstruktur ({pro_count} pendukung, {contra_count} pengkritik)."
    thought_steps.append(step2_msg)
    console.print(f"[cyan]AGENT STEP 2[/cyan] [dim]{step2_msg}[/dim]")

    # Step 3: Build compact structured knowledge context (~1,200 - 2,000 tokens)
    context_blocks = []
    all_grounded_citations = []
    found = retrieval.grounded_passages_batch([p.get("file") for p in referenced_papers], question, top_k=2, model=model)
    # A passage marked "fallback" is only the paper's opening, not a match for the question.
    found = {f: [psg for psg in (psgs or []) if not psg.get("fallback")] for f, psgs in found.items()}

    if intent.get("is_synthesis"):
        # For cross-document synthesis queries, retain all referenced papers for comparative reasoning
        dropped = []
        thought_steps.append(f"Menganalisis sintesis komparatif terhadap {len(referenced_papers)} paper dalam koleksi.")
    else:
        # A paper with no matching passage of its own text is left out of specific needle sources.
        dropped = [p for p in referenced_papers if not found.get(p.get("file"))]
        referenced_papers = [p for p in referenced_papers if found.get(p.get("file"))]
        if dropped:
            thought_steps.append(f"{len(dropped)} paper dikeluarkan karena teksnya tidak memuat bagian yang cocok dengan pertanyaan.")

    if not referenced_papers:
        thought_steps.append("Tidak ada paper di koleksi yang teksnya cocok dengan pertanyaan. AI tidak dipanggil.")
        return {"answer": "Tidak ditemukan di korpus ini untuk pertanyaan tersebut.", "thought_steps": thought_steps,
                "referenced_papers": [], "grounded_citations": []}

    for idx, p in enumerate(referenced_papers, 1):
        year = p.get("year") or "n.d."
        title = p.get("title") or "Untitled"
        stance = p.get("supports_or_critiques") or "neutral"
        arg_t = p.get("argument_type") or "other"
        
        block = f"### [Paper {idx}] {title} ({year})\n"
        try:
            names = json.loads(p.get("authors") or "[]")
        except Exception:
            names = []
        if names:
            block += f"- Penulis: {', '.join(names[:4])}{' dkk.' if len(names) > 4 else ''}\n"
        block += f"- Tipe Argumen: {arg_t} | Sikap: {stance}\n"
        if p.get("thesis"):
            block += f"- Tesis: {p.get('thesis')}\n"
        if p.get("premises"):
            block += f"- Premis: {'; '.join(p.get('premises'))}\n"
        if p.get("conclusion"):
            block += f"- Kesimpulan: {p.get('conclusion')}\n"
        if p.get("key_objection"):
            block += f"- Objeksi Kunci: {p.get('key_objection')}\n"
        if p.get("key_defense"):
            block += f"- Tanggapan: {p.get('key_defense')}\n"
        if p.get("quotes"):
            # Quotes checked against the PDF carry the PDF page they were found on; older ones only the AI's guess.
            quotes_str = " | ".join(
                f"\"{q.get('text', '')}\" (hal. PDF {q['page']})" if q.get("page")
                else f"\"{q.get('text', '')}\" (perkiraan AI: {q.get('page_hint') or 'tanpa halaman'})"
                for q in p.get("quotes")[:2])
            block += f"- Kutipan Ringkasan: {quotes_str}\n"

        # P1: Attach exact page-grounded passages
        f = p.get("file")
        if f:
            try:
                passages = found.get(f) or []
                for psg in passages:
                    all_grounded_citations.append({
                        "paper_title": title,
                        "year": year,
                        "file": f,
                        "page": psg["page"],
                        "page_label": psg["page_label"],
                        "verbatim": psg["verbatim"]
                    })
                if passages:
                    passages_str = " | ".join(f"\"{psg['verbatim']}\" ({psg['page_label']})" for psg in passages)
                    block += f"- Bukti Verbatim (teks asli paper): {passages_str}\n"
            except Exception:
                pass

        context_blocks.append(block)

    full_context = "\n\n".join(context_blocks)
    step3_msg = f"Menyusun matriks dialektika komparatif ({len(context_blocks)} node silogisme) untuk sintesis akhir."
    thought_steps.append(step3_msg)
    console.print(f"[cyan]AGENT STEP 3[/cyan] [dim]{step3_msg}[/dim]")

    # Call LLM with Agentic Persona
    client = OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
    )

    user_prompt = (f"KORPUS (ringkasan AI belum diverifikasi; hanya 'Bukti Verbatim' yang teks asli):\n{full_context}"
                   f"\n\nPERTANYAAN PENELITI:\n{question}")

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": AGENTIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            timeout=180.0,
            stream=True,
        )
        if hasattr(resp, "choices"):
            msg = resp.choices[0].message
            content = (msg.content or "").strip()
            reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
            if reasoning:
                thought_steps.append(f"AI Reasoning Chain: {reasoning[:300]}...")
        else:
            parts = []
            reasoning_parts = []
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if getattr(delta, "reasoning_content", None):
                        reasoning_parts.append(delta.reasoning_content)
                    elif getattr(delta, "reasoning", None):
                        reasoning_parts.append(delta.reasoning)
                    if getattr(delta, "content", None):
                        parts.append(delta.content)
            content = "".join(parts).strip()
            if reasoning_parts:
                thought_steps.append(f"AI Reasoning Chain: {''.join(reasoning_parts)[:300]}...")

        # No silent switch to another model: the user must know which model answered.
        if "上游错误" in content or "out of API credit" in content:
            answer = (f"Model {model} sedang tidak bisa dipakai (kuota atau batas layanan). "
                      "Coba lagi nanti atau ganti model.")
        else:
            answer = content or f"Model {model} tidak menghasilkan jawaban. Coba lagi."
    except Exception as e:
        answer = f"Gagal menghasilkan jawaban dengan model {model}: {e}"

    try:
        from . import audit

        audit.log("tanya", mode="agen", question=question, model=model,
                  prompt_version=audit.prompt_version(AGENTIC_SYSTEM_PROMPT),
                  papers=[p.get("file") for p in referenced_papers],
                  passages=[f"{g['paper_title'][:60]} | {g['page_label']}" for g in all_grounded_citations])
    except Exception:
        pass

    return {
        "answer": answer,
        "thought_steps": thought_steps,
        "referenced_papers": referenced_papers,
        "grounded_citations": all_grounded_citations,
    }
