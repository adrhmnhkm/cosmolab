"""
CosmoLab University: Progressive Curriculum & Dynamic Syllabus Engine
Provides structured 4-tier learning pathways for each faculty,
plus an AI-powered dynamic syllabus generator for any custom philosophical subject.
"""

import json
from pathlib import Path
from openai import OpenAI
from rich.console import Console
from . import db
from . import config
from . import faculties as _faculties

console = Console(force_terminal=True, legacy_windows=False)

FACULTY_ROADMAP_CONFIGS = {
    "ilahiyyat": [
        {
            "level": 1,
            "title": "Level 1: Fondasi Silogisme & Tesis Utama",
            "description": "Membangun fondasi logika: Pelajari formulasi primer silogisme Kalam klasik vs modern, prinsip kontingensi, dan argumen sebab pertama.",
            "keywords": ["kalam", "cosmological", "contingency", "first-cause", "existence"],
        },
        {
            "level": 2,
            "title": "Level 2: Tantangan Matematika, Premis Implisit & Ketakhinggaan",
            "description": "Menguji daya tahan logika: Analisis kritis dari sudut pandang himpunan transfinit Cantor, rekonstruksi grafik premis, dan paradoks Hilbert.",
            "keywords": ["mathematician", "implicit premises", "argument graphs", "counterexample", "infinity", "cantor", "hilbert"],
        },
        {
            "level": 3,
            "title": "Level 3: Fisika Kuantum, Kosmologi Relativistik & Kausalitas",
            "description": "Mendalami benturan sains modern: Mekanika kuantum, gravitasi kuantum, nonlokalitas, dan termodinamika relativistik.",
            "keywords": ["quantum", "entanglement", "thermodynamics", "causality", "causal", "time and causality"],
        },
        {
            "level": 4,
            "title": "Level 4: Sintesis Lintas Disiplin, Fine-Tuning & Epistemologi",
            "description": "Tingkat mahir: Penyelidikan penyetelan sempurna (fine-tuning), evaluasi benturan epistemis teis vs ateis, dan batas kosmologi.",
            "keywords": ["fine-tuning", "atheist", "challenge", "compatibilidad", "comparative"],
        },
    ],
    "epistemologi": [
        {
            "level": 1,
            "title": "Level 1: Fondasi Teori Ilmu & Validitas Akal",
            "description": "Mengenal epistemologi teologis: Sumber pengetahuan (Pancaindra, Khabar Mutawatir, Akal Murni), dan justifikasi epistemik.",
            "keywords": ["knowledge", "epistemic", "epistemology", "foundationalism"],
        },
        {
            "level": 2,
            "title": "Level 2: Logika Silogisme Burhani vs Jadal",
            "description": "Mantiq demonstratif: Pembedaan antara silogisme demonstratif bernilai pasti (Burhan) vs dialektika debat (Jadal) vs asumsi retorika.",
            "keywords": ["burhan", "syllogism", "logic", "demonstration", "mantiq"],
        },
        {
            "level": 3,
            "title": "Level 3: Menyelesaikan Skeptisisme Radikal & Relativisme",
            "description": "Refleksi kritis atas keraguan inderawi dan rasional: Telaah Al-Ghazali (Al-Munqidh) dan pembedaan antara keraguan metodis vs skeptisisme mutlak.",
            "keywords": ["skepticism", "al-munqidh", "ghazali", "doubt"],
        },
        {
            "level": 4,
            "title": "Level 4: Epistemologi Kontemporer & Justifikasi Keyakinan",
            "description": "Diskursus modern: Reformed Epistemology Alvin Plantinga, reliabilisme, dan rasionalitas iman teistik tanpa argumen deduktif.",
            "keywords": ["plantinga", "reformed epistemology", "warrant", "justification"],
        },
    ],
    "kausalitas": [
        {
            "level": 1,
            "title": "Level 1: Fondasi Hukum Sebab-Akibat vs Okasionalisme",
            "description": "Mengenal debat klasik kausalitas: Sebab esensial Aristotelian/Avicennian vs Okasionalisme Asy'ariyah (korelasi kebiasaan 'Adah).",
            "keywords": ["causality", "causal", "occasionalism", "iqtiran"],
        },
        {
            "level": 2,
            "title": "Level 2: Skeptisisme David Hume & Problem Induksi",
            "description": "Bantahan empiris Hume atas keniscayaan kausal (Constant Conjunction) dan kesejajaran argumennya dengan Mas'alah 17 Tahafut Al-Ghazali.",
            "keywords": ["hume", "induction", "constant conjunction"],
        },
        {
            "level": 3,
            "title": "Level 3: Determinisme, Kasb, & Tanggung Jawab Moral",
            "description": "Problem kehendak bebas: Menelaah teori Kasb (akuisisi) mazhab Asy'ari di antara Jabariyah (fatalisme) dan Qadariyah/Mu'tazilah.",
            "keywords": ["kasb", "free will", "determinism", "foreknowledge", "predestination"],
        },
        {
            "level": 4,
            "title": "Level 4: Indeterminisme Fisika Kuantum & Aksi Ilahi",
            "description": "Integrasi kosmologi sains: Apakah indeterminisme mekanika kuantum membuka ruang ontologis bagi aksi Ilahi tanpa melanggar hukum alam?",
            "keywords": ["quantum indeterminism", "divine action", "quantum", "chaos"],
        },
    ],
    "teodisi": [
        {
            "level": 1,
            "title": "Level 1: Anatomi Problem of Evil (Logis vs Evidansial)",
            "description": "Memetakan paradoks kejahatan: Mengapa penderitaan ada di dunia ciptaan Tuhan Yang Maha Kuasa dan Maha Pengasih?",
            "keywords": ["evil", "suffering", "theodicy", "problem of evil"],
        },
        {
            "level": 2,
            "title": "Level 2: Teodisi Mazhab Kalam (Asy'ari, Maturidi, Mu'tazilah)",
            "description": "Membedah respons teologi Islam: Prinsip Kedaulatan Mutlak vs Prinsip Hikmah & Ibtila' vs Prinsip Kewajiban Moral Ilahi (Aslah wa Salah).",
            "keywords": ["hikmah", "ibtila", "syurur", "divine justice"],
        },
        {
            "level": 3,
            "title": "Level 3: Pembelaan Kehendak Bebas & Penderitaan Tanpa Guna",
            "description": "Debat analitik modern: Free Will Defense Alvin Plantinga vs Gratuitous Evil William Rowe (penderitaan hewan di alam liar).",
            "keywords": ["plantinga", "rowe", "gratuitous evil", "free will defense"],
        },
        {
            "level": 4,
            "title": "Level 4: Doktrin Dunia Terbaik & Transendensi Keadilan",
            "description": "Sintesis mendalam: Doktrin Al-Ghazali 'Laysa fi al-imkan abda' mimma kan' dan batas antropomorfisme dalam menilai moralitas Ilahi.",
            "keywords": ["best of all possible worlds", "abda", "ghazali"],
        },
    ],
    "falsafah_jiwa": [
        {
            "level": 1,
            "title": "Level 1: Eksperimen Manusia Terbang & Dualisme Substansi",
            "description": "Mengenal ontologi jiwa: Argumen Manusia Terbang (The Flying Man) Ibn Sina sebagai bukti keberadaan kesadaran terpisah dari materi fisik.",
            "keywords": ["flying man", "avicenna", "soul", "nafs", "dualism"],
        },
        {
            "level": 2,
            "title": "Level 2: The Hard Problem of Consciousness & Qualia",
            "description": "Tantangan fisikalisme: Mengapa ada 'pengalaman subjektif' (rasa sakit, warna) yang tidak dapat direduksi menjadi pergerakan neuron semata?",
            "keywords": ["consciousness", "qualia", "hard problem", "chalmers", "nagel"],
        },
        {
            "level": 3,
            "title": "Level 3: Materialisme, Eliminativisme & Skeptisisme Jiwa",
            "description": "Kritik nalar reduksionis: Menelaah pandangan Daniel Dennett bahwa kesadaran adalah ilusi evolusioner, dan menguji kelemahannya.",
            "keywords": ["physicalism", "materialism", "dennett", "reductionism", "brain"],
        },
        {
            "level": 4,
            "title": "Level 4: Falsafah Jiwa Kontemporer & Artificial Intelligence",
            "description": "Batas kecerdasan buatan: Dapatkah sistem AI memiliki jiwa, kehendak bebas, atau kesadaran sejati menurut ontologi Islam dan filsafat pikiran?",
            "keywords": ["artificial intelligence", "ai consciousness", "mind-body", "substance dualism"],
        },
    ],
    "nubuwwat": [
        {
            "level": 1,
            "title": "Level 1: Rasionalitas Kenabian & Otoritas Moral",
            "description": "Fondasi nubuwwat: Mengapa akal manusia membutuhkan wahyu untuk keteraturan sosial, kesempurnaan jiwa, dan panduan akhirat.",
            "keywords": ["prophecy", "prophet", "nubuwwat", "revelation"],
        },
        {
            "level": 2,
            "title": "Level 2: Konsep Mukjizat (Kharq al-'Adah) & Hukum Alam",
            "description": "Definisi mukjizat: Pembedaan antara hal mustahil secara akal (lingkaran bersudut) vs mustahil secara kebiasaan empiris (Kharq al-'Adah).",
            "keywords": ["miracle", "kharq", "adah", "laws of nature"],
        },
        {
            "level": 3,
            "title": "Level 3: Skeptisisme David Hume tentang Mukjizat",
            "description": "Bantahan analitik: Menilai argumen Hume bahwa kesaksian manusia tidak pernah bisa membuktikan mukjizat di hadapan keteraturan hukum alam.",
            "keywords": ["hume on miracles", "testimony", "skepticism"],
        },
        {
            "level": 4,
            "title": "Level 4: Harmoni Akal dan Teks Wahyu",
            "description": "Hermeneutika tingkat tinggi: Fasl al-Maqal Ibn Rushd, Qanun al-Ta'wil Al-Ghazali, dan penyelesaian konflik teks lahiriah dengan sains demonstratif.",
            "keywords": ["fasl al-maqal", "ta'wil", "hermeneutics", "reason and revelation"],
        },
    ],
}

