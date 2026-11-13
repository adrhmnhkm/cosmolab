"""CosmoLab dashboard entry point (`cosmolab ui`).

Sets up the page, team login, and theme, draws the sidebar, then hands off
to the page module for the selected menu entry (cosmolab/ui/pages/).
"""

import importlib
import streamlit as st
from cosmolab import config
from cosmolab import db
from cosmolab import faculties as _faculties
from cosmolab import ask_agent as _ask_agent
from cosmolab import sparring as _sparring
from cosmolab import curriculum as _curriculum
from cosmolab import harvest as _harvest
from cosmolab import extract as _extract
from cosmolab import analyze as _analyze
from cosmolab import synthesize as _synthesize
from cosmolab import writer as _writer
from cosmolab import matrix as _matrix
from cosmolab import citations as _citations
from cosmolab import gap_finder as _gap_finder
from cosmolab import inspector as _inspector
from cosmolab import retrieval as _retrieval
from cosmolab import verify as _verify
from cosmolab import deliverables as _deliverables
from cosmolab import entail as _entail
from cosmolab import analysis_check as _acheck
from cosmolab import corrections as _corrections
from cosmolab import metadata as _metadata
from cosmolab import evaluate as _evaluate
from cosmolab import audit as _audit

from cosmolab.ui.components import ASSETS_DIR, LOGO_LIGHT_PNG, LOGO_MARK_PNG
from cosmolab.ui import pages
from cosmolab.ui import reload as _ui_reload

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
# Pages and the modules they use, including pages added since the server started.
_ui_reload.reload_ui()
from cosmolab.ui.sidebar import build_sidebar  # noqa: E402  (after the reload, so the new version is used)


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


# -------------------------------------------------------------
# Modern Design System & CSS
# -------------------------------------------------------------
# The stylesheet lives in cosmolab/assets/theme.css.
st.markdown(
    "\n<style>\n" + (ASSETS_DIR / "theme.css").read_text(encoding="utf-8") + "</style>\n",
    unsafe_allow_html=True,
)


# Menu entry (stored in st.session_state["active_nav_menu"]) -> page module.
PAGES = {
    "Beranda": pages.home,
    "Paper Explorer & Korpus": pages.explorer,
    "Roadmap Belajar & Kurikulum": pages.roadmap,
    "Arena Sparring Nalar": pages.sparring,
    "Tanya Korpus & Sintesis": pages.ask,
    "Review Draf Mahasiswa": pages.review,
    "Latihan Sidang": pages.defense,
    "Studio Artikel Siap Baca": pages.studio,
    "Bedah DOI Seketika": pages.doi,
    "Panen Paper Ilmiah": pages.harvest,
    "Full-Text Search": pages.fulltext,
    "Diagram Argumen": pages.diagram,
    "Laporan Sintesis": pages.synthesis,
    "Pusat Akurasi": pages.accuracy,
    "Ekspor Data & Flashcards": pages.export,
}

ctx = build_sidebar()
page = PAGES.get(ctx.menu)
if page:
    page.render(ctx)
