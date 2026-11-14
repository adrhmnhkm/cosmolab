"""
cosmolab.passages
~~~~~~~~~~~~~~~~~
Passage search inside one paper.

Each paper is cut into passages (paragraphs, long ones split into windows).
Passages are ranked with Okapi BM25 and, when an embedding model is
configured (config.EMBED_MODEL), also by vector similarity. The two rankings
are merged with Reciprocal Rank Fusion, so a passage that matches the words
OR the meaning of the query rises to the top.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter

from . import config

STOP = {
    # Indonesian
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "pada", "untuk", "dengan", "adalah", "dalam",
    "tentang", "bisa", "dapat", "oleh", "sebagai", "sebuah", "suatu", "akan", "jika", "bila",
    "antara", "atau", "juga", "tidak", "lebih", "karena", "bahwa", "telah", "sudah", "para",
    "apakah", "bagaimana", "mengapa", "apa", "siapa", "kapan", "dimana", "terhadap", "hal",
    "hlm", "dkk", "serta", "namun", "tetapi", "maka", "agar", "secara", "masih", "hanya",
    "ada", "cara", "berapa", "harus", "yaitu", "yakni", "tersebut", "merupakan", "menjadi", "seperti",
    "bagi", "hingga", "sampai", "saja", "lain", "setiap", "semua", "beberapa", "banyak", "sangat",
    "pernah", "belum", "lagi", "mana", "kami", "kita", "saya", "anda", "mereka", "dia", "pun",
    "lalu", "jadi", "sedang", "sejak", "punya", "memiliki", "yakni", "ialah", "adakah",
    # English
    "the", "and", "for", "with", "that", "this", "are", "was", "were", "from", "but", "not",
    "has", "have", "had", "its", "their", "which", "what", "how", "why", "who", "when", "where",
    "can", "does", "did", "also", "than", "then", "there", "these", "those", "such", "into",
    "been", "being", "our", "they", "them", "may", "will", "would", "should", "could", "about",
    "one", "two", "all", "any", "more", "most", "other", "some", "only", "very", "each",
}

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_SENT = re.compile(r"(?<=[.!?])\s+")

MIN_CHARS = 40
MAX_CHARS = 900
WINDOW = 600
RRF_K = 60.0
EXTRA_WEIGHT = 0.35
# A passage matches only if it holds enough of the question's words (or, with
# embeddings, is close enough in meaning). One shared common word is not a match.
MIN_QUERY_TERMS = 2   # distinct question words (fewer if the question has fewer)
MIN_EXTRA_TERMS = 2   # distinct expansion words, for a question in another language


def _stem(w: str) -> str:
    """Very light suffix stripping so 'violations' meets 'violation'."""
    if len(w) > 6 and w.endswith(("nya", "kan")):
        w = w[:-3]
    elif len(w) > 6 and w.endswith("an") and not w.endswith("ian"):
        w = w[:-2]
    if len(w) > 5:
        for suf in ("ations", "ation", "ates", "ate", "ions", "ion", "ings", "ing", "ies", "ed", "es", "ly", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


# Words found in papers of every field. They still score, but do not on their own make a
# passage a match: "time series" or "replacement strategy" says nothing about the topic.
GENERIC = {_stem(w) for w in (
    "time", "series", "strategy", "strategies", "replacement", "analysis", "method", "methods", "model",
    "models", "system", "systems", "design", "data", "effect", "effects", "factor", "factors", "study",
    "studies", "research", "result", "results", "approach", "framework", "process", "level", "levels",
    "impact", "development", "performance", "based", "case", "use", "using", "theory", "theoretical",
    "empirical", "evidence", "role", "relationship", "concept", "conceptual", "practice", "practices",
    "application", "applications", "technique", "techniques", "dynamics", "structure", "pattern",
    "patterns", "criteria", "selection", "procedure", "optimization", "evaluation", "assessment",
    "prediction", "forecasting", "regression", "variable", "variables", "management", "quality",
    "reduction", "protocol", "guidelines", "traditional", "modern", "general", "specific", "new",
    "high", "low", "long", "short", "term", "rate", "value", "price", "cost", "demand", "supply",
    "analisis", "metode", "model", "sistem", "data", "pengaruh", "faktor", "studi", "penelitian",
    "hasil", "pendekatan", "proses", "tingkat", "dampak", "pengembangan", "kinerja", "teori",
    "harga", "waktu", "nilai", "biaya", "bulan", "tahun", "hari",
)}


def tokenize(text: str) -> list[str]:
    out = []
    # NFKC turns PDF ligatures back into letters: "ﬁnite" -> "finite".
    for w in _WORD.findall(unicodedata.normalize("NFKC", text or "").lower()):
        if w in STOP or (len(w) < 3 and not w.isdigit()):
            continue
        out.append(_stem(w))
    return out


def chunk_pages(pages: list[dict]) -> list[dict]:
    """Turn extract.get_paper_pages() output into passages with page numbers."""
    chunks = []
    for p in pages or []:
        paragraphs = p.get("paragraphs") or [p.get("text", "")]
        for para in paragraphs:
            text = " ".join((para or "").split())
            if len(text) < MIN_CHARS:
                continue
            if len(text) <= MAX_CHARS:
                chunks.append({"page": p["page"], "text": text})
                continue
            # Long paragraph: overlapping sentence windows of about WINDOW chars.
            sents = [s for s in _SENT.split(text) if s.strip()]
            i = 0
            while i < len(sents):
                win, n = [], 0
                j = i
                while j < len(sents) and (n + len(sents[j]) <= WINDOW or not win):
                    win.append(sents[j])
                    n += len(sents[j]) + 1
                    j += 1
                chunks.append({"page": p["page"], "text": " ".join(win)})
                if j >= len(sents):
                    break
                i = max(i + 1, j - 1)  # keep one sentence of overlap
    return chunks


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.avg = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str] | dict[str, float]) -> list[float]:
        """BM25 score of every document. A dict query gives each term its own weight."""
        weights = query if isinstance(query, dict) else {t: 1.0 for t in query}
        out = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i]) or 1
            s = 0.0
            for t, wt in weights.items():
                f = tf.get(t)
                if not f:
                    continue
                s += wt * self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avg or 1)))
            out.append(s)
        return out


_INDEX: dict[str, dict] = {}


def _index(file_name: str) -> dict:
    from . import extract

    key = f"{config.ROOT}|{file_name}"
    if key in _INDEX:
        return _INDEX[key]
    chunks = chunk_pages(extract.get_paper_pages(file_name))
    toks = [tokenize(c["text"]) for c in chunks]
    idx = {"chunks": chunks, "bm25": BM25(toks), "vectors": None}
    _INDEX[key] = idx
    return idx


def clear_cache():
    _INDEX.clear()


# ---------------------------------------------------------------- dense part

def embeddings_enabled() -> bool:
    return bool(config.EMBED_MODEL)


_LOCAL_MODEL = None


def embed(texts: list[str], kind: str = "passage") -> list[list[float]]:
    """Embed texts with the configured model. Raises when none is configured."""
    model = config.EMBED_MODEL
    if not model:
        raise RuntimeError("EMBED_MODEL belum diatur")
    if model.startswith("local:"):
        global _LOCAL_MODEL
        from fastembed import TextEmbedding  # optional dependency

        if _LOCAL_MODEL is None:
            _LOCAL_MODEL = TextEmbedding(model_name=model[len("local:"):])
        prefix = "query: " if kind == "query" else "passage: "
        return [list(map(float, v)) for v in _LOCAL_MODEL.embed([prefix + t for t in texts])]

    from openai import OpenAI

    client = OpenAI(base_url=config.EMBED_BASE_URL, api_key=config.EMBED_API_KEY)
    out = []
    for i in range(0, len(texts), 64):
        resp = client.embeddings.create(model=model, input=texts[i:i + 64])
        out.extend(d.embedding for d in resp.data)
    return out


def _cache_path(file_name: str):
    from pathlib import Path

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(file_name).stem)[:120]
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", config.EMBED_MODEL)[:40]
    return config.ROOT / "embeddings" / f"{safe}.{tag}.json"


def _vectors(file_name: str, idx: dict):
    """Passage vectors, cached on disk per paper and model."""
    if idx["vectors"] is not None:
        return idx["vectors"]
    chunks = idx["chunks"]
    sig = hashlib.sha1("\n".join(c["text"] for c in chunks).encode("utf-8")).hexdigest()
    path = _cache_path(file_name)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("sig") == sig:
            idx["vectors"] = cached["vectors"]
            return idx["vectors"]
    except Exception:
        pass
    vecs = embed([c["text"] for c in chunks], kind="passage") if chunks else []
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sig": sig, "model": config.EMBED_MODEL, "vectors": vecs}), encoding="utf-8")
    except Exception:
        pass
    idx["vectors"] = vecs
    return vecs


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------- search

def search(file_name: str, query: str, top_k: int = 5, extra_terms: str = "", dense: bool | None = None) -> list[dict]:
    """Rank the passages of one paper for a query.

    Returns dicts with page, text, score (0-100, higher is better), bm25,
    and dense (cosine, or None when embeddings are off).
    """
    idx = _index(file_name)
    chunks = idx["chunks"]
    if not chunks:
        return []

    # Words of the query count fully; extra (expansion) terms count less.
    weights = {t: EXTRA_WEIGHT for t in tokenize(extra_terms)}
    weights.update({t: 1.0 for t in tokenize(query)})
    bm = idx["bm25"].scores(weights) if weights else [0.0] * len(chunks)

    # Phrase bonus: adjacent query words that also appear next to each other.
    raw = [w for w in _WORD.findall(query.lower()) if len(w) > 2 and w not in STOP]
    bigrams = {f"{raw[i]} {raw[i + 1]}" for i in range(len(raw) - 1)}
    if bigrams:
        for i, c in enumerate(chunks):
            low = c["text"].lower()
            hits = sum(1 for g in bigrams if g in low)
            if hits and bm[i] > 0:
                bm[i] *= 1 + 0.25 * min(hits, 3)

    use_dense = embeddings_enabled() if dense is None else dense
    cos = None
    if use_dense:
        try:
            vecs = _vectors(file_name, idx)
            qv = embed([(query + " " + extra_terms).strip()], kind="query")[0]
            cos = [_cos(qv, v) for v in vecs]
        except Exception:
            cos = None

    q_terms = {t for t, w in weights.items() if w == 1.0}
    x_terms = set(weights) - q_terms
    need = min(MIN_QUERY_TERMS, len(q_terms))
    tfs = idx["bm25"].tf

    def enough(terms, tf, n):
        # n shared words, at least one of them not GENERIC: "data" may help a methods
        # question match, but "time series" alone is no match.
        hit = terms.intersection(tf)
        return len(hit) >= n and bool(hit - GENERIC)

    def matches(i):
        if need and enough(q_terms, tfs[i], need):
            return True
        if enough(x_terms, tfs[i], MIN_EXTRA_TERMS):
            return True
        return cos is not None and cos[i] >= config.DENSE_MIN

    ok = [matches(i) for i in range(len(chunks))]
    order_bm = sorted(range(len(chunks)), key=lambda i: bm[i], reverse=True)
    fused = [0.0] * len(chunks)
    for r, i in enumerate(order_bm, 1):
        if bm[i] > 0 and ok[i]:
            fused[i] += 1.0 / (RRF_K + r)
    if cos is not None:
        for r, i in enumerate(sorted(range(len(chunks)), key=lambda i: cos[i], reverse=True), 1):
            if ok[i]:
                fused[i] += 1.0 / (RRF_K + r)

    best = max(fused) or 0.0
    ranked = sorted((i for i in range(len(chunks)) if fused[i] > 0), key=lambda i: fused[i], reverse=True)
    out = []
    for i in ranked[:top_k]:
        out.append({
            "page": chunks[i]["page"],
            "text": chunks[i]["text"],
            "score": round(100.0 * fused[i] / best, 2) if best else 0.0,
            "bm25": round(bm[i], 3),
            "dense": round(cos[i], 4) if cos is not None else None,
        })
    return out


# ---------------------------------------------------------------- LLM rerank

RERANK_PROMPT = """You rank passages from one academic paper by how directly they answer a question.
The question may be in Indonesian; the passages may be in another language. Judge meaning, not shared words.
Return ONLY JSON: {"order": [ids of the passages that help answer the question, best first]}"""


def _llm_rerank(question: str, texts: list[str], model: str = None) -> list[int]:
    from openai import OpenAI
    from .analyze import _parse_response

    listing = "\n\n".join(f"[{i}] {t[:600]}" for i, t in enumerate(texts, 1))
    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=model or config.LLM_MODEL,
        messages=[{"role": "system", "content": RERANK_PROMPT},
                  {"role": "user", "content": f"QUESTION: {question}\n\nPASSAGES:\n{listing}"}],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=60,
    )
    data = _parse_response(resp.choices[0].message.content or "")
    out = []
    for x in data.get("order") or []:
        m = re.search(r"\d+", str(x))
        if m and 1 <= int(m.group()) <= len(texts) and int(m.group()) - 1 not in out:
            out.append(int(m.group()) - 1)
    return out


def confident(hits: list[dict]) -> bool:
    """True when the top hit is a clear winner, so the LLM rerank would add nothing.

    Needs BM25 to put it first by a margin of 1.3x over the runner-up and, when
    embeddings are on, the embedding to rank it first as well.
    """
    if len(hits) < 2:
        return True
    top, second = hits[0], hits[1]
    if top["bm25"] <= 0 or top["bm25"] < 1.3 * second["bm25"]:
        return False
    if top["dense"] is not None and top["dense"] < max(h["dense"] for h in hits if h["dense"] is not None):
        return False
    return True


def _cached_order(question: str, texts: list[str], model: str, ranker) -> list[int]:
    """The LLM order for these passages, from the disk cache when the same call was made before."""
    if ranker is not None:
        return ranker(question, texts, model)
    from . import llmcache

    k = llmcache.key("rerank", model or config.LLM_MODEL, [RERANK_PROMPT, question, texts])
    cached = llmcache.get(k)
    if cached is not None:
        return list(cached)
    order = _llm_rerank(question, texts, model)
    llmcache.put(k, order)
    return order


def rerank(question: str, hits: list[dict], model: str = None, ranker=None) -> list[dict]:
    """Reorder search() hits with the LLM. Hits it leaves out keep their order after the chosen ones.

    On any error the original order is returned unchanged.
    """
    if len(hits) < 2:
        return hits
    if ranker is None and not config.RERANK_ALWAYS and confident(hits):
        return hits
    try:
        order = _cached_order(question, [h["text"] for h in hits], model, ranker)
    except Exception:
        return hits
    chosen = [hits[i] for i in order]
    rest = [h for i, h in enumerate(hits) if i not in order]
    for h in chosen:
        h["reranked"] = True
    return chosen + rest
