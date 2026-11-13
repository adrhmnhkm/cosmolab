"""
cosmolab.audit
~~~~~~~~~~~~~~
Append-only activity log for reproducibility.

Each AI step that produces research content (analysis, answer, claim check,
analysis check, evaluation run, researcher correction) writes one JSON line
to <root>/audit.jsonl: time, event, model, prompt version, and the inputs
needed to repeat it. The log can be exported for a paper's methods section.
"""

from __future__ import annotations

import csv
import getpass
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

from . import config

EVENT_LABELS = {
    "analisis": "Analisis paper",
    "tanya": "Tanya koleksi",
    "cek_klaim": "Cek klaim jawaban",
    "cek_analisis": "Cek analisis ke PDF",
    "evaluasi": "Uji akurasi",
    "koreksi": "Koreksi peneliti",
    "cek_metadata": "Cek metadata",
    "harvest": "Cari paper",
    "telusuri_sitasi": "Telusuri sitasi",
    "review_draf": "Review draf mahasiswa",
    "pertanyaan_riset": "Pertanyaan riset diubah",
    "posisi_paper": "Posisi paper dinilai",
    "latihan_sidang": "Latihan sidang",
    "review_draf_kirim": "Kirim catatan review",
}


def log_path() -> Path:
    return config.ROOT / "audit.jsonl"


def prompt_version(*prompts: str) -> str:
    """Short hash of the prompt text, so a changed prompt shows up in the log."""
    return hashlib.sha1("\n".join(p or "" for p in prompts).encode("utf-8")).hexdigest()[:10]


def _who() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def log(event: str, **data) -> dict:
    """Append one entry. Never raises: logging must not break the research step."""
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "event": event,
             "user": data.pop("user", None) or _who(), "project": config.PROJECT or ""}
    entry.update({k: v for k, v in data.items() if v is not None})
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    return entry


def read(limit: int | None = None, event: str | None = None) -> list[dict]:
    """Entries, newest first."""
    rows = []
    try:
        for line in log_path().read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if event and row.get("event") != event:
                continue
            rows.append(row)
    except FileNotFoundError:
        return []
    rows.reverse()
    return rows[:limit] if limit else rows


def to_csv(rows: list[dict]) -> str:
    cols = ["time", "event", "user", "project", "model", "prompt_version", "file", "question", "summary"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols + ["detail"])
    for r in rows:
        rest = {k: v for k, v in r.items() if k not in cols}
        w.writerow([json.dumps(r.get(c), ensure_ascii=False) if isinstance(r.get(c), (dict, list)) else (r.get(c) or "")
                    for c in cols] + [json.dumps(rest, ensure_ascii=False, default=str) if rest else ""])
    return buf.getvalue()


def methods_text(rows: list[dict]) -> str:
    """A short paragraph for a methods section, built from the log."""
    if not rows:
        return "Belum ada aktivitas yang tercatat."
    times = sorted(r["time"] for r in rows if r.get("time"))
    models = sorted({r["model"] for r in rows if r.get("model")})
    counts = {}
    for r in rows:
        counts[r["event"]] = counts.get(r["event"], 0) + 1
    parts = [f"{EVENT_LABELS.get(e, e).lower()} ({n} kali)" for e, n in sorted(counts.items(), key=lambda x: -x[1])]
    text = (
        f"Antara {times[0][:10]} dan {times[-1][:10]}, CosmoLab mencatat {len(rows)} langkah berbantuan AI: "
        f"{', '.join(parts)}. Model bahasa yang dipakai: {', '.join(models) or '-'}."
    )
    if counts.get("cek_klaim"):
        text += " Klaim bersitasi dalam jawaban AI dicek ke kutipan teks paper sumbernya."
    if counts.get("cek_analisis"):
        text += " Hasil analisis AI dicek ulang ke isi PDF."
    if counts.get("koreksi"):
        text += f" Peneliti meninjau dan mengoreksi {counts['koreksi']} pernyataan analisis."
    return text + " Log lengkap (waktu, model, versi prompt, masukan) tersedia sebagai lampiran."
