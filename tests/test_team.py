import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from cosmolab import audit, config, home, review, team

WEB = str(Path(__file__).resolve().parent.parent / "cosmolab" / "web.py")


class TeamCase(unittest.TestCase):
    """Accounts and projects in a temp folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._patches = [mock.patch.object(team, "USERS_FILE", tmp / "shared" / "team_users.json"),
                         mock.patch.object(config, "PROJECTS_DIR", tmp / "projects")]
        for p in self._patches:
            p.start()
        config.create_project("klien-a")
        config.create_project("klien-b")
        team.set_current(None)

    def tearDown(self):
        team.set_current(None)
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()


class TestAccounts(TeamCase):
    def test_password_is_hashed_and_checked(self):
        self.assertFalse(team.has_users())
        temp = team.add_user("Rina", role="konsultan", name="Rina Wulandari")
        raw = team.users_file().read_text(encoding="utf-8")
        self.assertNotIn(temp, raw)  # never stored as text
        self.assertEqual(len(json.loads(raw)["rina"]["hash"]), 64)
        self.assertIsNone(team.verify("rina", "salah-password"))
        self.assertIsNone(team.verify("tidak-ada", temp))
        user = team.verify("RINA", temp)
        self.assertEqual((user["username"], user["role"], user["name"], user["must_change"]),
                         ("rina", "konsultan", "Rina Wulandari", True))

    def test_bad_input(self):
        team.add_user("rina")
        for bad in ("", "a", "Rina W", "../x"):
            with self.assertRaises(ValueError):
                team.add_user(bad)
        with self.assertRaises(ValueError):
            team.add_user("rina")  # exists
        with self.assertRaises(ValueError):
            team.add_user("budi", role="bos")

    def test_first_login_must_change_password(self):
        temp = team.add_user("rina")
        with self.assertRaises(ValueError):
            team.change_password("rina", "pendek")
        with self.assertRaises(ValueError):
            team.change_password("rina", temp)  # same as the temporary one
        team.change_password("rina", "kata-sandi-baru-1")
        self.assertIsNone(team.verify("rina", temp))
        self.assertFalse(team.verify("rina", "kata-sandi-baru-1")["must_change"])
        new_temp = team.reset_password("rina")
        self.assertTrue(team.verify("rina", new_temp)["must_change"])
        self.assertIsNone(team.verify("rina", "kata-sandi-baru-1"))

    def test_project_access(self):
        team.add_user("admin1", role="admin")
        team.add_user("rina")
        admin, rina = team.get_user("admin1"), team.get_user("rina")
        self.assertTrue(team.can_access(admin, None) and team.can_access(admin, "klien-b"))
        self.assertFalse(team.can_access(rina, "klien-a"))
        team.add_member("klien-a", "rina")
        self.assertTrue(team.can_access(rina, "klien-a"))
        self.assertFalse(team.can_access(rina, "klien-b"))
        self.assertFalse(team.can_access(rina, None))  # main data is for admins
        self.assertFalse(team.can_access(None, "klien-a"))
        self.assertEqual(team.projects_of("rina"), ["klien-a"])
        with self.assertRaises(ValueError):
            team.add_member("klien-a", "hantu")
        with self.assertRaises(ValueError):
            team.add_member("tidak-ada", "rina")
        team.remove_member("klien-a", "rina")
        self.assertFalse(team.can_access(rina, "klien-a"))

    def test_remove_account(self):
        team.add_user("admin1", role="admin")
        team.add_user("rina")
        team.add_member("klien-a", "rina")
        with self.assertRaises(ValueError):
            team.remove_user("admin1")  # the only admin, others remain
        team.remove_user("rina")
        self.assertEqual(team.members("klien-a"), [])
        self.assertIsNone(team.get_user("rina"))
        team.remove_user("admin1")  # last account may go: back to the shared password
        self.assertFalse(team.has_users())

    def test_account_name_reaches_audit_review_and_owner_view(self):
        team.add_user("rina", name="Rina Wulandari")
        old_root = config.ROOT
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()
        try:
            with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), \
                    mock.patch.object(review, "report_markdown", lambda r: ""):
                team.set_current(team.get_user("rina"))
                self.assertEqual(audit.log("tanya", question="x")["user"], "rina")
                self.assertFalse(home.is_owner())
                report = {"title": "Draf", "comments": [], "paragraphs": []}
                review.save(report)
                self.assertEqual(report["created_by"], "rina")
                self.assertEqual(team.current_name(), "Rina Wulandari")
                team.set_current({"username": "bos", "role": "admin", "name": "Bos"})
                self.assertTrue(home.is_owner())
                review.save(report)
                self.assertEqual(report["created_by"], "rina")  # saving again keeps the maker
            team.set_current(None)
            self.assertNotEqual(audit.log("tanya", question="x")["user"], "rina")
        finally:
            config._set_root(old_root)


class TestLoginPage(TeamCase):
    def _app(self):
        at = AppTest.from_file(WEB, default_timeout=120)
        return at

    def test_shared_password_until_first_account(self):
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), mock.patch("importlib.reload", lambda m: m), \
                mock.patch.object(config, "TEAM_PASSWORD", "password-bersama-1"):
            at = self._app().run()
            self.assertEqual([t.label for t in at.text_input], ["Password tim"])
            at.text_input[0].set_value("password-bersama-1")
            at.button[0].click().run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertTrue(at.session_state["team_auth_ok"])

    def test_account_login_change_password_and_project_gate(self):
        temp = team.add_user("rina", name="Rina Wulandari")
        team.add_member("klien-a", "rina")
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), mock.patch("importlib.reload", lambda m: m):
            # Not a member of klien-b: refused with the same message as a wrong password.
            with mock.patch.object(config, "PROJECT", "klien-b"):
                at = self._app().run()
                self.assertEqual([t.label for t in at.text_input], ["Nama pengguna", "Password"])
                at.text_input[0].set_value("rina")
                at.text_input[1].set_value(temp)
                at.button[0].click().run()
                self.assertIn("salah, atau akun ini tidak punya akses", at.error[0].value)
                self.assertNotIn("team_user", at.session_state)

            with mock.patch.object(config, "PROJECT", "klien-a"):
                at = self._app().run()
                at.text_input[0].set_value("rina")
                at.text_input[1].set_value("salah")
                at.button[0].click().run()
                self.assertEqual(len(at.error), 1)

                at.text_input[0].set_value("rina")
                at.text_input[1].set_value(temp)
                at.button[0].click().run()
                self.assertEqual([e.value for e in at.exception], [])
                # Temporary password: only the change form shows, not the dashboard.
                self.assertEqual([t.label for t in at.text_input], ["Password baru", "Ulangi password baru"])
                at.text_input[0].set_value("kata-sandi-baru-1")
                at.text_input[1].set_value("kata-sandi-lain-22")
                at.button[0].click().run()
                self.assertIn("tidak sama", at.error[0].value)
                at.text_input[0].set_value("kata-sandi-baru-1")
                at.text_input[1].set_value("kata-sandi-baru-1")
                at.button[0].click().run()
                self.assertEqual([e.value for e in at.exception], [])
                self.assertEqual(at.session_state["team_user"]["username"], "rina")
                self.assertTrue(any("Masuk sebagai" in c.value for c in at.sidebar.caption))
                self.assertFalse(any("Khusus pemilik" in m.value for m in at.markdown))  # consultant: no owner section

                # Access revoked: the next click goes back to the login form.
                team.remove_member("klien-a", "rina")
                at.run()
                self.assertEqual([t.label for t in at.text_input], ["Nama pengguna", "Password"])


if __name__ == "__main__":
    unittest.main()
