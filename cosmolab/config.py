import os
from pathlib import Path
from dotenv import dotenv_values

# Load .env from project root (parent of cosmolab package)
PROJECT_ROOT = Path(__file__).parent.parent
env_config = dotenv_values(PROJECT_ROOT / ".env")

ROOT = Path(env_config.get("COSMOLAB_ROOT") or os.environ.get("COSMOLAB_ROOT", "data"))
PDF_DIR = ROOT / "pdf"
TEXT_DIR = ROOT / "text"
ANALYSIS_DIR = ROOT / "analysis"
SYNTH_DIR = ROOT / "synthesis"
META_FILE = ROOT / "metadata.jsonl"
DONE_FILE = ROOT / "downloaded.json"
DB_FILE = ROOT / "cosmolab.db"
OBSIDIAN_DIR = ROOT / "obsidian"

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
