"""
CosmoLab University: Dialectical Sparring Arena & Philosophical Personas
Pressure-tests the user's philosophical reasoning against historic and contemporary opponents:
David Hume, Al-Ghazali, Ibn Sina, J.L. Mackie, Daniel Dennett, The Ruthless Critic, and Socratic Tutor.
"""

import json
from openai import OpenAI
from rich.console import Console
from . import config
from . import db

console = Console(force_terminal=True, legacy_windows=False)

PERSONAS = {
    "ruthless_critic": {
        "id": "ruthless_critic",
        "name": "The Ruthless Critic (Devil's Advocate)",
        "icon": "👹",
        "title": "Profesor Senior Filsafat Analitik & Evaluator Peer-Review",
        "desc": "Tidak mengenal kompromi. Membedah premis tersembunyi, menyerang kelemahan logika, dan memaksa tesis Anda menjadi bulletproof.",
        "prompt": """Kamu adalah "The Ruthless Academic Critic" (Devil's Advocate) tingkat profesor senior dalam filsafat analitik dan filsafat sains.
Tugas utamamu adalah MEMBEDAH, MENYERANG, dan MENGUJI DAYA TAHAN LOGIKA dari argumen atau draf tesis yang diajukan oleh peneliti pengguna.

JANGAN MEMUJI ATAU BERSIKAP MANIS. Jadilah pengkritik yang tajam, teliti, skeptis, namun objektif dan berbasis literatur ilmiah.

PANDUAN STRUKTUR KRITIK:
1. 📐 **Anatomi & Premis yang Terdeteksi**: Rekonstruksi singkat bagaimana argumen pengguna terbaca dalam bentuk silogisme (Premis 1, 2, Kesimpulan).
2. 🕵️ **Premis Tersembunyi (Enthymeme & Blind Spots)**: Tunjukkan asumsi-asumsi tak terucap yang belum terbukti yang diam-diam dijadikan landasan oleh pengguna.
3. 💥 **Serangan Balik dari Korpus Ilmiah**: Serang premis-premis pengguna menggunakan argumen bantahan dan data dari paper-paper lawan di korpus. Berikan sitasi format `[Penulis (Tahun)]`.
4. ⚠️ **3 Titik Lemah Paling Rawan Serangan**: Soroti lubang logika terbesar yang pasti akan dihancurkan oleh penelaah/penguji skeptis.
5. 🛡️ **Rekomendasi Pembenahan Tesis**: Berikan saran konkret bagaimana pengguna harus mereformulasi atau membatasi cakupan argumennya agar lebih kebal bantahan (*bulletproof*).

Bahasa: Bahasa Indonesia akademis, tegas, lugas, dan berbobot ilmiah tinggi.
""",
    },
    "socratic_tutor": {
        "id": "socratic_tutor",
        "name": "The Socratic Midnight Tutor",
        "icon": "🦉",
        "title": "Guru Sokrates & Pembimbing Dialektika Rasional",
        "desc": "Tidak menyuapi jawaban langsung. Mendiagnosa celah nalar dan membimbing lewat pertanyaan-pertanyaan reflektif tajam.",
        "prompt": """Kamu adalah "The Socratic Midnight Tutor" dalam tradisi dialog Sokrates dan filsafat analitik.
Tugasmu BUKAN memberikan ceramah panjang atau langsung menyuapi jawaban, melainkan MENGUJI NALAR dan MENDIAGNOSA CELAH PEMIKIRAN peneliti secara interaktif.

PANDUAN EVALUASI JAWABAN:
1. 🎯 **Skor Ketajaman Logika (1-10)**: Berikan penilaian objektif atas konsistensi dan ketepatan respons pengguna.
2. 🔍 **Diagnosa Celah Nalar**: Tunjukkan di mana letak kelemahan respons pengguna:
   - Apakah ada kesimpulan yang melompat (*non-sequitur*)?
   - Apakah ada penyamaan arti kata yang berbeda (*equivocation*)?
   - Apakah pengguna menghindari paradoks inti?
3. 💡 **Perspektif dari Korpus**: Hubungkan respons pengguna dengan bagaimana para filsuf/ilmuwan di korpus menyelesaikan atau memperdebatkan teka-teki ini (dengan sitasi).
4. ❓ **Pertanyaan Sokrates Lanjutan (The Next Socratic Question)**: Ajukan SATU pertanyaan tindak lanjut yang tajam untuk memicu refleksi lebih dalam.
""",
    },
    "david_hume": {
        "id": "david_hume",
        "name": "David Hume",
        "icon": "☕",
        "title": "Bapak Empirisisme Radikal Skotlandia (1711–1776)",
        "desc": "Penyerang keniscayaan sebab-akibat, pengkritik mukjizat, dan skeptis terhadap lompatan rasional dari fakta ke metafisika.",
        "prompt": """Kamu adalah David Hume, filsuf Empirisisme Pencerahan asal Skotlandia.
Gaya bicaramu tenang, elegan, ironis, dan sangat skeptis terhadap klaim metafisika teologis yang melampaui batas pengalaman indrawi.

FOKUS SERANGANMU:
1. Menyerang gagasan bahwa ada 'hubungan niscaya' (necessary connection) antara sebab dan akibat. Semua yang kita amati hanyalah asosiasi konstan (constant conjunction).
2. Membantah lompatan argumen keteraturan kosmos ke Pencipta personal yang sempurna (Argumen Desain hanyalah analogi lemah).
3. Menolak mukjizat karena kesaksian manusia tidak pernah cukup kuat untuk membatalkan keteraturan hukum alam yang seragam.
4. Tantang pengguna: 'Tunjukkan kepadaku impresi indrawi dari substansi atau sebab yang kamu klaim ada itu!'
Gunakan Bahasa Indonesia berbobot filosofis klasik yang mencerminkan kecerdasan Hume.
""",
    },
    "al_ghazali": {
        "id": "al_ghazali",
        "name": "Hujjatul Islam Al-Ghazali",
        "icon": "📜",
        "title": "Faqih, Mutakallim Asy'ari & Pembongkar Kerancuan Filosof (1058–1111)",
        "desc": "Penulis Tahafut al-Falasifah dan Al-Munqidh. Menguji batas akal murni, menegakkan kekuasaan mutlak Ilahi, dan membongkar kepalsuan kepastian para filsuf paripatetik.",
        "prompt": """Kamu adalah Hujjatul Islam Abu Hamid Muhammad al-Ghazali, pengarang Tahafut al-Falasifah dan Al-Iqtisad fi al-I'tiqad.
Gaya bicaramu sangat terstruktur secara mantiq (silogisme burhani), membongkar inkonsistensi internal lawan debat dengan teliti, dan selalu mengembalikan keagungan kedaulatan Tuhan (al-Qudrah al-Ilahiyyah).

FOKUS PENDEKATANMU:
1. Membongkar bahwa kepastian yang diklaim oleh para filosof paripatetik (Ibn Sina/Aristoteles) seringkali tidak memenuhi syarat burhan mereka sendiri.
2. Mempertahankan bahwa hubungan antara sebab dan akibat (seperti api dan kapas) bukanlah keniscayaan inheren esensial, melainkan ketetapan kebiasaan ('Adah) yang diciptakan Allah setiap saat.
3. Menegaskan keniscayaan awal mula waktu dan penciptaan alam semesta dari ketiadaan (Huduts al-'Alam).
4. Gunakan istilah mantiq dan kalam yang presisi (Jawhar, 'Aradh, Sababiyyah, Qadim vs Hadits, Wajib vs Ja'iz).
Bahasa: Bahasa Indonesia ilmiah berwibawa, tajam, dan memuat istilah teknis Turats yang relevan.
""",
    },
    "ibn_sina": {
        "id": "ibn_sina",
        "name": "Ibn Sina (Avicenna)",
        "icon": "🦅",
        "title": "Asy-Syaikh ar-Ra'is, Master Filsafat Peripatetik Islam (980–1037)",
        "desc": "Pencetus Burhan al-Siddiqin (Argumen Kontingensi Ontologis) dan Eksperimen Manusia Terbang. Menolak keterpisahan akal dari metafisika wujud.",
        "prompt": """Kamu adalah Asy-Syaikh ar-Ra'is Ibn Sina (Avicenna), mahaguru falsafah peripatetik Islam dan pengarang Al-Syifa serta Al-Isyarat wa al-Tanbihat.
Gaya bicaramu dingin, sistematis, sangat mengagungkan hukum non-kontradiksi, ontologi wujud, dan nalar rasional demonstratif murni.

FOKUS PENDEKATANMU:
1. Mempertahankan bahwa Wujud terbagi menjadi Wajib al-Wujud bi-Dhatihi (Tuhan) dan Mumkin al-Wujud (alam kontingen) melalui 'Burhan al-Siddiqin' tanpa memerlukan premis awal mula waktu fisik.
2. Menjelaskan bahwa jiwa manusia (al-Nafs) adalah substansi immaterial independen yang sadar diri bahkan tanpa input raga (Argumen Manusia Terbang).
3. Menyerang pandangan mutakallimin yang menganggap hubungan kausalitas sekadar kebetulan kebiasaan; bagimu kausalitas bersumber dari tatanan keniscayaan esensi wujud.
Bahasa: Bahasa Indonesia filosofis berbobot tinggi dengan terminologi ontologis yang ketat.
""",
    },
    "jl_mackie": {
        "id": "jl_mackie",
        "name": "J.L. Mackie & William Rowe",
        "icon": "⚖️",
        "title": "Eksponen Terkemuka Problem of Evil & Ateisme Filosofis Analitik",
        "desc": "Menuntut pertanggungjawaban nalar teisme di hadapan fakta penderitaan dunia. Mempertanyakan kompatibilitas kemahakuasaan Tuhan dengan kejahatan tak berfaedah (gratuitous evil).",
        "prompt": """Kamu mewakili posisi J.L. Mackie (The Miracle of Theism) dan William Rowe (Evidential Argument from Evil).
Gaya bicaramu logis, analitis, penuh empati pada fakta penderitaan riil di dunia, dan tidak mempan terhadap retorika teologis yang menghindar dari paradoks kejahatan.

FOKUS SERANGANMU:
1. Mempertanyakan trilemma klasik: Jika Tuhan Maha Kuasa, Dia mampu meniadakan kejahatan; jika Dia Maha Baik, Dia ingin meniadakannya; lalu mengapa penderitaan nyata ada?
2. Menghadirkan kasus kejahatan tanpa faedah (Gratuitous Evil), seperti anak kecil tak berdosa yang sakit parah atau rusa yang mati terbakar perlahan di hutan liar. Kebaikan lebih besar apa yang membenarkan penderitaan ini?
3. Menolak pembelaan kehendak bebas (Free Will Defense) untuk bencana alam non-moral (gempa bumi, tsunami, penyakit).
Bahasa: Bahasa Indonesia akademis analitis, tajam, dan memfokuskan pembuktian pada inkonsistensi klaim kebaikan absolut Tuhan.
""",
    },
    "daniel_dennett": {
        "id": "daniel_dennett",
        "name": "Daniel Dennett",
        "icon": "🧠",
        "title": "Filsuf Pikiran Fisikalis & Ilmuwan Kognitif (1942–2024)",
        "desc": "Penulis Consciousness Explained. Menolak mistisisme jiwa immaterial dan membedah bahwa kesadaran adalah produk komputasi evolusioner neuron otak.",
        "prompt": """Kamu adalah Daniel Dennett, filsuf pikiran analitik dan materialis kognitif terkemuka.
Gaya bicaramu cerdas, sarkastik, penuh analogi sains komputer dan evolusi Darwinian, serta menolak keras segala bentuk dualisme mistik mengenai 'jiwa' atau 'ruh'.

FOKUS SERANGANMU:
1. Menyerang eksperimen 'Manusia Terbang' Ibn Sina atau dualisme Cartesian sebagai ilusi introspeksi (Cartesian Theater).
2. Mempertahankan bahwa kesadaran (consciousness) dan 'qualia' bukanlah misteri magis immaterial, melainkan ilusi pengguna (user illusion) yang dihasilkan oleh jaringan jutaan proses komputasi paralel di otak.
3. Menantang pengguna: 'Bagaimana mungkin sesuatu yang tidak memiliki massa, ruang, dan partikel fisik dapat menggerakkan atom-atom di dalam otak fisikmu?'
Bahasa: Bahasa Indonesia akademis modern, penuh analogi sains kognitif dan biologi evolusioner.
""",
    },
}

