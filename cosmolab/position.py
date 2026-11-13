"""
cosmolab.position
~~~~~~~~~~~~~~~~~
The research question of a project, and where each paper stands on it.

"Supports" or "critiques" only means something against a reference point. The
project's research question (and hypothesis, if any) is that reference point.
The AI reads the stored analysis of each paper (not the full text, so it is
cheap) and says whether the paper supports the hypothesis, contradicts it,
is mixed, or is not about it, with one sentence of reason.

Files in the active data root:
  research_question.json  {"topic", "question", "hypothesis", "updated"}
  positions.json          {"question_key", "papers": {file: {"position", "reason", "at"}}}

Positions are tied to the question they were judged against. When the question
or hypothesis changes, the old positions no longer count.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from . import audit, config
from .utils import fire_cb

QUESTION_FILE = "research_question.json"
POSITIONS_FILE = "positions.json"

SUPPORTS = "mendukung"
CONTRADICTS = "menolak"
MIXED = "campuran"
UNRELATED = "tidak_berkaitan"
ORDER = [SUPPORTS, MIXED, CONTRADICTS, UNRELATED]
LABELS = {SUPPORTS: "Mendukung", MIXED: "Campuran", CONTRADICTS: "Menolak", UNRELATED: "Tidak berkaitan"}

BATCH = 8                 # papers per AI call
SEC_PER_BATCH = (10, 30)  # rough duration of one call

PROMPT = """Kamu membantu konsultan riset menyusun tinjauan pustaka.

Kamu menerima pertanyaan riset sebuah proyek (dan hipotesisnya kalau ada), lalu ringkasan beberapa paper.
Untuk setiap paper, tentukan posisinya terhadap pertanyaan riset itu:
- "mendukung": temuan atau argumen paper mendukung hipotesis. Kalau tidak ada hipotesis: paper menjawab pertanyaan riset dengan "ya" atau menunjukkan pengaruh/hubungan yang ditanyakan.
- "menolak": temuan atau argumen paper bertentangan dengan hipotesis, atau menunjukkan tidak ada pengaruh/hubungan yang ditanyakan.
- "campuran": paper memuat bukti ke dua arah, atau hasilnya bergantung pada kondisi tertentu.
- "tidak_berkaitan": paper tidak membahas pertanyaan riset ini. Pilih ini kalau ragu apakah paper relevan.

Aturan:
- Nilai hanya dari ringkasan yang diberikan. Jangan menebak isi paper.
- "reason": satu kalimat bahasa Indonesia yang menyebut temuan atau argumen paper yang menjadi dasar penilaian.

