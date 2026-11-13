"""Paper labels, badges, analysis detail, and the researcher review panel."""

import json
from datetime import datetime
import streamlit as st
from cosmolab import config
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab import authors as _authors
from cosmolab import entail as _entail
from cosmolab import analysis_check as _acheck
from cosmolab import corrections as _corrections
from cosmolab import metadata as _metadata
from cosmolab import sinta as _sinta
from cosmolab.ui.components import _e
from cosmolab.ui.components import _badge
from cosmolab.ui.claims import CLAIM_TONES


# Friendly Labels & Classes
STANCE_LABELS = {
    "supports": "Mendukung",
    "critiques": "Mengkritik",
    "mixed": "Campuran",
    "neutral": "Netral",
}


TYPE_LABELS = {
    "kalam": "Kalam",
    "contingency": "Kontingensi",
    "first-cause": "Sebab Pertama (Aquinas)",
    "fine-tuning": "Penyetelan Sempurna (Fine-Tuning)",
    "mixed": "Campuran",
    "empiris_kuantitatif": "Empiris kuantitatif",
    "kualitatif_studi_kasus": "Kualitatif / studi kasus",
    "yuridis_normatif": "Yuridis normatif",
    "kajian_literatur": "Kajian literatur",
    "filosofis_rasional": "Filosofis rasional",
    "konseptual_teoretis": "Konseptual teoretis",
    "komparatif": "Komparatif",
    "other": "Lainnya",
}


# Argument types that are reasoning chains, so premises are shown as P1, P2, ...
ARGUMENT_TYPES = {"kalam", "contingency", "first-cause", "fine-tuning", "filosofis_rasional"}


def _is_argument_paper(p: dict) -> bool:
    """Philosophy/theology papers and reasoning-type analyses get a formal premise view."""
    if (p.get("argument_type") or "") in ARGUMENT_TYPES:
        return True
    fac = _faculties.get_faculty(p.get("faculty") or "ilahiyyat")
    return bool(fac and fac.category == "Filosofis & Teologis")


STANCE_TONES = {"supports": "good", "critiques": "bad", "mixed": "mix", "neutral": "muted"}


EMPIRICAL_TYPES = {"empiris_kuantitatif", "kualitatif_studi_kasus", "komparatif"}


REASONING_TYPES = ARGUMENT_TYPES | {"konseptual_teoretis", "mixed"}


def _type_tone(arg_t: str) -> str:
    if arg_t in EMPIRICAL_TYPES:
        return "info"
    if arg_t in REASONING_TYPES:
        return "teal"
    return "muted"


SINTA_TONES = {1: "good", 2: "good", 3: "info", 4: "info", 5: "muted", 6: "muted"}


def sinta_ranks() -> dict:
    """file -> SINTA entry, cached per session. Pop '_sinta_ranks' after the list changes."""
    if "_sinta_ranks" not in st.session_state:
        st.session_state["_sinta_ranks"] = _sinta.ranks_by_file()
    return st.session_state["_sinta_ranks"]


