"""Deterministic skill-assessment content and scoring.

The assessment bank is intentionally separate from Streamlit so it can be
reviewed, expanded, and tested without opening the interface. Knowledge
questions are marked deterministically. Practical exercises are not given a
numeric score; they are reviewed against published criteria and expected answer
elements.

Nothing in this module sends data to an AI provider or claims professional
certification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

CONTENT_VERSION = "2026-11-v1"

KNOWLEDGE = "knowledge"
PRACTICAL = "practical"
COMBINED = "combined"
ASSESSMENT_TYPES = (KNOWLEDGE, PRACTICAL, COMBINED)

TARGET_CAREER_AREA = "career_area"
TARGET_SKILL = "skill"
TARGET_TYPES = (TARGET_CAREER_AREA, TARGET_SKILL)

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUSES = (STATUS_IN_PROGRESS, STATUS_COMPLETED)

MAX_RESPONSE_CHARS = 5000
MIN_PRACTICAL_WORDS = 20

ASSESSMENT_TYPE_LABELS = {
    KNOWLEDGE: "Knowledge questions",
    PRACTICAL: "Practical exercises",
    COMBINED: "Knowledge and practical",
}

PROFICIENCY_BANDS = (
    {
        "min": 0,
        "max": 39,
        "label": "Needs development",
        "description": (
            "Build the basics with guided practice and a simple real example "
            "before relying on this skill at work."
        ),
    },
    {
        "min": 40,
        "max": 59,
        "label": "Developing",
        "description": (
            "You understand some core ideas. More practice and feedback will "
            "help you apply them consistently."
        ),
    },
    {
        "min": 60,
        "max": 79,
        "label": "Competent foundation",
        "description": (
            "You have a useful foundation. Keep practising realistic tasks and "
            "be ready to explain your choices."
        ),
    },
    {
        "min": 80,
        "max": 100,
        "label": "Strong foundation",
        "description": (
            "You show a strong foundation in this practice assessment. Continue "
            "with real examples and feedback from others."
        ),
    },
)

DISCLAIMER = (
    "This is an indicative practice result based on this assessment only. It is "
    "not a formal qualification, professional certification, or proof of "
    "workplace competence."
)


class SkillAssessmentError(Exception):
    """Base class for skill-assessment content and storage failures."""


class SkillAssessmentValidationError(SkillAssessmentError, ValueError):
    """Raised when assessment input fails validation."""


class SkillAssessmentContentError(SkillAssessmentError):
    """Raised when the assessment bank is internally inconsistent."""


@dataclass(frozen=True)
class AnswerOption:
    option_id: str
    text: str


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    label: str
    category: str
    description: str
    pathway_names: tuple[str, ...]
    development_actions: tuple[str, ...]


@dataclass(frozen=True)
class CareerArea:
    area_id: str
    label: str
    description: str
    skill_ids: tuple[str, ...]
    pathway_names: tuple[str, ...]


@dataclass(frozen=True)
class AssessmentQuestion:
    question_id: str
    skill_id: str
    skill_label: str
    category: str
    question_type: str
    difficulty: str
    question: str
    options: tuple[AnswerOption, ...] = ()
    correct_option_id: str | None = None
    explanation: str = ""
    marking_criteria: tuple[str, ...] = ()
    expected_elements: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssessmentPlan:
    assessment_key: str
    assessment_name: str
    target_type: str
    target_id: str
    target_label: str
    category: str
    description: str
    assessment_type: str
    content_version: str
    questions: tuple[AssessmentQuestion, ...]
    pathway_names: tuple[str, ...]

    @property
    def knowledge_questions(self) -> tuple[AssessmentQuestion, ...]:
        return tuple(
            question
            for question in self.questions
            if question.question_type == KNOWLEDGE
        )

    @property
    def practical_questions(self) -> tuple[AssessmentQuestion, ...]:
        return tuple(
            question
            for question in self.questions
            if question.question_type == PRACTICAL
        )

    @property
    def is_scored(self) -> bool:
        return bool(self.knowledge_questions)

    @property
    def method_label(self) -> str:
        return ASSESSMENT_TYPE_LABELS[self.assessment_type]

    @property
    def estimated_minutes(self) -> int:
        return max(3, len(self.questions) * 2)


SKILLS = (
    SkillDefinition(
        "computer_literacy",
        "Computer literacy",
        "Digital and technical",
        "Use a computer confidently for everyday work tasks, files, email, and safe sign-in habits.",
        ("ICT and digital services",),
        (
            "Practise creating, naming, saving, and finding files in a clear folder structure.",
            "Complete a short task that uses a browser, email, and a document safely.",
            "Explain how you would protect a shared computer and a work account.",
        ),
    ),
    SkillDefinition(
        "microsoft_office",
        "Microsoft Office",
        "Digital and technical",
        "Use word processing and spreadsheets to prepare clear documents, calculations, and simple reports.",
        ("Business, finance and administration", "ICT and digital services"),
        (
            "Build a one-page document with headings, a table, and a print preview.",
            "Create a simple spreadsheet with labels, formulas, and a checked total.",
            "Practise explaining what a formula does to someone who is new to spreadsheets.",
        ),
    ),
    SkillDefinition(
        "data_analysis",
        "Data analysis",
        "Digital and technical",
        "Organise simple data, check it, and turn it into clear findings for a decision.",
        ("ICT and digital services", "Business, finance and administration"),
        (
            "Clean a small dataset and calculate totals, averages, and simple percentages.",
            "Write three plain-language findings from a table and one recommendation.",
            "Check a chart or summary against the source data before sharing it.",
        ),
    ),
    SkillDefinition(
        "communication",
        "Communication",
        "Communication and people",
        "Explain information clearly, listen accurately, and write respectful messages for different audiences.",
        ("Health and community services", "Education and training", "Business, finance and administration"),
        (
            "Practise explaining a task in under two minutes to a peer.",
            "Rewrite a confusing or blunt message in clear, respectful language.",
            "Ask a follow-up question that checks whether your message was understood.",
        ),
    ),
    SkillDefinition(
        "customer_care",
        "Customer care",
        "Communication and people",
        "Respond calmly and fairly to customer needs, complaints, and follow-up requests.",
        ("Business, finance and administration", "Health and community services"),
        (
            "Role-play a calm response to an upset customer and agree the next step.",
            "Write a short complaint response with an apology, action, and follow-up.",
            "Review a customer interaction and note what you would do differently.",
        ),
    ),
    SkillDefinition(
        "teamwork",
        "Teamwork",
        "Communication and people",
        "Contribute to a shared goal, communicate progress, and support others without taking over.",
        ("Health and community services", "Education and training", "Trades and technical work"),
        (
            "Ask a teammate for feedback and agree one shared task.",
            "Prepare a short STAR example showing your role in a team result.",
            "Practise raising a concern in a way that focuses on the task, not the person.",
        ),
    ),
    SkillDefinition(
        "problem_solving",
        "Problem solving",
        "Work readiness",
        "Find the likely cause of a problem, test options, and take a practical next step.",
        ("ICT and digital services", "Trades and technical work", "Agriculture and environment"),
        (
            "Document a real problem using problem, options, action, and result.",
            "Complete a small troubleshooting exercise and record each step.",
            "Practise explaining why you chose one solution over another.",
        ),
    ),
    SkillDefinition(
        "time_management",
        "Time management",
        "Work readiness",
        "Plan priorities, estimate time, and communicate early when a deadline changes.",
        ("Business, finance and administration", "Education and training", "Trades and technical work"),
        (
            "Plan one week with priorities, time blocks, and a small buffer.",
            "Estimate a task, compare the estimate with the actual time, and adjust.",
            "Practise telling a supervisor about a delay before the deadline passes.",
        ),
    ),
    SkillDefinition(
        "critical_thinking",
        "Critical thinking",
        "Work readiness",
        "Ask useful questions, compare evidence, and avoid conclusions that the information does not support.",
        ("ICT and digital services", "Business, finance and administration", "Agriculture and environment"),
        (
            "Compare two options for a decision and list the evidence for each.",
            "Review a claim and identify what information is missing.",
            "Rewrite an overconfident statement so it matches the evidence.",
        ),
    ),
    SkillDefinition(
        "professional_ethics",
        "Professional ethics",
        "Work readiness",
        "Protect confidentiality, report mistakes, and follow fair workplace processes.",
        ("Health and community services", "Business, finance and administration", "Education and training"),
        (
            "Practise a confidential-record scenario and write the correct response.",
            "Review a workplace policy and explain two everyday examples.",
            "Prepare what you would say if asked to do something dishonest at work.",
        ),
    ),
    SkillDefinition(
        "bookkeeping",
        "Bookkeeping",
        "Practical and job-specific",
        "Record simple income and expenses accurately, keep evidence, and check totals.",
        ("Business, finance and administration",),
        (
            "Record ten sample transactions in a simple cash book.",
            "Reconcile a small cash record and explain any difference.",
            "Practise separating personal money from business money in a small enterprise.",
        ),
    ),
    SkillDefinition(
        "project_management",
        "Project management",
        "Practical and job-specific",
        "Plan a small piece of work, assign tasks, track progress, and review what happened.",
        ("Business, finance and administration", "Agriculture and environment", "Health and community services"),
        (
            "Plan a small event with tasks, owners, dates, and a simple budget.",
            "Track one project risk and write a short status update.",
            "Review a finished activity and record what you would change next time.",
        ),
    ),
)

SKILL_LOOKUP = {skill.skill_id: skill for skill in SKILLS}

CAREER_AREAS = (
    CareerArea(
        "digital_technical",
        "Digital and technical",
        "Confident use of computers, office tools, and simple data for everyday work.",
        ("computer_literacy", "microsoft_office", "data_analysis"),
        ("ICT and digital services", "Creative and media"),
    ),
    CareerArea(
        "communication_people",
        "Communication and people",
        "Clear communication, customer care, and teamwork with colleagues and the public.",
        ("communication", "customer_care", "teamwork"),
        ("Health and community services", "Education and training", "Business, finance and administration"),
    ),
    CareerArea(
        "work_readiness",
        "Work readiness",
        "Problem solving, planning, judgement, and professional behaviour in an entry-level role.",
        ("problem_solving", "time_management", "critical_thinking", "professional_ethics"),
        ("Business, finance and administration", "ICT and digital services", "Trades and technical work"),
    ),
    CareerArea(
        "practical_job_specific",
        "Practical and job-specific",
        "Practical record keeping and project coordination for small teams and businesses.",
        ("bookkeeping", "project_management"),
        ("Business, finance and administration", "Agriculture and environment", "Trades and technical work"),
    ),
)

CAREER_AREA_LOOKUP = {area.area_id: area for area in CAREER_AREAS}
ASSESSABLE_SKILL_LABELS = tuple(skill.label for skill in SKILLS)


def _options(*texts: str) -> tuple[AnswerOption, ...]:
    return tuple(
        AnswerOption(chr(65 + index), text)
        for index, text in enumerate(texts)
    )


def _knowledge(
    question_id: str,
    skill_id: str,
    question: str,
    options: tuple[AnswerOption, ...],
    correct_option_id: str,
    explanation: str,
    difficulty: str = "beginner",
) -> AssessmentQuestion:
    skill = SKILL_LOOKUP[skill_id]
    return AssessmentQuestion(
        question_id=question_id,
        skill_id=skill_id,
        skill_label=skill.label,
        category=skill.category,
        question_type=KNOWLEDGE,
        difficulty=difficulty,
        question=question,
        options=options,
        correct_option_id=correct_option_id,
        explanation=explanation,
    )


def _practical(
    question_id: str,
    skill_id: str,
    question: str,
    marking_criteria: tuple[str, ...],
    expected_elements: tuple[str, ...],
    difficulty: str = "beginner",
) -> AssessmentQuestion:
    skill = SKILL_LOOKUP[skill_id]
    return AssessmentQuestion(
        question_id=question_id,
        skill_id=skill_id,
        skill_label=skill.label,
        category=skill.category,
        question_type=PRACTICAL,
        difficulty=difficulty,
        question=question,
        marking_criteria=marking_criteria,
        expected_elements=expected_elements,
    )


QUESTION_BANK = (
    # Computer literacy
    _knowledge(
        "computer_literacy_k1",
        "computer_literacy",
        "A colleague asks you to save a report so another staff member can find it later. Which file name is most useful?",
        _options(
            "report",
            "final final new",
            "2026-11-16_customer_support_report",
            "IMG_2045",
        ),
        "C",
        "A descriptive name with a date and topic helps other people find and identify the file.",
    ),
    _knowledge(
        "computer_literacy_k2",
        "computer_literacy",
        "You receive an email attachment from an unknown sender. What is the safest first action?",
        _options(
            "Open it immediately to see what it is.",
            "Download it and run it.",
            "Do not open it; verify the sender through a trusted channel and report it if suspicious.",
            "Reply with your password so they can confirm who you are.",
        ),
        "C",
        "Unexpected attachments can contain malware. Verify the sender and follow your organisation's reporting process.",
    ),
    _knowledge(
        "computer_literacy_k3",
        "computer_literacy",
        "A shared workplace computer offers to remember your password. What should you do?",
        _options(
            "Accept so you can log in faster next time.",
            "Decline, sign out when finished, and keep your password private.",
            "Write the password on a note beside the screen.",
            "Share the password with a colleague so either of you can log in.",
        ),
        "B",
        "Shared devices should not store your password. Sign out and keep credentials private.",
    ),
    _knowledge(
        "computer_literacy_k4",
        "computer_literacy",
        "A shared folder contains hundreds of unsorted files. Which action best improves everyday computer use?",
        _options(
            "Delete all older files without checking.",
            "Create clearly named subfolders, move files into them, and agree a naming rule.",
            "Rename every file to 'document'.",
            "Email every file to yourself and delete the folder.",
        ),
        "B",
        "A simple, agreed folder and naming structure makes files easier to find and reduces duplicate work.",
    ),
    _practical(
        "computer_literacy_p1",
        "computer_literacy",
        "Write the steps you would follow to help a colleague who cannot find a document they saved last week. Include how you would search and how you would prevent the problem next time.",
        (
            "Asks where and when the document was saved.",
            "Searches by name, date, file type, and recent files in a sensible order.",
            "Checks the recycle bin or trash before assuming the file is lost.",
            "Suggests a clear folder and naming habit to prevent a repeat.",
            "Communicates calmly and confirms the colleague can find the file.",
        ),
        (
            "A short set of search steps.",
            "A check of likely locations.",
            "A prevention step such as a naming or folder rule.",
        ),
    ),
    # Microsoft Office
    _knowledge(
        "microsoft_office_k1",
        "microsoft_office",
        "In a spreadsheet, you need to add the values in cells B2 to B10. Which formula is correct?",
        _options("=SUM(B2:B10)", "SUM(B2-B10)", "=B2+B10", "=ADD(B2:B10)"),
        "A",
        "=SUM(B2:B10) adds the whole range. The other options either use the wrong range or invalid syntax.",
    ),
    _knowledge(
        "microsoft_office_k2",
        "microsoft_office",
        "You are writing a formal letter in a word processor. Which feature best keeps headings consistent?",
        _options(
            "Manually bolding each heading.",
            "Using the built-in heading styles.",
            "Changing the font size randomly.",
            "Adding extra blank lines before each heading.",
        ),
        "B",
        "Built-in heading styles keep formatting consistent and make the document easier to edit and navigate.",
    ),
    _knowledge(
        "microsoft_office_k3",
        "microsoft_office",
        "A table in a report runs past the page edge when printed. What is the best first step?",
        _options(
            "Delete the table.",
            "Adjust column widths or page layout and use print preview.",
            "Reduce the font to an unreadable size.",
            "Ignore it and print anyway.",
        ),
        "B",
        "Check print layout and column widths first. Print preview shows what the reader will actually receive.",
    ),
    _knowledge(
        "microsoft_office_k4",
        "microsoft_office",
        "You need to share a spreadsheet with a colleague but protect the original from accidental changes. What should you do?",
        _options(
            "Email the original and ask them not to edit it.",
            "Share a copy or use view-only permission where available.",
            "Delete the original after sending it.",
            "Rename the file and hope for the best.",
        ),
        "B",
        "A copy or view-only access reduces the risk of accidental changes to the original record.",
    ),
    _practical(
        "microsoft_office_p1",
        "microsoft_office",
        "Describe how you would create a simple monthly expenses spreadsheet for a small shop. Include the columns, one formula, and how you would check the totals.",
        (
            "Lists useful columns such as date, item, category, amount, and payment method.",
            "Includes at least one correct formula, such as a SUM formula.",
            "Explains how receipts or source records will be checked.",
            "Uses clear labels and a readable layout.",
            "Mentions checking the total against the underlying entries.",
        ),
        (
            "A simple table structure.",
            "One appropriate formula.",
            "A checking step.",
        ),
    ),
    # Data analysis
    _knowledge(
        "data_analysis_k1",
        "data_analysis",
        "A table shows daily sales for a week. Which summary best answers 'Which day had the highest sales?'",
        _options(
            "The total of all seven days.",
            "The day with the highest sales value.",
            "The average of the first two days.",
            "The number of rows in the table.",
        ),
        "B",
        "The question asks for the highest individual day, so compare the daily values and identify the maximum.",
    ),
    _knowledge(
        "data_analysis_k2",
        "data_analysis",
        "Two entries have the same customer name but different phone numbers. What is the best next step?",
        _options(
            "Delete both entries.",
            "Assume the longer number is correct.",
            "Check the source records and confirm which entry is accurate.",
            "Average the two phone numbers.",
        ),
        "C",
        "Data quality requires checking the source rather than guessing. Phone numbers cannot be averaged.",
    ),
    _knowledge(
        "data_analysis_k3",
        "data_analysis",
        "A report says 'sales increased'. Which additional information makes the claim most useful?",
        _options(
            "A larger font.",
            "The time period, the amount of increase, and the comparison baseline.",
            "A different colour.",
            "The manager's name.",
        ),
        "B",
        "A useful comparison states what changed, by how much, and compared with what period or group.",
    ),
    _knowledge(
        "data_analysis_k4",
        "data_analysis",
        "You are asked to summarise a survey of 20 customers. Which approach is most appropriate?",
        _options(
            "Count responses and calculate simple percentages.",
            "Invent answers for people who did not respond.",
            "Report only the answers you personally like.",
            "Use a complex model without checking the data.",
        ),
        "A",
        "For a small survey, transparent counts and percentages are appropriate. Do not invent missing data.",
    ),
    _practical(
        "data_analysis_p1",
        "data_analysis",
        "You have a list of 30 customer complaints with date, issue, and branch. Describe how you would analyse it and present three practical findings to a manager.",
        (
            "Checks the list for missing or inconsistent entries.",
            "Groups complaints by issue, branch, or time period.",
            "Uses counts or percentages rather than vague impressions.",
            "Chooses three clear findings that answer a practical question.",
            "Suggests a next step and uses plain language.",
        ),
        (
            "A cleaning step.",
            "A grouping or counting method.",
            "Three findings and a recommendation.",
        ),
    ),
    # Communication
    _knowledge(
        "communication_k1",
        "communication",
        "A customer sends a frustrating message with unclear details. What is the best first response?",
        _options(
            "Reply with a long list of rules.",
            "Acknowledge the concern and ask one or two calm clarifying questions.",
            "Ignore the message until the customer calms down.",
            "Blame another department.",
        ),
        "B",
        "Acknowledging the concern and asking focused questions shows respect and helps you get the facts.",
    ),
    _knowledge(
        "communication_k2",
        "communication",
        "You need to explain a delay to a client. Which message is clearest?",
        _options(
            "It is delayed.",
            "Your order is delayed because the supplier is late; we expect it on Friday and will update you on Thursday.",
            "Not our fault.",
            "Please wait.",
        ),
        "B",
        "The clear message gives the reason, the new expectation, and the next update without blaming anyone.",
    ),
    _knowledge(
        "communication_k3",
        "communication",
        "In a team meeting, a colleague's idea is unclear. What is the most professional response?",
        _options(
            "Say the idea makes no sense.",
            "Ask them to explain the main point and give an example.",
            "Talk over them.",
            "Ignore them and move on.",
        ),
        "B",
        "A specific, respectful question helps the speaker clarify without embarrassing them.",
    ),
    _knowledge(
        "communication_k4",
        "communication",
        "You must write an update for a busy manager. What should you put first?",
        _options(
            "A long history of everything you did.",
            "The main point and any action or decision needed.",
            "Your personal opinion about the team.",
            "Unrelated details to fill the message.",
        ),
        "B",
        "Busy readers need the headline and the required action first. Supporting detail can follow.",
    ),
    _practical(
        "communication_p1",
        "communication",
        "Write a short message to a customer explaining that a repair will take three more days. Include an apology, the reason, the new date, and the next update.",
        (
            "Uses a clear greeting and a courteous tone.",
            "Acknowledges the inconvenience without blaming others.",
            "Gives the new completion date and a reason in plain language.",
            "States when the customer will hear from you again.",
            "Avoids overpromising or inventing facts.",
        ),
        (
            "An apology or acknowledgement.",
            "The new date and reason.",
            "A clear next update.",
        ),
    ),
    # Customer care
    _knowledge(
        "customer_care_k1",
        "customer_care",
        "A customer arrives angry about a delayed order. What should you do first?",
        _options(
            "Defend the company immediately.",
            "Listen without interrupting and acknowledge the concern.",
            "Ask them to lower their voice before you help.",
            "Transfer them without explaining why.",
        ),
        "B",
        "Listening and acknowledging the concern helps the customer feel heard and gives you the facts you need.",
    ),
    _knowledge(
        "customer_care_k2",
        "customer_care",
        "You cannot solve a customer's issue yourself. What is the best next step?",
        _options(
            "Promise something you cannot deliver.",
            "Explain what you can do and refer them to the right person or process.",
            "Ignore the issue until they leave.",
            "Tell them to come back another day without a reason.",
        ),
        "B",
        "Be honest about your limits, explain the handover, and help the customer reach someone who can act.",
    ),
    _knowledge(
        "customer_care_k3",
        "customer_care",
        "A customer gives incomplete details about a complaint. What should you do?",
        _options(
            "Guess the missing details.",
            "Ask specific questions and confirm what you heard.",
            "Close the case immediately.",
            "Argue about who is right.",
        ),
        "B",
        "Specific questions and a summary check reduce misunderstanding and show that you are taking the complaint seriously.",
    ),
    _knowledge(
        "customer_care_k4",
        "customer_care",
        "Which action best protects customer confidentiality at a busy service desk?",
        _options(
            "Discuss cases loudly with colleagues.",
            "Leave customer records on the counter.",
            "Check identity before sharing details and keep records secure.",
            "Share screenshots with friends.",
        ),
        "C",
        "Confirm identity and keep records secure. Customer information should only be shared with people who need it.",
    ),
    _practical(
        "customer_care_p1",
        "customer_care",
        "A customer says they were charged twice for the same service. Write how you would handle the conversation from greeting to follow-up.",
        (
            "Greets the customer and listens without interrupting.",
            "Confirms identity and the relevant transaction details.",
            "Acknowledges the problem and explains the next step or timeline.",
            "Records the case accurately and keeps the customer informed.",
            "Follows up and stays calm and professional throughout.",
        ),
        (
            "A calm greeting and acknowledgement.",
            "Identity and transaction checks.",
            "A clear action, timeline, and follow-up.",
        ),
    ),
    # Teamwork
    _knowledge(
        "teamwork_k1",
        "teamwork",
        "A team member is quiet in meetings but does good work. What is the best way to include them?",
        _options(
            "Ignore them because they do not speak.",
            "Ask for their view directly and allow time to respond.",
            "Speak for them without checking.",
            "Assign all the work to them.",
        ),
        "B",
        "Directly inviting a quieter teammate and allowing time helps the team benefit from their knowledge.",
    ),
    _knowledge(
        "teamwork_k2",
        "teamwork",
        "Two teammates disagree about how to complete a task. What should you do?",
        _options(
            "Take sides immediately.",
            "Clarify the shared goal and compare the options using evidence.",
            "Avoid the topic until the deadline.",
            "Escalate without trying to understand the issue.",
        ),
        "B",
        "Focus on the shared goal and evidence rather than personalities. That makes a practical decision easier.",
    ),
    _knowledge(
        "teamwork_k3",
        "teamwork",
        "You finish your part of a team task early. What is the most useful action?",
        _options(
            "Leave without telling anyone.",
            "Share your progress and ask whether others need help.",
            "Start an unrelated project without checking priorities.",
            "Hide your work so you are not asked to do more.",
        ),
        "B",
        "Communicating progress and offering help supports the team goal and reduces last-minute surprises.",
    ),
    _knowledge(
        "teamwork_k4",
        "teamwork",
        "A teammate makes a mistake that affects the group. What is the most professional response?",
        _options(
            "Embarrass them in a public meeting.",
            "Focus on fixing the issue and discuss how to prevent a repeat.",
            "Ignore the mistake completely.",
            "Refuse to work with them again.",
        ),
        "B",
        "Address the work problem, protect the person's dignity, and agree a prevention step.",
    ),
    _practical(
        "teamwork_p1",
        "teamwork",
        "Describe a time you worked in a team. Explain your role, how you communicated, a challenge, and the result.",
        (
            "Describes a specific team situation and your own role.",
            "Shows how you communicated or coordinated with others.",
            "Names a real challenge or disagreement.",
            "Explains your contribution and the result.",
            "Reflects on what you learned or would do differently.",
        ),
        (
            "A concrete example.",
            "Your personal contribution.",
            "A result and a learning point.",
        ),
    ),
    # Problem solving
    _knowledge(
        "problem_solving_k1",
        "problem_solving",
        "A printer stops working before an important meeting. What is the best first step?",
        _options(
            "Replace the printer immediately.",
            "Check obvious causes such as power, paper, connections, and error messages.",
            "Ignore it and hope someone else fixes it.",
            "Blame the last person who used it.",
        ),
        "B",
        "Start with quick, low-cost checks. That usually identifies simple causes before replacing equipment.",
    ),
    _knowledge(
        "problem_solving_k2",
        "problem_solving",
        "You have three possible causes for a recurring error. What is the most useful next step?",
        _options(
            "Choose one randomly.",
            "Test one likely cause at a time and record what happens.",
            "Change everything at once.",
            "Stop investigating because the error is intermittent.",
        ),
        "B",
        "Testing one variable at a time helps you learn which cause actually matters.",
    ),
    _knowledge(
        "problem_solving_k3",
        "problem_solving",
        "A process keeps causing delays. Which question best helps find the root cause?",
        _options(
            "Who can we blame?",
            "What happens immediately before the delay, and why?",
            "Can we hide the delay from customers?",
            "Who has the longest lunch break?",
        ),
        "B",
        "Root-cause questions focus on the process and the conditions that create the delay.",
    ),
    _knowledge(
        "problem_solving_k4",
        "problem_solving",
        "After fixing a problem, what should you do to help the team next time?",
        _options(
            "Keep the solution secret.",
            "Document the cause and the fix briefly where the team can find it.",
            "Delete all evidence of the problem.",
            "Claim the fix was easy and move on.",
        ),
        "B",
        "A short record helps the team recognise the same issue and apply the fix faster next time.",
    ),
    _practical(
        "problem_solving_p1",
        "problem_solving",
        "Describe a real or realistic problem you solved. Explain the situation, what you checked, the action you took, and the result.",
        (
            "Clearly states the problem and its impact.",
            "Shows what you checked or which options you considered.",
            "Explains the action you personally took.",
            "Gives a result or observable outcome.",
            "States a learning point or prevention step.",
        ),
        (
            "A specific problem.",
            "A logical investigation.",
            "An action and result.",
        ),
    ),
    # Time management
    _knowledge(
        "time_management_k1",
        "time_management",
        "You have four tasks due today. Which approach is best?",
        _options(
            "Do the easiest first regardless of deadline.",
            "List deadlines and importance, then plan the order.",
            "Wait until someone reminds you.",
            "Start all four at the same time.",
        ),
        "B",
        "A short priority list based on deadline and impact helps you spend time where it matters most.",
    ),
    _knowledge(
        "time_management_k2",
        "time_management",
        "A task will take longer than expected. What should you do?",
        _options(
            "Hide the delay.",
            "Tell the relevant person early and agree a revised plan.",
            "Stop working on it without explanation.",
            "Blame a colleague.",
        ),
        "B",
        "Early communication gives others time to adjust and protects trust.",
    ),
    _knowledge(
        "time_management_k3",
        "time_management",
        "Which habit best reduces last-minute rushing?",
        _options(
            "Checking messages constantly.",
            "Breaking work into steps with short, realistic checkpoints.",
            "Saying yes to every request.",
            "Keeping no notes or calendar.",
        ),
        "B",
        "Small checkpoints make progress visible and reduce the chance of discovering a problem at the deadline.",
    ),
    _knowledge(
        "time_management_k4",
        "time_management",
        "You are constantly interrupted during focused work. What is a practical response?",
        _options(
            "Agree quiet periods or a signal with colleagues and check messages at set times.",
            "Work faster and skip breaks.",
            "Ignore every request permanently.",
            "Stop planning because plans never work.",
        ),
        "A",
        "Agreeing boundaries and batching communication is more realistic than trying to work faster all day.",
    ),
    _practical(
        "time_management_p1",
        "time_management",
        "Plan your next study or work week. List five tasks, estimate the time, set priorities, and explain how you will handle an unexpected urgent task.",
        (
            "Lists five specific tasks.",
            "Gives realistic time estimates.",
            "Explains the priority order using deadlines or impact.",
            "Leaves a buffer or identifies what can move.",
            "Describes how they would communicate or adjust for an urgent task.",
        ),
        (
            "A task list with estimates.",
            "A clear priority rule.",
            "A realistic response to an urgent change.",
        ),
    ),
    # Critical thinking
    _knowledge(
        "critical_thinking_k1",
        "critical_thinking",
        "A social media post claims a training course guarantees a job. What should you check first?",
        _options(
            "The number of likes.",
            "The source, evidence, and whether the claim is realistic.",
            "The colour of the post.",
            "Whether a friend shared it.",
        ),
        "B",
        "Check who is making the claim, what evidence supports it, and whether the promise is plausible.",
    ),
    _knowledge(
        "critical_thinking_k2",
        "critical_thinking",
        "You need to choose between two suppliers. Which approach is most reliable?",
        _options(
            "Choose the cheapest without checking anything else.",
            "Compare price, quality, delivery, and references.",
            "Ask only one colleague and stop.",
            "Flip a coin.",
        ),
        "B",
        "A decision based on several relevant criteria is stronger than a single factor or a guess.",
    ),
    _knowledge(
        "critical_thinking_k3",
        "critical_thinking",
        "A report gives a percentage but no sample size. Why does this matter?",
        _options(
            "Percentages are always wrong.",
            "A small sample may make the result less reliable.",
            "Sample size only affects the colours in a chart.",
            "It does not matter at all.",
        ),
        "B",
        "The sample size affects how much confidence you can place in a percentage.",
    ),
    _knowledge(
        "critical_thinking_k4",
        "critical_thinking",
        "A recommendation conflicts with your experience. What is the best response?",
        _options(
            "Reject it immediately.",
            "Examine the evidence and ask what context it applies to.",
            "Share it without checking.",
            "Ignore all data from then on.",
        ),
        "B",
        "Consider the evidence and context before accepting or rejecting a claim.",
    ),
    _practical(
        "critical_thinking_p1",
        "critical_thinking",
        "A manager says 'Customers prefer phone calls because our survey of five customers said so.' Write a short response explaining what you would check and what you would recommend.",
        (
            "Identifies the small sample size as a limitation.",
            "Asks whether the five customers represent the wider customer group.",
            "Considers other contact channels and customer preferences.",
            "Recommends gathering broader evidence before deciding.",
            "Uses a respectful, evidence-focused tone.",
        ),
        (
            "A clear limitation.",
            "A broader evidence suggestion.",
            "A respectful recommendation.",
        ),
    ),
    # Professional ethics
    _knowledge(
        "professional_ethics_k1",
        "professional_ethics",
        "A friend asks you to share a customer's phone number from work. What should you do?",
        _options(
            "Share it because they are a friend.",
            "Refuse and explain that customer information is confidential.",
            "Share only the last few digits.",
            "Post it in a group chat.",
        ),
        "B",
        "Customer information should only be used for legitimate work purposes. Friendship does not create an exception.",
    ),
    _knowledge(
        "professional_ethics_k2",
        "professional_ethics",
        "You make a mistake that affects a client. What is the most ethical response?",
        _options(
            "Hide it and hope nobody notices.",
            "Report it promptly and help correct it.",
            "Blame a colleague.",
            "Delete the record.",
        ),
        "B",
        "Prompt reporting and correction protects the client and the organisation, and is more ethical than concealment.",
    ),
    _knowledge(
        "professional_ethics_k3",
        "professional_ethics",
        "You are offered a small gift to move a client's request ahead of others. What should you do?",
        _options(
            "Accept it and skip the queue.",
            "Decline and follow the approved process.",
            "Accept it but tell nobody.",
            "Ask for a larger gift.",
        ),
        "B",
        "Fair processes should not be influenced by gifts. Decline politely and follow the approved procedure.",
    ),
    _knowledge(
        "professional_ethics_k4",
        "professional_ethics",
        "Which action best protects confidential work information?",
        _options(
            "Using a shared password.",
            "Locking your screen and storing files securely.",
            "Emailing files to a personal account.",
            "Leaving notes on a desk.",
        ),
        "B",
        "Locking screens and using secure storage reduces accidental or unauthorised access.",
    ),
    _practical(
        "professional_ethics_p1",
        "professional_ethics",
        "You see a colleague sharing confidential client information in a public group chat. Describe what you would do and why.",
        (
            "Does not repeat or spread the confidential information.",
            "Raises the concern privately through the appropriate person or process.",
            "Refers to the relevant policy or confidentiality principle.",
            "Focuses on protecting the client and correcting the situation.",
            "Avoids public shaming and documents the concern appropriately.",
        ),
        (
            "A private reporting step.",
            "A confidentiality reason.",
            "A protective follow-up.",
        ),
    ),
    # Bookkeeping
    _knowledge(
        "bookkeeping_k1",
        "bookkeeping",
        "A shop receives KSh 5,000 cash from a customer. Which entry is correct in a simple cash book?",
        _options(
            "Record it as an expense.",
            "Record it as cash received or income.",
            "Ignore it until the end of the month.",
            "Record it twice.",
        ),
        "B",
        "Cash received from a customer increases the cash balance and is recorded as income or cash received.",
    ),
    _knowledge(
        "bookkeeping_k2",
        "bookkeeping",
        "You are entering receipts and one is missing. What should you do?",
        _options(
            "Invent an amount.",
            "Leave a clear note and follow up for the receipt.",
            "Delete the transaction.",
            "Ask a colleague to guess the amount.",
        ),
        "B",
        "Record the known transaction and clearly mark the missing evidence for follow-up. Do not invent amounts.",
    ),
    _knowledge(
        "bookkeeping_k3",
        "bookkeeping",
        "Which action best reduces errors in a cash record?",
        _options(
            "Recording transactions later from memory.",
            "Recording each transaction promptly and checking totals.",
            "Keeping loose receipts in a pocket.",
            "Changing the format every day.",
        ),
        "B",
        "Prompt recording and regular total checks catch mistakes while the details are still fresh.",
    ),
    _knowledge(
        "bookkeeping_k4",
        "bookkeeping",
        "A cash book total does not match the money counted. What is the best first step?",
        _options(
            "Change the total to match the money.",
            "Recount the money and compare the entries and receipts.",
            "Ignore the difference.",
            "Borrow money to cover the gap.",
        ),
        "B",
        "Recount and trace the entries to find the cause. Do not force the total to match.",
    ),
    _practical(
        "bookkeeping_p1",
        "bookkeeping",
        "Create a simple record for five transactions: opening cash KSh 2,000, sale KSh 1,500, transport KSh 300, sale KSh 800, and airtime KSh 200. Show the running balance and explain how you checked it.",
        (
            "Records each transaction with a clear description and amount.",
            "Uses the correct direction for cash in and cash out.",
            "Calculates a running balance accurately.",
            "Checks the final balance against the individual entries.",
            "Mentions receipts or evidence and avoids invented figures.",
        ),
        (
            "Five correctly classified entries.",
            "A correct running balance.",
            "A checking step.",
        ),
    ),
    # Project management
    _knowledge(
        "project_management_k1",
        "project_management",
        "You are planning a small community clean-up. What should you define first?",
        _options(
            "The colour of the banner.",
            "The goal, scope, date, people, and budget.",
            "The food menu.",
            "The social media hashtag.",
        ),
        "B",
        "A clear goal, scope, date, people, and budget give the project a practical starting point.",
    ),
    _knowledge(
        "project_management_k2",
        "project_management",
        "A project task is running late. What is the best next step?",
        _options(
            "Ignore it and hope it catches up.",
            "Assess the impact and update the plan with the team.",
            "Cancel the whole project.",
            "Blame a volunteer.",
        ),
        "B",
        "Check the impact, adjust the plan, and communicate with the people affected.",
    ),
    _knowledge(
        "project_management_k3",
        "project_management",
        "Which tool best helps track tasks, owners, and deadlines for a small project?",
        _options(
            "A simple task list or board with dates and owners.",
            "A list of names without tasks.",
            "A single photograph.",
            "Memory alone.",
        ),
        "A",
        "A simple visible list with tasks, owners, and dates is enough for many small projects.",
    ),
    _knowledge(
        "project_management_k4",
        "project_management",
        "At the end of a project, what is the most useful action?",
        _options(
            "Delete all notes.",
            "Review what worked and what to change next time.",
            "Celebrate and skip the review.",
            "Blame delays on others.",
        ),
        "B",
        "A short review captures lessons and improves the next project.",
    ),
    _practical(
        "project_management_p1",
        "project_management",
        "Plan a one-day community clean-up for 20 volunteers. List the main tasks, owners, and a simple timeline, and identify one risk with a response.",
        (
            "States a clear goal and scope for the day.",
            "Lists practical tasks with owners.",
            "Provides a simple timeline with key times.",
            "Identifies a realistic risk and a response.",
            "Mentions communication, resources, or a short review.",
        ),
        (
            "Tasks and owners.",
            "A timeline.",
            "A risk and response.",
        ),
    ),
)

QUESTION_LOOKUP = {question.question_id: question for question in QUESTION_BANK}


def get_skill(skill_id: str) -> SkillDefinition | None:
    return SKILL_LOOKUP.get(str(skill_id or "").strip())


def get_career_area(area_id: str) -> CareerArea | None:
    return CAREER_AREA_LOOKUP.get(str(area_id or "").strip())


def get_question(question_id: str) -> AssessmentQuestion | None:
    return QUESTION_LOOKUP.get(str(question_id or "").strip())


def build_plan(
    target_type: str,
    target_id: str,
    assessment_type: str,
) -> AssessmentPlan:
    """Build a deterministic assessment plan for a target and method."""

    target_type = str(target_type or "").strip()
    target_id = str(target_id or "").strip()
    assessment_type = str(assessment_type or "").strip()

    if assessment_type not in ASSESSMENT_TYPES:
        raise SkillAssessmentValidationError("Choose a valid assessment method.")
    if target_type == TARGET_CAREER_AREA:
        area = get_career_area(target_id)
        if area is None:
            raise SkillAssessmentValidationError("Choose a valid career area.")
        skill_ids = area.skill_ids
        target_label = area.label
        assessment_name = f"{area.label} career-area assessment"
        category = area.label
        description = area.description
        pathway_names = area.pathway_names
    elif target_type == TARGET_SKILL:
        skill = get_skill(target_id)
        if skill is None:
            raise SkillAssessmentValidationError("Choose a valid skill.")
        skill_ids = (skill.skill_id,)
        target_label = skill.label
        assessment_name = f"{skill.label} assessment"
        category = skill.category
        description = skill.description
        pathway_names = skill.pathway_names
    else:
        raise SkillAssessmentValidationError("Choose a valid assessment target.")

    selected = [
        question
        for question in QUESTION_BANK
        if question.skill_id in skill_ids
    ]
    knowledge = [
        question for question in selected if question.question_type == KNOWLEDGE
    ]
    practical = [
        question for question in selected if question.question_type == PRACTICAL
    ]

    if assessment_type == KNOWLEDGE:
        questions = knowledge
    elif assessment_type == PRACTICAL:
        questions = practical
    else:
        questions = knowledge + practical

    if not questions:
        raise SkillAssessmentValidationError(
            "No assessment questions are available for that choice."
        )

    return AssessmentPlan(
        assessment_key=f"{target_type}:{target_id}",
        assessment_name=assessment_name,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        category=category,
        description=description,
        assessment_type=assessment_type,
        content_version=CONTENT_VERSION,
        questions=tuple(questions),
        pathway_names=tuple(pathway_names),
    )


def score_knowledge_question(
    question: AssessmentQuestion,
    selected_option_id: str,
) -> dict[str, Any]:
    """Mark one multiple-choice question deterministically."""

    if question.question_type != KNOWLEDGE:
        raise SkillAssessmentValidationError(
            "Only knowledge questions can be marked automatically."
        )

    selected = str(selected_option_id or "").strip()
    option_lookup = {option.option_id: option for option in question.options}
    if selected not in option_lookup:
        raise SkillAssessmentValidationError("Choose one answer before submitting.")

    correct = question.correct_option_id
    if correct not in option_lookup:
        raise SkillAssessmentContentError(
            "The assessment question has an invalid correct answer."
        )

    is_correct = selected == correct
    return {
        "is_correct": is_correct,
        "score_awarded": 1.0 if is_correct else 0.0,
        "feedback": {
            "question_id": question.question_id,
            "skill_id": question.skill_id,
            "skill_label": question.skill_label,
            "question_type": KNOWLEDGE,
            "selected_option_id": selected,
            "selected_option_text": option_lookup[selected].text,
            "correct_option_id": correct,
            "correct_option_text": option_lookup[correct].text,
            "explanation": question.explanation,
            "message": (
                "Correct. Review the explanation to make the reasoning explicit."
                if is_correct
                else "Not correct. Read the correct answer and explanation, then "
                "think about how you would apply it at work."
            ),
        },
    }


def evaluate_practical_response(
    question: AssessmentQuestion,
    response_text: str,
) -> dict[str, Any]:
    """Validate a practical response without pretending to score it objectively."""

    if question.question_type != PRACTICAL:
        raise SkillAssessmentValidationError(
            "This is not a practical exercise."
        )

    text = str(response_text or "").strip()
    if not text:
        raise SkillAssessmentValidationError(
            "Write a response before submitting the exercise."
        )
    if len(text) > MAX_RESPONSE_CHARS:
        raise SkillAssessmentValidationError(
            f"Keep each response under {MAX_RESPONSE_CHARS} characters."
        )

    word_count = len(text.split())
    if word_count < MIN_PRACTICAL_WORDS:
        raise SkillAssessmentValidationError(
            f"Write at least {MIN_PRACTICAL_WORDS} words so the response can be "
            "reviewed against the criteria."
        )

    return {
        "is_correct": None,
        "score_awarded": None,
        "feedback": {
            "question_id": question.question_id,
            "skill_id": question.skill_id,
            "skill_label": question.skill_label,
            "question_type": PRACTICAL,
            "marking_criteria": list(question.marking_criteria),
            "expected_elements": list(question.expected_elements),
            "word_count": word_count,
            "message": (
                "This practical response is not automatically scored. Review it "
                "against the marking criteria and expected elements. It is "
                "practice evidence, not a professional certification."
            ),
        },
    }


def score_to_percentage(correct: int, total: int) -> int | None:
    if total <= 0:
        return None
    bounded_correct = max(0, min(int(correct), int(total)))
    return int(round(100 * bounded_correct / int(total)))


def proficiency_band(score: int | float | None) -> dict[str, Any] | None:
    """Return the indicative band for a 0-100 score."""

    if score is None:
        return None

    try:
        value = int(round(float(score)))
    except (TypeError, ValueError):
        return None
    value = max(0, min(100, value))

    for band in PROFICIENCY_BANDS:
        if band["min"] <= value <= band["max"]:
            return dict(band)
    return None


def _unique(values: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text.casefold() not in seen:
            cleaned.append(text)
            seen.add(text.casefold())
    return cleaned


def build_result_summary(
    assessment: Mapping[str, Any],
    questions: Sequence[AssessmentQuestion],
    responses: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic, non-AI result summary from saved responses."""

    question_lookup = {
        question.question_id: question for question in questions
    }
    response_list = list(responses)
    response_lookup = {
        str(response.get("question_id")): response
        for response in response_list
    }

    knowledge_questions = [
        question
        for question in questions
        if question.question_type == KNOWLEDGE
    ]
    practical_questions = [
        question
        for question in questions
        if question.question_type == PRACTICAL
    ]

    knowledge_responses = [
        response
        for response in response_list
        if str(response.get("question_type")) == KNOWLEDGE
    ]
    practical_responses = [
        response
        for response in response_list
        if str(response.get("question_type")) == PRACTICAL
    ]

    knowledge_total = len(knowledge_questions) or len(knowledge_responses)
    knowledge_answered = len(knowledge_responses)
    knowledge_correct = sum(
        1
        for response in knowledge_responses
        if response.get("is_correct") is True
    )

    score_percent = None
    if (
        knowledge_total > 0
        and knowledge_answered == knowledge_total
        and str(assessment.get("status")) == STATUS_COMPLETED
    ):
        score_percent = score_to_percentage(knowledge_correct, knowledge_total)

    band = proficiency_band(score_percent)

    skill_labels: dict[str, str] = {}
    skill_question_ids: dict[str, list[str]] = {}
    for question in questions:
        skill_labels[question.skill_id] = question.skill_label
        skill_question_ids.setdefault(question.skill_id, []).append(
            question.question_id
        )

    for response in knowledge_responses:
        feedback = response.get("feedback")
        feedback = feedback if isinstance(feedback, Mapping) else {}
        skill_id = str(feedback.get("skill_id") or "").strip()
        skill_label = str(feedback.get("skill_label") or "").strip()
        if skill_id and skill_label:
            skill_labels[skill_id] = skill_label

    strong_areas: list[str] = []
    improve_areas: list[str] = []
    for skill_id, question_ids in skill_question_ids.items():
        answered = [
            response_lookup[question_id]
            for question_id in question_ids
            if question_id in response_lookup
        ]
        if not answered or len(answered) < len(question_ids):
            continue
        if all(response.get("is_correct") is True for response in answered):
            strong_areas.append(skill_labels.get(skill_id, skill_id))
        elif any(response.get("is_correct") is False for response in answered):
            improve_areas.append(skill_labels.get(skill_id, skill_id))

    incorrect_answers: list[dict[str, Any]] = []
    for response in knowledge_responses:
        if response.get("is_correct") is not False:
            continue
        feedback = response.get("feedback")
        feedback = feedback if isinstance(feedback, Mapping) else {}
        question_id = str(response.get("question_id") or "")
        question = question_lookup.get(question_id)
        incorrect_answers.append(
            {
                "question_id": question_id,
                "question": str(
                    response.get("question_text")
                    or (question.question if question else "")
                ),
                "selected_answer": str(
                    feedback.get("selected_option_text")
                    or response.get("selected_answer")
                    or ""
                ),
                "correct_answer": str(
                    feedback.get("correct_option_text")
                    or (question.correct_option_id if question else "")
                ),
                "explanation": str(
                    feedback.get("explanation")
                    or (question.explanation if question else "")
                ),
                "skill_label": str(
                    feedback.get("skill_label")
                    or (question.skill_label if question else "")
                ),
            }
        )

    practical_review: list[dict[str, Any]] = []
    for response in practical_responses:
        feedback = response.get("feedback")
        feedback = feedback if isinstance(feedback, Mapping) else {}
        question_id = str(response.get("question_id") or "")
        question = question_lookup.get(question_id)
        practical_review.append(
            {
                "question_id": question_id,
                "question": str(
                    response.get("question_text")
                    or (question.question if question else "")
                ),
                "response": str(response.get("response_text") or ""),
                "marking_criteria": list(
                    feedback.get("marking_criteria")
                    or (question.marking_criteria if question else ())
                ),
                "expected_elements": list(
                    feedback.get("expected_elements")
                    or (question.expected_elements if question else ())
                ),
                "word_count": int(feedback.get("word_count") or 0),
                "scored": False,
            }
        )

    assessed_skill_ids = _unique(
        [
            question.skill_id
            for question in questions
        ]
        + [
            str((response.get("feedback") or {}).get("skill_id") or "")
            for response in response_list
            if isinstance(response.get("feedback"), Mapping)
        ]
    )

    next_steps: list[str] = []
    for skill_id in assessed_skill_ids:
        skill = get_skill(skill_id)
        if skill:
            next_steps.extend(skill.development_actions)
    next_steps = _unique(next_steps)[:6]
    if not next_steps:
        next_steps = [
            "Choose one small real task and practise it until you can explain "
            "your process clearly.",
            "Ask a peer or supervisor for feedback and record one improvement.",
        ]

    pathway_names = _unique(
        pathway
        for skill_id in assessed_skill_ids
        for pathway in (get_skill(skill_id).pathway_names if get_skill(skill_id) else ())
    )[:4]

    skills_assessed = _unique(
        skill_labels.get(skill_id, skill_id)
        for skill_id in assessed_skill_ids
    )

    if score_percent is not None:
        message = (
            f"You answered {knowledge_correct} of {knowledge_total} knowledge "
            f"questions correctly ({score_percent}%)."
        )
    elif practical_responses:
        message = (
            "This assessment includes practical exercises. They are not "
            "automatically scored; review them against the marking criteria."
        )
    else:
        message = "No automatically marked knowledge questions were completed."

    return {
        "assessment_name": str(assessment.get("assessment_name") or ""),
        "assessment_type": str(assessment.get("assessment_type") or ""),
        "method_label": ASSESSMENT_TYPE_LABELS.get(
            str(assessment.get("assessment_type") or ""),
            "Assessment",
        ),
        "status": str(assessment.get("status") or ""),
        "completed_at": assessment.get("completed_at"),
        "questions_planned": len(questions) or len(response_list),
        "questions_answered": len(response_list),
        "knowledge_total": knowledge_total,
        "knowledge_answered": knowledge_answered,
        "knowledge_correct": knowledge_correct,
        "practical_total": len(practical_questions) or len(practical_responses),
        "practical_answered": len(practical_responses),
        "score_percent": score_percent,
        "proficiency_label": band["label"] if band else None,
        "proficiency_description": band["description"] if band else None,
        "proficiency_band": band,
        "is_scored": score_percent is not None,
        "strong_areas": strong_areas,
        "improve_areas": improve_areas,
        "skills_assessed": skills_assessed,
        "incorrect_answers": incorrect_answers,
        "practical_review": practical_review,
        "next_steps": next_steps,
        "pathway_names": pathway_names,
        "message": message,
        "disclaimer": DISCLAIMER,
    }


