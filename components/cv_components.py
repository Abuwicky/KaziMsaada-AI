"""Interactive CV builder with live preview and guided, user-friendly inputs."""

from __future__ import annotations

import hashlib
import html
import io
import json
import sqlite3
import uuid
from datetime import datetime

import streamlit as st

from core.cv import (
    TEMPLATES,
    build_cv_content,
    build_cv_html,
    cv_file_stem,
    generate_cv_pdf,
    save_cv_bundle,
    validate_cv_contact_details,
)
from core.cv_drafts import (
    CvDraftError,
    load_cv_draft,
    load_cv_draft_updated_at,
    save_cv_draft,
)
from core.cv_export import generate_cv_docx
from core.cv_insights import (
    analyse_job_ad,
    bullet_feedback,
    cover_letter,
    cv_strength,
    interview_questions,
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
    if profile_id not in drafts:
        try:
            drafts[profile_id] = load_cv_draft(profile_id)
        except (CvDraftError, sqlite3.Error):
            drafts[profile_id] = {}
        try:
            saved_at = load_cv_draft_updated_at(profile_id)
        except (CvDraftError, sqlite3.Error):
            saved_at = None
        st.session_state.setdefault("cv_draft_saved_at", {})[profile_id] = saved_at
    return drafts.setdefault(profile_id, {})


def _draft_signature(draft: dict) -> str:
    payload = {
        key: value
        for key, value in draft.items()
        if not str(key).startswith("_")
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _autosave_draft(profile_id: str, draft: dict) -> None:
    """Persist a draft only when its content has changed since the last save."""

    signature = _draft_signature(draft)
    signatures = st.session_state.setdefault("cv_draft_signatures", {})
    if signatures.get(profile_id) == signature:
        return

    try:
        save_cv_draft(profile_id, draft)
    except (CvDraftError, sqlite3.Error) as error:
        st.session_state.setdefault("cv_draft_autosave_errors", {})[profile_id] = str(error)
        return

    signatures[profile_id] = signature
    st.session_state.setdefault("cv_draft_saved_at", {})[profile_id] = (
        datetime.now().astimezone().isoformat(timespec="seconds")
    )
    st.session_state.setdefault("cv_draft_autosave_errors", {}).pop(profile_id, None)


def _saved_at_label(value: str | None) -> str:
    if not value:
        return "Autosave is on. Changes are saved to your workspace."
    try:
        saved = datetime.fromisoformat(str(value))
    except ValueError:
        return "Autosave is on. Changes are saved to your workspace."
    return f"Last autosaved {saved.strftime('%d %b %Y, %H:%M')}"


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
        "Add employment, internships, industrial attachments, NYS service, "
        "volunteering, freelance assignments or other relevant practical experience."
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
        placeholder="One per line, e.g.\nKenya Certificate of Secondary Education (KCSE) — 2021\nNITA craft certificate — 2023",
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


def _safe_accent(value, fallback: str) -> str:
    text = str(value or "").strip()
    if (
        len(text) == 7
        and text.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in text[1:])
    ):
        return text
    return fallback


def _render_template_gallery(profile_id: str, draft: dict) -> tuple[str, str]:
    """Show a visual template gallery and return the chosen template and accent."""

    stored = (
        draft.get("template")
        or st.session_state.get(f"cv_template_{profile_id}")
        or st.session_state.get("cv_template")
        or "classic"
    )
    if stored not in TEMPLATES:
        stored = "classic"

    st.caption(
        "Choose a starting design. You can change it at any time without losing "
        "the details you have entered."
    )
    templates = list(TEMPLATES.items())
    for start in range(0, len(templates), 3):
        row = st.columns(3)
        for column, (key, meta) in zip(row, templates[start : start + 3]):
            with column:
                selected = key == stored
                st.markdown(
                    f"""
                    <div class="km-template-card{' km-template-card-selected' if selected else ''}"
                         style="--template-accent:{meta['accent']}">
                      <div class="km-template-thumb">
                        <span class="km-thumb-bar"></span>
                        <span class="km-thumb-line km-thumb-line-wide"></span>
                        <span class="km-thumb-line"></span>
                        <span class="km-thumb-line km-thumb-line-short"></span>
                        <span class="km-thumb-rule"></span>
                        <span class="km-thumb-line km-thumb-line-wide"></span>
                        <span class="km-thumb-line"></span>
                      </div>
                      <div class="km-template-card-body">
                        <strong>{html.escape(meta['name'])}</strong>
                        <span>{html.escape(meta['description'])}</span>
                        <em>Best for: {html.escape(meta.get('best_for', 'General use'))}</em>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Selected" if selected else "Use this design",
                    key=f"cv_template_choice_{profile_id}_{key}",
                    disabled=selected,
                    width="stretch",
                ):
                    draft["template"] = key
                    draft["accent"] = meta["accent"]
                    st.session_state[f"cv_template_{profile_id}"] = key
                    st.session_state[f"cv_accent_{profile_id}"] = meta["accent"]
                    st.rerun()

    template = stored
    accent_key = f"cv_accent_{profile_id}"
    if accent_key not in st.session_state:
        st.session_state[accent_key] = _safe_accent(
            draft.get("accent"),
            TEMPLATES[template]["accent"],
        )
    accent_col, reset_col = st.columns([3, 1])
    with accent_col:
        accent = st.color_picker(
            "Accent colour",
            key=accent_key,
            help="Use your own colour while keeping the selected layout and structure.",
        )
    with reset_col:
        st.markdown("<div style='height: 1.65rem'></div>", unsafe_allow_html=True)
        if st.button(
            "Reset",
            key=f"cv_accent_reset_{profile_id}",
            width="stretch",
            help="Reset to the template's original colour",
        ):
            st.session_state[accent_key] = TEMPLATES[template]["accent"]
            draft["accent"] = TEMPLATES[template]["accent"]
            st.rerun()

    draft["template"] = template
    draft["accent"] = accent
    st.session_state[f"cv_template_{profile_id}"] = template
    return template, accent


def _render_preview(
    profile: dict,
    cv_data: dict,
    template: str,
    accent: str | None = None,
) -> None:
    st.markdown(
        f"""
        <div class="km-preview-head">
          <div>
            <strong>CV preview</strong>
            <span>{html.escape(TEMPLATES[template]["name"])}</span>
          </div>
          <span class="km-badge km-badge-available">Generated from your entries</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.iframe(
        build_cv_html(profile, cv_data, template, accent=accent),
        width="stretch",
        height=940,
        alt="CV preview",
    )
    st.caption(
        "This preview and the downloadable PDF use the same CV data and the "
        "same template settings."
    )


def _pdf_bytes(
    profile: dict,
    cv_data: dict,
    template: str,
    accent: str | None = None,
) -> bytes:
    buffer = io.BytesIO()
    generate_cv_pdf(
        build_cv_content(profile, cv_data),
        buffer,
        template=template,
        accent=accent,
    )
    return buffer.getvalue()


def _known_skills() -> list[str]:
    return [skill for skills in SKILL_LIBRARY.values() for skill in skills]


def _render_strength(profile: dict, cv_data: dict) -> None:
    result = cv_strength(profile, cv_data)
    with st.container(border=True):
        st.markdown("**CV strength score**")
        st.progress(result["score"] / 100)
        st.caption(f"{result['score']}/100 · {result['band']}")
        if result["fixes"]:
            st.markdown("**Next best fixes**")
            for item in result["fixes"]:
                st.markdown(f"- **{item['label']}:** {item['fix']}")
        else:
            st.caption("All checks are complete. Review the wording before sending.")
        with st.expander("See all checks"):
            for item in result["checks"]:
                marker = "✓" if item["earned"] >= item["points"] else "•"
                st.caption(
                    f"{marker} {item['label']} ({item['earned']}/{item['points']})"
                )
        st.caption(result["note"])


def _render_job_match(profile: dict, cv_data: dict, draft: dict, profile_id: str) -> None:
    st.markdown(
        '<div class="km-panel-title">Job-ad match</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Paste a job advert to see which skills and keywords it mentions. This "
        "never changes your CV until you confirm a skill yourself."
    )
    job_ad_key = _prepare_widget_state(
        f"cv_job_ad_{profile_id}", draft.get("job_ad", "")
    )
    job_ad = st.text_area(
        "Job advert text",
        key=job_ad_key,
        height=150,
        placeholder="Paste the duties and requirements from the advert here.",
    )
    draft["job_ad"] = job_ad
    _autosave_draft(profile_id, draft)

    result = analyse_job_ad(
        job_ad,
        profile,
        cv_data,
        known_skills=_known_skills(),
    )
    if not result.get("available"):
        st.info("Paste a job advert to start the comparison.")
        return

    st.progress(result["score"] / 100)
    st.caption(f"{result['score']}% wording coverage · {result['label']}")
    st.caption(result["note"])

    if result["matched"]:
        st.markdown("**Already reflected in this CV**")
        st.write(" · ".join(result["matched"]))

    if result["missing"]:
        st.markdown("**Mentioned in the advert but not in this CV**")
        st.write(" · ".join(result["missing"]))
        confirm_key = f"cv_confirm_skills_{profile_id}"
        selected = st.multiselect(
            "Select only the skills you can genuinely confirm",
            options=result["missing"],
            key=confirm_key,
            placeholder="Choose skills to add",
        )
        if st.button(
            "Add confirmed skills to this CV",
            key=f"cv_add_confirmed_{profile_id}",
            disabled=not selected,
            width="stretch",
        ):
            current = _unique_skills(
                _skill_values(draft.get("skills"))
                + _skill_values(draft.get("custom_skills"))
                + list(selected)
            )
            draft["skills"] = current
            draft["custom_skills"] = _unique_skills(
                _skill_values(draft.get("custom_skills")) + list(selected)
            )
            st.session_state.pop(confirm_key, None)
            _autosave_draft(profile_id, draft)
            st.rerun()
        st.caption(
            "Do not add a skill you cannot explain in an interview. You can remove "
            "confirmed custom skills in the skills section."
        )


def _render_bullet_coach(experience: list[dict]) -> None:
    bullets = [
        item
        for entry in experience
        for item in entry.get("responsibilities", [])
        if str(item).strip()
    ]
    if not bullets:
        return
    with st.expander("Improve your experience bullets", expanded=False):
        st.caption(
            "These are writing suggestions based only on your own words. Add a "
            "number or result only when you know it is accurate."
        )
        for bullet in bullets[:8]:
            feedback = bullet_feedback(bullet)
            st.markdown(f"**Before:** {html.escape(feedback['original'])}")
            if feedback["issues"]:
                for issue in feedback["issues"]:
                    st.caption(f"- {issue}")
                if feedback["suggestion"] != feedback["original"]:
                    st.markdown(
                        f"**Draft opener to review:** "
                        f"{html.escape(feedback['suggestion'])}"
                    )
            else:
                st.caption("This bullet already has a clear action and detail.")


def _render_cover_letter(profile: dict, cv_data: dict, draft: dict, profile_id: str) -> None:
    with st.expander("Cover letter draft", expanded=False):
        st.caption(
            "This draft uses only the facts already in your CV. Read it carefully, "
            "add the employer's name and any specific details, then edit it in your "
            "own voice before sending."
        )
        key = f"cv_cover_letter_text_{profile_id}"
        if st.button(
            "Generate or refresh cover letter",
            key=f"cv_cover_generate_{profile_id}",
            width="stretch",
        ):
            st.session_state[key] = cover_letter(profile, cv_data, draft.get("job_ad", ""))
        if key not in st.session_state:
            st.session_state[key] = cover_letter(profile, cv_data, draft.get("job_ad", ""))
        text = st.text_area(
            "Editable cover letter",
            key=key,
            height=330,
        )
        st.download_button(
            "Download cover letter",
            data=text.encode("utf-8"),
            file_name=f"{cv_file_stem(profile, cv_data).replace('_CV', '_Cover_Letter')}.txt",
            mime="text/plain",
            key=f"cv_cover_download_{profile_id}",
        )


def _render_interview_questions(profile: dict, cv_data: dict) -> None:
    questions = interview_questions(profile, cv_data)
    with st.expander("Interview questions based on this CV", expanded=False):
        st.caption(
            "These are practice prompts generated from your CV fields, not "
            "questions supplied by an employer."
        )
        for number, question in enumerate(questions, start=1):
            st.markdown(f"{number}. {question}")
        st.caption(
            "Open Interview Practice in the sidebar to record an answer and get "
            "structured feedback."
        )


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
    st.markdown(
        '<div class="km-panel-title">1. Choose a template</div>',
        unsafe_allow_html=True,
    )
    template, accent = _render_template_gallery(pid, draft)
    mobile_tabs = st.toggle(
        "Mobile Edit/Preview tabs",
        value=False,
        key=f"cv_mobile_tabs_{pid}",
        help=(
            "Use separate Edit and Preview tabs on a narrow screen instead of "
            "scrolling past the full preview."
        ),
    )
    if mobile_tabs:
        left, right = st.tabs(["Edit CV", "Preview"])
    else:
        left, right = st.columns([1.08, 1], gap="large")

    with left:
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
        target_error_slot = st.empty()

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
            phone_error_slot = st.empty()
        with contact_right:
            email_key = _prepare_widget_state(
                f"cv_email_{pid}", draft.get("email", "")
            )
            email = st.text_input(
                "Email address *",
                placeholder="you@example.com",
                key=email_key,
            )
            email_error_slot = st.empty()

        contact_errors = validate_cv_contact_details(target_role, email, phone)
        if str(target_role or "").strip() and "target_role" in contact_errors:
            target_error_slot.caption(f":red[{contact_errors['target_role']}]")
        if str(phone or "").strip() and "phone" in contact_errors:
            phone_error_slot.caption(f":red[{contact_errors['phone']}]")
        if str(email or "").strip() and "email" in contact_errors:
            email_error_slot.caption(f":red[{contact_errors['email']}]")

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
        with st.expander("Kenyan application notes", expanded=False):
            st.markdown(
                "- Use qualification names as they appear on your certificates "
                "(for example KCSE, KNEC, NITA, TVET or a university degree).\n"
                "- Treat attachments, internships and NYS service as practical "
                "experience. Name the organisation and the dates.\n"
                "- List Kiswahili only if you can use it professionally.\n"
                "- Ask referees for permission before sharing their details."
            )
        experience = _render_experience_cards(pid, draft)
        _render_bullet_coach(experience)

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

        # Preserve the draft for navigation and reruns. The draft is autosaved
        # to the signed-in owner's workspace; the final PDF is only written when
        # the user explicitly saves the CV.
        draft.update({
            "template": template,
            "accent": accent,
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
        _autosave_draft(pid, draft)
        saved_at = st.session_state.get("cv_draft_saved_at", {}).get(pid)
        autosave_error = st.session_state.get("cv_draft_autosave_errors", {}).get(pid)
        if autosave_error:
            st.caption(
                ":red[Autosave could not run. Your details remain on this page, "
                "but download or save the CV before closing.]"
            )
        else:
            st.caption(_saved_at_label(saved_at))

        ready = not contact_errors

        if contact_errors:
            st.warning(
                "Complete these required details to enable PDF download and saving:\n\n"
                + "\n".join(f"- {message}" for message in contact_errors.values())
                + "\n\nThe preview remains available while you finish these details."
            )

        pdf_bytes = None
        pdf_error = None
        docx_bytes = None
        docx_error = None
        if ready:
            try:
                pdf_bytes = _pdf_bytes(profile, cv_data, template, accent)
            except Exception as error:  # ReportLab failures should not crash the page.
                pdf_error = error
            try:
                docx_bytes = generate_cv_docx(profile, cv_data, accent)
            except Exception as error:
                docx_error = error

        download_name = f"{cv_file_stem(profile, cv_data)}.pdf"

        download_col, docx_col, save_col = st.columns(3)
        with download_col:
            st.download_button(
                "Download PDF",
                data=pdf_bytes or b"",
                file_name=download_name,
                mime="application/pdf",
                width="stretch",
                disabled=not ready or not pdf_bytes,
                key=f"cv_download_{pid}",
            )
        with docx_col:
            st.download_button(
                "Download DOCX",
                data=docx_bytes or b"",
                file_name=download_name.replace(".pdf", ".docx"),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                width="stretch",
                disabled=not ready or not docx_bytes,
                key=f"cv_download_docx_{pid}",
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
        if docx_error is not None:
            st.caption(":red[The editable DOCX could not be generated for this CV.]")

        if save_clicked:
            try:
                saved = save_cv_bundle(
                    profile,
                    cv_data,
                    template,
                    accent=accent,
                )
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
        _render_strength(profile, cv_data)
        _render_preview(profile, cv_data, template, accent=accent)
        _render_job_match(profile, cv_data, draft, pid)
        _render_cover_letter(profile, cv_data, draft, pid)
        _render_interview_questions(profile, cv_data)
