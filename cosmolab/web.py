import json
import re
import importlib
import subprocess
import sys
import html
from datetime import datetime
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from cosmolab import config
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab import export
from cosmolab import ask as _ask
from cosmolab import ask_agent as _ask_agent
from cosmolab import sparring as _sparring
from cosmolab import curriculum as _curriculum
from cosmolab import harvest as _harvest
from cosmolab import extract as _extract
from cosmolab import analyze as _analyze
from cosmolab import authors as _authors
from cosmolab import synthesize as _synthesize
from cosmolab import writer as _writer
from cosmolab import matrix as _matrix
from cosmolab import citations as _citations
from cosmolab import gap_finder as _gap_finder
from cosmolab import inspector as _inspector
from cosmolab import retrieval as _retrieval
from cosmolab import verify as _verify
from cosmolab import deliverables as _deliverables
from cosmolab import snowball as _snowball
from cosmolab import entail as _entail
from cosmolab import analysis_check as _acheck
from cosmolab import corrections as _corrections
from cosmolab import metadata as _metadata
from cosmolab import evaluate as _evaluate
from cosmolab import audit as _audit

# Live hot-reloading of submodules inside Streamlit session
try:
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(_faculties)
    importlib.reload(_sparring)
    importlib.reload(_curriculum)
    importlib.reload(_ask_agent)
    importlib.reload(_writer)
    importlib.reload(_harvest)
    importlib.reload(_extract)
    importlib.reload(_analyze)
    importlib.reload(_synthesize)
    importlib.reload(_matrix)
    importlib.reload(_citations)
    importlib.reload(_gap_finder)
    importlib.reload(_inspector)
    importlib.reload(_verify)
    importlib.reload(_deliverables)
    importlib.reload(_retrieval)
    importlib.reload(_entail)
    importlib.reload(_audit)
    importlib.reload(_corrections)
    importlib.reload(_acheck)
    importlib.reload(_metadata)
    importlib.reload(_evaluate)
except Exception:
    pass

# Logo files live in cosmolab/assets/
ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_MARK_PNG = ASSETS_DIR / "logo-mark.png"
LOGO_LIGHT_PNG = ASSETS_DIR / "logo-light.png"


def _svg_data_uri(path: Path) -> str:
    import base64
    try:
        return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


LOGO_MARK_URI = _svg_data_uri(ASSETS_DIR / "logo-mark.svg")

# Page Configuration
st.set_page_config(
    page_title="CosmoLab • Asisten Riset Multidisipliner",
    page_icon=str(LOGO_MARK_PNG) if LOGO_MARK_PNG.exists() else ":material/menu_book:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _require_team_login():
    """In team mode (`cosmolab ui --team`), ask for the team password before showing anything."""
    import hmac
    import os
    import time
    if os.environ.get("COSMOLAB_TEAM_MODE") != "1" or st.session_state.get("team_auth_ok"):
        return
    if LOGO_LIGHT_PNG.exists():
        st.image(str(LOGO_LIGHT_PNG), width=300)
    st.markdown("### Masuk tim")
    if not config.TEAM_PASSWORD:
        st.error("Password tim belum diatur di server. Hubungi admin tim.")
        st.stop()
    tries = st.session_state.get("team_auth_tries", 0)
    with st.form("team_login"):
        pw = st.text_input("Password tim", type="password")
        submitted = st.form_submit_button("Masuk")
    if submitted:
        if tries >= 5:
            time.sleep(min(30, 2 ** (tries - 4)))  # slow down repeated guesses
        if hmac.compare_digest(pw.encode("utf-8"), config.TEAM_PASSWORD.encode("utf-8")):
            st.session_state["team_auth_ok"] = True
            st.rerun()
        st.session_state["team_auth_tries"] = tries + 1
        st.error("Password salah.")
    st.stop()


_require_team_login()


def _e(value) -> str:
    """Escape text from papers, AI output or users before it goes into raw HTML."""
    return html.escape("" if value is None else str(value))


def _safe_url(url) -> str:
    """Allow only http(s) links in raw HTML."""
    url = str(url or "")
    return html.escape(url) if url.lower().startswith(("http://", "https://")) else "#"

# -------------------------------------------------------------
# Modern Design System & CSS
# -------------------------------------------------------------
# The stylesheet lives in cosmolab/assets/theme.css.
st.markdown(
    "\n<style>\n" + (ASSETS_DIR / "theme.css").read_text(encoding="utf-8") + "</style>\n",
    unsafe_allow_html=True,
)


_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF][\uFE0F\u200D]*[ ]?")


def render_table(rows: list[dict], height: int | None = None, hide_index: bool = True):
    """Show rows as a dataframe in the CosmoLab style: white cells, soft zebra rows, no emoji."""
    import pandas as pd

    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = df[col].map(lambda v: _EMOJI_RE.sub("", v).strip() if isinstance(v, str) else v)

    def _zebra(row):
        bg = "#FFFFFF" if row.name % 2 == 0 else "#F4F8F7"
        return [f"background-color: {bg}; color: #2F4440"] * len(row)

    styled = df.reset_index(drop=True).style.apply(_zebra, axis=1)
    kwargs = {"use_container_width": True, "hide_index": hide_index}
    if height:
        kwargs["height"] = height
    st.dataframe(styled, **kwargs)


def render_hero(title: str, subtitle: str, icon: str = "", badges: list = None):
    """Render modern high-impact hero masthead banner."""
    badge_html = ""
    if badges:
        items = []
        for b in badges:
            b_class = b.get("class", "hero-badge-primary")
            b_icon = b.get("icon", "")
            b_text = b.get("text", "")
            items.append(f'<span class="hero-badge {b_class}">{b_text}</span>')
        badge_html = f'<div class="cosmo-hero-badges">{" ".join(items)}</div>'

    html = f"""
    <div class="cosmo-hero">
        <div class="cosmo-hero-title">
            {title}
        </div>
        <div class="cosmo-hero-subtitle">{subtitle}</div>
        {badge_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_mermaid(code: str, height: int = 450):
    """Render Mermaid diagram inside Streamlit with modern frame."""
    html_code = f"""
    <div style="background: #FFFFFF; padding: 18px; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
      <pre class="mermaid" style="display: flex; justify-content: center;">
{code}
      </pre>
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    if hasattr(st, "iframe"):
        st.iframe(html_code, height=height)
    else:
        components.html(html_code, height=height, scrolling=True)


def render_client_delivery(md_path: Path, key: str):
    """Citation check + Word/PDF export with firm letterhead for one Markdown result."""
    st.markdown("##### Kirim ke Klien (Word / PDF berkop firma)")
    st.caption(
        "Sitasi diperiksa dulu ke koleksi proyek dan Crossref. Dokumen hanya dibuat kalau semua sitasi "
        "terverifikasi, atau peneliti menyatakan sudah memeriksa manual."
    )
    state_key = f"verify_report_{key}"
    col_v1, col_v2 = st.columns([1, 1])
    online = col_v2.toggle("Cek online ke Crossref", value=True, key=f"online_{key}")
    if col_v1.button("Periksa Sitasi", key=f"verify_btn_{key}", use_container_width=True):
        with st.spinner("Memeriksa rujukan..."):
            st.session_state[state_key] = _verify.verify_file(md_path, online=online)
            _verify.save_report(st.session_state[state_key])

    report = st.session_state.get(state_key)
    if report is None or report.source != str(md_path):
        return

    rows = [
        {"Rujukan": r.raw[:140], "Status": _verify.LABELS[r.status], "Catatan": (r.note + (f" DOI: {r.doi}" if r.doi else "")).strip()}
        for r in report.references
    ] + [
        {"Rujukan": f"(teks) {c.text}", "Status": _verify.LABELS[c.status], "Catatan": c.note}
        for c in report.citations if c.status != _verify.CITE_OK
    ]
    if rows:
        render_table(rows)
    else:
        st.info("Tidak ada daftar rujukan atau kutipan yang terdeteksi di dokumen ini.")

    if report.ok:
        st.success("Semua sitasi terverifikasi.")
        manual_ok = True
    else:
        st.warning(f"{len(report.blocking)} sitasi belum terverifikasi otomatis. Periksa manual sebelum dikirim.")
        manual_ok = st.checkbox(
            "Saya sudah memeriksa manual semua sitasi yang ditandai dan menyetujuinya.",
            key=f"manual_{key}",
        )

    reviewer = st.text_input("Nama peneliti pemeriksa (tercantum di dokumen):", key=f"reviewer_{key}")
    title_override = st.text_input("Judul dokumen (kosongkan untuk memakai judul artikel):", key=f"title_{key}")
    if st.button("Buat Word & PDF", key=f"deliver_btn_{key}", type="primary",
                 disabled=not (manual_ok and reviewer.strip()), use_container_width=True):
        try:
            with st.spinner("Menyusun dokumen klien..."):
                result = _deliverables.deliver(
                    md_path, reviewer=reviewer, title=title_override or None,
                    online=report.online, allow_unverified=manual_ok,
                )
            st.session_state[f"deliver_files_{key}"] = [str(f) for f in result["files"]]
        except Exception as e:
            st.error(f"Gagal membuat dokumen: {e}")

    for f in st.session_state.get(f"deliver_files_{key}", []):
        fp = Path(f)
        if fp.exists():
            mime = "application/pdf" if fp.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            st.download_button(f"Unduh {fp.suffix[1:].upper()}: {fp.name}", data=fp.read_bytes(),
                               file_name=fp.name, mime=mime, key=f"dl_{key}_{fp.suffix}", use_container_width=True)


# -------------------------------------------------------------
# Sidebar - University Header, Faculty Filter & Campus Stats
# -------------------------------------------------------------
st.sidebar.markdown("""
<div class="sidebar-brand-card">
    <div class="sidebar-brand-title">
        {mark}<span>Cosmo<span class="sidebar-brand-lab">Lab</span></span>
    </div>
    <div class="sidebar-brand-sub">Asisten riset multidisipliner</div>
</div>
""".format(mark=f'<img class="sidebar-brand-mark" src="{LOGO_MARK_URI}" alt="">' if LOGO_MARK_URI else ""),
    unsafe_allow_html=True)

# Active client project (set per dashboard process via `cosmolab -P <proyek> ui`)
_proj = config.project_info()
if config.PROJECT:
    _client = f" · {_proj['client']}" if _proj.get("client") else ""
    st.sidebar.info(f"Proyek: **{config.PROJECT}**{_client}")
else:
    st.sidebar.warning("Data utama (bukan proyek klien)")

# Faculty Filter in Sidebar
faculty_list = _faculties.list_faculties()
faculty_options = ["all"] + [f.id for f in faculty_list]
faculty_labels = {"all": "Semua bidang"}
for f in faculty_list:
    custom_tag = " [Kustom]" if getattr(f, "is_custom", False) else ""
    faculty_labels[f.id] = f"{f.name}{custom_tag}"

selected_faculty_id = st.sidebar.selectbox(
    "Bidang ilmu",
    faculty_options,
    format_func=lambda x: faculty_labels.get(x, x),
)

# Load DB papers
all_papers = db.get_all_papers_with_analyses()
if selected_faculty_id == "all":
    papers = all_papers
else:
    papers = [p for p in all_papers if p.get("faculty") == selected_faculty_id]

total_all = len(all_papers)
total_active = len(papers)
total_analyzed = len([p for p in papers if p.get("thesis")])

# One readable progress line instead of two cramped metric cards
st.sidebar.progress(
    total_analyzed / total_active if total_active else 0.0,
    text=f"{total_analyzed} dari {total_active} paper sudah dianalisis",
)

if "active_nav_menu" not in st.session_state:
    st.session_state["active_nav_menu"] = "Paper Explorer & Korpus"

def render_nav_item(label: str, target: str, badge: str = None, icon: str = None):
    is_active = (st.session_state["active_nav_menu"] == target)
    display_title = f"{label}  ·  {badge}" if badge else label
    if st.sidebar.button(
        display_title,
        key=f"nav_btn_{target}",
        type="primary" if is_active else "secondary",
        icon=icon,
        use_container_width=True
    ):
        st.session_state["active_nav_menu"] = target
        st.rerun()

# Menu follows the research workflow: collect, read, then ask and write.
st.sidebar.markdown("<div class='nav-cluster-header'>1 · Kumpulkan paper</div>", unsafe_allow_html=True)
render_nav_item("Cari & unduh paper", "Panen Paper Ilmiah", icon=":material/travel_explore:")
render_nav_item("Analisis dari DOI", "Bedah DOI Seketika", icon=":material/link:")

st.sidebar.markdown("<div class='nav-cluster-header'>2 · Baca & analisis</div>", unsafe_allow_html=True)
render_nav_item("Koleksi paper", "Paper Explorer & Korpus", str(total_active), icon=":material/library_books:")
render_nav_item("Cari kata di naskah", "Full-Text Search", icon=":material/search:")
render_nav_item("Diagram argumen", "Diagram Argumen", icon=":material/account_tree:")
render_nav_item("Periksa akurasi", "Pusat Akurasi", icon=":material/verified:")

st.sidebar.markdown("<div class='nav-cluster-header'>3 · Tanya & tulis</div>", unsafe_allow_html=True)
render_nav_item("Tanya Korpus (RAG)", "Tanya Korpus & Sintesis", icon=":material/forum:")
render_nav_item("Tulis artikel", "Studio Artikel Siap Baca", icon=":material/edit_note:")
render_nav_item("Laporan sintesis", "Laporan Sintesis", icon=":material/summarize:")

st.sidebar.markdown("<div class='nav-cluster-header'>Lainnya</div>", unsafe_allow_html=True)
render_nav_item("Kurikulum belajar", "Roadmap Belajar & Kurikulum", icon=":material/school:")
render_nav_item("Latihan debat", "Arena Sparring Nalar", icon=":material/record_voice_over:")
render_nav_item("Ekspor data", "Ekspor Data & Flashcards", icon=":material/ios_share:")

menu = st.session_state["active_nav_menu"]

st.sidebar.divider()

# Technical details live at the bottom, out of the researcher's way
from cosmolab import usage as _usage
_month = datetime.now().strftime("%Y-%m")
_u = _usage.summarize(_usage.load(config.ROOT, _month), by="month")
fac_dist = db.get_faculty_distribution()
with st.sidebar.expander("Info teknis", expanded=False):
    st.caption(f"Model AI: {config.LLM_MODEL}")
    if _u:
        _cost = _usage.format_money(_u[0]["cost"]) if _usage.pricing() else "tarif belum diisi"
        st.caption(f"Pemakaian AI bulan ini: {_u[0]['total_tokens']:,} token · {_u[0]['calls']} panggilan · {_cost}")
    st.caption("Paper per bidang:")
    for f in faculty_list:
        cnt = fac_dist.get(f.id, 0)
        if cnt:
            st.caption(f"{f.name}: {cnt}")


