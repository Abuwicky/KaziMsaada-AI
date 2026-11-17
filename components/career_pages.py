"""Guided career-support pages: interview, skills, guidance, and job search."""

from __future__ import annotations

import html
import sqlite3

import streamlit as st

from core.ai_client import AIProviderError, ai_status, get_ai_provider
from core.interview import CORE_INTERVIEW_QUESTIONS as INTERVIEW_QUESTIONS
from core.interview import CORE_QUESTION_IDS as INTERVIEW_QUESTION_IDS
from core.interview import CORE_QUESTION_LOOKUP as INTERVIEW_QUESTION_LOOKUP
from core.interview import InterviewConfigurationError, build_model_answer
from core.profiles import update_profile_record
from core.skill_assessment import (
    ASSESSMENT_TYPE_LABELS,
    ASSESSMENT_TYPES,
    CAREER_AREAS,
    KNOWLEDGE,
    PRACTICAL,
    SKILLS,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    TARGET_CAREER_AREA,
    TARGET_SKILL,
    SkillAssessmentError,
    build_plan,
    build_result_summary,
    get_career_area,
    get_skill,
)
from core.skill_assessment_store import (
    DuplicateAssessmentResponse,
    complete_assessment,
    create_assessment,
    get_assessment,
    get_assessment_questions,
    get_responses,
    list_assessments,
    save_response,
)

from .interview_centre import render_interview_centre
from .ui import (
    format_date,
    go_to,
    icon,
    page_header,
    set_flash,
    skill_chips,
    sub_section,
)

INTERVIEW_PRACTICE_QUESTION_KEY = "interview_practice_question_id"

INTERVIEW_STAR_FIELDS = (
    ("situation", "Situation"),
    ("task", "Task"),
    ("action", "Action"),
    ("result", "Result"),
)

INTERVIEW_CHECKLIST = (
    (
        "job_description_requirements",
        "Re-read the job description and note the top five requirements.",
    ),
    (
        "prepare_relevant_examples",
        "Prepare two or three real examples that match those requirements.",
    ),
    (
        "research_organisation",
        "Research the organisation's work, values, and recent public updates.",
    ),
    (
        "confirm_interview_details",
        "Confirm the interview time, format, location, or link.",
    ),
    (
        "prepare_questions_for_panel",
        "Prepare your own questions for the panel.",
    ),
    (
        "prepare_cv_and_certificates",
        "Print or save a clean copy of your CV and any certificates requested.",
    ),
    (
        "plan_route_and_travel_time",
        "Plan your route and leave enough travel time.",
    ),
)

SKILL_GROUPS = {
    "Digital and technical": [
        "Computer literacy",
        "Microsoft Office",
        "Data entry",
        "Programming",
        "Web development",
        "Computer networking",
        "Cybersecurity awareness",
        "Data analysis",
        "Graphic design",
        "Digital marketing",
        "Social media management",
        "Database administration",
    ],
    "Communication and people": [
        "Communication",
        "Customer care",
        "Public speaking",
        "Report writing",
        "Active listening",
        "Presentation skills",
        "Teamwork",
        "Conflict resolution",
        "Community engagement",
        "Teaching",
    ],
    "Work readiness": [
        "Time management",
        "Problem solving",
        "Critical thinking",
        "Adaptability",
        "Leadership",
        "Planning and organising",
        "Attention to detail",
        "Working under pressure",
        "Professional ethics",
    ],
    "Practical and job-specific": [
        "Accounting",
        "Bookkeeping",
        "Sales",
        "Project management",
        "Masonry",
        "Plumbing",
        "Electrical installation",
        "Caregiving",
        "Agriculture",
        "Logistics",
        "Hospitality",
        "Driving",
    ],
}

PATHWAYS = {
    "ICT and digital services": {
        "aliases": ["ict", "information technology", "computer", "software", "network", "data", "digital"],
        "summary": "Support, build, or secure the technology that organisations rely on.",
        "roles": [
            "ICT support / helpdesk officer",
            "Junior network or systems administrator",
            "Web or software developer (entry level)",
            "Data entry or data quality assistant",
            "Digital marketing or social media assistant",
        ],
        "skills": [
            "Computer literacy and troubleshooting",
            "Networking fundamentals",
            "One programming language",
            "Database basics and data handling",
            "Clear written communication",
        ],
        "steps": [
            "Build one small portfolio project you can explain end to end.",
            "Practise a mock support scenario: diagnose, resolve, document.",
            "Add measurable outcomes to your CV, not just task lists.",
            "Look for internships, attachments, and volunteer IT support roles.",
        ],
    },
    "Business, finance and administration": {
        "aliases": ["business", "finance", "account", "admin", "sales", "bank", "commerce"],
        "summary": "Keep organisations organised, compliant, and financially healthy.",
        "roles": [
            "Accounts assistant",
            "Administrative assistant",
            "Customer service representative",
            "Sales or business development assistant",
            "Procurement or stores assistant",
        ],
        "skills": [
            "Bookkeeping and spreadsheet confidence",
            "Accuracy and attention to detail",
            "Customer care and professional writing",
            "Time management and prioritisation",
            "Basic business reporting",
        ],
        "steps": [
            "Practise building a simple budget and expense report.",
            "Learn one accounting or spreadsheet workflow thoroughly.",
            "Prepare an example of handling a difficult customer or deadline.",
            "Target entry roles that offer structured training.",
        ],
    },
    "Health and community services": {
        "aliases": ["health", "nurse", "clinical", "community", "social work", "care", "counselling"],
        "summary": "Support people's wellbeing through direct care, coordination, or community work.",
        "roles": [
            "Community health assistant",
            "Care assistant",
            "Social work assistant",
            "Health records or clinic assistant",
            "Programme support assistant (NGO)",
        ],
        "skills": [
            "Confidentiality and professional boundaries",
            "Empathy and active listening",
            "Record keeping and reporting",
            "Team coordination",
            "Community facilitation",
        ],
        "steps": [
            "Confirm the licensing or registration requirements for your role.",
            "Gain supervised volunteering experience where possible.",
            "Prepare examples that show calm judgement under pressure.",
            "Highlight safeguarding and confidentiality awareness in your CV.",
        ],
    },
    "Education and training": {
        "aliases": ["education", "teacher", "teaching", "training", "tutor", "school"],
        "summary": "Help learners build knowledge and practical confidence.",
        "roles": [
            "Teaching assistant",
            "Tutor or learning support assistant",
            "Training coordinator",
            "Education programme assistant",
            "Content or curriculum support assistant",
        ],
        "skills": [
            "Lesson planning and explanation",
            "Classroom or group management",
            "Assessment and feedback",
            "Patience and adaptability",
            "Record keeping",
        ],
        "steps": [
            "Check registration requirements with the relevant authority.",
            "Prepare a short sample lesson or training session.",
            "Collect feedback from learners or peers and refine it.",
            "Show evidence of reaching learners with different needs.",
        ],
    },
    "Trades and technical work": {
        "aliases": ["construction", "building", "masonry", "plumbing", "electrical", "technical", "mechanic", "welding"],
        "summary": "Apply practical technical skill to build, maintain, and repair.",
        "roles": [
            "Masonry or construction assistant",
            "Plumbing assistant",
            "Electrical installation assistant",
            "Motor vehicle mechanic assistant",
            "Maintenance technician (entry level)",
        ],
        "skills": [
            "Safe use of tools and materials",
            "Reading drawings or technical instructions",
            "Measurement and quality checks",
            "Worksite safety",
            "Reliable record keeping",
        ],
        "steps": [
            "Document projects you have completed with photos and measurements.",
            "Confirm any certification required for electrical or specialised work.",
            "Ask experienced practitioners for a short reference.",
            "Emphasise safety, reliability, and finishing quality in your CV.",
        ],
    },
    "Creative and media": {
        "aliases": ["creative", "media", "design", "art", "journalism", "film", "photography", "content"],
        "summary": "Turn ideas into clear visuals, stories, and communication that audiences understand.",
        "roles": [
            "Graphic design assistant",
            "Content or social media assistant",
            "Photography or video assistant",
            "Communications assistant",
            "Copywriting or editorial assistant",
        ],
        "skills": [
            "One core design or editing tool",
            "Clear storytelling and structure",
            "Audience awareness",
            "Feedback and revision",
            "Deadline management",
        ],
        "steps": [
            "Build a small portfolio of three to five finished pieces.",
            "Explain the brief, your choices, and the result for each piece.",
            "Practise writing short, plain-language captions and summaries.",
            "Look for volunteer or community content projects.",
        ],
    },
    "Agriculture and environment": {
        "aliases": ["agriculture", "agri", "environment", "farming", "livestock", "conservation"],
        "summary": "Improve productivity, sustainability, and food or environmental outcomes.",
        "roles": [
            "Farm or field assistant",
            "Agribusiness sales assistant",
            "Environmental programme assistant",
            "Extension support assistant",
            "Records and logistics assistant",
        ],
        "skills": [
            "Practical field observation",
            "Record keeping and basic analysis",
            "Community communication",
            "Safety and sustainability awareness",
            "Planning seasonal work",
        ],
        "steps": [
            "Document a practical project, including inputs and results.",
            "Learn basic record keeping for yields or costs.",
            "Connect with cooperatives, extension officers, or local programmes.",
            "Show reliability and problem solving in your examples.",
        ],
    },
}

