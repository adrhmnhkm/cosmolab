"""
cosmolab.similarity
~~~~~~~~~~~~~~~~~~~
Pre-submission similarity check for a student's own draft.

Every sentence of the draft is compared with:
1. the full text and abstract of every paper in the project collection, and
2. the abstracts of the works the draft cites (looked up by DOI on OpenAlex).

Matching is plain text overlap: runs of SHINGLE consecutive words that appear
in both the sentence and a source. No AI is involved. Text in quotation marks,
in-text citations, and the reference list are left out, as Turnitin's usual
settings do.

A sentence that is close to a source gets one of three labels:
- tanpa_sitasi: close to a source, and no citation in or right after it;
- sitasi_lain: close to a source, but the citation points at another work;
- terlalu_dekat: cited correctly, but the wording is still mostly the source's.

The score is an estimate over these sources only. It is not a Turnitin score:
Turnitin compares against a far larger database this tool cannot reach.
"""

from __future__ import annotations

import re
from datetime import datetime

import requests

from . import authors as _authors
from . import config, verify

SHINGLE = 6           # words per overlapping run
MIN_SENTENCE_WORDS = 8
FLAG_COVERAGE = 0.5   # share of the sentence's words found in one source
FLAG_RUN = 10         # or this many identical words in a row
EXCERPT_CHARS = 240
# Fewer same-language sources than this and a low score says little.
WEAK_MIN_SOURCES = 5

LANG_NAMES = {"id": "Indonesia", "en": "Inggris"}
_LANG_WORDS = {
    "id": {"yang", "dan", "dengan", "untuk", "dalam", "ini", "pada", "dari", "adalah", "tidak", "akan", "oleh",
           "bahwa", "juga", "atau", "dapat", "sebagai", "tersebut"},
    "en": {"the", "and", "of", "to", "in", "is", "that", "for", "with", "are", "this", "by", "as", "be", "which",
           "from", "on", "was"},
}


def guess_lang(text: str, sample_words: int = 3000) -> str:
    """'id', 'en', or '' when unsure. Counts common function words; no AI."""
    ws = verify.normalize((text or "")[: sample_words * 10]).split()[:sample_words]
    counts = {lang: sum(1 for w in ws if w in vocab) for lang, vocab in _LANG_WORDS.items()}
    best = max(counts, key=counts.get)
    other = min(counts.values())
    if counts[best] < 5 or counts[best] < 1.5 * other:
        return ""
    return best

NO_CITATION, WRONG_SOURCE, TOO_CLOSE = "tanpa_sitasi", "sitasi_lain", "terlalu_dekat"
LABELS = {
    NO_CITATION: "Mirip sumber, tanpa sitasi",
    WRONG_SOURCE: "Mirip sumber, sitasinya ke karya lain",
    TOO_CLOSE: "Sitasi benar, tapi kalimatnya terlalu mirip sumber",
}
ADVICE = {
    NO_CITATION: "Tambahkan sitasi ke sumber ini, lalu tulis ulang dengan pemahaman sendiri.",
    WRONG_SOURCE: "Periksa sumbernya: kalimat ini sangat mirip karya yang tidak dikutip di sini.",
    TOO_CLOSE: "Beri tanda petik dan nomor halaman, atau parafrasekan dengan kata-kata sendiri.",
}
_ORDER = {NO_CITATION: 0, WRONG_SOURCE: 1, TOO_CLOSE: 2}

CAVEAT = ("Skor ini perkiraan berdasarkan koleksi paper proyek dan abstrak sumber yang dikutip. "
          "Ini bukan skor Turnitin; Turnitin membandingkan dengan basis data yang jauh lebih besar.")

_QUOTED_RE = re.compile(r"“[^”]{3,}”|\"[^\"]{3,}\"")
_SENT_RE = re.compile(r"(?<=[.!?])[\"”’)]?\s+(?=[A-Z\"“(])")
_ABBREV_END = re.compile(r"\b(?:et al|dkk|hlm|hal|dll|dsb|No|Vol|vs|cf|e\.g|i\.e|Dr|Prof)\.$", re.I)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def words(text: str) -> list[str]:
    return verify.normalize(text).split()


def _strip_citations(text: str) -> str:
    for regex in (verify.PAREN_CITE_RE, verify.NARRATIVE_CITE_RE, verify.BRACKET_CITE_RE):
        text = regex.sub(" ", text)
    return text


def split_sentences(paragraph: str) -> list[str]:
    parts, out = _SENT_RE.split(paragraph), []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and _ABBREV_END.search(out[-1]):
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return out


