"""
cosmolab.defense
~~~~~~~~~~~~~~~~
Latihan sidang: practice for a thesis defense.

The AI plays the examiner. It reads the student's own draft and asks the
questions an examiner would ask about the problem, theory, method, findings,
and contribution. The student (or the consultant with the student) answers,
and the AI says what is strong, what is missing, and what to prepare.

This is coaching, not ghostwriting: the feedback never writes a model answer
for the student. Each question must quote the draft, and the quote is checked
against the draft text, so the examiner cannot ask about things the draft
does not say.

Sessions are saved in <root>/defense/<stem>.json.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import audit, config
from . import review as _review
from . import team as _team

LEVELS = _review.LEVELS
AREAS = {
    "masalah": "Masalah dan tujuan",
    "teori": "Teori dan pustaka",
    "metode": "Metode",
    "hasil": "Hasil dan pembahasan",
    "kontribusi": "Kontribusi dan keterbatasan",
}
SCORES = {"kuat": "Kuat", "cukup": "Cukup", "lemah": "Perlu diperkuat"}

DRAFT_LIMIT = 45000        # characters of the draft sent with the question request
MIN_ANSWER_CHARS = 40
SEC_QUESTIONS = (20, 60)   # rough duration of the question request
SEC_FEEDBACK = (5, 20)     # rough duration of one feedback request

QUESTION_PROMPT = """Kamu adalah dosen penguji sidang {level}. Kamu sudah membaca draf mahasiswa di bawah.

Tulis {n} pertanyaan sidang yang benar-benar akan ditanyakan penguji untuk draf INI. Sebar ke area:
masalah (rumusan masalah, tujuan, alasan topik), teori (kerangka teori, posisi terhadap penelitian terdahulu),
metode (desain, sampel, instrumen, analisis), hasil (temuan, penafsiran, hubungan dengan teori),
kontribusi (kebaruan, keterbatasan, implikasi).

Aturan wajib:
- Setiap pertanyaan harus berangkat dari isi draf. Sertakan "quote": potongan 5-25 kata yang disalin PERSIS dari draf
  (huruf dan tanda baca sama), yaitu bagian yang kamu tanyakan. Jangan memparafrasekan kutipan.
- Pertanyaan harus menuntut penjelasan atau pembelaan, bukan jawaban ya/tidak. Satu pertanyaan, satu hal.
- "looks_for": 1-2 kalimat tentang apa yang ingin didengar penguji dari jawaban yang baik (kriteria, bukan jawabannya).
- Sesuaikan kedalaman dengan jenjang {level}. Tulis dalam bahasa Indonesia.

Balas HANYA JSON:
{{"questions": [{{"area": "masalah"|"teori"|"metode"|"hasil"|"kontribusi", "question": str, "quote": str,
   "looks_for": str}}]}}"""

FEEDBACK_PROMPT = """Kamu adalah dosen penguji sidang {level} yang sedang melatih mahasiswa menjelang sidang.

Kamu menerima satu pertanyaan sidang, bagian draf yang ditanyakan, dan jawaban mahasiswa. Nilai jawabannya.

Aturan wajib:
- JANGAN menuliskan jawaban yang seharusnya. Jangan memberi contoh kalimat jawaban. Mahasiswa harus menyusun
  jawabannya sendiri. Tugasmu menunjukkan apa yang sudah kuat, apa yang belum terjawab, dan apa yang perlu disiapkan.
- Nilai hanya dari jawaban dan bagian draf yang diberikan. Kalau jawaban menyebut hal yang tidak ada di draf, katakan
  bahwa penguji akan meminta buktinya.
- Tulis dalam bahasa Indonesia, langsung dan sopan.