TRUSTED_SOURCES = [
    ("BrighterMonday Kenya", "https://www.brightermonday.co.ke", "Broad range of Kenyan vacancies."),
    ("Fuzu", "https://www.fuzu.com/kenya", "Graduate, internship, and professional roles."),
    ("MyJobMag Kenya", "https://www.myjobmag.co.ke", "Frequently updated job listings."),
    ("Ajira Digital", "https://ajiradigital.go.ke", "Digital work readiness and freelancing resources."),
    ("Public Service Commission", "https://www.psc.go.ke", "Public service vacancies and announcements."),
]


NO_ACTIVE_PROFILE_SCOPE = "no-active-profile"

PATHWAY_TO_ASSESSMENT_AREA = {
    "ICT and digital services": "digital_technical",
    "Creative and media": "digital_technical",
    "Business, finance and administration": "practical_job_specific",
    "Health and community services": "communication_people",
    "Education and training": "communication_people",
    "Trades and technical work": "practical_job_specific",
    "Agriculture and environment": "practical_job_specific",
}


def _active_profile(profiles: list[dict]) -> dict | None:
    lookup = {profile["profile_id"]: profile for profile in profiles}
    active = lookup.get(st.session_state.get("active_profile_id"))
    return active or (profiles[0] if profiles else None)


def interview_profile_scope(profile: dict | None) -> str:
    """Return a stable session-state namespace for the active profile."""

    if not profile:
        return NO_ACTIVE_PROFILE_SCOPE

    profile_id = str(profile.get("profile_id") or "").strip()
    return profile_id or NO_ACTIVE_PROFILE_SCOPE


def interview_answer_widget_key(profile_scope: str, question_id: str) -> str:
    return f"interview_answer_widget::{profile_scope}::{question_id}"


def interview_answer_store_key(profile_scope: str, question_id: str) -> str:
    return f"interview_answer_store::{profile_scope}::{question_id}"


def interview_star_widget_key(
    profile_scope: str,
    question_id: str,
    star_field: str,
) -> str:
    return f"interview_star_widget::{profile_scope}::{question_id}::{star_field}"


def interview_star_store_key(
    profile_scope: str,
    question_id: str,
    star_field: str,
) -> str:
    return f"interview_star_store::{profile_scope}::{question_id}::{star_field}"


def interview_model_answer_key(profile_scope: str, question_id: str) -> str:
    return f"interview_model_answer::{profile_scope}::{question_id}"


def interview_model_answer_button_key(profile_scope: str, question_id: str) -> str:
    return f"interview_model_answer_button::{profile_scope}::{question_id}"


def interview_checklist_key(item_id: str) -> str:
    return f"interview_check::{item_id}"


def skill_assessment_active_key(profile_scope: str) -> str:
    return f"skill_assessment_active::{profile_scope}"


def skill_assessment_view_key(profile_scope: str) -> str:
    return f"skill_assessment_view::{profile_scope}"


def skill_assessment_answer_key(
    assessment_id: str,
    question_id: str,
) -> str:
    return f"skill_assessment_answer::{assessment_id}::{question_id}"


def _restore_widget_state(widget_key: str, store_key: str, default) -> None:
    """Restore a widget value without replacing an existing live widget value."""

    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state.get(store_key, default)
    if store_key not in st.session_state:
        st.session_state[store_key] = st.session_state[widget_key]


def _persist_widget_state(store_key: str, widget_key: str, default) -> None:
    st.session_state[store_key] = st.session_state.get(widget_key, default)


def _render_model_answer(model_answer: dict) -> None:
    st.markdown("#### AI-generated model answer")
    st.markdown(str(model_answer.get("model_answer", "")))

    why_it_works = str(model_answer.get("why_it_works", "") or "").strip()
    if why_it_works:
        st.markdown(f"**Why this example works:** {why_it_works}")

    star_breakdown = model_answer.get("star_breakdown")
    if isinstance(star_breakdown, dict) and star_breakdown:
        st.markdown("**STAR breakdown**")
        for label in ("Situation", "Task", "Action", "Result"):
            value = str(star_breakdown.get(label, "") or "").strip()
            if value:
                st.markdown(f"**{label}:** {value}")

    tips = model_answer.get("tips")
    if isinstance(tips, (list, tuple)) and tips:
        st.markdown("**Make it your own**")
        for tip in tips:
            text = str(tip).strip()
            if text:
                st.markdown(f"- {text}")

    st.caption(
        str(
            model_answer.get("disclaimer", "")
            or "AI-generated practice example, not the only correct answer."
        )
    )


