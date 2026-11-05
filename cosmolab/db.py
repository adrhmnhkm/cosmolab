import json
import sqlite3
from pathlib import Path
from rich.console import Console
from . import config
from . import faculties as _faculties
from . import authors as _authors
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
                faculty TEXT DEFAULT 'ilahiyyat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add faculty column if table existed without it
        try:
            cursor = con.execute("PRAGMA table_info(papers)")
            columns = [row[1] for row in cursor.fetchall()]
            if "faculty" not in columns:
                con.execute("ALTER TABLE papers ADD COLUMN faculty TEXT DEFAULT 'ilahiyyat'")
            if "authors" not in columns:
                con.execute("ALTER TABLE papers ADD COLUMN authors TEXT DEFAULT '[]'")
            if "authors_source" not in columns:
                con.execute("ALTER TABLE papers ADD COLUMN authors_source TEXT DEFAULT ''")
        except Exception:
            pass

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


def _meta_authors(meta: list[dict]) -> dict:
    """Last non-empty author list per file across all metadata records."""
    out = {}
    for rec in meta:
        names = _authors.as_list(rec.get("authors"))
        if rec.get("file") and names:
            out[rec["file"]] = names
    return out


def _set_authors(con, file_name: str, meta_names, store: dict) -> None:
    names, source = _authors.pick(file_name, meta_names, store)
    con.execute("UPDATE papers SET authors = ?, authors_source = ? WHERE file = ?",
                (json.dumps(names, ensure_ascii=False), source, file_name))


def set_authors(file_name: str, names: list[str]) -> None:
    """Save authors typed by a researcher. These are never overwritten by lookups."""
    _authors.save_entry(file_name, names, _authors.MANUAL, force=True)
    sync_one(file_name)