def render_snowball_tab():
    """Citation snowballing: papers cited by, or citing, the collection."""
    papers = db.get_all_papers_with_analyses()
    with st.container(border=True):
        st.caption(
            "Cari paper penting lewat jejak sitasi koleksi: rujukan yang dikutip paper koleksi (biasanya karya induk), "
            "dan paper baru yang mengutip koleksi. Data dari Semantic Scholar, cadangan OpenAlex."
        )
        if not papers:
            st.info("Koleksi masih kosong. Cari atau unggah paper dulu.")
            return
        labels = {p["file"]: f"{p.get('title') or p['file']} ({p.get('year') or 'n.d.'})" for p in papers}
        col_s1, col_s2 = st.columns([3, 2])
        with col_s1:
            picked = st.multiselect("Paper koleksi yang ditelusuri", list(labels), format_func=lambda f: labels[f],
                                    placeholder="Kosong = semua paper koleksi", key="sb_seeds")
        with col_s2:
            arah = st.radio("Arah", ["Keduanya", "Rujukan paper koleksi", "Paper yang mengutip koleksi"],
                            key="sb_arah")
        seeds = [p for p in papers if p["file"] in picked] if picked else papers
        directions = {"Keduanya": (_snowball.BACKWARD, _snowball.FORWARD),
                      "Rujukan paper koleksi": (_snowball.BACKWARD,),
                      "Paper yang mengutip koleksi": (_snowball.FORWARD,)}[arah]
        n_steps = len(seeds) * len(directions)
        secs = round(n_steps * 1.6)
        eta = f"{max(secs, 5)} detik" if secs < 60 else f"{round(secs / 60)} menit"
        st.caption(f"{len(seeds)} paper, {n_steps} penelusuran, sekitar {eta}.")
        if st.button("Telusuri sitasi", type="primary", width="stretch", key="btn_snowball"):
            bar = st.progress(0.0, text="Mulai menelusuri...")

            def _prog(i, n, seed, direction, count, src):
                bar.progress(i / n, text=f"{i}/{n} · {_snowball.DIRECTION_LABELS[direction]} · "
                                         f"{(seed.get('title') or '')[:50]} · {count} paper")

            res = _snowball.snowball(seeds, papers, directions=directions, progress=_prog)
            bar.empty()
            st.session_state["sb_result"] = res

    res = st.session_state.get("sb_result")
    if not res:
        return
    cands = res["candidates"]
    if not cands:
        st.info("Tidak ada kandidat baru. Semua paper yang terhubung sudah ada di koleksi.")
        return

    import pandas as pd

    st.markdown(f"##### {len(cands)} kandidat baru")
    st.caption("Diurutkan dari yang terhubung ke paling banyak paper koleksi, lalu jumlah sitasinya. "
               "Centang paper yang mau diunduh.")
    rows = [{
        "Pilih": False,
        "Judul": c["title"],
        "Tahun": c["year"],
        "Terhubung ke": c["link_count"],
        "Sitasi": c["citations"],
        "Arah": ", ".join(_snowball.DIRECTION_LABELS[d] for d in c["directions"]),
        "Versi terbuka": "PDF tersedia" if c["pdf_url"] else ("Cek lewat DOI" if c["doi"] else "Tidak ada"),
        "DOI": c["doi"],
    } for c in cands[:200]]
    edited = st.data_editor(
        pd.DataFrame(rows), hide_index=True, width="stretch", height=440, key="sb_table",
        disabled=["Judul", "Tahun", "Terhubung ke", "Sitasi", "Arah", "Versi terbuka", "DOI"],
        column_config={
            "Pilih": st.column_config.CheckboxColumn(width="small"),
            "Judul": st.column_config.TextColumn(width="large"),
            "Terhubung ke": st.column_config.NumberColumn(help="Jumlah paper koleksi yang terhubung", format="%d paper"),
        },
    )
    chosen = [cands[i] for i in edited.index[edited["Pilih"]].tolist()]
    col_u1, col_u2, col_u3 = st.columns([3, 2, 3])
    with col_u1:
        sb_fac = st.selectbox("Simpan ke bidang", ["auto"] + [f.id for f in faculty_list],
                              format_func=lambda x: "Deteksi otomatis" if x == "auto" else faculty_labels.get(x, x),
                              key="sb_fac")
    with col_u2:
        sb_an = st.checkbox("Langsung analisis", value=False, key="sb_auto_an")
    with col_u3:
        go = st.button(f"Unduh terpilih ({len(chosen)})", type="primary", disabled=not chosen,
                       width="stretch", key="btn_sb_import")
    if go:
        done, failed = [], []
        with st.spinner("Mengunduh paper terpilih..."):
            for c in chosen:
                r = _snowball.import_candidate(c, faculty=None if sb_fac == "auto" else sb_fac)
                (done if r.get("ok") else failed).append((c, r))
        if sb_an and done:
            with st.spinner(f"Menganalisis {len(done)} paper..."):
                _analyze.analyze_all(model=config.LLM_MODEL, lang="id", force=True, files=[r["file"] for _, r in done])
        db.sync_all()
        if done:
            st.success(f"{len(done)} paper masuk koleksi: " + "; ".join(r["title"][:60] for _, r in done))
        for c, r in failed:
            st.warning(f"Gagal: {c['title'][:70]}. {r.get('error', '')}")
        st.session_state["sb_result"] = None

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


def _badge(text: str, tone: str = "muted", icon: str = "") -> str:
    """Small colored pill. Tones: good, bad, mix, warn, info, teal, muted."""
    dot = f"<span class='cl-badge-dot'>{icon}</span>" if icon else "<span class='cl-badge-dot'></span>"
    return f"<span class='cl-badge {tone}'>{dot}{_e(text)}</span>"


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


def render_accuracy_page():
    render_hero(
        title="Periksa Akurasi",
        subtitle="Cek analisis ke isi PDF, cek metadata dan retraksi, ukur akurasi sistem, dan simpan jejak setiap langkah AI.",
        icon="",
    )
    tab_an, tab_meta, tab_eval, tab_log = st.tabs(["Cek analisis", "Metadata & retraksi", "Uji akurasi", "Log audit"])
    papers = db.get_all_papers_with_analyses()
    analyzed = [p for p in papers if p.get("thesis")]

    with tab_an:
        st.caption("Setiap pernyataan analisis AI (tesis, premis, temuan, kesimpulan) dibandingkan dengan teks PDF. "
                   "Kutipan dicari di PDF tanpa AI. Hasil dan koreksi per paper bisa dibuka di Koleksi paper, bagian detail analisis.")
        rows = []
        for p in analyzed:
            sc = _acheck.score(_acheck.load_check(p["file"]))
            cs = _corrections.summary(p["file"])
            rows.append({
                "Paper": f"{p.get('title') or p['file']} ({p.get('year') or 'n.d.'})",
                "Dicek": (sc.get("time") or "")[:10] if sc.get("checked") else "belum",
                "Didukung": f"{sc['supported']}/{sc['statements']}" if sc.get("checked") else "",
                "Perlu dicek": str(sc.get("flagged", "")) if sc.get("checked") else "",
                "Kutipan ada di PDF": f"{sc['quotes_found']}/{sc['quotes']}" if sc.get("checked") else "",
                "Koreksi peneliti": str(cs["total"] or ""),
                "_file": p["file"],
            })
        unchecked = [r["_file"] for r in rows if r["Dicek"] == "belum"]
        c1, c2 = st.columns([3, 1])
        with c1:
            pick = st.multiselect("Paper yang dicek", options=[r["_file"] for r in rows], default=unchecked[:5],
                                  format_func=lambda f: next(r["Paper"] for r in rows if r["_file"] == f)[:90],
                                  key="acc_pick")
        with c2:
            st.write("")
            go = st.button(f"Cek {len(pick)} paper", type="primary", width="stretch", disabled=not pick, key="acc_go")
        if go:
            bar = st.progress(0.0, text="Mulai...")
            _acheck.check_many(pick, model=config.LLM_MODEL,
                               progress_cb=lambda d, n, f: bar.progress(d / n, text=f"{d}/{n} selesai"))
            st.rerun()
        render_table([{k: v for k, v in r.items() if k != "_file"} for r in rows])

    with tab_meta:
        st.caption("Judul, tahun, dan penulis tiap paper dicocokkan ke Crossref atau DataCite lewat DOI. "
                   "Paper yang ditarik (retracted), ditarik penulis, atau diberi peringatan editor ditandai.")
        store = _meta_store()
        if st.button("Cek semua paper sekarang", type="primary", key="meta_go"):
            bar = st.progress(0.0, text="Mulai...")
            store = _metadata.check_all(progress_cb=lambda d, n, t: bar.progress(d / n, text=f"{d}/{n}: {t[:60]}"))
            st.session_state["_meta_store"] = store
        if store:
            bad = _metadata.flagged(store)
            if bad:
                st.error("Paper ini ditarik atau bermasalah. Jangan dikutip sebagai bukti tanpa membaca pemberitahuannya: "
                         + "; ".join(f"{r.get('title')} ({', '.join(n['label'] for n in r['notices'] if n.get('serious'))})" for r in bad))
            counts = {}
            for r in store.values():
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            tones = {_metadata.OK: "good", _metadata.DIFF: "warn", _metadata.NOT_FOUND: "warn",
                     _metadata.INVALID: "bad", _metadata.NO_DOI: "muted", _metadata.ERROR: "muted"}
            st.markdown("<div class='cl-badges'>" + "".join(
                _badge(f"{n} {_metadata.STATUS_LABELS[s].lower()}", tones.get(s, "muted")) for s, n in counts.items()
            ) + "</div>", unsafe_allow_html=True)
            render_table([{
                "Paper": r.get("title"),
                "DOI": r.get("doi") or "",
                "Status": _metadata.STATUS_LABELS.get(r["status"], r["status"]),
                "Beda": "; ".join(f"{d['field']}: kita {d['ours']}, sumber {d['crossref']}" for d in r.get("diffs", [])),
                "Pemberitahuan": "; ".join(n["label"] for n in r.get("notices", [])),
                "Dicek": (r.get("time") or "")[:10],
            } for r in sorted(store.values(), key=lambda r: (r["status"] == _metadata.OK, r.get("title") or ""))])
        else:
            st.info("Belum pernah dicek.")
        st.markdown("**Ekspor daftar pustaka**")
        st.caption("Memakai data Crossref bila sudah cocok. Entri yang belum terverifikasi atau bermasalah diberi catatan.")
        d1, d2 = st.columns(2)
        d1.download_button("Unduh BibTeX (.bib)", _metadata.to_bibtex(papers, store), "references.bib", "text/plain", width="stretch")
        d2.download_button("Unduh RIS (Zotero, Mendeley)", _metadata.to_ris(papers, store), "references.ris",
                           "application/x-research-info-systems", width="stretch")

    with tab_eval:
        st.caption("Set uji berisi pertanyaan dan klaim dari koleksi sendiri, beserta halaman dan jawaban yang benar. "
                   "Dengan ini akurasi pencarian dan cek klaim bisa diukur, dan setiap perubahan bisa dibandingkan.")
        gold = _evaluate.load_gold()
        reviewed = sum(1 for g in gold if g.get("reviewed"))
        st.markdown(f"Set uji: **{len(gold)} soal**, {reviewed} sudah diperiksa peneliti.")
        g1, g2 = st.columns([1, 3])
        n_new = g1.number_input("Paper baru", min_value=1, max_value=30, value=5, key="ev_n")
        g2.write("")
        if g2.button("Buat draf soal dengan AI", key="ev_draft"):
            bar = st.progress(0.0, text="Mulai...")
            new = _evaluate.draft_gold(n_papers=int(n_new), model=config.LLM_MODEL,
                                       progress_cb=lambda d, n, t: bar.progress(d / n, text=f"{d}/{n}: {t[:60]}"))
            st.success(f"{len(new)} soal baru ditambahkan. Periksa dulu sebelum dipakai sebagai patokan.")
            gold = _evaluate.load_gold()
        if gold:
            st.caption("Centang Diperiksa untuk soal yang sudah benar. Ubah teks atau jawaban bila perlu, lalu simpan.")
            table = [{
                "id": g["id"],
                "Jenis": "Pencarian" if g["kind"] == "retrieval" else "Klaim",
                "Soal": g.get("question") or g.get("claim"),
                "Jawaban benar": f"halaman {', '.join(map(str, g.get('pages') or []))}" if g["kind"] == "retrieval"
                else g.get("expected"),
                "Paper": (g.get("title") or g.get("file"))[:60],
                "Diperiksa": bool(g.get("reviewed")),
                "Hapus": False,
            } for g in gold]
            edited = st.data_editor(
                table, key="ev_editor", width="stretch", hide_index=True,
                disabled=["id", "Jenis", "Paper", "Jawaban benar"],
                column_config={"Soal": st.column_config.TextColumn(width="large")},
            )
            with st.expander("Kutipan sumber tiap soal"):
                for g in gold[:60]:
                    st.markdown(f"**{g['id']}** (hal. {g.get('page')}): {_e((g.get('passage') or '')[:500])}")
            if st.button("Simpan perubahan", key="ev_save"):
                by_id = {g["id"]: g for g in gold}
                out = []
                for row in edited:
                    g = by_id[row["id"]]
                    if row["Hapus"]:
                        continue
                    g["reviewed"] = bool(row["Diperiksa"])
                    g["question" if g["kind"] == "retrieval" else "claim"] = row["Soal"]
                    out.append(g)
                _evaluate.save_gold(out)
                st.success("Tersimpan.")
                st.rerun()

            r1, r2, r3 = st.columns([1, 1, 2])
            only_rev = r1.checkbox("Hanya soal yang diperiksa", value=reviewed > 0, key="ev_rev")
            k = r2.number_input("k (halaman teratas)", min_value=1, max_value=10, value=3, key="ev_k")
            r3.write("")
            if r3.button("Jalankan uji", type="primary", key="ev_run"):
                with st.spinner("Menjalankan uji, sekitar 15-20 detik per soal..."):
                    st.session_state["ev_last"] = _evaluate.run(k=int(k), reviewed_only=only_rev, model=config.LLM_MODEL)
        last = st.session_state.get("ev_last")
        if last:
            m1, m2, m3, m4 = st.columns(4)
            pct = lambda x: "-" if x is None else f"{x * 100:.0f}%"
            m1.metric(f"Halaman benar di {last['settings']['k']} teratas", pct(last["retrieval"]["recall_at_k"]))
            m2.metric("Akurasi cek klaim", pct(last["claims"]["accuracy"]))
            m3.metric("Klaim salah yang tertangkap", pct(last["claims"]["false_caught"]))
            m4.metric("Klaim benar yang lolos", pct(last["claims"]["true_passed"]))
            wrong = [r for r in last["claims"]["rows"] if not r["ok"]]
            if wrong:
                with st.expander(f"{len(wrong)} klaim dinilai keliru oleh pemeriksa"):
                    render_table([{"id": r["id"], "Seharusnya": r["expected"], "Hasil": r["got"], "Alasan": r["reason"]} for r in wrong])
        hist = _evaluate.history()
        if hist:
            st.markdown("**Riwayat uji**")
            pct = lambda x: "" if x is None else f"{x * 100:.0f}%"
            render_table([{"Waktu": h["time"].replace("T", " ")[:16], "k": str(h["k"]), "Halaman benar": pct(h["recall_at_k"]),
                           "MRR": "" if h["mrr"] is None else f"{h['mrr']:.2f}", "Akurasi klaim": pct(h["claim_accuracy"]),
                           "Salah tertangkap": pct(h["false_caught"]), "Benar lolos": pct(h["true_passed"]),
                           "Embedding": h.get("embed_model") or "-"} for h in hist])

    with tab_log:
        rows = _audit.read()
        st.caption("Setiap langkah AI dicatat: waktu, model, versi prompt, dan masukannya. Lampirkan log ini di bagian metode.")
        st.markdown("**Teks untuk bagian metode**")
        st.code(_audit.methods_text(rows), language="text", wrap_lines=True)
        if rows:
            l1, l2 = st.columns(2)
            l1.download_button("Unduh log (CSV)", _audit.to_csv(rows), "cosmolab_audit.csv", "text/csv", width="stretch")
            l2.download_button("Unduh log (JSONL)", "\n".join(json.dumps(r, ensure_ascii=False) for r in reversed(rows)),
                               "cosmolab_audit.jsonl", "application/json", width="stretch")
            render_table([{
                "Waktu": r.get("time", "").replace("T", " "),
                "Langkah": _audit.EVENT_LABELS.get(r.get("event"), r.get("event")),
                "Model": r.get("model") or "",
                "Paper / pertanyaan": r.get("question") or r.get("file") or "",
                "Ringkasan": json.dumps(r.get("summary"), ensure_ascii=False) if r.get("summary") else (r.get("status") or ""),
                "Oleh": r.get("user") or "",
            } for r in rows[:300]])
        else:
            st.info("Belum ada aktivitas yang tercatat.")


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