def render_interview_page(profiles: list[dict]) -> None:
    profile = _active_profile(profiles)
    profile_scope = interview_profile_scope(profile)
    page_header(
        "Interview preparation",
        "Practise the conversation before it matters",
        "Use real examples from your study, work, projects, or volunteering. "
        "Clear structure beats memorised answers.",
    )

    if profile:
        st.markdown(
            f"""
            <div class="km-note-card">
              {icon("message", 22)}
              <div>
                <strong>Preparing with {html.escape(str(profile.get("name", "your profile")))}</strong>
                <span>Target area: {html.escape(str(profile.get("career_interest", "not set")))}. Bring examples that connect your skills to that work.</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "No saved profile is active. You can still use the question bank and "
            "practise answers; they stay in this Streamlit session and are not saved."
        )

    tab_centre, tab_questions, tab_practice, tab_before = st.tabs(
        [
            "Mock Interview Centre",
            "Question bank",
            "STAR practice",
            "Before the interview",
        ]
    )

    with tab_centre:
        render_interview_centre(profile)

    with tab_questions:
        st.markdown(
            '<div class="km-guided-label">Guided preview · curated questions and coaching notes, not AI-generated answers</div>',
            unsafe_allow_html=True,
        )
        for question in INTERVIEW_QUESTIONS:
            with st.expander(f"{question.category} · {question.question}"):
                st.markdown(f"**What they are assessing:** {question.assesses}")
                st.markdown(f"**How to structure your answer:** {question.structure}")
                st.caption(
                    "Use a real example. Keep it under two minutes and finish with the result."
                )

    with tab_practice:
        sub_section("Build one answer at a time")
        if (
            st.session_state.get(INTERVIEW_PRACTICE_QUESTION_KEY)
            not in INTERVIEW_QUESTION_LOOKUP
        ):
            st.session_state.pop(INTERVIEW_PRACTICE_QUESTION_KEY, None)

        selected_question_id = st.selectbox(
            "Choose a question",
            INTERVIEW_QUESTION_IDS,
            format_func=lambda question_id: (
                f"{INTERVIEW_QUESTION_LOOKUP[question_id].category} · "
                f"{INTERVIEW_QUESTION_LOOKUP[question_id].question}"
            ),
            key=INTERVIEW_PRACTICE_QUESTION_KEY,
        )
        question = INTERVIEW_QUESTION_LOOKUP[selected_question_id]

        st.markdown(f"**Question:** {question.question}")
        st.caption(question.structure)

        model_answer_key = interview_model_answer_key(
            profile_scope, question.question_id
        )
        model_answer = st.session_state.get(model_answer_key)
        availability = ai_status()
        provider = None
        if availability.available:
            try:
                provider = get_ai_provider()
            except Exception:
                provider = None
        supports_model_answers = provider is not None and callable(
            getattr(provider, "generate_model_answer", None)
        )

        if supports_model_answers:
            st.caption(
                "Stuck? AI can draft one example answer. There is no single correct "
                "answer; use it as a practice model and replace placeholders with "
                "your own real experience."
            )
            button_label = (
                "Generate another AI model answer"
                if model_answer
                else "Generate AI model answer"
            )
            if st.button(
                button_label,
                key=interview_model_answer_button_key(
                    profile_scope, question.question_id
                ),
            ):
                target_role = str(
                    (profile or {}).get("career_interest", "") or ""
                ).strip()
                with st.spinner("Drafting a practice model answer..."):
                    try:
                        generated_answer = build_model_answer(
                            question,
                            target_role,
                            question.difficulty,
                            provider=provider,
                        )
                    except (
                        AIProviderError,
                        InterviewConfigurationError,
                        ValueError,
                    ) as error:
                        st.warning(
                            "An AI model answer could not be generated right now. "
                            f"{error} Your answer has not been changed; you can "
                            "retry or keep building your own response."
                        )
                    except Exception:
                        st.warning(
                            "An AI model answer could not be generated right now. "
                            "Your answer has not been changed. Try again or keep "
                            "building your own response."
                        )
                    else:
                        st.session_state[model_answer_key] = generated_answer
                        st.rerun()
        elif availability.available:
            st.caption(
                "The configured AI provider does not support model answers. The STAR "
                "exercise still works without AI."
            )
        elif availability.configured:
            st.info(availability.message)
        else:
            st.info(availability.message)

        if isinstance(model_answer, dict):
            _render_model_answer(model_answer)
            st.caption(
                "The AI model answer is displayed in this Streamlit session only and "
                "is not saved to your profile or database. Generating it sends only "
                "the question, target role, category and difficulty; your answer, "
                "profile and CV are not sent."
            )

        answer_widget_key = interview_answer_widget_key(
            profile_scope, question.question_id
        )
        answer_store_key = interview_answer_store_key(
            profile_scope, question.question_id
        )
        _restore_widget_state(answer_widget_key, answer_store_key, "")
        answer = st.text_area(
            "Your answer",
            key=answer_widget_key,
            height=190,
            placeholder="Situation → Task → Action → Result. Be specific about what you personally did.",
            on_change=_persist_widget_state,
            args=(answer_store_key, answer_widget_key, ""),
        )

        words = len(answer.split()) if answer else 0
        st.caption(
            f"{words} words · aim for roughly 120–220 words for a spoken answer "
            "of about one to two minutes."
        )

        star_columns = st.columns(4)
        for column, (star_field, star_label) in zip(
            star_columns, INTERVIEW_STAR_FIELDS
        ):
            star_widget_key = interview_star_widget_key(
                profile_scope, question.question_id, star_field
            )
            star_store_key = interview_star_store_key(
                profile_scope, question.question_id, star_field
            )
            _restore_widget_state(star_widget_key, star_store_key, False)
            with column:
                st.checkbox(
                    star_label,
                    key=star_widget_key,
                    on_change=_persist_widget_state,
                    args=(star_store_key, star_widget_key, False),
                )

        st.caption(
            "The STAR checkboxes are a manual self-review, not an AI evaluation "
            "or score. The optional AI model answer is a practice example, not an "
            "evaluation. Practice answers stay in this Streamlit session only, are "
            "kept separately for the active profile, and are not saved to your "
            "profile or database."
        )

    with tab_before:
        sub_section("Two days before")
        for item_id, item in INTERVIEW_CHECKLIST:
            st.checkbox(item, key=interview_checklist_key(item_id))

        sub_section("In the room or on the call")
        st.markdown(
            "- Listen to the whole question before answering.\n"
            "- It is acceptable to pause and think.\n"
            "- If you do not understand, ask for clarification.\n"
            "- Use specific examples rather than general claims.\n"
            "- Be honest about what you have not done yet, and show willingness to learn.\n"
            "- Thank the panel and ask about next steps."
        )


def render_skills_page(profiles: list[dict]) -> None:
    profile = _active_profile(profiles)
    page_header(
        "Skills assessment",
        "Take a guided assessment or record what you can already evidence",
        "Use a structured knowledge and practical assessment to identify strengths "
        "and development areas, then keep a saved progress record. These results "
        "are indicative practice, not a formal qualification.",
    )

    guided_tab, self_tab, history_tab = st.tabs(
        ["Guided assessment", "Self-assessment", "Results history"]
    )

    with guided_tab:
        _render_guided_assessment(profile)

    with self_tab:
        _render_self_assessment(profile)

    with history_tab:
        _render_assessment_history(profile)


def _render_self_assessment(profile: dict | None) -> None:
    all_skills = []
    canonical = {}
    for group in SKILL_GROUPS.values():
        for skill in group:
            key = skill.casefold()
            if key not in canonical:
                canonical[key] = skill
                all_skills.append(skill)

    profile_skills = [str(skill) for skill in (profile or {}).get("skills", [])]
    for skill in profile_skills:
        key = skill.casefold()
        if key not in canonical:
            canonical[key] = skill
            all_skills.append(skill)

    # Multiselect defaults must exactly match option values. Map the saved
    # profile skills onto their canonical spelling (e.g. "Digital Marketing"
    # -> "Digital marketing") so Streamlit accepts the defaults.
    default_skills = [
        canonical[skill.casefold()]
        for skill in profile_skills
        if skill.casefold() in canonical
    ]

    st.markdown(
        '<div class="km-guided-label">Self-assessment snapshot · your selections stay in this session</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.25, 1], gap="large")

    with left:
        selected = st.multiselect(
            "Skills you can already demonstrate",
            options=sorted(all_skills, key=str.casefold),
            default=default_skills,
            key="skills_strengths",
            help="Choose skills you could give a concrete example of in an interview.",
        )

        develop_options = sorted(all_skills, key=str.casefold)
        develop = st.multiselect(
            "Skills you want to develop next",
            options=develop_options,
            key="skills_develop",
            help="Choose two or three priorities rather than everything at once.",
        )
        develop = [skill for skill in develop if skill not in selected]

        if profile and selected:
            save_note = (
                "Saving adds these skills to your profile. Existing skills are kept; "
                "nothing is removed."
            )
            st.caption(save_note)
            if st.button(
                "Add selected skills to my profile",
                key="skills_save_profile",
                type="primary",
            ):
                updated = dict(profile)
                existing = {str(skill).casefold() for skill in updated.get("skills", [])}
                merged = list(updated.get("skills", []))
                for skill in selected:
                    if skill.casefold() not in existing:
                        merged.append(skill)
                        existing.add(skill.casefold())
                updated["skills"] = merged
                try:
                    changed = update_profile_record(updated)
                except sqlite3.Error as error:
                    st.error("Your skills could not be saved. No changes were made.")
                    with st.expander("Technical details"):
                        st.code(f"{type(error).__name__}: {error}", language=None)
                else:
                    if changed:
                        set_flash("Selected skills added to your profile.")
                        st.rerun()
                    else:
                        st.error("The profile could not be updated. Refresh and try again.")

    with right:
        categories_covered = 0
        for group_skills in SKILL_GROUPS.values():
            group_set = {skill.casefold() for skill in group_skills}
            if any(skill.casefold() in group_set for skill in selected):
                categories_covered += 1

        st.markdown(
            f"""
            <div class="km-skill-summary">
              <div class="km-skill-score">{len(selected)}</div>
              <div class="km-skill-score-label">skills you can evidence</div>
              <div class="km-skill-divider"></div>
              <div class="km-skill-stat"><span>Categories covered</span><strong>{categories_covered} of {len(SKILL_GROUPS)}</strong></div>
              <div class="km-skill-stat"><span>Development priorities</span><strong>{len(develop)}</strong></div>
              <div class="km-skill-stat"><span>Saved on profile</span><strong>{len(profile_skills)}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if selected:
            sub_section("Your selected strengths")
            st.markdown(skill_chips(selected), unsafe_allow_html=True)

        if develop:
            sub_section("Suggested next steps")
            for skill in develop[:3]:
                st.markdown(
                    f"- Build one small piece of evidence for **{html.escape(skill)}** "
                    "(a project, volunteer task, short course, or documented example)."
                )
            if len(develop) > 3:
                st.caption("Focus on the first three before adding more.")
        else:
            st.info("Choose one or two development priorities to see suggested next steps.")

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)
    sub_section("Explore skill groups")
    for group, skills in SKILL_GROUPS.items():
        with st.expander(group):
            st.markdown(skill_chips(skills), unsafe_allow_html=True)


