"""
cosmolab.backup
~~~~~~~~~~~~~~~
Zip one project's data folder (or the main data/ folder) for safekeeping.

The database is copied with SQLite's backup API, so the copy is consistent
even while the dashboard is running. The LLM cache is left out by default
because it rebuilds itself.
"""

from __future__ import annotations

import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import config

_DB_SIDE_FILES = ("-wal", "-shm", "-journal")


def default_dir() -> Path:
    return config.PROJECT_ROOT / "backups"


def _copy_db(src: Path, dst: Path) -> None:
    source = sqlite3.connect(src, timeout=30)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def make_backup(out_dir: Path | None = None, include_pdf: bool = True, include_cache: bool = False) -> dict:
    """Write <out_dir>/<project>_<timestamp>.zip and return its path and counts."""
    root = Path(config.ROOT)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder data tidak ditemukan: {root}")
    out_dir = Path(out_dir) if out_dir else default_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = config.PROJECT or "data"
    zip_path = out_dir / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.zip"

    db_file = Path(config.DB_FILE)
    db_names = {db_file.name} | {db_file.name + s for s in _DB_SIDE_FILES}
    skip_dirs = set()
    if not include_pdf:
        skip_dirs.add("pdf")
    if not include_cache:
        skip_dirs.add("cache")

    files = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if rel.parts[0] in skip_dirs or out_dir in path.parents:
                continue
            if len(rel.parts) == 1 and rel.name in db_names:
                continue
            zf.write(path, Path(name) / rel)
            files += 1
        if db_file.exists():
            with tempfile.TemporaryDirectory() as tmp:
                snap = Path(tmp) / db_file.name
                _copy_db(db_file, snap)
                zf.write(snap, Path(name) / db_file.name)
                files += 1

    return {"path": zip_path, "files": files, "size": zip_path.stat().st_size}