def paper_badges(p: dict) -> str:
    """Status, stance, study type, and warnings that need the researcher's attention."""
    out = []
    analyzed = bool(p.get("thesis"))
    out.append(_badge("Sudah dianalisis", "muted") if analyzed else _badge("Belum dianalisis", "warn"))
    if analyzed:
        stn = p.get("supports_or_critiques") or "neutral"
        out.append(_badge(STANCE_LABELS.get(stn, stn), STANCE_TONES.get(stn, "muted")))
        arg_t = p.get("argument_type") or ""
        if arg_t and arg_t not in ("other", "unclassified"):
            out.append(_badge(TYPE_LABELS.get(arg_t, arg_t), _type_tone(arg_t)))
    sinta = sinta_ranks().get(p.get("file") or "")
    if sinta:
        out.append(_badge(_sinta.label(sinta), SINTA_TONES.get(sinta["rank"], "muted")))
    meta = _meta_store().get(p.get("file") or "") or {}
    serious = [n["label"] for n in meta.get("notices", []) if n.get("serious")]
    if serious:
        out.append(_badge(serious[0], "bad"))
    elif meta.get("status") == _metadata.INVALID:
        out.append(_badge("DOI tidak terdaftar", "bad"))
    elif meta.get("status") == _metadata.DIFF:
        out.append(_badge("Metadata beda dengan Crossref", "warn"))
    if analyzed:
        sc = _acheck.score(_acheck.load_check(p.get("file") or ""))
        if sc.get("checked"):
            tone = "good" if not sc["flagged"] else "warn"
            out.append(_badge(f"Cek PDF: {sc['supported']}/{sc['statements']} didukung", tone))
    if not _authors.as_list(p.get("authors")):
        out.append(_badge("Penulis belum diketahui", "warn"))
    elif p.get("authors_source") == "pdf_ai":
        out.append(_badge("Penulis dibaca AI, mohon dicek", "warn"))
    try:
        age = datetime.now().year - int(str(p.get("year") or "")[:4])
        if age > 10:
            out.append(_badge(f"Terbit {age} tahun lalu", "muted"))
    except ValueError:
        pass
    return "<div class='cl-badges'>" + "".join(out) + "</div>"


def _numbered_list(items: list, prefix: str = "") -> str:
    rows = "".join(f"<li data-label='{prefix}{i}'>{_e(str(x))}</li>" for i, x in enumerate(items, 1) if str(x).strip())
    return f"<ol class='an-list'>{rows}</ol>"


