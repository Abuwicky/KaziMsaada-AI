"""Mentor Meeting Centre UI.

The centre is a human coaching workflow inside Interview Preparation. It is not
an AI chatbot and it does not pretend that local profile selection is secure
authentication. Administrator and mentor workspaces use explicit access codes.
"""

from __future__ import annotations

import html
import os
import sqlite3
from datetime import date, datetime, time, timedelta

import streamlit as st

from core.mentor_access import (
    ADMIN_SECRET_SECTION,
    admin_access_configured,
    verify_admin_access,
)
from core.mentor_store import (
    authenticate_mentor,
    cancel_booking,
    clear_reschedule_request,
    complete_booking,
    confirm_booking,
    create_availability,
    create_booking,
    create_mentor_application,
    get_mentor_by_application,
    get_mentor_workspace,
    list_applications_for_profile,
    list_bookings_for_mentor,
    list_bookings_for_profile,
    list_mentor_applications,
    list_mentor_availability,
    list_open_slots,
    list_public_industries,
    list_public_mentors,
    reject_booking,
    remove_availability,
    request_reschedule,
    review_mentor_application,
    rotate_mentor_access_code,
    submit_feedback,
    update_availability,
    update_meeting_link,
    update_mentor_profile,
    update_mentor_recommendations,
)
from core.mentors import (
    APPLICATION_STATUS_LABELS,
    BOOKING_CANCELLED,
    BOOKING_COMPLETED,
    BOOKING_CONFIRMED,
    BOOKING_PENDING,
    BOOKING_REJECTED,
    BOOKING_STATUS_LABELS,
    DURATION_OPTIONS,
    MentorError,
    NAIROBI_TZ,
    format_duration,
    format_nairobi,
    initials,
    nairobi_to_utc,
    parse_utc,
)

from .ui import icon, sub_section

NO_PROFILE_KEY = "no-profile"
ADMIN_STATE_KEY = "mentor_admin_session"
MENTOR_STATE_KEY = "mentor_workspace_id"
NOTICE_KEY = "mentor_notice"
NEW_CODES_KEY = "mentor_new_access_codes"


def _profile_scope(profile: dict | None) -> str:
    return str((profile or {}).get("profile_id") or NO_PROFILE_KEY)


def _key(profile: dict | None, name: str) -> str:
    return f"mentor::{_profile_scope(profile)}::{name}"


def _notify(message: str, kind: str = "success") -> None:
    st.session_state[NOTICE_KEY] = {"message": message, "kind": kind}


def _show_notice() -> None:
    notice = st.session_state.pop(NOTICE_KEY, None)
    if not notice:
        return
    renderer = {
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
        "info": st.info,
    }.get(notice.get("kind", "success"), st.info)
    renderer(notice.get("message", ""))


def _safe_secret_section() -> dict:
    try:
        section = st.secrets.get(ADMIN_SECRET_SECTION, {})
    except Exception:
        section = {}
    section = dict(section) if isinstance(section, dict) else {}
    if not admin_access_configured(section):
        env_code = str(os.environ.get("MENTOR_ADMIN_ACCESS_CODE", "")).strip()
        env_hash = str(os.environ.get("MENTOR_ADMIN_ACCESS_CODE_HASH", "")).strip()
        if env_hash:
            return {"access_code_hash": env_hash}
        if env_code:
            return {"access_code": env_code}
    return section


def _render_error(error: Exception) -> None:
    if isinstance(error, MentorError):
        st.error(str(error))
    elif isinstance(error, sqlite3.Error):
        st.error("The mentor centre could not save that change. No data was changed.")
        with st.expander("Technical details"):
            st.code(f"{type(error).__name__}: {error}", language=None)
    else:
        st.error("Something went wrong. No data was changed.")
        with st.expander("Technical details"):
            st.code(f"{type(error).__name__}: {error}", language=None)


def _status_class(status: str) -> str:
    return f"km-badge km-badge-{status}"


def _render_mentor_avatar(mentor: dict) -> str:
    return f'<div class="km-mentor-avatar">{html.escape(initials(mentor.get("full_name", "")))}</div>'