def sync_all() -> dict:
    """Sync all metadata.jsonl, text files, and analysis JSONs into SQLite database."""
    config.ensure_dirs()
    init_db()
    con = get_connection()

    meta = read_meta()
    stats = {"papers_synced": 0, "analyses_synced": 0}
    author_store = _authors.load()
    meta_authors = _meta_authors(meta)

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

            faculty = rec.get("faculty")
            if not faculty:
                faculty = _faculties.detect_faculty_from_text(rec.get("title") or "", abstract, full_text)

            # Upsert paper
            con.execute("""
                INSERT INTO papers (file, id, title, year, doi, url, source, arxiv_id, abstract, full_text, faculty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file) DO UPDATE SET
                    id=excluded.id,
                    title=excluded.title,
                    year=excluded.year,
                    doi=excluded.doi,
                    url=excluded.url,
                    source=excluded.source,
                    arxiv_id=excluded.arxiv_id,
                    abstract=excluded.abstract,
                    full_text=excluded.full_text,
                    faculty=excluded.faculty
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
                full_text,
                faculty
            ))
            _set_authors(con, file_name, meta_authors.get(file_name), author_store)
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


def sync_one(file_name: str) -> dict:
    """Sync a single paper (metadata, text, analysis) into SQLite database.
    
    Much faster than sync_all() when only one paper was updated — O(1) instead of O(N).
    """
    config.ensure_dirs()
    init_db()
    con = get_connection()
    stats = {"papers_synced": 0, "analyses_synced": 0}

    # Find the metadata record for this file
    meta = read_meta()
    rec = None
    stem = Path(file_name).stem
    for m in meta:
        m_file = m.get("file", "")
        if m_file == file_name or Path(m_file).stem == stem:
            rec = m
            break

    if not rec:
        con.close()
        return stats

    file_key = rec.get("file", "")
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
        abstract = str(abstract)

    faculty = rec.get("faculty")
    if not faculty:
        faculty = _faculties.detect_faculty_from_text(rec.get("title") or "", abstract, full_text)

    with con:
        # Upsert paper
        con.execute("""
            INSERT INTO papers (file, id, title, year, doi, url, source, arxiv_id, abstract, full_text, faculty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file) DO UPDATE SET
                id=excluded.id, title=excluded.title, year=excluded.year,
                doi=excluded.doi, url=excluded.url, source=excluded.source,
                arxiv_id=excluded.arxiv_id, abstract=excluded.abstract,
                full_text=excluded.full_text, faculty=excluded.faculty
        """, (
            file_key, rec.get("id"), rec.get("title"), rec.get("year"),
            rec.get("doi"), rec.get("url"), rec.get("source"), rec.get("arxiv_id"),
            abstract, full_text, faculty
        ))
        _set_authors(con, file_key, _meta_authors(meta).get(file_key), _authors.load())
        stats["papers_synced"] = 1

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
                        thesis=excluded.thesis, argument_type=excluded.argument_type,
                        conclusion=excluded.conclusion, supports_or_critiques=excluded.supports_or_critiques,
                        key_objection=excluded.key_objection, key_defense=excluded.key_defense,
                        premises_json=excluded.premises_json, notable_concepts_json=excluded.notable_concepts_json,
                        quotes_json=excluded.quotes_json, raw_json=excluded.raw_json
                """, (
                    file_key, thesis, argument_type, conclusion, stance,
                    key_objection, key_defense,
                    json.dumps(premises, ensure_ascii=False),
                    json.dumps(analysis_data.get("notable_concepts", []), ensure_ascii=False),
                    json.dumps(analysis_data.get("quotes", []), ensure_ascii=False),
                    json.dumps(analysis_data, ensure_ascii=False)
                ))
                stats["analyses_synced"] = 1
            except Exception as e:
                console.print(f"[yellow]WARN  Could not sync analysis for {stem}: {e}[/yellow]")

        # Update FTS5 index
        con.execute("DELETE FROM papers_fts WHERE paper_file = ?", (file_key,))
        con.execute("""
            INSERT INTO papers_fts (paper_file, title, abstract, full_text, thesis, argument_type, premises)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            file_key, rec.get("title") or "", abstract,
            full_text[:100000], thesis or "", argument_type or "", premises_str
        ))

    con.close()
    return stats


# Common question and functional stopwords that skew prefix search
STOP_WORDS = {
    "apakah", "bagaimana", "mengapa", "kenapa", "adakah", "apa", "siapa", "kapan",
    "dimana", "yang", "dan", "di", "ke", "dari", "ini", "itu", "pada", "untuk",
    "dengan", "adalah", "punya", "terhadap", "dalam", "tentang", "bisa", "dapat",
    "oleh", "sebagai", "sebuah", "suatu", "akan", "jika", "bila", "antara",
    "what", "is", "the", "how", "why", "who", "when", "where", "which", "are",
    "and", "or", "to", "in", "of", "for", "with", "on", "about", "can", "does",
    "did", "do", "an", "a", "by", "as", "at", "from", "that", "this"
}


def search(query: str, limit: int = 10) -> list[dict]:
    """Search papers using SQLite FTS5 with weighted columns and fallback to LIKE pattern.
    
    Weights configuration:
    - paper_file: 0.0 (UNINDEXED)
    - title: 10.0 (Core paper topic)
    - abstract: 5.0 (High summary value)
    - full_text: 1.0 (Raw paper body)
    - thesis: 10.0 (Extracted core thesis)
    - argument_type: 3.0 (Domain classification)
    - premises: 8.0 (Formal dialectical propositions)
    """
    config.ensure_dirs()
    if not config.DB_FILE.exists():
        sync_all()

    con = get_connection()
    # Clean FTS query (remove special FTS5 operators unless intended)
    clean_q = "".join(c if c.isalnum() or c in (" ", "-", "_") else " " for c in query).strip()
    raw_words = clean_q.split()
    if not raw_words:
        con.close()
        return []

    # Filter conversational question words unless all terms are stopwords
    meaningful_words = [w for w in raw_words if w.lower() not in STOP_WORDS]
    words = meaningful_words if meaningful_words else raw_words

    # Use prefix matching on each term (e.g., 'kalam*' OR 'contingency*')
    fts_query = " OR ".join(f'"{w}"*' for w in words)

    results = []
    try:
        cur = con.execute("""
            SELECT 
                p.file, p.title, p.year, p.doi, p.arxiv_id, p.faculty,
                a.argument_type, a.supports_or_critiques, a.thesis, a.conclusion,
                a.key_objection, a.key_defense, a.premises_json,
                snippet(papers_fts, 3, '[b][yellow]', '[/yellow][/b]', '...', 25) as snippet,
                bm25(papers_fts, 0.0, 10.0, 5.0, 1.0, 10.0, 3.0, 8.0) as rank
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
                p.file, p.title, p.year, p.doi, p.arxiv_id, p.faculty,
                a.argument_type, a.supports_or_critiques, a.thesis, a.conclusion,
                a.key_objection, a.key_defense, a.premises_json,
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


def get_papers_by_stance(argument_type: str = None, stance: str = None, limit: int = 10) -> list[dict]:
    """Retrieve structured papers filtered by argument type and stance (supports/critiques/mixed/neutral)."""
    con = get_connection()
    clauses = ["a.thesis IS NOT NULL"]
    params = []

    if argument_type and argument_type != "Semua":
        clauses.append("a.argument_type = ?")
        params.append(argument_type)

    if stance and stance != "Semua":
        clauses.append("a.supports_or_critiques = ?")
        params.append(stance)

    where_sql = " AND ".join(clauses)
    params.append(limit)

    cur = con.execute(f"""
        SELECT 
            p.file, p.title, p.year, p.doi, p.url, p.source,
            a.thesis, a.argument_type, a.conclusion, a.supports_or_critiques,
            a.key_objection, a.key_defense, a.premises_json, a.quotes_json
        FROM papers p
        JOIN analyses a ON a.paper_file = p.file
        WHERE {where_sql}
        ORDER BY p.year DESC
        LIMIT ?
    """, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def get_dialectical_pairs(argument_type: str = None) -> dict:
    """Retrieve opposing philosophical camps (proponents vs opponents) for dialectical reasoning."""
    proponents = get_papers_by_stance(argument_type=argument_type, stance="supports", limit=5)
    critiques = get_papers_by_stance(argument_type=argument_type, stance="critiques", limit=5)
    mixed_or_neutral = get_papers_by_stance(argument_type=argument_type, stance="mixed", limit=3)
    
    return {
        "argument_type": argument_type or "all",
        "proponents": proponents,
        "opponents": critiques,
        "evaluators": mixed_or_neutral,
    }


def get_paper_knowledge_summary(file_name: str) -> dict | None:
    """Get a compact structured syllogism summary of a paper (~350 tokens) for agent reasoning."""
    con = get_connection()
    cur = con.execute("""
        SELECT 
            p.file, p.title, p.year, p.doi,
            a.thesis, a.argument_type, a.conclusion, a.supports_or_critiques,
            a.key_objection, a.key_defense, a.premises_json, a.quotes_json
        FROM papers p
        JOIN analyses a ON a.paper_file = p.file
        WHERE p.file = ? OR p.file LIKE ?
        LIMIT 1
    """, (file_name, f"%{file_name}%"))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    
    d = dict(row)
    if d.get("premises_json"):
        try:
            d["premises"] = json.loads(d["premises_json"])
        except Exception:
            d["premises"] = []
    if d.get("quotes_json"):
        try:
            d["quotes"] = json.loads(d["quotes_json"])
        except Exception:
            d["quotes"] = []
    return d


def get_papers_by_faculty(faculty_id: str | None = None, limit: int = 100) -> list[dict]:
    """Retrieve papers belonging to a specific faculty."""
    con = get_connection()
    if faculty_id and faculty_id != "all":
        cur = con.execute("""
            SELECT 
                p.*,
                a.thesis, a.argument_type, a.conclusion, a.supports_or_critiques,
                a.key_objection, a.key_defense
            FROM papers p
            LEFT JOIN analyses a ON a.paper_file = p.file
            WHERE p.faculty = ?
            ORDER BY p.year DESC, p.title ASC
            LIMIT ?
        """, (faculty_id, limit))
    else:
        cur = con.execute("""
            SELECT 
                p.*,
                a.thesis, a.argument_type, a.conclusion, a.supports_or_critiques,
                a.key_objection, a.key_defense
            FROM papers p
            LEFT JOIN analyses a ON a.paper_file = p.file
            ORDER BY p.year DESC, p.title ASC
            LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def update_paper_faculty(file_name: str, faculty_id: str) -> bool:
    """Manually update or override a paper's assigned faculty."""
    con = get_connection()
    with con:
        con.execute("UPDATE papers SET faculty = ? WHERE file = ?", (faculty_id, file_name))
    con.close()
    return True


def get_faculty_distribution() -> dict[str, int]:
    """Get paper counts across all faculties."""
    con = get_connection()
    cur = con.execute("SELECT faculty, COUNT(*) as cnt FROM papers GROUP BY faculty")
    dist = {row["faculty"] or "ilahiyyat": row["cnt"] for row in cur.fetchall()}
    con.close()
    return dist

