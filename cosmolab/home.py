"""What the Home page shows: work waiting, a project summary, recent activity.

The owner view (the dashboard run without team mode) adds the setup status,
every project at a glance, and AI usage this month. Everything here is read
from files that already exist; nothing is stored for the Home page itself.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from . import review as _review
from . import usage as _usage

BACKUP_MAX_DAYS = 7

EVENT_LABELS = {
    "review_draf": "Review draf",
    "review_draf_kirim": "Word review dibuat",
    "analisis": "Analisis paper",
    "cek_analisis": "Cek analisis",
    "cek_klaim": "Cek klaim",
    "cek_metadata": "Cek metadata",
    "evaluasi": "Evaluasi",
    "koreksi": "Koreksi",
    "tanya": "Tanya koleksi",
}


# usage.jsonl stores the module that called the AI; these are the names people know.
FEATURE_LABELS = {
    "analyze": "Analisis paper",
    "ask": "Tanya koleksi",
    "ask_agent": "Tanya koleksi (agen)",
    "authors": "Cari nama penulis",
    "entail": "Cek klaim terhadap sumber",
    "evaluate": "Evaluasi jawaban",
    "passages": "Kutipan dari paper",
    "retrieval": "Pencarian di koleksi",
    "review": "Review draf",
    "writer": "Tulis artikel",
    "lainnya": "Lainnya",
}


def feature_label(key: str) -> str:
    return FEATURE_LABELS.get(key, key.replace("_", " ").capitalize())


def is_owner() -> bool:
    """The dashboard run on the owner's own computer, not the shared team login."""
    return os.environ.get("COSMOLAB_TEAM_MODE") != "1"


# ---------------------------------------------------------------------------
# Work waiting
# ---------------------------------------------------------------------------

