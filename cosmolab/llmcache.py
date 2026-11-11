"""
cosmolab.llmcache
~~~~~~~~~~~~~~~~~
Disk cache for small, repeatable LLM calls (query expansion, passage rerank).

Key = sha1 of (kind, model, payload). Same question over the same passages
gives the same answer at temperature 0, so a repeat costs no tokens. Stored in
<root>/cache/llm.json. Turn off with COSMOLAB_LLM_CACHE=0.
"""

from __future__ import annotations

import hashlib
import json
import threading

from . import config

_LOCK = threading.Lock()
_MAX = 5000


def enabled() -> bool:
    return config.LLM_CACHE


def _path():
    return config.ROOT / "cache" / "llm.json"


def key(kind: str, model: str, payload) -> str:
    raw = json.dumps([kind, model or "", payload], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(k: str):
    if not enabled():
        return None
    with _LOCK:
        return _load().get(k)


def put(k: str, value) -> None:
    if not enabled() or value is None:
        return
    with _LOCK:
        data = _load()
        data[k] = value
        if len(data) > _MAX:
            data = dict(list(data.items())[-_MAX:])
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(p)
        except Exception:
            pass


def clear() -> None:
    with _LOCK:
        try:
            _path().unlink()
        except FileNotFoundError:
            pass