def validate_assessment_bank() -> None:
    """Raise a content error if the bank is internally inconsistent."""

    question_ids: set[str] = set()
    skill_questions: dict[str, dict[str, int]] = {
        skill.skill_id: {KNOWLEDGE: 0, PRACTICAL: 0}
        for skill in SKILLS
    }

    for question in QUESTION_BANK:
        if question.question_id in question_ids:
            raise SkillAssessmentContentError(
                f"Duplicate question ID: {question.question_id}"
            )
        question_ids.add(question.question_id)

        skill = get_skill(question.skill_id)
        if skill is None:
            raise SkillAssessmentContentError(
                f"Unknown skill ID: {question.skill_id}"
            )
        if question.skill_label != skill.label:
            raise SkillAssessmentContentError(
                f"Skill label mismatch for {question.question_id}"
            )
        if question.category != skill.category:
            raise SkillAssessmentContentError(
                f"Category mismatch for {question.question_id}"
            )
        if question.question_type not in (KNOWLEDGE, PRACTICAL):
            raise SkillAssessmentContentError(
                f"Invalid question type for {question.question_id}"
            )

        if question.question_type == KNOWLEDGE:
            if len(question.options) < 2:
                raise SkillAssessmentContentError(
                    f"Not enough options for {question.question_id}"
                )
            option_ids = {option.option_id for option in question.options}
            if question.correct_option_id not in option_ids:
                raise SkillAssessmentContentError(
                    f"Invalid correct option for {question.question_id}"
                )
            if not question.explanation.strip():
                raise SkillAssessmentContentError(
                    f"Missing explanation for {question.question_id}"
                )
        else:
            if not question.marking_criteria:
                raise SkillAssessmentContentError(
                    f"Missing marking criteria for {question.question_id}"
                )
            if not question.expected_elements:
                raise SkillAssessmentContentError(
                    f"Missing expected elements for {question.question_id}"
                )

        skill_questions[question.skill_id][question.question_type] += 1

    for skill_id, counts in skill_questions.items():
        if counts[KNOWLEDGE] < 4:
            raise SkillAssessmentContentError(
                f"{skill_id} needs at least four knowledge questions."
            )
        if counts[PRACTICAL] < 1:
            raise SkillAssessmentContentError(
                f"{skill_id} needs at least one practical exercise."
            )

    area_skill_ids = [
        skill_id
        for area in CAREER_AREAS
        for skill_id in area.skill_ids
    ]
    if sorted(area_skill_ids) != sorted(skill_questions):
        raise SkillAssessmentContentError(
            "Every assessable skill must appear in exactly one career area."
        )

    for area in CAREER_AREAS:
        for skill_id in area.skill_ids:
            if skill_id not in SKILL_LOOKUP:
                raise SkillAssessmentContentError(
                    f"Unknown skill in career area: {skill_id}"
                )


