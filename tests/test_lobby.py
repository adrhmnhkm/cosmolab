"""Team lobby: one-time tickets, starting and stopping project dashboards, and the lobby page."""

import os
import time
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from cosmolab import config, servers, team
from test_team import TeamCase, WEB

LOBBY = str(Path(WEB).parent / "lobby.py")


class LobbyCase(TeamCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(servers, "SHARED_DIR", Path(self._tmp.name) / "shared")
        p.start()
        self._patches.append(p)


class TestTickets(LobbyCase):
    def test_ticket_works_once_and_only_for_its_project(self):
        team.add_user("rina")
        token = team.make_ticket("rina", "klien-a")
        self.assertIsNone(team.redeem_ticket(token, "klien-b"))
        self.assertEqual(team.redeem_ticket(token, "klien-a")["u"], "rina")
        self.assertIsNone(team.redeem_ticket(token, "klien-a"))  # used

    def test_forged_or_expired_ticket_is_refused(self):
        token = team.make_ticket("rina", "klien-a")
        body, sig = token.split(".")
        self.assertIsNone(team.redeem_ticket(body + "." + "0" * len(sig), "klien-a"))
        self.assertIsNone(team.redeem_ticket("rusak", "klien-a"))
        with mock.patch.object(team, "TICKET_TTL", -1):
            old = team.make_ticket("rina", "klien-a")
        self.assertIsNone(team.redeem_ticket(old, "klien-a"))

    def test_shared_password_ticket_for_main_data(self):
        token = team.make_ticket("", None)
        self.assertEqual(team.redeem_ticket(token, None)["u"], "")


class TestServers(LobbyCase):
    def _register(self, **entries):
        servers._save({k: {"project": k, "port": port, "host": "127.0.0.1", "pid": 0, "started_ts": time.time()}
                       for k, port in entries.items()})

    def test_running_drops_dashboards_that_stopped(self):
        self._register(**{"klien-a": 8502, "klien-b": 8503})
        with mock.patch.object(servers, "_answers", side_effect=lambda h, p, timeout=0.5: p == 8502):
            self.assertEqual(list(servers.running()), ["klien-a"])
        self.assertEqual(list(servers._load()), ["klien-a"])

    def test_running_dashboard_is_reused(self):
        self._register(**{"klien-a": 8502})
        with mock.patch.object(servers, "_answers", return_value=True), \
                mock.patch.object(servers, "_spawn") as spawn:
            self.assertEqual(servers.ensure("klien-a", "127.0.0.1"), 8502)
        spawn.assert_not_called()

    def test_new_dashboard_gets_a_free_port(self):
        proc = mock.Mock(pid=4321)
        proc.poll.return_value = None
        started = set()

        def answers(host, port, timeout=0.5):
            return port in started

        def spawn(project, host, port):
            started.add(port)
            return proc

        with mock.patch.object(servers, "_answers", side_effect=answers), \
                mock.patch.object(servers, "_spawn", side_effect=spawn):
            port = servers.ensure("klien-a", "127.0.0.1")
        self.assertGreaterEqual(port, servers.PORT_START)
        self.assertEqual(servers._load()["klien-a"]["pid"], 4321)

    def test_full_lobby_replaces_only_an_idle_dashboard(self):
        keys = {f"p{i}": 8502 + i for i in range(servers.MAX_RUNNING)}
        self._register(**keys)
        for k in keys:
            servers.touch(k)
        with mock.patch.object(servers, "_answers", return_value=True), mock.patch.object(servers, "_spawn"):
            with self.assertRaises(servers.LobbyFull):
                servers.ensure("klien-a", "127.0.0.1")

        old = time.time() - servers.MIN_IDLE_TO_REPLACE - 60
        os.utime(servers.heartbeat_path("p2"), (old, old))
        with mock.patch.object(servers, "_answers", return_value=True), \
                mock.patch.object(servers, "_free_port", return_value=8599), \
                mock.patch.object(servers, "_spawn", return_value=mock.Mock(pid=1, poll=lambda: None)), \
                mock.patch.object(servers, "_kill") as kill:
            self.assertEqual(servers.ensure("klien-a", "127.0.0.1"), 8599)
        kill.assert_called_once()
        self.assertNotIn("p2", servers._load())

    def test_idle_dashboards_are_stopped(self):
        self._register(**{"klien-a": 8502, "klien-b": 8503})
        servers.touch("klien-a")
        servers.touch("klien-b")
        old = time.time() - 3 * 3600
        os.utime(servers.heartbeat_path("klien-b"), (old, old))
        with mock.patch.object(servers, "_answers", return_value=True), mock.patch.object(servers, "_kill"):
            self.assertEqual(servers.stop_idle(), ["klien-b"])
        self.assertEqual(list(servers._load()), ["klien-a"])


class TestLobbyPage(LobbyCase):
    def _app(self):
        return AppTest.from_file(LOBBY, default_timeout=60)

    def _login(self, at, username, password):
        at.text_input[0].set_value(username)
        at.text_input[1].set_value(password)
        at.button[0].click().run()

    def _ready(self, username, role):
        team.add_user(username, role=role, name=username.title())
        team.change_password(username, "kata-sandi-baru-1")

    def test_consultant_sees_only_their_projects(self):
        self._ready("rina", "konsultan")
        team.add_member("klien-a", "rina")
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), \
                mock.patch.object(servers, "running", return_value={}):
            at = self._app().run()
            self._login(at, "rina", "kata-sandi-baru-1")
            self.assertEqual([e.value for e in at.exception], [])
            self.assertEqual(len(at.tabs), 0)  # no admin tabs
            self.assertFalse(any(b.label in ("Buat akun", "Buat proyek") for b in at.button))
            shown = " ".join(m.value for m in at.markdown)
            self.assertIn("klien-a", shown)
            self.assertNotIn("klien-b", shown)
            self.assertNotIn("Data utama", shown)

    def test_admin_creates_a_project_with_members(self):
        self._ready("bos", "admin")
        self._ready("rina", "konsultan")
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), \
                mock.patch.object(servers, "running", return_value={}):
            at = self._app().run()
            self._login(at, "bos", "kata-sandi-baru-1")
            self.assertEqual([t.label for t in at.tabs][:2], ["Proyek", "Proyek baru"])
            client = next(t for t in at.text_input if t.label == "Nama klien")
            client.set_value("Universitas X - Budi")
            at.multiselect[0].set_value(["rina"])
            next(b for b in at.button if b.label == "Buat proyek").click().run()
            self.assertEqual([e.value for e in at.exception], [])
        made = [p for p in config.list_projects() if p.get("client") == "Universitas X - Budi"]
        self.assertEqual(len(made), 1)
        self.assertTrue(made[0]["name"].endswith("-universitas-x-budi"))
        self.assertEqual(team.members(made[0]["name"]), ["rina"])


