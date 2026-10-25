import json
import sqlite3
from pathlib import Path
from rich.console import Console
from . import config
from .storage import read_meta

console = Console(force_terminal=True, legacy_windows=False)


def get_connection() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite database with relational tables and FTS5 search index."""
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True

    with con:
        # 1. Main papers table
        con.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                file TEXT PRIMARY KEY,
                id TEXT,
                title TEXT,
                year TEXT,
                doi TEXT,
                url TEXT,
                source TEXT,
                arxiv_id TEXT,
                abstract TEXT,
                full_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Analyses table
        con.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                paper_file TEXT PRIMARY KEY,
                thesis TEXT,
                argument_type TEXT,
                conclusion TEXT,
                supports_or_critiques TEXT,
                key_objection TEXT,
                key_defense TEXT,
                premises_json TEXT,
                notable_concepts_json TEXT,
                quotes_json TEXT,
                raw_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_file) REFERENCES papers(file)
            )
        """)

        # 3. FTS5 Virtual Table for full-text search
        con.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                paper_file UNINDEXED,
                title,
                abstract,
                full_text,
                thesis,
                argument_type,
                premises
            )
        """)

    if close_con:
        con.close()


def sync_all() -> dict:
    """Sync all metadata.jsonl, text files, and analysis JSONs into SQLite database."""
    config.ensure_dirs()
    init_db()
    con = get_connection()

    meta = read_meta()
    stats = {"papers_synced": 0, "analyses_synced": 0}

    with con:
        for rec in meta:
            file_name = rec.get("file", "")
            if not file_name:
                continue

            stem = Path(file_name).stem
            txt_path = config.TEXT_DIR / f"{stem}.txt"
            analysis_path = config.ANALYSIS_DIR / f"{stem}.json"

            full_text = ""
            if txt_path.exists():
                try:
                    full_text = txt_path.read_text(encoding="utf-8")
                except Exception:
                    pass

            abstract = rec.get("abstract") or ""
            if isinstance(abstract, dict):
                # Unwind inverted index if present
                abstract = str(abstract)

            # Upsert paper
            con.execute("""
                INSERT INTO papers (file, id, title, year, doi, url, source, arxiv_id, abstract, full_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file) DO UPDATE SET
                    id=excluded.id,
                    title=excluded.title,
                    year=excluded.year,
                    doi=excluded.doi,
                    url=excluded.url,
                    source=excluded.source,
                    arxiv_id=excluded.arxiv_id,
                    abstract=excluded.abstract,
                    full_text=excluded.full_text
            """, (
                file_name,
                rec.get("id"),
                rec.get("title"),
                rec.get("year"),
                rec.get("doi"),
                rec.get("url"),
                rec.get("source"),
                rec.get("arxiv_id"),
                abstract,
                full_text
            ))
            stats["papers_synced"] += 1

            # Analysis sync if exists
            thesis = None
            argument_type = None
            conclusion = None
            stance = None
            key_objection = None
            key_defense = None
            premises_str = ""

            if analysis_path.exists():
                try:
                    analysis_data = json.loads(analysis_path.read_text(encoding="utf-8"))
                    thesis = analysis_data.get("thesis")
                    argument_type = analysis_data.get("argument_type")
                    conclusion = analysis_data.get("conclusion")
                    stance = analysis_data.get("supports_or_critiques")
                    key_objection = analysis_data.get("key_objection")
                    key_defense = analysis_data.get("key_defense")
                    premises = analysis_data.get("premises", [])
                    premises_str = " \n ".join(premises)

                    con.execute("""
                        INSERT INTO analyses (
                            paper_file, thesis, argument_type, conclusion, supports_or_critiques,
                            key_objection, key_defense, premises_json, notable_concepts_json,
                            quotes_json, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(paper_file) DO UPDATE SET
                            thesis=excluded.thesis,
                            argument_type=excluded.argument_type,
                            conclusion=excluded.conclusion,
                            supports_or_critiques=excluded.supports_or_critiques,
                            key_objection=excluded.key_objection,
                            key_defense=excluded.key_defense,
                            premises_json=excluded.premises_json,
                            notable_concepts_json=excluded.notable_concepts_json,
                            quotes_json=excluded.quotes_json,
                            raw_json=excluded.raw_json
                    """, (
                        file_name,
                        thesis,
                        argument_type,
                        conclusion,
                        stance,
                        key_objection,
                        key_defense,
                        json.dumps(premises, ensure_ascii=False),
                        json.dumps(analysis_data.get("notable_concepts", []), ensure_ascii=False),
                        json.dumps(analysis_data.get("quotes", []), ensure_ascii=False),
                        json.dumps(analysis_data, ensure_ascii=False)
                    ))
                    stats["analyses_synced"] += 1
                except Exception as e:
                    console.print(f"[yellow]WARN  Could not sync analysis for {stem}: {e}[/yellow]")

            # Update FTS5 index
            con.execute("DELETE FROM papers_fts WHERE paper_file = ?", (file_name,))
            con.execute("""
                INSERT INTO papers_fts (paper_file, title, abstract, full_text, thesis, argument_type, premises)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                file_name,
                rec.get("title") or "",
                abstract,
                full_text[:100000],  # index first 100k chars for search efficiency
                thesis or "",
                argument_type or "",
                premises_str
            ))

    con.close()
    return stats


