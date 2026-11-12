"""Shared dashboard pieces: logo paths, HTML escaping, hero, tables, diagrams, client delivery."""

import re
import html
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from cosmolab import verify as _verify
from cosmolab import deliverables as _deliverables


# Logo files live in cosmolab/assets/
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


LOGO_MARK_PNG = ASSETS_DIR / "logo-mark.png"


LOGO_LIGHT_PNG = ASSETS_DIR / "logo-light.png"


def _svg_data_uri(path: Path) -> str:
    import base64
    try:
        return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


LOGO_MARK_URI = _svg_data_uri(ASSETS_DIR / "logo-mark.svg")


def _e(value) -> str:
    """Escape text from papers, AI output or users before it goes into raw HTML."""
    return html.escape("" if value is None else str(value))


def _safe_url(url) -> str:
    """Allow only http(s) links in raw HTML."""
    url = str(url or "")
    return html.escape(url) if url.lower().startswith(("http://", "https://")) else "#"


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


def _badge(text: str, tone: str = "muted", icon: str = "") -> str:
    """Small colored pill. Tones: good, bad, mix, warn, info, teal, muted."""
    dot = f"<span class='cl-badge-dot'>{icon}</span>" if icon else "<span class='cl-badge-dot'></span>"
    return f"<span class='cl-badge {tone}'>{dot}{_e(text)}</span>"
