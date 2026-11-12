"""Claim check on AI answers and its report."""

import streamlit as st
from cosmolab import config
from cosmolab import entail as _entail
from cosmolab.ui.components import _e
from cosmolab.ui.components import _badge


CLAIM_TONES = {
    _entail.SUPPORTED: "good",
    _entail.PARTIAL: "warn",
    _entail.UNSUPPORTED: "bad",
    _entail.NO_SOURCE: "bad",
    _entail.UNCHECKED: "muted",
}


CLAIM_ORDER = [_entail.UNSUPPORTED, _entail.NO_SOURCE, _entail.PARTIAL, _entail.UNCHECKED, _entail.SUPPORTED]


def run_claim_check(answer: str, numbered: list[dict] | None = None) -> dict | None:
    try:
        with st.spinner("Memeriksa setiap klaim terhadap isi paper..."):
            return _entail.check_answer(answer, model=config.LLM_MODEL, numbered=numbered)
    except Exception as e:
        st.warning(f"Pemeriksaan klaim gagal: {e}")
        return None


def render_claim_report(report: dict | None):
    """Show which cited sentences the sources back, and which need checking."""
    if not report:
        return
    total = report.get("total", 0)
    if not total:
        st.caption("Pemeriksaan klaim: jawaban ini tidak memuat kalimat bersitasi, jadi tidak ada yang bisa dicek.")
        return
    summary = report.get("summary", {})
    badges = " ".join(
        _badge(f"{summary[v]} {_entail.VERDICT_LABELS[v].lower()}", CLAIM_TONES[v])
        for v in CLAIM_ORDER if summary.get(v)
    )
    flagged = _entail.needs_attention(report)
    head = (f"{flagged} dari {total} klaim perlu dicek sebelum dikutip." if flagged
            else f"Semua {total} klaim bersitasi didukung isi paper.")
    st.markdown(
        f"<div class='cl-claim-sum'><div class='cl-claim-head'>Pemeriksaan klaim</div>"
        f"<div class='cl-claim-line'>{_e(head)}</div><div class='cl-claim-badges'>{badges}</div></div>",
        unsafe_allow_html=True,
    )
    if report.get("skipped"):
        st.caption(f"{report['skipped']} klaim terakhir tidak dicek karena batas jumlah klaim.")
    rows = sorted(report.get("claims", []), key=lambda c: (CLAIM_ORDER.index(c["verdict"]), c["id"]))
    with st.expander("Hasil cek per klaim", expanded=bool(flagged)):
        for c in rows:
            ev = [c["evidence"][i] for i in c.get("evidence_used", []) if i < len(c.get("evidence", []))]
            ev_html = "".join(
                f"<div class='cl-claim-ev'><span class='cl-claim-page'>{_e(e.get('page_label', ''))}</span>"
                f"&ldquo;{_e(e.get('text', '')[:400])}&rdquo;</div>"
                for e in ev[:2]
            )
            srcs = "; ".join(f"{x.get('title')} ({x.get('year') or 'n.d.'})" for x in c.get("papers", [])) \
                or "; ".join(c.get("citations", []))
            st.markdown(
                f"<div class='cl-claim {CLAIM_TONES[c['verdict']]}'>"
                f"<div>{_badge(_entail.VERDICT_LABELS[c['verdict']], CLAIM_TONES[c['verdict']])}</div>"
                f"<div class='cl-claim-text'>{_e(c['text'])}</div>"
                f"<div class='cl-claim-src'>Sumber: {_e(srcs)}</div>"
                + (f"<div class='cl-claim-reason'>{_e(c['reason'])}</div>" if c.get("reason") else "")
                + ev_html + "</div>",
                unsafe_allow_html=True,
            )
