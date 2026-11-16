"""Phase 0 regression tests for the interview preparation page.

These tests exercise pure catalogue and session-key helpers only. They do not
start Streamlit, open a database, or touch the real application data.
"""

from __future__ import annotations

import inspect
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.career_pages import (  # noqa: E402
    INTERVIEW_CHECKLIST,
    INTERVIEW_QUESTION_IDS,
    INTERVIEW_QUESTIONS,
    INTERVIEW_STAR_FIELDS,
    NO_ACTIVE_PROFILE_SCOPE,
    interview_answer_store_key,
    interview_answer_widget_key,
    interview_checklist_key,
    interview_model_answer_button_key,
    interview_model_answer_key,
    interview_profile_scope,
    interview_star_store_key,
    interview_star_widget_key,
    render_interview_page,
)


EXPECTED_QUESTION_IDS = (
    "opening_tell_me_about_yourself",
    "experience_proud_project",
    "experience_teamwork",
    "problem_solving_difficult_problem",
    "problem_solving_mistake",
    "motivation_role_and_organisation",
    "motivation_future_goals",
    "closing_questions_for_interviewer",
    "closing_anything_else",
)

EXPECTED_QUESTION_TEXTS = (
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


class InterviewCatalogueTests(unittest.TestCase):
    def test_all_nine_questions_are_preserved(self) -> None:
        self.assertEqual(len(INTERVIEW_QUESTIONS), 9)
        self.assertEqual(
            tuple(question.question for question in INTERVIEW_QUESTIONS),
            EXPECTED_QUESTION_TEXTS,
        )

    def test_question_ids_are_unique_and_stable(self) -> None:
        self.assertEqual(INTERVIEW_QUESTION_IDS, EXPECTED_QUESTION_IDS)
        self.assertEqual(len(set(INTERVIEW_QUESTION_IDS)), len(INTERVIEW_QUESTION_IDS))
        self.assertEqual(
            [question.question_id for question in INTERVIEW_QUESTIONS],
            list(EXPECTED_QUESTION_IDS),
        )

    def test_question_ids_are_slug_identifiers_not_positions(self) -> None:
        for question_id in INTERVIEW_QUESTION_IDS:
            with self.subTest(question_id=question_id):
                self.assertTrue(question_id)
                self.assertIsNone(re.fullmatch(r"\d+", question_id))
                self.assertRegex(question_id, r"^[a-z][a-z0-9_]+$")

    def test_question_guidance_is_present(self) -> None:
        for question in INTERVIEW_QUESTIONS:
            with self.subTest(question_id=question.question_id):
                self.assertTrue(question.category.strip())
                self.assertTrue(question.assesses.strip())
                self.assertTrue(question.structure.strip())

        project_question = INTERVIEW_QUESTIONS[1]
        self.assertIn("STAR", project_question.structure.upper())

    def test_categories_are_preserved(self) -> None:
        self.assertEqual(
            [question.category for question in INTERVIEW_QUESTIONS],
            [
                "Opening",
                "Experience",
                "Experience",
                "Problem solving",
                "Problem solving",
                "Motivation",
                "Motivation",
                "Closing",
                "Closing",
            ],
        )


class InterviewKeyTests(unittest.TestCase):
    def test_profile_scope_handles_missing_profiles(self) -> None:
        self.assertEqual(interview_profile_scope(None), NO_ACTIVE_PROFILE_SCOPE)
        self.assertEqual(interview_profile_scope({}), NO_ACTIVE_PROFILE_SCOPE)
        self.assertEqual(
            interview_profile_scope({"profile_id": "   "}),
            NO_ACTIVE_PROFILE_SCOPE,
        )
        self.assertEqual(
            interview_profile_scope({"profile_id": "profile-a"}),
            "profile-a",
        )

    def test_answer_keys_are_profile_and_question_specific(self) -> None:
        first = interview_answer_widget_key("profile-a", "question-one")
        self.assertEqual(
            first,
            interview_answer_widget_key("profile-a", "question-one"),
        )
        self.assertNotEqual(
            first,
            interview_answer_widget_key("profile-b", "question-one"),
        )
        self.assertNotEqual(
            first,
            interview_answer_widget_key("profile-a", "question-two"),
        )
        self.assertEqual(
            interview_answer_widget_key("profile-a", "question-one"),
            first,
        )

    def test_answer_store_keys_separate_profiles_and_questions(self) -> None:
        keys = {
            interview_answer_store_key("profile-a", "question-one"),
            interview_answer_store_key("profile-b", "question-one"),
            interview_answer_store_key("profile-a", "question-two"),
        }
        self.assertEqual(len(keys), 3)

    def test_model_answer_keys_separate_profiles_and_questions(self) -> None:
        keys = {
            interview_model_answer_key("profile-a", "question-one"),
            interview_model_answer_key("profile-b", "question-one"),
            interview_model_answer_key("profile-a", "question-two"),
            interview_model_answer_button_key("profile-a", "question-one"),
            interview_model_answer_button_key("profile-b", "question-one"),
        }
        self.assertEqual(len(keys), 5)

    def test_switching_question_keeps_answer_mapping_stable(self) -> None:
        profile_scope = "profile-a"
        answers = {}
        first_question = INTERVIEW_QUESTION_IDS[0]
        second_question = INTERVIEW_QUESTION_IDS[1]

        answers[interview_answer_store_key(profile_scope, first_question)] = (
            "First answer"
        )
        answers[interview_answer_store_key(profile_scope, second_question)] = (
            "Second answer"
        )

        self.assertEqual(
            answers[interview_answer_store_key(profile_scope, first_question)],
            "First answer",
        )
        self.assertEqual(
            answers[interview_answer_store_key(profile_scope, second_question)],
            "Second answer",
        )

    def test_star_keys_are_profile_question_and_field_specific(self) -> None:
        keys = set()
        for star_field, _ in INTERVIEW_STAR_FIELDS:
            with self.subTest(star_field=star_field):
                key = interview_star_widget_key(
                    "profile-a", "question-one", star_field
                )
                self.assertEqual(
                    key,
                    interview_star_widget_key(
                        "profile-a", "question-one", star_field
                    ),
                )
                self.assertNotEqual(
                    key,
                    interview_star_widget_key(
                        "profile-b", "question-one", star_field
                    ),
                )
                self.assertNotEqual(
                    key,
                    interview_star_widget_key(
                        "profile-a", "question-two", star_field
                    ),
                )
                self.assertNotEqual(
                    key,
                    interview_star_store_key(
                        "profile-a", "question-one", star_field
                    ),
                )
                keys.add(key)

        self.assertEqual(len(keys), len(INTERVIEW_STAR_FIELDS))

    def test_checklist_keys_are_unique_and_deterministic(self) -> None:
        ids = [item_id for item_id, _ in INTERVIEW_CHECKLIST]
        keys = [interview_checklist_key(item_id) for item_id in ids]

        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(keys, [interview_checklist_key(item_id) for item_id in ids])
        self.assertEqual(
            interview_checklist_key("job_description_requirements"),
            "interview_check::job_description_requirements",
        )
        self.assertNotIn("hash(", inspect.getsource(render_interview_page))

    def test_checklist_items_are_preserved(self) -> None:
        self.assertEqual(
            [text for _, text in INTERVIEW_CHECKLIST],
            [
                "Re-read the job description and note the top five requirements.",
                "Prepare two or three real examples that match those requirements.",
                "Research the organisation's work, values, and recent public updates.",
                "Confirm the interview time, format, location, or link.",
                "Prepare your own questions for the panel.",
                "Print or save a clean copy of your CV and any certificates requested.",
                "Plan your route and leave enough travel time.",
            ],
        )


class InterviewPageSafetyTests(unittest.TestCase):
    def test_manual_review_and_length_guidance_are_preserved(self) -> None:
        source = inspect.getsource(render_interview_page)
        self.assertIn("manual self-review, not an AI evaluation", source)
        self.assertIn("120–220 words", source)
        self.assertIn("not saved to your", source)
        self.assertIn("profile or database", source)

    def test_renderer_has_no_direct_database_calls(self) -> None:
        source = inspect.getsource(render_interview_page)
        self.assertNotIn("update_profile_record(", source)
        self.assertNotIn("get_database_connection(", source)
        self.assertNotIn(".execute(", source)
        self.assertNotIn("sqlite3.", source)

    def test_renderer_uses_question_ids_for_selection(self) -> None:
        source = inspect.getsource(render_interview_page)
        self.assertIn("INTERVIEW_QUESTION_IDS", source)
        self.assertIn("INTERVIEW_QUESTION_LOOKUP", source)
        self.assertNotIn("labels.index", source)
        self.assertNotIn("interview_answer_{index}", source)


if __name__ == "__main__":
    unittest.main()