def checkable_words(sentence: str) -> list[str]:
    """Words of a sentence that count: no quoted text, no citations."""
    return words(_strip_citations(_QUOTED_RE.sub(" ", sentence)))


def _shingles(ws: list[str]) -> list[str]:
    return [" ".join(ws[i:i + SHINGLE]) for i in range(len(ws) - SHINGLE + 1)]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def corpus_sources() -> list[dict]:
    from . import db

    try:
        papers = db.get_all_papers_with_analyses()
    except Exception:
        return []
    out = []
    for p in papers:
        text = " ".join(x for x in (p.get("abstract"), p.get("full_text")) if x)
        if text.strip():
            out.append({"kind": "korpus", "title": p.get("title") or p.get("file") or "",
                        "authors": _authors.as_list(p.get("authors")), "year": str(p.get("year") or ""),
                        "doi": p.get("doi") or "", "file": p.get("file") or "", "text": text})
    return out


def _cache_path():
    return config.ROOT / "abstracts_cache.json"


def _cached_abstract(doi: str) -> str:
    """OpenAlex abstract, cached per project so reruns do not ask again."""
    import json

    path = _cache_path()
    try:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        cache = {}
    if doi in cache:
        return cache[doi]
    text = _openalex_abstract(doi)
    cache[doi] = text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return text


def _openalex_abstract(doi: str) -> str:
    from .harvest import _flatten_inverted_abstract

    r = requests.get(f"{config.OPENALEX}/doi:{doi}", params={"select": "abstract_inverted_index", "mailto": config.EMAIL},
                     headers=config.HEADERS, timeout=20)
    if r.status_code != 200:
        return ""
    return _flatten_inverted_abstract(r.json().get("abstract_inverted_index") or {})


def cited_sources(citations: dict, corpus: list[dict], fetch=None) -> tuple[list[dict], int]:
    """Abstracts of cited works that are not already in the collection.

    Returns (sources, how many lookups found nothing).
    """
    fetch = fetch or _cached_abstract
    have = {s["doi"].lower() for s in corpus if s.get("doi")}
    out, missed = [], 0
    for ref in (citations or {}).get("references", []):
        doi = (ref.get("doi") or "").lower()
        if not doi or doi in have or ref.get("status") == verify.OK_CORPUS:
            continue
        have.add(doi)
        try:
            text = fetch(doi)
        except requests.RequestException:
            text = ""
        if not text:
            missed += 1
            continue
        out.append({"kind": "dikutip", "title": ref.get("matched_title") or ref.get("title") or ref["raw"][:120],
                    "authors": [ref.get("authors") or ""], "year": (ref.get("years") or [""])[0],
                    "doi": ref.get("doi") or "", "file": "", "text": text})
    return out, missed


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _cites_source(cites: list, source: dict) -> bool:
    """True when one of the citations names this source's first author (and year, if known)."""
    names = verify.normalize(" ".join(source.get("authors") or []))
    for c in cites:
        first = verify.normalize(c.name).split(" ")[0] if verify.normalize(c.name) else ""
        if first and first in names and (not source.get("year") or c.year == source["year"]):
            return True
    return False


def _excerpt(source_text: str, matched: set[str]) -> str:
    """The source passage around the first matching run, so the consultant can compare."""
    ws = source_text.split()
    norm = [verify.normalize(w) for w in ws]
    for i in range(len(norm) - SHINGLE + 1):
        if " ".join(x for x in norm[i:i + SHINGLE] if x) in matched:
            snippet = " ".join(ws[max(0, i - 3): i + 40])
            return snippet[:EXCERPT_CHARS] + ("..." if len(snippet) > EXCERPT_CHARS else "")
    return ""


TOPIC_PHRASES = 30      # most frequent two-word phrases of the draft, e.g. "ruang publik"
TOPIC_MIN_SHARE = 0.3   # share of those phrases a collection paper must contain to count as on topic