class TestOwner(LobbyCase):
    def test_earliest_admin_is_owner_until_handed_over(self):
        self.assertEqual(team.owner_username(), "")
        team.add_user("rina")
        team.add_user("bos", role="admin")
        team.add_user("wakil", role="admin")
        bos, wakil, rina = (team.get_user(u) for u in ("bos", "wakil", "rina"))
        self.assertEqual(team.owner_username(), "bos")
        self.assertTrue(team.can_manage(bos, "admin") and team.can_manage(bos, "konsultan"))
        self.assertFalse(team.can_manage(wakil, "admin"))
        self.assertTrue(team.can_manage(wakil, "konsultan"))
        self.assertFalse(team.can_manage(rina, "konsultan"))
        with self.assertRaises(ValueError):
            team.set_owner("rina")  # not an admin
        team.set_owner("wakil")
        self.assertTrue(team.is_owner(team.get_user("wakil")))
        self.assertFalse(team.is_owner(bos))

    def test_other_admin_manages_consultants_only(self):
        for name, role in (("bos", "admin"), ("wakil", "admin"), ("rina", "konsultan")):
            team.add_user(name, role=role)
            team.change_password(name, "kata-sandi-baru-1")
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), \
                mock.patch.object(servers, "running", return_value={}):
            at = AppTest.from_file(LOBBY, default_timeout=60).run()
            at.text_input[0].set_value("wakil")
            at.text_input[1].set_value("kata-sandi-baru-1")
            at.button[0].click().run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertFalse(any(r.label == "Peran" for r in at.radio))  # no role choice: consultant only
            # Only the consultant can be reset or deleted; not the owner, not another admin, not yourself.
            accounts = next(s for s in at.selectbox if s.label == "Akun").options
            self.assertEqual([o.split(" ")[0] for o in accounts], ["rina"])


class TestSharedPasswordLobby(LobbyCase):
    def test_shared_password_cannot_make_accounts(self):
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}),                 mock.patch.object(config, "TEAM_PASSWORD", "password-bersama-1"),                 mock.patch.object(servers, "running", return_value={}):
            at = AppTest.from_file(LOBBY, default_timeout=60).run()
            at.text_input[0].set_value("password-bersama-1")
            at.button[0].click().run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertEqual([t.label for t in at.tabs], ["Proyek", "Proyek baru", "Sedang terbuka"])
            self.assertFalse(any(b.label == "Buat akun" for b in at.button))
        self.assertFalse(team.has_users())


class TestTicketLogin(LobbyCase):
    def test_dashboard_accepts_a_lobby_ticket(self):
        team.add_user("rina", name="Rina")
        team.change_password("rina", "kata-sandi-baru-1")
        team.add_member("klien-a", "rina")
        token = team.make_ticket("rina", "klien-a")
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), mock.patch("importlib.reload", lambda m: m), \
                mock.patch.object(config, "PROJECT", "klien-a"):
            at = AppTest.from_file(WEB, default_timeout=120)
            at.query_params["tiket"] = token
            at.run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertEqual(at.session_state["team_user"]["username"], "rina")
            self.assertNotIn("tiket", at.query_params)

            # The same link again, in a fresh browser session: refused, the login form shows.
            again = AppTest.from_file(WEB, default_timeout=120)
            again.query_params["tiket"] = token
            again.run()
            self.assertEqual([t.label for t in again.text_input], ["Nama pengguna", "Password"])


if __name__ == "__main__":
    unittest.main()
