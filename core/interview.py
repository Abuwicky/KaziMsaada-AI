"""Interview question bank, configuration, and local feedback guidance.

This module is deliberately provider-neutral. It can produce useful local
practice guidance without any network access. An approved AI adapter can be
supplied later through ``core.ai_client`` without changing the UI or storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .ai_client import AIProvider, FeedbackRequest

MIN_QUESTIONS_PER_SESSION = 3
DEFAULT_QUESTIONS_PER_SESSION = 4
MAX_QUESTIONS_PER_SESSION = 6
MAX_ANSWER_CHARS = 5000
MAX_TARGET_ROLE_CHARS = 160
MAX_FEEDBACK_CHARS = 4000


@dataclass(frozen=True)
class InterviewCategory:
    category_id: str
    label: str
    description: str


@dataclass(frozen=True)
class InterviewQuestion:
    question_id: str
    category: str
    interview_categories: tuple[str, ...]
    role_groups: tuple[str, ...]
    difficulty: str
    question: str
    assesses: str
    structure: str
    encourage_star: bool = True


INTERVIEW_CATEGORIES = (
    InterviewCategory(
        "general",
        "General job interview",
        "Broad questions suitable for most advertised roles.",
    ),
    InterviewCategory(
        "graduate_entry",
        "Graduate and entry-level interviews",
        "Questions for students, recent graduates, and first professional roles.",
    ),
    InterviewCategory(
        "internship_attachment",
        "Internship and industrial attachment",
        "Practice for internships, attachments, and learning placements.",
    ),
    InterviewCategory(
        "behavioural_competency",
        "Behavioural and competency-based interviews",
        "Evidence-based questions about how you have worked with others.",
    ),
    InterviewCategory(
        "customer_service_admin",
        "Customer service and administration",
        "Questions about customers, records, accuracy, and office coordination.",
    ),
    InterviewCategory(
        "technical_professional",
        "Technical and professional interviews",
        "Questions for technical, specialist, and professional roles.",
    ),
)

CATEGORY_IDS = tuple(category.category_id for category in INTERVIEW_CATEGORIES)
CATEGORY_LOOKUP = {
    category.category_id: category for category in INTERVIEW_CATEGORIES
}
CATEGORY_LABELS = {
    category.category_id: category.label for category in INTERVIEW_CATEGORIES
}
CATEGORY_LABEL_TO_ID = {
    category.label: category.category_id for category in INTERVIEW_CATEGORIES
}

DIFFICULTY_IDS = ("beginner", "intermediate", "advanced")
DIFFICULTY_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}
DIFFICULTY_LABEL_TO_ID = {
    label: difficulty_id for difficulty_id, label in DIFFICULTY_LABELS.items()
}
DIFFICULTY_RANK = {
    difficulty_id: index for index, difficulty_id in enumerate(DIFFICULTY_IDS)
}

ROLE_GROUPS = (
    "general",
    "graduate_entry",
    "internship",
    "customer_service_admin",
    "technical",
    "professional",
)
ROLE_GROUP_KEYWORDS = {
    "graduate_entry": (
        "graduate",
        "student",
        "entry level",
        "entry-level",
        "trainee",
        "recent graduate",
    ),
    "internship": (
        "intern",
        "internship",
        "attachment",
        "industrial attachment",
        "placement",
    ),
    "customer_service_admin": (
        "customer",
        "customer service",
        "customer care",
        "customer support",
        "client support",
        "reception",
        "receptionist",
        "admin",
        "administration",
        "administrative",
        "office",
        "secretary",
        "clerical",
        "cashier",
        "sales",
    ),
    "technical": (
        "ict",
        "information technology",
        "computer",
        "software",
        "developer",
        "programmer",
        "network",
        "data",
        "database",
        "engineer",
        "engineering",
        "technical",
        "technician",
        "mechanic",
        "electrical",
        "plumbing",
        "construction",
        "masonry",
        "welding",
    ),
    "professional": (
        "account",
        "finance",
        "audit",
        "nurse",
        "clinical",
        "teacher",
        "lecturer",
        "lawyer",
        "legal",
        "human resource",
        "hr",
        "manager",
        "management",
        "officer",
        "specialist",
    ),
}


def _q(
    question_id: str,
    category: str,
    interview_categories: tuple[str, ...],
    role_groups: tuple[str, ...],
    difficulty: str,
    question: str,
    assesses: str,
    structure: str,
    encourage_star: bool = True,
) -> InterviewQuestion:
    return InterviewQuestion(
        question_id=question_id,
        category=category,
        interview_categories=interview_categories,
        role_groups=role_groups,
        difficulty=difficulty,
        question=question,
        assesses=assesses,
        structure=structure,
        encourage_star=encourage_star,
    )


# The original nine questions are kept verbatim so the existing question bank
# and Phase 0 tests continue to work unchanged.
CORE_INTERVIEW_QUESTIONS = [
    _q(
        "opening_tell_me_about_yourself",
        "Opening",
        ("general", "graduate_entry", "internship_attachment"),
        ("general",),
        "beginner",
        "Tell me about yourself.",
        "They are testing whether you can summarise your background in a clear, "
        "relevant way — not your whole life story.",
        "Present → proof → purpose. Say who you are, give one or two examples "
        "of relevant work or study, then explain why this role is the logical next step.",
        encourage_star=False,
    ),
    _q(
        "experience_proud_project",
        "Experience",
        (
            "general",
            "graduate_entry",
            "internship_attachment",
            "behavioural_competency",
            "technical_professional",
        ),
        ("general",),
        "intermediate",
        "Walk me through a project or task you are proud of.",
        "They want evidence of how you work, not just a description of the result.",
        "Use STAR: the situation, your specific task, the actions you personally took, "
        "and the result. Mention what you learned or improved.",
    ),
    _q(
        "experience_teamwork",
        "Experience",
        (
            "general",
            "graduate_entry",
            "internship_attachment",
            "behavioural_competency",
            "customer_service_admin",
        ),
        ("general",),
        "intermediate",
        "Tell me about a time you worked in a team.",
        "They are assessing collaboration, communication, and how you handle "
        "different working styles.",
        "Choose a real example. Explain your role, how you agreed responsibilities, "
        "how you handled a disagreement, and what the team delivered.",
    ),
    _q(
        "problem_solving_difficult_problem",
        "Problem solving",
        (
            "general",
            "graduate_entry",
            "internship_attachment",
            "behavioural_competency",
            "customer_service_admin",
            "technical_professional",
        ),
        ("general",),
        "intermediate",
        "Describe a difficult problem you solved.",
        "They want to see structured thinking and persistence, especially when "
        "resources were limited.",
        "Explain how you defined the problem, the options you considered, why you "
        "chose your approach, and how you checked that it worked.",
    ),
    _q(
        "problem_solving_mistake",
        "Problem solving",
        (
            "general",
            "graduate_entry",
            "internship_attachment",
            "behavioural_competency",
        ),
        ("general",),
        "intermediate",
        "Tell me about a mistake you made and what happened next.",
        "They are testing honesty, accountability, and whether you learn from feedback.",
        "Own the mistake without blaming others. Explain the impact, what you changed, "
        "and how you prevented a repeat.",
    ),
    _q(
        "motivation_role_and_organisation",
        "Motivation",
        ("general", "graduate_entry", "internship_attachment"),
        ("general",),
        "beginner",
        "Why do you want this role and this organisation?",
        "They want to know whether you understand the job and have a genuine reason "
        "to apply — not just that you need any job.",
        "Connect the organisation's work to your skills and interests. Mention "
        "something specific from the job description or their public information.",
        encourage_star=False,
    ),
    _q(
        "motivation_future_goals",
        "Motivation",
        ("general", "graduate_entry", "technical_professional"),
        ("general",),
        "beginner",
        "Where do you see yourself in the next few years?",
        "They are checking whether your goals fit the role and whether you are "
        "likely to grow with the organisation.",
        "Describe realistic growth areas linked to the role: deeper expertise, "
        "supervising work, or broader responsibility. Avoid naming a different career.",
        encourage_star=False,
    ),
    _q(
        "closing_questions_for_interviewer",
        "Closing",
        ("general", "graduate_entry", "internship_attachment"),
        ("general",),
        "beginner",
        "Do you have any questions for us?",
        "They are assessing your interest and whether you have prepared seriously.",
        "Ask about the first projects, how success is measured, training opportunities, "
        "or the team you would join. Avoid questions about salary at the first stage.",
        encourage_star=False,
    ),
    _q(
        "closing_anything_else",
        "Closing",
        ("general", "graduate_entry", "internship_attachment"),
        ("general",),
        "beginner",
        "Is there anything else you would like us to know?",
        "They are giving you a final chance to address a gap or reinforce your fit.",
        "Briefly restate your strongest relevant evidence and your enthusiasm. "
        "Do not introduce a completely new story.",
        encourage_star=False,
    ),
]

ADDITIONAL_INTERVIEW_QUESTIONS = [
    _q(
        "graduate_studies_to_role",
        "Graduate",
        ("graduate_entry",),
        ("graduate_entry",),
        "beginner",
        "Which parts of your studies best prepare you for this role?",
        "They want to see that you can connect your education to the requirements "
        "of the job, not just list subjects.",
        "Choose two or three relevant topics or projects. Explain what you learned, "
        "how you applied it, and how it would help you in this role.",
        encourage_star=False,
    ),
    _q(
        "graduate_group_assignment",
        "Graduate",
        ("graduate_entry", "behavioural_competency"),
        ("graduate_entry",),
        "intermediate",
        "Tell me about a group assignment where you had to rely on other people.",
        "They are assessing collaboration, reliability, and how you handle shared "
        "responsibility.",
        "Use STAR. Explain the shared goal, your part, how you coordinated, any "
        "disagreement, and the final result.",
    ),
    _q(
        "internship_why_attachment",
        "Internship",
        ("internship_attachment",),
        ("internship", "graduate_entry"),
        "beginner",
        "Why are you seeking an internship or industrial attachment with us?",
        "They want to know whether you understand the purpose of the attachment and "
        "have a genuine interest in learning.",
        "Connect your course or career direction to the organisation's work. Say what "
        "you want to learn, what you can contribute, and why this placement matters.",
        encourage_star=False,
    ),
    _q(
        "internship_learning_goals",
        "Internship",
        ("internship_attachment",),
        ("internship", "graduate_entry"),
        "beginner",
        "What do you hope to learn during this attachment?",
        "They are checking whether you have realistic learning goals and will make "
        "the most of supervision.",
        "Name two or three practical areas you want to develop. Link them to tasks "
        "you expect to observe or support, and show willingness to ask questions.",
        encourage_star=False,
    ),
    _q(
        "internship_routine_tasks",
        "Internship",
        ("internship_attachment",),
        ("internship", "graduate_entry"),
        "intermediate",
        "How would you stay motivated when given routine or repetitive tasks?",
        "They want to see reliability, attention to detail, and a professional "
        "attitude toward all parts of the work.",
        "Acknowledge that routine work matters. Give an example of doing it carefully "
        "and explain how you would keep learning and check your accuracy.",
    ),
    _q(
        "customer_service_upset_customer",
        "Customer service",
        ("customer_service_admin",),
        ("customer_service_admin",),
        "intermediate",
        "Tell me about a time you handled an upset customer.",
        "They are assessing empathy, calm communication, and whether you can follow "
        "a process without becoming defensive.",
        "Use STAR. Explain the customer's concern, what you did to listen and clarify, "
        "the action you took, and the outcome. Do not blame the customer.",
    ),
    _q(
        "customer_service_prioritise_tasks",
        "Customer service",
        ("customer_service_admin",),
        ("customer_service_admin",),
        "intermediate",
        "How do you prioritise several requests when everything feels urgent?",
        "They want to see organisation, judgement, and clear communication when "
        "demand exceeds time.",
        "Describe a simple method: check deadlines and impact, ask for clarification, "
        "complete the most time-sensitive task, and update the people affected.",
    ),
    _q(
        "customer_service_accuracy",
        "Customer service",
        ("customer_service_admin",),
        ("customer_service_admin",),
        "beginner",
        "How do you make sure customer details and records are accurate?",
        "They are checking attention to detail, confidentiality, and whether you use "
        "checks rather than relying on memory.",
        "Explain a specific checking habit: read back details, use a checklist, verify "
        "spelling or numbers, save records promptly, and ask when something is unclear.",
        encourage_star=False,
    ),
    _q(
        "customer_service_handover",
        "Customer service",
        ("customer_service_admin",),
        ("customer_service_admin",),
        "intermediate",
        "Tell me about a time you handed over work to a colleague or followed up on "
        "a customer issue.",
        "They want evidence that you can communicate clearly and take responsibility "
        "for unfinished work.",
        "Use STAR. Explain what was outstanding, what you recorded or communicated, "
        "who took over, and how you checked the issue was resolved.",
    ),
    _q(
        "technical_diagnose_problem",
        "Technical",
        ("technical_professional",),
        ("technical", "professional"),
        "intermediate",
        "Describe how you diagnosed and resolved a technical problem.",
        "They want to see a logical troubleshooting process, safe practice, and "
        "evidence of how you confirmed the fix.",
        "Explain the symptoms, the checks you made, the options you ruled out, the fix "
        "you applied, and how you tested or documented it.",
    ),
    _q(
        "technical_explain_simply",
        "Technical",
        ("technical_professional",),
        ("technical", "professional"),
        "intermediate",
        "Tell me about a time you explained a technical issue to someone without a "
        "technical background.",
        "They are assessing communication, patience, and whether you can adapt your "
        "language to the audience.",
        "Use STAR. Explain who needed help, how you simplified the explanation, what "
        "you asked them to do, and how you checked they understood.",
    ),
    _q(
        "technical_safety_quality",
        "Technical",
        ("technical_professional",),
        ("technical", "professional"),
        "advanced",
        "How do you balance speed with safety and quality in technical work?",
        "They want to see that you do not trade safety or quality for speed, and that "
        "you know when to stop and ask.",
        "Give a real example. Explain the safety or quality check, the pressure you "
        "faced, what you did, and the result. Mention when you would escalate.",
    ),
    _q(
        "professional_handle_pressure",
        "Professional",
        (
            "general",
            "behavioural_competency",
            "customer_service_admin",
            "technical_professional",
        ),
        ("professional", "general"),
        "intermediate",
        "Describe a time you worked under pressure and still delivered.",
        "They are checking planning, prioritisation, and how you communicate when "
        "deadlines are tight.",
        "Use STAR. Explain the deadline, what you planned, what you did first, who you "
        "updated, and the result.",
    ),
    _q(
        "professional_continuous_learning",
        "Technical",
        ("technical_professional",),
        ("technical", "professional"),
        "beginner",
        "How do you keep your professional knowledge up to date?",
        "They want to see curiosity, reliable learning habits, and awareness of "
        "standards in your field.",
        "Name specific sources and habits, such as short courses, reading, practice "
        "projects, mentorship, or professional bodies. Explain how you apply what you learn.",
        encourage_star=False,
    ),
]

QUESTION_BANK = [*CORE_INTERVIEW_QUESTIONS, *ADDITIONAL_INTERVIEW_QUESTIONS]
QUESTION_BANK_IDS = tuple(question.question_id for question in QUESTION_BANK)
QUESTION_LOOKUP = {question.question_id: question for question in QUESTION_BANK}
CORE_QUESTION_IDS = tuple(
    question.question_id for question in CORE_INTERVIEW_QUESTIONS
)
CORE_QUESTION_LOOKUP = {
    question.question_id: question for question in CORE_INTERVIEW_QUESTIONS
}


class InterviewConfigurationError(ValueError):
    """Raised when interview settings or question filters are invalid."""


def get_question(question_id: str) -> InterviewQuestion | None:
    return QUESTION_LOOKUP.get(str(question_id))


def category_label(category_id: str) -> str:
    return CATEGORY_LABELS.get(str(category_id), str(category_id))


def difficulty_label(difficulty_id: str) -> str:
    return DIFFICULTY_LABELS.get(str(difficulty_id), str(difficulty_id))


def detect_role_groups(target_role: str) -> set[str]:
    """Return likely role groups for a free-text target role."""

    text = str(target_role or "").casefold()
    groups = {"general"}
    for group, keywords in ROLE_GROUP_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            groups.add(group)
    return groups


def questions_for_category(category_id: str) -> list[InterviewQuestion]:
    if category_id not in CATEGORY_LOOKUP:
        raise InterviewConfigurationError("Unknown interview category.")
    return [
        question
        for question in QUESTION_BANK
        if category_id in question.interview_categories
    ]


def select_questions(
    category_id: str,
    difficulty: str,
    target_role: str,
    limit: int = DEFAULT_QUESTIONS_PER_SESSION,
) -> list[InterviewQuestion]:
    """Select role-relevant questions, preferring the chosen difficulty."""

    if category_id not in CATEGORY_LOOKUP:
        raise InterviewConfigurationError("Choose a valid interview category.")
    if difficulty not in DIFFICULTY_IDS:
        raise InterviewConfigurationError("Choose a valid difficulty level.")

    try:
        wanted = int(limit)
    except (TypeError, ValueError) as error:
        raise InterviewConfigurationError(
            "The number of questions must be a whole number."
        ) from error

    wanted = max(MIN_QUESTIONS_PER_SESSION, min(wanted, MAX_QUESTIONS_PER_SESSION))
    pool = questions_for_category(category_id)
    role_groups = detect_role_groups(target_role)
    target_rank = DIFFICULTY_RANK[difficulty]
    bank_order = {question.question_id: index for index, question in enumerate(QUESTION_BANK)}

    def role_match(question: InterviewQuestion) -> bool:
        return "general" in question.role_groups or bool(
            set(question.role_groups) & role_groups
        )

    ordered = sorted(
        pool,
        key=lambda question: (
            0 if role_match(question) else 1,
            abs(DIFFICULTY_RANK[question.difficulty] - target_rank),
            bank_order[question.question_id],
        ),
    )
    role_relevant = [question for question in ordered if role_match(question)]
    if role_relevant:
        ordered = role_relevant
    return ordered[:wanted]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _star_presence(answer: str) -> dict[str, bool]:
    text = answer.casefold()
    return {
        "situation": bool(
            re.search(r"\b(situation|context|when|while|during|at the time)\b", text)
        ),
        "task": bool(
            re.search(r"\b(task|goal|needed|responsible|had to|required)\b", text)
        ),
        "action": bool(
            re.search(
                r"\b(action|i did|i built|i organised|i organized|i contacted|"
                r"i prepared|i fixed|i led|i helped|i checked|i created|i reviewed)\b",
                text,
            )
        ),
        "result": bool(
            re.search(
                r"\b(result|outcome|achieved|improved|delivered|learned|reduced|"
                r"increased|completed|resolved)\b",
                text,
            )
        ),
    }


def _has_specific_detail(answer: str) -> bool:
    return bool(
        re.search(r"\b\d+[\d,.]*\b", answer)
        or re.search(
            r"\b(example|project|assignment|attachment|volunteer|customer|team|"
            r"system|report|record|deadline)\b",
            answer.casefold(),
        )
    )


def build_local_feedback(
    question: InterviewQuestion,
    answer: str,
    target_role: str,
    difficulty: str,
) -> dict[str, Any]:
    """Create transparent, non-scoring practice guidance from the answer."""

    clean_answer = str(answer or "").strip()
    if not clean_answer:
        raise InterviewConfigurationError("Write an answer before requesting feedback.")

    words = _word_count(clean_answer)
    sentences = max(1, len(re.findall(r"[.!?]+", clean_answer)) or 1)
    average_sentence = words / sentences
    star = _star_presence(clean_answer)
    star_complete = all(star.values())
    specific = _has_specific_detail(clean_answer)
    role = str(target_role or "the target role").strip() or "the target role"

    if words < 35:
        relevance = (
            "Your answer is quite short. Add a direct response to the question and "
            f"one concrete example connected to {role}."
        )
    elif words > 320:
        relevance = (
            "Your answer covers a lot of ground. Keep the most relevant example and "
            "remove background that does not help answer the question."
        )
    else:
        relevance = (
            "Your answer responds to the question. Make the connection to "
            f"{role} explicit so the interviewer can see why the example matters."
        )

    if words < 50:
        clarity = (
            "Use two or three shorter sentences: what happened, what you did, and "
            "what changed."
        )
    elif average_sentence > 30:
        clarity = (
            "Some sentences are long. Split them so the main action and result are "
            "easy to follow when spoken aloud."
        )
    else:
        clarity = (
            "Your answer is a workable length. Say it aloud once and check that the "
            "main point arrives early."
        )

    found_star = [name.title() for name, present in star.items() if present]
    missing_star = [name.title() for name, present in star.items() if not present]
    if star_complete:
        structure = (
            "Your answer appears to include Situation, Task, Action and Result. "
            "Check that the result is specific and honest."
        )
    elif found_star:
        structure = (
            "You include some STAR elements: "
            + ", ".join(found_star)
            + ". Add "
            + ", ".join(missing_star)
            + " to make the example easier to follow."
        )
    else:
        structure = (
            "Try a STAR structure: Situation (the context), Task (what you needed "
            "to do), Action (what you personally did), Result (what changed)."
        )

    if specific:
        examples = (
            "You include at least one concrete detail. Strengthen it with a measurable "
            "result only where you can verify it."
        )
    else:
        examples = (
            "Add one specific example from study, work, volunteering, attachment, "
            "a group assignment, a personal project, or a relevant life experience."
        )

    suggestions: list[str] = []
    if words < 80:
        suggestions.append("Expand the example with one action and one result.")
    if not star_complete:
        suggestions.append("Label the STAR parts in your notes before speaking.")
    if not specific:
        suggestions.append("Add a concrete detail such as what you built, fixed, organised or delivered.")
    if average_sentence > 30:
        suggestions.append("Shorten long sentences and pause between key points.")
    suggestions.append(f"Finish by linking the example back to {role}.")
    suggestions = suggestions[:5]

    return {
        "feedback_kind": "local_guidance",
        "source": "local_guidance",
        "summary": (
            "Local question-bank guidance, not AI-generated feedback. Use it as a "
            "practice checklist, not a score."
        ),
        "relevance": relevance,
        "clarity": clarity,
        "structure": structure,
        "examples": examples,
        "suggestions": suggestions,
        "star_checklist": star,
        "word_count": words,
        "disclaimer": (
            "This guidance is not a measurement of employability, intelligence or "
            "personality, and it does not guarantee interview success."
        ),
    }


def _truncate(value: Any, limit: int = MAX_FEEDBACK_CHARS) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _normalise_ai_feedback(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("The AI provider did not return a feedback object.")

    required = ("relevance", "clarity", "structure", "examples")
    feedback: dict[str, Any] = {}
    for key in required:
        value = _truncate(payload.get(key))
        if not value:
            raise ValueError("The AI provider returned incomplete feedback.")
        feedback[key] = value

    suggestions = payload.get("suggestions", [])
    if isinstance(suggestions, str):
        suggestions = [suggestions]
    if not isinstance(suggestions, (list, tuple)):
        suggestions = []
    feedback["suggestions"] = [
        _truncate(item, 500)
        for item in suggestions
        if str(item).strip()
    ][:5]
    if not feedback["suggestions"]:
        feedback["suggestions"] = [
            "Practise the answer aloud and keep the example and result specific."
        ]

    feedback["summary"] = _truncate(
        payload.get(
            "summary",
            "AI-generated practice feedback. Treat it as a prompt for reflection, "
            "not a definitive assessment.",
        )
    )
    feedback["star_checklist"] = (
        dict(payload.get("star_checklist", {}))
        if isinstance(payload.get("star_checklist"), Mapping)
        else {}
    )
    feedback["feedback_kind"] = "ai"
    feedback["source"] = "ai"
    feedback["disclaimer"] = (
        "AI-generated feedback is a practice aid. It is not a measurement of "
        "employability, intelligence or personality, and it does not guarantee "
        "interview success."
    )
    return feedback


def evaluate_answer(
    question: InterviewQuestion,
    answer: str,
    target_role: str,
    difficulty: str,
    provider: AIProvider | None = None,
) -> dict[str, Any]:
    """Return AI feedback when available, otherwise local guidance.

    Provider or validation errors are converted into local fallback guidance so
    the interview session cannot crash because of an external service.
    """

    local = build_local_feedback(question, answer, target_role, difficulty)
    if provider is None:
        return local

    request = FeedbackRequest(
        target_role=str(target_role or "").strip(),
        category=question.category,
        difficulty=difficulty,
        question=question.question,
        answer=str(answer or "").strip()[:MAX_ANSWER_CHARS],
    )

    try:
        payload = provider.generate_feedback(request)
        feedback = _normalise_ai_feedback(payload)
    except Exception as error:  # Provider failures must never break practice.
        local["source"] = "local_fallback"
        local["feedback_kind"] = "local_fallback"
        local["notice"] = (
            "AI feedback was unavailable, so this is local question-bank guidance. "
            "No answer was lost."
        )
        local["error_category"] = type(error).__name__
        return local

    feedback["provider_name"] = str(getattr(provider, "name", "AI provider"))
    return feedback


def build_session_summary(responses: list[dict]) -> dict[str, Any]:
    """Aggregate non-scoring strengths, improvements, and next steps."""

    feedback_items = [
        response.get("feedback")
        for response in responses
        if isinstance(response.get("feedback"), Mapping)
    ]
    strengths: list[str] = []
    improvements: list[str] = []

    if feedback_items:
        star_complete = sum(
            1
            for feedback in feedback_items
            if feedback.get("star_checklist")
            and all(feedback["star_checklist"].values())
        )
        if star_complete:
            strengths.append(
                f"You used a complete STAR structure in {star_complete} "
                f"{'answer' if star_complete == 1 else 'answers'}."
            )

        word_counts = [
            feedback.get("word_count")
            for feedback in feedback_items
            if isinstance(feedback.get("word_count"), int)
        ]
        if any(80 <= count <= 280 for count in word_counts):
            strengths.append(
                "At least one answer was developed enough to explain an example."
            )

        if any("concrete detail" in str(feedback.get("examples", "")).lower() for feedback in feedback_items):
            strengths.append(
                "You included concrete details that make an example easier to remember."
            )

        for feedback in feedback_items:
            for suggestion in feedback.get("suggestions", []) or []:
                text = str(suggestion).strip()
                if text and text not in improvements:
                    improvements.append(text)

    if not strengths:
        strengths.append(
            "You completed practice and gave yourself material to review. "
            "That is the starting point for improvement."
        )
    if not improvements:
        improvements.append(
            "Practise one answer aloud and add a specific result where you can."
        )

    next_steps = [
        "Re-answer one question using Situation, Task, Action and Result.",
        "Prepare one example from study, work, volunteering, attachment or a personal project.",
        "Ask a trusted peer or mentor to listen and give one clear improvement.",
        "Write down the result of each example, using numbers only where they are honest.",
    ]

    return {
        "feedback_kind": "local_guidance",
        "source": "local_guidance",
        "summary": (
            f"You answered {len(responses)} "
            f"{'question' if len(responses) == 1 else 'questions'}. "
            "Review the feedback below and choose one improvement to practise next."
        ),
        "strengths": strengths[:5],
        "improvements": improvements[:5],
        "next_steps": next_steps,
        "questions_answered": len(responses),
        "disclaimer": (
            "This summary is practice guidance, not a score or a prediction of "
            "interview success."
        ),
    }