def search(query: str, limit: int = 10) -> list[dict]:
    """Search papers using SQLite FTS5 with fallback to LIKE pattern."""
    config.ensure_dirs()
    if not config.DB_FILE.exists():
        sync_all()

    con = get_connection()
    # Clean FTS query (remove special FTS5 operators unless intended)
    clean_q = "".join(c if c.isalnum() or c in (" ", "-", "_") else " " for c in query).strip()
    words = clean_q.split()
    if not words:
        con.close()
        return []

    # Use prefix matching on each term (e.g., 'kalam*' OR 'contingency*')
    fts_query = " OR ".join(f'"{w}"*' for w in words)

    results = []
    try:
        cur = con.execute("""
            SELECT 
                p.file, p.title, p.year, p.doi, p.arxiv_id,
                a.argument_type, a.supports_or_critiques, a.thesis, a.key_objection,
                snippet(papers_fts, 3, '[b][yellow]', '[/yellow][/b]', '...', 25) as snippet,
                bm25(papers_fts) as rank
            FROM papers_fts
            JOIN papers p ON p.file = papers_fts.paper_file
            LEFT JOIN analyses a ON a.paper_file = p.file
            WHERE papers_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit))
        results = [dict(r) for r in cur.fetchall()]
    except Exception:
        # Fallback to simple LIKE search if FTS query syntax error
        cur = con.execute("""
            SELECT 
                p.file, p.title, p.year, p.doi, p.arxiv_id,
                a.argument_type, a.supports_or_critiques, a.thesis, a.key_objection,
                substr(p.full_text, 1, 150) as snippet,
                0.0 as rank
            FROM papers p
            LEFT JOIN analyses a ON a.paper_file = p.file
            WHERE p.title LIKE ? OR p.full_text LIKE ? OR p.abstract LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        results = [dict(r) for r in cur.fetchall()]

    con.close()
    return results


def get_all_papers_with_analyses() -> list[dict]:
    """Retrieve all papers combined with their analyses."""
    if not config.DB_FILE.exists():
        sync_all()

    con = get_connection()
    cur = con.execute("""
        SELECT 
            p.*,
            a.thesis, a.argument_type, a.conclusion, a.supports_or_critiques,
            a.key_objection, a.key_defense, a.premises_json, a.notable_concepts_json,
            a.quotes_json, a.raw_json
        FROM papers p
        LEFT JOIN analyses a ON a.paper_file = p.file
        ORDER BY p.year DESC, p.title ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows
