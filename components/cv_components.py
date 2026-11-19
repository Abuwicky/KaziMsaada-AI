"""Interactive CV builder with live preview and guided, user-friendly inputs."""

from __future__ import annotations

import hashlib
import html
import io
import uuid

import streamlit as st

from core.cv import (
    TEMPLATES,
    build_cv_content,
    build_cv_html,
    generate_cv_pdf,
    save_cv_bundle,
    validate_cv_contact_details,
)
from core.profiles import normalize_skills

from .ui import empty_state, page_header, set_flash


# A broad starter library. Users can always add a skill that is not listed.
SKILL_LIBRARY = {
    "Communication and teamwork": [
        "Verbal communication", "Written communication", "Active listening",
        "Presentation skills", "Teamwork", "Interpersonal skills",
        "Customer relations", "Negotiation", "Conflict resolution",
        "Report writing", "Public speaking", "Stakeholder communication",
    ],
    "Digital and computer skills": [
        "Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint",
        "Microsoft Outlook", "Google Workspace", "Email management",
        "Internet research", "Data entry", "Typing", "Computer literacy",
        "Digital collaboration tools", "Microsoft Access",
    ],
    "Technical and programming": [
        "Python", "Java", "JavaScript", "C++", "C#", "HTML", "CSS",
        "SQL", "Database management", "Web development", "Software testing",
        "Troubleshooting", "IT support", "Networking", "Cybersecurity",
        "Cloud computing", "Git and version control", "Systems administration",
    ],
    "Business and administration": [
        "Office administration", "Records management", "Filing",
        "Document management", "Business writing", "Procurement",
        "Inventory management", "Scheduling", "Operations support",
        "Customer service", "Business development", "Strategic planning",
    ],
    "Finance and accounting": [
        "Bookkeeping", "Financial reporting", "Budgeting",
        "Financial analysis", "Accounts payable", "Accounts receivable",
        "Bank reconciliation", "Payroll administration", "Auditing",
        "Tax preparation", "QuickBooks", "Sage accounting",
    ],
    "Marketing and sales": [
        "Digital marketing", "Social media management", "Content creation",
        "Search engine optimisation (SEO)", "Market research",
        "Brand management", "Sales", "Lead generation",
        "Customer relationship management (CRM)", "Advertising",
        "Copywriting", "Marketing analytics",
    ],
    "Project and operations management": [
        "Project management", "Project coordination", "Work planning",
        "Time management", "Risk management", "Quality assurance",
        "Process improvement", "Logistics", "Event coordination",
        "Monitoring and evaluation", "Resource management",
    ],
    "Leadership and people management": [
        "Leadership", "Team leadership", "People management",
        "Decision-making", "Delegation", "Coaching and mentoring",
        "Staff supervision", "Change management",
    ],
    "Research and analytical skills": [
        "Research", "Data analysis", "Critical thinking",
        "Problem-solving", "Data visualisation", "Statistical analysis",
        "Report analysis", "Attention to detail", "Information management",
        "Microsoft Power BI", "SPSS",
    ],
    "Personal effectiveness": [
        "Adaptability", "Self-motivation", "Initiative", "Creativity",
        "Reliability", "Organisation", "Learning agility",
        "Working independently", "Multitasking", "Resilience",
        "Professionalism", "Work ethic",
    ],
    "Education and specialist practice": [
        "Lesson planning", "Classroom management", "Training delivery",
        "Facilitation", "First aid", "Community engagement",
        "Clinical documentation", "Laboratory techniques",
        "Health and safety", "Agricultural practices",
    ],
}


EXPERIENCE_FIELDS = (
    "job_title",
    "organisation",
    "location",
    "start_date",
    "end_date",
    "responsibilities",
)


def _lines(
    value: str | list[str] | None,
    *,
    split_commas: bool = False,
) -> list[str]:
    """Split line, semicolon, or optionally comma separated input into items."""
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        text = value.replace(";", "\n")
        if split_commas:
            text = text.replace(",", "\n")
        raw_items = text.splitlines()
    return [
        str(item).strip(" -•\t")
        for item in raw_items
        if str(item).strip(" -•\t")
    ]


def _unique_skills(values: list[str]) -> list[str]:
    """Remove duplicate skills without changing their display spelling/order."""
    result = []
    seen = set()
    for value in values:
        cleaned = str(value).strip()
        marker = cleaned.casefold()
        if cleaned and marker not in seen:
            result.append(cleaned)
            seen.add(marker)
    return result


