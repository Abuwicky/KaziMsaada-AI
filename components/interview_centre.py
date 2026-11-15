"""Mock Interview Centre for the Interview Preparation page."""

from __future__ import annotations

import html
import sqlite3
from typing import Any, Mapping

import streamlit as st

from core.ai_client import ai_status, get_ai_provider
from core.interview import (
    CATEGORY_LABELS,
    CATEGORY_LABEL_TO_ID,
    DEFAULT_QUESTIONS_PER_SESSION,
    DIFFICULTY_LABELS,
    DIFFICULTY_LABEL_TO_ID,
    MAX_ANSWER_CHARS,
    MAX_QUESTIONS_PER_SESSION,
    MAX_TARGET_ROLE_CHARS,
    MIN_QUESTIONS_PER_SESSION,
    build_session_summary,
    category_label,
    difficulty_label,
    evaluate_answer,
    get_question,
    select_questions,
)
from core.interview_store import (
    DuplicateResponseError,
    InterviewSessionClosed,
    InterviewSessionNotFound,
    InterviewStoreError,
    InterviewValidationError,
    SESSION_CANCELLED,
    SESSION_COMPLETED,
    SESSION_IN_PROGRESS,
    cancel_session,
    complete_session,
    create_session,
    delete_session,
    get_responses,
    get_session,
    list_sessions,
    save_response,
)

from .ui import format_date, icon, sub_section

NO_ACTIVE_PROFILE_SCOPE = "no-active-profile"
STATUS_LABELS = {
    SESSION_IN_PROGRESS: "In progress",
    SESSION_COMPLETED: "Completed",
    SESSION_CANCELLED: "Ended early",
}


def interview_centre_profile_scope(profile: dict | None) -> str:
    if not profile:
        return NO_ACTIVE_PROFILE_SCOPE

    profile_id = str(profile.get("profile_id") or "").strip()
    return profile_id or NO_ACTIVE_PROFILE_SCOPE


def interview_centre_state_key(profile_scope: str, name: str) -> str:
    return f"mock_interview::{profile_scope}::{name}"


def _draft_widget_key(profile_scope: str, session_id: str, question_id: str) -> str:
    return f"mock_interview_answer_widget::{profile_scope}::{session_id}::{question_id}"


def _draft_store_key(profile_scope: str, session_id: str, question_id: str) -> str:
    return f"mock_interview_answer_store::{profile_scope}::{session_id}::{question_id}"


def _restore_widget_state(
    widget_key: str,
    store_key: str,
    default: str = "",
) -> None:
    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state.get(store_key, default)
    if store_key not in st.session_state:
        st.session_state[store_key] = st.session_state[widget_key]


def _persist_widget_state(store_key: str, widget_key: str) -> None:
    st.session_state[store_key] = st.session_state.get(widget_key, "")


def _resolve_provider():
    """Resolve an approved provider without ever calling the network here."""

    try:
        return get_ai_provider(), None
    except Exception:
        return None, (
            "AI feedback is unavailable in this workspace right now. "
            "Local question-bank guidance will be used."
        )


def render_interview_centre(profile: dict | None) -> None:
    """Render the landing page, active session, review, and history."""

    if not profile:
        st.info(
            "Create or select a saved profile to start a mock interview. "
            "Your practice sessions are stored separately for each profile."
        )
        return

    profile_id = str(profile.get("profile_id") or "").strip()
    if not profile_id:
        st.info("The active profile could not be identified. Please select a profile again.")
        return

    profile_scope = interview_centre_profile_scope(profile)
    active_key = interview_centre_state_key(profile_scope, "active_session_id")
    review_key = interview_centre_state_key(profile_scope, "review_session_id")
    notice_key = interview_centre_state_key(profile_scope, "notice")

    _render_landing_intro(profile)
    _render_ai_status()

    notice = st.session_state.pop(notice_key, None)
    if notice:
        st.info(notice)

    active_id = st.session_state.get(active_key)
    if active_id:
        session = get_session(active_id, profile_id)
        if session is None:
            st.session_state.pop(active_key, None)
        elif session["status"] == SESSION_IN_PROGRESS:
            _render_active_session(profile, profile_scope, session, active_key, review_key, notice_key)
            return
        else:
            st.session_state.pop(active_key, None)
            st.session_state[review_key] = session["id"]
            st.rerun()

    review_id = st.session_state.get(review_key)
    if review_id:
        session = get_session(review_id, profile_id)
        if session is None:
            st.session_state.pop(review_key, None)
        else:
            _render_session_review(profile_scope, session, active_key, review_key, notice_key)
            return

    _render_start_form(profile, profile_scope, active_key, review_key, notice_key)
    _render_history(profile_id, profile_scope, active_key, review_key)


