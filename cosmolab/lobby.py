"""Team lobby (`cosmolab tim`): log in once, pick or create a project, open its dashboard.

Each project's dashboard runs in its own process (see servers.py). The lobby
starts it when someone opens the project and hands over the login with a
one-time ticket, so nobody types a project name or a port.
"""

import os
import re
import threading
import time
from datetime import datetime

import streamlit as st

from cosmolab import config, servers
from cosmolab import team as _team
from cosmolab.ui import login as _login
from cosmolab.ui.components import ASSETS_DIR, LOGO_LIGHT_PNG, LOGO_MARK_PNG

st.set_page_config(
    page_title="CosmoLab • Lobi Tim",
    page_icon=str(LOGO_MARK_PNG) if LOGO_MARK_PNG.exists() else ":material/menu_book:",
    layout="centered",
)
st.markdown("\n<style>\n" + (ASSETS_DIR / "theme.css").read_text(encoding="utf-8") + "</style>\n",
            unsafe_allow_html=True)

_login.require_login(lobby=True)


@st.cache_resource
def _reaper():
    """Stop dashboards nobody has used for a while, once every few minutes."""
    def loop():
        while True:
            time.sleep(300)
            try:
                servers.stop_idle()
            except Exception:
                pass

    thread = threading.Thread(target=loop, daemon=True, name="lobi-penutup")
    thread.start()
    return thread


_reaper()

BIND_HOST = os.environ.get("COSMOLAB_SERVER_HOST", "127.0.0.1")
user = _team.current()
accounts = _team.has_users()
# An admin account manages accounts and members. With the shared team password (no accounts yet)
# everyone who got in may already open every project, so they may also create one, but never accounts:
# otherwise anyone who knows the shared password could make themselves admin.
account_admin = bool(user and user.get("role") == _team.ADMIN)
is_admin = (not accounts) or account_admin


def _browser_host() -> str:
    """The host name the visitor typed, so links work by IP or by Tailscale name."""
    try:
        host = st.context.headers.get("Host") or ""
    except Exception:
        host = ""
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return host or BIND_HOST


