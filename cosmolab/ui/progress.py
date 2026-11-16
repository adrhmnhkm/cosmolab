"""Live progress boxes for long dashboard jobs: importing a paper (DOI or upload) and AI analysis.

A box shows one overall bar and a checklist of steps. Each step is waiting, running (with live
details such as megabytes downloaded or tokens written), done, or failed. The import and
analysis functions report their steps through on_step(event, info); the handlers below turn
those events into box updates.
"""

from __future__ import annotations

import time

import streamlit as st

from cosmolab import analyze as _analyze
from cosmolab import config

_ICON = {
    "todo": ":gray[:material/radio_button_unchecked:]",
    "run": ":blue[:material/autorenew:]",
    "ok": ":green[:material/check_circle:]",
    "fail": ":red[:material/cancel:]",
    "skip": ":gray[:material/remove_circle_outline:]",
}

# Steps of an AI analysis, appended to an import or used alone. The AI step carries most of the weight.
ANALYSIS_STEPS = [("ai", "AI menganalisis naskah", 6.0), ("hasil", "Simpan hasil analisis", 0.5)]


def _mb(n) -> str:
    return f"{(n or 0) / 1_048_576:.1f} MB"


def _text_size(info: dict) -> str:
    pages = info.get("pages")
    return (f"{pages} halaman · " if pages else "") + f"{info.get('chars', 0):,} karakter"


def _secs(s) -> str:
    s = int(s or 0)
    return f"{s // 60} mnt {s % 60} dtk" if s >= 60 else f"{s} dtk"