Balas HANYA JSON:
{{"score": "kuat"|"cukup"|"lemah",
  "strengths": ["yang sudah baik dari jawaban, maksimal 2"],
  "gaps": ["yang belum terjawab atau lemah, maksimal 3"],
  "prepare": ["yang perlu disiapkan atau dibaca lagi sebelum sidang, maksimal 2"],
  "follow_up": "satu pertanyaan lanjutan yang kemungkinan diajukan penguji"}}"""


def _chat(messages: list[dict], model: str | None = None) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=model or config.LLM_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
        timeout=180,
    )
    return resp.choices[0].message.content or ""


def _json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _strings(value, limit: int) -> list[str]:
    return [str(x).strip() for x in (value if isinstance(value, list) else []) if str(x).strip()][:limit]


def trim_draft(md: str, limit: int = DRAFT_LIMIT) -> str:
    """The draft without its reference list; a long draft keeps its start, middle, and end."""
    body, _refs = _review.verify.split_reference_section(md)
    body = body.strip()
    if len(body) <= limit:
        return body
    head, mid, tail = int(limit * 0.35), int(limit * 0.40), int(limit * 0.25)
    centre = len(body) // 2
    return (body[:head] + "\n\n[... bagian dipotong ...]\n\n" + body[centre - mid // 2:centre + mid // 2]
            + "\n\n[... bagian dipotong ...]\n\n" + body[-tail:])


def _context(quote: str, paragraphs: list[dict]) -> dict | None:
    """The draft paragraph that contains the quote."""
    for p in paragraphs:
        if _review.quote_found(quote, p["text"]):
            return p
    return None


def estimate_text(md: str, n: int) -> str:
    chars = len(trim_draft(md))
    lo, hi = SEC_QUESTIONS
    return (f"Draf {chars:,} karakter dibaca sekali untuk menyusun {n} pertanyaan (perkiraan {lo}–{hi} detik). "
            f"Setiap umpan balik jawaban satu panggilan AI kecil ({SEC_FEEDBACK[0]}–{SEC_FEEDBACK[1]} detik).").replace(",", ".")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def sessions_dir() -> Path:
    return config.ROOT / "defense"


def save(session: dict) -> dict:
    out = sessions_dir()
    out.mkdir(parents=True, exist_ok=True)
    if not session.get("stem"):
        slug = re.sub(r"[^A-Za-z0-9]+", "_", session.get("title") or "").strip("_")[:60] or "draf"
        session["stem"] = f"{datetime.now():%Y%m%d_%H%M%S}_{slug}"
        if _team.current_username():
            session.setdefault("created_by", _team.current_username())
    (out / f"{session['stem']}.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return session


def load(stem: str) -> dict:
    path = sessions_dir() / f"{Path(stem).name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Latihan sidang {stem} tidak ditemukan")
    return json.loads(path.read_text(encoding="utf-8"))


def load_saved(limit: int = 30) -> list[dict]:
    """Saved sessions, newest first."""
    out = []
    folder = sessions_dir()
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.json"), reverse=True)[:limit]:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def progress(session: dict) -> dict:
    qs = session.get("questions") or []
    scored = [q["feedback"]["score"] for q in qs if q.get("feedback")]
    return {"total": len(qs), "answered": len(scored), **{k: scored.count(k) for k in SCORES}}


# ---------------------------------------------------------------------------
# Examiner
# ---------------------------------------------------------------------------

def start(md: str, title: str = "", level: str = "s2", n: int = 8, model: str | None = None, source: str = "",
          chat=None) -> dict:
    """Read the draft, write the examiner's questions, and save the session.

    Questions whose quote is not in the draft are dropped (the examiner must ask about what the draft says).
    Raises ValueError when the draft is too short or the AI returns no usable question.
    """
    paragraphs = _review.split_paragraphs(md)
    if len(paragraphs) < 3:
        raise ValueError("Draf terlalu pendek untuk latihan sidang (kurang dari 3 paragraf isi).")
    level = level if level in LEVELS else "s2"
    n = max(3, min(int(n), 12))
    messages = [{"role": "system", "content": QUESTION_PROMPT.format(level=LEVELS[level], n=n)},
                {"role": "user", "content": f"JUDUL: {title or '-'}\n\nDRAF:\n{trim_draft(md)}"}]
    data = _json((chat or _chat)(messages, model))
    questions, dropped = [], 0
    for raw in data.get("questions") if isinstance(data.get("questions"), list) else []:
        if not isinstance(raw, dict) or not str(raw.get("question") or "").strip():
            continue
        quote = str(raw.get("quote") or "").strip()
        par = _context(quote, paragraphs) if quote else None
        if not par:
            dropped += 1
            continue
        area = raw.get("area") if raw.get("area") in AREAS else "hasil"
        questions.append({"id": f"q{len(questions) + 1}", "area": area, "question": str(raw["question"]).strip(),
                          "quote": quote, "looks_for": str(raw.get("looks_for") or "").strip(),
                          "section": par.get("section") or "", "context": par["text"][:1500],
                          "answer": "", "feedback": None})
    if not questions:
        raise ValueError("AI tidak menghasilkan pertanyaan yang kutipannya ada di draf. Coba lagi.")
    session = save({"title": title or "Draf", "source": source, "level": level, "model": model or config.LLM_MODEL,
                    "created": datetime.now().isoformat(timespec="seconds"), "dropped": dropped,
                    "questions": questions})
    audit.log("latihan_sidang", file=source or title, questions=len(questions), dropped=dropped,
              model=session["model"], prompt_version=audit.prompt_version(QUESTION_PROMPT, FEEDBACK_PROMPT))
    return session


def answer(session: dict, qid: str, text: str, model: str | None = None, chat=None) -> dict:
    """Save the student's answer to one question and the examiner's feedback on it. Returns the question."""
    q = next((x for x in session.get("questions") or [] if x.get("id") == qid), None)
    if q is None:
        raise KeyError(qid)
    text = (text or "").strip()
    if len(text) < MIN_ANSWER_CHARS:
        raise ValueError(f"Jawaban terlalu pendek. Tulis minimal {MIN_ANSWER_CHARS} karakter, seperti menjawab di depan penguji.")
    level = LEVELS.get(session.get("level"), LEVELS["s2"])
    messages = [{"role": "system", "content": FEEDBACK_PROMPT.format(level=level)},
                {"role": "user", "content": (f"PERTANYAAN: {q['question']}\n\nYANG DILIHAT PENGUJI: {q.get('looks_for') or '-'}\n\n"
                                             f"BAGIAN DRAF:\n{q.get('context') or q.get('quote')}\n\nJAWABAN MAHASISWA:\n{text}")}]
    data = _json((chat or _chat)(messages, model or session.get("model")))
    if data.get("score") not in SCORES:
        raise ValueError("AI tidak memberi penilaian yang bisa dibaca. Coba lagi.")
    q["answer"] = text
    q["feedback"] = {"score": data["score"], "strengths": _strings(data.get("strengths"), 2),
                     "gaps": _strings(data.get("gaps"), 3), "prepare": _strings(data.get("prepare"), 2),
                     "follow_up": str(data.get("follow_up") or "").strip(),
                     "at": datetime.now().isoformat(timespec="seconds")}
    save(session)
    return q


def session_markdown(session: dict) -> str:
    """The session as notes the student can study from."""
    p = progress(session)
    lines = [f"# Latihan sidang: {session.get('title') or 'Draf'}", "",
             f"Jenjang: {LEVELS.get(session.get('level'), '-')}. Dibuat {str(session.get('created') or '')[:10]}. "
             f"Dijawab {p['answered']} dari {p['total']} pertanyaan.", "",
             "Catatan ini bahan latihan. Pertanyaan dan penilaian dibuat AI dari draf, bukan dari penguji sebenarnya.", ""]
    for i, q in enumerate(session.get("questions") or [], 1):
        lines += [f"## {i}. {q['question']}", "", f"Area: {AREAS.get(q['area'], q['area'])}"
                  + (f" · Bagian draf: {q['section']}" if q.get("section") else ""), "",
                  f"> {q['quote']}", ""]
        if q.get("looks_for"):
            lines += [f"Yang dilihat penguji: {q['looks_for']}", ""]
        if q.get("answer"):
            lines += ["**Jawaban:**", "", q["answer"], ""]
        fb = q.get("feedback")
        if fb:
            lines += [f"**Penilaian: {SCORES.get(fb['score'], fb['score'])}**", ""]
            for label, key in (("Sudah baik", "strengths"), ("Belum terjawab", "gaps"), ("Perlu disiapkan", "prepare")):
                if fb.get(key):
                    lines += [f"{label}:"] + [f"- {x}" for x in fb[key]] + [""]
            if fb.get("follow_up"):
                lines += [f"Pertanyaan lanjutan: {fb['follow_up']}", ""]
    return "\n".join(lines)
