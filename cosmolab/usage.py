"""
CosmoLab AI usage tracking.

Every chat completion made through the OpenAI client is logged to
<project folder>/usage.jsonl with its token counts, the model, and the CosmoLab
feature that made the call. This gives the cost of each client project, which
is what the firm needs to price its work.

Prices are read from COSMOLAB_PRICING in .env, per 1 million tokens:
    COSMOLAB_PRICING=gemini-3-8-flash:4500:18000;deepseek-v4-pro:9000:36000
    COSMOLAB_PRICING_CURRENCY=IDR
"""

import json
import sys
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import config

USAGE_FILE = "usage.jsonl"
_lock = threading.Lock()
_installed = False


def _caller_feature() -> str:
    """Name of the CosmoLab module that made the AI call (writer, ask, analyze, ...)."""
    frame = sys._getframe(2)
    while frame:
        name = frame.f_globals.get("__name__", "")
        if name.startswith("cosmolab.") and name != __name__:
            return name.split(".", 1)[1]
        if frame.f_code.co_filename.replace("\\", "/").endswith("cosmolab/web.py"):
            return "dashboard"
        frame = frame.f_back
    return "lainnya"


def record(model: str, prompt_tokens: int, completion_tokens: int, feature: str = "lainnya", root: Path | None = None):
    root = Path(root or config.ROOT)
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "project": config.PROJECT or "",
        "feature": feature,
        "model": model or "",
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        with _lock, (root / USAGE_FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # usage logging must never break the actual work


def install():
    """Wrap the OpenAI chat completion call once so every request is logged."""
    global _installed
    if _installed:
        return
    try:
        from openai.resources.chat.completions import Completions
    except Exception:
        return

    original = Completions.create

    def create(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            record(
                model=getattr(response, "model", None) or kwargs.get("model", ""),
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                feature=_caller_feature(),
            )
        return response

    create.__wrapped__ = original
    Completions.create = create
    _installed = True


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def pricing() -> dict:
    """{model: (input_price, output_price)} per 1M tokens, from COSMOLAB_PRICING."""
    raw = config._env("COSMOLAB_PRICING")
    prices = {}
    for part in raw.split(";"):
        bits = [b.strip() for b in part.split(":")]
        if len(bits) == 3 and bits[0]:
            try:
                prices[bits[0]] = (float(bits[1]), float(bits[2]))
            except ValueError:
                continue
    return prices


def currency() -> str:
    return config._env("COSMOLAB_PRICING_CURRENCY", "IDR")


def cost(entry: dict, prices: dict | None = None) -> float | None:
    prices = pricing() if prices is None else prices
    p = prices.get(entry.get("model", ""))
    if not p:
        return None
    return (entry["prompt_tokens"] * p[0] + entry["completion_tokens"] * p[1]) / 1_000_000


def load(root: Path | None = None, month: str | None = None) -> list[dict]:
    path = Path(root or config.ROOT) / USAGE_FILE
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if month and not row.get("ts", "").startswith(month):
            continue
        rows.append(row)
    return rows


def summarize(rows: list[dict], by: str = "feature") -> list[dict]:
    """Group rows by a key ("feature", "model", "month", "project")."""
    prices = pricing()
    groups = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "unpriced": 0})
    for r in rows:
        key = r.get("ts", "")[:7] if by == "month" else (r.get(by) or "-")
        g = groups[key]
        g["calls"] += 1
        g["prompt_tokens"] += r.get("prompt_tokens", 0)
        g["completion_tokens"] += r.get("completion_tokens", 0)
        c = cost(r, prices)
        if c is None:
            g["unpriced"] += 1
        else:
            g["cost"] += c
    return [{"key": k, **v, "total_tokens": v["prompt_tokens"] + v["completion_tokens"]}
            for k, v in sorted(groups.items(), key=lambda kv: -(kv[1]["prompt_tokens"] + kv[1]["completion_tokens"]))]


def all_roots() -> list[tuple[str, Path]]:
    """(label, folder) for the legacy data folder and every client project."""
    roots = [("(data utama)", config._default_root())]
    roots += [(p["name"], Path(p["path"])) for p in config.list_projects()]
    return roots


def format_money(value: float) -> str:
    cur = currency()
    if cur.upper() == "IDR":
        return "Rp " + f"{value:,.0f}".replace(",", ".")
    return f"{cur} {value:,.2f}"