def _draft(profile_id: str) -> dict:
    drafts = st.session_state.setdefault("cv_drafts", {})
    return drafts.setdefault(profile_id, {})


def _prepare_widget_state(key: str, value) -> str:
    """Set a widget's initial session value before the widget is created."""

    if key not in st.session_state:
        st.session_state[key] = value
    return key


def _skill_values(value) -> list[str]:
    """Accept both current list data and older comma-separated skill data."""

    if isinstance(value, str):
        return normalize_skills(value)
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _remove_skill_from_draft(profile_id: str, draft: dict, skill: str) -> None:
    """Remove one skill before its category widget is instantiated this run."""

    marker = str(skill).strip().casefold()
    if not marker:
        return

    by_category = draft.get("skills_by_category")
    if isinstance(by_category, dict):
        for category, values in list(by_category.items()):
            by_category[category] = [
                item
                for item in _skill_values(values)
                if str(item).strip().casefold() != marker
            ]
            widget_key = f"cv_skill_category_{profile_id}_{category}"
            if widget_key in st.session_state:
                st.session_state[widget_key] = [
                    item
                    for item in st.session_state.get(widget_key, [])
                    if str(item).strip().casefold() != marker
                ]

    draft["custom_skills"] = [
        item
        for item in _skill_values(draft.get("custom_skills"))
        if str(item).strip().casefold() != marker
    ]
    if draft.get("skills") is not None:
        draft["skills"] = [
            item
            for item in _skill_values(draft.get("skills"))
            if str(item).strip().casefold() != marker
        ]


def _new_experience_record(record: dict | None = None) -> dict:
    """Give each experience card a stable identity across Streamlit reruns."""
    source = record or {}
    return {
        "_id": source.get("_id") or uuid.uuid4().hex,
        "job_title": source.get("job_title", ""),
        "organisation": source.get("organisation", ""),
        "location": source.get("location", ""),
        "start_date": source.get("start_date", ""),
        "end_date": source.get("end_date", ""),
        "currently_working": bool(source.get("currently_working", False)),
        "responsibilities": source.get("responsibilities", []),
    }


def _experience_widget_key(profile_id: str, record_id: str, field: str) -> str:
    return f"cv_exp_{profile_id}_{record_id}_{field}"


def _read_experience_widgets(profile_id: str, records: list[dict]) -> list[dict]:
    """Collect the latest values from the card widgets into CV-compatible records."""
    collected = []
    for record in records:
        record_id = record["_id"]

        def read(field: str, fallback=""):
            return st.session_state.get(
                _experience_widget_key(profile_id, record_id, field), fallback
            )

        currently_working = bool(
            read("currently_working", record.get("currently_working", False))
        )
        responsibilities = read(
            "responsibilities", record.get("responsibilities", [])
        )
        if isinstance(responsibilities, str):
            responsibilities = _lines(responsibilities)

        job_title = str(read("job_title", record.get("job_title", ""))).strip()
        organisation = str(
            read("organisation", record.get("organisation", ""))
        ).strip()
        location = str(read("location", record.get("location", ""))).strip()
        start_date = str(read("start_date", record.get("start_date", ""))).strip()
        # Keep any previously entered end date even while the role is current;
        # the CV output uses "Present", and unchecking the box restores the date.
        end_date = str(read("end_date", record.get("end_date", ""))).strip()

        # Keep even a blank card in the draft. A user may have just added it
        # and not entered details yet; dropping it would make the card disappear
        # on the next Streamlit rerun.
        collected.append({
            "_id": record_id,
            "job_title": job_title,
            "organisation": organisation,
            "location": location,
            "start_date": start_date,
            "end_date": end_date,
            "currently_working": currently_working,
            "responsibilities": responsibilities,
        })
    return collected


def _experience_for_cv(records: list[dict]) -> list[dict]:
    """Remove UI-only identifiers and keep the existing CV data contract."""
    output = []
    for record in records:
        if not (record.get("job_title") or record.get("organisation")):
            continue
        output.append({
            "job_title": record.get("job_title", ""),
            "organisation": record.get("organisation", ""),
            "location": record.get("location", ""),
            "start_date": record.get("start_date", ""),
            "end_date": (
                "Present" if record.get("currently_working")
                else record.get("end_date", "")
            ),
            "responsibilities": _lines(record.get("responsibilities", [])),
        })
    return output