def _suggested_assessment_area(profile: dict | None) -> str | None:
    pathway = _match_pathway(profile)
    return PATHWAY_TO_ASSESSMENT_AREA.get(pathway) if pathway else None


def _assessment_status_label(status: str) -> str:
    return "Completed" if status == STATUS_COMPLETED else "In progress"


def _render_assessment_db_error(error: Exception) -> None:
    st.error(
        "The skill assessment could not be saved. Existing results were not "
        "changed."
    )
    with st.expander("Technical details"):
        st.code(f"{type(error).__name__}: {error}", language=None)


def _render_guided_assessment(profile: dict | None) -> None:
    if not profile:
        st.info(
            "Create or select a working profile to save a guided assessment. "
            "The self-assessment tab still works without a profile, but guided "
            "results are attached to the active profile so you can track progress."
        )
        return

    profile_id = str(profile.get("profile_id") or "").strip()
    profile_scope = interview_profile_scope(profile)
    active_key = skill_assessment_active_key(profile_scope)
    view_key = skill_assessment_view_key(profile_scope)

    active_id = st.session_state.get(active_key)
    if active_id:
        try:
            assessment = get_assessment(active_id, profile_id)
        except sqlite3.Error as error:
            _render_assessment_db_error(error)
            return
        if assessment and assessment.get("status") == STATUS_IN_PROGRESS:
            _render_assessment_runner(profile, assessment)
            return
        if assessment and assessment.get("status") == STATUS_COMPLETED:
            st.session_state.pop(active_key, None)
            st.session_state[view_key] = assessment["assessment_id"]
            st.rerun()
        st.session_state.pop(active_key, None)

    view_id = st.session_state.get(view_key)
    if view_id:
        try:
            assessment = get_assessment(view_id, profile_id)
        except sqlite3.Error as error:
            _render_assessment_db_error(error)
            return
        if assessment:
            if assessment.get("status") == STATUS_IN_PROGRESS:
                st.session_state.pop(view_key, None)
                st.session_state[active_key] = assessment["assessment_id"]
                st.rerun()
            _render_assessment_result(profile, assessment)
            return
        st.session_state.pop(view_key, None)

    _render_assessment_chooser(profile)