def render_analysis_detail(p: dict):
    """Analysis of one paper, laid out by paper kind: argument papers show premises,
    empirical papers show method and findings."""
    try:
        raw = json.loads(p.get("raw_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        raw = {}
    try:
        premises = json.loads(p.get("premises_json") or "[]") or []
    except (TypeError, json.JSONDecodeError):
        premises = []
    try:
        quotes = json.loads(p.get("quotes_json") or "[]") or []
    except (TypeError, json.JSONDecodeError):
        quotes = []
    method = raw.get("research_method")
    findings = [f for f in (raw.get("key_findings") or []) if isinstance(f, str) and f.strip()]
    is_arg = _is_argument_paper(p)
    arg_t = p.get("argument_type") or ""

    if not (p.get("thesis") or premises or findings):
        st.caption("Paper ini belum dianalisis. Tekan tombol Analisis di atas untuk mengisi bagian ini.")
        st.markdown(f"<div class='an-foot'>Sumber data: {_e(p.get('source') or 'web')} · File: {_e(p.get('file') or '')}</div>",
                    unsafe_allow_html=True)
        return

    facts = []
    if method:
        facts.append(("Metode riset", method))
    if arg_t and arg_t != "other":
        facts.append(("Jenis kajian", _badge(TYPE_LABELS.get(arg_t, arg_t), _type_tone(arg_t))))
    stn = p.get("supports_or_critiques") or "neutral"
    facts.append(("Sikap terhadap topik", _badge(STANCE_LABELS.get(stn, "Netral"), STANCE_TONES.get(stn, "muted"))))
    if p.get("doi"):
        facts.append(("DOI", p["doi"]))
    else:
        facts.append(("DOI", _badge("Tidak ada DOI, cek sumber sebelum dikutip", "warn")))
    st.markdown(
        "<div class='an-facts'>" + "".join(
            f"<div class='an-fact{' wide' if k == 'Metode riset' else ''}'><div class='an-fact-label'>{_e(k)}</div>"
            f"<div class='an-fact-value'>{v if str(v).startswith('<span') else _e(str(v))}</div></div>"
            for k, v in facts) + "</div>",
        unsafe_allow_html=True,
    )

    if is_arg and premises:
        st.markdown("<div class='an-section'>Rekonstruksi premis</div>"
                    "<div class='an-section-note'>Langkah penalaran penulis menuju kesimpulan.</div>"
                    + _numbered_list(premises, "P"), unsafe_allow_html=True)
        if findings:
            st.markdown("<div class='an-section'>Temuan utama</div>" + _numbered_list(findings), unsafe_allow_html=True)
    elif findings:
        st.markdown("<div class='an-section'>Temuan utama</div>"
                    "<div class='an-section-note'>Dari bagian hasil dan pembahasan.</div>"
                    + _numbered_list(findings), unsafe_allow_html=True)
    elif premises:
        st.markdown("<div class='an-section'>Alur argumen</div>" + _numbered_list(premises), unsafe_allow_html=True)

    if p.get("conclusion"):
        st.markdown(f"<div class='an-section'>Kesimpulan</div><div class='an-conclusion'>{_e(p['conclusion'])}</div>",
                    unsafe_allow_html=True)

    boxes = []
    if p.get("key_objection"):
        label = "Keberatan terkuat" if is_arg else "Kritik atau keterbatasan"
        boxes.append(f"<div class='an-box critique'><b>{label}</b>{_e(p['key_objection'])}</div>")
    if p.get("key_defense"):
        boxes.append(f"<div class='an-box defense'><b>Tanggapan penulis</b>{_e(p['key_defense'])}</div>")
    if boxes:
        st.markdown("<div class='an-section'>Kritik dan tanggapan</div><div class='an-pair'>" + "".join(boxes) + "</div>",
                    unsafe_allow_html=True)

    if quotes:
        q_html = []
        for q in quotes:
            if not isinstance(q, dict) or not q.get("text"):
                continue
            hint = q.get("page_hint") or ""
            src = f"<div class='an-quote-src'>{_e(hint)}</div>" if hint else ""
            q_html.append(f"<div class='an-quote'><div class='an-quote-text'>&ldquo;{_e(q['text'])}&rdquo;</div>{src}</div>")
        if q_html:
            st.markdown("<div class='an-section'>Kutipan kunci</div>" + "".join(q_html), unsafe_allow_html=True)

    st.markdown(f"<div class='an-foot'>Sumber data: {_e(p.get('source') or 'web')} · File: {_e(p.get('file') or '')}</div>",
                unsafe_allow_html=True)


REVIEW_TONES = {"benar": "good", "salah": "bad", "diedit": "info"}


def _meta_store() -> dict:
    if "_meta_store" not in st.session_state:
        st.session_state["_meta_store"] = _metadata.load_store()
    return st.session_state["_meta_store"]


def _statement_label(field: str, index) -> str:
    label = _acheck.FIELD_LABELS.get(field, field)
    return f"{label} {index + 1}" if index is not None else label


def render_analysis_review(p: dict, key: str):
    """Check one analysis against the PDF text, and let the researcher mark or edit each statement."""
    f = p.get("file")
    if not f:
        return
    analysis = _acheck.load_analysis(f)
    if not analysis:
        return
    report = _acheck.load_check(f)
    reviews = _corrections.load(f)
    head = st.columns([4, 1])
    with head[0]:
        if report:
            sc = _acheck.score(report)
            st.caption(
                f"Dicek {sc['time'][:16].replace('T', ' ')}: {sc['supported']} dari {sc['statements']} pernyataan "
                f"didukung teks paper, {sc['quotes_found']} dari {sc['quotes']} kutipan ada di PDF."
            )
        else:
            st.caption("Belum dicek. AI membandingkan setiap pernyataan analisis dengan teks PDF, sekitar 1 menit.")
    with head[1]:
        if st.button("Cek ulang" if report else "Cek ke PDF", key=f"acheck_{key}", width="stretch"):
            with st.spinner("Membandingkan analisis dengan teks PDF..."):
                try:
                    report = _acheck.check_paper(f, model=config.LLM_MODEL)
                except Exception as e:
                    st.error(f"Cek gagal: {e}")

    by_key = {_corrections.key_of(r["field"], r["index"]): r for r in (report or {}).get("statements", [])}
    for n, s in enumerate(_acheck.statements(analysis)):
        k = _corrections.key_of(s["field"], s["index"])
        r = by_key.get(k)
        if r and r.get("text") != s["text"]:
            r = None  # the check was made on an older analysis
        rev = reviews.get(k)
        stale = bool(rev) and _corrections.is_stale(rev, analysis, k)
        badges = []
        if r:
            badges.append(_badge(_entail.VERDICT_LABELS[r["verdict"]], CLAIM_TONES[r["verdict"]]))
        if rev and not stale:
            badges.append(_badge(_corrections.LABELS[rev["status"]], REVIEW_TONES[rev["status"]]))
        if stale:
            badges.append(_badge("Koreksi lama, analisis sudah berubah", "warn"))
        shown = rev["value"] if rev and rev["status"] == _corrections.EDITED and not stale else s["text"]
        tone = REVIEW_TONES.get(rev["status"]) if rev and not stale else (CLAIM_TONES[r["verdict"]] if r else "muted")
        ev_html = ""
        if r and r.get("evidence"):
            e = r["evidence"][0]
            ev_html = (f"<div class='cl-claim-ev'><span class='cl-claim-page'>{_e(e.get('page_label', ''))}</span>"
                       f"&ldquo;{_e(e.get('text', '')[:360])}&rdquo;</div>")
        struck = " style='text-decoration:line-through;opacity:.6'" if rev and rev["status"] == _corrections.WRONG and not stale else ""
        st.markdown(
            f"<div class='cl-claim {tone}'><div>{''.join(badges)}</div>"
            f"<div class='cl-claim-src'>{_e(_statement_label(s['field'], s['index']))}</div>"
            f"<div class='cl-claim-text'{struck}>{_e(shown)}</div>"
            + (f"<div class='cl-claim-reason'>{_e(r['reason'])}</div>" if r and r.get("reason") else "")
            + (f"<div class='cl-claim-reason'>Catatan peneliti: {_e(rev['note'])}</div>" if rev and rev.get("note") else "")
            + ev_html + "</div>",
            unsafe_allow_html=True,
        )
        with st.popover("Koreksi", width="content", key=f"rv_p_{key}_{n}"):
            choice = st.radio("Penilaian peneliti", ["Benar", "Salah", "Edit"], horizontal=True, key=f"rv_c_{key}_{n}")
            new_text = None
            if choice == "Edit":
                new_text = st.text_area("Teks yang benar", value=shown, key=f"rv_t_{key}_{n}")
            note = st.text_input("Catatan (opsional)", key=f"rv_n_{key}_{n}")
            b1, b2 = st.columns(2)
            if b1.button("Simpan", key=f"rv_s_{key}_{n}", type="primary", width="stretch"):
                status = {"Benar": _corrections.CORRECT, "Salah": _corrections.WRONG, "Edit": _corrections.EDITED}[choice]
                try:
                    _corrections.set_review(f, s["field"], s["index"], status, value=new_text, note=note,
                                            by=st.session_state.get("team_user", ""), analysis=analysis)
                    db.sync_one(f)
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
            if rev and b2.button("Hapus koreksi", key=f"rv_d_{key}_{n}", width="stretch"):
                _corrections.clear_review(f, s["field"], s["index"])
                db.sync_one(f)
                st.rerun()

    quotes = (report or {}).get("quotes") or []
    if quotes:
        st.markdown("**Kutipan di analisis**")
        tones = {_acheck.QUOTE_FOUND: "good", _acheck.QUOTE_CLOSE: "warn", _acheck.QUOTE_MISSING: "bad"}
        for q in quotes:
            extra = ""
            if q.get("page"):
                extra = f" Ditemukan di halaman PDF {q['page']}."
                if q.get("page_ok") is False:
                    extra += f" Nomor halaman di analisis ({_e(q.get('page_hint') or '-')}) beda, mungkin memakai nomor cetak jurnal."
            st.markdown(
                f"<div class='cl-claim {tones[q['status']]}'><div>{_badge(_acheck.QUOTE_LABELS[q['status']], tones[q['status']])}</div>"
                f"<div class='cl-claim-text'>&ldquo;{_e((q.get('text') or '')[:400])}&rdquo;</div>"
                f"<div class='cl-claim-reason'>{_e(extra.strip())}</div></div>",
                unsafe_allow_html=True,
            )