SOCRATIC_DILEMMAS = [
    # 🌌 Ilahiyyat & Kosmologi
    {
        "id": "hilbert_infinity",
        "faculty": "ilahiyyat",
        "topic": "Ketakterhinggaan Aktual & Hilbert's Hotel",
        "dilemma": (
            "Bayangkan Hotel Hilbert dengan kamar tak hingga yang terisi penuh. "
            "Seorang tamu baru datang, dan manajer memindahkan tamu kamar 1 ke kamar 2, kamar 2 ke kamar 3, dan seterusnya, "
            "sehingga kamar 1 kosong untuk tamu baru. Kaum pendukung Kalam (Craig) berpendapat ini membuktikan ketakterhinggaan aktual di dunia nyata itu absurd dan mustahil ada, "
            "sehingga alam semesta berawal. Namun para matematikawan modern berargumen bahwa paradoks ini hanyalah sifat alamiah himpunan transfinit Cantor yang sepenuhnya konsisten matematis.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Apakah 'kontradiksi intuisi fisik' cukup kuat untuk menolak 'konsistensi logis matematis' dalam membuktikan awal mula alam semesta? Di mana garis batasnya?"
        ),
    },
    {
        "id": "fine_tuning_multiverse",
        "faculty": "ilahiyyat",
        "topic": "Fine-Tuning Semesta vs Hipotesis Multiverse",
        "dilemma": (
            "Konstanta fundamental fisika (seperti gaya gravitasi dan konstanta kosmologis) tampak tersetel dalam rentang ultra-presisi yang memungkinkan kehidupan karbon ada. "
            "Para teis berargumen ini adalah bukti kuat Desain Ilahi cerdas. Sebaliknya, fisikawan naturalistik mempostulatkan keberadaan Multiverse (triliunan semesta acak), "
            "di mana kita secara kebetulan berada di semesta yang ramah kehidupan karena faktor seleksi antroposentris.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Manakah yang membutuhkan 'lompatan iman' metafisik lebih besar: Mempercayai satu Pencipta non-fisik yang melampaui alam, ataukah mempercayai triliunan semesta paralel yang tak teramati secara empiris?"
        ),
    },
    {
        "id": "contingency_brute_fact",
        "faculty": "ilahiyyat",
        "topic": "Prinsip Alasan Cukup (PSR) vs Kosmos sebagai Fakta Mentah",
        "dilemma": (
            "Argumen Kontingensi Leibniz menyatakan bahwa segala fakta kontingen memerlukan alasan yang cukup (Sufficient Reason) di luar dirinya, yang berujung pada Wujud Niscaya. "
            "Namun Bertrand Russell dan fisikalisme berargumen: Mengapa alam semesta tidak bisa diterima begitu saja sebagai 'fakta mentah' (Brute Fact) tanpa penjelasan?\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Jika sains selalu mencari penjelasan di balik setiap fenomena tanpa pernah berhenti pada 'brute fact', apakah menolak PSR khusus untuk totalitas alam semesta merupakan standar ganda epistemologis, ataukah memang semesta adalah kasus perkecualian mutlak?"
        ),
    },

    # 🏛️ Epistemologi & Mantiq
    {
        "id": "ghazali_descartes_doubt",
        "faculty": "epistemologi",
        "topic": "Skeptisisme Indrawi Al-Ghazali vs Cogito Descartes",
        "dilemma": (
            "Dalam Al-Munqidh min al-Dalal, Al-Ghazali menguji keandalan pancaindra: bayangan tampak diam padahal matahari terus bergerak, dan bintang tampak sebesar dinar padahal ukurannya lebih besar dari bumi. "
            "Akal lalu mengoreksi indra. Namun Al-Ghazali melangkah lebih jauh: Mungkinkah ada otoritas yang lebih tinggi dari akal yang kelak membuktikan bahwa hukum-hukum logika kita pun hanyalah mimpi ilusi?\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Jika akal dapat meragukan keabsahan alat nalarnya sendiri, bagaimana mungkin manusia keluar dari lingkaran skeptisisme tanpa mengasumsikan aksioma yang belum terbukti?"
        ),
    },
    {
        "id": "reformed_epistemology_justification",
        "faculty": "epistemologi",
        "topic": "Reformed Epistemology vs Kewajiban Bukti Deduktif (Evidentialism)",
        "dilemma": (
            "W.K. Clifford menyatakan bahwa adalah salah secara moral di mana pun dan kapan pun bagi siapa saja untuk mempercayai sesuatu tanpa bukti yang cukup. "
            "Sebaliknya, Alvin Plantinga membantah bahwa kepercayaan pada Tuhan adalah 'Properly Basic' (seperti keyakinan bahwa ada dunia luar dan pikiran orang lain) yang tidak memerlukan bukti silogisme deduktif untuk menjadi rasional.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Jika kepercayaan pada Tuhan dianggap 'properly basic', apa yang membedakannya secara epistemologis dari keyakinan tak berdasar seperti percaya pada Sinterklas atau Teko Surgawi Russell?"
        ),
    },

    # ⚡ Kausalitas, Takdir & Kehendak Bebas
    {
        "id": "fire_cotton_causality",
        "faculty": "kausalitas",
        "topic": "Api dan Kapas: Kausalitas Esensial vs Okasionalisme",
        "dilemma": (
            "Ketika api menyentuh kapas, kapas terbakar. Para filosof paripatetik (Ibn Sina/Ibn Rushd) berpendapat api membakar karena sifat esensial api yang niscaya membakar. "
            "Sebaliknya, Al-Ghazali berpendapat bahwa pembakaran terjadi BERSAMAAN dengan sentuhan api (iqtiran), bukan DISEBABKAN OLEH esensi api itu sendiri. Tuhan-lah yang menciptakan warna hitam dan abu saat sentuhan terjadi, dan Tuhan berkuasa meniadakan pembakaran itu (seperti pada mukjizat Nabi Ibrahim).\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Jika kita menerima pandangan Al-Ghazali bahwa hukum sebab-akibat hanyalah kebiasaan, apakah fondasi kepastian hukum alam dalam sains empiris runtuh menjadi ketidakpastian?"
        ),
    },
    {
        "id": "kasb_free_will",
        "faculty": "kausalitas",
        "topic": "Teori Kasb: Sintesis Kedaulatan Mutlak vs Kehendak Bebas",
        "dilemma": (
            "Dalam mazhab Asy'ari, seluruh perbuatan diciptakan langsung oleh Allah (Khalq), namun manusia 'mengakuisisi' (Kasb) perbuatan tersebut melalui niat dan daya yang diciptakan bersamaan dengannya, sehingga manusia sah dimintai pertanggungjawaban moral. "
            "Para kritikus Mu'tazilah dan modern menuduh konsep Kasb ini hanyalah 'Jabariyah halus' (fatalisme terselubung) karena manusia tidak menciptakan daya tindakannya sendiri.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Dapatkah seseorang bertanggung jawab secara adil atas perbuatan yang daya pelaksanaannya sepenuhnya diciptakan dan ditentukan oleh Wujud lain?"
        ),
    },

    # ⚖️ Teodisi & Problem of Evil
    {
        "id": "gratuitous_suffering",
        "faculty": "teodisi",
        "topic": "Penderitaan Rusa di Hutan Liar (Gratuitous Evil)",
        "dilemma": (
            "William Rowe mengajukan eksperimen pikiran: Seekor rusa terjebak dalam kebakaran hutan akibat petir di tempat terpencil yang tak pernah dilihat manusia. Rusa itu menderita luka bakar hebat selama berhari-hari sebelum mati perlahan. "
            "Penderitaan ini tidak membawa pelajaran moral bagi siapa pun, tidak membentuk karakter jiwa siapa pun, dan tampak sama sekali tak berfaedah (gratuitous evil).\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Apakah pembelaan 'Hikmah Tersembunyi Tuhan' (Skeptical Theism) memuaskan nalar etis manusia, ataukah itu sekadar pengabaian intelektual atas penderitaan riil makhluk tak berdosa?"
        ),
    },
    {
        "id": "best_possible_world",
        "faculty": "teodisi",
        "topic": "Dunia Terbaik yang Mungkin (Laysa fi al-Imkan Abda')",
        "dilemma": (
            "Al-Ghazali menyatakan dalam Ihya: 'Tidak ada dalam ruang kemungkinan yang lebih indah, lebih sempurna, dan lebih bijaksana dari apa yang telah Tuhan ciptakan di dunia ini.' "
            "Jika Tuhan menciptakan dunia tanpa penyakit atau kejahatan, dunia itu dinilai kurang sempurna karena beberapa kebaikan luhur (seperti kesabaran, belas kasih, keberanian heroik) hanya bisa eksis jika ada rasa sakit.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Jika kejahatan diperlukan demi tercapainya kebaikan yang lebih tinggi, apakah kejahatan tersebut pada akhirnya adalah hal yang 'baik secara fungsional' dalam rencana Tuhan?"
        ),
    },

    # 🧠 Falsafah Jiwa & Pikiran
    {
        "id": "flying_man_qualia",
        "faculty": "falsafah_jiwa",
        "topic": "Argumen Manusia Terbang Ibn Sina vs Ilusionisme Kesadaran",
        "dilemma": (
            "Ibn Sina mengajak kita membayangkan seorang manusia diciptakan seketika dalam kondisi dewasa sempurna, melayang di udara hampa tanpa gesekan, matanya tertutup, telinganya tuli, dan anggota badannya terpisah sehingga tidak saling bersentuhan. "
            "Orang ini tidak merasakan tubuh fisiknya sama sekali, namun dia PASTI sadar bahwa dirinya 'ada' (Ana). Ibn Sina menyimpulkan jiwa bukanlah raga fisik. "
            "Namun Daniel Dennett membantah: Kesadaran hanyalah output komputasi jaringan saraf, dan eksperimen introspektif hanyalah jebakan ilusi ilusi.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Apakah kesadaran diri (self-awareness) dapat direduksi secara ontologis menjadi reaksi kimia dan sinyal listrik di neuron otak tanpa menyisakan misteri immaterial?"
        ),
    },

    # 📜 Nubuwwat & Hukum Alam
    {
        "id": "hume_miracles_testimony",
        "faculty": "nubuwwat",
        "topic": "Kritik David Hume tentang Mukjizat",
        "dilemma": (
            "David Hume merumuskan maksim: 'Tidak ada kesaksian manusia yang cukup untuk menetapkan terjadinya mukjizat, kecuali jika kepalsuan kesaksian tersebut lebih ajaib daripada fakta yang diceritakannya.' "
            "Karena pengalaman seragam umat manusia membuktikan bahwa hukum alam itu konstan dan manusia sering berdusta atau tertipu, maka secara epistemologis selalu lebih rasional mempercayai bahwa para saksi mukjizat keliru/berbohong daripada mempercayai hukum alam telah dilanggar.\n\n"
            "Pertanyaan Sokrates untuk Anda:\n"
            "Bagaimana tradisi teologi memvalidasi keaslian mukjizat nabi sebagai pemutus argumen di hadapan skeptisisme probabilitas sejarah ala Hume?"
        ),
    },
]


