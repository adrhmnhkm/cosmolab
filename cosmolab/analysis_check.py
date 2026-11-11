"""
cosmolab.analysis_check
~~~~~~~~~~~~~~~~~~~~~~~
Check a paper's AI analysis against the paper's own text.

Every statement in the analysis (thesis, conclusion, premises, findings,
objection, defense) is judged by the claim checker using passages from the
PDF only, never the analysis itself. Every quote is searched for in the PDF
text, so invented or misquoted lines are caught without an LLM.

Results are saved to <root>/review/<stem>.check.json.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from . import config

# Fields checked, in display order: (key, label, is_list)
FIELDS = [
    ("thesis", "Tesis", False),
    ("conclusion", "Kesimpulan", False),
    ("premises", "Premis", True),
    ("key_findings", "Temuan", True),
    ("key_objection", "Keberatan utama", False),
    ("key_defense", "Pembelaan", False),
]
FIELD_LABELS = {k: label for k, label, _ in FIELDS}

QUOTE_FOUND = "ditemukan"
QUOTE_CLOSE = "mirip"
QUOTE_MISSING = "tidak_ditemukan"
QUOTE_LABELS = {
    QUOTE_FOUND: "Ada di PDF",
    QUOTE_CLOSE: "Mirip, tidak persis",
    QUOTE_MISSING: "Tidak ditemukan di PDF",
}


def review_dir() -> Path:
    return config.ROOT / "review"


def check_path(file_name: str) -> Path:
    return review_dir() / f"{Path(file_name).stem}.check.json"


def load_analysis(file_name: str) -> dict:
    path = config.ANALYSIS_DIR / f"{Path(file_name).stem}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def statements(analysis: dict) -> list[dict]:
    """Flatten the analysis into checkable statements: {field, index, text}."""
    out = []
    for key, _label, is_list in FIELDS:
        value = analysis.get(key)
        if is_list:
            for i, v in enumerate(value or []):
                if isinstance(v, str) and len(v.strip()) >= 12:
                    out.append({"field": key, "index": i, "text": v.strip()})
        elif isinstance(value, str) and len(value.strip()) >= 12:
            out.append({"field": key, "index": None, "text": value.strip()})
    return out


# --------------------------------------------------------------- quotes

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)  # join words split across lines: "assump- tions"
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def _page_no(hint) -> int | None:
    m = re.search(r"\d+", str(hint or ""))
    return int(m.group()) if m else None


def find_quote(quote: str, pages: list[dict]) -> dict:
    """Look for a quote in the paper's pages.

    Returns {status, page, ratio}: ratio is the share of the quote found as
    one unbroken run of text on the best page.
    """
    q = _norm(quote)
    if len(q) < 15:
        return {"status": QUOTE_MISSING, "page": None, "ratio": 0.0}
    best_page, best_ratio = None, 0.0
    for p in pages:
        body = _norm(p.get("text") or " ".join(p.get("paragraphs") or []))
        if q in body:
            return {"status": QUOTE_FOUND, "page": p["page"], "ratio": 1.0}
        m = SequenceMatcher(None, q, body, autojunk=False).find_longest_match(0, len(q), 0, len(body))
        ratio = m.size / len(q)
        if ratio > best_ratio:
            best_page, best_ratio = p["page"], ratio
    if best_ratio >= 0.9:
        status = QUOTE_FOUND
    elif best_ratio >= 0.5:
        status = QUOTE_CLOSE
    else:
        status = QUOTE_MISSING
    return {"status": status, "page": best_page if status != QUOTE_MISSING else None, "ratio": round(best_ratio, 2)}


def check_quotes(analysis: dict, pages: list[dict]) -> list[dict]:
    out = []
    for i, q in enumerate(analysis.get("quotes") or []):
        text = q.get("text") if isinstance(q, dict) else str(q)
        hint = q.get("page_hint") if isinstance(q, dict) else None
        found = find_quote(text or "", pages)
        claimed = _page_no(hint)
        found["page_ok"] = None if (claimed is None or found["page"] is None) else (claimed == found["page"])
        out.append({"index": i, "text": text, "page_hint": hint, **found})
    return out


# --------------------------------------------------------------- whole paper

def check_paper(file_name: str, model: str = None, judge=None, evidence_fn=None, pages=None,
                analysis: dict | None = None, paper: dict | None = None, save: bool = True) -> dict:
    """Check one paper's analysis. Returns the report and (by default) saves it."""
    from . import db, entail, extract

    analysis = analysis if analysis is not None else load_analysis(file_name)
    if not analysis:
        raise FileNotFoundError(f"Analisis untuk {file_name} belum ada.")
    pages = pages if pages is not None else extract.get_paper_pages(file_name)
    if paper is None:
        paper = next((p for p in db.get_all_papers_with_analyses() if p.get("file") == file_name), None) \
            or {"file": file_name, "title": file_name}

    items = statements(analysis)
    checked = entail.check_claims([{"text": it["text"], "paper": paper} for it in items], model=model,
                                  judge=judge, evidence_fn=evidence_fn, use_analysis=False) if items else []
    rows = []
    for it, row in zip(items, checked):
        used = [row["evidence"][i] for i in row["evidence_used"] if i < len(row["evidence"])]
        rows.append({
            **it,
            "label": FIELD_LABELS[it["field"]],
            "verdict": row["verdict"],
            "reason": row["reason"],
            "evidence": used or row["evidence"][:1],
        })
    quotes = check_quotes(analysis, pages)

    summary = {}
    for r in rows:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    report = {
        "file": file_name,
        "title": paper.get("title") or file_name,
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": model or config.LLM_MODEL,
        "statements": rows,
        "quotes": quotes,
        "summary": summary,
        "quote_summary": {s: sum(1 for q in quotes if q["status"] == s) for s in QUOTE_LABELS},
    }
    if save:
        path = check_path(file_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            from . import audit

            audit.log("cek_analisis", file=file_name, model=report["model"], summary=summary,
                      quotes=report["quote_summary"])
        except Exception:
            pass
    return report


def load_check(file_name: str) -> dict | None:
    try:
        return json.loads(check_path(file_name).read_text(encoding="utf-8"))
    except Exception:
        return None


def score(report: dict | None) -> dict:
    """Short numbers for lists and badges: how many statements and quotes passed."""
    if not report:
        return {"checked": False}
    from . import entail

    rows = report.get("statements") or []
    quotes = report.get("quotes") or []
    ok = sum(1 for r in rows if r["verdict"] == entail.SUPPORTED)
    flagged = sum(1 for r in rows if r["verdict"] in (entail.UNSUPPORTED, entail.PARTIAL))
    q_ok = sum(1 for q in quotes if q["status"] == QUOTE_FOUND)
    return {"checked": True, "statements": len(rows), "supported": ok, "flagged": flagged,
            "quotes": len(quotes), "quotes_found": q_ok, "time": report.get("time")}


def check_many(files: list[str], model: str = None, progress_cb=None) -> dict:
    """Check several papers one after another. Returns {file: score or error}."""
    out = {}
    for n, f in enumerate(files, 1):
        try:
            out[f] = score(check_paper(f, model=model))
        except Exception as e:
            out[f] = {"checked": False, "error": str(e)[:200]}
        if progress_cb:
            progress_cb(n, len(files), f)
    return out