UNIVERSAL_ROADMAP_TIERS = [
    {
        "level": 1,
        "title": "Level 1: Fondasi Teoretis & Kerangka Konseptual",
        "description": "Membangun landasan berpikir primer: Definisi ontologis, paradigma dasar, dan pemetaan literatur rujukan utama.",
        "keywords": ["foundation", "concept", "theory", "pengantar", "prinsip", "dasar", "paradigm", "kerangka", "fundamental"],
    },
    {
        "level": 2,
        "title": "Level 2: Metodologi, Model Empiris & Analisis Bukti",
        "description": "Mendalami instrumen riset: Desain penelitian, analisis data empiris, pengujian hipotesis, dan validitas metodologis.",
        "keywords": ["method", "empirical", "model", "analysis", "framework", "regresi", "kualitatif", "kuantitatif", "studi", "evaluation"],
    },
    {
        "level": 3,
        "title": "Level 3: Diskursus Komparatif, Anomali & Kritik Literatur",
        "description": "Menguji daya tahan argumen: Perbandingan antar-teori, anomali temuan terdahulu, dan sanggahan metodologis.",
        "keywords": ["critique", "comparative", "evaluasi", "tantangan", "limitations", "perbandingan", "debat", "challenge"],
    },
    {
        "level": 4,
        "title": "Level 4: Sintesis Kebaruan, Kebijakan & Isu Masa Depan",
        "description": "Tingkat mahir: Perumusan novelty riset, implikasi strategis/kebijakan, dan arah pengembangan keilmuan masa depan.",
        "keywords": ["synthesis", "novelty", "future", "kebijakan", "policy", "transformasi", "inovasi", "strategic", "kebaruan", "implication"],
    },
]


