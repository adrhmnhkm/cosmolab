"""
cosmolab.team
~~~~~~~~~~~~~
One account per team member, for the dashboard in team mode.

Accounts live in shared/team_users.json on the server (outside git). A
password is stored as a scrypt hash with its own salt, never as text. Two
roles: "admin" sees everything, including the owner section and every
project; "konsultan" does daily work in the projects they are a member of.

Project membership is the "members" list in the project's project.json.
The main data folder (no project) is for admins only.

Until the first account is made, the shared team password still works
(see web._require_team_login).
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import re
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config

ADMIN = "admin"
CONSULTANT = "konsultan"
ROLES = {ADMIN: "Admin", CONSULTANT: "Konsultan"}
MIN_PASSWORD = 10

USERS_FILE = None  # None = shared/team_users.json; tests point this elsewhere
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,31}$")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}

# The account using the current dashboard run. Set by web.py after login, read by audit.log.
_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("cosmolab_team_user", default=None)


def users_file() -> Path:
    return USERS_FILE or (config.PROJECT_ROOT / "shared" / "team_users.json")


def _load() -> dict:
    try:
        data = json.loads(users_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(users: dict) -> None:
    path = users_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT).hex()


def _set_password(record: dict, password: str, must_change: bool) -> None:
    salt = secrets.token_bytes(16)
    record.update({"salt": salt.hex(), "hash": _hash(password, salt), "must_change": must_change})


def _public(username: str, record: dict) -> dict:
    return {"username": username, "role": record.get("role", CONSULTANT), "name": record.get("name") or username,
            "must_change": bool(record.get("must_change")), "created": record.get("created", "")}


def validate_username(username: str) -> str:
    username = (username or "").strip().lower()
    if not _USERNAME_RE.match(username):
        raise ValueError("Nama pengguna 2-32 karakter: huruf kecil, angka, titik, garis bawah, atau tanda hubung.")
    return username


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def has_users() -> bool:
    return bool(_load())


def list_users() -> list[dict]:
    return [_public(u, r) for u, r in sorted(_load().items())]


def get_user(username: str) -> dict | None:
    record = _load().get((username or "").strip().lower())
    return _public(username.strip().lower(), record) if record else None


def add_user(username: str, role: str = CONSULTANT, name: str = "") -> str:
    """Create an account and return its temporary password (shown once; must be changed at first login)."""
    username = validate_username(username)
    if role not in ROLES:
        raise ValueError(f"Peran harus salah satu dari: {', '.join(ROLES)}.")
    users = _load()
    if username in users:
        raise ValueError(f"Akun '{username}' sudah ada.")
    password = secrets.token_urlsafe(9)
    record = {"role": role, "name": name.strip(), "created": datetime.now().isoformat(timespec="seconds")}
    _set_password(record, password, must_change=True)
    users[username] = record
    _save(users)
    return password


def reset_password(username: str) -> str:
    """New temporary password for an account."""
    username = validate_username(username)
    users = _load()
    if username not in users:
        raise ValueError(f"Akun '{username}' tidak ada.")
    password = secrets.token_urlsafe(9)
    _set_password(users[username], password, must_change=True)
    _save(users)
    return password


def remove_user(username: str) -> None:
    """Delete an account and take it out of every project's member list."""
    username = validate_username(username)
    users = _load()
    if username not in users:
        raise ValueError(f"Akun '{username}' tidak ada.")
    admins = [u for u, r in users.items() if r.get("role") == ADMIN]
    if admins == [username] and len(users) > 1:
        raise ValueError("Ini satu-satunya admin. Buat admin lain dulu sebelum menghapusnya.")
    del users[username]
    _save(users)
    for project in config.list_projects():
        if username in members(project["name"]):
            remove_member(project["name"], username)


def verify(username: str, password: str) -> dict | None:
    """The account when the password is right, else None. Takes the same time for a missing account."""
    record = _load().get((username or "").strip().lower())
    salt = bytes.fromhex(record["salt"]) if record else b"\x00" * 16
    expected = record["hash"] if record else "0" * 64
    ok = hmac.compare_digest(_hash(password or "", salt), expected)
    return _public(username.strip().lower(), record) if (record and ok) else None


def change_password(username: str, new_password: str) -> None:
    username = validate_username(username)
    if len(new_password or "") < MIN_PASSWORD:
        raise ValueError(f"Password minimal {MIN_PASSWORD} karakter.")
    users = _load()
    if username not in users:
        raise ValueError(f"Akun '{username}' tidak ada.")
    old = users[username]
    if hmac.compare_digest(_hash(new_password, bytes.fromhex(old["salt"])), old["hash"]):
        raise ValueError("Password baru harus berbeda dari password sementara.")
    _set_password(old, new_password, must_change=False)
    _save(users)


# ---------------------------------------------------------------------------
# Owner: the one admin who may create, reset, or delete other admins
# ---------------------------------------------------------------------------

def owner_username() -> str:
    """The owner: the admin marked "owner", else the earliest admin account. '' when there is no admin."""
    users = _load()
    marked = [u for u, r in users.items() if r.get("owner") and r.get("role") == ADMIN]
    if marked:
        return sorted(marked)[0]
    admins = sorted((r.get("created", ""), u) for u, r in users.items() if r.get("role") == ADMIN)
    return admins[0][1] if admins else ""