def _render_mentor_card(mentor: dict) -> None:
    avatar = _render_mentor_avatar(mentor)
    name = html.escape(str(mentor.get("full_name", "Mentor")))
    title = html.escape(str(mentor.get("professional_title", "")))
    industry = html.escape(str(mentor.get("industry", "")))
    specialisation = html.escape(str(mentor.get("specialisation", "")))
    biography = html.escape(str(mentor.get("biography", "")))
    languages = ", ".join(mentor.get("languages", [])) or "Not listed"
    coaching = ", ".join(mentor.get("coaching_areas", [])) or "Not listed"
    durations = ", ".join(format_duration(item) for item in mentor.get("duration_options", []))
    st.markdown(
        f"""
        <div class="km-mentor-card">
          {avatar}
          <div class="km-mentor-card-copy">
            <div class="km-mentor-card-top">
              <div>
                <h3>{name}</h3>
                <p class="km-mentor-title">{title}</p>
              </div>
              <span class="km-badge km-badge-approved">Approved mentor</span>
            </div>
            <p>{biography}</p>
            <div class="km-mentor-facts">
              <span><strong>Industry</strong>{industry}</span>
              <span><strong>Specialisation</strong>{specialisation}</span>
              <span><strong>Languages</strong>{html.escape(languages)}</span>
              <span><strong>Session lengths</strong>{html.escape(durations)}</span>
            </div>
            <div class="km-mentor-detail">
              <strong>Coaching areas</strong>
              <span>{html.escape(coaching)}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Experience and qualifications", expanded=False):
        st.markdown("**Professional experience**")
        st.write(mentor.get("experience", "Not provided"))
        st.markdown("**Qualifications**")
        st.write(mentor.get("qualifications", "Not provided"))
        st.caption(
            "Approved mentors are reviewed by an administrator. Qualifications are "
            "not independently verified by this local release."
        )


def _render_booking_meta(booking: dict, *, perspective: str) -> None:
    if perspective == "mentor":
        person = html.escape(str(booking.get("job_seeker_name", "Job seeker")))
        person_label = "Job seeker"
    else:
        person = html.escape(str(booking.get("mentor_name", "Mentor")))
        person_label = "Mentor"
    status = str(booking.get("status", ""))
    st.markdown(
        f"""
        <div class="km-booking-summary">
          <div><span>{person_label}</span><strong>{person}</strong></div>
          <div><span>When</span><strong>{html.escape(format_nairobi(booking.get("scheduled_start_utc", "")))}</strong></div>
          <div><span>Duration</span><strong>{html.escape(format_duration(booking.get("duration_minutes", 0)))}</strong></div>
          <div><span>Reference</span><strong>{html.escape(str(booking.get("booking_reference", "")))}</strong></div>
          <div><span>Status</span><strong><span class="{_status_class(status)}">{html.escape(BOOKING_STATUS_LABELS.get(status, status))}</span></strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"**What they need help with:** {booking.get('purpose', '')}")
    if booking.get("target_job_role"):
        st.caption(f"Target role: {booking.get('target_job_role')}")
    if booking.get("reschedule_requested_at"):
        st.info(
            f"Reschedule requested: {booking.get('reschedule_note', '')}"
        )
    if booking.get("cancellation_reason"):
        st.caption(f"Cancellation reason: {booking.get('cancellation_reason')}")
    if booking.get("mentor_recommendations"):
        st.markdown("**Mentor recommendations**")
        st.write(booking.get("mentor_recommendations"))


def _render_meeting_link(booking: dict, *, perspective: str) -> None:
    link = str(booking.get("meeting_link") or "").strip()
    if perspective == "job_seeker":
        if booking.get("status") == BOOKING_CONFIRMED:
            if link:
                st.link_button("Join meeting", link, type="primary")
                st.caption("This link is private to you and your mentor.")
            else:
                st.info(
                    "The mentor has not added a meeting link yet. Check this booking "
                    "again before the session."
                )