__all__ = [
    "ASSESSABLE_SKILL_LABELS",
    "ASSESSMENT_TYPES",
    "ASSESSMENT_TYPE_LABELS",
    "AnswerOption",
    "AssessmentPlan",
    "AssessmentQuestion",
    "CAREER_AREAS",
    "CAREER_AREA_LOOKUP",
    "COMBINED",
    "CONTENT_VERSION",
    "CareerArea",
    "DISCLAIMER",
    "KNOWLEDGE",
    "MAX_RESPONSE_CHARS",
    "MIN_PRACTICAL_WORDS",
    "PRACTICAL",
    "PROFICIENCY_BANDS",
    "QUESTION_BANK",
    "QUESTION_LOOKUP",
    "SKILLS",
    "SKILL_LOOKUP",
    "STATUS_COMPLETED",
    "STATUS_IN_PROGRESS",
    "STATUSES",
    "SkillAssessmentContentError",
    "SkillAssessmentError",
    "SkillAssessmentValidationError",
    "SkillDefinition",
    "TARGET_CAREER_AREA",
    "TARGET_SKILL",
    "TARGET_TYPES",
    "build_plan",
    "build_result_summary",
    "evaluate_practical_response",
    "get_career_area",
    "get_question",
    "get_skill",
    "proficiency_band",
    "score_knowledge_question",
    "score_to_percentage",
    "validate_assessment_bank",
]
