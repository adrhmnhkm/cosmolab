"""Dashboard page: Kelola Tim & Proyek.

Enables administrators to manage team accounts, reset passwords, assign
consultants to client projects, create new projects, and monitor team activities
all from the web interface without touching the command line.
"""

from datetime import datetime
import os
import re
import streamlit as st

from cosmolab import config, servers
from cosmolab import team as _team
from cosmolab.ui.components import render_hero
from cosmolab.ui.context import AppContext


def _slug(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")[:50]


def _paper_count(project: str | None) -> int:
    root = config.project_dir(project) if project else config._default_root()
    try:
        return sum(1 for _ in (root / "pdf").glob("*.pdf"))
    except OSError:
        return 0


def _flash(kind: str, text: str, secret: str = ""):
    st.session_state["team_admin_flash"] = (kind, text, secret)


def _show_flash():
    kind, text, secret = st.session_state.pop("team_admin_flash", (None, "", ""))
    if kind:
        getattr(st, kind)(text)
        if secret:
            st.code(secret, language=None)


def render(ctx: AppContext):
    """Render the Team & Project Management admin page."""
    render_hero(
        title="Kelola Tim & Proyek",
        subtitle="Kelola akun konsultan, hak akses anggota proyek klien, dan buat proyek baru langsung dari antarmuka web.",
        icon="",
    )
    _show_flash()

    user = _team.current()
    owner = _team.owner_username()
    has_acc = _team.has_users()

    tab_proj_member, tab_new_proj, tab_accounts, tab_server = st.tabs([
        "Anggota Proyek Ini",
        "Kelola Semua Proyek",
        "Akun Pengguna Tim",
        "Server & Lobi Tim",
    ])

    # -----------------------------------------------------------------------
    # Tab 1: Current Project Members
    # -----------------------------------------------------------------------
    with tab_proj_member:
        active_proj = config.PROJECT
        if not active_proj:
            st.info("Saat ini Anda sedang membuka **Data Utama** (bukan proyek klien). "
                    "Data utama dikhususkan untuk riset induk/internal. Anggota tim konsultan hanya "
                    "diberikan akses ke proyek klien tertentu.")
            st.caption("Pilih atau buat proyek klien di tab **Kelola Semua Proyek** untuk mengatur anggotanya.")
        else:
            p_info = config.project_info(active_proj)
            c_client = p_info.get("client") or "-"
            c_desc = p_info.get("description") or "-"

            with st.container(border=True):
                st.markdown(f"#### Proyek Aktif: **{active_proj}**")
                st.caption(f"Klien: **{c_client}** · Keterangan: {c_desc} · Koleksi: {_paper_count(active_proj)} paper")

            consultants = [u for u in _team.list_users() if u["role"] != _team.ADMIN]
            if not consultants:
                st.warning("Belum ada akun konsultan yang terdaftar di sistem. Buat akun konsultan baru di tab **Akun Pengguna Tim**.")
            else:
                current_members = _team.members(active_proj)
                c_names = {u["username"]: u["name"] for u in consultants}
                st.markdown("##### Anggota Konsultan Proyek Ini")
                st.caption("Konsultan yang dipilih dapat membuka, mengunggah paper, dan mereview draf pada proyek ini.")

                chosen = st.multiselect(
                    "Pilih anggota konsultan",
                    options=list(c_names.keys()),
                    default=[m for m in current_members if m in c_names],
                    format_func=lambda u: f"{c_names.get(u, u)} (@{u})",
                    key=f"team_proj_members_{active_proj}",
                )

                if st.button("Simpan Anggota Proyek", type="primary", key="btn_save_proj_members"):
                    for m in set(chosen) - set(current_members):
                        _team.add_member(active_proj, m)
                    for m in set(current_members) - set(chosen):
                        _team.remove_member(active_proj, m)
                    _flash("success", f"Daftar anggota proyek **{active_proj}** berhasil diperbarui.")
                    st.rerun()

    # -----------------------------------------------------------------------
    # Tab 2: All Projects & Create New Project
    # -----------------------------------------------------------------------
    with tab_new_proj:
        st.markdown("##### Buat Proyek Klien Baru")
        st.caption("Setiap klien memiliki ruang kerja, database SQLite, dan folder koleksi paper yang terisolasi.")

        consultants = [u for u in _team.list_users() if u["role"] != _team.ADMIN]
        with st.form("admin_buat_proyek_baru", clear_on_submit=True):
            col_c, col_f = st.columns(2)
            new_client = col_c.text_input("Nama klien", placeholder="Contoh: Universitas X - Budi Santoso")
            new_folder = col_f.text_input("Nama folder (opsional)",
                                          help="Kosongkan untuk dibuat otomatis dari nama klien (contoh: 2026-11-universitas-x-budi).")
            new_desc = st.text_input("Keterangan proyek (opsional)", placeholder="Contoh: Tesis Magister Manajemen Keuangan")

            new_members = st.multiselect(
                "Tugaskan ke konsultan",
                options=[u["username"] for u in consultants],
                format_func=lambda u: next((f"{x['name']} (@{u})" for x in consultants if x["username"] == u), u),
            ) if consultants else []

            submitted_proj = st.form_submit_button("Buat Proyek", type="primary")

        if submitted_proj:
            if not new_client.strip() and not new_folder.strip():
                st.error("Nama klien atau nama folder harus diisi.")
            else:
                proj_name = new_folder.strip() or f"{datetime.now():%Y-%m}-{_slug(new_client)}"
                try:
                    p_path = config.create_project(proj_name, client=new_client.strip(), description=new_desc.strip())
                    for m in new_members:
                        _team.add_member(p_path.name, m)
                except (ValueError, FileExistsError) as e:
                    st.error(str(e))
                else:
                    _flash("success", f"Proyek **{p_path.name}** berhasil dibuat dan siap digunakan.")
                    st.rerun()

        st.divider()
        st.markdown("##### Daftar Semua Proyek")
        all_projects = config.list_projects()
        if not all_projects:
            st.info("Belum ada proyek klien yang dibuat.")
        else:
            if config.PROJECT:
                if st.button("🏛️ Beralih ke Data Utama (Koleksi Induk)", key="btn_switch_main"):
                    st.session_state["active_project"] = None
                    st.session_state["active_project_switcher"] = ""
                    config.use_project(None)
                    st.session_state.pop("_sinta_ranks", None)
                    st.session_state.pop("_meta_store", None)
                    st.session_state.pop("review_current", None)
                    st.session_state["active_nav_menu"] = "Beranda"
                    _flash("success", "Beralih ke Data Utama.")
                    st.rerun()

            for p in all_projects:
                with st.container(border=True):
                    c_inf, c_btn = st.columns([3, 1], vertical_alignment="center")
                    with c_inf:
                        is_active = (config.PROJECT == p["name"])
                        badge = " 🟢 **(Sedang Dibuka)**" if is_active else ""
                        st.markdown(f"**{p.get('client') or p['name']}** ({p['name']}){badge}")
                        desc_text = f" · {p['description']}" if p.get("description") else ""
                        members_txt = ", ".join(_team.members(p["name"])) or "Semua admin"
                        st.caption(f"{_paper_count(p['name'])} paper{desc_text} · Anggota: {members_txt}")
                    with c_btn:
                        if is_active:
                            st.button("Sedang Aktif", key=f"active_{p['name']}", disabled=True, use_container_width=True)
                        elif st.button("Buka Proyek Ini", key=f"open_{p['name']}", type="primary", use_container_width=True):
                            st.session_state["active_project"] = p["name"]
                            st.session_state["active_project_switcher"] = p["name"]
                            config.use_project(p["name"])
                            st.session_state.pop("_sinta_ranks", None)
                            st.session_state.pop("_meta_store", None)
                            st.session_state.pop("review_current", None)
                            st.session_state["active_nav_menu"] = "Beranda"
                            _flash("success", f"Beralih ke proyek **{p.get('client') or p['name']}**.")
                            st.rerun()

    # -----------------------------------------------------------------------
    # Tab 3: Team User Accounts
    # -----------------------------------------------------------------------
    with tab_accounts:
        users = _team.list_users()

        def role_label(u):
            if u["username"] == owner:
                return "Pemilik (admin)"
            return _team.ROLES.get(u["role"], u["role"])

        if users:
            st.markdown("##### Daftar Akun Pengguna")
            st.dataframe(
                [{"Nama Pengguna": u["username"], "Nama Lengkap": u["name"], "Peran": role_label(u),
                  "Akses Proyek": "Semua proyek" if u["role"] == _team.ADMIN else ", ".join(_team.projects_of(u["username"])) or "(Belum ada)",
                  "Status Password": "Password Sementara" if u["must_change"] else "Aktif"} for u in users],
                hide_index=True, use_container_width=True)
        else:
            st.warning("Belum ada akun tim tersimpan di sistem (`shared/team_users.json`). Saat ini sistem masih menggunakan password bersama dari `.env`.")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            st.markdown("##### Tambah Akun Baru")
            roles = [r for r in _team.ROLES if (not user) or _team.can_manage(user, r)]
            if not roles:
                roles = [_team.CONSULTANT]

            with st.form("admin_buat_akun_baru", clear_on_submit=True):
                new_u = st.text_input("Nama pengguna", placeholder="contoh: rina")
                new_n = st.text_input("Nama lengkap", placeholder="contoh: Rina Wulandari")
                if len(roles) > 1:
                    new_r = st.radio("Peran", roles, format_func=_team.ROLES.get, horizontal=True,
                                     index=roles.index(_team.CONSULTANT) if _team.CONSULTANT in roles else 0)
                else:
                    new_r = _team.CONSULTANT
                    st.caption("Peran: **Konsultan**.")

                submitted_acc = st.form_submit_button("Buat Akun", type="primary")

            if submitted_acc:
                try:
                    temp_pw = _team.add_user(new_u, role=new_r, name=new_n)
                except ValueError as err:
                    st.error(str(err))
                else:
                    _flash("success", f"Akun **{new_u.strip().lower()}** berhasil dibuat. "
                                      "Password sementara (hanya tampil sekali, berikan ke yang bersangkutan):", temp_pw)
                    st.rerun()

        with col_a2:
            manageable = [u for u in users if (not user) or (u["username"] != user.get("username") and _team.can_manage(user, u["role"]))]
            if manageable:
                st.markdown("##### Kelola & Reset Password")
                names_map = {u["username"]: u for u in manageable}
                picked_u = st.selectbox(
                    "Pilih akun",
                    list(names_map.keys()),
                    format_func=lambda n: f"{names_map[n]['name']} (@{n}) - {role_label(names_map[n])}",
                    key="sel_manage_user",
                )

                if st.button("Buat Password Sementara Baru", key="btn_reset_pw", use_container_width=True):
                    new_pw = _team.reset_password(picked_u)
                    _flash("success", f"Password sementara baru untuk **{picked_u}** (hanya tampil sekali):", new_pw)
                    st.rerun()

                st.write("")
                confirm_del = st.checkbox(f"Konfirmasi ingin menghapus akun @{picked_u}", key=f"chk_del_{picked_u}")
                if st.button("Hapus Akun", disabled=not confirm_del, key=f"btn_del_{picked_u}", use_container_width=True):
                    try:
                        _team.remove_user(picked_u)
                    except ValueError as err:
                        st.error(str(err))
                    else:
                        _flash("success", f"Akun @{picked_u} berhasil dihapus.")
                        st.rerun()

    # -----------------------------------------------------------------------
    # Tab 4: Server & Lobby Status
    # -----------------------------------------------------------------------
    with tab_server:
        st.markdown("##### Status Lobi Tim & Server")
        lobby_port = os.environ.get("COSMOLAB_LOBBY_PORT", "8501")
        host = os.environ.get("COSMOLAB_SERVER_HOST", "127.0.0.1")
        is_team_mode = os.environ.get("COSMOLAB_TEAM_MODE") == "1"

        if is_team_mode:
            st.success(f"Mode Tim Aktif. Server Lobi berjalan di: `http://{host}:{lobby_port}`")
            st.link_button("Buka Lobi Tim", f"http://{host}:{lobby_port}", icon=":material/meeting_room:", type="primary")
        else:
            st.info("Dashboard ini sedang dijalankan dalam **Mode Mandiri/Lokal**. "
                    "Untuk membuka lobi terpusat bagi seluruh anggota tim lewat Tailscale, jalankan **Jalankan Server Tim.bat** di komputer server.")

        st.markdown("##### Proyek yang Sedang Menyala di Server")
        running_srvs = servers.running()
        if not running_srvs:
            st.caption("Tidak ada proyek latar belakang lain yang sedang berjalan.")
        else:
            for k, entry in running_srvs.items():
                col_i, col_btn = st.columns([3, 1], vertical_alignment="center")
                p_name = entry.get("project") or "Data utama"
                idle_m = int(servers.idle_seconds(k, entry) // 60)
                col_i.markdown(f"**{p_name}** · Port `{entry['port']}` · Aktif {idle_m} menit lalu")
                if col_btn.button("Tutup", key=f"stop_srv_{k}", use_container_width=True):
                    servers.stop(k)
                    _flash("success", f"Proyek {p_name} ditutup.")
                    st.rerun()
