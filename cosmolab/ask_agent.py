import json
import re
from openai import OpenAI
from rich.console import Console
from . import config
from . import db
from . import retrieval

console = Console(force_terminal=True, legacy_windows=False)

AGENTIC_SYSTEM_PROMPT = """Kamu adalah CosmoLab, Asisten Peneliti Akademik Senior multidisipliner berbasis "Agentic Second Brain".
Kamu bekerja lintas bidang: humaniora, filsafat, agama, hukum, ekonomi, pendidikan, psikologi, sosial, sains, teknologi, dan kesehatan.
Kenali bidang pertanyaan, lalu pakai kerangka teori, metode, dan istilah baku bidang tersebut.

TUGAS UTAMA:
Jawablah pertanyaan pengguna dengan melakukan SINTESIS DIALEKTIS yang membandingkan kubu pendukung (proponents) dan kubu pengkritik (opponents) berdasarkan argumen, data, dan literatur yang ada dalam korpus, serta tradisi keilmuan utama di bidang tersebut.

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
- Berpijak pada literatur yang ada dalam korpus, dan bila korpus terbatas, katakan terus terang lalu lengkapi dengan penalaran akademik yang objektif.
"""


def _detect_query_intent(question: str) -> dict:
    """Analyze the user's question to determine argument type, faculty domain, and whether dialectical contrast is needed."""
    q_lower = question.lower()
    
    # Detect faculty domain
    faculty = "ilahiyyat"
    if any(k in q_lower for k in ("epistemol", "mantiq", "tahu", "pengetahuan", "skeptis", "burhan", "silogisme", "justifik")):
        faculty = "epistemologi"
    elif any(k in q_lower for k in ("sebab", "kausal", "akibat", "takdir", "kasb", "kehendak bebas", "free will", "determinism", "occasionalism", "hume", "iqtiran")):
        faculty = "kausalitas"
    elif any(k in q_lower for k in ("evil", "kejahatan", "penderitaan", "teodisi", "theodicy", "adil", "keberatan jahat", "derita")):
        faculty = "teodisi"
    elif any(k in q_lower for k in ("jiwa", "ruh", "nafs", "pikiran", "mind", "consciousness", "kesadaran", "qualia", "otak", "manusia terbang", "flying man", "ai")):
        faculty = "falsafah_jiwa"
    elif any(k in q_lower for k in ("nabi", "kenabian", "prophe", "nubuwwat", "mukjizat", "miracle", "wahyu", "kharq")):
        faculty = "nubuwwat"

    # Detect specific argument type
    arg_type = None
    if any(k in q_lower for k in ("kalam", "mulai ada", "begin to exist", "waktu", "temporal", "huduts")):
        arg_type = "kalam"
    elif any(k in q_lower for k in ("fine-tuning", "penyetelan", "konstanta", "multiverse")):
        arg_type = "fine-tuning"
    elif any(k in q_lower for k in ("contingency", "kontingensi", "leibniz", "cukup", "psr", "imkan")):
        arg_type = "contingency"
    elif any(k in q_lower for k in ("first cause", "sebab pertama", "aquinas")):
        arg_type = "first-cause"

    # Detect if contrast / objection is requested
    needs_contrast = any(k in q_lower for k in (
        "bantah", "kritik", "sanggah", "objeksi", "lawan", "kontra", "debat",
        "beda", "perbedaan", "banding", "apakah benar", "masalah", "kelemahan",
        "vs", "versus"
    ))

    return {
        "faculty": faculty,
        "argument_type": arg_type,
        "needs_contrast": needs_contrast,
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

    # If dialectical contrast is needed, ensure we have both 'supports' and 'critiques'
    if needs_contrast or len(referenced_papers) < 3:
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

    pro_count = len([p for p in referenced_papers if p.get("supports_or_critiques") == "supports"])
    contra_count = len([p for p in referenced_papers if p.get("supports_or_critiques") == "critiques"])
    step2_msg = f"Menjelajahi Second Brain: Menemukan {len(referenced_papers)} paper terstruktur ({pro_count} pendukung, {contra_count} pengkritik)."
    thought_steps.append(step2_msg)
    console.print(f"[cyan]AGENT STEP 2[/cyan] [dim]{step2_msg}[/dim]")

    if not referenced_papers:
        # Fallback to general list if empty
        all_p = db.get_all_papers_with_analyses()
        referenced_papers = [db.get_paper_knowledge_summary(p["file"]) for p in all_p if p.get("thesis")][:top_k]

    # Step 3: Build compact structured knowledge context (~1,200 - 2,000 tokens)
    context_blocks = []
    for idx, p in enumerate(referenced_papers, 1):
        year = p.get("year") or "n.d."
        title = p.get("title") or "Untitled"
        stance = p.get("supports_or_critiques") or "neutral"
        arg_t = p.get("argument_type") or "other"
        
        block = f"### [Paper {idx}] {title} ({year})\n"
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
            quotes_str = " | ".join(f"\"{q.get('text', '')}\" (Hal. {q.get('page_hint', 'N/A')})" for q in p.get("quotes")[:2])
            block += f"- Kutipan: {quotes_str}\n"
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

    user_prompt = f"KORPUS SECOND BRAIN (Struktur Logika Terverifikasi):\n{full_context}\n\nPERTANYAAN PENELITI:\n{question}"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": AGENTIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        msg = resp.choices[0].message
        content = (msg.content or "").strip()

        # Capture reasoning chain if available
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if reasoning:
            thought_steps.append(f"AI Reasoning Chain: {reasoning[:300]}...")

        # Fallback if upstream error occurs on primary model
        if "上游错误" in content or "out of API credit" in content:
            thought_steps.append(f"Model utama ({model}) mengalami limit upstream. Mengalihkan secara otomatis ke gemini-3-8-flash...")
            fallback_resp = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": AGENTIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            content = (fallback_resp.choices[0].message.content or "").strip()

        if not content and reasoning:
            content = reasoning.strip()

        answer = content or "Tidak ada jawaban yang dihasilkan oleh model."
    except Exception as e:
        # Retry with gemini-3-8-flash if primary model raised exception
        try:
            thought_steps.append(f"Mencoba fallback model ke gemini-3-8-flash karena: {e}")
            fallback_resp = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": AGENTIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            answer = (fallback_resp.choices[0].message.content or "").strip()
        except Exception as fallback_err:
            answer = f"Gagal menghasilkan sintesis agen: {e} | Fallback err: {fallback_err}"

    return {
        "answer": answer,
        "thought_steps": thought_steps,
        "referenced_papers": referenced_papers,
    }