# Academic words that appear in almost any paper and say nothing about the topic.
_GENERIC = _LANG_WORDS["id"] | _LANG_WORDS["en"] | set("""
penelitian peneliti hasil metode data analisis secara terhadap berdasarkan merupakan menjadi memiliki sehingga
karena namun antara bagi lebih sangat banyak berbagai setiap telah sudah masih hanya maupun serta melalui
terdapat adanya dilakukan menggunakan digunakan menunjukkan sosial masyarakat indonesia tahun bentuk proses faktor
pengaruh tinggi besar baik sumber informasi jurnal kajian studi teori konsep aspek sistem pendekatan kualitatif
kuantitatif responden variabel hubungan peran upaya kondisi tujuan masalah penting utama umum khusus lain sendiri
mereka kami kita saya yaitu yakni misalnya seperti kemudian selain para cara salah satu pertama kedua nilai tingkat
jumlah pula agar ketika saat sejak hingga sampai tentang mengenai terkait dimana gambar tabel halaman sebuah suatu
individu kelompok kehidupan manusia dunia negara pemerintah perkembangan kemampuan pemahaman pengetahuan bagaimana
mengapa apakah karya penulis buku study research results analysis method based using used also however between
through their these those have been more other such than into about would could paper article university approach
findings review were there when what where while within without both each many most some only well
""".split())


def _content_bigrams(text: str) -> list[str]:
    ws = words(text)
    return [f"{a} {b}" for a, b in zip(ws, ws[1:])
            if len(a) > 3 and len(b) > 3 and a not in _GENERIC and b not in _GENERIC
            and not a.isdigit() and not b.isdigit()]


def topic_phrases(draft_text: str, n: int = TOPIC_PHRASES) -> list[str]:
    """The draft's most frequent two-word content phrases. They describe its topic far
    better than single words, which unrelated papers often share ("digital", "media")."""
    from collections import Counter

    return [b for b, _ in Counter(_content_bigrams(draft_text)).most_common(n)]


def on_topic(source_text: str, phrases: list[str]) -> bool:
    if not phrases:
        return True
    have = set(_content_bigrams(source_text[:60000]))
    return sum(p in have for p in phrases) / len(phrases) >= TOPIC_MIN_SHARE


def _language_check(paragraphs: list[dict], corpus: list[dict], cited: list[dict]) -> dict:
    """How many sources can really be compared: same language as the draft, and on its topic.

    Text matching only works within one language, and a collection paper on
    another topic will never match. Cited works count as on topic: the student
    chose them.
    """
    draft_text = " ".join(p["text"] for p in paragraphs)
    lang = guess_lang(draft_text)
    same = {"korpus": 0, "dikutip": 0}
    relevant = {"korpus": 0, "dikutip": 0}
    if lang:
        same_corpus = [s for s in corpus if guess_lang(s["text"]) == lang]
        same["korpus"] = len(same_corpus)
        same["dikutip"] = relevant["dikutip"] = sum(1 for s in cited if guess_lang(s["text"]) == lang)
        phrases = topic_phrases(draft_text)
        relevant["korpus"] = sum(1 for s in same_corpus if on_topic(s["text"], phrases))
    total = relevant["korpus"] + relevant["dikutip"]
    return {"lang": lang, "same_lang": same, "relevant": relevant, "weak": bool(lang) and total < WEAK_MIN_SOURCES}


def weak_message(sim: dict) -> str:
    """Warning shown instead of a reassuring 'nothing found' when few sources can really be compared."""
    lang = LANG_NAMES.get(sim.get("lang"), sim.get("lang"))
    rel = sim.get("relevant") or sim["same_lang"]
    n = rel["korpus"] + rel["dikutip"]
    off_topic = sim["same_lang"]["korpus"] - rel["korpus"]
    return (f"Pembanding lemah: hanya {n} sumber yang berbahasa {lang} dan setopik dengan draf"
            + (f" ({off_topic} paper berbahasa {lang} di koleksi topiknya berbeda)" if off_topic > 0 else "") + ". "
            f"Skor {sim['score']}% belum berarti aman, karena kalimat hanya bisa dicocokkan dengan sumber sebahasa "
            "dan setopik. "
            f"Lengkapi pembanding dari daftar pustaka, atau tambah paper berbahasa {lang} ke koleksi proyek"
            + (" (Panen Paper, centang Khusus jurnal Indonesia)" if sim.get("lang") == "id" else "")
            + ", lalu jalankan ulang.")


def weak_note_student(sim: dict) -> str:
    lang = LANG_NAMES.get(sim.get("lang"), sim.get("lang"))
    return (f"Catatan: sumber pembanding berbahasa {lang} masih sedikit, sehingga skor ini belum berarti draf "
            "bebas dari kemiripan dengan sumber lain.")