class StepProgress:
    """A bordered box with an overall progress bar and one line per step."""

    def __init__(self, title: str, steps: list[tuple[str, str, float]]):
        self.order = [k for k, _, _ in steps]
        self.steps = {k: {"label": label, "weight": w, "state": "todo", "detail": "", "frac": 0.0}
                      for k, label, w in steps}
        self.t0 = time.monotonic()
        self._shown = 0.0
        self._final = None
        with st.container(border=True):
            st.markdown(f"**{title}**")
            self._bar = st.progress(0.0, text="Mulai...")
            self._list = st.empty()
        self._render(force=True)

    # State changes -----------------------------------------------------------
    def run(self, key: str, detail: str = "", frac: float | None = None):
        if key in self.steps:
            s = self.steps[key]
            started = s["state"] != "run"
            s["state"], s["detail"] = "run", detail or s["detail"]
            if frac is not None:
                s["frac"] = max(0.0, min(frac, 1.0))
            # A step that just started always shows; live counters are throttled.
            self._render(force=started or frac is None)

    def ok(self, key: str, detail: str = ""):
        self._set(key, "ok", detail)

    def fail(self, key: str, detail: str = ""):
        self._set(key, "fail", detail)

    def skip(self, key: str, detail: str = ""):
        self._set(key, "skip", detail)

    def fail_current(self, detail: str):
        """Mark the step that was running (or the first unfinished one) as failed."""
        key = next((k for k in self.order if self.steps[k]["state"] == "run"), None) \
            or next((k for k in self.order if self.steps[k]["state"] == "todo"), None)
        if key:
            self.fail(key, detail)
        self._final = ("fail", detail)
        self._render(force=True)

    def finish(self, text: str):
        for k in self.order:
            if self.steps[k]["state"] == "todo":
                self.steps[k]["state"] = "skip"
        self._final = ("ok", text)
        self._render(force=True)

    def _set(self, key: str, state: str, detail: str):
        if key in self.steps:
            self.steps[key]["state"] = state
            if detail:
                self.steps[key]["detail"] = detail
            self._render(force=True)

    # Drawing -----------------------------------------------------------------
    def _render(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self._shown < 0.2:
            return
        self._shown = now
        total = sum(s["weight"] for s in self.steps.values()) or 1.0
        done = 0.0
        for s in self.steps.values():
            if s["state"] in ("ok", "skip"):
                done += s["weight"]
            elif s["state"] == "run":
                done += s["weight"] * s["frac"]
        pct = done / total
        elapsed = _secs(now - self.t0)
        if self._final and self._final[0] == "ok":
            pct, text = 1.0, f"Selesai dalam {elapsed}: {self._final[1]}"
        elif self._final:
            text = f"Berhenti setelah {elapsed}: {self._final[1]}"
        else:
            running = next((self.steps[k]["label"] for k in self.order if self.steps[k]["state"] == "run"), "Menyiapkan")
            text = f"{int(pct * 100)}% · {running} · {elapsed}"
        self._bar.progress(min(max(pct, 0.0), 1.0), text=text)
        lines = []
        for k in self.order:
            s = self.steps[k]
            label = f"**{s['label']}**" if s["state"] == "run" else s["label"]
            lines.append(f"{_ICON[s['state']]} {label}" + (f" · {s['detail']}" if s["detail"] else ""))
        self._list.markdown("  \n".join(lines))


# Event handlers --------------------------------------------------------------

def import_steps(source: str) -> list[tuple[str, str, float]]:
    """Steps of importing one paper. source: "doi" or "upload"."""
    if source == "doi":
        return [("cari", "Cari versi terbuka di Unpaywall", 1.0), ("pdf", "Unduh PDF", 2.0), ("teks", "Ambil teks PDF", 1.0)]
    return [("pdf", "Simpan PDF", 0.5), ("teks", "Ambil teks PDF", 1.0), ("penulis", "Cari nama penulis", 1.0)]


def import_handler(sp: StepProgress):
    """on_step for harvest.import_by_doi and harvest.import_local_pdf."""
    def on_step(event: str, info: dict):
        if event == "cari":
            sp.run("cari", f"DOI {info.get('doi')}")
        elif event == "ketemu":
            sp.ok("cari", f"{(info.get('title') or '')[:70]} ({info.get('year') or 'tahun?'})")
            sp.run("pdf", f"dari {info.get('host')}")
        elif event == "unduh":
            done, total = info.get("done") or 0, info.get("total")
            sp.run("pdf", f"{_mb(done)} dari {_mb(total)} · {info.get('host')}" if total else
                   f"{_mb(done)} · {info.get('host')}", frac=(done / total) if total else 0.5)
        elif event == "simpan":
            sp.run("pdf", _mb(info.get("size")))
        elif event == "ekstrak":
            if sp.steps.get("pdf", {}).get("state") == "run":
                sp.ok("pdf")
            sp.run("teks", "membaca halaman PDF")
        elif event == "ekstrak_ok":
            sp.ok("teks", _text_size(info))
        elif event == "ekstrak_gagal":
            sp.fail("teks", info.get("error", ""))
        elif event == "penulis":
            sp.run("penulis", "Crossref, OpenAlex, lalu AI membaca halaman pertama")
        elif event == "penulis_ok":
            names = info.get("names") or []
            if names:
                sp.ok("penulis", ", ".join(names[:3]) + (" dkk." if len(names) > 3 else ""))
            else:
                sp.skip("penulis", "tidak ditemukan, isi manual di Koleksi paper")
    return on_step


def analysis_handler(sp: StepProgress):
    """on_step for analyze.analyze_single_paper."""
    state = {"model": config.LLM_MODEL, "base": None}

    def on_step(event: str, info: dict):
        if event == "baca":
            if "teks" in sp.steps and sp.steps["teks"]["state"] != "ok":
                sp.ok("teks", _text_size(info))
            sp.run("ai", "menyiapkan naskah")
        elif event == "kirim":
            state["model"] = info.get("model") or state["model"]
            note = " (naskah dipotong ke bagian inti)" if info.get("trimmed") else ""
            sp.run("ai", f"{state['model']} membaca ~{info.get('input_tokens', 0):,} token{note}", frac=0.02)
        elif event == "pikir":
            # Thinking has no known length; creep toward 30% so the bar keeps moving.
            tokens = info.get("tokens", 0)
            sp.run("ai", f"{state['model']} berpikir dulu · {tokens:,} token · {_secs(info.get('elapsed'))}",
                   frac=0.02 + 0.28 * tokens / (tokens + 1500))
        elif event == "token":
            tokens, expected = info.get("tokens", 0), info.get("expected") or 1
            if state["base"] is None:  # writing starts where thinking left the bar
                state["base"] = max(sp.steps["ai"]["frac"], 0.03)
            base = state["base"]
            sp.run("ai", f"{state['model']} menulis {tokens:,} dari ~{expected:,} token · {_secs(info.get('elapsed'))}",
                   frac=min(base + (0.98 - base) * tokens / expected, 0.98))
        elif event == "ulang":
            state["base"] = None
            sp.run("ai", f":orange[coba lagi {info.get('attempt')}/{info.get('max')} dalam {info.get('wait')} dtk: "
                         f"{info.get('error')}]", frac=0.0)
        elif event == "selesai":
            sp.ok("ai", f"{state['model']} · {info.get('tokens', 0):,} token · {_secs(info.get('elapsed'))}")
        elif event == "simpan":
            sp.run("hasil", "menyimpan dan memperbarui koleksi")
        elif event == "beres":
            tokens = info.get("tokens")
            sp.ok("hasil", f"total {tokens:,} token" if isinstance(tokens, int) else "tersimpan")
    return on_step


def analyze_with_progress(file_name: str, title: str = "", lang: str = "id", force: bool = True,
                          sp: StepProgress | None = None) -> bool:
    """Analyze one paper inside a progress box. Shows the error in the box and returns False on failure."""
    sp = sp or StepProgress(f"Analisis AI: {(title or file_name)[:80]}", [("teks", "Baca teks paper", 0.5)] + ANALYSIS_STEPS)
    try:
        _analyze.analyze_single_paper(file_name, lang=lang, force=force, on_step=analysis_handler(sp))
    except Exception as err:
        sp.fail_current(str(err)[:200])
        st.error(f"Analisis gagal: {err}. Coba lagi, atau ganti AI di sidebar.")
        return False
    sp.finish("analisis tersimpan")
    return True