def get_learning_roadmap(faculty_id: str | None = None) -> list[dict]:
    """
    The Academic Advisor:
    Generates a structured 4-tier progressive reading roadmap from the corpus
    tailored to the chosen faculty (or across all faculties).
    """
    faculty_id = faculty_id or "ilahiyyat"
    config_tiers = FACULTY_ROADMAP_CONFIGS.get(faculty_id, UNIVERSAL_ROADMAP_TIERS)
    
    # Retrieve papers for this faculty
    all_papers = db.get_papers_by_faculty(faculty_id=faculty_id if faculty_id != "all" else None, limit=200)

    # Initialize tier buckets
    tier_buckets = [[] for _ in range(4)]

    for p in all_papers:
        title = (p.get("title") or "").lower()
        full_text = (p.get("full_text") or "")[:5000].lower()
        arg_t = p.get("argument_type") or "other"
        file_stem = (p.get("file") or "").replace(".pdf", "")

        item = {
            "file": p.get("file"),
            "stem": file_stem,
            "title": p.get("title"),
            "year": p.get("year", "n.d."),
            "argument_type": arg_t,
            "stance": p.get("supports_or_critiques", "neutral"),
            "thesis": p.get("thesis") or "Belum dianalisis",
            "key_objection": p.get("key_objection") or "-",
            "faculty": p.get("faculty") or faculty_id,
        }

        # Check keyword matches against tier configs (reversed from level 4 down to 1)
        placed = False
        for tier_idx in (3, 2, 1):
            kws = config_tiers[tier_idx].get("keywords", [])
            if any(k in title or k in full_text for k in kws):
                tier_buckets[tier_idx].append(item)
                placed = True
                break
        
        if not placed:
            tier_buckets[0].append(item)

    levels = []
    for idx, cfg in enumerate(config_tiers):
        levels.append({
            "level": cfg["level"],
            "title": cfg["title"],
            "description": cfg["description"],
            "papers": sorted(tier_buckets[idx], key=lambda x: str(x.get("year", "")), reverse=True),
        })

    return levels


