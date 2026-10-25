import json
import re
from pathlib import Path
from . import config


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s)[:120] or "untitled"


def load_done() -> set:
    if config.DONE_FILE.exists():
        return set(json.loads(config.DONE_FILE.read_text()))
    return set()


def save_done(done: set) -> None:
    config.DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.DONE_FILE.write_text(json.dumps(sorted(done)))


def append_meta(record: dict) -> None:
    config.META_FILE.parent.mkdir(parents=True, exist_ok=True)
    with config.META_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")


def read_meta() -> list:
    if not config.META_FILE.exists():
        return []
    return [json.loads(l) for l in config.META_FILE.read_text().splitlines() if l.strip()]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text())
