"""
cosmolab.corrections
~~~~~~~~~~~~~~~~~~~~
Researcher corrections to an AI analysis.

A researcher can mark any analysis statement as correct, wrong, or edit it.
Corrections live in <root>/review/<stem>.review.json, apart from the AI's
analysis file, so they survive and can be undone. db.sync applies them, so
every page and every AI answer uses the corrected version.

Each correction stores the original text it was made against. If the paper
is analysed again and that text changes, the correction is marked stale
instead of being applied to the wrong statement.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

from . import config

CORRECT = "benar"
WRONG = "salah"
EDITED = "diedit"
LABELS = {CORRECT: "Benar (dicek peneliti)", WRONG: "Salah (dibuang)", EDITED: "Diedit peneliti"}

LIST_FIELDS = {"premises", "key_findings", "notable_concepts"}
TEXT_FIELDS = {"thesis", "conclusion", "key_objection", "key_defense", "research_method"}


def key_of(field: str, index: int | None = None) -> str:
    return f"{field}.{index}" if index is not None else field


def _split(key: str) -> tuple[str, int | None]:
    field, _, idx = key.partition(".")
    return field, (int(idx) if idx.isdigit() else None)


def path_for(file_or_stem: str) -> Path:
    return config.ROOT / "review" / f"{Path(file_or_stem).stem}.review.json"


def load(file_or_stem: str) -> dict:
    try:
        return json.loads(path_for(file_or_stem).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(file_or_stem: str, data: dict) -> None:
    path = path_for(file_or_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _current(analysis: dict, field: str, index: int | None):
    value = analysis.get(field)
    if index is None:
        return value
    if isinstance(value, list) and 0 <= index < len(value):
        return value[index]
    return None


def set_review(file_or_stem: str, field: str, index: int | None, status: str, value: str | None = None,
               note: str = "", by: str = "", analysis: dict | None = None) -> dict:
    """Record one correction. `analysis` is the AI analysis (loaded from disk when omitted)."""
    if status not in LABELS:
        raise ValueError(f"Status tidak dikenal: {status}")
    if status == EDITED and not (value or "").strip():
        raise ValueError("Teks hasil edit tidak boleh kosong.")
    if analysis is None:
        from .analysis_check import load_analysis

        analysis = load_analysis(file_or_stem)
    data = load(file_or_stem)
    entry = {
        "status": status,
        "original": _current(analysis, field, index),
        "value": (value or "").strip() if status == EDITED else None,
        "note": note.strip(),
        "by": by,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    data[key_of(field, index)] = entry
    _save(file_or_stem, data)
    try:
        from . import audit

        audit.log("koreksi", file=Path(file_or_stem).stem, field=key_of(field, index), status=status,
                  user=by or None, note=entry["note"] or None)
    except Exception:
        pass
    return entry


def clear_review(file_or_stem: str, field: str, index: int | None = None, by: str = "") -> None:
    data = load(file_or_stem)
    if data.pop(key_of(field, index), None) is not None:
        _save(file_or_stem, data)
        try:
            from . import audit

            audit.log("koreksi", file=Path(file_or_stem).stem, field=key_of(field, index), status="dibatalkan",
                      user=by or None)
        except Exception:
            pass


def is_stale(entry: dict, analysis: dict, key: str) -> bool:
    field, index = _split(key)
    return entry.get("original") != _current(analysis, field, index)


def apply(file_or_stem: str, analysis: dict, reviews: dict | None = None) -> dict:
    """Return a copy of the analysis with corrections applied.

    Edited statements replace the AI text; wrong ones are removed (lists) or
    emptied (text fields). Adds "_review": {key: status} so pages can show
    which statements a researcher has checked.
    """
    reviews = load(file_or_stem) if reviews is None else reviews
    if not reviews:
        return analysis
    out = copy.deepcopy(analysis)
    marks, drop = {}, {}
    for key, entry in reviews.items():
        if is_stale(entry, analysis, key):
            marks[key] = "kedaluwarsa"
            continue
        field, index = _split(key)
        status = entry.get("status")
        marks[key] = status
        if status == EDITED:
            if index is None:
                out[field] = entry["value"]
            elif isinstance(out.get(field), list):
                out[field][index] = entry["value"]
        elif status == WRONG:
            if index is None:
                out[field] = None
            else:
                drop.setdefault(field, set()).add(index)
    for field, idxs in drop.items():
        if isinstance(out.get(field), list):
            out[field] = [v for i, v in enumerate(out[field]) if i not in idxs]
    out["_review"] = marks
    return out


def summary(file_or_stem: str, analysis: dict | None = None) -> dict:
    data = load(file_or_stem)
    counts = {s: 0 for s in LABELS}
    stale = 0
    if analysis is None and data:
        from .analysis_check import load_analysis

        analysis = load_analysis(file_or_stem)
    for key, e in data.items():
        if analysis is not None and is_stale(e, analysis, key):
            stale += 1
        else:
            counts[e.get("status")] = counts.get(e.get("status"), 0) + 1
    return {"total": len(data), "stale": stale, **counts}