AI_SYLLABUS_PROMPT = """Kamu adalah "The Academic Dean of CosmoLab University" — dekan multidisipliner yang menguasai kurikulum lintas bidang (humaniora, filsafat, agama, hukum, ekonomi, pendidikan, psikologi, sains, teknologi, kesehatan).
Tugasmu adalah menyusun SILABUS MATA KULIAH PROGRESIF 4-LEVEL untuk topik apa pun dari bidang mana pun yang diajukan oleh mahasiswa/peneliti, memakai kerangka dan bacaan baku bidang tersebut.

OUTPUT HARUS BERUPA JSON VALID dengan struktur persis seperti berikut:
{
  "course_title": "Judul Mata Kuliah / Topik Riset",
  "faculty_domain": "Nama Fakultas Terkait",
  "pedagogical_vision": "1-2 paragraf visi intelektual dari mata kuliah ini.",
  "learning_outcomes": ["Capaian 1", "Capaian 2", "Capaian 3"],
  "tiers": [
    {
      "tier_num": 1,
      "title": "Level 1: [Nama Tingkat Fondasi]",
      "description": "Fokus pembelajaran tingkat dasar.",
      "key_concepts": ["Konsep 1", "Konsep 2", "Konsep 3"],
      "milestone_task": "Tugas nalar mandiri untuk menuntaskan level ini."
    },
    {
      "tier_num": 2,
      "title": "Level 2: [Nama Tingkat Matan & Silogisme]",
      "description": "Fokus pembacaan teks matan dan dekonstruksi argumen.",
      "key_concepts": ["Konsep 1", "Konsep 2"],
      "milestone_task": "Tugas nalar mandiri."
    },
    {
      "tier_num": 3,
      "title": "Level 3: [Nama Tingkat Dialektika & Bantahan]",
      "description": "Fokus pengujian stres logika dan serangan lawan berpikir.",
      "key_concepts": ["Konsep 1", "Konsep 2"],
      "milestone_task": "Tugas nalar mandiri."
    },
    {
      "tier_num": 4,
      "title": "Level 4: [Nama Tingkat Sintesis Kontemporer]",
      "description": "Fokus integrasi dengan sains modern dan epistemologi.",
      "key_concepts": ["Konsep 1", "Konsep 2"],
      "milestone_task": "Tugas nalar mandiri."
    }
  ],
  "classic_turath_readings": ["Kitab 1 (Penulis)", "Kitab 2 (Penulis)"],
  "modern_academic_readings": ["Paper/Buku 1 (Penulis)", "Paper/Buku 2 (Penulis)"],
  "socratic_dilemma": "Dilema filosofis tajam yang paling mengguncang nalar pada topik ini.",
  "flashcards": [
    {"question": "Pertanyaan Active Recall 1?", "answer": "Jawaban presisi ringkas."},
    {"question": "Pertanyaan Active Recall 2?", "answer": "Jawaban presisi ringkas."},
    {"question": "Pertanyaan Active Recall 3?", "answer": "Jawaban presisi ringkas."}
  ]
}

Gunakan Bahasa Indonesia ilmiah yang elegan, mempertahankan istilah teknis Arab asli (misal: 'Wajib al-Wujud', 'Jawhar Fard', 'Harakah Jawhariyyah', 'Iqtiran') dan istilah analitik Barat yang tepat.
Kembalikan HANYA format JSON valid tanpa tanda kutip markdown backtick di luar JSON.
"""


