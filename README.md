# cosmolab

Personal research pipeline: harvest OA papers on the cosmological argument,
extract text, run LLM analysis, and synthesize a cross-paper report.

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
# Full-text search (FTS5) across titles, abstracts, texts, & premises
cosmolab search "kalam infinity"

# Ask research questions directly across your paper corpus (RAG)
cosmolab ask "Apa kritik matematika terhadap tak terhingga aktual pada argumen Kalam?"

# Export to Obsidian Vault notes with [[wikilinks]], tags, and comparative index
cosmolab export --format obsidian

# Export all papers to BibTeX for Zotero / Mendeley / LaTeX
cosmolab export --format bibtex

# Visualize paper argument flow as Mermaid diagram
cosmolab graph "2012_New_remarks"

# Re-sync SQLite database and search index from disk
cosmolab sync
```
