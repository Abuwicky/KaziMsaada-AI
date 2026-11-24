"""Settings, local workspace information, and developer diagnostics."""

from __future__ import annotations

import html
import json
import platform
import sqlite3

import streamlit as st

from core import (
    APP_DISPLAY_NAME,
    APP_VERSION,
    BUILD_STAMP,
    DATABASE_FILE,
)
from core.ai_client import ai_status, load_ai_settings
from core.auth import (
    is_authenticated,
    persistence_note,
    privacy_summary,
    workspace_label,
)
from core.cv import TEMPLATES, list_saved_cvs
from core.database import get_database_connection
from core.privacy import delete_owner_data, export_owner_data
from core.workspace import current_cv_dir

from .ui import format_date, icon, page_header, set_flash, sub_section


def _workspace_card(title: str, value: str, caption: str, icon_name: str) -> str:
    return f"""
    <div class="km-settings-card">
      <div class="km-settings-icon">{icon(icon_name, 20)}</div>
      <div>
        <span>{html.escape(title)}</span>
        <strong>{html.escape(value)}</strong>
        <em>{html.escape(caption)}</em>
      </div>
    </div>
    """


def render_settings_page(profiles: list[dict]) -> None:
    page_header(
        "Settings",
        "Workspace and data",
        "See where your data lives, what is stored, and how to export or delete a "
        "complete copy of your personal workspace.",
    )

    cvs = list_saved_cvs()

    col_one, col_two, col_three = st.columns(3)
    with col_one:
        st.markdown(
            _workspace_card(
                "Profiles",
                f"{len(profiles)} saved",
                "Stored in the workspace SQL database",
                "user",
            ),
            unsafe_allow_html=True,
        )
    with col_two:
        st.markdown(
            _workspace_card(
                "CV documents",
                f"{len(cvs)} PDF files",
                "Text and PDF copies in the CV folder",
                "file",
            ),
            unsafe_allow_html=True,
        )
    with col_three:
        st.markdown(
            _workspace_card(
                "Application",
                f"Version {APP_VERSION}",
                f"Build {BUILD_STAMP}",
                "settings",
            ),
            unsafe_allow_html=True,
        )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)

    left, right = st.columns([1.2, 1], gap="large")

    with left:
        sub_section("Data and privacy")
        st.markdown(
            f"""
            <div class="km-privacy">
              <div class="km-privacy-row">
                <span class="km-status-dot"></span>
                <div><strong>{html.escape(workspace_label())}</strong>
                <p>{html.escape(privacy_summary())}</p></div>
              </div>
              <div class="km-privacy-row">
                <span class="km-status-dot"></span>
                <div><strong>Storage can be temporary.</strong>
                <p>{html.escape(persistence_note())}</p></div>
              </div>
              <div class="km-privacy-row">
                <span class="km-status-dot"></span>
                <div><strong>AI is optional and scoped.</strong>
                <p>If AI practice features are enabled, only the interview practice
                details needed for that action are sent to the configured provider.
                Profile and CV documents are not sent.</p></div>
              </div>
              <div class="km-privacy-row">
                <span class="km-status-dot"></span>
                <div><strong>You control exports and deletion.</strong>
                <p>An export is created only when you click the download button.
                Delete removes your profiles, practice history, bookings and CV
                files from this workspace.</p></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        sub_section("Download a full copy of my data")
        st.caption(
            "This JSON export contains personal career information, practice "
            "history, bookings and CV draft details. Store it somewhere private "
            "and delete it when it is no longer needed."
        )
        export_payload = export_owner_data()
        export = json.dumps(export_payload, indent=2, ensure_ascii=False).encode("utf-8")
        st.download_button(
            "Download my data as JSON",
            data=export,
            file_name="kazimsaada_my_data_export.json",
            mime="application/json",
            key="settings_export_all",
        )
        if not profiles:
            st.caption("The export currently contains no saved profiles.")

        sub_section("Delete my data")
        st.warning(
            "This permanently removes the profiles, CV drafts, interview and "
            "skills history, and mentor bookings in this workspace. Generated CV "
            "files are deleted too. Approved public mentor directory entries are "
            "kept, but their link to your profile and private supporting "
            "information are removed."
        )
        delete_confirm = st.text_input(
            "Type DELETE to confirm",
            key="settings_delete_confirm",
            placeholder="DELETE",
        )
        delete_clicked = st.button(
            "Delete all my workspace data",
            type="secondary",
            disabled=delete_confirm.strip().upper() != "DELETE",
            key="settings_delete_button",
        )
        if delete_clicked:
            try:
                deleted = delete_owner_data()
            except sqlite3.Error as error:
                st.error("Your data could not be deleted. Please try again.")
                with st.expander("Technical details"):
                    st.code(f"{type(error).__name__}: {error}", language=None)
            else:
                st.session_state.pop("active_profile_id", None)
                st.session_state.pop("cv_drafts", None)
                set_flash(
                    "Workspace data deleted: "
                    f"{deleted['profiles']} profile(s), "
                    f"{deleted['interview_sessions']} interview session(s), "
                    f"{deleted['skill_assessments']} assessment(s), "
                    f"{deleted['mentor_bookings']} booking(s) and "
                    f"{deleted['cv_files']} CV file(s).",
                    "success",
                )
                st.rerun()

        sub_section("CV templates")
        st.caption(
            "Templates change presentation only. Always check the final PDF in the "
            "employer's application portal before submitting it."
        )
        for meta in TEMPLATES.values():
            st.markdown(
                f"""
                <div class="km-template-row">
                  <span class="km-template-swatch" style="background:{meta['accent']}"></span>
                  <div>
                    <strong>{html.escape(meta['name'])}</strong>
                    <span>{html.escape(meta['description'])}</span>
                    <span>Best for: {html.escape(meta.get('best_for', 'General use'))} ·
                    Layout: {html.escape(meta.get('ats', 'Single column'))}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        sub_section("Local paths")
        st.caption("Database")
        st.code(str(DATABASE_FILE), language=None)
        st.caption("CV folder")
        st.code(str(current_cv_dir()), language=None)
        st.caption("Original JSON backup")
        st.code(str(DATABASE_FILE.parent / "profiles.json"), language=None)

        sub_section("CV library")
        if cvs:
            for cv in cvs[:6]:
                st.markdown(
                    f"**{html.escape(cv['name'])}**  \n"
                    f"{cv['modified'].strftime('%d %b %Y, %H:%M')} · "
                    f"{max(1, round(cv['size'] / 1024))} KB"
                )
            if len(cvs) > 6:
                st.caption(f"Plus {len(cvs) - 6} older CV file(s).")
        else:
            st.caption("No CV files generated yet.")

        sub_section("Environment")
        st.caption(f"Python {platform.python_version()} · {platform.system()}")
        st.caption(f"Streamlit {st.__version__}")

        sub_section("AI assistance")
        ai_settings = load_ai_settings()
        ai_availability = ai_status(ai_settings)
        st.caption(
            f"Provider: {ai_settings.provider or 'not configured'} · "
            f"Model: {ai_settings.model or 'not configured'} · "
            f"API key: {'present' if ai_settings.api_key else 'missing'}"
        )
        if ai_availability.available:
            st.success(ai_availability.message)
        elif ai_availability.configured:
            st.warning(ai_availability.message)
        else:
            st.info(ai_availability.message)
        st.caption(
            "Streamlit Community Cloud: Manage app → Settings → Secrets. "
            "Local: .streamlit/secrets.toml. Never commit the API key."
        )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)

    with st.expander("Developer diagnostics", expanded=False):
        if is_authenticated():
            st.caption(
                "Global row counts and filesystem details are hidden in signed-in "
                "mode so one account cannot see another account's activity."
            )
            st.markdown(f"**App version:** {APP_VERSION}")
        else:
            st.caption(
                "Read-only checks. These details are shown locally and never sent anywhere."
            )
            try:
                with get_database_connection() as connection:
                    quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
                    table_rows = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    ).fetchall()
                    counts = {}
                    for row in table_rows:
                        table = row["name"]
                        if table.isidentifier():
                            counts[table] = connection.execute(
                                f'SELECT COUNT(*) FROM "{table}"'  # identifier checked above
                            ).fetchone()[0]
            except sqlite3.Error as error:
                st.error("The database diagnostic check could not be completed.")
                st.code(f"{type(error).__name__}: {error}", language=None)
            else:
                st.markdown(f"**Database integrity:** `{quick_check}`")
                for table, count in counts.items():
                    st.markdown(f"- `{table}`: {count} row(s)")
                st.markdown(f"**CV PDFs on disk:** {len(cvs)}")
                st.markdown(f"**Last profile update:** {format_date(max((p.get('updated_at') or p.get('created_at') or '' for p in profiles), default=''))}")
                st.markdown(f"**App version:** {APP_VERSION}")