def _slug(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")[:50]


def _paper_count(project: str | None) -> int:
    root = config.project_dir(project) if project else config._default_root()
    try:
        return sum(1 for _ in (root / "pdf").glob("*.pdf"))
    except OSError:
        return 0


def _flash(kind: str, text: str, secret: str = ""):
    st.session_state["lobi_flash"] = (kind, text, secret)


def _show_flash():
    kind, text, secret = st.session_state.pop("lobi_flash", (None, "", ""))
    if kind:
        getattr(st, kind)(text)
        if secret:
            st.code(secret, language=None)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

if LOGO_LIGHT_PNG.exists():
    st.image(str(LOGO_LIGHT_PNG), width=220)
head, out = st.columns([4, 1], vertical_alignment="center")
with head:
    st.markdown("### Pilih proyek")
    if user:
        st.caption(f"Masuk sebagai **{user['name']}** ({_team.ROLES.get(user['role'], user['role'])})")
with out:
    if st.button("Keluar", icon=":material/logout:", use_container_width=True):
        _login.logout()
        st.rerun()

_show_flash()


# ---------------------------------------------------------------------------
# Projects this person may open
# ---------------------------------------------------------------------------

def _visible_projects() -> list[dict]:
    projects = config.list_projects()
    if user and user.get("role") != _team.ADMIN:
        projects = [p for p in projects if user["username"] in (p.get("members") or [])]
    if is_admin:
        projects = projects + [{"name": "", "client": "Data utama", "description": "Bukan proyek klien"}]
    return projects


def _open_link(project: str, port: int) -> str:
    ticket = _team.make_ticket(user["username"] if user else "", project)
    return f"http://{_browser_host()}:{port}/?tiket={ticket}"


def _project_list():
    projects = _visible_projects()
    if not projects:
        st.info("Belum ada proyek untuk akun ini. Minta admin menambahkan Anda ke proyek.")
        return
    query = st.text_input("Cari proyek", placeholder="Nama proyek atau klien", label_visibility="collapsed") \
        if len(projects) > 6 else ""
    running = servers.running()
    for p in projects:
        name = p["name"]
        text = f"{name} {p.get('client', '')} {p.get('description', '')}".lower()
        if query and query.lower() not in text:
            continue
        key = servers.key_of(name)
        with st.container(border=True):
            info, action = st.columns([3, 1], vertical_alignment="center")
            with info:
                st.markdown(f"**{p.get('client') or name}**")
                details = [name] if name else []
                if p.get("description"):
                    details.append(p["description"])
                details.append(f"{_paper_count(name or None)} paper")
                if key in running:
                    details.append("sedang terbuka")
                st.caption(" · ".join(details))
            with action:
                if key in running:
                    st.link_button("Masuk", _open_link(name, int(running[key]["port"])), type="primary",
                                   icon=":material/arrow_forward:", use_container_width=True)
                elif st.button("Buka", key=f"buka_{key}", use_container_width=True):
                    with st.spinner("Menyiapkan proyek, biasanya 10-20 detik..."):
                        try:
                            servers.ensure(name or None, BIND_HOST)
                        except servers.LobbyFull as e:
                            _flash("warning", str(e))
                        except Exception as e:
                            _flash("error", f"Proyek gagal dibuka: {e}")
                        else:
                            _flash("success", f"Proyek **{p.get('client') or name}** siap. Klik **Masuk**.")
                    st.rerun()


# ---------------------------------------------------------------------------
# Admin: new project, members, accounts, open dashboards
# ---------------------------------------------------------------------------

def _new_project():
    consultants = [u for u in _team.list_users() if u["role"] != _team.ADMIN]
    with st.form("lobi_proyek_baru", clear_on_submit=True):
        client = st.text_input("Nama klien", placeholder="Contoh: Universitas X - Budi Santoso")
        description = st.text_input("Keterangan (opsional)", placeholder="Contoh: tesis manajemen keuangan")
        folder = st.text_input("Nama folder (opsional)",
                               help="Kosongkan untuk dibuat otomatis, misalnya 2026-11-universitas-x-budi-santoso.")
        members = st.multiselect("Anggota tim", [u["username"] for u in consultants],
                                 format_func=lambda n: next((u["name"] for u in consultants if u["username"] == n), n)) \
            if consultants else []
        submitted = st.form_submit_button("Buat proyek", type="primary")
    if not submitted:
        return
    if not client.strip() and not folder.strip():
        st.error("Isi nama klien dulu.")
        return
    name = folder.strip() or f"{datetime.now():%Y-%m}-{_slug(client)}"
    try:
        path = config.create_project(name, client=client.strip(), description=description.strip())
        for m in members:
            _team.add_member(path.name, m)
    except (ValueError, FileExistsError) as e:
        st.error(str(e))
        return
    _flash("success", f"Proyek **{path.name}** dibuat. Buka dari tab Proyek.")
    st.rerun()


def _members():
    projects = config.list_projects()
    consultants = [u for u in _team.list_users() if u["role"] != _team.ADMIN]
    if not projects or not consultants:
        st.info("Belum ada proyek atau akun konsultan. Admin selalu bisa membuka semua proyek.")
        return
    labels = {p["name"]: f"{p.get('client') or p['name']} ({p['name']})" for p in projects}
    project = st.selectbox("Proyek", list(labels), format_func=labels.get)
    current = _team.members(project)
    names = {u["username"]: u["name"] for u in consultants}
    chosen = st.multiselect("Anggota", list(names), default=[m for m in current if m in names],
                            format_func=lambda n: names.get(n, n), key=f"anggota_{project}")
    if st.button("Simpan anggota", type="primary"):
        for m in set(chosen) - set(current):
            _team.add_member(project, m)
        for m in set(current) - set(chosen):
            _team.remove_member(project, m)
        _flash("success", f"Anggota **{project}** disimpan. Akses yang dicabut berlaku di klik berikutnya.")
        st.rerun()


def _accounts():
    if not account_admin:  # second guard: only an admin account reaches this tab
        return
    owner = _team.owner_username()
    users = _team.list_users()

    def role_label(u):
        return "Pemilik (admin)" if u["username"] == owner else _team.ROLES.get(u["role"], u["role"])

    if users:
        st.dataframe(
            [{"Nama pengguna": u["username"], "Nama": u["name"], "Peran": role_label(u),
              "Proyek": "semua" if u["role"] == _team.ADMIN else ", ".join(_team.projects_of(u["username"])) or "-",
              "Password": "sementara" if u["must_change"] else "sudah diganti"} for u in users],
            hide_index=True, use_container_width=True)

    st.markdown("**Akun baru**")
    roles = [r for r in _team.ROLES if _team.can_manage(user, r)]
    with st.form("lobi_akun_baru", clear_on_submit=True):
        c1, c2 = st.columns(2)
        username = c1.text_input("Nama pengguna", placeholder="rina")
        name = c2.text_input("Nama lengkap", placeholder="Rina Wulandari")
        if len(roles) > 1:
            role = st.radio("Peran", roles, format_func=_team.ROLES.get, horizontal=True,
                            index=roles.index(_team.CONSULTANT),
                            help="Admin bisa membuka semua proyek dan mengelola akun konsultan.")
        else:
            role = _team.CONSULTANT
            st.caption("Akun baru berperan Konsultan. Hanya pemilik yang bisa membuat akun admin.")
        submitted = st.form_submit_button("Buat akun", type="primary")
    if submitted:
        try:
            if not _team.can_manage(user, role):
                raise ValueError("Hanya pemilik yang bisa membuat akun admin.")
            temp = _team.add_user(username, role=role, name=name)
        except ValueError as e:
            st.error(str(e))
        else:
            _flash("success", f"Akun **{username.strip().lower()}** dibuat. Password sementara (hanya tampil sekali, "
                              "berikan langsung ke orangnya):", temp)
            st.rerun()

    # Your own account is left out so nobody deletes or resets themselves; on the server use `cosmolab team reset`.
    manageable = [u for u in users if u["username"] != user["username"] and _team.can_manage(user, u["role"])]
    if not manageable:
        return
    st.markdown("**Ubah akun**")
    names = {u["username"]: u for u in manageable}
    who = st.selectbox("Akun", list(names), format_func=lambda n: f"{n} ({names[n]['name']}, {role_label(names[n])})")
    c1, c2 = st.columns(2)
    if c1.button("Buat password sementara baru", use_container_width=True):
        if _team.can_manage(user, _team.get_user(who)["role"]):
            _flash("success", f"Password sementara baru untuk **{who}** (hanya tampil sekali):",
                   _team.reset_password(who))
        st.rerun()
    sure = st.checkbox(f"Ya, hapus akun {who}", key=f"hapus_{who}")
    if c2.button("Hapus akun", disabled=not sure, use_container_width=True):
        try:
            if not _team.can_manage(user, _team.get_user(who)["role"]):
                raise ValueError("Hanya pemilik yang bisa menghapus akun admin.")
            _team.remove_user(who)
        except ValueError as e:
            st.error(str(e))
        else:
            _flash("success", f"Akun **{who}** dihapus.")
            st.rerun()


def _open_dashboards():
    running = servers.running()
    st.caption(f"Paling banyak {servers.MAX_RUNNING} proyek terbuka bersamaan. Proyek yang "
               f"{servers.IDLE_HOURS:g} jam tidak dipakai ditutup otomatis.")
    if not running:
        st.info("Tidak ada proyek yang sedang terbuka.")
        return
    for key, entry in running.items():
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        idle = int(servers.idle_seconds(key, entry) // 60)
        c1.markdown(f"**{entry.get('project') or 'Data utama'}** · port {entry['port']} · "
                    f"terakhir dipakai {idle} menit lalu")
        if c2.button("Tutup", key=f"tutup_{key}", use_container_width=True):
            servers.stop(key)
            st.rerun()


if account_admin:
    tabs = st.tabs(["Proyek", "Proyek baru", "Anggota", "Akun", "Sedang terbuka"])
    with tabs[0]:
        _project_list()
    with tabs[1]:
        _new_project()
    with tabs[2]:
        _members()
    with tabs[3]:
        _accounts()
    with tabs[4]:
        _open_dashboards()
elif is_admin:
    # Shared team password: no accounts tab. The first admin account is made on the server itself.
    st.caption("Tim masih memakai password bersama. Admin membuat akun pertama di komputer server: "
               "`cosmolab team add <nama> --role admin`.")
    tabs = st.tabs(["Proyek", "Proyek baru", "Sedang terbuka"])
    with tabs[0]:
        _project_list()
    with tabs[1]:
        _new_project()
    with tabs[2]:
        _open_dashboards()
else:
    _project_list()
