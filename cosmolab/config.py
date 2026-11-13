import json
import os
import re
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values

# Load .env from project root (parent of cosmolab package)
PROJECT_ROOT = Path(__file__).parent.parent
env_config = dotenv_values(PROJECT_ROOT / ".env")

# Client projects: each one keeps its own papers, database and outputs under
# projects/<name>/. With no project selected, the legacy data folder is used.
PROJECTS_DIR = PROJECT_ROOT / "projects"
PROJECT_META_FILE = "project.json"
_PROJECT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _default_root() -> Path:
    raw = env_config.get("COSMOLAB_ROOT") or os.environ.get("COSMOLAB_ROOT") or "data"
    path = Path(raw)
    # Resolve against the repo, not the current directory, so the launcher and
    # the CLI always find the same folder.
    return path if path.is_absolute() else PROJECT_ROOT / path


def validate_project_name(name: str) -> str:
    """Return the normalized project name, or raise ValueError if it is unsafe."""
    norm = (name or "").strip().lower()
    if not _PROJECT_NAME_RE.match(norm):
        raise ValueError(
            "Nama proyek hanya boleh huruf kecil, angka, '-' dan '_' (maks. 64 karakter), "
            "dan harus diawali huruf atau angka. Contoh: 2026-11-klien-a"
        )
    return norm


def _set_root(root: Path):
    global ROOT, PDF_DIR, TEXT_DIR, ANALYSIS_DIR, SYNTH_DIR, META_FILE, DONE_FILE, DB_FILE, OBSIDIAN_DIR
    ROOT = root
    PDF_DIR = ROOT / "pdf"
    TEXT_DIR = ROOT / "text"
    ANALYSIS_DIR = ROOT / "analysis"
    SYNTH_DIR = ROOT / "synthesis"
    META_FILE = ROOT / "metadata.jsonl"
    DONE_FILE = ROOT / "downloaded.json"
    DB_FILE = ROOT / "cosmolab.db"
    OBSIDIAN_DIR = ROOT / "obsidian"


def project_dir(name: str) -> Path:
    return PROJECTS_DIR / validate_project_name(name)


def use_project(name: str | None):
    """Point every data path at a client project (None = the legacy data folder).

    The project must already exist; create it with create_project().
    """
    global PROJECT
    if not name:
        PROJECT = None
        _set_root(_default_root())
        return
    path = project_dir(name)
    if not (path / PROJECT_META_FILE).exists():
        raise FileNotFoundError(
            f"Proyek '{name}' belum ada. Buat dulu dengan: cosmolab project new {name}"
        )
    PROJECT = path.name
    _set_root(path)