# -------------------------------------------------------------
# Module 1: Paper Explorer & Korpus
# -------------------------------------------------------------
if menu == "Paper Explorer & Korpus":
    active_fac_name = faculty_labels.get(selected_faculty_id, "Universal")
    render_hero(
        title="Koleksi Paper",
        subtitle=f"Bidang: <b>{active_fac_name}</b>. Telusuri paper, lihat hasil analisis AI, dan ambil format sitasinya.",
        icon="",
    )

    tab_pe1, tab_pe2 = st.tabs([
        "Daftar paper",
        "Matriks literatur"
    ])

    with tab_pe1:
        if not papers:
            st.warning(f"Belum ada paper di fakultas ini. Buka tab 'Panen Paper Ilmiah' untuk mengunduh literatur bidang {active_fac_name}.")
        else:
            with st.container(border=True):
                col_f1, col_f2 = st.columns([3, 2])
                filter_q = col_f1.text_input("Cari judul", placeholder="Ketik kata kunci...")
                filter_status = col_f2.selectbox("Status", ["Semua Status", "Belum Dianalisis", "Sudah Dianalisis"],
                                                 format_func=lambda x: {"Semua Status": "Semua paper", "Belum Dianalisis": "Belum dianalisis", "Sudah Dianalisis": "Sudah dianalisis"}[x])

                with st.expander("Filter lain", expanded=False):
                    arg_types = ["Semua"] + sorted(list({p.get("argument_type") for p in papers if p.get("argument_type")}))
                    filter_type = st.selectbox("Jenis argumen", arg_types, format_func=lambda x: TYPE_LABELS.get(x, x))
                    stance_keys = ["Semua", "supports", "critiques", "mixed", "neutral"]
                    filter_stance = st.pills(
                        "Sikap penulis",
                        stance_keys,
                        default="Semua",
                        format_func=lambda x: "Semua" if x == "Semua" else STANCE_LABELS.get(x, x),
                    )

            filtered = papers
            if filter_q:
                filtered = [p for p in filtered if filter_q.lower() in (p.get("title") or "").lower()]
            if filter_type != "Semua":
                filtered = [p for p in filtered if p.get("argument_type") == filter_type]
            if filter_stance and filter_stance != "Semua":
                filtered = [p for p in filtered if p.get("supports_or_critiques") == filter_stance]
            if filter_status == "Belum Dianalisis":
                filtered = [p for p in filtered if not p.get("thesis")]
            elif filter_status == "Sudah Dianalisis":
                filtered = [p for p in filtered if p.get("thesis")]

            # Unanalyzed alert & batch analyze banner
            unanalyzed_scope = [p for p in papers if not p.get("thesis")]
            if unanalyzed_scope:
                with st.container(border=True):
                    col_ub1, col_ub2 = st.columns([3, 2])
                    col_ub1.markdown(f"**{len(unanalyzed_scope)} paper belum dianalisis.**")
                    col_ub1.caption("AI mengekstrak tesis, metodologi, temuan, dan kutipan dengan nomor halaman.")
                    if col_ub2.button(f"Analisis semua ({len(unanalyzed_scope)})", type="primary", key="btn_batch_analyze_all", use_container_width=True):
                        with st.spinner(f"Sedang membedah {len(unanalyzed_scope)} naskah dengan AI ({config.LLM_MODEL})..."):
                            target_f = [p["file"] for p in unanalyzed_scope]
                            _analyze.analyze_all(model=config.LLM_MODEL, concurrency=4, lang="id", files=target_f)
                            db.sync_all()
                            st.success(f"Pembedahan {len(unanalyzed_scope)} naskah selesai!")
                            st.rerun()

            no_author = [p for p in papers if not _authors.as_list(p.get("authors"))]
            if no_author:
                col_na1, col_na2 = st.columns([3, 2])
                col_na1.caption(f"{len(no_author)} paper belum punya nama penulis. CosmoLab mencarinya lewat DOI, arXiv, OpenAlex, dan Crossref, lalu halaman pertama PDF.")
                if col_na2.button(f"Lengkapi penulis ({len(no_author)})", key="btn_fill_authors", use_container_width=True):
                    with st.spinner("Mencari nama penulis..."):
                        _stats = _authors.fill_missing(use_ai=True)
                        db.sync_all()
                    st.success(f"{_stats['found']} dari {_stats['checked']} paper sekarang punya nama penulis.")
                    st.rerun()

            st.markdown(
                f"<div class='cl-legend'><span>Menampilkan {len(filtered)} dari {len(papers)} paper.</span>"
                + _badge("Mendukung", "good") + _badge("Mengkritik", "bad") + _badge("Campuran", "mix") + _badge("Kajian empiris", "info")
                + _badge("Kajian argumen", "teal") + _badge("Perlu dicek", "warn") + "</div>",
                unsafe_allow_html=True,
            )

            for idx, p in enumerate(filtered, start=1):
                title = p.get("title") or "Untitled"
                year = p.get("year") or "n.d."
                arg_t = p.get("argument_type") or "unclassified"
                stn = p.get("supports_or_critiques") or "neutral"
                source = p.get("source") or "web"
                p_faculty = p.get("faculty") or "ilahiyyat"
                fac_info = _faculties.get_faculty(p_faculty)
                fac_icon = fac_info.icon if fac_info else ""
                fac_name = fac_info.name if fac_info else p_faculty

                stance_str = STANCE_LABELS.get(stn, stn)
                type_str = TYPE_LABELS.get(arg_t, arg_t)

                p_authors = _authors.as_list(p.get("authors"))
                meta_bits = ([_authors.display(p_authors)] if p_authors else []) + [str(year), fac_name]

                with st.container(border=True):
                    st.markdown(
                        f"<div class='paper-card-title'>{idx}. {_e(title)}</div>"
                        f"<div class='paper-card-meta'>{_e(' · '.join(meta_bits))}</div>"
                        + paper_badges(p),
                        unsafe_allow_html=True,
                    )

                    if p.get("thesis"):
                        st.markdown(f"<div class='paper-card-thesis'>{_e(p.get('thesis'))}</div>", unsafe_allow_html=True)

                    col_a1, col_a2, col_a3 = st.columns([3, 2, 2])
                    with col_a1:
                        if not p.get("thesis"):
                            st.caption("AI membaca naskah utuh, sekitar 1 menit per paper.")
                    with col_a2:
                        if not p.get("thesis"):
                            if st.button("Analisis", key=f"btn_an_single_{idx}_{p.get('file')}", type="primary", use_container_width=True):
                                with st.spinner(f"Menganalisis '{title[:35]}...'"):
                                    try:
                                        _analyze.analyze_single_paper(p.get("file"), model=config.LLM_MODEL, lang="id")
                                        db.sync_all()
                                        st.success("Analisis selesai.")
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Analisis gagal: {err}")
                    with col_a3:
                        if p.get("url"):
                            st.link_button("Buka sumber", p["url"], use_container_width=True)

                    # Logic expander
                    with st.expander("Lihat detail analisis", expanded=False):
                        render_analysis_detail(p)
                        if p.get("thesis") and st.toggle("Cek ke PDF & koreksi peneliti", key=f"rv_on_{idx}_{p.get('file')}"):
                            render_analysis_review(p, f"{idx}_{p.get('file')}")

                        # Citations
                        apa_ref = _citations.format_apa(p)
                        chicago_ref = _citations.format_chicago_bib(p)
                        in_text_ref = _citations.format_in_text_apa(p)
                        with st.expander("Format Sitasi Akademik Standar (APA 7th & Chicago 17th)"):
                            st.markdown(f"**APA 7th Reference:**")
                            st.code(apa_ref, language="text")
                            st.markdown(f"**Chicago 17th Bibliography:**")
                            st.code(chicago_ref, language="text")
                            st.markdown(f"**Sitasi Dalam Teks (In-Text APA):** `{in_text_ref}`")

                        # Authors: researcher can correct them; manual names are never overwritten
                        with st.expander("Ubah penulis"):
                            src = p.get("authors_source") or ""
                            src_label = {"manual": "diisi peneliti", "metadata": "dari sumber unduhan", "doi": "dari DOI",
                                         "arxiv": "dari arXiv", "openalex": "dari OpenAlex", "crossref": "dari Crossref",
                                         "pdf_ai": "dibaca AI dari halaman pertama PDF, mohon dicek"}.get(src, "belum ada")
                            st.caption(f"Sumber: {src_label}")
                            new_authors = st.text_area("Satu nama per baris", value=chr(10).join(p_authors),
                                                       key=f"authors_edit_{p.get('file')}", height=100)
                            if st.button("Simpan penulis", key=f"btn_save_authors_{p.get('file')}"):
                                db.set_authors(p.get("file"), _authors.parse_input(new_authors))
                                st.success("Penulis disimpan.")
                                st.rerun()

                        # Faculty reallocation
                        with st.expander("Ubah Pemetaan Fakultas untuk Paper Ini"):
                            col_re1, col_re2 = st.columns([3, 1])
                            new_fac = col_re1.selectbox(
                                "Pindahkan ke Fakultas:",
                                [f.id for f in faculty_list],
                                index=[f.id for f in faculty_list].index(p_faculty) if p_faculty in [f.id for f in faculty_list] else 0,
                                format_func=lambda x: faculty_labels.get(x, x),
                                key=f"fac_change_{p.get('file')}"
                            )
                            if col_re2.button("Simpan", key=f"btn_save_fac_{p.get('file')}", use_container_width=True):
                                db.update_paper_faculty(p.get("file"), new_fac)
                                st.success(f"Fakultas diperbarui ke: {faculty_labels.get(new_fac)}")
                                st.rerun()

                        # Re-analyze on demand
                        if p.get("thesis"):
                            with st.expander("Bedah Ulang Naskah Ini (Deep Scan v3)"):
                                st.caption("Jalankan ulang analisis AI jika ingin memperbarui hasil bedah naskah dengan prompt v3 terbaru (metodologi riset & kutipan dari bab pembahasan).")
                                if st.button("Jalankan Ulang Analisis AI", key=f"btn_re_an_{idx}_{p.get('file')}", use_container_width=True):
                                    with st.spinner(f"Menganalisis ulang '{title[:35]}...' dengan AI ({config.LLM_MODEL})..."):
                                        try:
                                            _analyze.analyze_single_paper(p.get("file"), model=config.LLM_MODEL, lang="id", force=True)
                                            db.sync_all()
                                            st.success("Pembedahan ulang naskah selesai!")
                                            st.rerun()
                                        except Exception as err:
                                            st.error(f"Gagal membedah ulang: {err}")

    with tab_pe2:
        st.caption("Ringkasan semua paper dalam satu tabel: penulis, tahun, tesis, premis, dan objeksi.")

        matrix_data = _matrix.build_literature_matrix(selected_faculty_id)

        if not matrix_data:
            st.info("Belum ada paper untuk ditampilkan dalam matriks.")
        else:
            col_m_tb1, col_m_tb2, col_m_tb3 = st.columns(3)
            
            csv_file = _matrix.export_matrix_csv(matrix_data)
            csv_bytes = csv_file.read_bytes()
            
            md_file = _matrix.export_matrix_markdown(matrix_data)
            md_text = md_file.read_text(encoding="utf-8")

            with col_m_tb1:
                st.download_button(
                    "Unduh CSV",
                    data=csv_bytes,
                    file_name=csv_file.name,
                    mime="text/csv",
                    use_container_width=True
                )
            with col_m_tb2:
                st.download_button(
                    "Unduh Markdown",
                    data=md_text,
                    file_name=md_file.name,
                    mime="text/markdown",
                    use_container_width=True
                )
            with col_m_tb3:
                if st.button("Simpan ke Obsidian", key="btn_save_matrix_obsidian", use_container_width=True):
                    obs_out = _matrix.export_matrix_obsidian(matrix_data, faculty_labels.get(selected_faculty_id, "Semua Fakultas"))
                    st.success(f"Tersimpan di Obsidian: `{obs_out.name}`")

            # Audit Kebaruan Pustaka (Standar Dikti / Scopus 5 Tahun Terakhir)
            recency = _matrix.calculate_recency_compliance(matrix_data, threshold_years=5)
            with st.container(border=True):
                col_rc1, col_rc2, col_rc3 = st.columns([3, 3, 4])
                col_rc1.metric("Terbit 5 tahun terakhir", f"{recency['percentage']}%", border=False)
                col_rc2.metric(f"Sejak {recency['cutoff_year']}", f"{recency['recent_count']} / {recency['total']}", border=False)
                with col_rc3:
                    st.markdown(f"**Kebaruan pustaka:** {_EMOJI_RE.sub('', str(recency['status_label'])).strip()}")
                    st.caption(recency['message'])

            display_rows = []
            for r in matrix_data:
                display_rows.append({
                    "No": r["no"],
                    "Penulis & Tahun": f"{r['author']} ({r['year']})",
                    "Judul": r["title"],
                    "Fakultas": r["faculty"],
                    "Sikap": r["stance"],
                    "Tesis": r["thesis"],
                    "Premis Inti": r["premises"],
                    "Objeksi": r["key_objection"],
                })
            with st.container(border=True):
                render_table(display_rows, height=520)


