"""Shared UI helpers for the KaziMsaada AI Streamlit interface."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import streamlit as st

NAV_ITEMS = [
    "Dashboard",
    "My Profile",
    "CV Builder",
    "Interview Preparation",
    "Skills Assessment",
    "Career Guidance",
    "Job Search Support",
    "Settings",
]

DEFAULT_STATE = {
    "page": "Dashboard",
    "nav": "Dashboard",
    "active_profile_id": None,
    "profile_mode": "view",
    "cv_template": "classic",
}

ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "user": '<path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h6"/>',
    "sparkles": '<path d="m12 3 1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    "message": '<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8"/><path d="M8 13h5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
    "settings": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/><circle cx="8" cy="6" r="2" fill="currentColor" stroke="none"/><circle cx="16" cy="12" r="2" fill="currentColor" stroke="none"/><circle cx="10" cy="18" r="2" fill="currentColor" stroke="none"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "download": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "arrow": '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
}


def initialize_state() -> None:
    for key, value in DEFAULT_STATE.items():
        st.session_state.setdefault(key, value)


def go_to(page: str, mode: str | None = None) -> None:
    """Navigation callback used by sidebar and dashboard buttons."""

    st.session_state["page"] = page
    st.session_state["nav"] = page
    if mode:
        st.session_state["profile_mode"] = mode


def set_flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = {"message": message, "kind": kind}


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if not item:
        return

    renderer = {
        "success": st.success,
        "error": st.error,
        "warning": st.warning,
        "info": st.info,
    }.get(item.get("kind", "success"), st.info)

    renderer(item.get("message", ""))


def icon(name: str, size: int = 20) -> str:
    path = ICONS.get(name, ICONS["dashboard"])
    return (
        f'<svg class="km-icon" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )


def section_header(title: str, subtitle: str | None = None) -> None:
    safe_title = html.escape(title)
    st.markdown(
        f'<div class="km-section-head"><h2>{safe_title}</h2>'
        f'{f"<p>{html.escape(subtitle)}</p>" if subtitle else ""}</div>',
        unsafe_allow_html=True,
    )


def sub_section(title: str) -> None:
    """Render a visually compact h2 without skipping heading levels."""

    st.markdown(
        f'<h2 class="km-subhead">{html.escape(title)}</h2>',
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="km-page-head">
          <div class="km-eyebrow">{html.escape(eyebrow)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_date(value) -> str:
    if not value:
        return "Not recorded"

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(value)


def skill_chips(skills, limit: int | None = None) -> str:
    items = [str(skill) for skill in skills if str(skill).strip()]
    if limit:
        items = items[:limit]

    if not items:
        return '<span class="km-muted">No skills added yet.</span>'

    return "".join(
        f'<span class="km-chip">{html.escape(item)}</span>' for item in items
    )


def metric_card(label: str, value, caption: str, icon_name: str) -> str:
    return f"""
    <div class="km-metric">
      <div class="km-metric-top">
        <span class="km-metric-icon">{icon(icon_name, 18)}</span>
        <span class="km-metric-label">{html.escape(label)}</span>
      </div>
      <div class="km-metric-value">{value}</div>
      <div class="km-metric-caption">{html.escape(caption)}</div>
    </div>
    """


def feature_card(
    key: str,
    icon_name: str,
    title: str,
    description: str,
    target: str,
    badge: str,
    badge_kind: str = "available",
    mode: str | None = None,
) -> None:
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="km-feature">
              <div class="km-feature-icon">{icon(icon_name, 22)}</div>
              <div class="km-feature-body">
                <div class="km-feature-title">{html.escape(title)}</div>
                <div class="km-feature-desc">{html.escape(description)}</div>
                <span class="km-badge km-badge-{badge_kind}">{html.escape(badge)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.button(
            "Open tool",
            key=key,
            width="stretch",
            on_click=go_to,
            args=(target, mode) if mode else (target,),
        )


def empty_state(title: str, message: str, button_label: str, target: str, mode: str | None = None, key: str = "empty_cta") -> None:
    st.markdown(
        f"""
        <div class="km-empty">
          <div class="km-empty-icon">{icon("sparkles", 26)}</div>
          <div class="km-empty-title">{html.escape(title)}</div>
          <p>{html.escape(message)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        button_label,
        key=key,
        type="primary",
        on_click=go_to,
        args=(target, mode) if mode else (target,),
    )


def read_asset(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "assets" / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
