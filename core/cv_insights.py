"""Deterministic CV coaching tools.

These helpers never add unconfirmed skills, never invent experience, and never
send personal data to an AI provider. They explain what is present in the CV and
what the applicant may want to review.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .cv import build_cv_document, validate_cv_contact_details

_STOPWORDS = {
    "about", "above", "after", "again", "against", "along", "also", "among",
    "and", "another", "applicant", "application", "apply", "are", "around",
    "because", "been", "before", "being", "below", "between", "both", "but",
    "can", "candidate", "candidates", "company", "could", "daily", "describe",
    "does", "doing", "during", "each", "either", "ensure", "every", "from",
    "have", "including", "into", "its", "job", "join", "more", "most", "must",
    "need", "other", "our", "over", "position", "preferred", "provide",
    "required", "requirements", "role", "should", "some", "such", "support",
    "than", "that", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "under", "using", "very", "what", "when", "where",
    "which", "while", "will", "with", "within", "work", "working", "would",
    "years", "your",
}

_ACTION_VERBS = {
    "achieved", "adapted", "administered", "advised", "analysed", "analyzed",
    "assisted", "built", "coached", "collaborated", "communicated", "completed",
    "coordinated", "created", "delivered", "designed", "developed", "documented",
    "enabled", "enhanced", "established", "facilitated", "handled", "identified",
    "implemented", "improved", "increased", "initiated", "inspected", "installed",
    "led", "maintained", "managed", "mentored", "monitored", "organised",
    "organized", "planned", "prepared", "processed", "provided", "reduced",
    "repaired", "reported", "resolved", "reviewed", "scheduled", "served",
    "supported", "trained", "troubleshot", "verified",
}

_WEAK_OPENERS = (
    ("responsible for ", ""),
    ("duties included ", ""),
    ("duties include ", ""),
    ("tasked with ", ""),
    ("helped with ", "Supported "),
    ("assisted with ", "Supported "),
    ("worked on ", "Contributed to "),
    ("participated in ", "Contributed to "),
    ("involved in ", "Contributed to "),
)

_COMMON_PAST = {
    "helping": "Supported", "managing": "Managed", "handling": "Handled",
    "supporting": "Supported", "preparing": "Prepared", "maintaining": "Maintained",
    "organising": "Organised", "organizing": "Organized", "coordinating": "Coordinated",
    "assisting": "Supported", "working": "Worked", "creating": "Created",
    "developing": "Developed", "training": "Trained", "monitoring": "Monitored",
    "reporting": "Reported", "processing": "Processed", "repairing": "Repaired",
    "installing": "Installed", "troubleshooting": "Troubleshot",
    "documenting": "Documented", "planning": "Planned", "leading": "Led",
    "supervising": "Supervised", "teaching": "Taught", "cleaning": "Cleaned",
    "serving": "Served", "selling": "Sold", "driving": "Drove", "writing": "Wrote",
    "communicating": "Communicated", "collaborating": "Collaborated",
    "ensuring": "Ensured", "performing": "Performed", "conducting": "Conducted",
    "reviewing": "Reviewed", "updating": "Updated", "recording": "Recorded",
    "checking": "Checked", "answering": "Answered", "responding": "Responded",
    "scheduling": "Scheduled", "filing": "Filed", "typing": "Typed",
    "entering": "Entered", "reconciling": "Reconciled", "auditing": "Audited",
    "budgeting": "Budgeted", "forecasting": "Forecasted", "designing": "Designed",
    "building": "Built", "testing": "Tested", "deploying": "Deployed",
    "configuring": "Configured", "resolving": "Resolved", "analysing": "Analysed",
    "analyzing": "Analyzed", "measuring": "Measured", "collecting": "Collected",
    "delivering": "Delivered", "packing": "Packed", "loading": "Loaded",
    "dispatching": "Dispatched", "inspecting": "Inspected", "mentoring": "Mentored",
    "coaching": "Coached", "facilitating": "Facilitated", "presenting": "Presented",
    "translating": "Translated",
}


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _skill_aliases(skill: str) -> list[str]:
    text = _clean_text(skill)
    if not text:
        return []
    aliases = [text]
    for inside in re.findall(r"\(([^)]+)\)", text):
        inside = inside.strip()
        if inside:
            aliases.append(inside)
    return aliases


def _has_phrase(text: str, phrase: str) -> bool:
    parts = [re.escape(part) for part in _clean_text(phrase).split()]
    if not parts:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s+".join(parts) + r"(?![a-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _cv_text(profile: dict, cv_data: dict) -> str:
    document = build_cv_document(profile, cv_data)
    chunks = [
        document.get("target_role", ""),
        document.get("summary", ""),
        " ".join(document.get("skills", [])),
        " ".join(document.get("education", [])),
        " ".join(document.get("projects", [])),
        " ".join(document.get("volunteering", [])),
        " ".join(document.get("certifications", [])),
    ]
    for entry in document.get("experience", []):
        chunks.extend(
            [
                entry.get("job_title", ""),
                entry.get("organisation", ""),
                " ".join(entry.get("responsibilities", [])),
            ]
        )
    return _clean_text(" ".join(chunks))


def _fallback_terms(job_ad: str, cv_text: str) -> tuple[list[str], list[str]]:
    words = re.findall(r"[A-Za-z][A-Za-z+#.-]{3,}", job_ad)
    counts = Counter(
        word.casefold()
        for word in words
        if word.casefold() not in _STOPWORDS
        and not word.casefold().isdigit()
    )
    cv_lower = cv_text.casefold()
    ordered = [word for word, _ in counts.most_common(30)]
    required = ordered[:12]
    missing = [word for word in required if word not in cv_lower]
    matched = [word for word in required if word in cv_lower]
    return matched, missing


def analyse_job_ad(
    job_ad: str,
    profile: dict,
    cv_data: dict,
    known_skills: Iterable[str] | None = None,
) -> dict:
    """Compare a pasted job advert with the CV without changing the CV."""

    advert = _clean_text(job_ad)
    if not advert:
        return {"available": False}

    cv_text = _cv_text(profile, cv_data)
    aliases: dict[str, str] = {}
    for skill in known_skills or []:
        for alias in _skill_aliases(str(skill)):
            aliases.setdefault(alias.casefold(), str(skill).strip())

    required: list[str] = []
    seen: set[str] = set()
    for alias, display in aliases.items():
        if _has_phrase(advert, alias) and display.casefold() not in seen:
            seen.add(display.casefold())
            required.append(display)

    fallback = not required
    if fallback:
        matched_terms, missing_terms = _fallback_terms(advert, cv_text)
        required = matched_terms + missing_terms
        matched = matched_terms
        missing = missing_terms
    else:
        matched = [skill for skill in required if _has_phrase(cv_text, skill)]
        missing = [skill for skill in required if skill not in matched]

    coverage = round(100 * len(matched) / len(required)) if required else 0
    if coverage >= 75:
        label = "Strong coverage"
    elif coverage >= 50:
        label = "Partial coverage"
    elif coverage:
        label = "Needs strengthening"
    else:
        label = "No clear match found"

    return {
        "available": True,
        "job_ad": advert,
        "required": required,
        "matched": matched,
        "missing": missing[:12],
        "score": coverage,
        "label": label,
        "fallback": fallback,
        "note": (
            "This is a wording comparison, not an employer's shortlisting system. "
            "Only add a skill if it genuinely describes your experience."
            if not fallback
            else "No recognised skill names were found in the advert, so these are "
            "frequent keywords to review. Do not add a keyword unless it is true."
        ),
    }


def cv_strength(profile: dict, cv_data: dict) -> dict:
    """Return a rules-based readiness score with the highest-value next fixes."""

    document = build_cv_document(profile, cv_data)
    contact_errors = validate_cv_contact_details(
        document.get("target_role", ""),
        document.get("email", ""),
        document.get("phone", ""),
    )
    experience = document.get("experience", [])
    responsibilities = [
        item for entry in experience for item in entry.get("responsibilities", [])
    ]
    checks: list[dict] = []

    def check(label: str, points: int, earned: int, fix: str) -> None:
        checks.append(
            {
                "label": label,
                "points": points,
                "earned": max(0, min(points, earned)),
                "fix": fix,
            }
        )

    check(
        "Target role and contact details",
        10,
        10 if not contact_errors else 0,
        "Add a target job position, a complete email address and a phone number.",
    )
    summary_length = len(document.get("summary", ""))
    check(
        "Professional summary",
        12,
        12 if summary_length >= 100 else 8 if summary_length >= 40 else 0,
        "Write two or three honest lines about your background and the role you want.",
    )
    check(
        "Education and training",
        10,
        10 if document.get("education") else 0,
        "Add your highest qualification, institution and year where known.",
    )
    skill_count = len(document.get("skills", []))
    check(
        "Relevant skills",
        15,
        15 if skill_count >= 5 else 8 if skill_count >= 2 else 0,
        "Select at least five skills that genuinely reflect your experience.",
    )
    check(
        "Work, attachment or practical experience",
        20,
        20 if experience else 0,
        "Add an attachment, internship, volunteering role or practical project.",
    )
    strong_bullets = sum(
        1
        for item in responsibilities
        if 8 <= len(item.split()) <= 30 and re.search(r"\d", item)
    )
    check(
        "Results-focused experience bullets",
        10,
        10 if strong_bullets >= 2 else 5 if responsibilities else 0,
        "Use a new line per achievement and add a number only where you know it.",
    )
    check(
        "Projects, volunteering or certifications",
        8,
        8 if (
            document.get("projects")
            or document.get("volunteering")
            or document.get("certifications")
        ) else 0,
        "Add a project, volunteer role or short course that supports this job.",
    )
    check(
        "Languages",
        4,
        4 if document.get("languages") else 0,
        "List languages you can actually use at work, such as English and Kiswahili.",
    )
    check(
        "Referees",
        3,
        3 if document.get("referees") else 0,
        "Add referees or write 'Available upon request'.",
    )
    check(
        "Professional presentation",
        8,
        8 if document.get("summary") and skill_count and experience else 4 if document.get("summary") or experience else 0,
        "Complete the main sections so the CV reads as one consistent document.",
    )

    score = sum(item["earned"] for item in checks)
    if score >= 85:
        band = "Strong"
    elif score >= 65:
        band = "Good foundation"
    elif score >= 45:
        band = "Needs strengthening"
    else:
        band = "Just starting"

    fixes = sorted(
        (item for item in checks if item["earned"] < item["points"]),
        key=lambda item: item["points"] - item["earned"],
        reverse=True,
    )[:3]
    return {
        "score": score,
        "band": band,
        "checks": checks,
        "fixes": fixes,
        "note": (
            "This is a completeness and clarity checklist, not a guarantee of "
            "shortlisting or an employer's ATS result."
        ),
    }


def bullet_feedback(text: str) -> dict:
    """Review one experience bullet without inventing facts or results."""

    original = _clean_text(text).lstrip("-• ").strip()
    if not original:
        return {"original": "", "suggestion": "", "issues": [], "ok": False}

    lower = original.casefold()
    suggestion = original
    issues: list[str] = []
    for weak, replacement in _WEAK_OPENERS:
        if lower.startswith(weak):
            tail = original[len(weak):].strip()
            first_word = tail.split()[0] if tail else ""
            past = _COMMON_PAST.get(first_word.casefold())
            if past:
                tail = f"{past}{tail[len(first_word):]}"
            else:
                tail = f"{replacement or 'Handled '}{tail}".strip()
            suggestion = tail
            issues.append(f"Remove the weak opener '{weak.strip()}'.")
            break

    if suggestion:
        suggestion = suggestion[0].upper() + suggestion[1:]

    words = original.split()
    if len(words) > 30:
        issues.append("Shorten this bullet to roughly 12-25 words.")
    if len(words) < 5:
        issues.append("Add enough detail to show what you actually did.")
    if re.search(r"\b(I|my|me)\b", original, re.IGNORECASE):
        issues.append("Use an implied first person: start with the action, not 'I'.")
    first = re.sub(r"[^a-z]", "", words[0].casefold()) if words else ""
    if first not in _ACTION_VERBS:
        issues.append("Start with a specific action verb such as supported, prepared or resolved.")
    if not re.search(r"\d", original):
        issues.append(
            "No number is present. Add a measurable result only if you know the real figure."
        )
    if "responsible for" in lower or "duties" in lower:
        issues.append("Describe the action and outcome, not only the duty.")

    return {
        "original": original,
        "suggestion": suggestion,
        "issues": issues,
        "ok": not issues,
    }


def cover_letter(profile: dict, cv_data: dict, job_ad: str = "") -> str:
    """Build a factual cover-letter draft from the current CV data."""

    document = build_cv_document(profile, cv_data)
    name = document.get("name") or "Applicant"
    target = str(document.get("target_role") or "").strip()
    target_phrase = f"the {target} role" if target else "the advertised role"
    contact = " | ".join(
        value
        for value in (document.get("email"), document.get("phone"), document.get("location"))
        if value
    )

    lines = ["Dear Hiring Manager,", "", f"I am writing to apply for {target_phrase}."]
    if document.get("summary"):
        lines.extend(["", document["summary"]])
    else:
        education = document.get("education", [])
        if education:
            lines.extend(
                [
                    "",
                    f"My background includes {education[0]}, and I am now seeking an opportunity as {target or 'a professional in this field'}.",
                ]
            )

    skills = document.get("skills", [])[:6]
    if skills:
        lines.extend(
            [
                "",
                "The skills I would bring to this role include "
                + ", ".join(skills)
                + ". They come from my education, practical work and the projects described in my CV.",
            ]
        )

    experience = document.get("experience", [])
    if experience:
        first = experience[0]
        role = first.get("job_title") or "my practical role"
        organisation = first.get("organisation")
        where = f" at {organisation}" if organisation else ""
        lines.extend(
            [
                "",
                f"In my role as {role}{where}, I developed practical experience that I can apply to this position. My CV gives specific examples of the work I did and the skills I used.",
            ]
        )

    if str(job_ad or "").strip():
        lines.extend(
            [
                "",
                "I have read the requirements in the job advert and have focused this application on the experience and skills that are genuinely relevant to them.",
            ]
        )

    lines.extend(
        [
            "",
            "Thank you for considering my application. I would welcome the opportunity to discuss how my background fits the role.",
            "",
            "Sincerely,",
            name,
        ]
    )
    if contact:
        lines.append(contact)
    lines.extend(
        [
            "",
            "Note: review this draft and add any specific facts about the employer or role before sending it.",
        ]
    )
    return "\n".join(lines)


def interview_questions(profile: dict, cv_data: dict) -> list[str]:
    """Create practice questions grounded in the applicant's own CV data."""

    document = build_cv_document(profile, cv_data)
    target = str(document.get("target_role") or "").strip()
    questions = [
        (
            f"Why are you interested in the {target} role, and what makes you a suitable candidate?"
            if target
            else "Why are you interested in this role, and what makes you a suitable candidate?"
        ),
    ]
    for entry in document.get("experience", [])[:2]:
        title = entry.get("job_title") or "practical experience"
        organisation = entry.get("organisation")
        if organisation:
            questions.append(f"Tell me about your work as {title} at {organisation}.")
        else:
            questions.append(f"Tell me about your experience as {title}.")
    for skill in document.get("skills", [])[:3]:
        questions.append(
            f"Describe a time you used {skill} to solve a problem or complete a task."
        )
    if document.get("education"):
        questions.append(
            "How has your education or training prepared you for this role?"
        )
    lowered = _cv_text(profile, cv_data).casefold()
    if "attachment" in lowered or "intern" in lowered:
        questions.append(
            "What did you learn during your attachment or internship, and how would you apply it at work?"
        )
    questions.append("Tell me about a time you worked with others to meet a deadline.")
    questions.append("Describe a challenge you faced and how you handled it.")
    return list(dict.fromkeys(questions))[:8]


__all__ = [
    "analyse_job_ad",
    "bullet_feedback",
    "cover_letter",
    "cv_strength",
    "interview_questions",
]
