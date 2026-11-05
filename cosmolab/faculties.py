"""
CosmoLab University: Knowledge Architecture & Faculty Catalog
Defines the core philosophy & theology faculties,
expanded multidisciplinary faculties (Hukum, Ekonomi, Pendidikan, Sains/Teknologi, Psikologi, Kesehatan),
and a dynamic custom faculty engine for any university department or research niche.
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
    category: str = "Filosofis & Teologis"


CORE_FACULTIES: Dict[str, Faculty] = {
    # -------------------------------------------------------------
    # 1. Fondasi Filosofis & Teologis Klasik
    # -------------------------------------------------------------
    "ilahiyyat": Faculty(
        id="ilahiyyat",
        name="Ilahiyyat & Kosmologi Rasional",
        icon="🌌",
        short_desc="Eksistensi Tuhan, Argumen Kosmologis, Teleologis, Wajib al-Wujud & Awal Mula Alam.",
        full_desc=(
            "Mengkaji argumen rasional tentang pembuktian adanya Pencipta: Dalil Huduts (Kalam), "
            "Dalil Imkan / Kontingensi (Ibn Sina & Leibniz), Dalil Inayah/Hikmah (Teleologis/Fine-Tuning), "
            "status ontologis Wajib al-Wujud, dan benturan dengan model kosmologi fisika modern (Multiverse, Singularitas, Vakum Kuantum)."
        ),
        default_queries=[
            "kalam cosmological argument",
            "contingency cosmological argument",
            "fine-tuning teleological argument",
            "ibn sina burhan al-siddiqin",
            "actual infinity hilbert paradox cosmology",
        ],
        classic_references=[
            "Al-Ghazali - Tahafut al-Falasifah (Mas'alah 1: Qidam al-'Alam)",
            "Ibn Sina - Al-Isyarat wa al-Tanbihat (Namat 4: Al-Wujud wa 'Ilaluh)",
            "Fakhr al-Din al-Razi - Al-Matalib al-'Aliyah min al-'Ilm al-Ilahi",
            "Sa'aduddin at-Taftazani - Syarh al-Aqa'id an-Nasafiyyah",
        ],
        modern_references=[
            "William Lane Craig - The Kalam Cosmological Argument",
            "Alexander Pruss - The Principle of Sufficient Reason",
            "Robin Collins - The Teleological Argument: An Exploration of the Fine-Tuning",
            "Graham Oppy - Arguing about Gods",
        ],
        key_debates=[
            "Ketakterhinggaan Waktu Lampau (Tahallul vs Cantorian Actual Infinity)",
            "Fluktuasi Kuantum Ruang Hampa vs Prinsip Kausalitas",
            "Prinsip Alasan Cukup (PSR) vs Kosmos sebagai Fakta Mentah (Brute Fact)",
        ],
        category="Filosofis & Teologis",
    ),
    "epistemologi": Faculty(
        id="epistemologi",
        name="Epistemologi & Mantiq (Teori Pengetahuan)",
        icon="🏛️",
        short_desc="Validitas Akal, Sumber Pengetahuan, Silogisme Burhani, Skeptisisme & Relativisme.",
        full_desc=(
            "Fondasi metodologis penalaran akidah: Teori ilmu dalam Kalam, sumber pengetahuan (Khabar Shadiq/Otoritas, "
            "Pancaindra, Akal Murni, dan Ilham/Kasyaf), pembedaan antara nalar demonstratif (Burhan) vs dialektika (Jadal) "
            "vs retorika (Khitabah), serta penyelesaian skeptisisme radikal."
        ),
        default_queries=[
            "islamic epistemology theory of knowledge kalam",
            "al-ghazali skepticism al-munqidh min al-dalal",
            "burhan demonstrative syllogism islamic philosophy",
            "epistemic justification foundationalism coherentism",
            "reformed epistemology alvin plantinga",
        ],
        classic_references=[
            "Al-Ghazali - Al-Mustasfa (Muqaddimah Mantiqiyyah) & Al-Munqidh min al-Dalal",
            "Al-Farabi - Kitab al-Burhan",
            "Ibn Hazm - Al-Taqrib li-Hadd al-Mantiq",
            "Qadhi Abdul Jabbar - Al-Mughni fi Abwab al-Tawhid wa al-'Adl",
        ],
        modern_references=[
            "Alvin Plantinga - Warrant and Proper Function",
            "Seyyed Hossein Nasr - Knowledge and the Sacred",
            "Ernest Sosa - A Virtue Epistemology",
            "Richard Swinburne - Faith and Reason",
        ],
        key_debates=[
            "Apakah akal mandiri menentukan kebenaran teologis sebelum datangnya wahyu?",
            "Skeptisisme Indrawi Al-Ghazali vs Fondasionalisme Cogito Descartes",
            "Status epistemologis mukjizat sebagai bukti kebenaran kabar",
        ],
        category="Filosofis & Teologis",
    ),
    "kausalitas": Faculty(
        id="kausalitas",
        name="Kausalitas, Takdir & Kehendak Bebas",
        icon="⚡",
        short_desc="Sebab-Akibat, Okasionalisme, Determinisme, Kasb Asy'ari vs Ikhtiyar Mu'tazili.",
        full_desc=(
            "Penyelidikan mendalam tentang hukum sebab-akibat: Apakah alam semesta beroperasi dengan keniscayaan kausal esensial "
            "(Aristoteles/Ibn Sina) ataukah sekadar korelasi kebiasaan konstan yang terus diciptakan Tuhan (Okasionalisme Al-Ghazali / Hume)? "
            "Dilanjutkan dengan diskursus kehendak bebas manusia, tanggung jawab moral, dan ilmu Tuhan yang mendahului masa depan (Divine Foreknowledge)."
        ),
        default_queries=[
            "occasionalism al-ghazali causality tahafut",
            "hume causality induction constant conjunction",
            "divine foreknowledge human free will compatibility",
            "asharite theory of kasb acquisition",
            "quantum indeterminism divine action free will",
        ],
        classic_references=[
            "Al-Ghazali - Tahafut al-Falasifah (Mas'alah 17: Al-Sababiyyah)",
            "Ibn Rushd - Tahafut al-Tahafut (Sanggahan Kausalitas)",
            "Al-Baqillani - Kitab al-Tamhid",
            "Al-Jurjani - Syarh al-Mawaqif fi 'Ilm al-Kalam",
        ],
        modern_references=[
            "David Hume - An Enquiry Concerning Human Understanding (Section IV & VII)",
            "Walter Fred - Occasionalism: Causation Among the Cartesians",
            "Peter van Inwagen - An Essay on Free Will",
            "Eleonore Stump - Aquina's Account of Free Will",
        ],
        key_debates=[
            "Apakah api membakar kapas karena esensinya sendiri atau karena kehendak Ilahi yang menciptakan pembakaran?",
            "Teori Kasb: Sintesis brilian antara kemahakuasaan Tuhan dan tanggung jawab manusia ataukah ilusi kompatibilisme?",
            "Pengetahuan Tuhan atas masa depan: Apakah menutup kemungkinan pilihan bebas manusia?",
        ],
        category="Filosofis & Teologis",
    ),
    "teodisi": Faculty(
        id="teodisi",
        name="Teodisi & Problem of Evil (Al-Syurur wa al-'Adl)",
        icon="⚖️",
        short_desc="Keadilan Ilahi, Eksistensi Penderitaan, Hikmah Bencana, Problem Logis & Bukti Kejahatan.",
        full_desc=(
            "Salah satu tantangan terberat bagi teisme: Jika Tuhan Maha Kuasa, Maha Mengetahui, dan Maha Pengasih, "
            "mengapa kejahatan dan penderitaan ada di dunia? Membedah perspektif Teodisi Asy'ariyah (kedaulatan mutlak Ilahi di luar konsep kewajiban moral manusia), "
            "Maturidiyah (prinsip Hikmah di balik setiap ciptaan), Mu'tazilah (keharusan berbuat adil), dan pembelaan kehendak bebas kontemporer."
        ),
        default_queries=[
            "problem of evil philosophy of religion",
            "theodicy divine justice suffering kalam",
            "alvin plantinga free will defense evil",
            "evidential problem of evil william rowe",
            "al-ghazali best of all possible worlds laysa fi al-imkan",
        ],
        classic_references=[
            "Al-Ghazali - Ihya' 'Ulum al-Din (Kitab al-Tawhid wa al-Tawakkul: Konsep Dunia Terbaik)",
            "Al-Maturidi - Kitab al-Tawhid (Bab Hikmah wa al-Ibtila')",
            "Abu Bakr al-Razi vs Ahmad bin Hamdan - Al-Munazarat",
            "Ibn al-Qayyim - Syifa' al-'Alil fi Masa'il al-Qadha' wa al-Qadar wa al-Hikmah",
        ],
        modern_references=[
            "J.L. Mackie - Evil and Omnipotence",
            "Alvin Plantinga - God, Freedom, and Evil",
            "William Rowe - The Problem of Evil and Some Varieties of Atheism",
            "Marilyn McCord Adams - Horrendous Evils and the Goodness of God",
        ],
        key_debates=[
            "Kejahatan Tanpa Manfaat Nyata (Gratuitous Evil): Apakah penderitaan hewan di alam liar menggugurkan teisme?",
            "Apakah konsep 'Kebaikan' Tuhan setara dengan konsep kebaikan moral manusia (Analogi vs Equivocation)?",
            "Pernyataan Al-Ghazali: 'Laysa fi al-imkan abda' mimma kan' (Tidak ada dalam kemungkinan yang lebih indah dari apa yang telah diciptakan).",
        ],
        category="Filosofis & Teologis",
    ),
    "falsafah_jiwa": Faculty(
        id="falsafah_jiwa",
        name="Falsafah Jiwa & Pikiran (Ilm an-Nafs)",
        icon="🧠",
        short_desc="Hakekat Nafs & Ruh, Dualisme Jiwa-Raga, Hard Problem of Consciousness, AI & Jiwa.",
        full_desc=(
            "Penyelidikan hakekat eksistensi manusia: Apakah kesadaran hanyalah aktivitas elektrokimia otak fisik (Fisikalisme/Materialisme) "
            "ataukah jiwa adalah substansi immaterial non-fisik (Dualisme Substansi Ibn Sina / Descartes)? "
            "Menghubungkan argumen klasik Manusia Terbang (The Flying Man) dengan misteri kesadaran modern (Qualia) dan batas kecerdasan artifisial."
        ),
        default_queries=[
            "islamic philosophy mind nafs soul avicenna",
            "ibn sina flying man argument dualism",
            "hard problem of consciousness physicalism qualia",
            "substance dualism cartesian mind body problem",
            "artificial intelligence consciousness soul philosophy",
        ],
        classic_references=[
            "Ibn Sina - Kitab al-Syifa (Al-Nafs / De Anima & Argumen Manusia Terbang)",
            "Al-Ghazali - Ma'arij al-Quds fi Madarij Ma'rifat al-Nafs",
            "Ibn al-Nafis - Al-Risalah al-Kamiliyyah fi al-Sirah al-Nabawiyyah",
            "Mulla Sadra - Al-Hikmah al-Muta'aliyah (Harakah Jawhariyyah an-Nafs)",
        ],
        modern_references=[
            "David Chalmers - The Conscious Mind: In Search of a Fundamental Theory",
            "Daniel Dennett - Consciousness Explained (Kritik Ilusionisme)",
            "Thomas Nagel - What Is It Like to Be a Bat?",
            "Richard Swinburne - The Evolution of the Soul",
        ],
        key_debates=[
            "Argumen Manusia Terbang Ibn Sina: Bukti independensi jiwa atau sekadar eksperimen pikiran spekulatif?",
            "Misteri Kesadaran (Qualia): Dapatkah sains materialis menjelaskan rasa sakit atau persepsi subjektif warna?",
            "Kecerdasan Buatan (AI): Apakah mesin komputasi super canggih dapat memiliki jiwa dan kesadaran sejati?",
        ],
        category="Filosofis & Teologis",
    ),
    "nubuwwat": Faculty(
        id="nubuwwat",
        name="Nubuwwat, Mukjizat & Hukum Alam",
        icon="📜",
        short_desc="Rasionalitas Kenabian, Definisi Mukjizat (Kharq al-'Adah), Akal vs Wahyu, Hermeneutika.",
        full_desc=(
            "Kajian rasional atas fenomena kenabian: Bukti urgensi pengutusan nabi bagi peradaban, status mukjizat sebagai perombakan hukum kebiasaan "
            "(Kharq al-'Adah), distingsi logis antara kemustahilan nalar (Mustahil Aqli) vs kemustahilan pengalaman empiris (Mustahil 'Adi), "
            "serta prinsip hermeneutika ketika wahyu tampak bertentangan dengan sains/logika (Qanun al-Kulli)."
        ),
        default_queries=[
            "philosophy of prophecy islamic theology nubuwwat",
            "hume on miracles criticism philosophy of religion",
            "miracles kharq al-adah islamic epistemology",
            "faith and reason revelation rationalism al-ghazali",
            "ibn rushd fasl al-maqal harmony of religion and philosophy",
        ],
        classic_references=[
            "Al-Ghazali - Qanun al-Ta'wil & Tahafut al-Falasifah",
            "Ibn Rushd - Fasl al-Maqal fi ma bayna al-Hikmah wa al-Syari'ah min al-Ittisal",
            "Fakhr al-Din al-Razi - Al-Nubuwwat wa ma Yata'allaqu biha",
            "Al-Qadhi Iyad - Al-Syifa bi Ta'rif Huquq al-Mustafa",
        ],
        modern_references=[
            "David Hume - Of Miracles (An Enquiry Concerning Human Understanding, Part X)",
            "Richard Swinburne - The Concept of Miracle",
            "C.S. Lewis - Miracles: A Preliminary Study",
            "Oliver Leaman - An Introduction to Classical Islamic Philosophy",
        ],
        key_debates=[
            "Kritik David Hume: Apakah kesaksian manusia tentang mukjizat selalu kalah kredibel dibandingkan keteraturan hukum alam?",
            "Mustahil Aqli vs Mustahil 'Adi: Apakah tongkat menjadi ular itu kontradiksi logis (seperti lingkaran bersudut) atau sekadar perubahan materi super cepat?",
            "Harmoni Akal dan Teks: Siapa penentu akhir jika teks lahiriah bertentangan dengan temuan akal demonstratif?",
        ],
        category="Filosofis & Teologis",
    ),

    # -------------------------------------------------------------
    # 2. Multidisiplin & Keilmuan Terapan
    # -------------------------------------------------------------
    "hukum": Faculty(
        id="hukum",
        name="Ilmu Hukum, Tata Negara & Syariah",
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
        category="Multidisiplin & Terapan",
    ),
    "ekonomi": Faculty(
        id="ekonomi",
        name="Ekonomi, Bisnis & Manajemen",
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
        category="Multidisiplin & Terapan",
    ),
    "pendidikan": Faculty(
        id="pendidikan",
        name="Ilmu Pendidikan, Pedagogi & Kurikulum",
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
        category="Multidisiplin & Terapan",
    ),
    "psikologi_sosial": Faculty(
        id="psikologi_sosial",
        name="Psikologi & Ilmu Sosial-Humaniora",
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
        category="Multidisiplin & Terapan",
    ),
    "sains_teknologi": Faculty(
        id="sains_teknologi",
        name="Sains, Teknologi & Rekayasa Terapan",
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
        category="Multidisiplin & Terapan",
    ),
    "kesehatan": Faculty(
        id="kesehatan",
        name="Kedokteran & Kesehatan Masyarakat",
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
        category="Multidisiplin & Terapan",
    ),
}

# Dynamic storage pointer
CUSTOM_FACULTIES_FILE = config.ROOT / "custom_faculties.json"


def _sanitize_slug(text: str) -> str:
    """Generate a clean ASCII identifier slug."""
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", s)


def load_custom_faculties() -> Dict[str, Faculty]:
    """Load user-defined custom faculties from data/custom_faculties.json."""
    if not CUSTOM_FACULTIES_FILE.exists():
        return {}
    try:
        data = json.loads(CUSTOM_FACULTIES_FILE.read_text(encoding="utf-8"))
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
    CUSTOM_FACULTIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_FACULTIES_FILE.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Keep global dict synchronized
    _sync_global_faculties()
    return new_fac


def delete_custom_faculty(faculty_id: str) -> bool:
    """Delete a custom faculty by ID."""
    customs = load_custom_faculties()
    if faculty_id in customs:
        del customs[faculty_id]
        serialized = [asdict(f) for f in customs.values()]
        CUSTOM_FACULTIES_FILE.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")
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

    # Keywords for standard faculties
    keywords: Dict[str, List[str]] = {
        # Filosofis & Teologis
        "epistemologi": ["epistemic", "epistemology", "knowledge", "burhan", "demonstration", "skepticism", "mantiq", "syllogism", "justification", "foundationalism"],
        "ilahiyyat": ["cosmological", "fine-tuning", "contingency", "kalam", "multiverse", "big bang", "infinity", "cantor", "creator", "god's existence", "wajib al-wujud", "first cause", "ilahiyyat"],
        "kausalitas": ["causality", "causal", "occasionalism", "hume", "constant conjunction", "free will", "determinism", "foreknowledge", "kasb", "predestination"],
        "teodisi": ["problem of evil", "evil", "suffering", "theodicy", "divine justice", "syurur", "hikmah", "gratuitous", "plantinga", "rowe", "omnipoten"],
        "falsafah_jiwa": ["mind", "soul", "nafs", "consciousness", "qualia", "dualism", "physicalism", "flying man", "brain", "ilm an-nafs"],
        "nubuwwat": ["prophecy", "prophet", "miracle", "kharq", "revelation", "fasl al-maqal", "ta'wil", "hermeneutics", "nubuwwat", "scripture and reason"],

        # Multidisiplin & Terapan
        "hukum": [
            "hukum", "law", "legal", "syariah", "shariah", "fiqh", "jurisprudence", "constitutional",
            "hak asasi", "pidana", "perdata", "yurisprudensi", "peradilan", "undang-undang", "regulatif",
            "regulasi", "perlindungan data", "cyber law", "uu pdp", "hak cipta", "kebijakan publik", "advokasi"
        ],
        "ekonomi": [
            "ekonomi", "economic", "finance", "financial", "banking", "manajemen", "management", "bisnis",
            "business", "akuntansi", "accounting", "pemasaran", "marketing", "saham", "murabahah", "fintech",
            "laba", "profitability", "umkm", "pembiayaan", "modal", "kredit", "investasi", "msme", "sme",
            "usaha mikro", "perbankan syariah", "kinerja keuangan"
        ],
        "pendidikan": [
            "pendidikan", "education", "pedagogy", "pedagogis", "curriculum", "kurikulum", "pembelajaran",
            "learning", "siswa", "student", "teacher", "guru", "sekolah", "edtech", "didaktik", "hasil belajar",
            "modul ajar", "media pembelajaran", "evaluasi pembelajaran"
        ],
        "psikologi_sosial": [
            "psikologi", "psychology", "mental health", "kecemasan", "anxiety", "depression", "depresi",
            "resilience", "burnout", "sociology", "sosiologi", "komunikasi", "social behavior", "perilaku",
            "kesejahteraan subjektif", "interaksi sosial"
        ],
        "sains_teknologi": [
            "machine learning", "deep learning", "artificial intelligence", "algorithm", "software",
            "cloud computing", "iot", "sensor", "cybersecurity", "teknik", "rekayasa", "renewable energy",
            "solar cell", "ai", "etika ai", "data pribadi", "privasi", "siber", "informatika", "komputasi"
        ],
        "kesehatan": [
            "kesehatan", "health", "hospital", "rumah sakit", "clinical", "klinis", "epidemiology",
            "epidemiologi", "patient", "pasien", "stunting", "gizi", "nutrition", "pharmacology", "farmasi",
            "kedokteran", "faskes", "bpjs kesehatan", "keperawatan", "rekam medis"
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

    for f_id, kws in keywords.items():
        for kw in kws:
            if kw in text:
                # Give higher weight to matches in the title
                weight = 3 if kw in title.lower() else 1
                scores[f_id] += weight

    best_faculty = max(scores, key=scores.get)
    if scores[best_faculty] == 0:
        return "ilahiyyat"
    return best_faculty
