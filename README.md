# cosmolab

Multidisciplinary research assistant: harvest open-access papers from any field,
extract text, run LLM analysis, ask questions across the corpus, and write
cross-paper syntheses, literature matrices, and articles.

## Setup

    export COSMOLAB_EMAIL="you@example.com"
    export OPENAI_API_KEY="sk-..."
    pip install -e .

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
