"""Guided career-support pages: interview, skills, guidance, and job search."""

from __future__ import annotations

import html
import sqlite3

import streamlit as st

from core.interview import CORE_INTERVIEW_QUESTIONS as INTERVIEW_QUESTIONS
from core.interview import CORE_QUESTION_IDS as INTERVIEW_QUESTION_IDS
from core.interview import CORE_QUESTION_LOOKUP as INTERVIEW_QUESTION_LOOKUP
from core.profiles import update_profile_record

from .interview_centre import render_interview_centre
from .ui import go_to, icon, page_header, set_flash, skill_chips, sub_section

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


def interview_checklist_key(item_id: str) -> str:
    return f"interview_check::{item_id}"


def _restore_widget_state(widget_key: str, store_key: str, default) -> None:
    """Restore a widget value without replacing an existing live widget value."""

    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state.get(store_key, default)
    if store_key not in st.session_state:
        st.session_state[store_key] = st.session_state[widget_key]


def _persist_widget_state(store_key: str, widget_key: str, default) -> None:
    st.session_state[store_key] = st.session_state.get(widget_key, default)


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
            "or score. Practice answers stay in this Streamlit session only, are "
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
        "Name your strengths. Choose what to build next.",
        "A practical self-assessment to help you describe your skills clearly and "
        "focus your development. It is not a formal qualification.",
    )

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
