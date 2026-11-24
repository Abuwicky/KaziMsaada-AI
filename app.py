"""KaziMsaada AI — local Streamlit career-readiness workspace.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from components.career_pages import (
    render_guidance_page,
    render_interview_page,
    render_job_search_page,
    render_skills_page,
)
from components.cv_components import render_cv_builder
from components.dashboard import render_dashboard
from components.profile_components import render_profile_page
from components.settings import render_settings_page
from components.sidebar import render_sidebar
from components.ui import read_asset, show_flash
from core import APP_DISPLAY_NAME, APP_TAGLINE, APP_VERSION, BUILD_STAMP
from core.auth import require_workspace_owner, workspace_label
from core.database import initialize_database, migrate_json_profiles
from core.profiles import load_profiles
from core.workspace import get_current_owner_id

st.set_page_config(
    page_title=f"{APP_DISPLAY_NAME} · Career Readiness",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="auto",
)


def _inject_styles() -> None:
    css = read_asset("styles.css")
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _bootstrap_database() -> dict:
    """Create tables and run the JSON migration once per Streamlit process."""

    initialize_database()
    return migrate_json_profiles()


def _friendly_failure(title: str, message: str, error: Exception | None = None) -> None:
    st.error(f"{title} {message}")
    if error is not None:
        with st.expander("Technical details"):
            st.code(f"{type(error).__name__}: {error}", language=None)
    if st.button("Try again", key="global_retry"):
        st.rerun()


_inject_styles()

# Privacy gate: resolve the signed-in owner before any database access. When
# sign-in is required, this stops the script until authentication succeeds.
require_workspace_owner()
_owner = get_current_owner_id()
_previous_owner = st.session_state.get("_workspace_owner")
if _previous_owner and _previous_owner != _owner:
    # Never carry one person's in-memory drafts or selection into another
    # person's workspace after an account switch.
    for _key in list(st.session_state.keys()):
        if _key != "_workspace_owner":
            del st.session_state[_key]
st.session_state["_workspace_owner"] = _owner

try:
    migration_result = _bootstrap_database()
except sqlite3.Error as error:
    st.markdown(
        f'<div class="km-page-head"><div class="km-eyebrow">KaziMsaada AI</div>'
        f"<h1>Database unavailable</h1></div>",
        unsafe_allow_html=True,
    )
    _friendly_failure(
        "KaziMsaada AI could not open the local database.",
        "Your existing data has not been changed. Check that the data folder is "
        "readable, then try again.",
        error,
    )
    st.stop()
except Exception as error:
    st.markdown(
        f'<div class="km-page-head"><div class="km-eyebrow">KaziMsaada AI</div>'
        f"<h1>Startup check failed</h1></div>",
        unsafe_allow_html=True,
    )
    _friendly_failure(
        "The workspace could not finish its startup checks.",
        "No data was changed. Please review the technical details and try again.",
        error,
    )
    st.stop()

try:
    profiles = load_profiles()
except sqlite3.Error as error:
    profiles = None
    profile_error = error
except Exception as error:  # Keep the interface usable if storage is malformed.
    profiles = None
    profile_error = error
else:
    profile_error = None

if profiles is None:
    st.markdown(
        '<div class="km-page-head"><div class="km-eyebrow">KaziMsaada AI</div>'
        "<h1>Saved profiles could not be loaded</h1></div>",
        unsafe_allow_html=True,
    )
    _friendly_failure(
        "The profile list could not be read.",
        "Your database has not been modified. This may be a temporary file-lock "
        "or permissions issue.",
        profile_error,
    )
    st.stop()

if migration_result.get("status") in {"source_error", "database_error"}:
    st.warning(
        "The one-time JSON profile migration could not run. Your existing "
        "database profiles are still available."
    )
    with st.expander("Migration details"):
        st.code(
            f"Status: {migration_result.get('status')}\n"
            f"Detail: {migration_result.get('error')}",
            language=None,
        )

page = render_sidebar(profiles)
show_flash()

if page == "Dashboard":
    render_dashboard(profiles)
elif page == "My Profile":
    render_profile_page(profiles)
elif page == "CV Builder":
    render_cv_builder(profiles)
elif page == "Interview Preparation":
    render_interview_page(profiles)
elif page == "Skills Assessment":
    render_skills_page(profiles)
elif page == "Career Guidance":
    render_guidance_page(profiles)
elif page == "Job Search Support":
    render_job_search_page(profiles)
elif page == "Settings":
    render_settings_page(profiles)
else:
    st.session_state["page"] = "Dashboard"
    st.session_state["nav"] = "Dashboard"
    st.rerun()

st.markdown(
    f"""
    <div class="km-footer">
      <span>{APP_DISPLAY_NAME} · {APP_TAGLINE}</span>
      <span>{workspace_label()} · v{APP_VERSION} · {BUILD_STAMP}</span>
    </div>
    """,
    unsafe_allow_html=True,
)
