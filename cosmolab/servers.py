"""
cosmolab.servers
~~~~~~~~~~~~~~~~
Starts and stops one dashboard per project for the team lobby (`cosmolab tim`).

The data folder of a dashboard is fixed for its whole process (config.ROOT),
so every project runs in its own Streamlit process on its own port. The lobby
starts a project's dashboard the first time someone opens it, reuses it after
that, and stops dashboards nobody has used for a while.

Running dashboards are listed in shared/servers.json. Each dashboard touches a
file in shared/aktif/ on every click, which is how the lobby knows it is idle.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config

MAIN = "_utama"           # key for the main data folder (no client project)
PORT_START = 8502         # the lobby itself runs on 8501
PORT_END = 8599
MAX_RUNNING = 4           # each dashboard holds its own memory, including the embedding model
IDLE_HOURS = 2.0          # a dashboard unused this long is stopped
MIN_IDLE_TO_REPLACE = 15 * 60  # at the limit, only a dashboard idle this many seconds makes room
START_TIMEOUT = 60

SHARED_DIR = None  # None = <repo>/shared; tests point this elsewhere
_LOCK = threading.Lock()


class LobbyFull(RuntimeError):
    """Every dashboard slot is taken by one that is still in use."""


def shared_dir() -> Path:
    return SHARED_DIR or (config.PROJECT_ROOT / "shared")


def _registry_path() -> Path:
    return shared_dir() / "servers.json"


def heartbeat_path(key: str) -> Path:
    return shared_dir() / "aktif" / key


def key_of(project: str | None) -> str:
    return project or MAIN


def _load() -> dict:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _answers(host: str, port: int, timeout: float = 0.5) -> bool:
    """True when something accepts connections on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _free_port(host: str, taken: set[int]) -> int:
    for port in range(PORT_START, PORT_END + 1):
        if port in taken or _answers(host, port, timeout=0.2):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
        return port
    raise RuntimeError(f"Tidak ada port kosong antara {PORT_START} dan {PORT_END}.")


def touch(key: str) -> None:
    """Mark a dashboard as used now. Called by the dashboard on every click."""
    path = heartbeat_path(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError:
        pass


def idle_seconds(key: str, entry: dict | None = None) -> float:
    try:
        last = heartbeat_path(key).stat().st_mtime
    except OSError:
        last = (entry or {}).get("started_ts", time.time())
    return max(0.0, time.time() - last)


def running() -> dict:
    """Dashboards that still answer, by key. Entries of dashboards that died are dropped."""
    with _LOCK:
        data = _load()
        alive = {k: v for k, v in data.items() if _answers(v.get("host", "127.0.0.1"), int(v["port"]))}
        if alive != data:
            _save(alive)
        return alive


def _kill(pid: int) -> None:
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def stop(key: str) -> None:
    with _LOCK:
        data = _load()
        entry = data.pop(key, None)
        _save(data)
    if entry:
        _kill(int(entry.get("pid") or 0))


def stop_all() -> None:
    # running() first drops entries whose port is silent: after a restart their pid may belong to another program.
    for key in list(running()):
        stop(key)


def stop_idle(hours: float = IDLE_HOURS) -> list[str]:
    """Stop dashboards unused for `hours`. Returns the keys stopped."""
    stopped = []
    for key, entry in running().items():
        if idle_seconds(key, entry) >= hours * 3600:
            stop(key)
            stopped.append(key)
    return stopped


def _spawn(project: str | None, host: str, port: int) -> subprocess.Popen:
    web = Path(__file__).parent / "web.py"
    env = os.environ.copy()
    env["COSMOLAB_TEAM_MODE"] = "1"
    env["COSMOLAB_FROM_LOBBY"] = key_of(project)
    if project:
        env["COSMOLAB_PROJECT"] = project
    else:
        env.pop("COSMOLAB_PROJECT", None)
    log_dir = shared_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / f"{key_of(project)}.log", "ab")
    args = [sys.executable, "-m", "streamlit", "run", str(web), "--server.port", str(port),
            "--server.address", host, "--server.headless", "true"]
    # Same console as the lobby: closing the server window stops these dashboards too.
    return subprocess.Popen(args, env=env, cwd=str(config.PROJECT_ROOT), stdout=log, stderr=subprocess.STDOUT)


def ensure(project: str | None, host: str) -> int:
    """Port of the project's dashboard, starting it first if it is not running."""
    key = key_of(project)
    if project:
        config.validate_project_name(project)
    current = running()
    if key in current:
        return int(current[key]["port"])

    if len(current) >= MAX_RUNNING:
        # Make room by stopping the dashboard that has gone unused the longest.
        idlest = max(current, key=lambda k: idle_seconds(k, current[k]))
        if idle_seconds(idlest, current[idlest]) < MIN_IDLE_TO_REPLACE:
            raise LobbyFull(f"Sudah {MAX_RUNNING} proyek terbuka dan semuanya sedang dipakai. "
                            "Coba lagi nanti, atau minta admin menutup salah satu.")
        stop(idlest)

    with _LOCK:
        data = _load()
        port = _free_port(host, {int(v["port"]) for v in data.values()})
        proc = _spawn(project, host, port)
        data[key] = {"project": project or "", "port": port, "host": host, "pid": proc.pid,
                     "started": datetime.now().isoformat(timespec="seconds"), "started_ts": time.time()}
        _save(data)
    touch(key)

    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if _answers(host, port):
            return port
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    stop(key)
    raise RuntimeError(f"Dashboard proyek gagal menyala. Lihat {shared_dir() / 'logs' / (key + '.log')}.")