def render_mentor_centre(profile: dict | None) -> None:
    """Render the complete Mentor Meeting Centre."""

    st.markdown(
        f"""
        <div class="km-note-card">
          {icon("message", 24)}
          <div>
            <strong>Mentor Meeting Centre</strong>
            <span>
              Book a one-to-one session with an approved human mentor for interview
              coaching, confidence, technical preparation or employer expectations.
              This is separate from AI mock-interview practice.
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _show_notice()
    st.caption(
        "Profile selection is a local convenience, not sign-in security. Mentor and "
        "administrator workspaces use separate access codes. Full public deployment "
        "still requires real authentication and role-based access control."
    )

    sections = [
        "Find a mentor",
        "My meetings",
        "Mentor workspace",
        "Apply to mentor",
        "Admin review",
    ]
    section = st.pills(
        "Mentor Meeting Centre section",
        sections,
        default=sections[0],
        key="mentor_centre_section",
        label_visibility="collapsed",
        width="stretch",
    )

    if section == "Find a mentor":
        _render_find_mentor(profile)
    elif section == "My meetings":
        _render_my_meetings(profile)
    elif section == "Mentor workspace":
        _render_mentor_workspace()
    elif section == "Apply to mentor":
        _render_application_form(profile)
    elif section == "Admin review":
        _render_admin_review()


def _render_find_mentor(profile: dict | None) -> None:
    sub_section("Find an approved mentor")
    search_key = _key(profile, "mentor_search")
    industry_key = _key(profile, "mentor_industry")
    search = st.text_input(
        "Search by name, skill or industry",
        placeholder="e.g. interview coaching, HR, data",
        key=search_key,
    )
    industries = list_public_industries()
    industry_options = ["All industries", *industries]
    industry = st.selectbox(
        "Filter by industry",
        industry_options,
        key=industry_key,
    )
    mentors = list_public_mentors(
        search=search,
        industry="" if industry == "All industries" else industry,
    )
    if not mentors:
        st.info(
            "No approved mentors match that search yet. Professionals can apply using "
            "the **Apply to mentor** tab. Pending and rejected applicants are never "
            "shown as bookable mentors."
        )
        return

    mentor_lookup = {mentor["mentor_id"]: mentor for mentor in mentors}
    mentor_ids = list(mentor_lookup)
    selected_key = _key(profile, "selected_mentor")
    if st.session_state.get(selected_key) not in mentor_lookup:
        st.session_state[selected_key] = mentor_ids[0]
    selected_id = st.selectbox(
        "Choose a mentor",
        mentor_ids,
        format_func=lambda mentor_id: (
            f"{mentor_lookup[mentor_id]['full_name']} · "
            f"{mentor_lookup[mentor_id]['professional_title']}"
        ),
        key=selected_key,
    )
    mentor = mentor_lookup[selected_id]
    _render_mentor_card(mentor)

    sub_section("Available meeting times")
    slots = list_open_slots(mentor["mentor_id"])
    if not slots:
        st.info(
            "This mentor has no open slots right now. Please check again later or "
            "choose another mentor."
        )
        return

    if not profile:
        st.warning("Create or select a saved profile before booking a mentor.")
        return

    slot_lookup = {
        slot["slot_id"]: (
            f"{format_nairobi(slot['start_at_utc'])} · "
            f"{format_duration(slot['duration_minutes'])}"
        )
        for slot in slots
    }
    form_key = _key(profile, f"booking_form_{mentor['mentor_id']}")
    with st.form(form_key, clear_on_submit=False):
        slot_id = st.selectbox(
            "Choose a time (Nairobi time)",
            list(slot_lookup),
            format_func=lambda item: slot_lookup[item],
        )
        purpose = st.text_area(
            "What do you need help with? *",
            placeholder=(
                "e.g. Preparing for a customer-service interview, improving "
                "confidence, or practising technical explanations."
            ),
            height=120,
        )
        target_role = st.text_input(
            "Target job role (optional)",
            value=str((profile or {}).get("career_interest", "") or ""),
        )
        st.caption(
            "The booking is created as a request. The mentor must confirm it before "
            "the meeting is final. A unique booking reference is generated."
        )
        submitted = st.form_submit_button("Send booking request", type="primary")
    if submitted:
        try:
            booking = create_booking(
                profile["profile_id"],
                mentor["mentor_id"],
                slot_id,
                purpose,
                target_role,
            )
        except Exception as error:
            _render_error(error)
        else:
            _notify(
                f"Booking request {booking['booking_reference']} sent to "
                f"{booking['mentor_name']}. Track it in My meetings."
            )
            st.rerun()


def _render_my_meetings(profile: dict | None) -> None:
    sub_section("My mentor meetings")
    if not profile:
        st.info("Create or select a saved profile to view your mentor meetings.")
        return
    bookings = list_bookings_for_profile(profile["profile_id"])
    if not bookings:
        st.info(
            "You have no mentor meetings yet. Use **Find a mentor** to send your first "
            "booking request."
        )
        return

    for booking in bookings:
        status = str(booking.get("status", ""))
        label = (
            f"{format_nairobi(booking.get('scheduled_start_utc', ''))} · "
            f"{booking.get('mentor_name', 'Mentor')} · "
            f"{BOOKING_STATUS_LABELS.get(status, status)}"
        )
        with st.expander(label, expanded=status in {BOOKING_PENDING, BOOKING_CONFIRMED}):
            _render_booking_meta(booking, perspective="job_seeker")
            _render_meeting_link(booking, perspective="job_seeker")
            if booking.get("feedback"):
                feedback = booking["feedback"]
                st.markdown("**Your feedback**")
                st.write(f"Rating: {feedback.get('rating', 0)} / 5")
                if feedback.get("comment"):
                    st.write(feedback["comment"])
            elif status == BOOKING_COMPLETED:
                _render_feedback_form(profile, booking)

            if status in {BOOKING_PENDING, BOOKING_CONFIRMED}:
                _render_job_seeker_booking_actions(profile, booking)


def _render_feedback_form(profile: dict, booking: dict) -> None:
    st.markdown("**Share feedback after the session**")
    form_key = f"mentor_feedback_form_{booking['booking_id']}"
    with st.form(form_key, clear_on_submit=False):
        rating = st.select_slider(
            "Session rating",
            options=[1, 2, 3, 4, 5],
            value=5,
        )
        comment = st.text_area(
            "What was most useful?",
            placeholder="A short comment helps mentors improve.",
            height=90,
        )
        helpful = st.checkbox("This session was helpful", value=True)
        further = st.text_area(
            "What further support do you need?",
            height=80,
        )
        submitted = st.form_submit_button("Submit feedback", type="primary")
    if submitted:
        try:
            submit_feedback(
                booking["booking_id"],
                profile["profile_id"],
                rating,
                comment,
                helpful,
                further,
            )
        except Exception as error:
            _render_error(error)
        else:
            _notify("Thank you. Your feedback has been saved.")
            st.rerun()


def _render_job_seeker_booking_actions(profile: dict, booking: dict) -> None:
    st.markdown("**Manage this booking**")
    form_key = f"mentor_reschedule_form_{booking['booking_id']}"
    with st.expander("Request a different time", expanded=False):
        with st.form(form_key, clear_on_submit=False):
            note = st.text_area(
                "Explain the change you need *",
                placeholder="e.g. I can no longer attend at 10:00 and would prefer the afternoon.",
                height=90,
            )
            requested = st.form_submit_button("Send reschedule request")
        if requested:
            try:
                request_reschedule(
                    booking["booking_id"],
                    profile["profile_id"],
                    note,
                )
            except Exception as error:
                _render_error(error)
            else:
                _notify("Reschedule request sent to the mentor.")
                st.rerun()

    if booking.get("reschedule_requested_at"):
        st.caption("A reschedule request is already with the mentor.")

    confirm_key = f"mentor_cancel_confirm_{booking['booking_id']}"
    confirm = st.checkbox(
        "I understand this cancels the booking.",
        key=confirm_key,
    )
    if st.button(
        "Cancel booking",
        key=f"mentor_cancel_{booking['booking_id']}",
        disabled=not confirm,
    ):
        try:
            cancel_booking(
                booking["booking_id"],
                profile_id=profile["profile_id"],
                reason="Cancelled by the job seeker",
            )
        except Exception as error:
            _render_error(error)
        else:
            _notify("Booking cancelled. The slot has been released for others.")
            st.rerun()


def _render_application_form(profile: dict | None) -> None:
    sub_section("Apply to become a mentor")
    st.caption(
        "Applications are reviewed manually. Approved mentors only appear in the "
        "public directory. This release does not verify qualifications or upload "
        "supporting documents; do not submit sensitive documents."
    )
    if profile:
        applications = list_applications_for_profile(profile["profile_id"])
        if applications:
            st.markdown("**Your applications**")
            for application in applications:
                status = application.get("status", "")
                with st.expander(
                    f"{status_label(status)} · {format_nairobi(application.get('created_at', ''))}"
                ):
                    st.write(f"Professional title: {application.get('professional_title', '')}")
                    st.write(f"Email: {application.get('email', '')}")
                    if application.get("review_note"):
                        st.caption(f"Review note: {application['review_note']}")

    form_key = _key(profile, "mentor_application_form")
    with st.form(form_key, clear_on_submit=False):
        full_name = st.text_input("Full name *")
        email = st.text_input("Email address *")
        professional_title = st.text_input("Professional title *")
        industry = st.text_input("Industry *", placeholder="e.g. Human resources, ICT")
        specialisation = st.text_input(
            "Primary specialisation *",
            placeholder="e.g. Interview coaching",
        )
        expertise = st.text_input(
            "Areas of expertise *",
            placeholder="Comma-separated, e.g. Interview coaching, CV review, Career planning",
        )
        experience = st.text_area(
            "Professional experience *",
            placeholder="Describe your relevant experience, years and sectors.",
            height=110,
        )
        biography = st.text_area(
            "Public biography *",
            placeholder="What should job seekers know about how you coach?",
            height=110,
        )
        qualifications = st.text_area(
            "Qualifications *",
            placeholder="One per line or comma-separated.",
            height=90,
        )
        languages = st.text_input(
            "Languages *",
            placeholder="e.g. English, Kiswahili",
        )
        supporting_info = st.text_area(
            "Relevant supporting information",
            placeholder="Optional context for the administrator.",
            height=90,
        )
        avatar_url = st.text_input(
            "Public profile image URL (optional, https only)",
        )
        submitted = st.form_submit_button("Submit mentor application", type="primary")
    if submitted:
        try:
            create_mentor_application(
                {
                    "full_name": full_name,
                    "email": email,
                    "professional_title": professional_title,
                    "industry": industry,
                    "specialisation": specialisation,
                    "areas_of_expertise": expertise,
                    "experience": experience,
                    "biography": biography,
                    "qualifications": qualifications,
                    "languages": languages,
                    "supporting_info": supporting_info,
                    "avatar_url": avatar_url,
                },
                applicant_profile_id=(profile or {}).get("profile_id"),
            )
        except Exception as error:
            _render_error(error)
        else:
            _notify(
                "Application submitted. It is pending administrator review and does "
                "not appear publicly yet."
            )
            st.rerun()


def _status_label(status: str) -> str:
    return APPLICATION_STATUS_LABELS.get(status, str(status).title())


def _render_mentor_workspace() -> None:
    sub_section("Mentor workspace")
    mentor_id = st.session_state.get(MENTOR_STATE_KEY)
    if mentor_id:
        mentor = get_mentor_workspace(mentor_id)
        if mentor is None or mentor.get("approval_status") != "approved":
            st.session_state.pop(MENTOR_STATE_KEY, None)
            mentor_id = None
        else:
            _render_mentor_dashboard(mentor)
            return

    st.info(
        "Approved mentors receive a private access code from the administrator after "
        "approval. Enter it here to manage availability, bookings and meeting links."
    )
    with st.form("mentor_access_form", clear_on_submit=False):
        code = st.text_input("Mentor access code", type="password")
        submitted = st.form_submit_button("Open mentor workspace", type="primary")
    if submitted:
        mentor = authenticate_mentor(code)
        if mentor is None:
            st.error("That mentor access code is not valid, or the mentor is not approved.")
        else:
            st.session_state[MENTOR_STATE_KEY] = mentor["mentor_id"]
            st.rerun()


def _render_mentor_dashboard(mentor: dict) -> None:
    st.success(
        f"Signed in as {mentor.get('full_name', 'mentor')} · "
        f"{mentor.get('professional_title', '')}"
    )
    if st.button("Sign out of mentor workspace", key="mentor_sign_out"):
        st.session_state.pop(MENTOR_STATE_KEY, None)
        st.rerun()

    sections = ["Availability", "Booking requests", "Upcoming", "Completed", "Profile"]
    section_key = f"mentor_workspace_section_{mentor['mentor_id']}"
    section = st.pills(
        "Mentor workspace section",
        sections,
        default=sections[0],
        key=section_key,
        label_visibility="collapsed",
        width="stretch",
    )
    if section == "Availability":
        _render_mentor_availability(mentor)
    elif section == "Booking requests":
        _render_mentor_requests(mentor)
    elif section == "Upcoming":
        _render_mentor_upcoming(mentor)
    elif section == "Completed":
        _render_mentor_completed(mentor)
    elif section == "Profile":
        _render_mentor_profile_form(mentor)


def _render_mentor_availability(mentor: dict) -> None:
    sub_section("Add availability")
    st.caption("Times are entered in Africa/Nairobi and stored in UTC.")
    minimum_date = date.today() + timedelta(days=1)
    with st.form("mentor_add_availability_form", clear_on_submit=False):
        day = st.date_input("Date", value=minimum_date, min_value=minimum_date)
        start_time = st.time_input("Start time (EAT)", value=time(9, 0))
        duration = st.selectbox(
            "Session duration",
            list(mentor.get("duration_options") or DURATION_OPTIONS),
            format_func=format_duration,
        )
        submitted = st.form_submit_button("Add availability slot", type="primary")
    if submitted:
        try:
            start_utc = nairobi_to_utc(day, start_time)
            create_availability(mentor["mentor_id"], start_utc.isoformat(), duration)
        except Exception as error:
            _render_error(error)
        else:
            _notify("Availability slot added.")
            st.rerun()

    sub_section("Your availability")
    slots = [
        slot
        for slot in list_mentor_availability(mentor["mentor_id"], include_past=False)
        if slot.get("status") != "removed"
    ]
    if not slots:
        st.info("No upcoming availability. Job seekers cannot book you yet.")
        return

    for slot in slots:
        local = parse_utc(slot["start_at_utc"]).astimezone(NAIROBI_TZ)
        label = (
            f"{format_nairobi(slot['start_at_utc'])} · "
            f"{format_duration(slot['duration_minutes'])} · "
            f"{str(slot.get('status', '')).title()}"
        )
        with st.expander(label, expanded=False):
            if slot["status"] == "open":
                _render_availability_editor(mentor, slot, local)
            elif slot["status"] == "booked":
                st.caption("This slot is booked. Manage it from Upcoming or Requests.")


def _render_availability_editor(mentor: dict, slot: dict, local: datetime) -> None:
    key = slot["slot_id"]
    with st.form(f"mentor_edit_slot_form_{key}", clear_on_submit=False):
        day = st.date_input(
            "New date",
            value=local.date(),
            min_value=date.today(),
            key=f"mentor_slot_date_{key}",
        )
        start_time = st.time_input(
            "New start time (EAT)",
            value=local.time().replace(second=0, microsecond=0),
            key=f"mentor_slot_time_{key}",
        )
        duration = st.selectbox(
            "Duration",
            list(mentor.get("duration_options") or DURATION_OPTIONS),
            index=max(
                0,
                list(mentor.get("duration_options") or DURATION_OPTIONS).index(
                    slot["duration_minutes"]
                )
                if slot["duration_minutes"]
                in (mentor.get("duration_options") or DURATION_OPTIONS)
                else 0,
            ),
            format_func=format_duration,
            key=f"mentor_slot_duration_{key}",
        )
        updated = st.form_submit_button("Save changes")
    if updated:
        try:
            update_availability(
                mentor["mentor_id"],
                key,
                nairobi_to_utc(day, start_time).isoformat(),
                duration,
            )
        except Exception as error:
            _render_error(error)
        else:
            _notify("Availability updated.")
            st.rerun()

    confirm = st.checkbox(
        "I understand removing this slot hides it from job seekers.",
        key=f"mentor_remove_confirm_{key}",
    )
    if st.button(
        "Remove availability",
        key=f"mentor_remove_slot_{key}",
        disabled=not confirm,
    ):
        try:
            remove_availability(mentor["mentor_id"], key)
        except Exception as error:
            _render_error(error)
        else:
            _notify("Availability slot removed.")
            st.rerun()


def _render_mentor_requests(mentor: dict) -> None:
    sub_section("Booking requests")
    bookings = [
        booking
        for booking in list_bookings_for_mentor(mentor["mentor_id"])
        if booking.get("status") == BOOKING_PENDING
    ]
    if not bookings:
        st.info("No pending booking requests.")
        return
    for booking in bookings:
        label = (
            f"{format_nairobi(booking['scheduled_start_utc'])} · "
            f"{booking.get('job_seeker_name', 'Job seeker')}"
        )
        with st.expander(label, expanded=True):
            _render_booking_meta(booking, perspective="mentor")
            note = st.text_input(
                "Note if rejecting (optional)",
                key=f"mentor_reject_note_{booking['booking_id']}",
            )
            approve_col, reject_col = st.columns(2)
            with approve_col:
                if st.button(
                    "Confirm booking",
                    key=f"mentor_confirm_{booking['booking_id']}",
                    type="primary",
                ):
                    try:
                        confirm_booking(booking["booking_id"], mentor["mentor_id"])
                    except Exception as error:
                        _render_error(error)
                    else:
                        _notify(
                            f"Booking {booking['booking_reference']} confirmed. "
                            "Add a meeting link from the Upcoming tab."
                        )
                        st.rerun()
            with reject_col:
                if st.button(
                    "Reject request",
                    key=f"mentor_reject_{booking['booking_id']}",
                ):
                    try:
                        reject_booking(
                            booking["booking_id"],
                            mentor["mentor_id"],
                            note,
                        )
                    except Exception as error:
                        _render_error(error)
                    else:
                        _notify("Booking request rejected and the slot released.")
                        st.rerun()


def _render_mentor_upcoming(mentor: dict) -> None:
    sub_section("Upcoming confirmed meetings")
    bookings = [
        booking
        for booking in list_bookings_for_mentor(mentor["mentor_id"])
        if booking.get("status") == BOOKING_CONFIRMED
    ]
    if not bookings:
        st.info("No confirmed upcoming meetings.")
        return
    for booking in bookings:
        with st.expander(
            f"{format_nairobi(booking['scheduled_start_utc'])} · "
            f"{booking.get('job_seeker_name', 'Job seeker')}",
            expanded=True,
        ):
            _render_booking_meta(booking, perspective="mentor")
            if booking.get("reschedule_requested_at"):
                st.warning(f"Reschedule request: {booking.get('reschedule_note', '')}")
                if st.button(
                    "Clear reschedule request",
                    key=f"mentor_clear_reschedule_{booking['booking_id']}",
                ):
                    try:
                        clear_reschedule_request(
                            booking["booking_id"], mentor["mentor_id"]
                        )
                    except Exception as error:
                        _render_error(error)
                    else:
                        _notify("Reschedule request cleared.")
                        st.rerun()
            link_key = f"mentor_link_{booking['booking_id']}"
            with st.form(link_key, clear_on_submit=False):
                link = st.text_input(
                    "Meeting link (https only)",
                    value=booking.get("meeting_link") or "",
                    placeholder="https://meet.example.com/your-private-room",
                )
                save_link = st.form_submit_button("Save meeting link")
            if save_link:
                try:
                    update_meeting_link(
                        booking["booking_id"], mentor["mentor_id"], link
                    )
                except Exception as error:
                    _render_error(error)
                else:
                    _notify("Meeting link saved privately to this booking.")
                    st.rerun()
            if booking.get("meeting_link"):
                st.link_button("Test meeting link", booking["meeting_link"])

            complete_col, cancel_col = st.columns(2)
            with complete_col:
                if st.button(
                    "Mark completed",
                    key=f"mentor_complete_{booking['booking_id']}",
                ):
                    try:
                        complete_booking(
                            booking["booking_id"], mentor["mentor_id"]
                        )
                    except Exception as error:
                        _render_error(error)
                    else:
                        _notify(
                            "Meeting marked completed. You can add recommendations "
                            "in the Completed tab."
                        )
                        st.rerun()
            with cancel_col:
                if st.button(
                    "Cancel meeting",
                    key=f"mentor_cancel_booking_{booking['booking_id']}",
                ):
                    try:
                        cancel_booking(
                            booking["booking_id"],
                            mentor_id=mentor["mentor_id"],
                            reason="Cancelled by mentor",
                        )
                    except Exception as error:
                        _render_error(error)
                    else:
                        _notify("Meeting cancelled and the slot released.")
                        st.rerun()


def _render_mentor_completed(mentor: dict) -> None:
    sub_section("Completed meetings")
    bookings = [
        booking
        for booking in list_bookings_for_mentor(mentor["mentor_id"])
        if booking.get("status") == BOOKING_COMPLETED
    ]
    if not bookings:
        st.info("No completed meetings yet.")
        return
    for booking in bookings:
        with st.expander(
            f"{format_nairobi(booking['scheduled_start_utc'])} · "
            f"{booking.get('job_seeker_name', 'Job seeker')}",
            expanded=False,
        ):
            _render_booking_meta(booking, perspective="mentor")
            if booking.get("feedback"):
                feedback = booking["feedback"]
                st.markdown("**Job seeker feedback**")
                st.write(f"Rating: {feedback.get('rating', 0)} / 5")
                if feedback.get("comment"):
                    st.write(feedback["comment"])
                if feedback.get("further_support"):
                    st.caption(f"Further support: {feedback['further_support']}")
            with st.form(
                f"mentor_recommendations_{booking['booking_id']}",
                clear_on_submit=False,
            ):
                recommendations = st.text_area(
                    "Preparation recommendations",
                    value=booking.get("mentor_recommendations") or "",
                    height=100,
                )
                saved = st.form_submit_button("Save recommendations")
            if saved:
                try:
                    update_mentor_recommendations(
                        booking["booking_id"],
                        mentor["mentor_id"],
                        recommendations,
                    )
                except Exception as error:
                    _render_error(error)
                else:
                    _notify("Recommendations saved for the job seeker.")
                    st.rerun()


def _render_mentor_profile_form(mentor: dict) -> None:
    sub_section("Public mentor profile")
    st.caption("Only approved public fields are shown in the mentor directory.")
    with st.form("mentor_profile_form", clear_on_submit=False):
        full_name = st.text_input("Full name", value=mentor.get("full_name", ""))
        title = st.text_input(
            "Professional title", value=mentor.get("professional_title", "")
        )
        biography = st.text_area(
            "Biography", value=mentor.get("biography", ""), height=120
        )
        industry = st.text_input("Industry", value=mentor.get("industry", ""))
        specialisation = st.text_input(
            "Specialisation", value=mentor.get("specialisation", "")
        )
        experience = st.text_area(
            "Professional experience", value=mentor.get("experience", ""), height=110
        )
        qualifications = st.text_area(
            "Qualifications", value=mentor.get("qualifications", ""), height=90
        )
        languages = st.text_input(
            "Languages (comma-separated)",
            value=", ".join(mentor.get("languages", [])),
        )
        coaching = st.text_input(
            "Coaching areas (comma-separated)",
            value=", ".join(mentor.get("coaching_areas", [])),
        )
        durations = st.multiselect(
            "Session durations",
            options=list(DURATION_OPTIONS),
            default=mentor.get("duration_options") or list(DURATION_OPTIONS),
            format_func=format_duration,
        )
        avatar_url = st.text_input(
            "Public profile image URL (https only)",
            value=mentor.get("avatar_url", ""),
        )
        saved = st.form_submit_button("Save public profile", type="primary")
    if saved:
        try:
            update_mentor_profile(
                mentor["mentor_id"],
                {
                    "full_name": full_name,
                    "professional_title": title,
                    "biography": biography,
                    "industry": industry,
                    "specialisation": specialisation,
                    "experience": experience,
                    "qualifications": qualifications,
                    "languages": languages,
                    "coaching_areas": coaching,
                    "duration_options": durations,
                    "avatar_url": avatar_url,
                },
            )
        except Exception as error:
            _render_error(error)
        else:
            _notify("Public mentor profile updated.")
            st.rerun()


def _render_admin_review() -> None:
    sub_section("Administrator review")
    section = _safe_secret_section()
    if not admin_access_configured(section):
        st.warning(
            "Administrator access is not configured. This app does not treat the "
            "active profile selector as administrator authentication."
        )
        st.caption("Add a strong code to Streamlit secrets, then reboot the app:")
        st.code(
            "[mentor_admin]\n"
            "access_code = \"replace-with-a-long-random-code\"\n\n"
            "# Stronger option: store only a PBKDF2 hash\n"
            "# access_code_hash = \"pbkdf2_sha256$...\"",
            language="toml",
        )
        return

    if not st.session_state.get(ADMIN_STATE_KEY):
        with st.form("mentor_admin_access_form", clear_on_submit=False):
            code = st.text_input("Administrator access code", type="password")
            submitted = st.form_submit_button("Open administrator review", type="primary")
        if submitted:
            if verify_admin_access(code, section):
                st.session_state[ADMIN_STATE_KEY] = True
                st.rerun()
            else:
                st.error("That administrator access code is not valid.")
        return

    st.success("Administrator session active for this Streamlit session.")
    if st.button("Sign out of administrator review", key="mentor_admin_sign_out"):
        st.session_state.pop(ADMIN_STATE_KEY, None)
        st.rerun()

    codes = st.session_state.get(NEW_CODES_KEY, {})
    for mentor_id, payload in list(codes.items()):
        st.warning(
            f"Share this access code privately with {payload['name']}. It is shown "
            "once and only a hash is stored."
        )
        st.code(payload["code"])
        if st.button(
            "I have shared this code",
            key=f"mentor_code_shared_{mentor_id}",
        ):
            codes.pop(mentor_id, None)
            st.session_state[NEW_CODES_KEY] = codes
            st.rerun()

    pending = list_mentor_applications("pending")
    if not pending:
        st.info("No pending mentor applications.")
    for application in pending:
        with st.expander(
            f"{application.get('full_name', 'Applicant')} · "
            f"{application.get('professional_title', '')}",
            expanded=True,
        ):
            st.write(f"Email: {application.get('email', '')}")
            st.write(f"Industry: {application.get('industry', '')}")
            st.write(f"Specialisation: {application.get('specialisation', '')}")
            st.write(
                "Areas of expertise: "
                + ", ".join(application.get("areas_of_expertise", []))
            )
            st.write(f"Languages: {', '.join(application.get('languages', []))}")
            st.markdown("**Experience**")
            st.write(application.get("experience", ""))
            st.markdown("**Biography**")
            st.write(application.get("biography", ""))
            st.markdown("**Qualifications**")
            st.write(application.get("qualifications", ""))
            if application.get("supporting_info"):
                st.markdown("**Supporting information**")
                st.write(application["supporting_info"])
            review_note = st.text_input(
                "Review note (optional)",
                key=f"mentor_admin_note_{application['application_id']}",
            )
            approve_col, reject_col = st.columns(2)
            with approve_col:
                if st.button(
                    "Approve application",
                    key=f"mentor_admin_approve_{application['application_id']}",
                    type="primary",
                ):
                    try:
                        result = review_mentor_application(
                            application["application_id"],
                            "approved",
                            review_note,
                        )
                    except Exception as error:
                        _render_error(error)
                    else:
                        if result.get("mentor") and result.get("access_code"):
                            codes = st.session_state.get(NEW_CODES_KEY, {})
                            codes[result["mentor"]["mentor_id"]] = {
                                "name": result["mentor"]["full_name"],
                                "code": result["access_code"],
                            }
                            st.session_state[NEW_CODES_KEY] = codes
                        _notify("Mentor application approved.")
                        st.rerun()
            with reject_col:
                if st.button(
                    "Reject application",
                    key=f"mentor_admin_reject_{application['application_id']}",
                ):
                    try:
                        review_mentor_application(
                            application["application_id"],
                            "rejected",
                            review_note,
                        )
                    except Exception as error:
                        _render_error(error)
                    else:
                        _notify("Mentor application rejected.")
                        st.rerun()

    reviewed = [
        application
        for application in list_mentor_applications()
        if application.get("status") != "pending"
    ]
    if reviewed:
        st.markdown("**Previously reviewed applications**")
        for application in reviewed:
            with st.expander(
                f"{_status_label(application.get('status', ''))} · "
                f"{application.get('full_name', 'Applicant')}",
                expanded=False,
            ):
                st.write(f"Email: {application.get('email', '')}")
                if application.get("reviewed_at"):
                    st.caption(
                        f"Reviewed {format_nairobi(application['reviewed_at'])}"
                    )
                if application.get("review_note"):
                    st.write(f"Review note: {application['review_note']}")
                if application.get("status") == "approved":
                    mentor = get_mentor_by_application(
                        application["application_id"]
                    )
                    if mentor:
                        st.caption(
                            "If the mentor loses the original code, issue a replacement. "
                            "The previous code stops working immediately."
                        )
                        if st.button(
                            "Issue replacement access code",
                            key=f"mentor_admin_rotate_{application['application_id']}",
                        ):
                            try:
                                replacement = rotate_mentor_access_code(
                                    mentor["mentor_id"]
                                )
                            except Exception as error:
                                _render_error(error)
                            else:
                                codes = st.session_state.get(NEW_CODES_KEY, {})
                                codes[mentor["mentor_id"]] = {
                                    "name": mentor["full_name"],
                                    "code": replacement,
                                }
                                st.session_state[NEW_CODES_KEY] = codes
                                _notify("Replacement mentor access code generated.")
                                st.rerun()