def _render_landing_intro(profile: dict) -> None:
    name = html.escape(str(profile.get("name", "your profile")))
    interest = html.escape(str(profile.get("career_interest", "") or "your target area"))
    st.markdown(
        f"""
        <div class="km-note-card">
          {icon("sparkles", 24)}
          <div>
            <strong>Mock Interview Centre for {name}</strong>
            <span>
              Practise one question at a time, receive supportive feedback, and
              build confidence before the real conversation. Target area: {interest}.
              This release is text-based practice; human coach booking is planned
              for a later phase.
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "You do not need formal work experience. You can draw on academic projects, "
        "group assignments, volunteering, industrial attachment, internships, "
        "personal projects, or relevant life experiences."
    )
    st.caption(
        "Profile selection is a local convenience, not sign-in security. Add proper "
        "authentication and authorisation before exposing this workspace publicly."
    )


def _render_ai_status() -> None:
    availability = ai_status()
    if availability.available:
        st.caption("AI-assisted feedback is configured for this workspace.")
    elif availability.configured:
        st.warning(availability.message)
    else:
        st.info(availability.message)


def _render_start_form(
    profile: dict,
    profile_scope: str,
    active_key: str,
    review_key: str,
    notice_key: str,
) -> None:
    sub_section("Start a mock interview")
    st.caption(
        "Choose a role and interview style. The session is saved to this profile, "
        "so you can return to an incomplete session from your history."
    )

    profile_id = str(profile.get("profile_id"))
    default_role = str(profile.get("career_interest", "") or "").strip()[
        :MAX_TARGET_ROLE_CHARS
    ]
    form_key = interview_centre_state_key(profile_scope, "start_form")
    target_key = interview_centre_state_key(profile_scope, "target_role_input")
    category_key = interview_centre_state_key(profile_scope, "category_input")
    difficulty_key = interview_centre_state_key(profile_scope, "difficulty_input")
    count_key = interview_centre_state_key(profile_scope, "question_count_input")

    category_labels = list(CATEGORY_LABELS.values())
    difficulty_labels = list(DIFFICULTY_LABELS.values())

    with st.form(form_key, clear_on_submit=False):
        target_role = st.text_input(
            "Target job position",
            value=default_role,
            max_chars=MAX_TARGET_ROLE_CHARS,
            key=target_key,
            placeholder="e.g. Customer service assistant, ICT support officer",
        )
        category_choice = st.selectbox(
            "Interview category",
            category_labels,
            key=category_key,
            help="Choose the type of interview you want to practise.",
        )
        difficulty_choice = st.selectbox(
            "Difficulty level",
            difficulty_labels,
            key=difficulty_key,
            help="The session keeps its difficulty label and preferences in feedback.",
        )
        question_count = st.slider(
            "Number of questions",
            min_value=MIN_QUESTIONS_PER_SESSION,
            max_value=MAX_QUESTIONS_PER_SESSION,
            value=DEFAULT_QUESTIONS_PER_SESSION,
            step=1,
            key=count_key,
            help="A shorter session is easier to complete in one sitting.",
        )
        started = st.form_submit_button("Start mock interview", type="primary")

    if not started:
        return

    target_role = target_role.strip()
    if not target_role:
        st.error("Enter the job position you want to practise for.")
        return

    category_id = CATEGORY_LABEL_TO_ID.get(category_choice)
    difficulty_id = DIFFICULTY_LABEL_TO_ID.get(difficulty_choice)
    if not category_id or not difficulty_id:
        st.error("Choose a valid interview category and difficulty.")
        return

    try:
        questions = select_questions(
            category_id,
            difficulty_id,
            target_role,
            question_count,
        )
        if not questions:
            st.error(
                "No questions matched that configuration. Try another category or "
                "describe your target role differently."
            )
            return

        session = create_session(
            profile_id,
            target_role,
            category_id,
            difficulty_id,
            [question.question_id for question in questions],
        )
    except (InterviewValidationError, InterviewStoreError, sqlite3.Error) as error:
        st.error(f"The mock interview could not be started. {error}")
        return

    st.session_state[active_key] = session["id"]
    st.session_state.pop(review_key, None)
    st.session_state[notice_key] = (
        f"Mock interview started with {len(session['question_ids'])} questions."
    )
    st.rerun()


def _render_active_session(
    profile: dict,
    profile_scope: str,
    session: dict[str, Any],
    active_key: str,
    review_key: str,
    notice_key: str,
) -> None:
    profile_id = str(profile.get("profile_id"))
    session_id = str(session["id"])

    try:
        responses = get_responses(session_id, profile_id)
    except (InterviewSessionNotFound, sqlite3.Error) as error:
        st.error(f"Saved answers could not be loaded. {error}")
        return

    question_ids = [str(item) for item in session.get("question_ids", [])]
    total = len(question_ids)
    if total == 0:
        st.error("This practice session has no questions. End it and start again.")
        _render_cancel_control(profile_scope, session, active_key, notice_key)
        return

    answered_ids = {str(response["question_id"]) for response in responses}
    unanswered = [question_id for question_id in question_ids if question_id not in answered_ids]

    if not unanswered:
        _complete_and_review(
            profile_id,
            session,
            responses,
            active_key,
            review_key,
            notice_key,
        )
        return

    current_id = unanswered[0]
    question = get_question(current_id)
    if question is None:
        st.error("This session contains a question that is no longer available.")
        _render_cancel_control(profile_scope, session, active_key, notice_key)
        return

    question_number = question_ids.index(current_id) + 1
    category = category_label(str(session.get("category", "")))
    target_role = str(session.get("target_role", ""))
    difficulty = difficulty_label(str(session.get("difficulty", "")))

    st.markdown(
        f"### {category} · Question {question_number} of {total}"
    )
    st.caption(
        f"Target position: {target_role} · Difficulty: {difficulty}"
    )
    st.progress(min(1.0, len(responses) / total))
    st.caption(f"{len(responses)} of {total} questions answered")

    if responses:
        with st.expander("Feedback on your last answer", expanded=False):
            _render_feedback(responses[-1].get("feedback", {}))

    st.markdown(f"#### {question.question}")
    with st.expander("What the interviewer is assessing", expanded=False):
        st.write(question.assesses)
        st.markdown(f"**How to structure a good answer:** {question.structure}")

    draft_widget = _draft_widget_key(profile_scope, session_id, current_id)
    draft_store = _draft_store_key(profile_scope, session_id, current_id)
    _restore_widget_state(draft_widget, draft_store)
    answer = st.text_area(
        "Your answer",
        key=draft_widget,
        height=220,
        max_chars=MAX_ANSWER_CHARS,
        placeholder=(
            "Write what you would say aloud. Use a real example and be specific "
            "about what you personally did."
        ),
        on_change=_persist_widget_state,
        args=(draft_store, draft_widget),
    )
    words = len(answer.split()) if answer else 0
    st.caption(
        f"{words} words · aim for a focused answer of roughly one to two minutes. "
        "You can review it before submitting."
    )

    submit_key = interview_centre_state_key(
        profile_scope, f"submit::{session_id}::{current_id}"
    )
    if st.button(
        "Submit answer",
        key=submit_key,
        type="primary",
        disabled=not answer.strip(),
    ):
        _submit_answer(
            profile,
            profile_scope,
            session,
            current_id,
            answer,
            active_key,
            review_key,
            notice_key,
            draft_store,
        )

    st.caption(
        "Feedback is supportive practice guidance. It is not a score, a measurement "
        "of employability, or a guarantee of interview success."
    )
    _render_cancel_control(profile_scope, session, active_key, notice_key)


def _submit_answer(
    profile: dict,
    profile_scope: str,
    session: dict[str, Any],
    question_id: str,
    answer: str,
    active_key: str,
    review_key: str,
    notice_key: str,
    draft_store: str,
) -> None:
    profile_id = str(profile.get("profile_id"))
    session_id = str(session["id"])
    answer = str(answer or "").strip()

    if not answer:
        st.error("Write an answer before submitting.")
        return
    if len(answer) > MAX_ANSWER_CHARS:
        st.error(f"Keep your answer under {MAX_ANSWER_CHARS} characters.")
        return

    try:
        existing = get_responses(session_id, profile_id)
    except (InterviewSessionNotFound, sqlite3.Error) as error:
        st.error(f"The session could not be checked. {error}")
        return

    if question_id in {str(response["question_id"]) for response in existing}:
        st.info("That answer has already been saved. Moving to the next question.")
        st.rerun()

    question = get_question(question_id)
    if question is None:
        st.error("That question is no longer available.")
        return

    provider, provider_notice = _resolve_provider()
    feedback = evaluate_answer(
        question,
        answer,
        str(session.get("target_role", "")),
        str(session.get("difficulty", "")),
        provider=provider,
    )
    if provider_notice and feedback.get("source") != "ai":
        feedback["notice"] = provider_notice

    try:
        save_response(
            session_id,
            profile_id,
            question_id,
            answer,
            feedback,
            assessment_data={
                "source": feedback.get("source"),
                "feedback_kind": feedback.get("feedback_kind"),
                "word_count": feedback.get("word_count"),
            },
        )
    except DuplicateResponseError:
        st.info("That answer has already been saved. Moving to the next question.")
        st.rerun()
    except InterviewSessionClosed:
        st.session_state.pop(active_key, None)
        st.session_state[notice_key] = "This practice session is already closed."
        st.rerun()
    except (InterviewValidationError, InterviewStoreError, sqlite3.Error) as error:
        st.error(f"The answer could not be saved. {error}")
        return

    # The draft is complete. Clearing the non-widget store avoids restoring it if
    # the same question is ever rendered again.
    st.session_state.pop(draft_store, None)

    try:
        responses = get_responses(session_id, profile_id)
    except (InterviewSessionNotFound, sqlite3.Error):
        responses = []

    total = len(session.get("question_ids", []))
    if len(responses) >= total:
        _complete_and_review(
            profile_id,
            session,
            responses,
            active_key,
            review_key,
            notice_key,
        )
        return

    st.session_state[notice_key] = "Answer saved. Continue with the next question."
    st.rerun()


def _complete_and_review(
    profile_id: str,
    session: dict[str, Any],
    responses: list[dict[str, Any]],
    active_key: str,
    review_key: str,
    notice_key: str,
) -> None:
    summary = build_session_summary(responses)
    try:
        complete_session(
            str(session["id"]),
            profile_id,
            summary,
        )
    except (InterviewValidationError, InterviewSessionClosed, InterviewStoreError, sqlite3.Error) as error:
        st.error(f"The practice session could not be completed. {error}")
        return

    st.session_state.pop(active_key, None)
    st.session_state[review_key] = session["id"]
    st.session_state[notice_key] = "Practice session completed. Review your feedback below."
    st.rerun()


def _render_cancel_control(
    profile_scope: str,
    session: dict[str, Any],
    active_key: str,
    notice_key: str,
) -> None:
    session_id = str(session["id"])
    with st.expander("End this practice session", expanded=False):
        st.caption(
            "Submitted answers remain in your practice history. The session will be "
            "marked as ended early."
        )
        confirm_key = interview_centre_state_key(
            profile_scope, f"cancel_confirm::{session_id}"
        )
        if st.checkbox("I want to end this practice session.", key=confirm_key):
            button_key = interview_centre_state_key(
                profile_scope, f"cancel_button::{session_id}"
            )
            if st.button("End practice session", key=button_key):
                try:
                    cancel_session(session_id, str(session["profile_id"]))
                except (InterviewSessionClosed, InterviewStoreError, sqlite3.Error) as error:
                    st.error(f"The session could not be ended. {error}")
                    return
                st.session_state.pop(active_key, None)
                st.session_state[notice_key] = (
                    "Practice session ended early. Its answers are still available "
                    "in your history."
                )
                st.rerun()


def _render_session_review(
    profile_scope: str,
    session: dict[str, Any],
    active_key: str,
    review_key: str,
    notice_key: str,
) -> None:
    profile_id = str(session.get("profile_id"))
    status = str(session.get("status"))
    st.markdown("### Practice session review")
    st.caption(
        f"{category_label(str(session.get('category', '')))} · "
        f"{str(session.get('target_role', ''))} · "
        f"{difficulty_label(str(session.get('difficulty', '')))} · "
        f"Started {format_date(session.get('started_at'))}"
    )

    try:
        responses = get_responses(str(session["id"]), profile_id)
    except (InterviewSessionNotFound, sqlite3.Error) as error:
        st.error(f"Session answers could not be loaded. {error}")
        return

    total = len(session.get("question_ids", []))
    st.markdown(
        f"**Status:** {STATUS_LABELS.get(status, status)} · "
        f"**Questions answered:** {len(responses)} of {total}"
    )

    if status == SESSION_IN_PROGRESS:
        st.info(
            "This session is incomplete. You can continue it or leave it here; "
            "submitted answers are already saved."
        )
        if st.button(
            "Continue this session",
            key=interview_centre_state_key(profile_scope, f"continue_review::{session['id']}"),
            type="primary",
        ):
            st.session_state[active_key] = session["id"]
            st.session_state.pop(review_key, None)
            st.rerun()
    elif status == SESSION_CANCELLED:
        st.warning(
            "This session was ended early. You can review the answers and feedback "
            "that were submitted before it ended."
        )
    else:
        st.success("This practice session is complete.")

    overall = session.get("overall_feedback")
    if not isinstance(overall, Mapping):
        overall = build_session_summary(responses) if responses else None
    if overall:
        _render_overall_feedback(overall)

    if not responses:
        st.info("No answers were submitted in this session.")
    else:
        for index, response in enumerate(responses, start=1):
            with st.expander(
                f"Question {index}: {response.get('question_text', 'Interview question')}",
                expanded=index == 1,
            ):
                st.markdown("**Your answer**")
                st.write(response.get("answer_text", ""))
                st.markdown("**Feedback**")
                _render_feedback(response.get("feedback", {}))

    st.caption(
        "This review is a practice aid. It is not a definitive measurement of "
        "employability, intelligence, or personality."
    )

    with st.expander("Delete this practice record", expanded=False):
        st.caption(
            "This permanently removes the session and all answers from this "
            "profile's practice history."
        )
        delete_confirm_key = interview_centre_state_key(
            profile_scope, f"delete_confirm::{session['id']}"
        )
        if st.checkbox("I understand this cannot be undone.", key=delete_confirm_key):
            delete_button_key = interview_centre_state_key(
                profile_scope, f"delete_button::{session['id']}"
            )
            if st.button("Delete practice record", key=delete_button_key):
                try:
                    delete_session(str(session["id"]), profile_id)
                except (InterviewStoreError, sqlite3.Error) as error:
                    st.error(f"The practice record could not be deleted. {error}")
                    return
                st.session_state.pop(active_key, None)
                st.session_state.pop(review_key, None)
                st.session_state[notice_key] = "Practice record deleted."
                st.rerun()

    if st.button(
        "Back to Mock Interview Centre",
        key=interview_centre_state_key(profile_scope, f"close_review::{session['id']}"),
    ):
        st.session_state.pop(review_key, None)
        st.rerun()


def _render_overall_feedback(overall: Mapping[str, Any]) -> None:
    st.markdown("### Overall practice guidance")
    summary = str(overall.get("summary", "")).strip()
    if summary:
        st.write(summary)
    st.caption(
        "This overall summary is assembled locally from the feedback saved for "
        "each answer."
    )

    strengths = overall.get("strengths", [])
    if isinstance(strengths, (list, tuple)) and strengths:
        st.markdown("**Strengths to keep**")
        for item in strengths:
            st.write(f"• {item}")

    improvements = overall.get("improvements", [])
    if isinstance(improvements, (list, tuple)) and improvements:
        st.markdown("**Areas to improve**")
        for item in improvements:
            st.write(f"• {item}")

    next_steps = overall.get("next_steps", [])
    if isinstance(next_steps, (list, tuple)) and next_steps:
        st.markdown("**Recommended next practice steps**")
        for item in next_steps:
            st.write(f"• {item}")

    disclaimer = str(overall.get("disclaimer", "")).strip()
    if disclaimer:
        st.caption(disclaimer)


def _render_feedback(feedback: Mapping[str, Any]) -> None:
    if not isinstance(feedback, Mapping) or not feedback:
        st.write("No feedback is available for this answer.")
        return

    source = str(feedback.get("source", "local_guidance"))
    if source == "ai":
        st.caption("Source: AI-generated practice feedback.")
    elif source == "local_fallback":
        st.warning(
            str(
                feedback.get(
                    "notice",
                    "AI feedback was unavailable. This is local question-bank guidance.",
                )
            )
        )
    else:
        st.caption(
            "Source: local question-bank guidance. This is not AI-generated feedback."
        )

    for label, key in (
        ("Relevance to the question", "relevance"),
        ("Clarity of communication", "clarity"),
        ("Answer structure", "structure"),
        ("Quality and relevance of examples", "examples"),
    ):
        value = str(feedback.get(key, "")).strip()
        if value:
            st.markdown(f"**{label}**")
            st.write(value)

    suggestions = feedback.get("suggestions", [])
    if isinstance(suggestions, (list, tuple)) and suggestions:
        st.markdown("**Actionable improvement suggestions**")
        for item in suggestions:
            st.write(f"• {item}")

    star = feedback.get("star_checklist")
    if isinstance(star, Mapping) and star:
        found = [str(name).title() for name, present in star.items() if present]
        if found:
            st.caption("STAR elements detected in your answer: " + ", ".join(found))
        else:
            st.caption(
                "No STAR elements were detected. Try Situation, Task, Action and Result."
            )

    disclaimer = str(feedback.get("disclaimer", "")).strip()
    if disclaimer:
        st.caption(disclaimer)


def _render_history(
    profile_id: str,
    profile_scope: str,
    active_key: str,
    review_key: str,
) -> None:
    sub_section("Practice history")
    try:
        sessions = list_sessions(profile_id)
    except (InterviewValidationError, sqlite3.Error) as error:
        st.error(f"Practice history could not be loaded. {error}")
        return

    if not sessions:
        st.caption("No mock interview sessions yet. Start one above when you are ready.")
        return

    for session in sessions[:20]:
        session_id = str(session["id"])
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(
                    f"**{session.get('target_role', 'Interview practice')}**"
                )
                st.caption(
                    f"{category_label(str(session.get('category', '')))} · "
                    f"{difficulty_label(str(session.get('difficulty', '')))} · "
                    f"{format_date(session.get('started_at'))} · "
                    f"{session.get('answered_count', 0)} answers"
                )
            with right:
                status = str(session.get("status"))
                st.caption(STATUS_LABELS.get(status, status))
                action_label = "Continue" if status == SESSION_IN_PROGRESS else "Review"
                if st.button(
                    action_label,
                    key=interview_centre_state_key(
                        profile_scope, f"history::{session_id}"
                    ),
                ):
                    if status == SESSION_IN_PROGRESS:
                        st.session_state[active_key] = session_id
                        st.session_state.pop(review_key, None)
                    else:
                        st.session_state[review_key] = session_id
                    st.rerun()

    if len(sessions) > 20:
        st.caption("Showing the 20 most recent sessions.")