def _render_assessment_chooser(profile: dict) -> None:
    profile_id = str(profile.get("profile_id") or "").strip()
    profile_scope = interview_profile_scope(profile)
    active_key = skill_assessment_active_key(profile_scope)
    view_key = skill_assessment_view_key(profile_scope)
    suggested_area = _suggested_assessment_area(profile)

    st.markdown(
        '<div class="km-guided-label">Guided assessment · deterministic marking · no AI required</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Assess a whole career area or one skill. You can take knowledge questions, "
        "practical exercises, or both."
    )

    target_type = st.radio(
        "What do you want to assess?",
        options=[TARGET_CAREER_AREA, TARGET_SKILL],
        format_func=lambda value: (
            "A career area"
            if value == TARGET_CAREER_AREA
            else "One individual skill"
        ),
        horizontal=True,
        key=f"skill_assessment_target::{profile_scope}",
    )

    if target_type == TARGET_CAREER_AREA:
        area_ids = [area.area_id for area in CAREER_AREAS]
        area_lookup = {area.area_id: area for area in CAREER_AREAS}
        default_index = (
            area_ids.index(suggested_area)
            if suggested_area in area_ids
            else 0
        )
        area_id = st.selectbox(
            "Career area",
            options=area_ids,
            index=default_index,
            format_func=lambda value: area_lookup[value].label,
            key=f"skill_assessment_area::{profile_scope}",
        )
        area = get_career_area(area_id)
        if area is None:
            st.error("Choose a valid career area.")
            return
        target_id = area.area_id
        target_label = area.label
        description = area.description
        skill_labels = [
            get_skill(skill_id).label
            for skill_id in area.skill_ids
            if get_skill(skill_id)
        ]
        pathway_names = area.pathway_names
        if suggested_area == area.area_id:
            st.caption(
                "Suggested from the career interest in your active profile. "
                "You can choose a different area."
            )
    else:
        assessable_by_label = {
            skill.label.casefold(): skill for skill in SKILLS
        }
        skill_options = [
            (group_label, assessable_by_label[label.casefold()])
            for group_label, group_skills in SKILL_GROUPS.items()
            for label in group_skills
            if label.casefold() in assessable_by_label
        ]
        skill_ids = [skill.skill_id for _group, skill in skill_options]
        skill_lookup = {
            skill.skill_id: skill for _group, skill in skill_options
        }
        group_lookup = {
            skill.skill_id: group_label
            for group_label, skill in skill_options
        }
        saved_skills = {
            str(skill).casefold()
            for skill in (profile.get("skills") or [])
        }
        default_skill_index = next(
            (
                index
                for index, (_group, skill) in enumerate(skill_options)
                if skill.label.casefold() in saved_skills
            ),
            0,
        )
        skill_id = st.selectbox(
            "Individual skill",
            options=skill_ids,
            index=default_skill_index,
            format_func=lambda value: (
                f"{group_lookup[value]} · {skill_lookup[value].label}"
            ),
            key=f"skill_assessment_skill::{profile_scope}",
        )
        skill = get_skill(skill_id)
        if skill is None:
            st.error("Choose a valid skill.")
            return
        target_id = skill.skill_id
        target_label = skill.label
        description = skill.description
        skill_labels = [skill.label]
        pathway_names = skill.pathway_names

    assessment_type = st.radio(
        "Assessment method",
        options=list(ASSESSMENT_TYPES),
        format_func=lambda value: ASSESSMENT_TYPE_LABELS[value],
        key=f"skill_assessment_method::{profile_scope}",
        help=(
            "Knowledge questions are marked automatically. Practical exercises "
            "are reviewed against criteria and are not given an automatic score."
        ),
    )

    try:
        plan = build_plan(target_type, target_id, assessment_type)
    except SkillAssessmentError as error:
        st.error(str(error))
        return

    with st.container(border=True):
        st.markdown(f"#### {plan.assessment_name}")
        st.markdown(plan.description)
        knowledge_count = len(plan.knowledge_questions)
        practical_count = len(plan.practical_questions)
        st.markdown(
            f"**Questions:** {len(plan.questions)} "
            f"({knowledge_count} knowledge, {practical_count} practical)"
        )
        st.markdown(f"**Estimated time:** about {plan.estimated_minutes} minutes")
        st.markdown("**Timer:** No countdown timer. Take your time.")
        if assessment_type == KNOWLEDGE:
            st.markdown(
                "**Scoring:** Knowledge answers are marked automatically. "
                "You will see explanations after completing the assessment."
            )
        elif assessment_type == PRACTICAL:
            st.markdown(
                "**Scoring:** Practical responses are not automatically scored. "
                "Review them against the marking criteria and expected elements."
            )
        else:
            st.markdown(
                "**Scoring:** The knowledge section is marked automatically. "
                "Practical responses are reviewed against criteria and are not "
                "part of the percentage score."
            )
        st.markdown(
            "**Saving:** Your progress is saved to the active profile after each "
            "answer. Previous attempts are kept."
        )
        st.caption(
            "Results are indicative practice, not formal qualifications, "
            "professional certification, or proof of workplace competence."
        )
        st.markdown(
            f"**Skills included:** {', '.join(html.escape(item) for item in skill_labels)}"
        )
        if pathway_names:
            st.caption(
                "Related career pathways: "
                + ", ".join(html.escape(name) for name in pathway_names)
            )

    try:
        in_progress = list_assessments(
            profile_id,
            status=STATUS_IN_PROGRESS,
        )
    except sqlite3.Error as error:
        _render_assessment_db_error(error)
        in_progress = []

    matching_attempts = [
        assessment
        for assessment in in_progress
        if assessment.get("assessment_key") == plan.assessment_key
        and assessment.get("assessment_type") == plan.assessment_type
        and assessment.get("content_version") == plan.content_version
    ]
    if matching_attempts:
        latest_attempt = matching_attempts[0]
        st.info(
            "You already have an unfinished attempt for this assessment choice. "
            "You can continue it, or start a new attempt below."
        )
        if st.button(
            "Continue unfinished attempt",
            key=f"skill_assessment_continue_matching::{profile_scope}",
        ):
            st.session_state[active_key] = latest_attempt["assessment_id"]
            st.session_state.pop(view_key, None)
            st.rerun()

    if st.button(
        "Start assessment",
        type="primary",
        key=f"skill_assessment_start::{profile_scope}",
    ):
        try:
            assessment = create_assessment(profile_id, plan)
        except sqlite3.Error as error:
            _render_assessment_db_error(error)
        except SkillAssessmentError as error:
            st.error(str(error))
        else:
            st.session_state[active_key] = assessment["assessment_id"]
            st.session_state.pop(view_key, None)
            st.rerun()

    st.caption(
        "Starting again creates a new attempt. It does not overwrite earlier "
        "results."
    )