def create_project(name: str, client: str = "", description: str = "") -> Path:
    path = project_dir(name)
    meta_path = path / PROJECT_META_FILE
    if meta_path.exists():
        raise FileExistsError(f"Proyek '{path.name}' sudah ada.")
    path.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": path.name,
        "client": client,
        "description": description,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def list_projects() -> list[dict]:
    projects = []
    if PROJECTS_DIR.exists():
        for meta_path in sorted(PROJECTS_DIR.glob(f"*/{PROJECT_META_FILE}")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
            meta["name"] = meta_path.parent.name
            meta["path"] = str(meta_path.parent)
            projects.append(meta)
    return projects


def project_info(name: str | None = None) -> dict:
    """Metadata of a project (default: the active one). Empty dict for the legacy folder."""
    name = name or PROJECT
    if not name:
        return {}
    meta_path = project_dir(name) / PROJECT_META_FILE
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {"name": name}


PROJECT = None
use_project(os.environ.get("COSMOLAB_PROJECT") or env_config.get("COSMOLAB_PROJECT") or None)

EMAIL = env_config.get("COSMOLAB_EMAIL") or os.environ.get("COSMOLAB_EMAIL", "you@example.com")
HEADERS = {
    "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 PersonalResearchArchive/1.0 ({EMAIL})",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
}

OPENALEX = "https://api.openalex.org/works"
UNPAYWALL = "https://api.unpaywall.org/v2"
CORE_API_URL = "https://api.core.ac.uk/v3/search/works"
CORE_API_KEY = env_config.get("CORE_API_KEY") or os.environ.get("CORE_API_KEY", "")
CROSSREF_API_URL = "https://api.crossref.org/works"

# LLM Gateway Configuration - prioritize .env file over system env
LLM_API_KEY = (
    env_config.get("LLM_API_KEY")
    or os.environ.get("LLM_API_KEY")
    or env_config.get("NINEROUTER_API_KEY")
    or os.environ.get("NINEROUTER_API_KEY", "")
)
LLM_BASE_URL = (
    env_config.get("LLM_BASE_URL")
    or os.environ.get("LLM_BASE_URL")
    or env_config.get("NINEROUTER_BASE_URL")
    or os.environ.get("NINEROUTER_BASE_URL", "https://api.openai.com/v1")
)
LLM_MODEL = (
    env_config.get("LLM_MODEL")
    or os.environ.get("LLM_MODEL")
    or env_config.get("NINEROUTER_MODEL")
    or "deepseek-v4-pro"
)

# Backward-compatibility aliases
NINEROUTER_API_KEY = LLM_API_KEY
NINEROUTER_BASE_URL = LLM_BASE_URL
NINEROUTER_MODEL = LLM_MODEL


def ensure_dirs():
    for d in (PDF_DIR, TEXT_DIR, ANALYSIS_DIR, SYNTH_DIR, OBSIDIAN_DIR):
        d.mkdir(parents=True, exist_ok=True)


# Firm branding used on client deliverables (Word/PDF)
def _env(key: str, default: str = "") -> str:
    return env_config.get(key) or os.environ.get(key) or default


FIRM_NAME = _env("COSMOLAB_FIRM_NAME", "CosmoLab Research")
FIRM_TAGLINE = _env("COSMOLAB_FIRM_TAGLINE", "Layanan Riset Multidisipliner")
FIRM_ADDRESS = _env("COSMOLAB_FIRM_ADDRESS")
FIRM_CONTACT = _env("COSMOLAB_FIRM_CONTACT")
_logo = _env("COSMOLAB_FIRM_LOGO")
FIRM_LOGO = (Path(_logo) if Path(_logo).is_absolute() else PROJECT_ROOT / _logo) if _logo else None

# Papers analysed at the same time. 4 suits a paid API. A local model (llama.cpp) shares one
# context across parallel requests, so set LLM_CONCURRENCY=1 there.
def _concurrency(value: str) -> int:
    try:
        return max(1, min(int(value), 8))
    except (TypeError, ValueError):
        return 4


LLM_CONCURRENCY = _concurrency(_env("LLM_CONCURRENCY", "4"))

# Team access: password asked by the dashboard when started with `cosmolab ui --team`.
TEAM_PASSWORD = _env("COSMOLAB_TEAM_PASSWORD")

# Dense passage search (optional). Leave EMBED_MODEL empty to use keyword (BM25) search only.
# Remote: any OpenAI-compatible /embeddings model, e.g. EMBED_MODEL=bge-m3.
# Local: EMBED_MODEL=local:<fastembed model>, needs `pip install fastembed`.
EMBED_MODEL = _env("EMBED_MODEL")
EMBED_BASE_URL = _env("EMBED_BASE_URL") or LLM_BASE_URL
EMBED_API_KEY = _env("EMBED_API_KEY") or LLM_API_KEY

# Let the LLM reorder passage candidates by meaning in Tanya Korpus (one extra call per paper,
# run in parallel). Set COSMOLAB_RERANK_PASSAGES=0 to turn it off.
RERANK_PASSAGES = _env("COSMOLAB_RERANK_PASSAGES", "1").strip().lower() not in ("0", "false", "no", "off")

# Cache of small LLM calls (query expansion, passage rerank) in <root>/cache/llm.json.
# Set COSMOLAB_LLM_CACHE=0 to turn it off.
LLM_CACHE = _env("COSMOLAB_LLM_CACHE", "1").strip().lower() not in ("0", "false", "no", "off")

# Skip the LLM rerank when BM25 and embeddings agree on one clear winner.
# Set COSMOLAB_RERANK_ALWAYS=1 to rerank every time.
RERANK_ALWAYS = _env("COSMOLAB_RERANK_ALWAYS", "0").strip().lower() in ("1", "true", "yes", "on")