def generate_ai_syllabus(topic_title: str, topic_description: str = "", model: str = None) -> dict:
    """Generate a full progressive university syllabus for any custom topic using LLM."""
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    user_prompt = f"Rancanglah silabus kurikulum universitas yang komprehensif untuk topik berikut:\n\nTOPIK UTAMA: {topic_title}\nDESKRIPSI / FOKUS KHUSUS: {topic_description or 'Kaji secara mendalam dari tradisi Kalam klasik dan filsafat analitik modern.'}"

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    raw_content = ""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": AI_SYLLABUS_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        raw_content = (resp.choices[0].message.content or "").strip()
        if not raw_content or "上游错误" in raw_content:
            fb = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": AI_SYLLABUS_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            raw_content = (fb.choices[0].message.content or "").strip()
    except Exception as e:
        console.print(f"[red]Error calling primary model for syllabus: {e}. Trying fallback...[/red]")
        try:
            fb = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": AI_SYLLABUS_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            raw_content = (fb.choices[0].message.content or "").strip()
        except Exception as e2:
            return {"error": f"Failed to generate syllabus: {e2}"}

    # Clean JSON markdown fences if present
    cleaned = raw_content
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("\n", 1)[0]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        return data
    except Exception:
        # Fallback dictionary
        return {
            "course_title": topic_title,
            "faculty_domain": "Kalam & Filsafat Terapan",
            "pedagogical_vision": raw_content[:400],
            "raw_text": raw_content,
            "tiers": [
                {"tier_num": 1, "title": "Level 1: Fondasi", "description": "Konsep dasar.", "key_concepts": [], "milestone_task": "Membaca teks primer."},
                {"tier_num": 2, "title": "Level 2: Silogisme", "description": "Rekonstruksi logika.", "key_concepts": [], "milestone_task": "Uji silogisme."},
                {"tier_num": 3, "title": "Level 3: Dialektika", "description": "Bantahan lawan.", "key_concepts": [], "milestone_task": "Sparring nalar."},
                {"tier_num": 4, "title": "Level 4: Sintesis", "description": "Integrasi modern.", "key_concepts": [], "milestone_task": "Menulis tesis sintesis."},
            ],
            "classic_turath_readings": [],
            "modern_academic_readings": [],
            "socratic_dilemma": "Bagaimana batas rasio dalam membuktikan hal transenden?",
            "flashcards": [],
        }


def save_syllabus_to_obsidian(syllabus: dict) -> Path:
    """Save an AI-generated curriculum as an Obsidian study guide markdown note."""
    config.ensure_dirs()
    curriculum_dir = config.OBSIDIAN_DIR / "curriculums"
    curriculum_dir.mkdir(parents=True, exist_ok=True)

    title = syllabus.get("course_title", "Kurikulum_Filsafat")
    safe_title = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in title).strip().replace(" ", "_")
    out_path = curriculum_dir / f"Syllabus_{safe_title}.md"

    md = f"""# 🏛️ CosmoLab University: {syllabus.get('course_title', 'Silabus Studi')}
**Fakultas / Domain:** {syllabus.get('faculty_domain', 'Multidisipliner')}
**Status:** Kurikulum Terverifikasi AI

---

## 🎯 Visi Pedagogis
{syllabus.get('pedagogical_vision', '')}

### Capaian Pembelajaran:
"""
    for lo in syllabus.get("learning_outcomes", []):
        md += f"- [ ] {lo}\n"

    md += "\n---\n\n## 🗺️ Tahapan Belajar 4-Tingkat\n\n"
    for t in syllabus.get("tiers", []):
        t_num = t.get("tier_num", "-")
        t_title = t.get("title", f"Level {t_num}")
        md += f"### {t_title}\n"
        md += f"*{t.get('description', '')}*\n\n"
        if t.get("key_concepts"):
            md += "**Konsep Kunci:** " + ", ".join([f"`{c}`" for c in t["key_concepts"]]) + "\n\n"
        if t.get("milestone_task"):
            md += f"🏁 **Milestone Uji Nalar:** {t['milestone_task']}\n\n"

    md += "---\n\n## 📚 Rujukan Wajib\n\n### 📜 Naskah Klasik Turāth:\n"
    for r in syllabus.get("classic_turath_readings", []):
        md += f"- 📖 {r}\n"

    md += "\n### 🔬 Riset & Debat Modern:\n"
    for r in syllabus.get("modern_academic_readings", []):
        md += f"- 📄 {r}\n"

    if syllabus.get("socratic_dilemma"):
        md += f"\n---\n\n## ⚡ Dilema Sokrates Inti\n> \"{syllabus.get('socratic_dilemma')}\"\n"

    if syllabus.get("flashcards"):
        md += "\n---\n\n## 🧠 Kartu Active Recall (Spaced Repetition)\n\n"
        for idx, fc in enumerate(syllabus["flashcards"], 1):
            md += f"#### #{idx} {fc.get('question')}\n?{fc.get('answer')}\n\n"

    out_path.write_text(md, encoding="utf-8")
    return out_path