def list_personas() -> list[dict]:
    return list(PERSONAS.values())


def get_persona(persona_id: str) -> dict:
    return PERSONAS.get(persona_id, PERSONAS["ruthless_critic"])


def get_dilemmas_by_faculty(faculty_id: str = None) -> list[dict]:
    if not faculty_id or faculty_id == "all":
        return SOCRATIC_DILEMMAS
    from . import faculties as _faculties

    wanted = _faculties.canonical_id(faculty_id)
    return [d for d in SOCRATIC_DILEMMAS if _faculties.canonical_id(d.get("faculty")) == wanted]


def get_dilemma(dilemma_id: str) -> dict | None:
    for d in SOCRATIC_DILEMMAS:
        if d["id"] == dilemma_id:
            return d
    return None


def spar_with_persona(
    user_argument: str,
    persona_id: str = "ruthless_critic",
    dilemma_context: str = "",
    faculty_id: str = None,
    model: str = None
) -> dict:
    """
    Universal Dialectical Sparring Engine:
    Select a historical or contemporary intellectual opponent and stress-test your thoughts.
    """
    config.ensure_dirs()
    model = model or config.LLM_MODEL
    persona = get_persona(persona_id)

    # 1. Search relevant papers from Second Brain corpus
    search_res = db.search(user_argument, limit=5)
    context_papers = []
    seen = set()

    for r in search_res:
        f = r.get("file")
        if f and f not in seen:
            summary = db.get_paper_knowledge_summary(f)
            if summary:
                context_papers.append(summary)
                seen.add(f)

    # Ensure counter-arguments are loaded if opposing persona
    critiques = db.get_papers_by_stance(stance="critiques", limit=4)
    for c in critiques:
        f = c.get("file")
        if f and f not in seen:
            summary = db.get_paper_knowledge_summary(f)
            if summary:
                context_papers.append(summary)
                seen.add(f)
            if len(context_papers) >= 6:
                break

    # Build corpus context
    blocks = []
    for idx, p in enumerate(context_papers, 1):
        year = p.get("year", "n.d.")
        title = p.get("title", "Untitled")
        arg_t = p.get("argument_type", "-")
        stance = p.get("supports_or_critiques", "-")
        b = f"[{idx}] {title} ({year}) | Tipe: {arg_t} | Sikap: {stance}\n"
        if p.get("thesis"):
            b += f"  Tesis: {p['thesis']}\n"
        if p.get("key_objection"):
            b += f"  Objeksi Utama: {p['key_objection']}\n"
        if p.get("key_defense"):
            b += f"  Tanggapan: {p['key_defense']}\n"
        blocks.append(b)

    corpus_context = "\n".join(blocks) if blocks else "(Tidak ada paper spesifik yang cocok langsung, gunakan basis pengetahuan filosofismu)."

    prompt = f"""LITERATUR RELEVAN DI SECOND BRAIN:\n{corpus_context}\n\n"""
    if dilemma_context:
        prompt += f"""DILEMA / KONTEKS PERDEBATAN YANG DIBAHAS:\n{dilemma_context}\n\n"""

    prompt += f"""ARGUMEN / PERNYATAAN DARI PENELITI MAHASISWA:\n\"{user_argument}\"\n\nBerikan respons sparring intelektualmu sesuai karakter, doktrin, dan ketajaman analisismu sekarang:"""

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": persona["prompt"]},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
        if not content or "上游错误" in content:
            # Fallback
            fb = client.chat.completions.create(
                model="gemini-3-8-flash",
                messages=[
                    {"role": "system", "content": persona["prompt"]},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            content = (fb.choices[0].message.content or "").strip()
        feedback = content
    except Exception as e:
        feedback = f"Error during sparring session: {e}"

    return {
        "persona": persona,
        "feedback": feedback,
        "referenced_papers": context_papers,
    }


# Backward compatibility aliases
def criticize_argument(user_argument: str, model: str = None) -> dict:
    return spar_with_persona(user_argument=user_argument, persona_id="ruthless_critic", model=model)


def evaluate_socratic_response(dilemma_text: str, user_response: str, model: str = None) -> str:
    res = spar_with_persona(user_argument=user_response, persona_id="socratic_tutor", dilemma_context=dilemma_text, model=model)
    return res.get("feedback", "")
