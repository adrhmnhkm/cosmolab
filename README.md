# cosmolab

Multidisciplinary research assistant: harvest open-access papers from any field,
extract text, run LLM analysis, ask questions across the corpus, and write
cross-paper syntheses, literature matrices, and articles.

Team members without a technical background: start with
[PANDUAN_TIM.md](PANDUAN_TIM.md) (Indonesian, step by step).

## Setup

Windows: double-click `Pasang CosmoLab.bat`. It creates `.venv`, installs the
package, and copies `.env.example` to `.env` for you to fill in.

Manual setup:

    python -m venv .venv
    .venv/Scripts/python -m pip install -e .     # Linux/macOS: .venv/bin/python
    cp .env.example .env                          # then fill in LLM_API_KEY, LLM_MODEL, COSMOLAB_EMAIL

## Client projects

Each client project keeps its own papers, database, and outputs in
`projects/<name>/` (git-ignored). Without `--project`, the legacy `data/`
folder is used.

```bash
cosmolab project new 2026-11-klien-a --client "Klien A"
cosmolab project list
cosmolab -P 2026-11-klien-a harvest "islamic microfinance" --max-results 30
cosmolab -P 2026-11-klien-a ui            # dashboard for that project only
```

`COSMOLAB_PROJECT=<name>` in the environment does the same as `-P`. Run one
dashboard per project (use `--port` to run several side by side).

## Team access and AI cost

```bash
# Serve one project to the team over Tailscale (needs COSMOLAB_TEAM_PASSWORD, 10+ chars)
cosmolab -P 2026-11-klien-a ui --team --port 8501

# Token usage and estimated cost (prices: COSMOLAB_PRICING in .env)
cosmolab -P 2026-11-klien-a usage --by feature
cosmolab usage --all --month 2026-11
```

`--team` binds to this machine's Tailscale IP (override with `--host`) and puts
a password screen in front of the dashboard. Without `--team` the dashboard
only listens on `localhost`. Every chat completion is logged to
`<project>/usage.jsonl` by `cosmolab/usage.py`.

## Client deliverables

```bash
# Check every reference against the project corpus and Crossref
cosmolab -P 2026-11-klien-a verify articles/20261105_Judul.md

# Build Word + PDF with the firm letterhead into projects/<name>/deliverables/
cosmolab -P 2026-11-klien-a deliver articles/20261105_Judul.md --reviewer "Dr. Nama"
```

`deliver` refuses to build while references are unverified (wrong year or
author, not found, cited in text but missing from the list). After checking
them by hand, rerun with `--sudah-cek-manual`. The internal citation report
goes to `projects/<name>/qa/`. Letterhead settings are the `COSMOLAB_FIRM_*`
keys in `.env` (see `.env.example`).

## Usage

### 1. Core Pipeline
```bash
# Harvest papers from arXiv & OpenAlex (with smart deduplication)
cosmolab harvest "kalam cosmological argument" --max-results 40

# Extract text using layout-aware block sorting (handles 2-column papers)
cosmolab extract [--force]

# Analyze arguments with LLM & Pydantic structured output
cosmolab analyze --model ngoding

# Synthesize cross-paper research report (EN or ID)
cosmolab synthesize --model ngoding --lang id

# Check pipeline & database status
cosmolab status
```

### 2. Search & Knowledge Management
```bash
# Hybrid semantic search with RRF & column weighting (supports Indonesian & conceptual queries)
cosmolab search "apakah alam semesta punya awal mula"

# Exact weighted FTS5 search
cosmolab search "kalam infinity" --exact

# Ask research questions directly across your paper corpus (with RRF retrieval & LLM re-ranking)
cosmolab ask "Apa kritik matematika terhadap tak terhingga aktual pada argumen Kalam?"

# Export to Obsidian Vault notes with [[wikilinks]], tags, and comparative index
cosmolab export --format obsidian

# Export all papers to BibTeX for Zotero / Mendeley / LaTeX
cosmolab export --format bibtex

# Visualize paper argument flow as Mermaid diagram
cosmolab graph "2012_New_remarks"

# Re-sync SQLite database and search index from disk
cosmolab sync

# Launch interactive local Web Dashboard (Streamlit UI)
cosmolab ui
```

### 3. Federated Multi-Source Search
Cosmolab harvests academic papers concurrently across 4 major sources:
- **arXiv**: Physics, Quantum Cosmology, Math & Logic preprints.
- **DOAJ**: 100% Peer-reviewed open-access philosophy & humanities journals.
- **Semantic Scholar**: 200M+ academic paper AI graph.
- **OpenAlex**: Global open academic catalogue.
```