# -------------------------------------------------------------
# Module 2: Roadmap Belajar & Kurikulum
# -------------------------------------------------------------
elif menu == "Roadmap Belajar & Kurikulum":
    render_hero(
        title="Kurikulum & Silabus Progresif (The Academic Dean)",
        subtitle="Peta jalan intelektual 4-tingkat berbasis perpaduan tradisi Turāth Kalam dan filsafat analitik kontemporer untuk penguasaan sistematis.",
        icon="",
        badges=[
            {"icon": "", "text": "4-Tier Progression", "class": "hero-badge-primary"},
            {"icon": "", "text": "Dynamic AI Dean", "class": "hero-badge-accent"},
            {"icon": "", "text": "Obsidian Export Ready", "class": "hero-badge-model"}
        ]
    )

    tab_road1, tab_road2 = st.tabs(["Roadmap Fakultas Terstruktur", "Generator Silabus AI untuk Topik Bebas"])

    with tab_road1:
        cur_fac_id = selected_faculty_id if selected_faculty_id != "all" else "ilahiyyat"
        cur_fac_obj = _faculties.get_faculty(cur_fac_id)
        
        with st.container(border=True):
            st.markdown(f"### Kurikulum: {cur_fac_obj.name}")
            st.caption(cur_fac_obj.full_desc)

        levels = _curriculum.get_learning_roadmap(cur_fac_id)

        for idx_l, lvl in enumerate(levels):
            with st.container(border=True):
                st.markdown(f"#### **{lvl['title']}**")
                st.info(lvl['description'])
                if not lvl['papers']:
                    st.caption("Belum ada paper di level ini dalam korpus lokal. Gunakan tab 'Panen Paper Ilmiah' untuk menambah paper.")
                else:
                    for p_idx, p in enumerate(lvl['papers'], 1):
                        col_p1, col_p2, col_p3 = st.columns([4, 1, 1])
                        col_p1.markdown(f"**{p_idx}. [{p['year']}] {p['title']}**")
                        col_p1.caption(f"*Tesis:* {p['thesis'][:150]}...")
                        col_p2.write(f"Tipe: `{p['argument_type']}`")
                        col_p3.markdown(f"<span class='stance-pill stance-{_e(p['stance'])}'>{_e(p['stance'])}</span>", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:4px 0; border:none; border-top:1px dashed #E2E8F0;'>", unsafe_allow_html=True)

        with st.expander("Rujukan Standar & Debat Inti Fakultas Ini", expanded=False):
            col_ref1, col_ref2 = st.columns(2)
            with col_ref1:
                st.markdown("#### Naskah Turāth Klasik:")
                for r in cur_fac_obj.classic_references:
                    st.markdown(f"- {r}")
            with col_ref2:
                st.markdown("#### Riset Analitik Modern:")
                for r in cur_fac_obj.modern_references:
                    st.markdown(f"- {r}")

    with tab_road2:
        with st.container(border=True):
            st.markdown("### Generator Silabus AI: Rancang Kurikulum Topik Apa Saja")
            st.caption("Ketik topik dari bidang apa pun yang ingin Anda pelajari secara mendalam. Dekan AI akan menyusun silabus 4 tingkat, bacaan wajib, dilema Sokrates, dan flashcards.")

            col_tp1, col_tp2 = st.columns([2, 1])
            custom_topic = col_tp1.text_input("Judul Topik / Mata Kuliah Baru:", placeholder="contoh: Teori Kausalitas Al-Ghazali vs Hume, Problem of Evil, Argumen Jiwa Ibn Sina...")
            custom_desc = col_tp2.text_input("Fokus Khusus (Opsional):", placeholder="contoh: Komparasi dengan mekanika kuantum")

            if st.button("Susun Silabus Kurikulum Lengkap", type="primary", use_container_width=True):
                if not custom_topic.strip():
                    st.error("Silakan masukkan topik terlebih dahulu.")
                else:
                    with st.spinner("Dekan Akademik AI sedang merancang silabus, memetakan naskah klasik, dan menyusun kartu nalar..."):
                        syllabus_data = _curriculum.generate_ai_syllabus(custom_topic, custom_desc, model=config.LLM_MODEL)
                        st.session_state["active_syllabus"] = syllabus_data

        if "active_syllabus" in st.session_state:
            syl = st.session_state["active_syllabus"]
            with st.container(border=True):
                st.markdown(f"## Silabus: **{syl.get('course_title')}**")
                st.markdown(f"**Domain Bidang:** `{syl.get('faculty_domain', 'Multidisipliner')}`")
                st.info(f"**Visi Pedagogis:**\n\n{syl.get('pedagogical_vision', '')}")

                st.markdown("### Tahapan Belajar 4-Tingkat:")
                for t in syl.get("tiers", []):
                    t_title = t.get('title', f"Level {t.get('tier_num', '-')}")
                    with st.expander(f"**{t_title}**", expanded=True):
                        st.write(t.get("description", ""))
                        if t.get("key_concepts"):
                            st.markdown("**Konsep Kunci:** " + ", ".join([f"`{c}`" for c in t["key_concepts"]]))
                        if t.get("milestone_task"):
                            st.warning(f"**Milestone Uji Nalar:** {t['milestone_task']}")

                col_rb1, col_rb2 = st.columns(2)
                with col_rb1:
                    st.markdown("#### Naskah Klasik Turāth:")
                    for r in syl.get("classic_turath_readings", []):
                        st.markdown(f"- {r}")
                with col_rb2:
                    st.markdown("#### Rujukan Akademik Modern:")
                    for r in syl.get("modern_academic_readings", []):
                        st.markdown(f"- {r}")

                if syl.get("socratic_dilemma"):
                    st.markdown("#### Dilema Sokrates Inti:")
                    st.info(syl["socratic_dilemma"])

                if syl.get("flashcards"):
                    st.markdown(f"#### Kartu Active Recall ({len(syl['flashcards'])} kartu):")
                    for fc in syl["flashcards"]:
                        st.markdown(f"- **Q:** {fc.get('question')}  \n  *A:* {fc.get('answer')}")

                if st.button("Simpan Silabus ke Obsidian Vault", type="primary"):
                    out_p = _curriculum.save_syllabus_to_obsidian(syl)
                    st.success(f"Silabus berhasil disimpan ke Obsidian: `{out_p.name}`")


# -------------------------------------------------------------
# Module 3: Arena Sparring Nalar
# -------------------------------------------------------------
elif menu == "Arena Sparring Nalar":
    render_hero(
        title="Arena Sparring & Pelatihan Nalar Kritis",
        subtitle="Uji ketahanan tesis dan silogisme Anda berhadapan langsung dengan para raksasa pemikiran: Hume, Al-Ghazali, Ibn Sina, Mackie, Dennett, dan The Ruthless Critic.",
        icon="",
        badges=[
            {"icon": "", "text": "Intellectual Duel", "class": "hero-badge-primary"},
            {"icon": "", "text": "Enthymeme Detection", "class": "hero-badge-accent"},
            {"icon": "", "text": "Socratic Method", "class": "hero-badge-model"}
        ]
    )

    spar_tab1, spar_tab2 = st.tabs(["Sparring dengan Lawan Debat Filosofis", "The Ruthless Critic (Devil's Advocate Tesis Mandiri)"])

    with spar_tab1:
        personas = _sparring.list_personas()
        
        with st.container(border=True):
            col_pers, col_dil = st.columns([1, 2])
            
            with col_pers:
                selected_persona_id = st.selectbox(
                    "Pilih Lawan Tanding:",
                    [p["id"] for p in personas],
                    format_func=lambda x: f"{_sparring.get_persona(x)['icon']} {_sparring.get_persona(x)['name']}"
                )
                cur_persona = _sparring.get_persona(selected_persona_id)
                st.markdown(f"""
                <div class="persona-card">
                    <div class="persona-header">{cur_persona['icon']} {cur_persona['name']}</div>
                    <div class="persona-title">{cur_persona['title']}</div>
                    <div class="persona-desc">{cur_persona['desc']}</div>
                </div>
                """, unsafe_allow_html=True)

            with col_dil:
                dilemmas = _sparring.get_dilemmas_by_faculty(selected_faculty_id)
                dilemma_options = ["(Ketik Dilema Bebas Sendiri)"] + [d["topic"] for d in dilemmas]
                chosen_dilemma_title = st.selectbox("Pilih Kasus Dilema:", dilemma_options)
                
                if chosen_dilemma_title == "(Ketik Dilema Bebas Sendiri)":
                    dilemma_text = st.text_area("Tuliskan Konteks / Dilema Bebas:", value="Apakah konsep keniscayaan kausalitas itu nyata atau sekadar kebiasaan indrawi?", height=85)
                else:
                    matched_d = next(d for d in dilemmas if d["topic"] == chosen_dilemma_title)
                    dilemma_text = matched_d["dilemma"]
                    st.info(dilemma_text)

            user_statement = st.text_area(
                "Tuliskan Argumen / Jawaban Anda untuk Menghadapi Lawan Tanding:",
                height=130,
                placeholder="Ketik penalaran logis, premis, atau sanggahan Anda di sini..."
            )

            launch_duel = st.button("Luncurkan Sparring Nalar!", type="primary", use_container_width=True)

        if launch_duel:
            if not user_statement.strip():
                st.error("Silakan tuliskan argumen Anda terlebih dahulu.")
            else:
                with st.spinner(f"{cur_persona['name']} sedang menganalisis titik lemah logika Anda..."):
                    res = _sparring.spar_with_persona(
                        user_argument=user_statement,
                        persona_id=selected_persona_id,
                        dilemma_context=dilemma_text,
                        faculty_id=selected_faculty_id,
                        model=config.LLM_MODEL
                    )
                    st.session_state["last_spar_result"] = {
                        "user_arg": user_statement,
                        "persona": cur_persona,
                        "res": res
                    }

        if "last_spar_result" in st.session_state:
            spar_data = st.session_state["last_spar_result"]
            p_obj = spar_data["persona"]
            r_obj = spar_data["res"]

            st.markdown("### Arena Duel Pemikiran:")
            
            with st.chat_message("user"):
                st.markdown(f"**Tesis / Argumen Anda:**\n\n{spar_data['user_arg']}")

            with st.chat_message("assistant", avatar=":material/person:"):
                st.markdown(f"#### {p_obj['icon']} Respons {p_obj['name']} ({p_obj['title']}):")
                st.markdown(r_obj.get("feedback", ""))

            if r_obj.get("referenced_papers"):
                with st.expander("Rujukan Paper Korpus yang Digunakan"):
                    for p in r_obj["referenced_papers"]:
                        st.markdown(f"- **[{p.get('year', 'n.d.')}] {p.get('title')}** | Sikap: `{p.get('supports_or_critiques')}`")

    with spar_tab2:
        with st.container(border=True):
            st.markdown("### The Ruthless Critic: Stress-Test Tesis Mandiri")
            st.caption("AI akan membongkar premis tersembunyi (*enthymeme*), menyerang celah logika, dan memberikan rekomendasi pembenahan tesis agar *bulletproof*.")

            default_arg = "Saya berpendapat bahwa mekanika kuantum tidak membatalkan premis kausalitas Kalam, karena fluktuasi vakum kuantum tetap memerlukan ruang hampa yang berenergi sebagai sebab materialnya, bukan ketiadaan mutlak."
            user_arg = st.text_area("Tuliskan Draf Tesis / Argumen Anda:", value=default_arg, height=110)

            run_critic = st.button("Bedah & Serang Tesis Saya!", type="primary", use_container_width=True)

        if run_critic:
            if not user_arg.strip():
                st.error("Silakan masukkan tesis terlebih dahulu.")
            else:
                with st.spinner("The Ruthless Critic sedang mencari paper lawan di korpus dan membedah struktur logika Anda..."):
                    critique_res = _sparring.criticize_argument(user_arg, model=config.LLM_MODEL)
                    st.session_state["critic_result"] = critique_res

        if "critic_result" in st.session_state:
            with st.chat_message("assistant", avatar=":material/sports_kabaddi:"):
                st.markdown(st.session_state["critic_result"].get("feedback", ""))


# -------------------------------------------------------------
# Module 4: Tanya Korpus & Sintesis (Universal Second Brain)
# -------------------------------------------------------------
elif menu == "Tanya Korpus & Sintesis":
    active_fac_name = faculty_labels.get(selected_faculty_id, "Universal")
    render_hero(
        title="Tanya Korpus & Sintesis",
        subtitle=f"Ajukan pertanyaan riset. AI menjawab hanya dari paper di koleksi (bidang: <b>{active_fac_name}</b>) dan menyebutkan rujukannya.",
        icon="",
    )

    fac_suggestions = {
        "ilahiyyat": [
            "Bagaimana para peneliti membantah klaim bahwa fluktuasi vakum kuantum membatalkan hukum kausalitas?",
            "Apa bantahan matematika terhadap keberatan Hilbert's Hotel pada ketakterhinggaan waktu lampau?",
            "Mengapa hipotesis Multiverse dianggap tidak menyelesaikan persoalan fine-tuning kosmos?"
        ],
        "epistemologi": [
            "Bagaimana Al-Ghazali dalam Al-Munqidh menyelesaikan keraguan terhadap pancaindra dan akal?",
            "Apa perbedaan epistemologis antara silogisme Burhani dengan Jadal dalam pembuktian akidah?",
            "Bagaimana Reformed Epistemology Alvin Plantinga membela rasionalitas iman tanpa bukti deduktif?"
        ],
        "kausalitas": [
            "Apa perbedaan mendasar antara doktrin Okasionalisme Al-Ghazali dengan Skeptisisme David Hume tentang sebab-akibat?",
            "Bagaimana teori Kasb mazhab Asy'ari menjelaskan kebebasan memilih di bawah kedaulatan mutlak takdir?",
            "Apakah indeterminisme fisika kuantum membuka ruang logis bagi tindakan Ilahi (Divine Action) di alam semesta?"
        ],
        "teodisi": [
            "Bagaimana pembelaan Alvin Plantinga (Free Will Defense) menghadapi argumen logis kejahatan dari J.L. Mackie?",
            "Apa respon teisme analitik terhadap problem penderitaan tanpa faedah (Gratuitous Evil) William Rowe?",
            "Apa makna doktrin Al-Ghazali 'Laysa fi al-imkan abda' mimma kan' dalam konteks teodisi?"
        ],
        "falsafah_jiwa": [
            "Bagaimana Argumen Manusia Terbang (The Flying Man) Ibn Sina membuktikan eksistensi jiwa immaterial?",
            "Mengapa 'The Hard Problem of Consciousness' menjadi batu sandungan bagi materialisme dan fisikalisme?",
            "Dapatkah kecerdasan buatan (AI) memiliki kesadaran sejati (qualia) menurut filsafat pikiran Islam?"
        ],
        "nubuwwat": [
            "Bagaimana tradisi teologi Islam merespons kritik probabilitas David Hume mengenai mukjizat?",
            "Apa distingsi logis antara hal yang mustahil secara akal (Mustahil Aqli) vs mustahil secara kebiasaan (Mustahil 'Adi)?",
            "Bagaimana hermeneutika Ibn Rushd (Fasl al-Maqal) menyelesaikan pertentangan teks wahyu dengan akal demonstratif?"
        ],
    }

    generic_suggestions = [
        "Apa temuan utama paper-paper di koleksi ini, dan di mana mereka saling bertentangan?",
        "Metodologi apa saja yang dipakai, dan apa kelemahan masing-masing?",
        "Pertanyaan apa yang belum dijawab oleh paper-paper ini?",
    ]
    active_sug_list = fac_suggestions.get(selected_faculty_id, generic_suggestions)
    
    with st.container(border=True):
        selected_sug = st.selectbox("Contoh pertanyaan (opsional)", ["(Ketik pertanyaan sendiri...)"] + active_sug_list)

        user_q = st.text_area(
            "Pertanyaan Anda",
            value=selected_sug if selected_sug != "(Ketik pertanyaan sendiri...)" else "",
            placeholder="Ketik pertanyaan riset Anda di sini...",
            height=95
        )

        col_r1, col_r2 = st.columns([1, 2])
        k_val = col_r1.slider("Jumlah paper yang dibaca", min_value=2, max_value=8, value=6)
        rag_mode = col_r2.radio(
            "Jenis jawaban",
            ["Agentic", "Classic"],
            format_func=lambda x: "Mendalam: bandingkan pendapat pro dan kontra" if x == "Agentic" else "Cepat: jawaban ringkas",
            horizontal=True
        )

        check_claims = st.checkbox(
            "Periksa setiap klaim terhadap isi paper", value=True,
            help="Setiap kalimat yang menyebut sumber dicek: apakah isi paper itu benar-benar mendukungnya. Menambah sekitar 10–30 detik.",
        )

        ask_btn = st.button("Tanyakan", type="primary", use_container_width=True)

    if ask_btn:
        if not user_q.strip():
            st.error("Silakan masukkan pertanyaan terlebih dahulu.")
        else:
            if "Agentic" in rag_mode:
                with st.spinner("Membaca paper dan membandingkan pendapat. Biasanya 30–90 detik..."):
                    try:
                        res = _ask_agent.ask_agentic(question=user_q, model=config.LLM_MODEL, top_k=k_val)
                        st.session_state.pop("classic_answer", None)
                        st.session_state["agentic_answer"] = {
                            "q": user_q,
                            "res": res,
                            "claims": run_claim_check(res.get("answer", ""), res.get("referenced_papers")) if check_claims else None,
                        }
                    except Exception as e:
                        st.error(f"Gagal memproses pertanyaan: {e}")
            else:
                with st.spinner("Membaca paper. Biasanya 10–30 detik..."):
                    try:
                        answer = _ask.ask(question=user_q, model=config.LLM_MODEL, top_k=k_val)
                        st.session_state.pop("agentic_answer", None)
                        st.session_state["classic_answer"] = {
                            "q": user_q,
                            "answer": answer,
                            "claims": run_claim_check(answer) if check_claims else None,
                        }
                    except Exception as e:
                        st.error(f"Gagal memproses pertanyaan: {e}")

    if "agentic_answer" in st.session_state:
        ans_data = st.session_state["agentic_answer"]
        res = ans_data["res"]

        with st.expander("Langkah kerja AI", expanded=False):
            for idx, step in enumerate(res.get("thought_steps", []), 1):
                st.markdown(f"**Langkah {idx}:** {step}")

        with st.chat_message("assistant", avatar=":material/balance:"):
            st.markdown(res.get("answer", ""))

        render_claim_report(ans_data.get("claims"))

        ref_papers = res.get("referenced_papers", [])
        if ref_papers:
            with st.expander(f"Paper yang dipakai ({len(ref_papers)})", expanded=False):
                for p in ref_papers:
                    st.markdown(f"- **[{p.get('year', 'n.d.')}] {p.get('title')}** | Sikap: `{p.get('supports_or_critiques')}`")
                    if p.get("thesis"):
                        st.caption(f"  *Tesis:* {p.get('thesis')}")

        grounded_cits = res.get("grounded_citations", [])
        if grounded_cits:
            with st.expander(f"Bukti Verbatim dan Halaman PDF Terverifikasi ({len(grounded_cits)})", expanded=True):
                st.caption("Kutipan langsung dari naskah PDF asli yang diverifikasi oleh sistem Page-Aware Grounding:")
                for gc in grounded_cits:
                    st.markdown(
                        f'''<div style="background-color: rgba(28, 100, 242, 0.05); border-left: 4px solid #1c64f2; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;">
                            <div style="font-size: 0.85rem; font-weight: 600; color: #1c64f2; margin-bottom: 3px;">
                                📄 {html.escape(gc.get('paper_title', ''))} ({gc.get('year', '')}) &mdash; <span style="background: #e1effe; color: #1e429f; padding: 1px 6px; border-radius: 4px;">{gc.get('page_label', '')}</span>
                            </div>
                            <div style="font-size: 0.88rem; font-style: italic; color: #374151;">
                                &ldquo;{html.escape(gc.get('verbatim', ''))}&rdquo;
                            </div>
                        </div>''',
                        unsafe_allow_html=True
                    )

        if st.button("Simpan jawaban ke catatan Obsidian", key="btn_save_agent_obsidian"):
            saved_path = export.export_agent_synthesis_to_obsidian(ans_data["q"], res.get("answer", ""), ref_papers)
            st.success(f"Berhasil disimpan ke Obsidian: `{saved_path.name}`")

    elif "classic_answer" in st.session_state:
        ans_data = st.session_state["classic_answer"]
        with st.chat_message("assistant", avatar=":material/description:"):
            st.markdown(ans_data["answer"])
        render_claim_report(ans_data.get("claims"))


# -------------------------------------------------------------
# Module 5: Studio Artikel Siap Baca
# -------------------------------------------------------------
elif menu == "Studio Artikel Siap Baca":
    render_hero(
        title="Tulis Artikel",
        subtitle="AI menulis draf artikel dari paper di koleksi. Draf wajib diperiksa peneliti sebelum dikirim ke klien.",
        icon="",
    )

    tab_art1, tab_art2 = st.tabs(["Tulis baru", "Artikel tersimpan & kirim ke klien"])

    with tab_art1:
        topic_presets = {
            "ilahiyyat": "Menemukan Kembali Awal Mula: Dialektika Singularitas Kosmologi dan Argumen Kalam",
            "kausalitas": "Teka-teki Sebab-Akibat: Mempertemukan Api Al-Ghazali, Skeptisisme Hume, dan Ketidakpastian Kuantum",
            "teodisi": "Di Balik Tirai Penderitaan: Menimbang Keadilan Ilahi Antara Logika Mackie dan Teodisi Hikmah",
            "falsafah_jiwa": "Manusia yang Melayang di Ruang Hampa: Mengapa Kesadaran Menolak Reduksi Materialistik",
            "epistemologi": "Skeptisisme Radikal dan Batas Akal: Dari Al-Munqidh Al-Ghazali ke Cogito Descartes",
            "nubuwwat": "Ketika Hukum Alam Terdiam: Menimbang Rasionalitas Mukjizat di Hadapan Keraguan Hume",
        }
        default_preset = topic_presets.get(selected_faculty_id, "")

        with st.container(border=True):
            col_a1, col_a2 = st.columns([3, 2])
            article_topic = col_a1.text_input("Topik atau judul artikel", value=default_preset, placeholder="contoh: Dampak kebijakan zakat produktif terhadap UMKM")
            
            style_keys = list(_writer.ARTICLE_STYLES.keys())
            article_style = col_a2.selectbox(
                "Jenis tulisan",
                style_keys,
                format_func=lambda x: _writer.ARTICLE_STYLES[x]["name"]
            )
            st.caption(f"*{_writer.ARTICLE_STYLES[article_style]['desc']}*")

            col_src1, col_src2 = st.columns(2)
            with col_src1:
                ref_mode = st.radio("Paper rujukan", ["Otomatis Cari dari Second Brain", "Pilih Paper Tertentu dari Database"],
                                    format_func=lambda x: "Pilih otomatis" if x.startswith("Otomatis") else "Saya pilih sendiri", horizontal=True)
            
            specific_papers = None
            if ref_mode == "Pilih Paper Tertentu dari Database":
                with col_src2:
                    paper_options = [p["file"] for p in all_papers if p.get("thesis")]
                    _paper_titles = {p["file"]: p.get("title") or p["file"] for p in all_papers}
                    specific_papers = st.multiselect("Paper yang dipakai", paper_options, default=paper_options[:3] if len(paper_options) >= 3 else paper_options,
                                                     format_func=lambda f: _paper_titles.get(f, f))

            col_cp1, col_cp2 = st.columns([3, 2])
            custom_prompt = col_cp1.text_input("Instruksi tambahan (opsional)", placeholder="contoh: Jelaskan istilah teknis saat pertama kali muncul...")
            model_choice = col_cp2.selectbox(
                "Kecepatan",
                ["gemini-3-8-flash", "deepseek-v4-pro"],
                format_func=lambda x: "Cepat (±15 detik)" if "gemini" in x else "Mendalam (±90 detik)"
            )

            write_btn = st.button("Tulis artikel", type="primary", use_container_width=True)

        if write_btn:
            if not article_topic.strip():
                st.error("Silakan masukkan topik artikel terlebih dahulu.")
            else:
                with st.spinner("Menulis artikel dari paper di koleksi..."):
                    art_result = _writer.generate_article(
                        topic=article_topic,
                        style=article_style,
                        custom_instructions=custom_prompt,
                        faculty_id=selected_faculty_id,
                        paper_files=specific_papers,
                        model=model_choice
                    )
                    st.session_state["current_article"] = art_result
                    saved_files = _writer.save_article(art_result)
                    st.session_state["saved_article_paths"] = saved_files

        if "current_article" in st.session_state:
            curr = st.session_state["current_article"]
            saved = st.session_state.get("saved_article_paths", {})
            html_content = _writer.format_article_html(curr)

            # Action Toolbar inside a border container
            with st.container(border=True):
                st.success(f"Draf selesai: sekitar {curr.get('reading_time_min', 5)} menit baca. "
                           "Untuk mengirim ke klien, buka tab **Artikel tersimpan & kirim ke klien**.")
                col_tb3, col_tb4 = st.columns(2)
                
                with col_tb3:
                    st.download_button(
                        "Unduh draf (.md)",
                        data=curr["content_md"],
                        file_name=f"{curr.get('title', 'Artikel')[:40]}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                with col_tb4:
                    st.download_button(
                        "Unduh draf (.html)",
                        data=html_content,
                        file_name=f"{curr.get('title', 'Artikel')[:40]}.html",
                        mime="text/html",
                        use_container_width=True
                    )

            if saved.get("md_path"):
                st.caption(f"Tersimpan sebagai `{saved['md_path'].name}`")

            # Elegant Reader View
            st.markdown("#### Pratinjau")
            if hasattr(st, "iframe"):
                st.iframe(html_content, height=650)
            else:
                st.components.v1.html(html_content, height=650, scrolling=True)

            if curr.get("referenced_papers"):
                with st.expander("Paper yang dipakai"):
                    for rp in curr["referenced_papers"]:
                        st.markdown(f"- **[{rp.get('year', 'n.d.')}] {rp.get('title')}** | {rp.get('supports_or_critiques')}")

    with tab_art2:
        articles_dir = config.ROOT / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)
        md_articles = sorted(list(articles_dir.glob("*.md")), reverse=True)

        if not md_articles:
            st.info("Belum ada artikel. Tulis artikel baru di tab sebelah.")
        else:
            selected_art_file = st.selectbox("Pilih artikel", [a.name for a in md_articles])
            art_path = articles_dir / selected_art_file
            art_text = art_path.read_text(encoding="utf-8")
            
            html_partner = articles_dir / f"{art_path.stem}.html"
            html_partner_data = html_partner.read_text(encoding="utf-8") if html_partner.exists() else _writer.format_article_html({"title": art_path.stem, "content_md": art_text})

            render_client_delivery(art_path, key=f"art_{art_path.stem}")

            with st.expander("Unduhan internal (Markdown / HTML, bukan untuk klien)"):
                col_ar1, col_ar2 = st.columns(2)
                with col_ar1:
                    st.download_button("Unduh .md", data=art_text, file_name=selected_art_file, mime="text/markdown", use_container_width=True)
                with col_ar2:
                    st.download_button("Unduh .html", data=html_partner_data, file_name=f"{art_path.stem}.html", mime="text/html", use_container_width=True)

            st.markdown("#### Pratinjau")
            if hasattr(st, "iframe"):
                st.iframe(html_partner_data, height=650)
            else:
                st.markdown(art_text)


# -------------------------------------------------------------
# Module: Bedah DOI Seketika (AMRC & Elsevier Highlights)
# -------------------------------------------------------------
elif menu == "Bedah DOI Seketika":
    render_hero(
        title="Bedah DOI Seketika (Smart Paper Inspector)",
        subtitle="Masukkan <b>DOI artikel ilmiah</b> apa saja dari Elsevier, Springer, Nature, Wiley, atau jurnal mana pun. Sistem seketika mengekstrak <b>Latar Belakang, Metodologi, Temuan Kunci, Kesimpulan</b>, serta <b>Celah Riset untuk Skripsi/Tesis</b>.",
        icon="",
        badges=[
            {"icon": "", "text": "AMRC Breakdown", "class": "hero-badge-primary"},
            {"icon": "", "text": "Elsevier Style Highlights", "class": "hero-badge-accent"},
            {"icon": "", "text": "Research Gap Finder", "class": "hero-badge-model"}
        ]
    )

    if "inspector_doi_input" not in st.session_state:
        st.session_state["inspector_doi_input"] = ""

    st.markdown("##### Coba Contoh DOI Cepat:")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    if col_ex1.button("Elsevier (Kognisi & Memori)", use_container_width=True):
        st.session_state["inspector_doi_input"] = "10.1016/j.concog.2020.102980"
        st.rerun()
    if col_ex2.button("Springer (Kalam & Matematika)", use_container_width=True):
        st.session_state["inspector_doi_input"] = "10.1007/s00283-022-10224-8"
        st.rerun()
    if col_ex3.button("Oxford Mind (Kausalitas)", use_container_width=True):
        st.session_state["inspector_doi_input"] = "10.1093/mind/fzv156"
        st.rerun()

    doi_val = st.text_input(
        "Masukkan DOI atau URL Paper Ilmiah:",
        value=st.session_state["inspector_doi_input"],
        placeholder="Contoh: 10.1016/j.concog.2020.102980 atau https://doi.org/10.1007/...",
        help="Mendukung format DOI murni (10.xxxx/...) atau link https://doi.org/...",
    )

    col_btn1, col_btn2 = st.columns([1, 3])
    run_inspect = col_btn1.button("Bedah Paper Sekarang", type="primary", use_container_width=True)

    if run_inspect and doi_val.strip():
        with st.spinner("Menghubungi Crossref, Semantic Scholar, OpenAlex & membedah dengan AI..."):
            res = _inspector.inspect_paper(doi_val.strip())
            st.session_state["last_inspection_res"] = res

    if "last_inspection_res" in st.session_state and st.session_state["last_inspection_res"]:
        res = st.session_state["last_inspection_res"]
        if not res.get("success"):
            st.error(f"{res.get('error')}")
        else:
            a = res.get("analysis", {})

            st.markdown("---")
            # Header Card
            pdf_link_html = f" • <a href='{_safe_url(res.get('pdf_url'))}' target='_blank' style='background:#10B981; color:white; padding:3px 8px; border-radius:6px; text-decoration:none; font-weight:600; font-size:0.8rem;'>Unduh PDF Terbuka (Legal)</a>" if res.get("pdf_url") else ""
            oa_badge = "<span style='background:#DCFCE7; color:#166534; padding:3px 8px; border-radius:6px; font-weight:600; font-size:0.85rem;'>Open Access (Tersedia Naskah Terbuka)</span>" if res.get("is_oa") else "<span style='background:#FEF3C7; color:#92400E; padding:3px 8px; border-radius:6px; font-weight:600; font-size:0.85rem;'>Paywalled / Berbayar</span>"
            
            st.markdown(f"""
            <div style="background:white; border:1px solid #E2E8F0; border-radius:12px; padding:20px; margin-bottom:18px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:6px;">
                    <b>{_e(res.get('venue') or res.get('publisher') or 'Jurnal Ilmiah')}</b> • Tahun {_e(res.get('year'))} • {oa_badge}{pdf_link_html} • <b>{_e(res.get('citation_count'))}</b> Sitasi
                </div>
                <h3 style="margin-top:0; color:#0F172A; font-weight:700;">{_e(res.get('title'))}</h3>
                <div style="color:#475569; font-size:0.92rem; margin-bottom:10px;">
                    <b>Penulis:</b> {_e(', '.join(res.get('authors', [])) or 'Anonim')}
                </div>
                <div>
                    <a href="{_safe_url(res.get('url'))}" target="_blank" style="text-decoration:none; color:#2563EB; font-weight:600;">https://doi.org/{_e(res.get('doi'))}</a>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # One-Sentence Takeaway
            if a.get("one_sentence_takeaway"):
                st.info(f"**Intisari 1 Kalimat:** \"{a.get('one_sentence_takeaway')}\"")

            # Elsevier-Style Highlights
            if a.get("highlights"):
                st.markdown("##### Research Highlights (Gaya Elsevier ScienceDirect)")
                hl_html = "".join(f"<li style='margin-bottom:6px; color:#1E293B;'>{_e(h)}</li>" for h in a.get("highlights"))
                st.markdown(f"""
                <div style="background:#F8FAFC; border-left:4px solid #10B981; padding:12px 18px; border-radius:0 8px 8px 0; margin-bottom:20px;">
                    <ul style="margin:0; padding-left:20px;">{hl_html}</ul>
                </div>
                """, unsafe_allow_html=True)

            # AMRC Quadrants / Tabs
            tab_prob, tab_meth, tab_res, tab_conc, tab_gap = st.tabs([
                "Latar Belakang & Masalah",
                "Metodologi",
                "Temuan Kunci (Result)",
                "Kesimpulan & Implikasi",
                "Celah Riset (Untuk Skripsi/Tesis)"
            ])

            with tab_prob:
                st.markdown(f"**Urgensi & Masalah yang Diteliti:**\n\n{a.get('problem_statement', '-')}")
                if res.get("abstract"):
                    with st.expander("Teks Asli Abstrak dari Penerbit", expanded=False):
                        st.write(res.get("abstract"))

            with tab_meth:
                st.markdown(f"**Desain Riset & Pendekatan Ilmiah:**\n\n{a.get('methodology', '-')}")

            with tab_res:
                st.markdown("**Temuan Signifikan:**")
                kfs = a.get("key_findings", [])
                if isinstance(kfs, list):
                    for f in kfs:
                        st.markdown(f"- {f}")
                else:
                    st.write(kfs)

            with tab_conc:
                st.markdown(f"**Kesimpulan Akhir & Dampak Riset:**\n\n{a.get('conclusion', '-')}")

            with tab_gap:
                st.markdown("**Celah Riset & Ide Penelitian Turunan (Cocok untuk Judul Skripsi/Tesis Baru):**")
                gaps = a.get("research_gaps", [])
                if isinstance(gaps, list):
                    for g in gaps:
                        st.markdown(f"- {g}")
                else:
                    st.write(gaps)

            # Citation Section
            st.markdown("---")
            st.markdown("##### Format Sitasi & Rujukan")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("**Format APA 7th:**")
                st.code(res.get("apa_citation", ""), language="markdown")
            with col_c2:
                st.markdown("**Format BibTeX (Mendeley / Zotero / LaTeX):**")
                st.code(res.get("bibtex", ""), language="bibtex")

            # Actions
            col_act1, col_act2 = st.columns(2)
            if col_act1.button("Simpan Hasil Bedah ke Disk", use_container_width=True):
                saved_path = _inspector.save_inspection(res)
                st.success(f"Berhasil disimpan di: `{saved_path}`")
            
            if col_act2.button("Masukkan Metadata ke Database CosmoLab", use_container_width=True):
                try:
                    con = db.get_connection()
                    con.execute("""
                        INSERT OR REPLACE INTO papers (file, id, title, year, doi, url, source, abstract, faculty)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"doi_{res['doi'].replace('/', '_')}.pdf",
                        res["doi"],
                        res["title"],
                        str(res["year"]),
                        res["doi"],
                        res["url"],
                        "doi_inspector",
                        res.get("abstract", ""),
                        "ilahiyyat"
                    ))
                    con.commit()
                    con.close()
                    st.success("Berhasil ditambahkan ke Database Korpus CosmoLab!")
                except Exception as e:
                    st.error(f"Gagal menyimpan ke DB: {e}")


