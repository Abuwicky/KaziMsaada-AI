"""Profile viewing, creation, editing, and deletion."""

from __future__ import annotations

import html
import sqlite3

import streamlit as st

from core.profiles import (
    ProfileValidationError,
    create_profile,
    delete_profile_record,
    normalize_skills,
    profile_completeness,
    update_profile_record,
    validate_profile,
)

from .ui import (
    empty_state,
    format_date,
    go_to,
    icon,
    page_header,
    set_flash,
    skill_chips,
)


def _database_error(action: str, error: Exception) -> None:
    st.error(
        f"{action} could not be completed. Your existing data has not been "
        "changed. Please try again."
    )
    with st.expander("Technical details"):
        st.code(f"{type(error).__name__}: {error}", language=None)


def _select_for_page(profile_id: str | None) -> None:
    st.session_state["active_profile_id"] = profile_id


def _profile_select(profiles: list[dict]) -> dict | None:
    if not profiles:
        return None

    ids = [profile["profile_id"] for profile in profiles]
    lookup = {profile["profile_id"]: profile for profile in profiles}
    active_id = st.session_state.get("active_profile_id")

    if active_id not in ids:
        active_id = ids[0]
        st.session_state["active_profile_id"] = active_id

    # Keep the widget in step with the authoritative active profile. This is
    # done before the selectbox is created, which is the only safe time to
    # update widget state.
    widget_key = "profile_page_select_widget"
    if st.session_state.get(widget_key) != active_id:
        st.session_state[widget_key] = active_id

    def _sync_selection() -> None:
        st.session_state["active_profile_id"] = st.session_state.get(widget_key)

    selected = st.selectbox(
        "Select a saved profile",
        ids,
        format_func=lambda pid: (
            f"{lookup[pid].get('name', 'Unnamed profile')} · "
            f"{lookup[pid].get('career_interest', 'Career profile')}"
        ),
        key=widget_key,
        on_change=_sync_selection,
    )

    return lookup.get(selected)