def is_owner(user: dict | None) -> bool:
    return bool(user) and user.get("role") == ADMIN and user.get("username") == owner_username()


def set_owner(username: str) -> None:
    """Hand ownership to another admin (from the server's command line)."""
    username = validate_username(username)
    users = _load()
    if users.get(username, {}).get("role") != ADMIN:
        raise ValueError(f"'{username}' bukan akun admin.")
    for u, r in users.items():
        r.pop("owner", None)
        if u == username:
            r["owner"] = True
    _save(users)


def can_manage(actor: dict | None, target_role: str) -> bool:
    """May `actor` create, reset, or delete an account with `target_role` from the dashboard?

    The owner manages everyone. Other admins manage consultants only, so an admin cannot make
    new admins or take over the owner's account by resetting its password.
    """
    if is_owner(actor):
        return True
    return bool(actor) and actor.get("role") == ADMIN and target_role == CONSULTANT


# ---------------------------------------------------------------------------
# Project access
# ---------------------------------------------------------------------------

def _meta_path(project: str) -> Path:
    return config.project_dir(project) / config.PROJECT_META_FILE


def _read_meta(project: str) -> dict:
    path = _meta_path(project)
    if not path.exists():
        raise ValueError(f"Proyek '{project}' tidak ada.")
    return json.loads(path.read_text(encoding="utf-8"))


def members(project: str) -> list[str]:
    try:
        return [str(m) for m in _read_meta(project).get("members") or []]
    except (ValueError, OSError):
        return []


def add_member(project: str, username: str) -> None:
    username = validate_username(username)
    if username not in _load():
        raise ValueError(f"Akun '{username}' tidak ada.")
    meta = _read_meta(project)
    meta["members"] = sorted(set(meta.get("members") or []) | {username})
    _meta_path(project).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_member(project: str, username: str) -> None:
    username = validate_username(username)
    meta = _read_meta(project)
    meta["members"] = [m for m in meta.get("members") or [] if m != username]
    _meta_path(project).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def projects_of(username: str) -> list[str]:
    return [p["name"] for p in config.list_projects() if username in (p.get("members") or [])]


def can_access(user: dict | None, project: str | None) -> bool:
    """Admins open everything. A consultant opens only projects they are a member of, never the main data."""
    if not user:
        return False
    if user.get("role") == ADMIN:
        return True
    return bool(project) and user.get("username") in members(project)


# ---------------------------------------------------------------------------
# Lobby tickets: open a project's dashboard without logging in again
# ---------------------------------------------------------------------------

TICKET_TTL = 600  # seconds a link from the lobby stays valid; each link works once


def _secret() -> bytes:
    """Key that signs lobby tickets. Made once, kept next to the accounts file (outside git)."""
    path = users_file().parent / "lobby_secret"
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        path.write_text(key.hex(), encoding="utf-8")
        return key


def _sign(body: str) -> str:
    return hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()


def make_ticket(username: str, project: str | None) -> str:
    """One-time link token for `username` to enter `project` ('' = shared team password)."""
    import base64
    payload = {"u": username or "", "p": project or "", "exp": int(time.time()) + TICKET_TTL,
               "n": secrets.token_hex(8)}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{_sign(body)}"


def _used_path() -> Path:
    return users_file().parent / "tickets_used.json"


def _spend(nonce: str, exp: int) -> bool:
    """Record a ticket as used. False when it was used before."""
    path = _used_path()
    try:
        used = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        used = {}
    now = time.time()
    used = {n: e for n, e in used.items() if e > now}
    if nonce in used:
        return False
    used[nonce] = exp
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(used), encoding="utf-8")
    tmp.replace(path)
    return True


def redeem_ticket(token: str, project: str | None) -> dict | None:
    """The payload {"u": username, "p": project} when the ticket is genuine, unexpired, unused and for this project."""
    import base64
    try:
        body, sig = (token or "").split(".", 1)
        if not hmac.compare_digest(_sign(body), sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, TypeError):
        return None
    if payload.get("p", "") != (project or "") or int(payload.get("exp", 0)) < time.time():
        return None
    if not _spend(str(payload.get("n", "")), int(payload["exp"])):
        return None
    return payload


# ---------------------------------------------------------------------------
# Who is using the dashboard right now
# ---------------------------------------------------------------------------

def set_current(user: dict | None) -> None:
    _current.set(user)


def current() -> dict | None:
    user = _current.get()
    if user is None and "streamlit" in sys.modules:
        # A fragment rerun does not pass through web.py, so read the login from the session.
        try:
            import streamlit as st
            from streamlit.runtime.scriptrunner import get_script_run_ctx

            if get_script_run_ctx() is not None:
                user = st.session_state.get("team_user")
        except Exception:
            user = None
    return user


def current_username() -> str:
    user = current()
    return user["username"] if user else ""


def current_name() -> str:
    user = current()
    return (user.get("name") or user["username"]) if user else ""


def is_admin() -> bool:
    user = current()
    return bool(user) and user.get("role") == ADMIN