def _saved_reviews(root: Path) -> list[dict]:
    out = []
    folder = Path(root) / "reviews"
    if not folder.exists():
        return out
    for jp in sorted(folder.glob("*.json"), reverse=True):
        try:
            report = json.loads(jp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(_review._normalize(report, jp.stem))
    return out


def _sent(root: Path) -> dict:
    """Source file -> latest time a Word review was made for it, from the audit log.

    Covers reviews exported before the review itself recorded its Word file.
    """
    out = {}
    for row in _read_audit(root):
        if row.get("event") == "review_draf_kirim" and row.get("file"):
            out[row["file"]] = max(out.get(row["file"], ""), str(row.get("time", "")))
    return out


def review_issues(report: dict, sent: dict | None = None) -> list[str]:
    """What is still open on one review. Empty once the Word file has been made."""
    if report.get("docx_path"):
        return []
    key = report.get("source") or report.get("title")
    if sent and key in sent and sent[key] >= str(report.get("reviewed_at", "")):
        return []
    issues = []
    d = _review.decision_counts(report)
    total = len(report.get("comments") or [])
    if d[_review.PENDING]:
        issues.append(f"{d[_review.PENDING]} dari {total} komentar belum diputuskan")
    sim = report.get("similarity") or {}
    if sim.get("weak"):
        issues.append("pembanding kemiripan lemah")
    missing = [it for it in (report.get("coverage") or {}).get("items", []) if it.get("status") == "tidak_tersedia"]
    if missing:
        issues.append(f"{len(missing)} sumber perlu diminta ke mahasiswa")
    if not d[_review.PENDING]:
        issues.append("siap, Word belum dibuat")
    return issues


def todo(papers: list[dict], root: Path | None = None) -> list[dict]:
    """[{"kind", "title", "detail", "stem"}]: reviews with open work, then papers not yet analyzed."""
    items = []
    root = root or config.ROOT
    sent = _sent(root)
    for report in _saved_reviews(root):
        issues = review_issues(report, sent)
        if issues:
            d = _review.decision_counts(report)
            total = len(report.get("comments") or [])
            items.append({"kind": "review", "title": report.get("title") or report["stem"],
                          "detail": "; ".join(issues), "stem": report["stem"], "issues": issues,
                          "decided": total - d[_review.PENDING], "total": total})
    unanalyzed = sum(1 for p in papers if not p.get("thesis"))
    if unanalyzed:
        items.append({"kind": "analisis", "title": f"{unanalyzed} paper belum dianalisis",
                      "detail": "Analisis dulu supaya bisa dipakai di Tanya koleksi, tinjauan pustaka, dan cek kemiripan.",
                      "stem": ""})
    return items


def summary(papers: list[dict], root: Path | None = None) -> dict:
    from . import sinta

    files = {p.get("file") for p in papers}
    try:
        ranked = sum(1 for f in sinta.ranks_by_file() if f in files)
    except Exception:
        ranked = 0
    return {"papers": len(papers), "analyzed": sum(1 for p in papers if p.get("thesis")),
            "reviews": len(_saved_reviews(root or config.ROOT)), "sinta": ranked}


# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------

def _read_audit(root: Path) -> list[dict]:
    path = Path(root) / "audit.jsonl"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


def recent(limit: int = 5, roots: list[tuple[str, Path]] | None = None) -> list[dict]:
    """Newest audit entries from the given roots (default: the active one)."""
    roots = roots or [(config.PROJECT or "", config.ROOT)]
    rows = []
    for label, root in roots:
        for row in _read_audit(root):
            rows.append({**row, "_root": label})
    rows.sort(key=lambda r: r.get("time", ""), reverse=True)
    return rows[:limit]


def describe(row: dict) -> str:
    label = EVENT_LABELS.get(row.get("event"), str(row.get("event", "")).replace("_", " ").capitalize())
    target = row.get("file") or row.get("question") or ""
    if target:
        target = Path(str(target)).name if row.get("file") else str(target)
        label += f": {target[:80]}"
    if row.get("event") == "review_draf" and row.get("comments"):
        label += f", {row['comments']} komentar"
    return label


def when(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{t:%d %b %H:%M}"


# ---------------------------------------------------------------------------
# Owner view
# ---------------------------------------------------------------------------

def last_backup() -> datetime | None:
    from . import backup

    folder = backup.default_dir()
    zips = list(folder.glob("*.zip")) if folder.exists() else []
    if not zips:
        return None
    return datetime.fromtimestamp(max(z.stat().st_mtime for z in zips))


def setup_checks(now: datetime | None = None) -> list[dict]:
    """[{"label", "ok", "detail"}]; detail says how to fix what is not ok."""
    from . import sinta

    now = now or datetime.now()
    try:
        n_sinta = len(sinta.load())
    except Exception:
        n_sinta = 0
    backed = last_backup()
    age = (now - backed).days if backed else None
    return [
        {"label": "Kunci API AI", "ok": bool(config.LLM_API_KEY),
         "detail": "Terisi." if config.LLM_API_KEY else "Belum diisi: analisis, komentar review, dan tanya koleksi tidak "
                                                       "bisa jalan. Isi LLM_API_KEY di .env."},
        {"label": "Email untuk Crossref dan OpenAlex", "ok": config.EMAIL != "you@example.com",
         "detail": "Terisi." if config.EMAIL != "you@example.com" else
         "Masih contoh. Layanan bisa membatasi akses. Isi COSMOLAB_EMAIL di .env."},
        {"label": "Kunci CORE", "ok": bool(config.CORE_API_KEY),
         "detail": "Terisi." if config.CORE_API_KEY else
         "Belum diisi: Cari & tambah paper tidak mencari di CORE. Isi CORE_API_KEY di .env."},
        {"label": "Tarif AI", "ok": bool(_usage.pricing()),
         "detail": "Terisi." if _usage.pricing() else
         "Belum diisi: biaya hanya tampil sebagai jumlah token. Isi COSMOLAB_PRICING di .env."},
        {"label": "Daftar jurnal SINTA", "ok": n_sinta > 0,
         "detail": f"{n_sinta} jurnal." if n_sinta else
         "Kosong: label SINTA tidak muncul. Isi di Cari & tambah paper, tab Peringkat SINTA."},
        {"label": "Backup", "ok": age is not None and age <= BACKUP_MAX_DAYS,
         "detail": ("Belum pernah. Jalankan: cosmolab backup" if age is None else
                    f"Terakhir {backed:%d %b %Y}" + ("." if age <= BACKUP_MAX_DAYS else
                                                     f", {age} hari lalu. Jalankan: cosmolab backup"))},
    ]


def _db_counts(root: Path) -> tuple[int, int]:
    path = Path(root) / "cosmolab.db"
    if not path.exists():
        return 0, 0
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            papers = con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
            analyzed = con.execute("SELECT COUNT(*) FROM analyses WHERE thesis IS NOT NULL AND thesis != ''").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return 0, 0
    return papers, analyzed


def _month_cost(root: Path, month: str) -> tuple[int, float | None]:
    rows = _usage.load(root, month)
    tokens = sum(r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in rows)
    costs = [_usage.cost(r) for r in rows]
    known = [c for c in costs if c is not None]
    return tokens, (sum(known) if known else None)


def projects_overview(month: str | None = None) -> list[dict]:
    month = month or datetime.now().strftime("%Y-%m")
    out = []
    for label, root in _usage.all_roots():
        papers, analyzed = _db_counts(root)
        reviews = _saved_reviews(root)
        pending = sum(_review.decision_counts(r)[_review.PENDING] for r in reviews)
        tokens, cost = _month_cost(root, month)
        out.append({"Proyek": label, "Paper": papers, "Dianalisis": analyzed, "Review draf": len(reviews),
                    "Komentar belum diputuskan": pending, "Token AI bulan ini": tokens,
                    "Biaya AI bulan ini": _usage.format_money(cost) if cost is not None else "-"})
    return out


def usage_by_feature(month: str | None = None) -> list[dict]:
    month = month or datetime.now().strftime("%Y-%m")
    rows = []
    for _, root in _usage.all_roots():
        rows += _usage.load(root, month)
    return _usage.summarize(rows, by="feature")


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------

RECENT_YEARS = 5
# Indonesian names for the analysis field `argument_type`.
METHOD_LABELS = {
    "empiris_kuantitatif": "Empiris kuantitatif",
    "kualitatif_studi_kasus": "Kualitatif / studi kasus",
    "kajian_literatur": "Kajian literatur",
    "komparatif": "Komparatif",
    "yuridis_normatif": "Yuridis normatif",
    "konseptual_teoretis": "Konseptual / teoretis",
    "filosofis_rasional": "Filosofis",
    "other": "Lainnya",
}
SOURCE_LABELS = {"arxiv": "arXiv", "openalex": "OpenAlex", "doaj": "DOAJ", "crossref": "Crossref",
                 "semanticscholar": "Semantic Scholar", "core": "CORE", "lokal": "Unggahan lokal"}


def kpis(papers: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now()
    month = now.strftime("%Y-%m")
    reviews = _saved_reviews(config.ROOT)
    sent = _sent(config.ROOT)
    return {
        "papers": len(papers),
        "new_this_month": sum(1 for p in papers if str(p.get("created_at") or "").startswith(month)),
        "analyzed": sum(1 for p in papers if p.get("thesis")),
        "pending": sum(_review.decision_counts(r)[_review.PENDING] for r in reviews),
        "reviews_open": sum(1 for r in reviews if review_issues(r, sent)),
    }


def year_counts(papers: list[dict], now: datetime | None = None) -> dict:
    """{"rows": [{"Tahun", "Paper", "Baru"}], "recent_share": 0..1, "unknown": n}. Baru = last 5 years."""
    this_year = (now or datetime.now()).year
    years, unknown = Counter(), 0
    for p in papers:
        y = str(p.get("year") or "")[:4]
        if y.isdigit():
            years[int(y)] += 1
        else:
            unknown += 1
    known = sum(years.values())
    recent = sum(n for y, n in years.items() if y > this_year - RECENT_YEARS)
    rows = [{"Tahun": str(y), "Paper": n, "Baru": y > this_year - RECENT_YEARS} for y, n in sorted(years.items())]
    return {"rows": rows, "recent_share": recent / known if known else 0.0, "unknown": unknown}


def method_counts(papers: list[dict]) -> list[dict]:
    """[{"Nama", "Paper"}] by type of research; papers not yet analyzed are left out."""
    return ranked_counts([METHOD_LABELS.get(p.get("argument_type") or "other", "Lainnya")
                          for p in papers if p.get("thesis")])


def ranked_counts(values: list[str], top: int = 6) -> list[dict]:
    """[{"Nama", "Paper"}], largest first; the tail folds into "Lainnya"."""
    c = Counter(v for v in values if v)
    rows = [{"Nama": k, "Paper": n} for k, n in c.most_common(top)]
    rest = sum(c.values()) - sum(r["Paper"] for r in rows)
    if rest:
        rows.append({"Nama": "Lainnya", "Paper": rest})
    return rows


def source_counts(papers: list[dict]) -> list[dict]:
    return ranked_counts([SOURCE_LABELS.get(p.get("source") or "", p.get("source") or "Lainnya") for p in papers])


def faculty_counts(papers: list[dict], labels: dict) -> list[dict]:
    return ranked_counts([labels.get(p.get("faculty"), p.get("faculty") or "") for p in papers])


def activity_days(roots: list[tuple[str, Path]] | None = None, weeks: int = 12,
                  today: date | None = None) -> list[dict]:
    """One row per day for the last `weeks` weeks, ending this week: {"Tanggal", "Minggu", "Hari", "Kegiatan"}."""
    today = today or date.today()
    roots = roots or [(config.PROJECT or "", config.ROOT)]
    counts = Counter()
    for _, root in roots:
        for row in _read_audit(root):
            counts[str(row.get("time", ""))[:10]] += 1
    end = today + timedelta(days=6 - today.weekday())  # Sunday of this week
    start = end - timedelta(days=weeks * 7 - 1)       # a Monday
    out = []
    for i in range(weeks * 7):
        d = start + timedelta(days=i)
        if d > today:
            break
        out.append({"Tanggal": d.isoformat(), "Minggu": i // 7, "Hari": d.weekday(),
                    "Kegiatan": counts.get(d.isoformat(), 0)})
    return out


def usage_days(days: int = 30, today: date | None = None) -> list[dict]:
    """AI tokens per day over the last `days` days, across every project: [{"Tanggal", "Token"}]."""
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    tokens = Counter()
    for _, root in _usage.all_roots():
        for r in _usage.load(root):
            day = str(r.get("ts", ""))[:10]
            if day >= start.isoformat():
                tokens[day] += r.get("prompt_tokens", 0) + r.get("completion_tokens", 0)
    return [{"Tanggal": (start + timedelta(days=i)).isoformat(),
             "Token": tokens.get((start + timedelta(days=i)).isoformat(), 0)} for i in range(days)]


def paper_growth(papers: list[dict], days: int = 30, today: date | None = None) -> list[int]:
    """Collection size at the end of each of the last `days` days (for a sparkline)."""
    today = today or date.today()
    added = sorted(str(p.get("created_at") or "")[:10] for p in papers)
    out = []
    for i in range(days):
        day = (today - timedelta(days=days - 1 - i)).isoformat()
        out.append(sum(1 for a in added if a and a <= day) + sum(1 for a in added if not a))
    return out


def weekly_activity(rows: list[dict]) -> list[int]:
    """Activity per week from activity_days rows (for a sparkline)."""
    weeks = Counter()
    for r in rows:
        weeks[r["Minggu"]] += r["Kegiatan"]
    return [weeks.get(w, 0) for w in range(max((r["Minggu"] for r in rows), default=-1) + 1)]