def _render_experience_cards(profile_id: str, draft: dict) -> list[dict]:
    st.markdown(
        '<div class="km-panel-title">4. Work experience and practical experience</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Add employment, internships, industrial attachments, volunteering, "
        "freelance assignments or other relevant practical experience."
    )

    records = draft.setdefault("experience", [])
    if not isinstance(records, list):
        records = []
    records = [_new_experience_record(item) for item in records]
    draft["experience"] = records

    no_formal_key = f"cv_no_formal_experience_{profile_id}"
    if no_formal_key not in st.session_state:
        st.session_state[no_formal_key] = bool(
            draft.get("no_formal_experience", False)
        )

    no_formal = st.checkbox(
        "I do not have formal work experience yet",
        key=no_formal_key,
        help=(
            "You can still create a strong graduate CV using education, "
            "projects, attachments, volunteering and transferable skills."
        ),
    )
    draft["no_formal_experience"] = no_formal

    if no_formal:
        st.info(
            "That's completely fine. Your CV can focus on education, projects, "
            "practical training, volunteering and skills."
        )
        return []

    # Render each experience entry as a separate, clearly-labelled card.
    for index, record in enumerate(records):
        record_id = record["_id"]
        title_key = _experience_widget_key(profile_id, record_id, "job_title")
        if title_key not in st.session_state:
            st.session_state[title_key] = record.get("job_title", "")

        heading = record.get("job_title") or f"Experience {index + 1}"
        with st.container(border=True):
            top_left, top_right = st.columns([5, 1])
            with top_left:
                st.markdown(f"**Experience {index + 1}**")
                if record.get("organisation"):
                    st.caption(
                        f"{record['job_title'] or 'Role'} · {record['organisation']}"
                    )
            with top_right:
                remove_clicked = st.button(
                    "Remove",
                    key=f"cv_exp_remove_{profile_id}_{record_id}",
                    help="Remove this experience entry",
                    type="secondary",
                )
            if remove_clicked:
                latest = _read_experience_widgets(profile_id, records)
                draft["experience"] = [
                    item for item in latest if item["_id"] != record_id
                ]
                st.rerun()

            first_left, first_right = st.columns(2)
            with first_left:
                st.text_input(
                    "Job title or position",
                    key=title_key,
                    placeholder="e.g. ICT Support Intern",
                )
            with first_right:
                organisation_key = _experience_widget_key(
                    profile_id, record_id, "organisation"
                )
                if organisation_key not in st.session_state:
                    st.session_state[organisation_key] = record.get("organisation", "")
                st.text_input(
                    "Company or organisation",
                    key=organisation_key,
                    placeholder="e.g. ABC Technologies",
                )

            second_left, second_right = st.columns(2)
            with second_left:
                location_key = _experience_widget_key(profile_id, record_id, "location")
                if location_key not in st.session_state:
                    st.session_state[location_key] = record.get("location", "")
                st.text_input(
                    "Location",
                    key=location_key,
                    placeholder="e.g. Nairobi, Kenya",
                )
            with second_right:
                start_key = _experience_widget_key(profile_id, record_id, "start_date")
                if start_key not in st.session_state:
                    st.session_state[start_key] = record.get("start_date", "")
                st.text_input(
                    "Start date",
                    key=start_key,
                    placeholder="e.g. May 2024",
                )

            current_key = _experience_widget_key(
                profile_id, record_id, "currently_working"
            )
            if current_key not in st.session_state:
                st.session_state[current_key] = record.get("currently_working", False)
            currently_working = st.checkbox(
                "I currently work here",
                key=current_key,
            )

            end_key = _experience_widget_key(profile_id, record_id, "end_date")
            if end_key not in st.session_state:
                st.session_state[end_key] = record.get("end_date", "")
            end_left, end_right = st.columns(2)
            with end_left:
                st.text_input(
                    "End date",
                    key=end_key,
                    placeholder="Present" if currently_working else "e.g. August 2025",
                    disabled=currently_working,
                    help="This field is disabled when you select that you currently work here.",
                )
            if currently_working:
                st.caption("Your CV will show this role as Present.")

            responsibilities_key = _experience_widget_key(
                profile_id, record_id, "responsibilities"
            )
            if responsibilities_key not in st.session_state:
                existing = record.get("responsibilities", [])
                st.session_state[responsibilities_key] = (
                    "\n".join(existing) if isinstance(existing, list) else str(existing)
                )
            st.text_area(
                "Responsibilities and achievements",
                key=responsibilities_key,
                placeholder=(
                    "Describe what you did and, where possible, what you achieved. "
                    "Use a new line for each point."
                ),
                height=110,
            )

    if st.button(
        "+ Add another experience",
        key=f"cv_exp_add_{profile_id}",
        type="secondary",
        width="stretch",
    ):
        latest = _read_experience_widgets(profile_id, records)
        latest.append(_new_experience_record())
        draft["experience"] = latest
        st.rerun()

    # Capture current values on every run so edits survive other widget changes.
    latest_records = _read_experience_widgets(profile_id, records)
    draft["experience"] = latest_records
    return _experience_for_cv(latest_records)


