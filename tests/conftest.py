"""Run every test against a throwaway copy of the data folder.

Some tests sync the database, save custom faculties, or write reports. Without
this, they would change the real research data in data/ (or COSMOLAB_ROOT).

The copy holds only what tests read: the database, metadata, analyses, and
extracted text, plus one sample PDF. Other PDFs, embeddings, and caches are
left out to keep it small.
This runs at import time, before test modules compute HAS_CORPUS.
"""

import shutil
import tempfile
from pathlib import Path

from cosmolab import config

_FILES = ("cosmolab.db", "metadata.jsonl", "downloaded.json", "authors.json", "dois.json", "custom_faculties.json")
_DIRS = ("analysis", "text")

_real_root = Path(config.ROOT)
_tmp = Path(tempfile.mkdtemp(prefix="cosmolab-tests-"))
_test_root = _tmp / "data"
_test_root.mkdir()

for name in _FILES:
    if (_real_root / name).is_file():
        shutil.copy2(_real_root / name, _test_root / name)
for name in _DIRS:
    if (_real_root / name).is_dir():
        shutil.copytree(_real_root / name, _test_root / name)
# The one PDF that test_passage_grounding reads.
_SAMPLE_PDF = "2012_New_remarks_on_the_Cosmological_Argument.pdf"
if (_real_root / "pdf" / _SAMPLE_PDF).is_file():
    (_test_root / "pdf").mkdir()
    shutil.copy2(_real_root / "pdf" / _SAMPLE_PDF, _test_root / "pdf" / _SAMPLE_PDF)

config._set_root(_test_root)
# use_project(None) resets to the default root; keep that inside the copy too.
config._default_root = lambda: _test_root

# The SINTA journal list is shared by all projects and lives outside data/.
from cosmolab import sinta  # noqa: E402

sinta.list_path = lambda: _tmp / "shared" / "sinta_journals.json"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_tmp, ignore_errors=True)
