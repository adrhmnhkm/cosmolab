import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

__version__ = "0.1.0"

# Log every AI call's token usage to the active project (see cosmolab/usage.py).
from . import usage as _usage  # noqa: E402

_usage.install()
