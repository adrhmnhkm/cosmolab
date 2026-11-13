"""
Fields of study (bidang ilmu): the built-in general fields plus custom fields
made by the team. Each paper gets one field, detected from its text or set by hand.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path
from . import config


@dataclass
class Faculty:
    id: str
    name: str
    icon: str
    short_desc: str
    full_desc: str
    default_queries: List[str]
    classic_references: List[str] = field(default_factory=list)
    modern_references: List[str] = field(default_factory=list)
    key_debates: List[str] = field(default_factory=list)
    is_custom: bool = False
    category: str = "Bidang umum"


CORE_FACULTIES: Dict[str, Faculty] = {
    "agama_filsafat": Faculty(
        id="agama_filsafat",
        name="Agama & Filsafat",
        icon="📜",
        short_desc="Studi agama, tafsir dan hadis, kalam dan tasawuf, filsafat, dan etika.",
        full_desc=(
            "Kajian teks dan pemikiran keagamaan (tafsir, hadis, kalam, tasawuf), agama dan masyarakat, "
            "filsafat (epistemologi, metafisika, etika, filsafat pikiran), serta hubungan agama dan sains."
        ),
        default_queries=[
            "islamic studies quranic exegesis hadith",
            "philosophy of religion existence of god",
            "islamic philosophy kalam epistemology",
            "religion and society religious moderation",
            "ethics moral philosophy virtue",
        ],
        classic_references=[
            "Al-Ghazali - Tahafut al-Falasifah",
            "Ibn Rusyd - Fasl al-Maqal",
            "Ibn Sina - Al-Isyarat wa al-Tanbihat",
        ],
        modern_references=[
            "Fazlur Rahman - Islam and Modernity",
            "Alvin Plantinga - Warranted Christian Belief",
            "Charles Taylor - A Secular Age",
        ],
        key_debates=[
            "Akal dan wahyu dalam epistemologi Islam",
            "Agama dan sains modern",
            "Moderasi beragama di ruang publik",
        ],
        category="Bidang umum",
    ),
    "hukum": Faculty(
        id="hukum",
        name="Hukum",
        icon="⚖️",
        short_desc="Hukum Tata Negara, Pidana, Perdata, Maqasid Syariah & Yurisprudensi Perbandingan.",
        full_desc=(
            "Mengkaji kepastian hukum, konstitusi, hak asasi manusia, yurisprudensi perbandingan mazhab fikih, "
            "maqasid al-syariah, pembaharuan hukum perdata/pidana modern, perlindungan konsumen, dan keadilan substantif."
        ),
        default_queries=[
            "constitutional law judicial review",
            "islamic jurisprudence fiqh maqasid shariah",
            "comparative criminal law human rights justice",
            "contract law corporate governance liability",
            "administrative law public policy governance",
        ],
        classic_references=[
            "Asy-Syathibi - Al-Muwafaqat fi Usul al-Syari'ah",
            "Ibn Rusyd - Bidayat al-Mujtahid wa Nihayat al-Muqtasid",
            "Al-Mawardi - Al-Ahkam al-Sulthaniyyah",
        ],
        modern_references=[
            "H.L.A. Hart - The Concept of Law",
            "John Rawls - A Theory of Justice",
            "Jasser Auda - Maqasid al-Shariah as Philosophy of Islamic Law",
        ],
        key_debates=[
            "Positivisme Hukum vs Hukum Kodrat & Keadilan Substantif",
            "Formalisme Tekstual Fikih vs Fleksibilitas Maqasid al-Syariah",
            "Independensi Lembaga Yudisial di Era Demokrasi Digital",
        ],
        category="Bidang umum",
    ),
    "ekonomi": Faculty(
        id="ekonomi",
        name="Ekonomi & Bisnis",
        icon="📈",
        short_desc="Manajemen Strategis, Keuangan Syariah, Akuntansi, Pemasaran & Perilaku Konsumen.",
        full_desc=(
            "Riset komprehensif teori manajemen, efisiensi pasar modal, perbankan syariah, ekonometrika mikro-makro, "
            "supply chain, kepemimpinan organisasi, inovasi fintech, dan perilaku konsumen digital."
        ),
        default_queries=[
            "islamic banking financial performance risk management",
            "behavioral economics decision making heuristics",
            "supply chain resilience digital transformation business",
            "corporate financial distress altman z score",
            "brand equity consumer behavior social media marketing",
        ],
        classic_references=[
            "Ibn Khaldun - Muqaddimah (Bab Produksi, Nilai & Pasar)",
            "Adam Smith - The Wealth of Nations",
            "Al-Ghazali - Ihya' 'Ulum al-Din (Kitab Adab al-Kasb wa al-Ma'asy)",
        ],
        modern_references=[
            "Michael Porter - Competitive Advantage & Competitive Strategy",
            "Daniel Kahneman - Thinking, Fast and Slow (Behavioral Economics)",
            "Philip Kotler - Marketing Management",
        ],
        key_debates=[
            "Riba, Murabahah vs Bagi Hasil Murni (Mudharabah/Musyarakah)",
            "Teori Pasar Efisien (EMH) vs Irrasionalitas Investor (Behavioral Finance)",
            "Disrupsi FinTech terhadap Ketahanan Perbankan Tradisional",
        ],
        category="Bidang umum",
    ),
    "pendidikan": Faculty(
        id="pendidikan",
        name="Pendidikan",
        icon="🎓",
        short_desc="Model Pembelajaran Abad 21, Evaluasi Pendidikan, EdTech & Manajemen Sekolah.",
        full_desc=(
            "Analisis pedagogi, teknologi pembelajaran (EdTech/AI in education), asesmen autentik, "
            "pengembangan kurikulum, psikologi perkembangan siswa, dan kepemimpinan sekolah/madrasah."
        ),
        default_queries=[
            "educational technology blended learning student engagement",
            "higher education curriculum pedagogical leadership",
            "critical thinking assessment rubrics learning outcomes",
            "project based learning stem education achievement",
            "teacher pedagogical competence professional development",
        ],
        classic_references=[
            "Al-Zarnuji - Ta'lim al-Muta'allim Tariq at-Ta'allum",
            "John Dewey - Democracy and Education",
            "Ibn Sahnun - Adab al-Mu'allimin",
        ],
        modern_references=[
            "Lev Vygotsky - Mind in Society (Zone of Proximal Development)",
            "Benjamin Bloom - Taxonomy of Educational Objectives",
            "Paulo Freire - Pedagogy of the Oppressed",
        ],
        key_debates=[
            "Pembelajaran Berbasis AI / Adaptif vs Sentuhan Kemanusiaan Guru",
            "Standarisasi Ujian Nasional vs Asesmen Formatif Holistik",
            "Pendidikan Vokasi Terapan vs Pembentukan Karakter & Literasi Kritis",
        ],
        category="Bidang umum",
    ),
    "psikologi_sosial": Faculty(
        id="psikologi_sosial",
        name="Psikologi & Sosial",
        icon="🧠",
        short_desc="Kesehatan Mental, Dinamika Sosial, Komunikasi, Sosiologi & Perilaku.",
        full_desc=(
            "Kajian psikologi klinis & kognitif, resiliensi emosional, komunikasi massa, sosiologi perubahan masyarakat, "
            "dinamika kelompok, dan interaksi budaya di era masyarakat digital."
        ),
        default_queries=[
            "social psychology subjective well being resilience",
            "anxiety depression mental health adolescents cognitive therapy",
            "organizational culture burnout job satisfaction",
            "social media public polarization discourse analysis",
            "intercultural communication social identity theory",
        ],
        classic_references=[
            "Abu Zayd al-Balkhi - Mashalih al-Abdan wa al-Anfus",
            "Ibn Hazm - Tawq al-Hamamah fi al-Ulfah wa al-Ullaf",
            "Aristotle - Rhetoric & Politics",
        ],
        modern_references=[
            "Albert Bandura - Social Learning Theory & Self-Efficacy",
            "Sigmund Freud - The Interpretation of Dreams",
            "Erving Goffman - The Presentation of Self in Everyday Life",
        ],
        key_debates=[
            "CBT (Cognitive Behavioral Therapy) vs Pendekatan Spiritual / Sufistik",
            "Dampak Algoritma Media Sosial terhadap Gelembung Filter (Echo Chambers)",
            "Budaya Hustle & Burnout Kerja di Kalangan Generasi Z",
        ],
        category="Bidang umum",
    ),
    "sains_teknologi": Faculty(
        id="sains_teknologi",
        name="Sains & Teknologi",
        icon="🔬",
        short_desc="Artificial Intelligence, Software Engineering, Energi Terbarukan & Data Science.",
        full_desc=(
            "Eksplorasi algoritma machine learning/deep learning, rekayasa perangkat lunak, arsitektur cloud, "
            "keamanan siber, IoT, optimasi energi hijau terbarukan, dan sains komputasi material."
        ),
        default_queries=[
            "deep learning convolutional neural network transformer",
            "software engineering microservices clean architecture",
            "renewable energy photovoltaic solar cell efficiency",
            "cybersecurity anomaly intrusion detection system",
            "internet of things edge computing latency optimization",
        ],
        classic_references=[
            "Al-Khwarizmi - Kitab al-Jabr wa'l-Muqabala",
            "Al-Biruni - Kitab al-Tafhim li Awa'il Sina'at al-Tanjim",
            "Ibn al-Haytham - Kitab al-Manazir (Book of Optics)",
        ],
        modern_references=[
            "Stuart Russell & Peter Norvig - Artificial Intelligence: A Modern Approach",
            "Martin Fowler - Refactoring & Patterns of Enterprise Architecture",
            "Richard Feynman - The Feynman Lectures on Physics",
        ],
        key_debates=[
            "Etika Model Generatif AI, Hak Cipta & Bias Data Latih",
            "Komputasi Awan (Cloud) Sentral vs Edge Computing & Privasi Data",
            "Transisi Baterai EV vs Keterbatasan Pasokan Logam Langka",
        ],
        category="Bidang umum",
    ),
    "kesehatan": Faculty(
        id="kesehatan",
        name="Kesehatan",
        icon="🩺",
        short_desc="Epidemiologi, Manajemen RS, Farmakologi Klinis, Gizi & Promosi Kesehatan.",
        full_desc=(
            "Studi prevalensi penyakit, efektivitas terapi klinis, mutu pelayanan rumah sakit (akreditasi/BPJS), "
            "nutrisi penanganan stunting, farmasi klinik, serta kebijakan kesehatan masyarakat."
        ),
        default_queries=[
            "public health epidemiology chronic disease prevention",
            "clinical pharmacology randomized controlled trial efficacy",
            "hospital management healthcare service quality patient satisfaction",
            "stunting malnutrition maternal child health intervention",
            "telemedicine digital health adoption accessibility",
        ],
        classic_references=[
            "Ibn Sina - Al-Qanun fi al-Tibb (The Canon of Medicine)",
            "Al-Razi - Kitab al-Hawi fi al-Tibb (Continens Liber)",
            "Al-Zahrawi - Kitab al-Tasrif (Pionir Bedah Medis)",
        ],
        modern_references=[
            "David L. Sackett - Evidence-Based Medicine",
            "Leon Gordis - Epidemiology",
            "WHO - Guidelines for Quality of Care in Health Facilities",
        ],
        key_debates=[
            "Pemberian Layanan Universal (UHC/BPJS) vs Keberlanjutan Finansial RS",
            "Telemedicine vs Diagnosis Tatap Muka Langsung",
            "Intervensi Spesifik Gizi vs Sensitif Sosial dalam Penurunan Stunting",
        ],
        category="Bidang umum",
    ),
    "bahasa_sastra": Faculty(
        id="bahasa_sastra",
        name="Bahasa & Sastra",
        icon="📚",
        short_desc="Linguistik, pengajaran bahasa, penerjemahan, analisis wacana, dan kajian sastra.",
        full_desc=(
            "Linguistik (pragmatik, sosiolinguistik, morfologi, sintaksis), pengajaran bahasa Indonesia, Inggris, "
            "dan Arab, penerjemahan, analisis wacana, serta kritik dan kajian sastra."
        ),
        default_queries=[
            "english language teaching efl speaking writing skill",
            "sociolinguistics code switching bilingual",
            "pragmatics speech acts politeness",
            "critical discourse analysis media",
            "literary criticism postcolonial literature",
        ],
        classic_references=[
            "Ferdinand de Saussure - Course in General Linguistics",
            "Abd al-Qahir al-Jurjani - Dala'il al-I'jaz",
            "Mikhail Bakhtin - The Dialogic Imagination",
        ],
        modern_references=[
            "Norman Fairclough - Critical Discourse Analysis",
            "Stephen Krashen - Principles and Practice in Second Language Acquisition",
            "Penelope Brown & Stephen Levinson - Politeness",
        ],
        key_debates=[
            "Pembelajaran bahasa komunikatif vs tata bahasa",
            "Penerjemahan mesin vs penerjemah manusia",
            "Bahasa daerah di tengah bahasa nasional dan global",
        ],
        category="Bidang umum",
    ),
    "umum": Faculty(
        id="umum",
        name="Lintas bidang & metodologi",
        icon="🧭",
        short_desc="Metodologi riset, dan paper yang belum cocok dengan bidang lain.",
        full_desc=(
            "Metodologi penelitian, penulisan ilmiah, statistik terapan, dan paper lintas bidang. "
            "Paper yang tidak cocok dengan bidang lain masuk ke sini sampai dipindah manual."
        ),
        default_queries=[
            "systematic literature review methodology",
            "mixed methods research design",
            "structural equation modeling pls-sem",
            "qualitative research thematic analysis",
            "research ethics academic integrity",
        ],
        classic_references=[
            "John W. Creswell - Research Design",
            "Robert K. Yin - Case Study Research",
            "Wayne C. Booth et al. - The Craft of Research",
        ],
        modern_references=[
            "Joseph F. Hair et al. - A Primer on PLS-SEM",
            "Virginia Braun & Victoria Clarke - Thematic Analysis",
            "Matthew J. Page et al. - PRISMA 2020 Statement",
        ],
        key_debates=[
            "Kuantitatif, kualitatif, atau metode campuran",
            "Krisis replikasi dan praktik sains terbuka",
            "Penggunaan AI dalam penulisan ilmiah",
        ],
        category="Bidang umum",
    ),
}

# The six philosophy and theology fields of the first version were merged into
# agama_filsafat (13 Nov 2026). Papers still carrying an old id are classified
# again from their text (see resolve_faculty and db.init_db).
LEGACY_IDS = {
    "ilahiyyat": "agama_filsafat",
    "epistemologi": "agama_filsafat",
    "kausalitas": "agama_filsafat",
    "teodisi": "agama_filsafat",
    "falsafah_jiwa": "agama_filsafat",
    "nubuwwat": "agama_filsafat",
}
DEFAULT_FACULTY = "umum"


def canonical_id(faculty_id: Optional[str]) -> str:
    """Current id for a faculty id, mapping the old philosophy ids to agama_filsafat."""
    return LEGACY_IDS.get(faculty_id or "", faculty_id or "")


def resolve_faculty(faculty_id: Optional[str], title: str = "", abstract: str = "", full_text: str = "") -> str:
    """Faculty to store for a paper: a current id is kept; an old or missing one is detected from the text."""
    if faculty_id and faculty_id not in LEGACY_IDS:
        return faculty_id
    return detect_faculty_from_text(title, abstract, full_text)

# Dynamic storage pointer. None = follow the active project (config.ROOT).
CUSTOM_FACULTIES_FILE = None


def _custom_faculties_file() -> Path:
    return CUSTOM_FACULTIES_FILE or (config.ROOT / "custom_faculties.json")


def _sanitize_slug(text: str) -> str:
    """Generate a clean ASCII identifier slug."""
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", s)


def load_custom_faculties() -> Dict[str, Faculty]:
    """Load user-defined custom faculties from data/custom_faculties.json."""
    if not _custom_faculties_file().exists():
        return {}
    try:
        data = json.loads(_custom_faculties_file().read_text(encoding="utf-8"))
        result = {}
        for item in data:
            fac = Faculty(
                id=item["id"],
                name=item["name"],
                icon=item.get("icon", "🎓"),
                short_desc=item.get("short_desc", ""),
                full_desc=item.get("full_desc", ""),
                default_queries=item.get("default_queries", []),
                classic_references=item.get("classic_references", []),
                modern_references=item.get("modern_references", []),
                key_debates=item.get("key_debates", []),
                is_custom=True,
                category=item.get("category", "Kustom Peneliti"),
            )
            result[fac.id] = fac
        return result
    except Exception:
        return {}


def save_custom_faculty(
    name: str,
    default_queries: List[str],
    icon: str = "🎓",
    short_desc: str = "",
    full_desc: str = "",
    faculty_id: Optional[str] = None,
    category: str = "Kustom Peneliti",
    classic_references: Optional[List[str]] = None,
    modern_references: Optional[List[str]] = None,
    key_debates: Optional[List[str]] = None,
) -> Faculty:
    """
    Register a new custom faculty or update an existing one.
    Persists immediately to custom_faculties.json.
    """
    config.ensure_dirs()
    f_id = _sanitize_slug(faculty_id or name)
    if not f_id:
        f_id = f"faculty_{int(Path().stat().st_mtime)}"

    new_fac = Faculty(
        id=f_id,
        name=name.strip(),
        icon=icon.strip() or "🎓",
        short_desc=short_desc.strip() or f"Program Studi / Fokus Riset {name.strip()}",
        full_desc=full_desc.strip() or f"Koleksi literatur dan riset terarah untuk {name.strip()}.",
        default_queries=[q.strip() for q in default_queries if q.strip()],
        classic_references=classic_references or [],
        modern_references=modern_references or [],
        key_debates=key_debates or [],
        is_custom=True,
        category=category,
    )

    customs = load_custom_faculties()
    customs[f_id] = new_fac

    # Save to disk
    serialized = [asdict(f) for f in customs.values()]
    _custom_faculties_file().parent.mkdir(parents=True, exist_ok=True)
    _custom_faculties_file().write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Keep global dict synchronized
    _sync_global_faculties()
    return new_fac


def delete_custom_faculty(faculty_id: str) -> bool:
    """Delete a custom faculty by ID."""
    customs = load_custom_faculties()
    if faculty_id in customs:
        del customs[faculty_id]
        serialized = [asdict(f) for f in customs.values()]
        _custom_faculties_file().write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")
        _sync_global_faculties()
        return True
    return False


def _get_all_faculties_dict() -> Dict[str, Faculty]:
    """Combine core faculties with dynamically loaded custom faculties."""
    all_facs = dict(CORE_FACULTIES)
    all_facs.update(load_custom_faculties())
    return all_facs


def _sync_global_faculties():
    global FACULTIES
    FACULTIES.clear()
    FACULTIES.update(_get_all_faculties_dict())


# Initialize FACULTIES dict for backward compatibility
FACULTIES: Dict[str, Faculty] = _get_all_faculties_dict()


def get_faculty(faculty_id: str) -> Optional[Faculty]:
    """
    Retrieve a faculty by its ID.
    If it's an ad-hoc unregistered name, returns a graceful dynamic Faculty object.
    """
    all_facs = _get_all_faculties_dict()
    faculty_id = canonical_id(faculty_id)
    if faculty_id in all_facs:
        return all_facs[faculty_id]

    # If completely unknown (e.g. ad-hoc user query), create a virtual placeholder
    clean_id = (faculty_id or "umum").strip().lower()
    return Faculty(
        id=clean_id,
        name=clean_id.replace("_", " ").title(),
        icon="🎓",
        short_desc=f"Disiplin Riset: {clean_id.replace('_', ' ').title()}",
        full_desc="Bidang riset kustom peneliti.",
        default_queries=[clean_id.replace("_", " ")],
        is_custom=True,
        category="Kustom Peneliti",
    )


def list_faculties(category: Optional[str] = None) -> List[Faculty]:
    """List all registered faculties, optionally filtered by category."""
    all_facs = list(_get_all_faculties_dict().values())
    if category:
        return [f for f in all_facs if f.category == category]
    return all_facs


def detect_faculty_from_text(title: str, abstract: str = "", full_text: str = "") -> str:
    """
    Heuristic rule to classify a paper into one of the faculties based on keyword frequency.
    Supports core theological, multidisciplinary, and custom faculties.
    """
    text = f"{title} {abstract} {full_text[:3000]}".lower()

    # Keywords per field. A keyword matches at the start of a word; keywords of
    # four letters or fewer must match the whole word (so "ai" does not match "said").
    keywords: Dict[str, List[str]] = {
        "agama_filsafat": [
            "teologi", "theolog", "tafsir", "exegesis", "hadis", "hadith", "quran", "qur'an", "al-qur",
            "akidah", "aqidah", "kalam", "kalām", "tasawuf", "sufi", "dakwah", "moderasi beragama", "religious",
            "religion", "keagamaan", "filsafat", "philosoph", "metaphysic", "ontolog", "epistemolog",
            "moral philosophy", "existence of god", "god's existence", "cosmological argument", "fine-tuning",
            "wajib al-wujud", "ilahiyyat", "occasionalism", "free will", "determinism", "predestination",
            "takdir", "problem of evil", "theodicy", "teodisi", "divine", "soul", "nafs", "consciousness",
            "qualia", "dualism", "physicalism", "prophecy", "prophet", "nabi", "miracle", "mukjizat",
            "revelation", "wahyu", "hermeneutic", "syllogism", "mantiq", "skepticism", "hume", "ghazali",
            "ibn sina", "avicenna",
        ],
        "hukum": [
            "hukum", "yuridis", "rule of law", "criminal law", "civil law", "islamic law", "legal", "syariah", "shariah", "fiqh", "jurisprudence", "constitutional",
            "hak asasi", "pidana", "perdata", "yurisprudensi", "peradilan", "undang-undang", "regulatif",
            "regulasi", "perlindungan data", "cyber law", "uu pdp", "hak cipta", "kebijakan publik", "advokasi",
        ],
        "ekonomi": [
            "ekonomi", "economic", "finance", "financial", "banking", "manajemen", "management", "bisnis",
            "business", "akuntansi", "accounting", "pemasaran", "marketing", "saham", "murabahah", "fintech",
            "laba", "profitability", "umkm", "pembiayaan", "modal", "kredit", "investasi", "msme", "sme",
            "usaha mikro", "perbankan syariah", "kinerja keuangan",
        ],
        "pendidikan": [
            "pendidikan", "education", "pedagog", "curriculum", "kurikulum", "pembelajaran",
            "learning", "siswa", "student", "teacher", "guru", "sekolah", "edtech", "didaktik", "hasil belajar",
            "modul ajar", "media pembelajaran", "evaluasi pembelajaran",
        ],
        "psikologi_sosial": [
            "psikologi", "psychology", "mental health", "kecemasan", "anxiety", "depression", "depresi",
            "resilience", "burnout", "sociology", "sosiologi", "komunikasi", "social behavior", "perilaku",
            "kesejahteraan subjektif", "interaksi sosial",
        ],
        "sains_teknologi": [
            "machine learning", "deep learning", "artificial intelligence", "algorithm", "software",
            "cloud computing", "iot", "sensor", "cybersecurity", "teknik", "rekayasa", "renewable energy",
            "solar cell", "ai", "etika ai", "data pribadi", "privasi", "siber", "informatika", "komputasi",
            "distributed", "optimization", "network", "quantum", "physics", "fisika", "relativity", "gravity",
            "gravitation", "thermodynamic", "entanglement", "cosmology", "astrophysic", "mathematic",
            "matematika", "dynamical system",
        ],
        "kesehatan": [
            "kesehatan", "health", "hospital", "rumah sakit", "clinical", "klinis", "epidemiology",
            "epidemiologi", "patient", "pasien", "stunting", "gizi", "nutrition", "pharmacology", "farmasi",
            "kedokteran", "faskes", "bpjs kesehatan", "keperawatan", "rekam medis",
        ],
        "bahasa_sastra": [
            "linguistik", "linguistic", "sastra", "literary", "puisi", "poetry", "cerpen", "pragmatik",
            "pragmatics", "semantik", "sintaksis", "morfologi", "fonologi", "sosiolinguistik",
            "sociolinguistic", "wacana", "discourse", "penerjemahan", "translation studies", "efl", "esl",
            "english language teaching", "bahasa inggris", "bahasa arab", "bahasa indonesia",
            "speaking skill", "writing skill", "reading comprehension", "keterampilan menulis",
            "keterampilan berbicara", "code switching", "alih kode",
        ],
    }

    # Add custom faculty keywords dynamically
    custom_facs = load_custom_faculties()
    for c_id, c_fac in custom_facs.items():
        c_kws = [w.lower() for w in re.findall(r"\w+", c_fac.name) if len(w) > 3]
        for q in c_fac.default_queries:
            c_kws.extend([w.lower() for w in re.findall(r"\w+", q) if len(w) > 3])
        keywords[c_id] = list(set(c_kws))

    scores = {f_id: 0 for f_id in keywords.keys()}

    title_l = (title or "").lower()
    for f_id, kws in keywords.items():
        for kw in kws:
            pattern = re.compile(r"\b" + re.escape(kw) + (r"\b" if len(kw) <= 4 else ""))
            if pattern.search(text):
                # Give higher weight to matches in the title
                scores[f_id] += 3 if pattern.search(title_l) else 1

    best_faculty = max(scores, key=scores.get)
    if scores[best_faculty] == 0:
        return DEFAULT_FACULTY
    return best_faculty
