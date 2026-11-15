"""Login for the dashboard in team mode (`cosmolab ui --team`).

With accounts in shared/team_users.json, each person logs in with their own
user name and password, and may open only the projects they are a member of.
Until the first account is made, the shared team password still works.
"""

import hmac
import os
import time

import streamlit as st

from cosmolab import audit, config
from cosmolab import team as _team
from cosmolab.ui.components import LOGO_LIGHT_PNG

MAX_FAST_TRIES = 5


def _logo(title: str):
    if LOGO_LIGHT_PNG.exists():
        st.image(str(LOGO_LIGHT_PNG), width=300)
    st.markdown(f"### {title}")


def _slow_down() -> int:
    tries = st.session_state.get("team_auth_tries", 0)
    if tries >= MAX_FAST_TRIES:
        time.sleep(min(30, 2 ** (tries - MAX_FAST_TRIES + 1)))  # slow down repeated guesses
    return tries


def _from_ticket() -> dict | None:
    """A one-time ticket from the lobby link (?tiket=...), for this dashboard's project. Removed from the URL."""
    token = st.query_params.get("tiket")
    if not token:
        return None
    del st.query_params["tiket"]
    return _team.redeem_ticket(token, config.PROJECT)


def logout():
    for key in ("team_user", "team_auth_ok", "team_auth_tries"):
        st.session_state.pop(key, None)
    _team.set_current(None)


def _shared_login():
    """One password for the whole team: used only while no account exists."""
    _team.set_current(None)
    if st.session_state.get("team_auth_ok"):
        return
    ticket = _from_ticket()
    if ticket and not ticket["u"]:
        st.session_state["team_auth_ok"] = True
        return
    _logo("Masuk tim")
    if not config.TEAM_PASSWORD:
        st.error("Belum ada akun tim dan password tim belum diatur di server. Hubungi admin.")
        st.stop()
    with st.form("team_login"):
        pw = st.text_input("Password tim", type="password")
        submitted = st.form_submit_button("Masuk")
    if submitted:
        tries = _slow_down()
        if hmac.compare_digest(pw.encode("utf-8"), config.TEAM_PASSWORD.encode("utf-8")):
            st.session_state["team_auth_ok"] = True
            st.rerun()
        st.session_state["team_auth_tries"] = tries + 1
        st.error("Password salah.")
    st.stop()


def _change_password(user: dict):
    _logo("Ganti password")
    st.caption(f"Akun **{user['username']}** masih memakai password sementara. Buat password sendiri "
               f"(minimal {_team.MIN_PASSWORD} karakter) sebelum mulai bekerja.")
    with st.form("team_change_password"):
        new = st.text_input("Password baru", type="password")
        again = st.text_input("Ulangi password baru", type="password")
        submitted = st.form_submit_button("Simpan", type="primary")
    if submitted:
        if new != again:
            st.error("Kedua password tidak sama.")
        else:
            try:
                _team.change_password(user["username"], new)
            except ValueError as e:
                st.error(str(e))
            else:
                st.session_state["team_user"] = _team.get_user(user["username"])
                st.rerun()
    if st.button("Keluar", key="team_change_logout"):
        logout()
        st.rerun()
    st.stop()


def _account_login(lobby: bool = False):
    # The lobby only needs a valid account; it lists the projects each person may open.
    def allowed(u):
        return bool(u) and (lobby or _team.can_access(u, config.PROJECT))

    user = st.session_state.get("team_user")
    if not user:
        ticket = _from_ticket()
        found = _team.get_user(ticket["u"]) if ticket and ticket["u"] else None
        if allowed(found):
            user = st.session_state["team_user"] = found
            _team.set_current(found)
            audit.log("masuk", via="lobi")
    if user:
        # Read the account again on every run: a removed account or a revoked project loses access at the next click.
        fresh = _team.get_user(user["username"])
        if allowed(fresh):
            st.session_state["team_user"] = fresh
            if fresh["must_change"]:
                _change_password(fresh)
            _team.set_current(fresh)
            return
        logout()

    _logo("Masuk")
    st.caption("Lobi proyek CosmoLab" if lobby else f"Proyek: {config.PROJECT or 'data utama (khusus admin)'}")
    with st.form("team_login"):
        username = st.text_input("Nama pengguna")
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Masuk", type="primary")
    if submitted:
        tries = _slow_down()
        found = _team.verify(username, pw)
        if allowed(found):
            st.session_state["team_user"] = found
            st.session_state.pop("team_auth_tries", None)
            _team.set_current(found)
            audit.log("masuk")
            st.rerun()
        st.session_state["team_auth_tries"] = tries + 1
        # One message for every failure, so a guess does not reveal which accounts exist.
        st.error("Nama pengguna atau password salah, atau akun ini tidak punya akses ke proyek ini.")
    st.stop()


def require_login(lobby: bool = False):
    """Stop the page until the visitor is logged in. Does nothing outside team mode.

    lobby=True: any valid account may enter (the lobby itself shows only their projects).
    """
    if os.environ.get("COSMOLAB_TEAM_MODE") != "1":
        _team.set_current(None)
        return
    if _team.has_users():
        _account_login(lobby)
    else:
        _shared_login()