Kembalikan JSON saja:
{"results": [{"id": <nomor paper>, "position": "mendukung"|"menolak"|"campuran"|"tidak_berkaitan", "reason": str}]}
"""


def _root(root: Path | None = None) -> Path:
    return root or config.ROOT


# ---------------------------------------------------------------------------
# Research question
# ---------------------------------------------------------------------------

def load_question(root: Path | None = None) -> dict:
    """{"topic", "question", "hypothesis", "updated"}; empty strings when not set."""
    data = {}
    try:
        data = json.loads((_root(root) / QUESTION_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"topic": str(data.get("topic") or ""), "question": str(data.get("question") or ""),
            "hypothesis": str(data.get("hypothesis") or ""), "updated": str(data.get("updated") or "")}


def save_question(topic: str, question: str, hypothesis: str = "", root: Path | None = None) -> dict:
    data = {"topic": topic.strip(), "question": question.strip(), "hypothesis": hypothesis.strip(),
            "updated": datetime.now().isoformat(timespec="seconds")}
    path = _root(root) / QUESTION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    audit.log("pertanyaan_riset", question=data["question"][:200])
    return data


def question_key(q: dict) -> str:
    """Changes when the question or hypothesis changes (the topic is only a label)."""
    text = " ".join(f"{q.get('question', '')} || {q.get('hypothesis', '')}".lower().split())
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

_cache: dict = {}


def _read_positions(root: Path) -> dict:
    path = root / POSITIONS_FILE
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {}
    hit = _cache.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    _cache[str(path)] = (stamp, data)
    return data


def load_positions(root: Path | None = None) -> dict:
    """{file: {"position", "reason", "at"}} judged against the current question; {} if the question changed."""
    root = _root(root)
    q = load_question(root)
    if not q["question"]:
        return {}
    data = _read_positions(root)
    if data.get("question_key") != question_key(q):
        return {}
    return data.get("papers") or {}


def position_of(file: str, root: Path | None = None) -> dict | None:
    return load_positions(root).get(file or "")


def pending(papers: list[dict], root: Path | None = None) -> list[dict]:
    """Analysed papers with no position for the current question."""
    done = load_positions(root)
    return [p for p in papers if p.get("thesis") and p.get("file") not in done]


def counts(papers: list[dict], root: Path | None = None) -> list[dict]:
    """[{"Posisi", "Paper"}] in fixed order, for the papers given."""
    done = load_positions(root)
    tally = {k: 0 for k in ORDER}
    for p in papers:
        entry = done.get(p.get("file") or "")
        if entry and entry.get("position") in tally:
            tally[entry["position"]] += 1
    return [{"Posisi": LABELS[k], "Paper": tally[k]} for k in ORDER if tally[k]]


def estimate_text(n: int) -> str:
    batches = -(-n // BATCH)
    lo, hi = batches * SEC_PER_BATCH[0], batches * SEC_PER_BATCH[1]
    span = f"{lo}–{hi} detik" if hi < 120 else f"{max(1, lo // 60)}–{-(-hi // 60)} menit"
    return f"{n} paper, {batches} panggilan AI, perkiraan {span}."


def _digest(p: dict) -> str:
    try:
        raw = json.loads(p.get("raw_json") or "{}")
    except (TypeError, ValueError):
        raw = {}
    lines = [f"Judul: {p.get('title') or '-'} ({p.get('year') or 'n.d.'})", f"Inti: {p.get('thesis') or '-'}"]
    if raw.get("research_question"):
        lines.append(f"Tujuan: {raw['research_question']}")
    if raw.get("sample_data"):
        lines.append(f"Sampel/data: {raw['sample_data']}")
    findings = [x for x in (raw.get("key_findings") or []) if isinstance(x, str) and x.strip()]
    if findings:
        lines.append("Temuan: " + "; ".join(findings)[:1200])
    if p.get("conclusion"):
        lines.append(f"Kesimpulan: {str(p['conclusion'])[:600]}")
    return "\n".join(lines)


def _parse(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return []
    try:
        results = json.loads(text[start:end + 1]).get("results")
    except (ValueError, AttributeError):
        return []
    return [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []


def _ask(q: dict, batch: list[dict], model: str) -> dict:
    """{file: {"position", "reason"}} for one batch. Papers the AI skipped or mislabelled are left out."""
    head = f"PERTANYAAN RISET: {q['question']}\nHIPOTESIS: {q['hypothesis'] or '(tidak ada)'}"
    if q["topic"]:
        head = f"TOPIK: {q['topic']}\n" + head
    body = "\n\n".join(f"PAPER {i}\n{_digest(p)}" for i, p in enumerate(batch, 1))
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": f"{head}\n\n{body}"}],
        temperature=0.1,
        timeout=90.0,
    )
    content = resp.choices[0].message.content if resp and resp.choices else ""
    out = {}
    for r in _parse(content):
        try:
            idx = int(r.get("id")) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(batch) and r.get("position") in LABELS:
            out[batch[idx]["file"]] = {"position": r["position"], "reason": str(r.get("reason") or "").strip()[:400]}
    return out


def judge(papers: list[dict], model: str | None = None, progress_cb=None, root: Path | None = None) -> dict:
    """Judge every analysed paper that has no position yet. Saves after each batch.

    Returns {"judged": n, "failed": n, "error": str | None}. Stops at the first failed AI call.
    """
    root = _root(root)
    q = load_question(root)
    if not q["question"]:
        return {"judged": 0, "failed": 0, "error": "Pertanyaan riset belum diisi."}
    todo = [p for p in pending(papers, root) if p.get("file")]
    model = model or config.LLM_MODEL
    key = question_key(q)
    stored = _read_positions(root)
    done = dict(stored.get("papers") or {}) if stored.get("question_key") == key else {}
    judged, error = 0, None
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        fire_cb(progress_cb, "item", f"menilai paper {start + 1}–{start + len(batch)} dari {len(todo)}",
                {"done": start, "total": len(todo)})
        try:
            got = _ask(q, batch, model)
        except Exception as exc:  # network, quota, bad key: keep what is already saved
            error = str(exc)
            break
        now = datetime.now().isoformat(timespec="seconds")
        for file, entry in got.items():
            done[file] = {**entry, "at": now}
        judged += len(got)
        (root / POSITIONS_FILE).write_text(
            json.dumps({"question_key": key, "question": q["question"], "hypothesis": q["hypothesis"], "papers": done},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    audit.log("posisi_paper", judged=judged, total=len(todo), model=model, prompt_version=audit.prompt_version(PROMPT))
    return {"judged": judged, "failed": len(todo) - judged, "error": error}
