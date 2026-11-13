"""Reload changed code on every dashboard run, so an update shows without restarting the server.

Streamlit runs web.py again on each interaction, but modules it imported stay
cached in the server process. Without this, a page added or changed after the
server started is missing or out of date (for example "module
'cosmolab.ui.pages' has no attribute 'home'").
"""

import importlib
import pkgutil
import sys

# Core modules the pages use that web.py does not already reload. usage is
# left out: it wraps the AI client once at startup.
CORE = ("cosmolab.utils", "cosmolab.sinta", "cosmolab.similarity", "cosmolab.coverage", "cosmolab.review",
        "cosmolab.backup", "cosmolab.position", "cosmolab.home")
# Shared UI modules, before the pages that import from them.
UI = ("cosmolab.ui.components", "cosmolab.ui.context", "cosmolab.ui.claims", "cosmolab.ui.papers",
      "cosmolab.ui.sidebar")


def _load(name: str):
    mod = sys.modules.get(name)
    return importlib.reload(mod) if mod else importlib.import_module(name)


def reload_ui() -> list[str]:
    """Reload the core modules, the shared UI modules, and every page, picking up new pages.

    Returns the modules that failed to load; the rest still reload.
    """
    failed = []
    for name in CORE + UI:
        try:
            _load(name)
        except Exception:
            failed.append(name)
    pkg = importlib.import_module("cosmolab.ui.pages")
    for info in pkgutil.iter_modules(pkg.__path__):
        name = f"{pkg.__name__}.{info.name}"
        try:
            setattr(pkg, info.name, _load(name))
        except Exception:
            failed.append(name)
    return failed