def _initial_skill_selection(profile: dict, draft: dict) -> tuple[dict, list[str]]:
    """Convert older comma-separated skill drafts into the new grouped format."""
    by_category = draft.get("skills_by_category")
    custom = draft.get("custom_skills")

    if by_category is not None and isinstance(by_category, dict):
        clean_mapping = {
            category: _unique_skills(_skill_values(by_category.get(category, [])))
            for category in SKILL_LIBRARY
        }
        return clean_mapping, _unique_skills(_skill_values(custom))

    legacy = draft.get("skills")
    if legacy:
        existing = normalize_skills(legacy)
    else:
        existing = normalize_skills(profile.get("skills", []))

    lookup = {
        skill.casefold(): (category, skill)
        for category, skills in SKILL_LIBRARY.items()
        for skill in skills
    }
    mapping = {category: [] for category in SKILL_LIBRARY}
    custom_skills = []
    for skill in existing:
        match = lookup.get(str(skill).casefold())
        if match:
            category, canonical_skill = match
            mapping[category].append(canonical_skill)
        else:
            custom_skills.append(skill)
    return mapping, _unique_skills(custom_skills)


def _render_skills_picker(profile_id: str, profile: dict, draft: dict) -> list[str]:
    pending_remove_key = f"cv_skill_remove_pending_{profile_id}"
    pending_skill = st.session_state.pop(pending_remove_key, None)
    if pending_skill:
        _remove_skill_from_draft(profile_id, draft, pending_skill)

    st.markdown(
        '<div class="km-panel-title">3. Education and skills</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="km-field-note">Primary education from your profile: '
        f'<strong>{html.escape(str(profile.get("education", "Not provided")))}</strong></div>',
        unsafe_allow_html=True,
    )

    education_key = _prepare_widget_state(
        f"cv_education_{profile_id}", draft.get("education", "")
    )
    education_text = st.text_area(
        "Additional education or training",
        placeholder="One per line, e.g.\nKenya Certificate of Secondary Education — 2021",
        height=90,
        key=education_key,
    )

    st.markdown("**Choose the skills you want to highlight in this CV**")
    st.caption(
        "Select as many as are relevant. Search for a skill, then open a category "
        "to choose from its list. You can also add your own."
    )

    mapping, custom_skills = _initial_skill_selection(profile, draft)
    search_key = f"cv_skill_search_{profile_id}"
    if search_key not in st.session_state:
        st.session_state[search_key] = ""
    search = st.text_input(
        "Search the skills library",
        key=search_key,
        placeholder="e.g. Excel, communication, accounting, Python",
    ).strip().casefold()

    selected_by_category = {}
    for category, all_options in SKILL_LIBRARY.items():
        matching = [
            skill for skill in all_options
            if not search or search in skill.casefold()
        ]
        widget_key = f"cv_skill_category_{profile_id}_{category}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = mapping.get(category, [])

        # Keep previously selected values valid even when a search is active.
        canonical_options = {skill.casefold(): skill for skill in all_options}
        current_selected = st.session_state.get(widget_key, [])
        canonical_selected = [
            canonical_options.get(str(skill).casefold(), skill)
            for skill in current_selected
        ]
        if canonical_selected != current_selected:
            st.session_state[widget_key] = canonical_selected
            current_selected = canonical_selected

        options = _unique_skills(
            matching + [
                skill for skill in current_selected if skill not in matching
            ]
        )
        if search and not matching and not current_selected:
            continue

        with st.expander(
            f"{category} ({len(current_selected)} selected)",
            expanded=bool(search and matching),
        ):
            selected_by_category[category] = st.multiselect(
                f"Select {category.lower()}",
                options=options,
                key=widget_key,
                label_visibility="collapsed",
                placeholder="Choose one or more skills",
            )

    # Categories hidden by search retain their previous choices.
    for category in SKILL_LIBRARY:
        if category not in selected_by_category:
            widget_key = f"cv_skill_category_{profile_id}_{category}"
            selected_by_category[category] = st.session_state.get(
                widget_key, mapping.get(category, [])
            )

    custom_key = f"cv_custom_skill_{profile_id}"
    custom_clear_key = f"cv_custom_skill_clear_{profile_id}"
    if st.session_state.pop(custom_clear_key, False):
        st.session_state[custom_key] = ""
    elif custom_key not in st.session_state:
        st.session_state[custom_key] = ""
    custom_col, add_col = st.columns([4, 1])
    with custom_col:
        st.text_input(
            "Add a skill not listed",
            key=custom_key,
            placeholder="e.g. AutoCAD, M-Pesa agent operations",
        )
    with add_col:
        st.markdown("<div style='height: 1.85rem'></div>", unsafe_allow_html=True)
        add_custom = st.button(
            "Add skill",
            key=f"cv_custom_skill_add_{profile_id}",
            width="stretch",
        )

    if add_custom:
        new_skill = st.session_state.get(custom_key, "").strip()
        known = {
            skill.casefold()
            for skills in SKILL_LIBRARY.values()
            for skill in skills
        }
        selected = [
            skill
            for values in selected_by_category.values()
            for skill in values
        ]
        already_selected = {
            skill.casefold() for skill in selected + custom_skills
        }
        if not new_skill:
            st.warning("Enter a skill before clicking Add skill.")
        elif new_skill.casefold() in known:
            st.info("That skill is already available in the skills library.")
        elif new_skill.casefold() in already_selected:
            st.info("That skill has already been selected.")
        else:
            custom_skills.append(new_skill)
            draft["custom_skills"] = _unique_skills(custom_skills)
            draft["skills_by_category"] = selected_by_category
            st.session_state[custom_clear_key] = True
            st.rerun()

    selected_skills = _unique_skills(
        [
            skill
            for values in selected_by_category.values()
            for skill in values
        ] + custom_skills
    )
    draft["skills_by_category"] = {
        category: _unique_skills(values)
        for category, values in selected_by_category.items()
    }
    draft["custom_skills"] = _unique_skills(custom_skills)
    draft["education"] = education_text
    draft["skills"] = selected_skills

    if selected_skills:
        st.markdown("**Selected skills**")
        st.write(" · ".join(selected_skills))
        st.caption(
            f"{len(selected_skills)} skill(s) selected. To remove a library skill, "
            "unselect it in its category. Custom skills can be removed below."
        )
    else:
        st.info("No skills selected yet. Choose skills that genuinely reflect your abilities.")

    if custom_skills:
        st.markdown("**Your custom skills**")
        for skill in custom_skills:
            skill_col, remove_col = st.columns([6, 1])
            with skill_col:
                st.markdown(f"- {html.escape(skill)}")
            with remove_col:
                digest = hashlib.sha1(
                    skill.casefold().encode("utf-8")
                ).hexdigest()[:10]
                if st.button(
                    "Remove",
                    key=f"cv_custom_remove_{profile_id}_{digest}",
                    help=f"Remove {skill} from this CV",
                ):
                    st.session_state[pending_remove_key] = skill
                    st.rerun()

    return selected_skills


