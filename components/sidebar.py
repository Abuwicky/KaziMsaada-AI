"""Sidebar navigation and working-profile selection."""

from __future__ import annotations

import html

import streamlit as st

from core.config import APP_DISPLAY_NAME, APP_VERSION, DATABASE_FILE
from core.profiles import profile_completeness

from .ui import NAV_ITEMS, icon, initialize_state


def _profile_label(profile: dict) -> str:
    name = str(profile.get("name", "Unnamed profile")).strip() or "Unnamed profile"
    interest = str(profile.get("career_interest", "")).strip()
    if interest:
        return f"{name} · {interest[:28]}"
    return name


def render_sidebar(profiles: list[dict]) -> str:
    initialize_state()

    with st.sidebar:
        st.markdown(
            f"""
            <div class="km-brand">
              <div class="km-logo">KM</div>
              <div>
                <div class="km-brand-name">{html.escape(APP_DISPLAY_NAME)}</div>
                <div class="km-brand-sub">Career readiness workspace</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="km-nav-label">Workspace</div>', unsafe_allow_html=True)

        selected = st.radio(
            "Navigation",
            NAV_ITEMS,
            key="nav",
            label_visibility="collapsed",
        )

        # The radio is the user's navigation control. Programmatic navigation
        # (dashboard cards, empty-state buttons) updates both "page" and "nav"
        # before the widget renders, so no pre-widget reset is needed here.
        st.session_state["page"] = selected

        st.markdown('<div class="km-side-divider"></div>', unsafe_allow_html=True)

        active_id = st.session_state.get("active_profile_id")
        ids = [profile["profile_id"] for profile in profiles]

        if profiles:
            if active_id not in ids:
                active_id = ids[0]
                st.session_state["active_profile_id"] = active_id

            # The active profile is the single source of truth. Sync the widget
            # before it is created so programmatic changes (dashboard cards,
            # create, delete) are reflected immediately.
            widget_key = "sidebar_profile_widget"
            if st.session_state.get(widget_key) != active_id:
                st.session_state[widget_key] = active_id

            st.markdown(
                '<div class="km-nav-label">Working profile</div>',
                unsafe_allow_html=True,
            )

            lookup = {profile["profile_id"]: profile for profile in profiles}

            def _sync_working_profile() -> None:
                st.session_state["active_profile_id"] = st.session_state.get(widget_key)

            chosen = st.selectbox(
                "Working profile",
                ids,
                format_func=lambda pid: _profile_label(lookup[pid]),
                key=widget_key,
                label_visibility="collapsed",
                on_change=_sync_working_profile,
            )
            st.session_state["active_profile_id"] = chosen

            profile = lookup[chosen]
            completeness = profile_completeness(profile)
            st.markdown(
                f"""
                <div class="km-side-profile">
                  <div class="km-side-profile-row">
                    <span>{html.escape(str(profile.get("career_interest", "Career profile"))[:30])}</span>
                    <strong>{completeness}%</strong>
                  </div>
                  <div class="km-progress"><span style="width:{completeness}%"></span></div>
                  <div class="km-side-profile-caption">Profile completeness</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="km-side-empty">
                  No saved profile yet. Create one to unlock the CV builder.
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('<div class="km-side-spacer"></div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="km-side-status">
              <div class="km-status-dot"></div>
              <div>
                <strong>Local workspace</strong>
                <span>SQLite · v{html.escape(APP_VERSION)}</span>
              </div>
            </div>
            <div class="km-side-foot">
              Profiles and CVs stay on this computer.
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("Workspace details", expanded=False):
            st.caption("Database")
            st.code(str(DATABASE_FILE), language=None)
            st.caption(
                "Profiles and CVs are stored locally. When AI practice feedback is "
                "enabled, only the target role, category, difficulty, question, and "
                "answer are sent to the configured provider."
            )

    return st.session_state["page"]


def sidebar_icon(name: str) -> str:
    return icon(name, 18)
