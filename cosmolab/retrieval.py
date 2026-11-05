"""
cosmolab.retrieval
~~~~~~~~~~~~~~~~~~
Advanced Retrieval Engine for CosmoLab:
- Semantic Concept Expansion (Multi-Query / Cross-Lingual Academic Bridge)
- Hybrid Reciprocal Rank Fusion (RRF)
- Micro Cross-Attention Re-ranking with Dialectical Balance
"""

import json
import re
from openai import OpenAI
from rich.console import Console
from . import config
from . import db

console = Console(force_terminal=True, legacy_windows=False)

# Heuristic domain mappings for instant zero-latency query expansion fallback
DOMAIN_CONCEPT_MAP = {
    "alam": ["temporal origin", "beginning of universe", "kalam cosmological argument", "cosmic inception"],
    "semesta": ["cosmic expansion", "physical cosmology", "multiverse", "big bang singularity"],
    "awal": ["temporal beginning", "finite past", "actual infinite", "creation ex nihilo"],
    "sebab": ["principle of sufficient reason", "causality", "efficient cause", "first cause"],
    "takdir": ["occasionalism", "determinism", "free will", "divine foreknowledge", "kasb"],
    "jahat": ["problem of evil", "theodicy", "gratuitous evil", "divine justice"],
    "penderitaan": ["soul-making theodicy", "existential suffering", "defense of theodicy"],
    "jiwa": ["philosophy of mind", "substance dualism", "flying man argument", "consciousness", "qualia"],
    "kontingensi": ["contingency argument", "necessary existence", "wajib al-wujud", "contingent beings"],
    "tak terhingga": ["actual infinite", "hilbert hotel", "cantorian set theory", "temporal regress"],
    "infinit": ["infinite regress", "potential infinite", "transfinite numbers", "successive addition"],
}


def expand_academic_query(query: str, client: OpenAI = None, model: str = None) -> list[str]:
    """Expand a user query (Indonesian, casual, or conceptual) into precise academic English keywords.
    
    Falls back to heuristic concept mapping if LLM API is unavailable.
    """
    model = model or config.LLM_MODEL
    try:
        if not client:
            client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)

        prompt = f"""Given this research query (any academic field):
"{query}"

Generate 3-5 concise, high-yield academic English search terms and phrases that would appear in journal paper titles, abstracts, or theses.
Return ONLY a valid JSON list of strings, for example: ["temporal origin", "kalam argument", "actual infinite"]"""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )
        content = (resp.choices[0].message.content or "").strip()
        # Parse JSON array from content
        m = re.search(r"\[.*\]", content, re.DOTALL)
        if m:
            terms = json.loads(m.group(0))
            if isinstance(terms, list) and terms:
                return [str(t).strip() for t in terms if str(t).strip()]
    except Exception:
        pass

    # Heuristic fallback
    q_lower = query.lower()
    fallback_terms = []
    for key, terms in DOMAIN_CONCEPT_MAP.items():
        if key in q_lower:
            fallback_terms.extend(terms[:2])

    return list(dict.fromkeys(fallback_terms)) if fallback_terms else [query]


def hybrid_search(
    query: str,
    limit: int = 10,
    expand_concepts: bool = True,
    client: OpenAI = None,
    model: str = None,
) -> list[dict]:
    """Execute hybrid retrieval combining exact weighted FTS5 with conceptual expansion via RRF.
    
    Uses Reciprocal Rank Fusion (RRF) to blend keyword precision with semantic breadth:
      RRF_score(d) = sum( 1.0 / (k + rank) )
    """
    # 1. Base weighted FTS5 on literal query
    raw_results = db.search(query, limit=limit * 2)

    if not expand_concepts:
        return raw_results[:limit]

    # 2. Extract conceptual academic keywords
    expanded_terms = expand_academic_query(query, client=client, model=model)
    if not expanded_terms:
        return raw_results[:limit]

    concept_query = " ".join(expanded_terms)
    expanded_results = db.search(concept_query, limit=limit * 2)

    # 3. Reciprocal Rank Fusion (k = 60 standard constant)
    k = 60.0
    scores = {}
    doc_map = {}

    # Accumulate scores from raw search (weight 1.0)
    for rank, doc in enumerate(raw_results, start=1):
        f = doc["file"]
        doc_map[f] = doc
        scores[f] = scores.get(f, 0.0) + (1.0 / (k + rank))

    # Accumulate scores from conceptual expansion (weight 1.2 for semantic boost)
    for rank, doc in enumerate(expanded_results, start=1):
        f = doc["file"]
        doc_map[f] = doc
        scores[f] = scores.get(f, 0.0) + (1.2 / (k + rank))

    # Sort merged papers by descending RRF score
    ranked_files = sorted(scores.keys(), key=lambda f: scores[f], reverse=True)
    merged_results = []
    for f in ranked_files[:limit]:
        item = dict(doc_map[f])
        item["rrf_score"] = round(scores[f], 5)
        merged_results.append(item)

    return merged_results


def rerank_papers(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    client: OpenAI = None,
    model: str = None,
) -> list[dict]:
    """Re-rank candidate papers using LLM micro cross-attention on theses and premises.
    
    Evaluates exact dialectical relevance to the research question:
    - Eliminates documents that only casually mention terms (name-dropping).
    - Prioritizes papers whose theses directly engage or refute the core premises.
    """
    if not candidates or len(candidates) <= top_k:
        return candidates

    model = model or config.LLM_MODEL
    if not client:
        client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)

    # Build concise candidate summaries for re-ranking prompt
    candidate_prompts = []
    for idx, c in enumerate(candidates, start=1):
        title = c.get("title") or "Untitled"
        year = c.get("year") or "n.d."
        thesis = c.get("thesis") or "N/A"
        stance = c.get("supports_or_critiques") or "neutral"
        premises = ""
        if c.get("premises_json"):
            try:
                p_list = json.loads(c["premises_json"])
                premises = " | ".join(p_list[:3])
            except Exception:
                premises = ""

        c_text = f"[{idx}] \"{title}\" ({year})\n   - Stance: {stance}\n   - Thesis: {thesis}"
        if premises:
            c_text += f"\n   - Key Premises: {premises}"
        candidate_prompts.append(c_text)

    prompt = f"""You are an expert academic research re-ranker.
Research Query: "{query}"

Evaluate the following candidate papers and rank the top {top_k} papers that most directly address, support, or refute the core argument or research problem in the query. Filter out papers that merely mention terms in passing.

Candidates:
{chr(10).join(candidate_prompts)}

Return ONLY a valid JSON list of integers representing the chosen candidate IDs in order of highest relevance, for example: [3, 1, 5, 2]"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        content = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\[[0-9,\s]+\]", content)
        if m:
            indices = json.loads(m.group(0))
            reranked = []
            seen = set()
            for i in indices:
                if 1 <= i <= len(candidates) and i not in seen:
                    item = dict(candidates[i - 1])
                    item["rerank_boost"] = True
                    reranked.append(item)
                    seen.add(i)

            # Fill in remaining candidates if any slots are left
            for idx, c in enumerate(candidates, start=1):
                if idx not in seen and len(reranked) < top_k:
                    reranked.append(c)

            return reranked
    except Exception as e:
        console.print(f"[dim yellow]Notice: Re-ranking fallback to hybrid order ({e})[/dim yellow]")

    return candidates[:top_k]
