"""Tests for the Mock Interview Centre.

Every persistence test uses a temporary SQLite database. The real
data/kazimsaada.db file is never opened by this test module.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.interview_centre import (  # noqa: E402
    NO_ACTIVE_PROFILE_SCOPE,
    interview_centre_profile_scope,
    interview_centre_state_key,
)
from core.ai_client import (  # noqa: E402
    AIProviderNotConfigured,
    ai_status,
    get_ai_provider,
    load_ai_settings,
)
from core.database import initialize_database  # noqa: E402
from core.interview import (  # noqa: E402
    CORE_INTERVIEW_QUESTIONS,
    CORE_QUESTION_IDS,
    DIFFICULTY_IDS,
    MAX_QUESTIONS_PER_SESSION,
    InterviewConfigurationError,
    QUESTION_BANK,
    QUESTION_BANK_IDS,
    ROLE_GROUPS,
    build_local_feedback,
    build_model_answer,
    build_session_summary,
    evaluate_answer,
    generate_ai_question,
    get_question,
    select_questions,
)
from core.interview_store import (  # noqa: E402
    DuplicateResponseError,
    InterviewSessionClosed,
    InterviewSessionNotFound,
    InterviewValidationError,
    SESSION_CANCELLED,
    SESSION_COMPLETED,
    SESSION_IN_PROGRESS,
    add_custom_question,
    cancel_session,
    complete_session,
    create_session,
    delete_session,
    get_responses,
    get_session,
    get_session_questions,
    list_sessions,
    save_response,
)
from core.profiles import create_profile, delete_profile_record  # noqa: E402

SAMPLE_PROFILE = {
    "name": "Test Applicant",
    "education": "Diploma in Information Technology",
    "location": "Nairobi",
    "experience": "One year of ICT support attachment",
    "career_interest": "ICT support",
    "skills": ["Computer literacy", "Problem solving"],
}

SECOND_PROFILE = {
    "name": "Second Applicant",
    "education": "Bachelor of Commerce",
    "location": "Kisumu",
    "experience": "Customer service volunteering",
    "career_interest": "Customer service",
    "skills": ["Customer care", "Record keeping"],
}


class InterviewTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        initialize_database(self.db_path)
        self.profile = create_profile(SAMPLE_PROFILE, db_path=self.db_path)
        self.other_profile = create_profile(SECOND_PROFILE, db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def question_ids(self, count: int = 3) -> list[str]:
        return list(QUESTION_BANK_IDS[:count])

    def create_test_session(self, count: int = 3, profile: dict | None = None):
        profile = profile or self.profile
        questions = self.question_ids(count)
        return create_session(
            profile["profile_id"],
            profile["career_interest"],
            "general",
            "intermediate",
            questions,
            db_path=self.db_path,
        )

    def feedback_for(self, question_id: str, answer: str) -> dict:
        question = get_question(question_id)
        self.assertIsNotNone(question)
        return build_local_feedback(
            question,
            answer,
            self.profile["career_interest"],
            "intermediate",
        )


class QuestionBankTests(unittest.TestCase):
    def test_question_ids_are_unique_and_stable(self) -> None:
        self.assertEqual(len(QUESTION_BANK_IDS), len(set(QUESTION_BANK_IDS)))
        self.assertEqual(len(CORE_QUESTION_IDS), 9)
        self.assertEqual(CORE_QUESTION_IDS[0], "opening_tell_me_about_yourself")
        self.assertEqual(CORE_QUESTION_IDS[-1], "closing_anything_else")
        for question_id in QUESTION_BANK_IDS:
            with self.subTest(question_id=question_id):
                self.assertTrue(question_id)
                self.assertIsNone(re.fullmatch(r"\d+", question_id))
                self.assertRegex(question_id, r"^[a-z][a-z0-9_]+$")

    def test_questions_contain_required_fields(self) -> None:
        category_ids = {category for category in (question.category for question in QUESTION_BANK)}
        self.assertTrue(category_ids)
        for question in QUESTION_BANK:
            with self.subTest(question_id=question.question_id):
                self.assertTrue(question.category.strip())
                self.assertTrue(question.interview_categories)
                self.assertTrue(question.role_groups)
                self.assertTrue(question.question.strip())
                self.assertTrue(question.assesses.strip())
                self.assertTrue(question.structure.strip())
                self.assertIn(question.difficulty, DIFFICULTY_IDS)
                self.assertTrue(set(question.role_groups).issubset(set(ROLE_GROUPS)))

    def test_existing_nine_questions_are_retained(self) -> None:
        expected_texts = (
            "Tell me about yourself.",
            "Walk me through a project or task you are proud of.",
            "Tell me about a time you worked in a team.",
            "Describe a difficult problem you solved.",
            "Tell me about a mistake you made and what happened next.",
            "Why do you want this role and this organisation?",
            "Where do you see yourself in the next few years?",
            "Do you have any questions for us?",
            "Is there anything else you would like us to know?",
        )
        self.assertEqual(
            tuple(question.question for question in CORE_INTERVIEW_QUESTIONS),
            expected_texts,
        )
        self.assertTrue(set(CORE_QUESTION_IDS).issubset(set(QUESTION_BANK_IDS)))

    def test_role_and_category_filtering_works(self) -> None:
        customer_questions = select_questions(
            "customer_service_admin",
            "beginner",
            "customer service assistant",
            6,
        )
        self.assertTrue(customer_questions)
        self.assertTrue(
            all(
                "customer_service_admin" in question.interview_categories
                for question in customer_questions
            )
        )
        self.assertTrue(
            any(
                "customer_service_admin" in question.role_groups
                for question in customer_questions
            )
        )

        technical_questions = select_questions(
            "technical_professional",
            "advanced",
            "ICT support officer",
            6,
        )
        self.assertTrue(technical_questions)
        self.assertEqual(technical_questions[0].difficulty, "advanced")

        mismatched = select_questions(
            "customer_service_admin",
            "beginner",
            "software engineer",
            6,
        )
        self.assertTrue(mismatched)
        self.assertTrue(
            all(
                "general" in question.role_groups
                for question in mismatched
            )
        )

    def test_more_than_six_questions_can_be_selected(self) -> None:
        self.assertGreaterEqual(MAX_QUESTIONS_PER_SESSION, len(QUESTION_BANK))
        questions = select_questions(
            "general",
            "intermediate",
            "ICT support officer",
            MAX_QUESTIONS_PER_SESSION,
        )
        self.assertGreater(len(questions), 6)
        self.assertEqual(len({question.question_id for question in questions}), len(questions))

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            select_questions("not-a-category", "beginner", "support", 4)
        with self.assertRaises(Exception):
            select_questions("general", "not-a-difficulty", "support", 4)


class LocalFeedbackAndAiTests(unittest.TestCase):
    def test_local_feedback_is_not_ai_and_has_all_sections(self) -> None:
        question = get_question("experience_proud_project")
        feedback = build_local_feedback(
            question,
            (
                "During my attachment I supported a staff member whose laptop "
                "would not connect. I checked the cable, reset the connection and "
                "documented the fix. The staff member was able to work again and I "
                "learned to check the simplest cause first."
            ),
            "ICT support officer",
            "intermediate",
        )
        self.assertEqual(feedback["source"], "local_guidance")
        self.assertNotEqual(feedback["source"], "ai")
        for key in ("relevance", "clarity", "structure", "examples", "suggestions"):
            self.assertIn(key, feedback)
        self.assertIn("not AI-generated", feedback["summary"])
        self.assertIn("does not guarantee", feedback["disclaimer"])

    def test_missing_ai_configuration_is_safe(self) -> None:
        settings = load_ai_settings({})
        self.assertFalse(settings.configured)
        self.assertIsNone(get_ai_provider(settings))
        status = ai_status(settings)
        self.assertFalse(status.configured)
        self.assertFalse(status.available)
        self.assertIn("not configured", status.message)

        configured = load_ai_settings(
            {"ai": {"provider": "example", "api_key": "top-secret-value"}}
        )
        self.assertTrue(configured.configured)
        self.assertNotIn("top-secret-value", repr(configured))
        with self.assertRaises(AIProviderNotConfigured):
            get_ai_provider(configured)

    def test_ai_provider_errors_fall_back_without_crashing(self) -> None:
        class BrokenProvider:
            name = "broken"

            def generate_feedback(self, request):
                raise RuntimeError("simulated network failure")

        question = get_question("opening_tell_me_about_yourself")
        feedback = evaluate_answer(
            question,
            "I am an ICT support graduate with practical attachment experience.",
            "ICT support officer",
            "beginner",
            provider=BrokenProvider(),
        )
        self.assertEqual(feedback["source"], "local_fallback")
        self.assertIn("AI feedback was unavailable", feedback["notice"])
        self.assertNotIn("simulated network failure", json.dumps(feedback))

    def test_ai_provider_success_is_labelled(self) -> None:
        class WorkingProvider:
            name = "approved-test-provider"

            def generate_feedback(self, request):
                return {
                    "relevance": "The answer addresses the question.",
                    "clarity": "The answer is easy to follow.",
                    "structure": "Add a clearer result.",
                    "examples": "Add one concrete example.",
                    "suggestions": ["Name the result."],
                }

        question = get_question("opening_tell_me_about_yourself")
        feedback = evaluate_answer(
            question,
            "I am an ICT support graduate with practical attachment experience.",
            "ICT support officer",
            "beginner",
            provider=WorkingProvider(),
        )
        self.assertEqual(feedback["source"], "ai")
        self.assertEqual(feedback["provider_name"], "approved-test-provider")
        self.assertIn("AI-generated", feedback["disclaimer"])

    def test_ai_followup_question_is_labelled_and_uses_minimum_context(self) -> None:
        class WorkingQuestionProvider:
            name = "approved-question-provider"

            def __init__(self) -> None:
                self.request = None

            def generate_question(self, request):
                self.request = request
                return {
                    "question": "Tell me about a time you explained a technical issue to a non-technical colleague.",
                    "assesses": "Communication and empathy.",
                    "structure": "Use a specific example and explain the result.",
                }

        provider = WorkingQuestionProvider()
        generated = generate_ai_question(
            "general",
            "ICT support officer",
            "intermediate",
            ["Tell me about yourself."],
            provider,
        )
        self.assertEqual(generated["source"], "ai")
        self.assertIn("non-technical colleague", generated["question"])
        self.assertEqual(
            provider.request.previous_questions,
            ("Tell me about yourself.",),
        )
        self.assertNotIn("CV", repr(provider.request))
        self.assertNotIn("profile", repr(provider.request))

    def test_ai_followup_question_rejects_a_repeat(self) -> None:
        class RepeatingProvider:
            name = "repeating-provider"

            def generate_question(self, request):
                return {
                    "question": "Tell me about yourself.",
                    "assesses": "Opening question.",
                    "structure": "Use a short summary.",
                }

        with self.assertRaises(InterviewConfigurationError):
            generate_ai_question(
                "general",
                "ICT support officer",
                "intermediate",
                ["Tell me about yourself."],
                RepeatingProvider(),
            )

    def test_ai_model_answer_is_labelled_and_uses_minimum_context(self) -> None:
        class WorkingModelAnswerProvider:
            name = "approved-model-answer-provider"

            def __init__(self) -> None:
                self.request = None

            def generate_model_answer(self, request):
                self.request = request
                return {
                    "model_answer": (
                        "In my [project], I noticed [problem]. I took responsibility "
                        "for [action], worked with [people], and the result was [result]."
                    ),
                    "why_it_works": "It uses a specific example and a clear result.",
                    "star_breakdown": {
                        "situation": "A real project.",
                        "task": "Fix the issue.",
                        "action": "Investigated and involved others.",
                        "result": "The issue was resolved.",
                    },
                    "tips": ["Replace the placeholders with real details."],
                }

        question = get_question("experience_proud_project")
        provider = WorkingModelAnswerProvider()
        answer = build_model_answer(
            question,
            "ICT support officer",
            "intermediate",
            provider,
        )
        self.assertEqual(answer["source"], "ai")
        self.assertEqual(answer["provider_name"], "approved-model-answer-provider")
        self.assertEqual(answer["star_breakdown"]["Situation"], "A real project.")
        self.assertIn("not a score", answer["disclaimer"])
        self.assertEqual(provider.request.question, question.question)
        self.assertNotIn("answer", provider.request.__dict__)

    def test_ai_model_answer_requires_a_configured_provider(self) -> None:
        question = get_question("opening_tell_me_about_yourself")
        with self.assertRaises(InterviewConfigurationError):
            build_model_answer(question, "ICT support officer", "beginner", None)

    def test_session_summary_is_non_scoring(self) -> None:
        response = {
            "feedback": {
                "star_checklist": {
                    "situation": True,
                    "task": True,
                    "action": True,
                    "result": True,
                },
                "word_count": 150,
                "examples": "You include a concrete detail.",
                "suggestions": ["Add a measurable result."],
            }
        }
        summary = build_session_summary([response])
        self.assertEqual(summary["questions_answered"], 1)
        self.assertTrue(summary["strengths"])
        self.assertTrue(summary["improvements"])
        self.assertTrue(summary["next_steps"])
        self.assertNotIn("score", summary["summary"].casefold())


class InterviewStoreTests(InterviewTestBase):
    def test_new_tables_exist_and_migrations_are_repeatable(self) -> None:
        initialize_database(self.db_path)
        session = self.create_test_session(1)
        initialize_database(self.db_path)
        self.assertEqual(get_session(session["id"], self.profile["profile_id"], db_path=self.db_path)["id"], session["id"])

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()
        self.assertIn("interview_sessions", tables)
        self.assertIn("interview_responses", tables)
        self.assertIn("interview_custom_questions", tables)

    def test_session_creation_and_retrieval(self) -> None:
        session = self.create_test_session(3)
        self.assertEqual(session["status"], SESSION_IN_PROGRESS)
        self.assertEqual(session["profile_id"], self.profile["profile_id"])
        self.assertEqual(session["answered_count"], 0)
        self.assertEqual(len(session["question_ids"]), 3)

        loaded = get_session(session["id"], self.profile["profile_id"], db_path=self.db_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["id"], session["id"])

        sessions = list_sessions(self.profile["profile_id"], db_path=self.db_path)
        self.assertEqual([item["id"] for item in sessions], [session["id"]])

    def test_more_than_six_questions_can_be_created(self) -> None:
        session = self.create_test_session(10)
        self.assertEqual(len(session["question_ids"]), 10)
        self.assertEqual(
            len(
                get_session_questions(
                    session["id"],
                    self.profile["profile_id"],
                    db_path=self.db_path,
                )
            ),
            10,
        )

    def test_ai_followup_question_can_be_added_and_answered(self) -> None:
        session = self.create_test_session(1)
        custom = add_custom_question(
            session["id"],
            self.profile["profile_id"],
            "How would you explain a password reset to a frustrated user?",
            "general",
            "intermediate",
            assesses="Customer care and communication.",
            structure="Use a calm, step-by-step example.",
            db_path=self.db_path,
        )
        self.assertEqual(custom["source"], "ai")
        self.assertTrue(str(custom["question_id"]).startswith("ai_"))

        questions = get_session_questions(
            session["id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[-1]["question"], custom["question"])
        self.assertEqual(questions[-1]["source"], "ai")

        answer = (
            "I would stay calm, confirm the user's details, explain each step, and "
            "check that they can sign in before ending the call."
        )
        feedback = evaluate_answer(
            questions[-1],
            answer,
            self.profile["career_interest"],
            "intermediate",
        )
        saved = save_response(
            session["id"],
            self.profile["profile_id"],
            custom["question_id"],
            answer,
            feedback,
            db_path=self.db_path,
        )
        self.assertEqual(saved["question_text"], custom["question"])
        self.assertEqual(saved["feedback"]["source"], "local_guidance")

    def test_duplicate_ai_followup_question_is_rejected(self) -> None:
        session = self.create_test_session(1)
        text = "How would you handle a difficult customer?"
        add_custom_question(
            session["id"],
            self.profile["profile_id"],
            text,
            "general",
            "intermediate",
            db_path=self.db_path,
        )
        with self.assertRaises(InterviewValidationError):
            add_custom_question(
                session["id"],
                self.profile["profile_id"],
                text,
                "general",
                "intermediate",
                db_path=self.db_path,
            )

    def test_response_saving_and_retrieval(self) -> None:
        session = self.create_test_session(2)
        question_id = session["question_ids"][0]
        answer = "During my attachment I fixed a network cable and documented the change."
        feedback = self.feedback_for(question_id, answer)

        saved = save_response(
            session["id"],
            self.profile["profile_id"],
            question_id,
            answer,
            feedback,
            assessment_data={"source": "local_guidance"},
            db_path=self.db_path,
        )
        self.assertEqual(saved["answer_text"], answer)
        self.assertEqual(saved["feedback"]["source"], "local_guidance")

        responses = get_responses(session["id"], self.profile["profile_id"], db_path=self.db_path)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["question_id"], question_id)
        self.assertEqual(
            get_session(session["id"], self.profile["profile_id"], db_path=self.db_path)["answered_count"],
            1,
        )

    def test_empty_and_too_short_responses_are_rejected(self) -> None:
        session = self.create_test_session(1)
        question_id = session["question_ids"][0]
        for answer in ("", "   ", "too short"):
            with self.subTest(answer=answer):
                with self.assertRaises(InterviewValidationError):
                    save_response(
                        session["id"],
                        self.profile["profile_id"],
                        question_id,
                        answer,
                        {"source": "local_guidance"},
                        db_path=self.db_path,
                    )

    def test_duplicate_responses_are_prevented(self) -> None:
        session = self.create_test_session(1)
        question_id = session["question_ids"][0]
        answer = "I handled a customer request and recorded the outcome carefully."
        feedback = self.feedback_for(question_id, answer)

        save_response(
            session["id"],
            self.profile["profile_id"],
            question_id,
            answer,
            feedback,
            db_path=self.db_path,
        )
        with self.assertRaises(DuplicateResponseError):
            save_response(
                session["id"],
                self.profile["profile_id"],
                question_id,
                answer,
                feedback,
                db_path=self.db_path,
            )

    def test_session_completion_and_closed_session(self) -> None:
        session = self.create_test_session(1)
        question_id = session["question_ids"][0]
        answer = "I completed a group assignment by coordinating tasks and reviewing the result."
        save_response(
            session["id"],
            self.profile["profile_id"],
            question_id,
            answer,
            self.feedback_for(question_id, answer),
            db_path=self.db_path,
        )
        summary = build_session_summary(
            get_responses(session["id"], self.profile["profile_id"], db_path=self.db_path)
        )
        completed = complete_session(
            session["id"],
            self.profile["profile_id"],
            summary,
            db_path=self.db_path,
        )
        self.assertEqual(completed["status"], SESSION_COMPLETED)
        self.assertIsNotNone(completed["completed_at"])
        self.assertEqual(completed["overall_feedback"]["questions_answered"], 1)

        with self.assertRaises(InterviewSessionClosed):
            save_response(
                session["id"],
                self.profile["profile_id"],
                question_id,
                answer,
                self.feedback_for(question_id, answer),
                db_path=self.db_path,
            )

    def test_cancelled_and_incomplete_sessions_are_handled(self) -> None:
        session = self.create_test_session(2)
        cancelled = cancel_session(
            session["id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(cancelled["status"], SESSION_CANCELLED)

        question_id = session["question_ids"][0]
        with self.assertRaises(InterviewSessionClosed):
            save_response(
                session["id"],
                self.profile["profile_id"],
                question_id,
                "I answered this before the session ended.",
                {"source": "local_guidance"},
                db_path=self.db_path,
            )
        with self.assertRaises(InterviewSessionClosed):
            complete_session(
                session["id"],
                self.profile["profile_id"],
                {"summary": "test"},
                db_path=self.db_path,
            )

        incomplete = self.create_test_session(1)
        self.assertEqual(incomplete["status"], SESSION_IN_PROGRESS)
        self.assertEqual(incomplete["answered_count"], 0)

    def test_completion_requires_all_answers(self) -> None:
        session = self.create_test_session(2)
        with self.assertRaises(InterviewValidationError):
            complete_session(
                session["id"],
                self.profile["profile_id"],
                {"summary": "not finished"},
                db_path=self.db_path,
            )

    def test_profile_ownership_is_enforced(self) -> None:
        session = self.create_test_session(1)
        question_id = session["question_ids"][0]
        answer = "I explained a customer issue and recorded the agreed next step."

        self.assertIsNone(
            get_session(
                session["id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )
        )
        self.assertEqual(
            list_sessions(self.other_profile["profile_id"], db_path=self.db_path),
            [],
        )

        with self.assertRaises(InterviewSessionNotFound):
            get_responses(
                session["id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )
        with self.assertRaises(InterviewSessionNotFound):
            save_response(
                session["id"],
                self.other_profile["profile_id"],
                question_id,
                answer,
                {"source": "local_guidance"},
                db_path=self.db_path,
            )
        with self.assertRaises(InterviewSessionNotFound):
            delete_session(
                session["id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )

    def test_deleting_session_removes_responses(self) -> None:
        session = self.create_test_session(1)
        question_id = session["question_ids"][0]
        answer = "I completed the task and documented the result for the team."
        save_response(
            session["id"],
            self.profile["profile_id"],
            question_id,
            answer,
            self.feedback_for(question_id, answer),
            db_path=self.db_path,
        )
        self.assertTrue(
            delete_session(
                session["id"],
                self.profile["profile_id"],
                db_path=self.db_path,
            )
        )

        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM interview_responses WHERE session_id = ?",
                (session["id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 0)
        self.assertIsNone(
            get_session(session["id"], self.profile["profile_id"], db_path=self.db_path)
        )

    def test_deleting_session_removes_ai_followup_questions(self) -> None:
        session = self.create_test_session(1)
        add_custom_question(
            session["id"],
            self.profile["profile_id"],
            "What would you do if a user could not explain the problem clearly?",
            "general",
            "intermediate",
            db_path=self.db_path,
        )
        self.assertTrue(
            delete_session(
                session["id"],
                self.profile["profile_id"],
                db_path=self.db_path,
            )
        )
        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM interview_custom_questions WHERE session_id = ?",
                (session["id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 0)

    def test_deleting_profile_cascades_ai_followup_questions(self) -> None:
        session = self.create_test_session(1)
        add_custom_question(
            session["id"],
            self.profile["profile_id"],
            "How would you prioritise two urgent support requests?",
            "general",
            "intermediate",
            db_path=self.db_path,
        )
        self.assertTrue(
            delete_profile_record(
                self.profile["profile_id"],
                db_path=self.db_path,
            )
        )
        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM interview_custom_questions WHERE session_id = ?",
                (session["id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 0)

    def test_deleting_profile_cascades_interview_data(self) -> None:
        session = self.create_test_session(1)
        self.assertTrue(
            delete_profile_record(
                self.profile["profile_id"],
                db_path=self.db_path,
            )
        )
        connection = sqlite3.connect(self.db_path)
        try:
            sessions = connection.execute(
                "SELECT COUNT(*) FROM interview_sessions WHERE profile_id = ?",
                (self.profile["profile_id"],),
            ).fetchone()[0]
            responses = connection.execute(
                "SELECT COUNT(*) FROM interview_responses WHERE session_id = ?",
                (session["id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(sessions, 0)
        self.assertEqual(responses, 0)


class InterviewStateKeyTests(unittest.TestCase):
    def test_profile_scoped_state_keys_are_stable_and_isolated(self) -> None:
        first = interview_centre_state_key("profile-a", "active_session_id")
        second = interview_centre_state_key("profile-b", "active_session_id")
        self.assertEqual(
            first,
            interview_centre_state_key("profile-a", "active_session_id"),
        )
        self.assertNotEqual(first, second)
        self.assertEqual(
            interview_centre_profile_scope(None),
            NO_ACTIVE_PROFILE_SCOPE,
        )
        self.assertEqual(
            interview_centre_profile_scope({"profile_id": "profile-a"}),
            "profile-a",
        )


if __name__ == "__main__":
    unittest.main()
