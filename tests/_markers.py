"""Skip conditions for tests that need local data or the network.

Some tests read the local paper collection (data/ or COSMOLAB_ROOT). A fresh
checkout, such as CI, has no collection, so those tests are skipped there.
Tests that call outside services run only with COSMOLAB_NETWORK_TESTS=1.
"""

import os
import unittest

from cosmolab import config


def _has_corpus() -> bool:
    if not config.DB_FILE.exists():
        return False
    from cosmolab import db
    try:
        return bool(db.get_all_papers_with_analyses())
    except Exception:
        return False


HAS_CORPUS = _has_corpus()

needs_corpus = unittest.skipUnless(HAS_CORPUS, "needs a local paper collection with analyses")
needs_network = unittest.skipUnless(
    os.environ.get("COSMOLAB_NETWORK_TESTS") == "1", "set COSMOLAB_NETWORK_TESTS=1 to call outside services"
)
