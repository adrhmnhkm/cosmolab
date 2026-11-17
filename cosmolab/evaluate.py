"""
cosmolab.evaluate
~~~~~~~~~~~~~~~~~
Evaluation set: measure how accurate retrieval and the claim checker are on
the researcher's own collection.

The gold file (<root>/eval/gold.jsonl) holds one test item per line:

  {"id": "r1", "kind": "retrieval", "question": "...", "file": "x.pdf", "pages": [3], "reviewed": false}
  {"id": "c1", "kind": "claim", "claim": "...", "file": "x.pdf", "expected": "didukung", "reviewed": false}
  {"id": "n1", "kind": "negative", "question": "...", "reviewed": true}
  {"id": "ab1", "kind": "abstain", "question": "...", "reviewed": true}
  {"id": "a1", "kind": "ask", "question": "...", "file": "x.pdf", "reviewed": true}

Retrieval items are scored twice: is the right page among the passages of the
right paper, and is the right paper among the sources an answer would use.
Negative items are questions the collection does not cover; the system should
find no source for them. Without negative items in the file, a few
off-topic questions (NEGATIVE_DEFAULTS) are used.

`draft_gold()` writes a first draft from the collection with the LLM. The
researcher should read it and set "reviewed": true on items that are correct.
`run()` scores the current system and saves the result under eval/runs/,
so changes can be compared over time.
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime

from . import config

KINDS = ("retrieval", "claim", "negative", "abstain", "ask")
SOURCES_K = 5  # papers an answer uses (ask: top_k=5)

# Questions no academic collection here should answer. Override with "negative" items in gold.jsonl.
NEGATIVE_DEFAULTS = [
    "Bagaimana cara menanam selada hidroponik dengan sistem NFT di rumah?",
    "Berapa dosis vaksin rabies yang dianjurkan untuk kucing peliharaan?",
    "Bagaimana cara mengganti oli mesin sepeda motor matic?",
    "Resep rendang daging sapi yang empuk dan tahan lama",
    "Berapa harga tiket kereta Jakarta ke Surabaya bulan depan?",
]


def eval_dir():
    return config.ROOT / "eval"


def gold_path():
    return eval_dir() / "gold.jsonl"


def load_gold(path=None) -> list[dict]:
    path = path or gold_path()
    items = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                items.append(json.loads(line))
    except FileNotFoundError:
        pass
    return items


def save_gold(items: list[dict], path=None) -> None:
    path = path or gold_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items), encoding="utf-8")


# --------------------------------------------------------------- drafting

DRAFT_PROMPT = """Kamu menyusun soal uji untuk sistem pencarian paper akademik.
Diberikan satu kutipan dari sebuah paper. Buat:
1. "question": satu pertanyaan Bahasa Indonesia yang jawabannya ada di kutipan. Pakai kata-kata sendiri, jangan menyalin frasa kutipan.
2. "true_claim": satu kalimat Bahasa Indonesia yang benar menurut kutipan.
3. "false_claim": satu kalimat Bahasa Indonesia yang mirip, tetapi salah menurut kutipan (ubah angka, arah hubungan, atau kesimpulan).
Jawab HANYA JSON: {"question": "...", "true_claim": "...", "false_claim": "..."}"""

_BIBLIO = re.compile(r"(\bdoi\b|https?://|\bvol\.|\bpp\.|et al\.|\(\d{4}\)\s*\d+[-–]\d+|Phys\. Rev)", re.I)


def _pick_passage(file_name: str, rng: random.Random) -> dict | None:
    from . import extract, passages

    chunks = passages.chunk_pages(extract.get_paper_pages(file_name))
    good = [c for c in chunks if 250 <= len(c["text"]) <= 900 and not _BIBLIO.search(c["text"])]
    if not good:
        return None
    # Skip the first page when possible: questions about the abstract are too easy.
    later = [c for c in good if c["page"] > 1] or good
    return rng.choice(later)


def _llm_draft(passage: str, model: str = None) -> dict:
    from openai import OpenAI
    from .analyze import _parse_response

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=model or config.DRAFT_MODEL or config.LLM_MODEL,
        messages=[{"role": "system", "content": DRAFT_PROMPT}, {"role": "user", "content": passage}],
        response_format={"type": "json_object"},
        temperature=0.3,
        timeout=90,
    )
    return _parse_response(resp.choices[0].message.content or "")


def draft_gold(n_papers: int = 10, model: str = None, seed: int = 7, drafter=None, papers=None,
               progress_cb=None, include_ask: bool = False, include_abstain: bool = False) -> list[dict]:
    """Add draft items for up to n_papers papers that are not in the gold set yet.

    Each paper gives 1 retrieval item and 2 claim items (one true, one false).
    If include_ask is True, also adds an end-to-end ask item.
    If include_abstain is True, adds abstain test questions.
    Returns the new items; they are also appended to gold.jsonl.
    """
    import warnings
    from . import db

    draft_model = model or config.DRAFT_MODEL or config.LLM_MODEL
    if draft_model and config.JUDGE_MODEL and draft_model == config.JUDGE_MODEL:
        warnings.warn(
            f"Model pembuat draf ({draft_model}) sama dengan JUDGE_MODEL. "
            "Disarankan menggunakan model berbeda (set DRAFT_MODEL) untuk menghindari bias evaluasi."
        )

    drafter = drafter or _llm_draft
    rng = random.Random(seed)
    gold = load_gold()
    used = {it.get("file") for it in gold}
    if papers is None:
        papers = db.get_all_papers_with_analyses()
    pool = [p for p in papers if p.get("file") and p["file"] not in used]
    rng.shuffle(pool)

    new, next_id = [], len(gold) + 1
    done = 0
    for p in pool:
        if done >= n_papers:
            break
        psg = _pick_passage(p["file"], rng)
        if not psg:
            continue
        try:
            d = drafter(psg["text"], draft_model)
        except Exception:
            continue
        if not d.get("question"):
            continue
        base = {"file": p["file"], "title": p.get("title") or p["file"], "page": psg["page"],
                "passage": psg["text"], "reviewed": False, "source": "auto"}
        new.append({"id": f"r{next_id}", "kind": "retrieval", "question": d["question"],
                    "pages": [psg["page"]], **base})
        if d.get("true_claim"):
            new.append({"id": f"c{next_id}a", "kind": "claim", "claim": d["true_claim"], "expected": "didukung", **base})
        if d.get("false_claim"):
            new.append({"id": f"c{next_id}b", "kind": "claim", "claim": d["false_claim"],
                        "expected": "tidak_didukung", **base})
        if include_ask:
            new.append({"id": f"a{next_id}", "kind": "ask", "question": d["question"], **base})
        next_id += 1
        done += 1
        if progress_cb:
            progress_cb(done, n_papers, p.get("title") or p["file"])

    if include_abstain:
        for i, q in enumerate(NEGATIVE_DEFAULTS[:n_papers], 1):
            if not any(it.get("kind") == "abstain" and it.get("question") == q for it in gold + new):
                new.append({"id": f"ab{next_id}", "kind": "abstain", "question": q,
                            "reviewed": True, "source": "auto"})
                next_id += 1

    save_gold(gold + new)
    return new


# --------------------------------------------------------------- scoring

def _retrieval_hit(item: dict, k: int, expand: bool, model=None, rerank: bool = False) -> dict:
    from . import retrieval

    extra = ""
    if expand:
        try:
            extra = " ".join(retrieval.expand_academic_query(item["question"], model=model))
        except Exception:
            extra = ""
    hits = retrieval.find_grounded_passages(item["file"], item["question"], top_k=k, max_length=700,
                                            extra_terms=extra, rerank=rerank, model=model)
    pages = [h["page"] for h in hits if not h.get("fallback")]
    want = set(item.get("pages") or [])
    rank = next((i for i, pg in enumerate(pages, 1) if pg in want), None)
    return {"id": item["id"], "hit": rank is not None, "rank": rank, "got_pages": pages}


def _sources(question: str, expand: bool, model, rerank: bool) -> list[str]:
    from . import retrieval

    # Reranking passages only reorders them inside a paper; it never decides which paper stays.
    # Skipping it gives the same sources with up to SOURCES_K fewer AI calls per question.
    with _no_passage_rerank():
        papers, _ = retrieval.select_sources(question, top_k=SOURCES_K, model=model, expand=expand, rerank=rerank)
    return [p.get("file") for p in papers]


class _no_passage_rerank:
    def __enter__(self):
        self._old = config.RERANK_PASSAGES
        config.RERANK_PASSAGES = False

    def __exit__(self, *exc):
        config.RERANK_PASSAGES = self._old


def ai_reachable(timeout: float = 5.0) -> str | None:
    """None when the AI server answers, else the reason. Checked before a run, so a stopped
    local server does not turn every claim into a failure."""
    import urllib.request

    url = config.LLM_BASE_URL.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {config.LLM_API_KEY or 'x'}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return None
    except Exception as e:
        return f"AI tidak bisa dihubungi di {config.LLM_BASE_URL}: {str(e)[:120]}"


def run(k: int = 3, expand: bool = True, rerank: bool = True, reviewed_only: bool = False, model: str = None,
        judge=None, evidence_fn=None, items: list[dict] | None = None, save: bool = True,
        limit: int | None = None, progress_cb=None,
        ask_fn=None, ask_agent_fn=None, check_answer_fn=None) -> dict:
    """Score retrieval (recall@k, MRR) and the claim checker (accuracy) on the gold set.

    limit: at most this many items of each kind (a quicker, lighter run).
    progress_cb(text) is called before each step.
    """
    from . import db, entail

    say = progress_cb or (lambda text: None)
    items = load_gold() if items is None else items
    if reviewed_only:
        items = [it for it in items if it.get("reviewed")]
    if limit:
        kept, seen = [], {}
        for it in items:
            seen[it.get("kind")] = seen.get(it.get("kind"), 0) + 1
            if seen[it.get("kind")] <= limit:
                kept.append(it)
        items = kept

    ret_items = [it for it in items if it.get("kind") == "retrieval"]
    ret_rows = []
    for n, it in enumerate(ret_items, 1):
        say(f"halaman {n}/{len(ret_items)}")
        try:
            ret_rows.append(_retrieval_hit(it, k, expand, model, rerank))
        except Exception as e:
            ret_rows.append({"id": it["id"], "hit": False, "rank": None, "error": str(e)[:120]})
    n_ret = len(ret_rows)
    recall = sum(r["hit"] for r in ret_rows) / n_ret if n_ret else None
    mrr = sum(1.0 / r["rank"] for r in ret_rows if r["rank"]) / n_ret if n_ret else None

    # Is the right paper among the sources an answer would use?
    src_rows = []
    for n, it in enumerate(ret_items, 1):
        say(f"sumber {n}/{len(ret_items)}")
        try:
            got = _sources(it["question"], expand, model, rerank)
            rank = next((i for i, f in enumerate(got, 1) if f == it.get("file")), None)
            src_rows.append({"id": it["id"], "hit": rank is not None, "rank": rank, "n_sources": len(got)})
        except Exception as e:
            src_rows.append({"id": it["id"], "hit": False, "rank": None, "n_sources": 0, "error": str(e)[:120]})
    n_src = len(src_rows)

    # Questions the collection does not cover: no source should be found.
    neg_items = [it for it in items if it.get("kind") == "negative"]
    if not neg_items:
        neg_items = [{"id": f"n{i}", "question": q} for i, q in enumerate(NEGATIVE_DEFAULTS, 1)]
        if limit:
            neg_items = neg_items[:limit]
    neg_rows = []
    for n, it in enumerate(neg_items, 1):
        say(f"di luar topik {n}/{len(neg_items)}")
        try:
            got = _sources(it["question"], expand, model, rerank)
            neg_rows.append({"id": it["id"], "ok": not got, "sources": got})
        except Exception as e:
            neg_rows.append({"id": it["id"], "ok": False, "sources": [], "error": str(e)[:120]})

    # Questions the system should abstain from ("tidak ditemukan")
    abstain_items = [it for it in items if it.get("kind") == "abstain"]
    abstain_rows = []
    if abstain_items:
        say(f"cek {len(abstain_items)} soal abstain")
        ask_call = ask_fn
        if ask_call is None:
            from . import ask as _ask
            ask_call = _ask.ask
        agent_call = ask_agent_fn
        if agent_call is None:
            from . import ask_agent as _agent
            agent_call = _agent.ask_agentic

        for n, it in enumerate(abstain_items, 1):
            say(f"abstain {n}/{len(abstain_items)}")
            q = it["question"]
            try:
                c_res = ask_call(q, model=model)
                c_text = c_res if isinstance(c_res, str) else (c_res.get("answer", "") if isinstance(c_res, dict) else str(c_res))
                c_ok = bool(re.search(r"tidak\s+ditemukan", c_text, re.I))
            except Exception as e:
                c_text, c_ok = f"error: {e}", False

            try:
                a_res = agent_call(q, model=model)
                a_text = a_res if isinstance(a_res, str) else (a_res.get("answer", "") if isinstance(a_res, dict) else str(a_res))
                a_ok = bool(re.search(r"tidak\s+ditemukan", a_text, re.I))
            except Exception as e:
                a_text, a_ok = f"error: {e}", False

            abstain_rows.append({
                "id": it["id"],
                "question": q,
                "classic_ok": c_ok,
                "classic_answer": c_text[:160],
                "agentic_ok": a_ok,
                "agentic_answer": a_text[:160],
                "ok": c_ok and a_ok,
            })
    n_ab = len(abstain_rows)
    abstain_rate = (sum(r["ok"] for r in abstain_rows) / n_ab) if n_ab else None
    classic_rate = (sum(r["classic_ok"] for r in abstain_rows) / n_ab) if n_ab else None
    agentic_rate = (sum(r["agentic_ok"] for r in abstain_rows) / n_ab) if n_ab else None

    # End-to-end ask questions evaluated with entail.check_answer
    ask_items = [it for it in items if it.get("kind") == "ask"]
    ask_rows = []
    if ask_items:
        say(f"cek {len(ask_items)} soal ask end-to-end")
        ask_call = ask_fn
        if ask_call is None:
            from . import ask as _ask
            ask_call = _ask.ask
        agent_call = ask_agent_fn
        if agent_call is None:
            from . import ask_agent as _agent
            agent_call = _agent.ask_agentic
        checker = check_answer_fn
        if checker is None:
            from . import entail as _entail
            checker = _entail.check_answer

        for n, it in enumerate(ask_items, 1):
            say(f"ask end-to-end {n}/{len(ask_items)}")
            q = it["question"]
            try:
                c_res = ask_call(q, model=model)
                c_text = c_res if isinstance(c_res, str) else (c_res.get("answer", "") if isinstance(c_res, dict) else str(c_res))
                c_rep = checker(c_text, judge=judge, evidence_fn=evidence_fn)
                c_cls = c_rep.get("claims", [])
                c_tot = len(c_cls)
                c_supp = sum(1 for cl in c_cls if cl.get("verdict") == entail.SUPPORTED)
                c_att = entail.needs_attention(c_rep)
                c_uncited = sum(1 for cl in c_cls if cl.get("verdict") == entail.NO_CITATION)
            except Exception as e:
                c_text, c_cls, c_tot, c_supp, c_att, c_uncited = f"error: {e}", [], 0, 0, 0, 0

            try:
                a_res = agent_call(q, model=model)
                a_text = a_res if isinstance(a_res, str) else (a_res.get("answer", "") if isinstance(a_res, dict) else str(a_res))
                a_rep = checker(a_text, judge=judge, evidence_fn=evidence_fn)
                a_cls = a_rep.get("claims", [])
                a_tot = len(a_cls)
                a_supp = sum(1 for cl in a_cls if cl.get("verdict") == entail.SUPPORTED)
                a_att = entail.needs_attention(a_rep)
                a_uncited = sum(1 for cl in a_cls if cl.get("verdict") == entail.NO_CITATION)
            except Exception as e:
                a_text, a_cls, a_tot, a_supp, a_att, a_uncited = f"error: {e}", [], 0, 0, 0, 0

            ask_rows.append({
                "id": it["id"],
                "question": q,
                "file": it.get("file"),
                "classic": {
                    "answer": c_text[:200],
                    "total_claims": c_tot,
                    "supported_claims": c_supp,
                    "attention_claims": c_att,
                    "uncited_claims": c_uncited,
                    "grounded_ratio": (c_supp / c_tot) if c_tot else None,
                },
                "agentic": {
                    "answer": a_text[:200],
                    "total_claims": a_tot,
                    "supported_claims": a_supp,
                    "attention_claims": a_att,
                    "uncited_claims": a_uncited,
                    "grounded_ratio": (a_supp / a_tot) if a_tot else None,
                },
            })

    c_tot_all = sum(r["classic"]["total_claims"] for r in ask_rows)
    c_supp_all = sum(r["classic"]["supported_claims"] for r in ask_rows)
    c_att_all = sum(r["classic"]["attention_claims"] for r in ask_rows)
    c_unc_all = sum(r["classic"]["uncited_claims"] for r in ask_rows)

    a_tot_all = sum(r["agentic"]["total_claims"] for r in ask_rows)
    a_supp_all = sum(r["agentic"]["supported_claims"] for r in ask_rows)
    a_att_all = sum(r["agentic"]["attention_claims"] for r in ask_rows)
    a_unc_all = sum(r["agentic"]["uncited_claims"] for r in ask_rows)

    ask_summary = {
        "n": len(ask_rows),
        "classic": {
            "grounded_ratio": (c_supp_all / c_tot_all) if c_tot_all else None,
            "total_claims": c_tot_all,
            "supported_claims": c_supp_all,
            "attention_claims": c_att_all,
            "uncited_claims": c_unc_all,
        },
        "agentic": {
            "grounded_ratio": (a_supp_all / a_tot_all) if a_tot_all else None,
            "total_claims": a_tot_all,
            "supported_claims": a_supp_all,
            "attention_claims": a_att_all,
            "uncited_claims": a_unc_all,
        },
        "rows": ask_rows,
    }

    claim_items = [it for it in items if it.get("kind") == "claim"]
    if claim_items:
        say(f"cek {len(claim_items)} klaim")
    by_file = {p["file"]: p for p in (db.get_all_papers_with_analyses() if claim_items else [])}
    checked = entail.check_claims(
        [{"text": it["claim"], "paper": by_file.get(it["file"]) or {"file": it["file"], "title": it.get("title")}}
         for it in claim_items],
        # The claim checker runs on its own server with JUDGE_MODEL; `model` is the main AI used for retrieval.
        # use_analysis=False: judge against the paper's own text only, not the AI-generated summary.
        model=None, judge=judge, evidence_fn=evidence_fn, use_analysis=False,
    ) if claim_items else []
    claim_rows, confusion = [], {}
    for it, row in zip(claim_items, checked):
        got = row["verdict"]
        expected = it.get("expected")
        ok = got == expected  # "sebagian" counts as wrong for both kinds
        failed = got == entail.UNCHECKED and "gagal" in (row.get("reason") or "")
        claim_rows.append({"id": it["id"], "expected": expected, "got": got, "ok": ok, "reason": row["reason"],
                           "failed": failed})
        if not failed:
            confusion.setdefault(expected, {}).setdefault(got, 0)
            confusion[expected][got] += 1
    # A claim the AI never judged (server down, timeout) says nothing about accuracy: left out, reported.
    judged = [r for r in claim_rows if not r["failed"]]
    n_claim = len(judged)
    accuracy = sum(r["ok"] for r in judged) / n_claim if n_claim else None
    false_caught = [r for r in judged if r["expected"] == "tidak_didukung"]
    true_passed = [r for r in judged if r["expected"] == "didukung"]

    result = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "settings": {"k": k, "expand": expand, "rerank": rerank, "reviewed_only": reviewed_only, "model": model or config.LLM_MODEL,
                     "embed_model": config.EMBED_MODEL or None},
        "retrieval": {"n": n_ret, "recall_at_k": recall, "mrr": mrr, "rows": ret_rows},
        "sources": {"n": n_src, "k": SOURCES_K,
                    "recall": sum(r["hit"] for r in src_rows) / n_src if n_src else None,
                    "mrr": sum(1.0 / r["rank"] for r in src_rows if r["rank"]) / n_src if n_src else None,
                    "avg_sources": sum(r["n_sources"] for r in src_rows) / n_src if n_src else None,
                    "rows": src_rows},
        "negatives": {"n": len(neg_rows),
                      "rejected": sum(r["ok"] for r in neg_rows) / len(neg_rows) if neg_rows else None,
                      "rows": neg_rows},
        "abstain": {
            "n": n_ab,
            "abstain_rate": abstain_rate,
            "classic_rate": classic_rate,
            "agentic_rate": agentic_rate,
            "rows": abstain_rows,
        },
        "ask": ask_summary,
        "claims": {
            "n": n_claim, "failed": len(claim_rows) - n_claim, "accuracy": accuracy, "confusion": confusion,
            "rows": claim_rows,
            # Share of false claims the checker flags, and of true claims it lets through.
            "false_caught": (sum(r["ok"] for r in false_caught) / len(false_caught)) if false_caught else None,
            "true_passed": (sum(r["ok"] for r in true_passed) / len(true_passed)) if true_passed else None,
        },
    }
    if save:
        try:
            from . import audit, entail as _e

            audit.log("evaluasi", model=result["settings"]["model"], n_retrieval=n_ret, n_claims=n_claim,
                      prompt_version=audit.prompt_version(_e.JUDGE_PROMPT, _e.TERMS_PROMPT),
                      summary={"recall_at_k": recall, "mrr": mrr, "claim_accuracy": accuracy,
                               "abstain_rate": abstain_rate,
                               "ask_classic_grounded": ask_summary["classic"]["grounded_ratio"],
                               "ask_agentic_grounded": ask_summary["agentic"]["grounded_ratio"]}, k=k)
        except Exception:
            pass
        out = eval_dir() / "runs"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{datetime.now():%Y%m%d_%H%M%S}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def history(limit: int = 20) -> list[dict]:
    """Summaries of past runs, newest first."""
    out = []
    for path in sorted((eval_dir() / "runs").glob("*.json"), reverse=True)[:limit]:
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "file": path.name, "time": r.get("time"),
            "recall_at_k": r["retrieval"]["recall_at_k"], "mrr": r["retrieval"]["mrr"],
            "claim_accuracy": r["claims"]["accuracy"], "false_caught": r["claims"].get("false_caught"),
            "true_passed": r["claims"].get("true_passed"), "k": r["settings"]["k"],
            "source_recall": (r.get("sources") or {}).get("recall"),
            "negatives_rejected": (r.get("negatives") or {}).get("rejected"),
            "abstain_rate": (r.get("abstain") or {}).get("abstain_rate"),
            "ask_classic_grounded": ((r.get("ask") or {}).get("classic") or {}).get("grounded_ratio"),
            "ask_agentic_grounded": ((r.get("ask") or {}).get("agentic") or {}).get("grounded_ratio"),
            "embed_model": r["settings"].get("embed_model"),
        })
    return out
