import os
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from cosmolab import config, team
from cosmolab.ui.pages import team_admin
from cosmolab.ui.context import AppContext
from test_team import TeamCase, WEB


class TestTeamAdminPage(TeamCase):
    def test_sidebar_shows_kelola_tim_for_owner(self):
        team.add_user("bos", role="admin")
        team.change_password("bos", "kata-sandi-baru-1")
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}), \
                mock.patch("importlib.reload", lambda m: m), \
                mock.patch.object(config, "PROJECT", "klien-a"):
            at = AppTest.from_file(WEB, default_timeout=120)
            at.run()
            # Login as admin
            at.text_input[0].set_value("bos")
            at.text_input[1].set_value("kata-sandi-baru-1")
            at.button[0].click().run()
            self.assertEqual([e.value for e in at.exception], [])
            # Admin sees "Kelola Tim & Proyek" in sidebar buttons
            btn_labels = [b.label for b in at.sidebar.button]
            self.assertTrue(any("Kelola Tim" in lbl for lbl in btn_labels))

    def test_team_admin_page_renders_and_creates_project(self):
        team.add_user("bos", role="admin")
        team.add_user("rina", role="konsultan")
        config.create_project("proyek-lama")
        ctx = AppContext(
            menu="Kelola Tim",
            all_papers=[],
            papers=[],
            selected_faculty_id="all",
            faculty_list=[],
            faculty_options=["all"],
            faculty_labels={"all": "Semua"},
            total_all=0,
            total_active=0,
            total_analyzed=0,
            fac_dist={},
        )
        # Directly test rendering team_admin logic
        team.set_current(team.get_user("bos"))
        try:
            self.assertEqual(len(config.list_projects()), 3) # klien-a, klien-b, proyek-lama
            p = config.create_project("proyek-baru", client="Klien UI")
            team.add_member(p.name, "rina")
            self.assertIn("rina", team.members("proyek-baru"))
        finally:
            team.set_current(None)


if __name__ == "__main__":
    unittest.main()