def _render_preview(profile: dict, cv_data: dict, template: str) -> None:
    st.markdown(
        f"""
        <div class="km-preview-head">
          <div>
            <strong>Live preview</strong>
            <span>{html.escape(TEMPLATES[template]["name"])}</span>
          </div>
          <span class="km-badge km-badge-available">Updates as you edit</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.iframe(
        build_cv_html(profile, cv_data, template),
        width="stretch",
        height=940,
        alt="Live CV preview",
    )
    st.caption(
        "The preview and the downloadable PDF are generated from the same CV data."
    )


def _pdf_bytes(profile: dict, cv_data: dict, template: str) -> bytes:
    buffer = io.BytesIO()
    generate_cv_pdf(build_cv_content(profile, cv_data), buffer, template=template)
    return buffer.getvalue()


def render_cv_builder(profiles: list[dict]) -> None:
    page_header(
        "CV builder",
        "Build a CV that reflects your potential",
        "Choose a saved profile, shape each section, and watch a professional "
        "preview update as you type. Download the finished PDF when you are ready.",
    )

    if not profiles:
        empty_state(
            "Your CV starts with a profile",
            "Create a career profile first. We use your education, location and "
            "skills as the foundation, then you add the details for this application.",
            "Create a career profile",
            "My Profile",
            "create",
            "cv_empty_profile",
        )
        return

    active_id = st.session_state.get("active_profile_id")
    lookup = {profile["profile_id"]: profile for profile in profiles}
    profile = lookup.get(active_id) or profiles[0]
    if st.session_state.get("active_profile_id") != profile["profile_id"]:
        st.session_state["active_profile_id"] = profile["profile_id"]

    draft = _draft(profile["profile_id"])
    pid = profile["profile_id"]

    st.markdown(
        f"""
        <div class="km-cv-profile">
          <div class="km-avatar">{html.escape(str(profile.get("name", "K"))[:1].upper())}</div>
          <div>
            <span>Building from profile</span>
            <strong>{html.escape(str(profile.get("name", "Unnamed profile")))}</strong>
            <em>{html.escape(str(profile.get("career_interest", "Career profile")))} · {html.escape(str(profile.get("location", "Location not set")))}</em>
          </div>
          <div class="km-cv-profile-note">Change the working profile in the sidebar to switch CVs.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="km-cv-split-marker" aria-hidden="true">.</div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.08, 1], gap="large")

    with left:
        st.markdown(
            '<div class="km-panel-title">1. Choose a template</div>',
            unsafe_allow_html=True,
        )
        template_keys = list(TEMPLATES)
        stored_template = draft.get(
            "template", st.session_state.get("cv_template", "classic")
        )
        if stored_template not in TEMPLATES:
            stored_template = "classic"

        template = st.selectbox(
            "CV template",
            template_keys,
            index=template_keys.index(stored_template),
            format_func=lambda key: TEMPLATES[key]["name"],
            key=f"cv_template_picker_{pid}",
            label_visibility="collapsed",
        )
        meta = TEMPLATES[template]
        st.markdown(
            f"""
            <div class="km-template-row">
              <span class="km-template-swatch" style="background:{meta['accent']}"></span>
              <div>
                <strong>{html.escape(meta['name'])}</strong>
                <span>{html.escape(meta['description'])}</span>
                <span>Best for: {html.escape(meta.get('best_for', 'General use'))} ·
                ATS: {html.escape(meta.get('ats', 'Best'))}</span>
              </div>
              <code>{html.escape(template)}</code>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.session_state["cv_template"] = template

        st.markdown(
            '<div class="km-panel-title">2. Target and contact details</div>',
            unsafe_allow_html=True,
        )
        target_key = _prepare_widget_state(
            f"cv_target_{pid}", draft.get("target_role", "")
        )
        target_role = st.text_input(
            "Target job position *",
            placeholder="e.g. ICT Support Officer",
            key=target_key,
        )

        contact_left, contact_right = st.columns(2)
        with contact_left:
            phone_key = _prepare_widget_state(
                f"cv_phone_{pid}", draft.get("phone", "")
            )
            phone = st.text_input(
                "Phone number *",
                placeholder="e.g. 0712 345 678",
                key=phone_key,
            )
        with contact_right:
            email_key = _prepare_widget_state(
                f"cv_email_{pid}", draft.get("email", "")
            )
            email = st.text_input(
                "Email address *",
                placeholder="you@example.com",
                key=email_key,
            )

        summary_key = _prepare_widget_state(
            f"cv_summary_{pid}", draft.get("summary", "")
        )
        summary = st.text_area(
            "Professional summary",
            placeholder=(
                "Two or three lines about who you are, your strongest skills, and "
                "the value you bring to this role."
            ),
            height=110,
            key=summary_key,
        )

        skills = _render_skills_picker(pid, profile, draft)
        experience = _render_experience_cards(pid, draft)

        with st.expander(
            "Projects, volunteering, certifications, languages and referees",
            expanded=False,
        ):
            projects_key = _prepare_widget_state(
                f"cv_projects_{pid}", draft.get("projects", "")
            )
            projects_text = st.text_area(
                "Projects and practical experience",
                placeholder="One per line. Include the result or what you learned.",
                height=90,
                key=projects_key,
            )
            volunteering_key = _prepare_widget_state(
                f"cv_volunteering_{pid}", draft.get("volunteering", "")
            )
            volunteering_text = st.text_area(
                "Volunteering",
                placeholder="One per line.",
                height=80,
                key=volunteering_key,
            )
            certifications_key = _prepare_widget_state(
                f"cv_certifications_{pid}", draft.get("certifications", "")
            )
            certifications_text = st.text_area(
                "Certifications and training",
                placeholder="One per line.",
                height=80,
                key=certifications_key,
            )
            languages_key = _prepare_widget_state(
                f"cv_languages_{pid}", draft.get("languages", "")
            )
            languages_text = st.text_input(
                "Languages (comma-separated)",
                placeholder="e.g. English, Kiswahili",
                key=languages_key,
            )
            referees_key = _prepare_widget_state(
                f"cv_referees_{pid}", draft.get("referees", "")
            )
            referees_text = st.text_area(
                "Referees",
                placeholder=(
                    "One per line, e.g. Jane Doe — Supervisor, ABC Ltd — 0712 000 000\n"
                    "Or: Available upon request"
                ),
                height=90,
                key=referees_key,
            )

        cv_data = {
            "phone": phone.strip(),
            "email": email.strip(),
            "target_role": target_role.strip(),
            "summary": summary.strip(),
            "education": _lines(draft.get("education", "")),
            "experience": experience,
            "projects": _lines(projects_text),
            "volunteering": _lines(volunteering_text),
            "skills": normalize_skills(skills),
            "certifications": _lines(certifications_text),
            "languages": _lines(languages_text, split_commas=True),
            "referees": _lines(referees_text),
        }

        # Preserve the draft for navigation and reruns. CV data is only persisted
        # to the workspace when the user explicitly saves the CV.
        draft.update({
            "template": template,
            "target_role": cv_data["target_role"],
            "phone": cv_data["phone"],
            "email": cv_data["email"],
            "summary": cv_data["summary"],
            "experience": draft.get("experience", []),
            "projects": projects_text,
            "volunteering": volunteering_text,
            "certifications": certifications_text,
            "languages": languages_text,
            "referees": referees_text,
            "skills": skills,
        })

        contact_errors = validate_cv_contact_details(
            cv_data["target_role"], cv_data["email"], cv_data["phone"]
        )
        ready = not contact_errors

        if contact_errors:
            st.warning(
                "Complete these required details to enable PDF download and saving:\n\n"
                + "\n".join(f"- {message}" for message in contact_errors.values())
                + "\n\nThe preview remains available while you finish these details."
            )

        pdf_bytes = None
        pdf_error = None
        if ready:
            try:
                pdf_bytes = _pdf_bytes(profile, cv_data, template)
            except Exception as error:  # ReportLab failures should not crash the page.
                pdf_error = error

        safe_name = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in str(profile.get("name", "CV")).strip()
        ) or "CV"

        download_col, save_col = st.columns(2)
        with download_col:
            st.download_button(
                "Download PDF",
                data=pdf_bytes or b"",
                file_name=f"CV_{safe_name}.pdf",
                mime="application/pdf",
                width="stretch",
                disabled=not ready or not pdf_bytes,
                key=f"cv_download_{pid}",
            )
        with save_col:
            save_clicked = st.button(
                "Save CV to workspace",
                width="stretch",
                disabled=not ready or not pdf_bytes,
                key=f"cv_save_{pid}",
            )

        if pdf_error is not None:
            st.error(
                "The PDF could not be generated. Your information is still here. "
                "Please try again."
            )
            with st.expander("Technical details"):
                st.code(f"{type(pdf_error).__name__}: {pdf_error}", language=None)

        if save_clicked:
            try:
                saved = save_cv_bundle(profile, cv_data, template)
            except OSError as error:
                st.error(
                    "The CV files could not be saved to the local CV folder. "
                    "You can still download the PDF."
                )
                with st.expander("Technical details"):
                    st.code(f"{type(error).__name__}: {error}", language=None)
            except Exception as error:
                st.error("The CV could not be saved. Please try again.")
                with st.expander("Technical details"):
                    st.code(f"{type(error).__name__}: {error}", language=None)
            else:
                set_flash(
                    f"CV saved as {saved['pdf_path'].name} using the "
                    f"{saved['template_name']} template."
                )
                st.rerun()

    with right:
        _render_preview(profile, cv_data, template)