def _profile_detail(profile: dict) -> None:
    name = html.escape(str(profile.get("name", "Unnamed profile")))
    interest = html.escape(str(profile.get("career_interest", "Not provided")))
    education = html.escape(str(profile.get("education", "Not provided")))
    location = html.escape(str(profile.get("location", "Not provided")))
    experience = html.escape(str(profile.get("experience", "Not provided")))
    completeness = profile_completeness(profile)
    short_id = html.escape(str(profile.get("profile_id", ""))[:8])

    st.markdown(
        f"""
        <div class="km-detail-card">
          <div class="km-detail-head">
            <div class="km-avatar km-avatar-lg">{html.escape(name[:1].upper() or "K")}</div>
            <div class="km-detail-title">
              <h2>{name}</h2>
              <p>{interest}</p>
            </div>
            <div class="km-detail-score">
              <strong>{completeness}%</strong>
              <span>complete</span>
            </div>
          </div>
          <div class="km-detail-grid">
            <div><span>Location</span><strong>{location}</strong></div>
            <div><span>Education</span><strong>{education}</strong></div>
            <div><span>Created</span><strong>{format_date(profile.get("created_at"))}</strong></div>
            <div><span>Last updated</span><strong>{format_date(profile.get("updated_at")) if profile.get("updated_at") else "Not updated yet"}</strong></div>
          </div>
          <div class="km-detail-block">
            <span>Work experience</span>
            <p>{experience}</p>
          </div>
          <div class="km-detail-block">
            <span>Skills</span>
            <div class="km-profile-skills">{skill_chips(profile.get("skills", []))}</div>
          </div>
          <div class="km-detail-foot">Profile reference: {short_id}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _refresh_profiles() -> None:
    set_flash("Profile list refreshed from the local database.", "info")


def _create_form(has_profiles: bool) -> None:
    st.markdown(
        """
        <div class="km-form-intro">
          <strong>Create a career profile</strong>
          <p>Start with the essentials. You can refine everything later, and your
          profile will power your CV, guidance, and skills tools.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("create_profile_form", clear_on_submit=False):
        left, right = st.columns(2)
        with left:
            name = st.text_input("Full name *", placeholder="e.g. Amani Wanjiku")
            education = st.text_input(
                "Highest education level *",
                placeholder="e.g. Diploma in Information Technology",
            )
            location = st.text_input(
                "Town or county *", placeholder="e.g. Kakamega"
            )
        with right:
            career_interest = st.text_input(
                "Career or industry of interest *",
                placeholder="e.g. ICT support, social work, construction",
            )
            experience = st.text_area(
                "Work experience",
                placeholder=(
                    "Describe paid work, internships, attachments, or volunteering. "
                    "Leave blank if you have no formal experience yet."
                ),
                height=100,
            )
            skills_text = st.text_input(
                "Skills (comma-separated)",
                placeholder="e.g. Computer literacy, Customer care, Problem solving",
            )

        st.caption("* Required. Your data is saved only to the local SQLite database.")
        submitted = st.form_submit_button(
            "Create profile",
            type="primary",
            width="stretch",
        )

    cancel = st.button("Cancel", key="create_cancel")
    if cancel:
        if has_profiles:
            st.session_state["profile_mode"] = "view"
        else:
            go_to("Dashboard")
        st.rerun()

    if not submitted:
        return

    data = {
        "name": name,
        "education": education,
        "location": location,
        "experience": experience.strip() or "No formal work experience yet",
        "career_interest": career_interest,
        "skills": normalize_skills(skills_text),
    }

    errors = validate_profile(data)
    if errors:
        for message in errors.values():
            st.error(message)
        return

    try:
        profile = create_profile(data)
    except ProfileValidationError as error:
        for message in error.errors.values():
            st.error(message)
        return
    except sqlite3.Error as error:
        _database_error("Creating the profile", error)
        return

    _select_for_page(profile["profile_id"])
    st.session_state["profile_mode"] = "view"
    set_flash(f"Profile created for {profile['name']}. Your CV builder is ready.")
    st.rerun()


def _edit_form(profile: dict) -> None:
    profile_id = profile["profile_id"]

    st.markdown(
        f"""
        <div class="km-form-intro">
          <strong>Editing {html.escape(str(profile.get("name", "profile")))}</strong>
          <p>Saving updates this existing record. It will not create a duplicate.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form(f"edit_profile_form_{profile_id}", clear_on_submit=False):
        left, right = st.columns(2)
        with left:
            name = st.text_input("Full name *", value=str(profile.get("name", "")))
            education = st.text_input(
                "Highest education level *", value=str(profile.get("education", ""))
            )
            location = st.text_input(
                "Town or county *", value=str(profile.get("location", ""))
            )
        with right:
            career_interest = st.text_input(
                "Career or industry of interest *",
                value=str(profile.get("career_interest", "")),
            )
            experience = st.text_area(
                "Work experience",
                value=str(profile.get("experience", "")),
                height=100,
            )
            skills_text = st.text_input(
                "Skills (comma-separated)",
                value=", ".join(profile.get("skills", [])),
            )

        submitted = st.form_submit_button(
            "Save changes",
            type="primary",
            width="stretch",
        )

    cancel = st.button("Cancel changes", key=f"edit_cancel_{profile_id}")
    if cancel:
        st.session_state["profile_mode"] = "view"
        st.rerun()

    if not submitted:
        return

    updated = dict(profile)
    updated.update(
        {
            "name": name.strip(),
            "education": education.strip(),
            "location": location.strip(),
            "experience": experience.strip() or "No formal work experience yet",
            "career_interest": career_interest.strip(),
            "skills": normalize_skills(skills_text),
        }
    )

    errors = validate_profile(updated)
    if errors:
        for message in errors.values():
            st.error(message)
        return

    try:
        changed = update_profile_record(updated)
    except sqlite3.Error as error:
        _database_error("Updating the profile", error)
        return

    if not changed:
        st.error(
            "The profile could not be updated. It may have been removed. "
            "Refresh the page and try again."
        )
        return

    st.session_state["profile_mode"] = "view"
    set_flash("Profile updated successfully.")
    st.rerun()


def _delete_panel(profile: dict, profiles: list[dict]) -> None:
    profile_id = profile["profile_id"]
    name = html.escape(str(profile.get("name", "this profile")))

    with st.expander("Delete this profile", expanded=False):
        st.warning(
            f"Deleting “{name}” removes the profile from the local database. "
            "Generated CV files remain in your CV folder. This cannot be undone."
        )
        confirmation = st.text_input(
            "Type DELETE to confirm",
            key=f"delete_confirm_{profile_id}",
            placeholder="DELETE",
        )
        if st.button(
            "Permanently delete profile",
            key=f"delete_button_{profile_id}",
            disabled=confirmation.strip() != "DELETE",
            type="primary",
        ):
            try:
                deleted = delete_profile_record(profile_id)
            except sqlite3.Error as error:
                _database_error("Deleting the profile", error)
                return

            if not deleted:
                st.error("The profile could not be found. It may already be removed.")
                return

            remaining = [
                item for item in profiles if item["profile_id"] != profile_id
            ]
            replacement = remaining[0]["profile_id"] if remaining else None
            _select_for_page(replacement)
            st.session_state["profile_mode"] = "view"
            set_flash(f"Profile “{name}” was deleted.", "warning")
            st.rerun()


def render_profile_page(profiles: list[dict]) -> None:
    page_header(
        "Career profile",
        "My Profile",
        "Keep your education, experience, location and skills current. "
        "Everything you build in KaziMsaada AI starts here.",
    )

    mode = st.session_state.get("profile_mode", "view")
    if not profiles and mode != "create":
        mode = "create"
        st.session_state["profile_mode"] = "create"

    if mode == "view":
        nav_left, nav_right, _ = st.columns([1, 1, 3])
        with nav_left:
            st.button(
                "Create new profile",
                key="profile_new_top",
                on_click=go_to,
                args=("My Profile", "create"),
                width="stretch",
            )
        with nav_right:
            st.button(
                "Refresh profiles",
                key="profile_refresh",
                width="stretch",
                on_click=_refresh_profiles,
            )

        profile = _profile_select(profiles)
        if profile is None:
            empty_state(
                "No profile selected",
                "Create a profile to unlock the CV builder and personalised guidance.",
                "Create a profile",
                "My Profile",
                "create",
                "profile_empty_create",
            )
            return

        st.markdown('<div class="km-space-sm"></div>', unsafe_allow_html=True)
        _profile_detail(profile)

        action_left, action_mid, _ = st.columns([1, 1, 3])
        with action_left:
            st.button(
                "Edit this profile",
                key=f"profile_edit_{profile['profile_id']}",
                type="primary",
                width="stretch",
                on_click=go_to,
                args=("My Profile", "edit"),
            )
        with action_mid:
            st.button(
                "Build a CV",
                key=f"profile_cv_{profile['profile_id']}",
                width="stretch",
                on_click=go_to,
                args=("CV Builder",),
            )

        st.markdown('<div class="km-space-sm"></div>', unsafe_allow_html=True)
        _delete_panel(profile, profiles)

    elif mode == "create":
        back = st.button(
            "← Back to saved profiles" if profiles else "← Back to dashboard",
            key="create_back",
        )
        if back:
            if profiles:
                st.session_state["profile_mode"] = "view"
            else:
                go_to("Dashboard")
            st.rerun()
        _create_form(has_profiles=bool(profiles))

    elif mode == "edit":
        active_id = st.session_state.get("active_profile_id")
        profile = next(
            (item for item in profiles if item["profile_id"] == active_id),
            None,
        )
        if profile is None:
            st.session_state["profile_mode"] = "view"
            st.rerun()
            return

        back = st.button("← Back without saving", key=f"edit_back_{profile['profile_id']}")
        if back:
            st.session_state["profile_mode"] = "view"
            st.rerun()
        _edit_form(profile)
