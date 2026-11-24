"""Dashboard page for KaziMsaada AI."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from core.auth import privacy_summary
from core.cv import TEMPLATES, list_saved_cvs
from core.profiles import profile_completeness

from .ui import (
    empty_state,
    feature_card,
    format_date,
    go_to,
    icon,
    metric_card,
    section_header,
    skill_chips,
)


def _open_profile(profile_id: str) -> None:
    st.session_state["active_profile_id"] = profile_id
    go_to("My Profile")


def _template_for(filename: str) -> str:
    for template_id, meta in TEMPLATES.items():
        if f"_{template_id}_" in filename:
            return meta["name"]
    return "CV"


def _profile_card(profile: dict) -> str:
    name = html.escape(str(profile.get("name", "Unnamed profile")))
    interest = html.escape(str(profile.get("career_interest", "No career interest set")))
    location = html.escape(str(profile.get("location", "Not provided")))
    education = html.escape(str(profile.get("education", "Not provided")))
    experience = html.escape(str(profile.get("experience", "Not provided")))
    if len(experience) > 170:
        experience = experience[:167].rstrip() + "..."

    completeness = profile_completeness(profile)

    return f"""
    <div class="km-profile-card">
      <div class="km-profile-top">
        <div class="km-avatar">{html.escape(name[:1].upper() or "K")}</div>
        <div>
          <div class="km-profile-name">{name}</div>
          <div class="km-profile-role">{interest}</div>
        </div>
        <div class="km-completeness">{completeness}%</div>
      </div>
      <div class="km-profile-grid">
        <div><span>Location</span><strong>{location}</strong></div>
        <div><span>Education</span><strong>{education}</strong></div>
      </div>
      <div class="km-profile-exp"><span>Experience</span><p>{experience}</p></div>
      <div class="km-profile-skills">{skill_chips(profile.get("skills", []), limit=6)}</div>
    </div>
    """


def render_dashboard(profiles: list[dict]) -> None:
    active_id = st.session_state.get("active_profile_id")
    lookup = {profile["profile_id"]: profile for profile in profiles}
    active = lookup.get(active_id) or (profiles[0] if profiles else None)

    cvs = list_saved_cvs()
    completeness = profile_completeness(active) if active else 0
    first_name = str(active.get("name", "")).split()[0] if active else ""
    greeting = f"Welcome back, {html.escape(first_name)}." if first_name else "Build your next opportunity with confidence."
    intro = (
        "Your profile is ready to power a professional CV. Keep your details current, "
        "then explore interview practice, skills insights, and practical job-search support."
        if active
        else "KaziMsaada AI brings your career profile, CV builder, interview preparation, "
        "skills assessment, and job-search guidance into one calm, local workspace."
    )

    st.markdown(
        f"""
        <div class="km-hero">
          <div class="km-hero-copy">
            <div class="km-eyebrow">Career readiness workspace</div>
            <h1>{greeting}</h1>
            <p>{intro}</p>
            <div class="km-hero-note">
              <span class="km-status-dot"></span>
              Private by design · {html.escape(privacy_summary())}
            </div>
          </div>
          <div class="km-hero-mark">{icon("compass", 72)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cta_left, cta_right, cta_space = st.columns([1.1, 1.1, 3.2])
    with cta_left:
        st.button(
            "Build my CV" if active else "Create my first profile",
            type="primary",
            width="stretch",
            key="hero_cv" if active else "hero_create",
            on_click=go_to,
            args=("CV Builder",) if active else ("My Profile", "create"),
        )
    with cta_right:
        st.button(
            "Manage profile" if active else "View saved profiles",
            width="stretch",
            key="hero_profile",
            on_click=go_to,
            args=("My Profile", "view") if active else ("My Profile",),
        )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)

    metric_cols = st.columns(4)
    metrics = [
        ("Saved profiles", len(profiles), "Career profiles in your workspace", "user"),
        ("CVs generated", len(cvs), "PDF documents in your CV library", "file"),
        ("Career tools", 6, "Profile, CV, interview, skills, guidance, jobs", "compass"),
        (
            "Profile strength",
            f"{completeness}%",
            "Based on the active profile's key sections",
            "target",
        ),
    ]
    for column, (label, value, caption, icon_name) in zip(metric_cols, metrics):
        with column:
            st.markdown(
                metric_card(label, value, caption, icon_name),
                unsafe_allow_html=True,
            )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)
    section_header(
        "Your career toolkit",
        "Six practical tools, one consistent workspace. Start with your profile or go straight to a CV.",
    )

    row_one = st.columns(3)
    with row_one[0]:
        feature_card(
            "tool_cv_create",
            "file",
            "Create a CV",
            "Turn your saved profile into a polished, downloadable CV with a live preview.",
            "CV Builder",
            "Available",
            "available",
        )
    with row_one[1]:
        feature_card(
            "tool_cv_improve",
            "sparkles",
            "Improve an Existing CV",
            "Refine your summary, experience and skills, then compare the template gallery.",
            "CV Builder",
            "Available",
            "available",
        )
    with row_one[2]:
        feature_card(
            "tool_interview",
            "message",
            "Interview Preparation",
            "Practise common questions and structure stronger answers with the STAR method.",
            "Interview Preparation",
            "Guided preview",
            "preview",
        )

    row_two = st.columns(3)
    with row_two[0]:
        feature_card(
            "tool_skills",
            "target",
            "Skills Assessment",
            "Map your strengths, spot transferable skills, and choose a focused next step.",
            "Skills Assessment",
            "Guided preview",
            "preview",
        )
    with row_two[1]:
        feature_card(
            "tool_guidance",
            "compass",
            "Career Guidance",
            "Explore pathways, typical roles, and practical development steps for your interests.",
            "Career Guidance",
            "Guided preview",
            "preview",
        )
    with row_two[2]:
        feature_card(
            "tool_jobs",
            "briefcase",
            "Job Search Support",
            "Use an application checklist, trusted job sources, and scam-safety reminders.",
            "Job Search Support",
            "Guided preview",
            "preview",
        )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)

    overview_col, recent_col = st.columns([1.55, 1])

    with overview_col:
        section_header("Profile overview", "The information that powers your CV and guidance.")
        if active:
            st.markdown(_profile_card(active), unsafe_allow_html=True)
            action_one, action_two, action_space = st.columns([1, 1, 2.2])
            with action_one:
                st.button(
                    "View full profile",
                    width="stretch",
                    key="overview_view",
                    on_click=go_to,
                    args=("My Profile", "view"),
                )
            with action_two:
                st.button(
                    "Edit details",
                    width="stretch",
                    key="overview_edit",
                    on_click=go_to,
                    args=("My Profile", "edit"),
                )
        else:
            empty_state(
                "No career profile yet",
                "Create a profile with your education, experience, location and skills. "
                "Everything else in KaziMsaada AI builds from it.",
                "Create a profile",
                "My Profile",
                "create",
                "dash_empty_create",
            )

    with recent_col:
        section_header("Recently saved", "Profiles ordered by when they were created.")
        if profiles:
            for profile in profiles[:3]:
                name = html.escape(str(profile.get("name", "Unnamed profile")))
                interest = html.escape(str(profile.get("career_interest", "Career profile")))
                created = format_date(profile.get("created_at"))
                is_active = profile["profile_id"] == (active or {}).get("profile_id")
                st.markdown(
                    f"""
                    <div class="km-recent-row">
                      <div class="km-recent-avatar">{html.escape(name[:1].upper() or "K")}</div>
                      <div class="km-recent-copy">
                        <strong>{name}</strong>
                        <span>{interest} · {created}</span>
                      </div>
                      {'<span class="km-current">Current</span>' if is_active else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if not is_active:
                    st.button(
                        f"Open {name}",
                        key=f"recent_open_{profile['profile_id']}",
                        on_click=_open_profile,
                        args=(profile["profile_id"],),
                    )
        else:
            st.info("Saved profiles will appear here once you create one.")

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)
    section_header("Recent CV documents", "Only files that actually exist in your CV folder are shown.")

    if cvs:
        for cv in cvs[:3]:
            path = Path(cv["path"])
            size_kb = max(1, round(cv["size"] / 1024))
            download_col, meta_col = st.columns([1, 3.4])
            with download_col:
                try:
                    pdf_bytes = path.read_bytes()
                except OSError:
                    st.caption("File unavailable")
                else:
                    st.download_button(
                        "Download",
                        data=pdf_bytes,
                        file_name=path.name,
                        mime="application/pdf",
                        key=f"dash_download_{path.name}",
                        width="stretch",
                    )
            with meta_col:
                st.markdown(
                    f"""
                    <div class="km-cv-row">
                      <div class="km-cv-icon">{icon("file", 20)}</div>
                      <div>
                        <strong>{html.escape(path.name)}</strong>
                        <span>{_template_for(path.name)} · {size_kb} KB · {cv["modified"].strftime("%d %b %Y, %H:%M")}</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            f"""
            <div class="km-inline-empty">
              {icon("file", 22)}
              <div>
                <strong>No CVs generated yet.</strong>
                <span>Build one from your profile; the PDF will appear here and in your downloads.</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