def _render_assessment_runner(
    profile: dict,
    assessment: dict,
) -> None:
    profile_id = str(profile.get("profile_id") or "").strip()
    profile_scope = interview_profile_scope(profile)
    active_key = skill_assessment_active_key(profile_scope)
    view_key = skill_assessment_view_key(profile_scope)
    assessment_id = str(assessment.get("assessment_id") or "")

    try:
        questions = get_assessment_questions(assessment_id, profile_id)
        responses = get_responses(assessment_id, profile_id)
    except sqlite3.Error as error:
        _render_assessment_db_error(error)
        return

    if not questions:
        st.error(
            "This assessment has no available questions. Its saved history has "
            "not been changed."
        )
        if st.button(
            "Back to assessment choices",
            key=f"skill_assessment_missing::{assessment_id}",
        ):
            st.session_state.pop(active_key, None)
            st.rerun()
        return

    answered_ids = {
        str(response.get("question_id")) for response in responses
    }
    total = len(questions)
    answered_count = sum(
        1 for question in questions if question.question_id in answered_ids
    )
    progress = answered_count / total if total else 0.0

    st.markdown(
        '<div class="km-guided-label">Saved assessment · progress is kept for this profile</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"### {assessment.get('assessment_name', 'Skill assessment')}")
    st.caption(
        f"{assessment.get('skill_category', '')} · "
        f"{ASSESSMENT_TYPE_LABELS.get(assessment.get('assessment_type'), 'Assessment')} · "
        f"{_assessment_status_label(str(assessment.get('status', '')))}"
    )
    st.progress(min(1.0, progress))
    st.caption(
        f"{answered_count} of {total} questions answered. Progress is saved after "
        "each answer."
    )

    current_question = next(
        (
            question
            for question in questions
            if question.question_id not in answered_ids
        ),
        None,
    )

    if current_question is not None:
        question_number = questions.index(current_question) + 1
        with st.container(border=True):
            st.markdown(f"#### Question {question_number} of {total}")
            st.caption(
                f"{current_question.skill_label} · "
                f"{current_question.difficulty.title()} · "
                f"{current_question.question_type.title()}"
            )
            st.markdown(f"**{current_question.question}**")

            if current_question.question_type == KNOWLEDGE:
                option_lookup = {
                    option.option_id: option
                    for option in current_question.options
                }
                option_ids = [""] + list(option_lookup)
                with st.form(
                    key=(
                        "skill_assessment_form::"
                        f"{assessment_id}::{current_question.question_id}"
                    ),
                    clear_on_submit=False,
                ):
                    selected = st.radio(
                        "Choose one answer",
                        options=option_ids,
                        format_func=lambda value: (
                            "Select an answer"
                            if not value
                            else option_lookup[value].text
                        ),
                        key=skill_assessment_answer_key(
                            assessment_id,
                            current_question.question_id,
                        ),
                    )
                    submitted = st.form_submit_button(
                        "Save answer",
                        type="primary",
                    )

                if submitted:
                    try:
                        save_response(
                            assessment_id,
                            profile_id,
                            current_question.question_id,
                            selected_answer=selected,
                        )
                    except DuplicateAssessmentResponse:
                        set_flash(
                            "That answer was already saved. Continuing.",
                            "info",
                        )
                        st.rerun()
                    except SkillAssessmentError as error:
                        st.error(str(error))
                    except sqlite3.Error as error:
                        _render_assessment_db_error(error)
                    else:
                        set_flash(
                            "Answer saved. Continue with the next question.",
                            "success",
                        )
                        st.rerun()
            else:
                with st.expander("Marking criteria", expanded=True):
                    for criterion in current_question.marking_criteria:
                        st.markdown(f"- {criterion}")
                with st.form(
                    key=(
                        "skill_assessment_form::"
                        f"{assessment_id}::{current_question.question_id}"
                    ),
                    clear_on_submit=False,
                ):
                    response_text = st.text_area(
                        "Your response",
                        key=skill_assessment_answer_key(
                            assessment_id,
                            current_question.question_id,
                        ),
                        height=220,
                        placeholder=(
                            "Use a real or realistic example. Explain what you "
                            "would do and why."
                        ),
                    )
                    submitted = st.form_submit_button(
                        "Save practical response",
                        type="primary",
                    )

                if submitted:
                    try:
                        save_response(
                            assessment_id,
                            profile_id,
                            current_question.question_id,
                            response_text=response_text,
                        )
                    except DuplicateAssessmentResponse:
                        set_flash(
                            "That response was already saved. Continuing.",
                            "info",
                        )
                        st.rerun()
                    except SkillAssessmentError as error:
                        st.error(str(error))
                    except sqlite3.Error as error:
                        _render_assessment_db_error(error)
                    else:
                        set_flash(
                            "Practical response saved. Continue with the next question.",
                            "success",
                        )
                        st.rerun()

        if st.button(
            "Save and exit",
            key=f"skill_assessment_exit::{assessment_id}",
        ):
            st.session_state.pop(active_key, None)
            set_flash(
                "Assessment progress saved. Continue from Results history.",
                "info",
            )
            st.rerun()
        st.caption(
            "Each answer is saved only when you press its save button. You can "
            "leave and continue later from Results history."
        )
    else:
        st.success("All questions in this attempt have been answered.")
        st.caption(
            "Review your answers before finishing. Finishing saves the "
            "deterministic score and proficiency band, where applicable."
        )
        if st.button(
            "Finish assessment and save result",
            type="primary",
            key=f"skill_assessment_finish::{assessment_id}",
        ):
            try:
                completed = complete_assessment(assessment_id, profile_id)
            except SkillAssessmentError as error:
                st.error(str(error))
            except sqlite3.Error as error:
                _render_assessment_db_error(error)
            else:
                st.session_state.pop(active_key, None)
                st.session_state[view_key] = completed["assessment_id"]
                set_flash(
                    "Assessment completed and saved to the active profile."
                )
                st.rerun()

    if responses:
        with st.expander(
            f"Review answered questions ({len(responses)})",
            expanded=False,
        ):
            for index, response in enumerate(responses):
                _render_response_feedback(response)
                if index < len(responses) - 1:
                    st.divider()


def _render_response_feedback(response: dict) -> None:
    feedback = response.get("feedback")
    feedback = feedback if isinstance(feedback, dict) else {}
    question_text = str(response.get("question_text") or "Question")
    question_type = str(response.get("question_type") or "")

    st.markdown(f"**{question_text}**")

    if question_type == KNOWLEDGE:
        selected = (
            feedback.get("selected_option_text")
            or response.get("selected_answer")
            or "Not recorded"
        )
        st.write(f"Your answer: {selected}")
        if response.get("is_correct") is True:
            st.markdown("**Correct**")
        elif response.get("is_correct") is False:
            st.markdown("**Not correct**")
            st.write(
                "Correct answer: "
                f"{feedback.get('correct_option_text') or 'Not recorded'}"
            )
        explanation = str(feedback.get("explanation") or "").strip()
        if explanation:
            st.caption(f"Why: {explanation}")
        return

    st.write("Your response:")
    st.write(response.get("response_text") or "(No response recorded)")
    criteria = feedback.get("marking_criteria") or []
    if isinstance(criteria, list) and criteria:
        st.markdown("**Marking criteria**")
        for criterion in criteria:
            st.markdown(f"- {criterion}")
    expected = feedback.get("expected_elements") or []
    if isinstance(expected, list) and expected:
        st.markdown("**Expected elements**")
        for element in expected:
            st.markdown(f"- {element}")
    st.caption(
        "This practical response is not automatically scored. It is practice "
        "evidence, not a professional certification."
    )


def _render_assessment_result(
    profile: dict,
    assessment: dict,
    surface: str = "guided",
) -> None:
    profile_id = str(profile.get("profile_id") or "").strip()
    profile_scope = interview_profile_scope(profile)
    active_key = skill_assessment_active_key(profile_scope)
    view_key = skill_assessment_view_key(profile_scope)
    assessment_id = str(assessment.get("assessment_id") or "")

    if assessment.get("status") != STATUS_COMPLETED:
        _render_assessment_runner(profile, assessment)
        return

    try:
        questions = get_assessment_questions(assessment_id, profile_id)
        responses = get_responses(assessment_id, profile_id)
    except sqlite3.Error as error:
        _render_assessment_db_error(error)
        return

    summary = build_result_summary(assessment, questions, responses)

    st.markdown(
        '<div class="km-guided-label">Guided assessment result · saved to this profile</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"### {assessment.get('assessment_name', 'Skill assessment')}")
    st.caption(
        f"{assessment.get('skill_category', '')} · "
        f"{summary['method_label']} · "
        f"Completed {format_date(assessment.get('completed_at'))}"
    )

    if summary["score_percent"] is not None:
        st.markdown(
            f"""
            <div class="km-skill-summary">
              <div class="km-skill-score">{summary['score_percent']}%</div>
              <div class="km-skill-score-label">{html.escape(str(summary['proficiency_label'] or ''))}</div>
              <div class="km-skill-divider"></div>
              <div class="km-skill-stat"><span>Knowledge questions</span><strong>{summary['knowledge_answered']} of {summary['knowledge_total']}</strong></div>
              <div class="km-skill-stat"><span>Correct answers</span><strong>{summary['knowledge_correct']}</strong></div>
              <div class="km-skill-stat"><span>Practical exercises</span><strong>{summary['practical_answered']}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="km-skill-summary">
              <div class="km-skill-score">{summary['practical_answered']}</div>
              <div class="km-skill-score-label">practical exercises submitted</div>
              <div class="km-skill-divider"></div>
              <div class="km-skill-stat"><span>Automatic score</span><strong>Not available</strong></div>
              <div class="km-skill-stat"><span>Proficiency band</span><strong>Not assigned</strong></div>
              <div class="km-skill-stat"><span>Review method</span><strong>Marking criteria</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(
        f"Questions completed: {summary['questions_answered']} of "
        f"{summary['questions_planned']}."
    )
    st.markdown(summary["message"])
    if summary["proficiency_description"]:
        st.caption(summary["proficiency_description"])

    left, right = st.columns(2)
    with left:
        sub_section("Skills demonstrated")
        if summary["strong_areas"]:
            st.markdown(
                skill_chips(summary["strong_areas"]),
                unsafe_allow_html=True,
            )
        elif summary["knowledge_total"]:
            st.caption(
                "No knowledge area was fully correct in this attempt. That is "
                "useful information for planning practice."
            )
        else:
            st.caption(
                "This was a practical-only assessment, so no automatic skill "
                "score is assigned."
            )

    with right:
        sub_section("Areas to improve")
        if summary["improve_areas"]:
            st.markdown(
                skill_chips(summary["improve_areas"]),
                unsafe_allow_html=True,
            )
        elif summary["knowledge_total"]:
            st.caption("No incorrect knowledge answers were recorded.")
        else:
            st.caption("Review the practical criteria below to identify next steps.")

    if summary["incorrect_answers"]:
        sub_section("Review incorrect answers")
        for item in summary["incorrect_answers"]:
            label = (
                f"{item.get('skill_label') or 'Knowledge'} · "
                f"{str(item.get('question') or 'Question')[:90]}"
            )
            with st.expander(label):
                st.write(
                    f"Your answer: {item.get('selected_answer') or 'Not recorded'}"
                )
                st.write(
                    f"Correct answer: {item.get('correct_answer') or 'Not recorded'}"
                )
                st.caption(str(item.get("explanation") or ""))

    if summary["practical_review"]:
        sub_section("Practical exercise review")
        st.caption(
            "These responses are not automatically scored. Use the criteria and "
            "expected elements to review your own answer or discuss it with a "
            "mentor."
        )
        for item in summary["practical_review"]:
            with st.expander(
                str(item.get("question") or "Practical exercise")
            ):
                st.write("Your response:")
                st.write(item.get("response") or "(No response recorded)")
                if item.get("marking_criteria"):
                    st.markdown("**Marking criteria**")
                    for criterion in item["marking_criteria"]:
                        st.markdown(f"- {criterion}")
                if item.get("expected_elements"):
                    st.markdown("**Expected elements**")
                    for element in item["expected_elements"]:
                        st.markdown(f"- {element}")

    sub_section("Recommended next steps")
    for step in summary["next_steps"]:
        st.markdown(f"- {step}")

    if summary["pathway_names"]:
        sub_section("Related career pathways")
        for pathway_name in summary["pathway_names"]:
            pathway = PATHWAYS.get(pathway_name)
            if not pathway:
                continue
            st.markdown(f"**{html.escape(pathway_name)}**")
            for step in pathway["steps"][:2]:
                st.markdown(f"- {step}")
        st.caption(
            "These are existing pathway suggestions, not guaranteed training "
            "places, certificates, or job opportunities."
        )

    st.caption(summary["disclaimer"])
    st.caption(
        "This result is based only on this guided assessment. It is kept "
        "separate from the skills you select in the self-assessment and is not "
        "used to overwrite your profile skills."
    )

    if st.button(
        "Start another assessment",
        type="primary",
        key=f"skill_assessment_new::{surface}::{assessment_id}",
    ):
        st.session_state.pop(active_key, None)
        st.session_state.pop(view_key, None)
        st.rerun()


def _render_progress_comparison(assessments: list[dict]) -> None:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for assessment in assessments:
        if assessment.get("status") != STATUS_COMPLETED:
            continue
        if assessment.get("score") is None:
            continue
        key = (
            str(assessment.get("assessment_key") or ""),
            str(assessment.get("assessment_type") or ""),
            str(assessment.get("content_version") or ""),
        )
        groups.setdefault(key, []).append(assessment)

    comparable_groups = {
        key: attempts
        for key, attempts in groups.items()
        if len(attempts) >= 2
    }
    if not comparable_groups:
        st.caption(
            "Complete the same assessment choice more than once to see a simple "
            "progress comparison."
        )
        return

    sub_section("Progress over time")
    st.caption(
        "Only completed attempts with the same target, assessment method, and "
        "content version are compared. Practical-only attempts have no "
        "comparable score."
    )

    for (_key, method, _version), attempts in comparable_groups.items():
        ordered = sorted(
            attempts,
            key=lambda item: (
                str(item.get("started_at") or ""),
                str(item.get("completed_at") or ""),
            ),
        )
        first = ordered[0]
        last = ordered[-1]
        delta = int(round(float(last["score"]) - float(first["score"])))
        with st.expander(
            f"{last.get('assessment_name', 'Assessment')} · "
            f"{ASSESSMENT_TYPE_LABELS.get(method, method)}"
        ):
            for attempt in ordered:
                st.markdown(
                    f"- {format_date(attempt.get('completed_at'))} · "
                    f"**{int(round(float(attempt['score'])))}%** · "
                    f"{attempt.get('proficiency_level') or 'No band'}"
                )
            if delta > 0:
                st.success(
                    f"Up {delta} percentage points from the first comparable "
                    "attempt."
                )
            elif delta < 0:
                st.warning(
                    f"Down {abs(delta)} percentage points from the first "
                    "comparable attempt. Use the recommendations to plan the "
                    "next practice step."
                )
            else:
                st.info(
                    "The latest comparable score is the same as the first."
                )


def _render_assessment_history(profile: dict | None) -> None:
    if not profile:
        st.info(
            "Create or select a working profile to save and track guided "
            "assessments."
        )
        return

    profile_id = str(profile.get("profile_id") or "").strip()
    profile_scope = interview_profile_scope(profile)
    active_key = skill_assessment_active_key(profile_scope)
    view_key = skill_assessment_view_key(profile_scope)

    view_id = st.session_state.get(view_key)
    if view_id:
        try:
            viewed = get_assessment(view_id, profile_id)
        except sqlite3.Error as error:
            _render_assessment_db_error(error)
            viewed = None
        if viewed:
            if viewed.get("status") == STATUS_COMPLETED:
                _render_assessment_result(profile, viewed, surface="history")
                st.divider()
            else:
                st.session_state.pop(view_key, None)
                st.session_state[active_key] = viewed["assessment_id"]
                st.rerun()
        else:
            st.session_state.pop(view_key, None)

    try:
        assessments = list_assessments(profile_id)
    except sqlite3.Error as error:
        _render_assessment_db_error(error)
        return

    st.markdown(
        '<div class="km-guided-label">Results history · saved to this profile</div>',
        unsafe_allow_html=True,
    )
    if not assessments:
        st.info(
            "No guided assessments yet. Start one from the Guided assessment "
            "tab. Previous attempts are kept when you start again."
        )
        return

    _render_progress_comparison(assessments)

    sub_section("All saved attempts")
    for assessment in assessments:
        status_label = _assessment_status_label(
            str(assessment.get("status") or "")
        )
        when = format_date(
            assessment.get("completed_at") or assessment.get("started_at")
        )
        with st.expander(
            f"{assessment.get('assessment_name', 'Assessment')} · "
            f"{when} · {status_label}"
        ):
            question_count = len(assessment.get("question_ids") or [])
            response_count = int(assessment.get("response_count") or 0)
            st.caption(
                f"{assessment.get('skill_category', '')} · "
                f"{ASSESSMENT_TYPE_LABELS.get(assessment.get('assessment_type'), 'Assessment')} · "
                f"{response_count} of {question_count} answered"
            )

            if assessment.get("status") == STATUS_COMPLETED:
                if assessment.get("score") is not None:
                    st.markdown(
                        f"**Score:** {int(round(float(assessment['score'])))}% · "
                        f"{assessment.get('proficiency_level') or 'No band'}"
                    )
                else:
                    st.caption(
                        "This practical-only attempt has no automatic score."
                    )
                if st.button(
                    "Open full result",
                    key=f"skill_assessment_open::{assessment['assessment_id']}",
                ):
                    st.session_state[view_key] = assessment["assessment_id"]
                    st.rerun()
            else:
                st.caption(
                    "This attempt is incomplete. Its saved answers are kept."
                )
                if st.button(
                    "Continue assessment",
                    key=f"skill_assessment_resume::{assessment['assessment_id']}",
                ):
                    st.session_state[active_key] = assessment["assessment_id"]
                    st.session_state.pop(view_key, None)
                    st.rerun()


def _match_pathway(profile: dict | None) -> str | None:
    if not profile:
        return None

    text = " ".join(
        [
            str(profile.get("career_interest", "")),
            str(profile.get("education", "")),
            str(profile.get("experience", "")),
            " ".join(profile.get("skills", [])),
        ]
    ).casefold()

    best = None
    best_score = 0
    for name, pathway in PATHWAYS.items():
        score = sum(1 for alias in pathway["aliases"] if alias in text)
        if score > best_score:
            best = name
            best_score = score

    return best


def render_guidance_page(profiles: list[dict]) -> None:
    profile = _active_profile(profiles)
    page_header(
        "Career guidance",
        "Explore a direction, then test it in the real world",
        "Use these pathway summaries to compare roles, skills, and practical next "
        "steps. Always verify current requirements with employers and professional bodies.",
    )

    suggested = _match_pathway(profile)
    if profile and suggested:
        st.markdown(
            f"""
            <div class="km-note-card">
              {icon("compass", 22)}
              <div>
                <strong>Suggested starting point: {html.escape(suggested)}</strong>
                <span>Based on the career interest and skills saved in {html.escape(str(profile.get("name", "your profile")))}. This is a starting point, not a verdict.</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    names = list(PATHWAYS)
    default_index = names.index(suggested) if suggested in names else 0
    chosen = st.selectbox("Explore a pathway", names, index=default_index, key="guidance_pathway")
    pathway = PATHWAYS[chosen]

    st.markdown(
        f"""
        <div class="km-pathway">
          <div class="km-pathway-head">
            <div>
              <div class="km-eyebrow">Pathway</div>
              <h2>{html.escape(chosen)}</h2>
              <p>{html.escape(pathway["summary"])}</p>
            </div>
            <div class="km-pathway-icon">{icon("compass", 34)}</div>
          </div>
          <div class="km-pathway-columns">
            <div>
              <h3>Typical entry roles</h3>
              <ul>{''.join(f'<li>{html.escape(role)}</li>' for role in pathway["roles"])}</ul>
            </div>
            <div>
              <h3>Skills employers look for</h3>
              <ul>{''.join(f'<li>{html.escape(skill)}</li>' for skill in pathway["skills"])}</ul>
            </div>
          </div>
          <div class="km-pathway-steps">
            <h3>Practical next steps</h3>
            <ol>{''.join(f'<li>{html.escape(step)}</li>' for step in pathway["steps"])}</ol>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_left, action_mid, _ = st.columns([1, 1, 2.4])
    with action_left:
        st.button(
            "Assess your skills",
            key="guidance_skills",
            width="stretch",
            on_click=go_to,
            args=("Skills Assessment",),
        )
    with action_mid:
        st.button(
            "Tailor your CV",
            key="guidance_cv",
            width="stretch",
            on_click=go_to,
            args=("CV Builder",),
        )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)
    sub_section("Cross-cutting moves that help in most pathways")
    st.markdown(
        "- Build evidence: projects, volunteering, attachments, or documented tasks.\n"
        "- Ask two people doing the work what they wish they had learned earlier.\n"
        "- Keep a simple record of achievements, numbers, and feedback.\n"
        "- Strengthen plain-language writing and basic spreadsheet skills.\n"
        "- Verify licensing, registration, or certification requirements before paying for training.\n"
        "- Research current salary ranges yourself; they vary by employer and county."
    )


def render_job_search_page(profiles: list[dict]) -> None:
    profile = _active_profile(profiles)
    page_header(
        "Job search support",
        "Apply deliberately, not endlessly",
        "A practical checklist, trusted places to look, and a clear reminder of how "
        "to protect yourself from job scams.",
    )

    if profile:
        st.markdown(
            f"""
            <div class="km-note-card">
              {icon("briefcase", 22)}
              <div>
                <strong>Ready to tailor your application, {html.escape(str(profile.get("name", "friend")))}?</strong>
                <span>Use the same profile to produce a role-specific CV in the CV Builder.</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    left, right = st.columns([1.15, 1], gap="large")

    with left:
        sub_section("Application checklist")
        checklist = [
            "I have read the full job description and noted the closing date.",
            "My CV matches the role title and the top requirements.",
            "I have tailored my summary and examples to this employer.",
            "My contact details and referees are correct.",
            "I have checked spelling, dates, and file names.",
            "I have prepared a short, specific cover message.",
            "I know how and where to submit the application.",
            "I have saved a copy of what I submitted.",
        ]
        for index, item in enumerate(checklist):
            st.checkbox(item, key=f"job_check_{index}")
        st.caption("Checklist state is session-only and is not saved to the database.")

    with right:
        sub_section("Where to look")
        for name, url, note in TRUSTED_SOURCES:
            st.markdown(
                f"**[{name}]({url})**  \n{note}"
            )

        sub_section("Build a stronger application")
        st.markdown(
            "- Mirror the employer's job title in your CV target position.\n"
            "- Put the most relevant evidence in the top half of page one.\n"
            "- Use numbers where you can: users supported, projects delivered, marks improved.\n"
            "- Keep one CV file per application so you can track what you sent.\n"
            "- Follow up politely once if the employer provided a contact."
        )

    st.markdown('<div class="km-space"></div>', unsafe_allow_html=True)
    sub_section("Protect yourself from job scams")
    st.error(
        "Never pay a fee to get a job, interview, or placement. Legitimate "
        "employers do not ask candidates to pay for employment."
    )
    scam_left, scam_right = st.columns(2)
    with scam_left:
        st.markdown(
            "- Be cautious of offers without an interview.\n"
            "- Check that the email domain matches the organisation.\n"
            "- Do not share bank details, passwords, or ID scans early.\n"
            "- Meet in a public place or a real office for interviews."
        )
    with scam_right:
        st.markdown(
            "- Be wary of unusually high pay for vague work.\n"
            "- Do not install unknown apps or pay for 'registration'.\n"
            "- Verify the vacancy on the organisation's official website.\n"
            "- Ask a trusted person to review anything that feels rushed."
        )

    with st.expander("Short application email template"):
        st.code(
            "Subject: Application for [Job Title] — [Your Name]\n\n"
            "Dear [Hiring Manager or Selection Panel],\n\n"
            "I am applying for the [Job Title] position advertised on [source] on "
            "[date]. I have attached my CV and the requested documents.\n\n"
            "My background in [relevant education or experience] has prepared me to "
            "[one specific contribution linked to the role]. In particular, [one "
            "concrete example with a result].\n\n"
            "I would welcome the opportunity to discuss how I can support [organisation]. "
            "Thank you for your time and consideration.\n\n"
            "Kind regards,\n"
            "[Your Name]\n"
            "[Phone] · [Email]",
            language=None,
        )
