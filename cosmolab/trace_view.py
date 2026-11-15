"""
cosmolab.trace_view
~~~~~~~~~~~~~~~~~~~
Draws a recorded source search (cosmolab.trace) in the terminal, step by step.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from . import passages

SOURCE_STYLE = {"ai": "green", "cache": "cyan", "dilewati": "dim", "fallback": "yellow",
                "peta konsep": "yellow", "pertanyaan apa adanya": "yellow"}


def _first(events, stage):
    return next((e for e in events if e["stage"] == stage), None)


def _src(source: str) -> str:
    return f"[{SOURCE_STYLE.get(source, 'white')}]{source}[/]"


def _name(titles: dict, f: str, n: int = 60) -> str:
    t = titles.get(f) or f or ""
    return t if len(t) <= n else t[: n - 3] + "..."


def _question(console, question: str):
    words = passages._WORD.findall(question.lower())
    text = Text()
    for w in words:
        if w in passages.STOP or (len(w) < 3 and not w.isdigit()):
            text.append(w, style="dim strike")
        else:
            t = passages._stem(w)
            style = "magenta" if t in passages.FILLER else "yellow" if t in passages.GENERIC else "bold green"
            text.append(w if t == w else f"{w}→{t}", style=style)
        text.append("  ")
    console.print(Panel(text, title="1. Pertanyaan dipecah jadi kata", border_style="cyan",
                        subtitle="[bold green]spesifik[/]  [yellow]umum (GENERIC)[/]  "
                                 "[magenta]kata tanya (FILLER)[/]  [dim strike]dibuang (STOP)[/]"))


def _fts(console, events, titles):
    fts = [e for e in events if e["stage"] == "fts"][:2]
    if not fts:
        return
    w = fts[0]["weights"]
    console.print(Rule("2. Cari paper di database (SQLite FTS5 + BM25)"))
    console.print("[dim]Bobot kolom: " + ", ".join(f"{k} {v:g}" for k, v in w.items())
                  + ". Teks asli paper lebih berat daripada ringkasan AI. Skor makin besar makin cocok.[/dim]")
    for label, e in zip(("kueri asli", "kueri ekspansi"), fts):
        tbl = Table(title=f"{label}: {e['fts_query'][:90]}  [dim]({e['mode']})[/dim]",
                    show_lines=False, border_style="blue", title_justify="left")
        tbl.add_column("#", justify="right", width=3)
        tbl.add_column("Paper")
        tbl.add_column("Tahun", width=6)
        tbl.add_column("BM25", justify="right", width=9)
        for i, r in enumerate(e["results"][:10], 1):
            titles.setdefault(r["file"], r.get("title"))
            # SQLite gives bm25 as a negative number (lower is better); shown flipped.
            tbl.add_row(str(i), _name(titles, r["file"]), str(r.get("year") or ""), f"{-r['rank']:.2f}")
        if not e["results"]:
            tbl.add_row("-", "[red]tidak ada paper yang cocok[/red]", "", "")
        console.print(tbl)


def _expand(console, events):
    e = _first(events, "expand")
    if not e:
        return
    console.print(Rule("3. Ekspansi kueri (istilah akademik bahasa Inggris)"))
    line = f"Asal: {_src(e['source'])}  Istilah: [bold]{', '.join(e['terms'])}[/bold]"
    if e.get("error"):
        line += f"\n[yellow]AI gagal: {e['error']}[/yellow]"
    console.print(line)


def _rrf(console, events, titles):
    e = _first(events, "rrf")
    if not e:
        return
    console.print(Rule(f"4. Gabung dua daftar dengan RRF  (skor = 1/(k+peringkat), k={e['k']:g}, "
                       f"bobot ekspansi {e['expansion_weight']:g})"))
    tbl = Table(border_style="blue")
    tbl.add_column("#", justify="right", width=3)
    tbl.add_column("Paper")
    tbl.add_column("Pkt asli", justify="right", width=8)
    tbl.add_column("Pkt ekspansi", justify="right", width=12)
    tbl.add_column("Skor RRF", justify="right", width=9)
    for i, r in enumerate(e["rows"][:12], 1):
        titles.setdefault(r["file"], r.get("title"))
        style = "" if r["kept"] else "dim"
        tbl.add_row(str(i), _name(titles, r["file"]), str(r["raw"] or "-"), str(r["expanded"] or "-"),
                    f"{r['score']:.4f}", style=style)
    console.print(tbl)
    if len(e["rows"]) > e["limit"]:
        console.print(f"[dim]{e['limit']} teratas diteruskan; {len(e['rows']) - e['limit']} lainnya berhenti di sini.[/dim]")


def _rerank_papers(console, events, titles):
    e = _first(events, "rerank_papers")
    if not e:
        return
    console.print(Rule("5. AI memilih paper yang benar-benar menjawab (rerank)"))
    head = f"Asal: {_src(e['source'])}"
    if e.get("model"):
        head += f"  Model: {e['model']}"
    if e.get("reason"):
        head += f"  [dim]({e['reason']})[/dim]"
    if e.get("error"):
        head += f"\n[yellow]AI gagal, urutan RRF dipakai apa adanya: {e['error']}[/yellow]"
    console.print(head)
    chosen = e.get("chosen") or []
    rows = e.get("candidates") or [{"file": f, "passage": ""} for f in chosen]
    tbl = Table(border_style="blue", show_lines=True)
    tbl.add_column("Status", width=10)
    tbl.add_column("Paper", width=40)
    tbl.add_column("Pasase yang dilihat AI", style="dim")
    for c in rows:
        f = c["file"]
        if f in chosen:
            status = f"[green]dipilih #{chosen.index(f) + 1}[/green]"
        elif e["source"] == "fallback":
            status = "[dim]di luar top_k[/dim]"
        else:
            status = "[red]ditolak AI[/red]"
        tbl.add_row(status, _name(titles, f), c.get("passage") or "[i](tidak ada pasase cocok)[/i]")
    console.print(tbl)


def _papers(console, events, titles):
    # Passage searches after the paper rerank are the ones that pick the evidence.
    start = next((i for i, e in enumerate(events) if e["stage"] == "rerank_papers"), -1) + 1
    later = events[start:]
    found = {}
    for e in later:
        if e["stage"] in ("passages", "passage_rerank") and e.get("file"):
            found.setdefault(e["file"], {})[e["stage"]] = e
    if not found:
        return
    console.print(Rule("6. Di dalam tiap paper: chunking, bobot kata, gerbang, skor pasase"))
    for f, parts in found.items():
        tree = Tree(f"[bold]{_name(titles, f, 80)}[/bold]")
        p = parts.get("passages")
        if p:
            tree.add(f"Dipotong jadi [bold]{p['chunks']}[/bold] chunk (paragraf, atau jendela ±600 karakter "
                     f"bila paragraf > 900 karakter)")
            terms = tree.add("Bobot kata di BM25 (k1=1.4, b=0.75)")
            for t in sorted(p["terms"], key=lambda t: -t["weight"])[:12]:
                tag = " [magenta]FILLER[/]" if t["filler"] else " [yellow]GENERIC[/]" if t["generic"] else ""
                src = "pertanyaan" if t["weight"] == 1.0 else "ekspansi"
                idf = f"idf {t['idf']:g}" if t["idf"] else "[red]tidak ada di paper ini[/red]"
                terms.add(f"{t['term']}  bobot {t['weight']:g} ({src})  {idf}{tag}")
            if p["bigrams"]:
                tree.add(f"Bonus frasa (+25% per frasa, maks 3): {', '.join(p['bigrams'][:6])}")
            gate = tree.add(f"Gerbang relevansi: [bold]{p['passed']}[/bold] dari {p['chunks']} chunk lolos")
            for why, n in sorted(p["reasons"].items(), key=lambda x: -x[1]):
                gate.add(f"{n} lewat {why}")
            if p["generic_only"]:
                gate.add("[yellow]Pertanyaan hanya berisi kata umum: cocok bila 2 kata umum ada bersama[/yellow]")
            if not p["dense_on"]:
                gate.add("[dim]Embedding mati: hanya kecocokan kata[/dim]")
            top = tree.add("Pasase teratas (skor fusi RRF dari BM25" + (" + dense" if p["dense_on"] else "") + ")")
            for h in p["top"][:4]:
                extra = f" ×{h['boost']:g} frasa" if h["boost"] != 1.0 else ""
                dense = f" dense {h['dense']:.2f}" if h["dense"] is not None else ""
                top.add(f"[yellow]hal. {h['page']}[/yellow] skor {h['score']:g}  bm25 {h['bm25']:g}{extra}{dense}"
                        f"  [dim]({h['why']})[/dim]\n[italic]{h['text']}[/italic]")
            if not p["top"]:
                tree.add("[red]Tidak ada pasase yang lolos gerbang[/red]")
        r = parts.get("passage_rerank")
        if r:
            if r["source"] == "ai":
                tree.add(f"Rerank pasase oleh AI: urutan halaman {r['before']} → {r['chosen']}"
                         + (f", ditolak {r['rejected']}" if r["rejected"] else ""))
            else:
                tree.add(f"Rerank pasase: {_src(r['source'])} [dim]{r.get('reason') or r.get('error') or ''}[/dim]")
        console.print(tree)


def _select(console, events, titles):
    e = _first(events, "select")
    if not e:
        return
    titles.update({k: v for k, v in (e.get("titles") or {}).items() if v})
    console.print(Rule("7. Sumber yang dipakai untuk menjawab"))
    tbl = Table(border_style="green", show_lines=True)
    tbl.add_column("Status", width=10)
    tbl.add_column("Paper", width=40)
    tbl.add_column("Bukti verbatim (halaman asli PDF)")
    for f in e["kept"]:
        ev = "\n".join(f"[yellow]hal. {p['page']}[/yellow] {p['text']}" for p in e["passages"].get(f, []))
        tbl.add_row("[green]dipakai[/green]", _name(titles, f), ev)
    for f in e["dropped"]:
        tbl.add_row("[red]dibuang[/red]", _name(titles, f), "[dim]tidak ada pasase teks asli yang cocok[/dim]")
    console.print(tbl)
    if not e["kept"]:
        console.print("[bold yellow]Hasil: \"Tidak ditemukan di korpus ini\". AI tidak dipanggil untuk menjawab.[/bold yellow]")


_LIVE = {
    "fts": lambda e: f"cari paper di database: {len(e['results'])} hasil",
    "expand": lambda e: f"ekspansi kueri ({e['source']}): {', '.join(e['terms'])[:80]}",
    "rrf": lambda e: f"gabung RRF: {len(e['rows'])} paper",
    "rerank_papers": lambda e: f"rerank paper ({e['source']}): {len(e['chosen'])} dipilih",
    "passages": lambda e: f"pasase {e['file'][:45]}: {e['passed']}/{e['chunks']} chunk lolos",
    "passage_rerank": lambda e: f"rerank pasase {e['file'][:45]} ({e['source']})",
    "select": lambda e: f"selesai: {len(e['kept'])} paper dipakai, {len(e['dropped'])} dibuang",
}


def live(console: Console):
    """A trace listener that prints one line per recorded step, so a slow AI call shows where it waits."""
    def show(e):
        fmt = _LIVE.get(e["stage"])
        if fmt:
            err = f"  [yellow]{e['error'][:70]}[/yellow]" if e.get("error") else ""
            console.print(f"[dim]{e['t']:6.1f}s[/dim]  {fmt(e)}{err}")
    return show


def render(events: list[dict], question: str, console: Console | None = None):
    console = console or Console()
    titles: dict = {}
    _question(console, question)
    _fts(console, events, titles)
    _expand(console, events)
    _rrf(console, events, titles)
    _rerank_papers(console, events, titles)
    _papers(console, events, titles)
    _select(console, events, titles)
    if events:
        console.print(f"[dim]Total waktu pencarian: {events[-1]['t']:.1f} detik, {len(events)} langkah tercatat.[/dim]")