def check(paragraphs: list[dict], citations: dict | None = None, online: bool = True,
          sources: list[dict] | None = None, fetch=None) -> dict:
    """Compare every sentence of the draft with the sources.

    paragraphs: [{"n", "text"}] as from review.split_paragraphs.
    sources: override the collection (tests); otherwise the project corpus.
    """
    corpus = corpus_sources() if sources is None else sources
    cited, missed = cited_sources(citations, corpus, fetch) if online and citations else ([], 0)
    all_sources = corpus + cited

    sentences = []
    for p in paragraphs:
        for i, s in enumerate(split_sentences(p["text"])):
            sentences.append({"paragraph": p["n"], "i": i, "text": s, "words": checkable_words(s)})

    wanted = {sh for s in sentences for sh in _shingles(s["words"])}
    # source index -> shingles it shares with the draft. Only draft shingles are
    # kept, so memory stays small however large the collection is.
    shared: dict[int, set[str]] = {}
    for idx, src in enumerate(all_sources):
        hits = wanted.intersection(_shingles(words(src["text"])))
        if hits:
            shared[idx] = hits

    total_words = sum(len(s["words"]) for s in sentences)
    findings, flagged_words, by_source = [], 0, {}
    for k, s in enumerate(sentences):
        if len(s["words"]) < MIN_SENTENCE_WORDS:
            continue
        sh = _shingles(s["words"])
        best = None
        for idx, hits in shared.items():
            on = [x in hits for x in sh]
            if not any(on):
                continue
            covered = set()
            run = longest = 0
            for j, hit in enumerate(on):
                if hit:
                    covered.update(range(j, j + SHINGLE))
                    run += 1
                    longest = max(longest, run + SHINGLE - 1)
                else:
                    run = 0
            coverage = len(covered) / len(s["words"])
            if best is None or (coverage, longest) > (best[1], best[2]):
                best = (idx, coverage, longest)
        if not best or (best[1] < FLAG_COVERAGE and best[2] < FLAG_RUN):
            continue

        idx, coverage, longest = best
        src = all_sources[idx]
        # A citation counts when it is in the sentence or the next one in the same paragraph.
        nxt = sentences[k + 1]["text"] if k + 1 < len(sentences) and sentences[k + 1]["paragraph"] == s["paragraph"] else ""
        cites = verify.extract_citations(s["text"]) or verify.extract_citations(nxt)
        if not cites:
            label = NO_CITATION
        elif not _cites_source(cites, src):
            label = WRONG_SOURCE
        else:
            label = TOO_CLOSE

        n_words = round(coverage * len(s["words"]))
        flagged_words += n_words
        key = src.get("doi") or src.get("file") or src["title"]
        by_source[key] = by_source.get(key, 0) + n_words
        findings.append({
            "paragraph": s["paragraph"],
            "sentence": s["text"][:400],
            "match_pct": round(coverage * 100),
            "run": longest,
            "label": label,
            "cited_as": ", ".join(f"{c.name} {c.year}" for c in cites),
            "source": {k2: src.get(k2, "") for k2 in ("kind", "title", "authors", "year", "doi", "file")},
            "source_excerpt": _excerpt(src["text"], {x for x in sh if x in shared[idx]}),
            "hidden": False,
        })

    findings.sort(key=lambda f: (_ORDER[f["label"]], f["paragraph"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"m{i}"
    top = []
    for key, n in sorted(by_source.items(), key=lambda kv: -kv[1])[:10]:
        src = next(s for s in all_sources if (s.get("doi") or s.get("file") or s["title"]) == key)
        top.append({"title": src["title"], "authors": src["authors"], "year": src["year"], "kind": src["kind"],
                    "pct": round(100 * n / total_words, 1) if total_words else 0.0})
    return {
        **_language_check(paragraphs, corpus, cited),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "online": online,
        "sources": {"korpus": len(corpus), "dikutip": len(cited), "dikutip_gagal": missed},
        "cited_dois": [s["doi"].lower() for s in cited],
        "corpus_files": [s["file"] for s in corpus if s.get("file")],
        "words": total_words,
        "score": round(100 * flagged_words / total_words, 1) if total_words else 0.0,
        "findings": findings,
        "top_sources": top,
    }


def visible(sim: dict) -> list[dict]:
    return [f for f in (sim or {}).get("findings", []) if not f.get("hidden")]


def set_hidden(sim: dict, fid: str, hidden: bool) -> None:
    for f in sim.get("findings", []):
        if f["id"] == fid:
            f["hidden"] = bool(hidden)
            return
    raise KeyError(f"Temuan {fid} tidak ada")


def source_label(src: dict) -> str:
    who = _authors.display(src.get("authors") or []) if src.get("kind") == "korpus" else (src.get("authors") or [""])[0]
    who = (who or "").strip()
    year = f" ({src['year']})" if src.get("year") else ""
    return f"{who}{year}, {src.get('title', '')}".strip(", ")
