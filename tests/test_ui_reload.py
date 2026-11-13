import sys
import unittest
from unittest import mock

from cosmolab.ui import pages
from cosmolab.ui import reload as ui_reload


class TestUiReload(unittest.TestCase):
    def test_page_added_after_start_is_picked_up(self):
        # Simulate a server started before home.py existed.
        saved = sys.modules.pop("cosmolab.ui.pages.home")
        delattr(pages, "home")
        try:
            # reload() is patched out: reloading for real would undo conftest's patches
            # (for example the test copy of the SINTA list).
            with mock.patch("importlib.reload", lambda m: m):
                failed = ui_reload.reload_ui()
            self.assertEqual(failed, [])
            self.assertTrue(hasattr(pages.home, "render"))
        finally:
            sys.modules["cosmolab.ui.pages.home"] = saved
            pages.home = saved


if __name__ == "__main__":
    unittest.main()