# -------------------------------------------------------------
# Module 6: Panen Paper Ilmiah (Multi-Faculty)
# -------------------------------------------------------------
elif menu == "Panen Paper Ilmiah":
    render_hero(
        title="Cari & Unduh Paper",
        subtitle="Cari paper di 6 basis data akademik. CosmoLab hanya mengunduh naskah yang legal dan terbuka (open access).",
        icon="",
    )

    # Visual Ribbon of Connected Sources
    st.markdown("""
    <div style="font-size:0.8rem; color:#64748B; margin-bottom:10px;">
        Sumber: arXiv · DOAJ · Semantic Scholar · Crossref · OpenAlex · CORE
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Sumber tambahan: CORE (opsional)", expanded=False):
        core_key = getattr(config, "CORE_API_KEY", "")
        if core_key:
            st.success(f"**CORE API Terhubung.** Kunci API terdeteksi di lingkungan sistem.")
        else:
            st.info(
                "**CORE API Key (Opsional):** CORE mengagregasi naskah tesis dan preprint dari ribuan repositori universitas dunia. "
                "Untuk mengaktifkannya, daftarkan email Anda di [core.ac.uk/services/api](https://core.ac.uk/services/api) (gratis), lalu tambahkan `CORE_API_KEY=...` ke file `.env`."
            )

    badge_config = {
        "search_start": ("#3B82F6", "MENCARI"),
        "faculty_start": ("#6366F1", "BIDANG"),
        "query_step": ("#3B82F6", "KATA KUNCI"),
        "paper_found": ("#06B6D4", "DITEMUKAN"),
        "download_start": ("#F59E0B", "MENGUNDUH"),
        "download_ok": ("#10B981", "TERUNDUH"),
        "download_retry": ("#F97316", "COBA LAGI"),
        "download_fail": ("#EF4444", "GAGAL"),
        "skip": ("#94A3B8", "DILEWATI"),
        "duplicate": ("#94A3B8", "SUDAH ADA"),
        "no_pdf": ("#F43F5E", "TIDAK ADA PDF TERBUKA"),
        "extract_start": ("#0EA5E9", "MEMBACA TEKS"),
        "extract_ok": ("#10B981", "TEKS SIAP"),
        "extract_skip": ("#94A3B8", "TEKS SUDAH ADA"),
        "extract_fail": ("#EF4444", "TEKS GAGAL"),
        "analyze_start": ("#8B5CF6", "MENGANALISIS"),
        "analyze_ok": ("#10B981", "TERANALISIS"),
        "analyze_skip": ("#94A3B8", "SUDAH DIANALISIS"),
        "analyze_fail": ("#EF4444", "AI GAGAL"),
    }

    def run_live_harvest_process(harvest_callable, auto_analyze: bool = True):
        console_box = st.container(border=True)
        with console_box:
            st.markdown("#### Proses berjalan")
            status_box = st.empty()
            progress_bar = st.progress(0.05, text="Menginisialisasi koneksi repositori global...")
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            m_found = col_m1.empty()
            m_downloaded = col_m2.empty()
            m_extracted = col_m3.empty()
            m_analyzed = col_m4.empty()

            m_found.metric("Ditemukan", 0, border=True)
            m_downloaded.metric("Diunduh", 0, border=True)
            m_extracted.metric("Teks Siap", 0, border=True)
            m_analyzed.metric("Dianalisis AI", 0, border=True)

            st.markdown("<div style='font-size:0.82rem; font-weight:700; color:#64748B; margin-top:8px; margin-bottom:4px;'>LIVE HARVEST ACTIVITY STREAM:</div>", unsafe_allow_html=True)
            terminal_box = st.empty()

        logs = []
        counters = {"found": 0, "downloaded": 0, "extracted": 0, "analyzed": 0}
        new_papers = []

        def _ui_cb(event_type: str, message: str, data: dict = None):
            now_t = datetime.now().strftime("%H:%M:%S")
            color, b_label = badge_config.get(event_type, ("#64748B", "INFO"))

            # Update metrics
            if event_type == "paper_found":
                counters["found"] += 1
                m_found.metric("Ditemukan", counters["found"], border=True)
                progress_bar.progress(min(0.35, 0.05 + counters["found"] * 0.02), text=f"Menemukan literatur ({counters['found']} naskah)...")
            elif event_type == "download_ok":
                counters["downloaded"] += 1
                m_downloaded.metric("Diunduh", counters["downloaded"], border=True)
                progress_bar.progress(min(0.65, 0.35 + counters["downloaded"] * 0.05), text=f"Mengunduh PDF legal ({counters['downloaded']} file siap)...")
                if data and data.get("title"):
                    new_papers.append(data)
            elif event_type == "extract_ok":
                counters["extracted"] += 1
                m_extracted.metric("Teks Siap", counters["extracted"], border=True)
                progress_bar.progress(min(0.80, 0.65 + counters["extracted"] * 0.03), text=f"Mengekstrak teks naskah ({counters['extracted']} selesai)...")
            elif event_type == "analyze_ok":
                counters["analyzed"] += 1
                m_analyzed.metric("Dianalisis AI", counters["analyzed"], border=True)
                progress_bar.progress(min(0.95, 0.80 + counters["analyzed"] * 0.03), text=f"Membedah naskah utuh ({counters['analyzed']} selesai)...")

            safe_msg = html.escape(message)
            line_html = (
                f"<div style='font-family:\"JetBrains Mono\", monospace; font-size:0.78rem; line-height:1.45; margin-bottom:3px;'>"
                f"<span style='color:#64748B;'>[{now_t}]</span> "
                f"<span style='background:{color}22; color:{color}; border:1px solid {color}44; padding:1px 5px; border-radius:3px; font-weight:700;'>{b_label}</span> "
                f"<span style='color:#CBD5E1;'>{safe_msg}</span>"
                f"</div>"
            )
            logs.append(line_html)
            
            terminal_view = f"""
            <div style='background:#0B0F19; border-radius:6px; padding:10px 12px; height:240px; overflow-y:auto; border:1px solid #1E293B;'>
                {''.join(logs[-25:])}
            </div>
            """
            terminal_box.markdown(terminal_view, unsafe_allow_html=True)

        try:
            status_box.info("**Sedang menjalankan pencarian & pengunduhan naskah...**")
            harvest_stats = harvest_callable(_ui_cb)

            target_files = [p['file'] for p in new_papers if p.get('file')]

            # Step 2: Extraction
            status_box.info("**Mengekstrak teks lengkap dari berkas PDF baru...**")
            try:
                ext_stats = _extract.extract_all(progress_cb=_ui_cb, files=target_files if target_files else None)
            except TypeError:
                ext_stats = _extract.extract_all()

            # Step 3: Analysis
            if auto_analyze and counters["downloaded"] > 0:
                status_box.info(f"**AI ({config.LLM_MODEL}) sedang membedah naskah utuh (Metodologi, Temuan Pembahasan & Kesimpulan)...**")
                try:
                    an_stats = _analyze.analyze_all(model=config.LLM_MODEL, concurrency=4, lang="id", progress_cb=_ui_cb, files=target_files if target_files else None)
                except TypeError:
                    an_stats = _analyze.analyze_all(model=config.LLM_MODEL, concurrency=4, lang="id")

            # Sync DB
            db.sync_all()

            progress_bar.progress(1.0, text="Seluruh tahapan panen, ekstraksi, dan analisis berhasil diselesaikan!")
            status_box.success(
                f"**Panen Berhasil Diselesaikan!** Ditemukan: {counters['found']} | Berhasil Diunduh: **{counters['downloaded']} paper** | "
                f"Teks Siap: **{counters['extracted']}** | Dianalisis AI: **{counters['analyzed']}**."
            )

            if new_papers:
                with st.expander(f"Naskah yang Baru Saja Berhasil Diunduh ({len(new_papers)} Paper)", expanded=True):
                    for p_idx, np in enumerate(new_papers[:8], 1):
                        st.markdown(f"**{p_idx}. {_e(np.get('title'))}** &nbsp; <span style='font-size:0.75rem; color:#64748B;'>`{_e(np.get('file', ''))}`</span>", unsafe_allow_html=True)

        except Exception as e:
            status_box.error(f"Terjadi kesalahan saat proses panen: {e}")

    def run_live_analyze_process(target_files: list[str], model: str, lang: str, workers: int):
        console_box = st.container(border=True)
        with console_box:
            st.markdown("#### Proses analisis berjalan")
            status_box = st.empty()
            progress_bar = st.progress(0.05, text="Memulai pembedahan naskah...")
            col_m1, col_m2 = st.columns(2)
            m_extracted = col_m1.empty()
            m_analyzed = col_m2.empty()
            m_extracted.metric("Teks Disiapkan", 0, border=True)
            m_analyzed.metric("Dianalisis AI", 0, border=True)
            terminal_box = st.empty()

        logs = []
        counters = {"extracted": 0, "analyzed": 0}
        total = len(target_files)

        def _an_cb(event_type: str, message: str, data: dict = None):
            now_t = datetime.now().strftime("%H:%M:%S")
            color, b_label = badge_config.get(event_type, ("#8B5CF6", "AI"))
            if event_type == "extract_ok":
                counters["extracted"] += 1
                m_extracted.metric("Teks Disiapkan", counters["extracted"], border=True)
            elif event_type == "analyze_ok":
                counters["analyzed"] += 1
                m_analyzed.metric("Dianalisis AI", counters["analyzed"], border=True)
                progress_bar.progress(min(1.0, counters["analyzed"] / max(1, total)), text=f"Pembedahan AI: {counters['analyzed']}/{total} paper...")

            safe_msg = html.escape(message)
            line_html = (
                f"<div style='font-family:\"JetBrains Mono\", monospace; font-size:0.78rem; line-height:1.45; margin-bottom:3px;'>"
                f"<span style='color:#64748B;'>[{now_t}]</span> "
                f"<span style='background:{color}22; color:{color}; border:1px solid {color}44; padding:1px 5px; border-radius:3px; font-weight:700;'>{b_label}</span> "
                f"<span style='color:#CBD5E1;'>{safe_msg}</span>"
                f"</div>"
            )
            logs.append(line_html)
            terminal_box.markdown(f"<div style='background:#0B0F19; border-radius:6px; padding:10px 12px; height:220px; overflow-y:auto; border:1px solid #1E293B;'>{''.join(logs[-25:])}</div>", unsafe_allow_html=True)

        try:
            status_box.info(f"Menyiapkan teks naskah untuk {total} berkas...")
            _extract.extract_all(progress_cb=_an_cb, files=target_files)
            status_box.info(f"Membedah {total} naskah dengan AI ({model})...")
            _analyze.analyze_all(model=model, concurrency=workers, lang=lang, force=True, progress_cb=_an_cb, files=target_files)
            db.sync_all()
            progress_bar.progress(1.0, text="Seluruh naskah berhasil dibedah!")
            status_box.success(f"Pembedahan selesai! {counters['analyzed']} paper berhasil dianalisis.")
        except Exception as e:
            status_box.error(f"Terjadi kesalahan: {e}")

    tab_h2, tab_h6, tab_h1, tab_h4, tab_h5, tab_h3 = st.tabs([
        "Cari topik",
        "Telusuri sitasi",
        "Per bidang ilmu",
        "Unggah PDF / DOI",
        "Analisis paper",
        "Kelola bidang ilmu"
    ])

    with tab_h1:
        with st.container(border=True):
            col_cat, col_fac = st.columns([1, 2])
            cat_filter = col_cat.selectbox(
                "Kategori",
                ["Semua Kategori", "Multidisiplin & Terapan", "Filosofis & Teologis", "Kustom Peneliti"],
                key="h_cat_filter"
            )

            filtered_faculties = faculty_list
            if cat_filter != "Semua Kategori":
                filtered_faculties = [f for f in faculty_list if getattr(f, "category", "") == cat_filter]
                if not filtered_faculties:
                    filtered_faculties = faculty_list

            target_fac_id = col_fac.selectbox(
                "Bidang ilmu",
                [f.id for f in filtered_faculties],
                format_func=lambda x: faculty_labels.get(x, x),
                key="h_fac_select"
            )
            target_fac_obj = _faculties.get_faculty(target_fac_id)
            
            st.markdown(
                f"### {_e(target_fac_obj.name)} "
                f"<span style='background:#EEF2FF; color:#4338CA; border:1px solid #C7D2FE; padding:3px 10px; border-radius:9999px; font-size:0.8rem; font-weight:600;'>{_e(getattr(target_fac_obj, 'category', 'Umum'))}</span>",
                unsafe_allow_html=True
            )
            st.caption(target_fac_obj.full_desc or target_fac_obj.short_desc)
            
            st.markdown(f"**Kata kunci yang dicari:** {', '.join([f'`{q}`' for q in target_fac_obj.default_queries])}")
            
            col_hp1, col_hp2 = st.columns([1, 1])
            h_max_per_q = int(col_hp1.number_input("Paper per kata kunci", min_value=2, max_value=25, value=6, key="hp_max"))
            col_hp2.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
            auto_an_fac = col_hp2.checkbox("Langsung analisis setelah diunduh", value=True, key="hp_auto")

            harvest_fac_btn = st.button("Cari & unduh", type="primary", key="btn_harvest_fac", use_container_width=True)

        if harvest_fac_btn:
            run_live_harvest_process(
                lambda cb: _harvest.harvest_faculty(target_fac_id, max_results_per_query=h_max_per_q, workers=4, delay=0.5, progress_cb=cb),
                auto_analyze=auto_an_fac
            )

    with tab_h2:
        with st.container(border=True):
            st.caption("Kata kunci bahasa Inggris memberi hasil paling banyak.")
            
            col_c1, col_c2 = st.columns([3, 1])
            custom_q = col_c1.text_input("Topik atau kata kunci", placeholder="contoh: green accounting, blended learning, islamic microfinance")
            custom_max = int(col_c2.number_input("Jumlah paper", min_value=3, max_value=60, value=10, key="c_max"))

            # Options include all registered faculties + option to create ad-hoc
            fac_dropdown_keys = [f.id for f in faculty_list] + ["_new_faculty_on_the_fly_"]
            def _format_fac_choice(k):
                if k == "_new_faculty_on_the_fly_":
                    return "Bidang baru..."
                return faculty_labels.get(k, k)

            col_cf1, col_cf2 = st.columns([2, 1])
            chosen_fac_key = col_cf1.selectbox("Simpan ke bidang", fac_dropdown_keys, format_func=_format_fac_choice, key="c_fac_select",
                                              index=fac_dropdown_keys.index(selected_faculty_id) if selected_faculty_id in fac_dropdown_keys else 0)
            col_cf2.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
            auto_an_cust = col_cf2.checkbox("Langsung analisis", value=True, key="c_auto")

            effective_fac_id = chosen_fac_key
            if chosen_fac_key == "_new_faculty_on_the_fly_":
                col_nf1, col_nf2 = st.columns([3, 1])
                new_fac_name = col_nf1.text_input("Nama bidang baru", placeholder="contoh: Teknik Arsitektur & Perkotaan", key="nf_name_input")
                new_fac_icon = col_nf2.text_input("Ikon", value="", key="nf_icon_input")

            harvest_cust_btn = st.button("Cari & unduh", type="primary", key="btn_harvest_cust", use_container_width=True)

        if harvest_cust_btn and not custom_q.strip():
            st.error("Isi topik atau kata kunci dulu.")
        elif harvest_cust_btn:
            if chosen_fac_key == "_new_faculty_on_the_fly_":
                if not new_fac_name.strip():
                    st.error("Isi nama bidang baru dulu.")
                    st.stop()
                # Create and register the new faculty permanently
                saved_new_fac = _faculties.save_custom_faculty(
                    name=new_fac_name.strip(),
                    icon=new_fac_icon.strip() or "",
                    default_queries=[custom_q],
                    short_desc=f"Fokus riset {new_fac_name.strip()}",
                    category="Kustom Peneliti"
                )
                effective_fac_id = saved_new_fac.id
                st.success(f"Bidang '{saved_new_fac.name}' tersimpan.")

            run_live_harvest_process(
                lambda cb: _harvest.harvest(custom_q, max_results=custom_max, workers=4, delay=0.5, faculty=effective_fac_id, progress_cb=cb),
                auto_analyze=auto_an_cust
            )

    with tab_h3:
        with st.container(border=True):
            st.caption("Buat bidang ilmu sendiri untuk riset klien, misalnya Manajemen Rumah Sakit atau Hukum Lingkungan. Bidang ini langsung muncul di semua pilihan bidang.")

            col_cf_form1, col_cf_form2 = st.columns([3, 1])
            new_dept_name = col_cf_form1.text_input("Nama bidang ilmu", placeholder="Contoh: Manajemen Rumah Sakit & Layanan Kesehatan", key="reg_fac_name")
            new_dept_icon = col_cf_form2.text_input("Ikon", value="", key="reg_fac_icon")

            col_cf_meta1, col_cf_meta2 = st.columns(2)
            new_dept_category = col_cf_meta1.selectbox("Kategori", ["Multidisiplin & Terapan", "Kustom Peneliti", "Sains & Humaniora"], key="reg_fac_cat")
            new_dept_short = col_cf_meta2.text_input("Deskripsi singkat", placeholder="Contoh: Mutu faskes, akreditasi RS, kepuasan pasien BPJS", key="reg_fac_short")

            new_dept_queries = st.text_area(
                "Kata kunci pencarian (satu per baris)",
                placeholder="hospital administration quality\nbpjs kesehatan patient satisfaction\nlean hospital management clinical governance\nelectronic medical record healthcare adoption",
                key="reg_fac_queries",
                height=110
            )

            if st.button("Simpan bidang ilmu", type="primary", key="btn_save_custom_fac", use_container_width=True):
                if not new_dept_name.strip():
                    st.error("Nama Fakultas/Prodi wajib diisi.")
                elif not new_dept_queries.strip():
                    st.error("Harap masukkan minimal 1 kata kunci panen.")
                else:
                    raw_queries = [q.strip() for line in new_dept_queries.split("\n") for q in line.split(",") if q.strip()]
                    saved_fac = _faculties.save_custom_faculty(
                        name=new_dept_name.strip(),
                        icon=new_dept_icon.strip() or "",
                        default_queries=raw_queries,
                        short_desc=new_dept_short.strip(),
                        category=new_dept_category,
                    )
                    st.success(f"Berhasil mendaftarkan fakultas baru: **{saved_fac.name}** dengan {len(raw_queries)} query terkurasi!")
                    st.rerun()

        st.markdown("#### Bidang ilmu buatan tim")
        custom_list = [f for f in faculty_list if getattr(f, "is_custom", False)]
        if not custom_list:
            st.info("Belum ada. Isi formulir di atas untuk membuat bidang ilmu baru.")
        else:
            for cfac in custom_list:
                cfac_papers = [p for p in all_papers if p.get("faculty") == cfac.id]
                with st.container(border=True):
                    col_info, col_act = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"**{cfac.name}**")
                        st.caption(cfac.short_desc or "Tidak ada deskripsi.")
                        st.markdown(f"**Query Terdaftar:** {', '.join([f'`{q}`' for q in cfac.default_queries])}")
                        st.markdown(f"<span style='font-size:0.8rem; color:#64748B;'>Paper di Database: <b>{len(cfac_papers)} paper</b></span>", unsafe_allow_html=True)

                    with col_act:
                        if st.button("Cari & unduh", key=f"btn_harvest_cf_{cfac.id}", use_container_width=True):
                            run_live_harvest_process(
                                lambda cb: _harvest.harvest_faculty(cfac.id, max_results_per_query=5, workers=4, delay=0.5, progress_cb=cb),
                                auto_analyze=True
                            )

                        if st.button("Hapus bidang", key=f"btn_del_cf_{cfac.id}", use_container_width=True):
                            _faculties.delete_custom_faculty(cfac.id)
                            st.warning(f"Bidang '{cfac.name}' dihapus.")
                            st.rerun()

    with tab_h6:
        render_snowball_tab()

    with tab_h4:
        with st.container(border=True):
            st.caption("Pakai ini untuk paper yang tidak ketemu lewat pencarian: PDF yang Anda punya, atau paper yang Anda tahu DOI-nya.")

            col_m_up, col_m_doi = st.columns(2)

            with col_m_up:
                st.markdown("#### Unggah PDF")
                uploaded_pdf = st.file_uploader("File PDF", type=["pdf"], key="manual_pdf_upload")
                manual_title = st.text_input("Judul (opsional)", placeholder="Jika kosong, memakai nama file", key="manual_title_input")
                manual_fac = st.selectbox("Simpan ke bidang", [f.id for f in faculty_list], format_func=lambda x: faculty_labels.get(x, x), key="manual_fac_select")
                auto_an_upload = st.checkbox("Langsung analisis", value=True, key="manual_auto_an")

                if st.button("Unggah", type="primary", key="btn_import_pdf", use_container_width=True):
                    if not uploaded_pdf:
                        st.error("Pilih file PDF dulu.")
                    else:
                        with st.spinner("Menyimpan PDF dan mengekstrak teks..."):
                            res = _harvest.import_local_pdf(
                                file_bytes=uploaded_pdf.read(),
                                filename=uploaded_pdf.name,
                                title=manual_title,
                                faculty=manual_fac
                            )
                            st.success(f"Berhasil mengimpor: {res['title']}!")

                        if auto_an_upload:
                            with st.spinner("Menganalisis paper ini..."):
                                _analyze.analyze_single_paper(res["file"], model=config.LLM_MODEL, lang="id")
                                st.success("Analisis selesai.")

                        db.sync_all()
                        st.rerun()

            with col_m_doi:
                st.markdown("#### Dari DOI")
                input_doi = st.text_input("DOI atau link DOI", placeholder="contoh: 10.1007/s11153-021-09800-4", key="manual_doi_input")
                doi_fac = st.selectbox("Simpan ke bidang", [f.id for f in faculty_list], format_func=lambda x: faculty_labels.get(x, x), key="doi_fac_select")
                auto_an_doi = st.checkbox("Langsung analisis", value=True, key="doi_auto_an")
                st.caption("Hanya berhasil kalau paper punya versi terbuka (open access).")

                if st.button("Cari & unduh", type="primary", key="btn_import_doi", use_container_width=True):
                    if not input_doi.strip():
                        st.error("Isi DOI dulu.")
                    else:
                        with st.spinner("Mencari versi terbuka paper ini..."):
                            doi_res = _harvest.import_by_doi(doi=input_doi, faculty=doi_fac)
                            if "error" in doi_res:
                                st.error(doi_res["error"])
                            else:
                                st.success(f"Berhasil mengunduh: {doi_res['title']}!")
                                if auto_an_doi:
                                    with st.spinner("Menganalisis paper ini..."):
                                        _analyze.analyze_single_paper(doi_res["file"], model=config.LLM_MODEL, lang="id")
                                        st.success("Analisis selesai.")
                                db.sync_all()
                                st.rerun()

    with tab_h5:
        st.caption("Analisis paper yang belum dianalisis, atau ulangi analisis paper tertentu.")

        unanalyzed_all = [p for p in all_papers if not p.get("thesis")]
        analyzed_all = [p for p in all_papers if p.get("thesis")]

        st.progress(len(analyzed_all) / len(all_papers) if all_papers else 0.0,
                    text=f"{len(analyzed_all)} dari {len(all_papers)} paper sudah dianalisis")

        tab_sub1, tab_sub2 = st.tabs([
            f"Belum dianalisis ({len(unanalyzed_all)})",
            "Analisis ulang"
        ])

        with tab_sub1:
            if not unanalyzed_all:
                st.success("Semua paper sudah dianalisis.")
            else:
                with st.container(border=True):
                    st.caption("AI membaca naskah utuh lalu mengekstrak tesis, metodologi, temuan, dan kutipan dengan nomor halaman. Sekitar 1 menit per paper.")

                    col_opt1, col_opt2, col_opt3 = st.columns([2, 1, 1])
                    studio_model = col_opt1.selectbox("Model AI", [config.LLM_MODEL, "gemini-3-8-flash", "gemini-2.5-flash"], index=0, key="studio_model_opt")
                    studio_workers = col_opt2.slider("Paper sekaligus", min_value=1, max_value=6, value=4, key="studio_workers_opt")
                    studio_lang = col_opt3.selectbox("Bahasa hasil", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English", key="studio_lang_opt")

                    # Multi-select options
                    unanalyzed_dict = {p.get("file"): f"{p.get('title') or p.get('file')} ({p.get('year', 'n.d.')})" for p in unanalyzed_all}
                    chosen_targets = st.multiselect(
                        "Pilih paper (kosongkan untuk semua)",
                        options=list(unanalyzed_dict.keys()),
                        format_func=lambda x: unanalyzed_dict.get(x, x),
                        key="studio_chosen_targets"
                    )

                    target_files = chosen_targets if chosen_targets else list(unanalyzed_dict.keys())
                    btn_text = f"Analisis {len(target_files)} paper terpilih" if chosen_targets else f"Analisis semua ({len(unanalyzed_all)})"

                    if st.button(btn_text, type="primary", key="btn_run_studio_batch", use_container_width=True):
                        run_live_analyze_process(
                            target_files=target_files,
                            model=studio_model,
                            lang=studio_lang,
                            workers=studio_workers
                        )
                        st.rerun()

                st.markdown("##### Daftar paper")
                for u_idx, up in enumerate(unanalyzed_all, 1):
                    with st.container(border=True):
                        col_ui1, col_ui2 = st.columns([3, 1])
                        u_fac = _faculties.get_faculty(up.get("faculty") or "ilahiyyat")
                        u_icon = u_fac.icon if u_fac else ""
                        u_fname = u_fac.name if u_fac else (up.get("faculty") or "Umum")
                        with col_ui1:
                            st.markdown(f"**{u_idx}. {up.get('title') or up.get('file')}**")
                            st.caption(f"{u_fname} · {up.get('year', 'n.d.')}")
                        with col_ui2:
                            if st.button("Analisis", key=f"btn_single_studio_{u_idx}_{up.get('file')}", use_container_width=True):
                                with st.spinner(f"Menganalisis '{(up.get('title') or '')[:30]}...'"):
                                    try:
                                        _analyze.analyze_single_paper(up.get("file"), model=studio_model, lang=studio_lang)
                                        db.sync_all()
                                        st.success("Analisis berhasil!")
                                        st.rerun()
                                    except Exception as err:
                                        st.error(f"Gagal analisis: {err}")

        with tab_sub2:
            with st.container(border=True):
                st.caption("Pilih paper untuk dianalisis ulang, misalnya kalau hasil sebelumnya kurang lengkap.")

                all_file_map = {p.get("file"): f"[{'' if p.get('thesis') else ''}] {p.get('title') or p.get('file')} ({p.get('year', 'n.d.')})" for p in all_papers}
                chosen_file = st.selectbox(
                    "Paper",
                    options=list(all_file_map.keys()),
                    format_func=lambda x: all_file_map.get(x, x),
                    key="studio_single_chosen"
                )

                if chosen_file:
                    target_rec = next((p for p in all_papers if p.get("file") == chosen_file), None)
                    if target_rec:
                        if target_rec.get("thesis"):
                            st.info(f"**Tesis saat ini:** {target_rec.get('thesis')}")
                        else:
                            st.caption("Paper ini belum dianalisis.")

                        col_re1, col_re2 = st.columns(2)
                        re_model = col_re1.selectbox("Model LLM:", [config.LLM_MODEL, "gemini-3-8-flash", "gemini-2.5-flash"], key="re_model_single")
                        re_lang = col_re2.selectbox("Bahasa Analisis:", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English", key="re_lang_single")

                        if st.button("Analisis ulang", type="primary", key="btn_exec_single_re", use_container_width=True):
                            with st.spinner(f"Menganalisis naskah '{chosen_file}' dengan {re_model}..."):
                                try:
                                    _analyze.analyze_single_paper(chosen_file, model=re_model, lang=re_lang, force=True)
                                    db.sync_all()
                                    st.success(f"Pembedahan ulang selesai untuk: {chosen_file}")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"Gagal analisis: {err}")


# -------------------------------------------------------------
# Module 7: Full-Text Search
# -------------------------------------------------------------
elif menu == "Full-Text Search":
    render_hero(
        title="Pencarian Cerdas Korpus (Hybrid Semantic & FTS5)",
        subtitle="Pencarian berbobot multi-dimensi (judul, tesis, premis) dipadukan dengan ekspansi semantik RRF.",
        icon="",
        badges=[
            {"icon": "", "text": "FTS5 BM25 Weighted", "class": "hero-badge-primary"},
            {"icon": "", "text": "Hybrid RRF Semantic", "class": "hero-badge-accent"}
        ]
    )

    with st.container(border=True):
        col_s1, col_s2 = st.columns([3, 1])
        search_query = col_s1.text_input("Ketik Kata Kunci / Pertanyaan Riset:", placeholder="contoh: apakah alam semesta punya awal mula, causality, hilbert, theodicy...")
        limit_count = col_s2.slider("Maksimal Hasil:", min_value=3, max_value=20, value=8)
        use_hybrid = st.checkbox("Gunakan Hybrid Semantic RRF (Paham Bahasa Indonesia & Konsep Abstrak)", value=True)

    if search_query:
        with st.spinner("Mencari paper yang relevan..."):
            if use_hybrid:
                results = _retrieval.hybrid_search(search_query, limit=limit_count, expand_concepts=True)
            else:
                results = db.search(search_query, limit=limit_count)

        if not results:
            st.warning(f"Tidak ada paper yang cocok dengan kata kunci: '{search_query}'")
        else:
            mode_badge = "Hybrid RRF Semantic" if use_hybrid else "Exact Weighted FTS5"
            st.success(f"Ditemukan **{len(results)}** paper relevan via **{mode_badge}**:")
            for r in results:
                with st.container(border=True):
                    st.markdown(f"#### {r.get('title')} ({r.get('year', 'n.d.')})")
                    score_txt = f" | RRF Score: `{r.get('rrf_score')}`" if "rrf_score" in r else ""
                    st.caption(f"Tipe: `{r.get('argument_type') or '-'}` | Stance: `{r.get('supports_or_critiques') or '-'}` | Fakultas: `{r.get('faculty') or '-'}`{score_txt}")
                    if r.get("thesis"):
                        st.info(f"**Tesis Utama:** {r.get('thesis')}")
                    if r.get("key_objection"):
                        st.warning(f"**Objeksi Kunci:** {r.get('key_objection')}")
                    if r.get("snippet"):
                        st.markdown(f"**Kutipan Teks:** ...*{r.get('snippet')}*...")
                    if r.get("file"):
                        try:
                            passages = _retrieval.find_grounded_passages(r["file"], search_query, top_k=1)
                            if passages:
                                psg = passages[0]
                                psg_text = html.escape(psg['verbatim'])
                                st.caption(f"📍 **{psg['page_label']}**: *\"{psg_text}\"*")
                        except Exception:
                            pass


# -------------------------------------------------------------
# Module 8: Diagram Argumen
# -------------------------------------------------------------
elif menu == "Diagram Argumen":
    render_hero(
        title="Visualisasi Pohon Argumen (Mermaid)",
        subtitle="Visualisasi alur silogisme formal secara grafis: Tesis → Premis → Kesimpulan → Objeksi → Pertahanan.",
        icon="",
        badges=[
            {"icon": "", "text": "Formal Syllogism Graph", "class": "hero-badge-primary"},
            {"icon": "", "text": "Counter-Argument Topology", "class": "hero-badge-accent"}
        ]
    )

    paper_choices = [p["file"] for p in papers if p.get("thesis")]
    if not paper_choices:
        st.warning("Belum ada paper yang selesai dianalisis di fakultas ini.")
    else:
        with st.container(border=True):
            selected_file = st.selectbox("Pilih Paper untuk Divisualisasikan:", paper_choices)
        
        stem = Path(selected_file).stem
        mermaid_code = export.generate_mermaid_graph(stem)

        st.markdown(f"### Diagram Logika: *{stem}*")
        render_mermaid(mermaid_code)

        with st.expander("Lihat Kode Sumber Mermaid"):
            st.code(mermaid_code, language="mermaid")


# -------------------------------------------------------------
# Module 9: Laporan Sintesis & Celah Riset
# -------------------------------------------------------------
elif menu == "Laporan Sintesis":
    render_hero(
        title="Laporan Sintesis",
        subtitle="Tinjauan pustaka dari seluruh koleksi, serta celah riset dan usulan topik baru.",
        icon="",
    )

    tab_synth1, tab_synth2 = st.tabs([
        "Tinjauan pustaka",
        "Celah riset & kebaruan"
    ])

    with tab_synth1:
        with st.container(border=True):
            col_s1, col_s2 = st.columns([1, 1])
            lang_choice = col_s1.selectbox("Bahasa", ["id", "en"], format_func=lambda x: "Bahasa Indonesia" if x == "id" else "English")
            
            col_s2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            gen_synth = col_s2.button("Buat tinjauan pustaka baru", type="primary", use_container_width=True)

        if gen_synth:
            with st.spinner("Menyusun tinjauan pustaka dari seluruh koleksi. Bisa beberapa menit..."):
                res = _synthesize.synthesize(model=config.LLM_MODEL, lang=lang_choice)
                st.success("Laporan selesai.")

        st.markdown("#### Laporan tersimpan")
        reports = sorted(list(config.SYNTH_DIR.glob("*.md")), reverse=True)
        if not reports:
            st.info("Belum ada laporan. Klik **Buat tinjauan pustaka baru**.")
        else:
            with st.container(border=True):
                selected_rep = st.selectbox("Pilih laporan", [r.name for r in reports])
                rep_file = config.SYNTH_DIR / selected_rep
                with st.container(height=600):
                    st.markdown(rep_file.read_text(encoding="utf-8"))
            render_client_delivery(rep_file, key=f"synth_{rep_file.stem}")

    with tab_synth2:
        with st.container(border=True):
            st.caption("AI membaca seluruh koleksi, lalu mencari perdebatan yang belum selesai, kelemahan metodologi, dan menyusun 3 usulan topik riset baru.")

            col_gap1, col_gap2 = st.columns([2, 1])
            gap_focus = col_gap1.text_input("Fokus (opsional)", placeholder="contoh: dampak terhadap UMKM di daerah")
            gap_model = col_gap2.selectbox("Kecepatan", ["deepseek-v4-pro", "gemini-3-8-flash"], format_func=lambda x: "Mendalam" if "deepseek" in x else "Cepat")

            btn_find_gap = st.button("Cari celah riset", type="primary", use_container_width=True)

        if btn_find_gap:
            with st.spinner("Membaca koleksi dan mencari celah riset. Bisa beberapa menit..."):
                gap_report = _gap_finder.find_research_gaps(
                    faculty_id=selected_faculty_id,
                    custom_focus=gap_focus,
                    model=gap_model
                )
                st.session_state["current_gap_report"] = gap_report
                saved_gap = _gap_finder.save_gap_report(gap_report)
                st.session_state["saved_gap_paths"] = saved_gap

        if "current_gap_report" in st.session_state:
            rep = st.session_state["current_gap_report"]
            saved_paths = st.session_state.get("saved_gap_paths", {})

            with st.container(border=True):
                st.markdown(f"#### Bidang: {rep.get('faculty_domain')}")
                st.info(f"**Ringkasan:**\n\n{rep.get('executive_summary', '')}")

                col_gp1, col_gp2 = st.columns(2)
                with col_gp1:
                    st.markdown("**Yang sudah disepakati**")
                    for c in rep.get("established_consensus", []):
                        st.markdown(f"- {c}")
                with col_gp2:
                    st.markdown("**Kelemahan metodologi**")
                    for b in rep.get("methodological_blindspots", []):
                        st.markdown(f"- {b}")

                st.markdown("---")
                st.markdown("#### Perdebatan yang belum selesai")
                for idx_ut, ut in enumerate(rep.get("unresolved_tensions", []), 1):
                    with st.expander(f"{idx_ut}. {ut.get('issue', 'Isu perdebatan')}", expanded=False):
                        st.write(f"**Pihak yang mendukung:** {ut.get('thesis_side')}")
                        st.write(f"**Pihak yang mengkritik:** {ut.get('antithesis_side')}")
                        st.warning(f"**Mengapa belum selesai:** {ut.get('why_stuck')}")

                st.markdown("---")
                st.markdown("#### Usulan topik riset baru")
                for idx_p, prop in enumerate(rep.get("novel_research_proposals", []), 1):
                    with st.container(border=True):
                        st.markdown(f"**Usulan {idx_p}: {prop.get('title')}**")
                        col_pr1, col_pr2 = st.columns([1, 1])
                        col_pr1.caption(f"Jenjang: {prop.get('target_level', 'Tesis S2/S3')}")
                        col_pr2.caption(f"Kerangka teori: {prop.get('theoretical_framework', '-')}")
                        
                        st.write(f"**Celah yang dijawab:** {prop.get('gap_addressed')}")
                        st.write(f"**Hipotesis:** {prop.get('proposed_hypothesis')}")
                        st.write(f"**Kebaruan:** {prop.get('expected_novelty')}")
                        
                        if prop.get("research_questions"):
                            st.markdown("**Rumusan masalah:**")
                            for q in prop["research_questions"]:
                                st.markdown(f"- {q}")

                if saved_paths.get("md_path"):
                    col_g_dl1, col_g_dl2 = st.columns(2)
                    with col_g_dl1:
                        st.download_button(
                            "Unduh laporan celah riset (.md)",
                            data=saved_paths["markdown_content"],
                            file_name=saved_paths["md_path"].name,
                            mime="text/markdown",
                            use_container_width=True
                        )
                    with col_g_dl2:
                        st.caption(f"Tersimpan sebagai `{saved_paths['md_path'].name}`")


# -------------------------------------------------------------
# Module 10: Ekspor Data & Flashcards
# -------------------------------------------------------------
elif menu == "Pusat Akurasi":
    render_accuracy_page()

elif menu == "Ekspor Data & Flashcards":
    render_hero(
        title="Ekspor Data & Kartu Active Recall",
        subtitle="Integrasi korpus CosmoLab University ke Zotero, Mendeley, Obsidian Vault, dan Anki untuk alur riset berkelanjutan.",
        icon="",
        badges=[
            {"icon": "", "text": "BibTeX & RIS Integration", "class": "hero-badge-primary"},
            {"icon": "", "text": "Obsidian [[Wikilinks]]", "class": "hero-badge-accent"},
            {"icon": "", "text": "Anki Active Recall", "class": "hero-badge-model"}
        ]
    )

    col_e1, col_e2, col_e3, col_e4 = st.columns(4)

    with col_e1:
        with st.container(border=True):
            st.markdown("### Ekspor BibTeX")
            st.write("Format standar untuk **LaTeX & Zotero**.")
            if st.button("Generate .bib", use_container_width=True):
                bib_path = export.export_bibtex()
                st.success(f"Berhasil!")
                st.download_button(
                    "Unduh .bib",
                    data=bib_path.read_text(encoding="utf-8"),
                    file_name="references.bib",
                    mime="text/plain",
                    use_container_width=True
                )

    with col_e2:
        with st.container(border=True):
            st.markdown("### Ekspor RIS")
            st.write("Format standar untuk **Zotero & Mendeley**.")
            if st.button("Generate .ris", use_container_width=True):
                all_p = db.get_all_papers_with_analyses()
                ris_path = _citations.export_ris(all_p)
                st.success(f"Berhasil!")
                st.download_button(
                    "Unduh .ris",
                    data=ris_path.read_text(encoding="utf-8"),
                    file_name="references.ris",
                    mime="text/plain",
                    use_container_width=True
                )

    with col_e3:
        with st.container(border=True):
            st.markdown("### Ekspor Obsidian")
            st.write("Catatan Markdown berformat `[[wikilinks]]`.")
            if st.button("Generate Vault", use_container_width=True):
                vault_path = export.export_obsidian()
                st.success(f"Berhasil!")
                st.info("Buka Obsidian, lalu pilih **Open folder as vault** ke `data/obsidian`.")

    with col_e4:
        with st.container(border=True):
            st.markdown("### Active Recall")
            st.write("Flashcards Spaced Repetition untuk **Anki**.")
            if st.button("Generate Cards", use_container_width=True):
                fc_path = export.export_flashcards_to_obsidian()
                st.success(f"Berhasil!")
                st.download_button(
                    "Unduh Cards.md",
                    data=fc_path.read_text(encoding="utf-8"),
                    file_name="Cosmology_Active_Recall_Cards.md",
                    mime="text/plain",
                    use_container_width=True
                )
