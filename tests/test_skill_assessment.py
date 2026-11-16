"""Tests for guided skill assessments and their SQLite persistence.

Every database test uses a temporary SQLite file. The real
data/kazimsaada.db database is never opened by this module.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.career_pages import SKILL_GROUPS  # noqa: E402
from core.database import initialize_database  # noqa: E402
from core.profiles import (  # noqa: E402
    create_profile,
    delete_profile_record,
)
from core.skill_assessment import (  # noqa: E402
    ASSESSABLE_SKILL_LABELS,
    ASSESSMENT_TYPES,
    CAREER_AREAS,
    COMBINED,
    CONTENT_VERSION,
    KNOWLEDGE,
    PRACTICAL,
    QUESTION_BANK,
    SKILLS,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    TARGET_CAREER_AREA,
    TARGET_SKILL,
    SkillAssessmentValidationError,
    build_plan,
    build_result_summary,
    evaluate_practical_response,
    proficiency_band,
    score_knowledge_question,
    score_to_percentage,
    validate_assessment_bank,
)
from core.skill_assessment_store import (  # noqa: E402
    DuplicateAssessmentResponse,
    SkillAssessmentNotFound,
    complete_assessment,
    create_assessment,
    delete_assessment,
    get_assessment,
    get_assessment_questions,
    get_response,
    get_responses,
    list_assessments,
    list_comparable_assessments,
    save_response,
)

SAMPLE_PROFILE = {
    "name": "Skill Test Applicant",
    "education": "Diploma in Information Technology",
    "location": "Nairobi",
    "experience": "ICT support attachment",
    "career_interest": "ICT support",
    "skills": ["Computer literacy", "Communication", "Problem solving"],
}

OTHER_PROFILE = {
    "name": "Other Skill Applicant",
    "education": "Certificate in Business Administration",
    "location": "Kisumu",
    "experience": "Volunteer shop assistant",
    "career_interest": "Business administration",
    "skills": ["Bookkeeping", "Customer care"],
}

EXPECTED_SKILL_IDS = {
    "computer_literacy",
    "microsoft_office",
    "data_analysis",
    "communication",
    "customer_care",
    "problem_solving",
    "time_management",
    "teamwork",
    "critical_thinking",
    "professional_ethics",
    "bookkeeping",
    "project_management",
}


def wrong_option(question):
    return next(
        option.option_id
        for option in question.options
        if option.option_id != question.correct_option_id
    )


def practical_text() -> str:
    return (
        "I would first listen carefully, confirm the details, and explain the "
        "next step in plain language. Then I would record the issue, agree a "
        "timeline, and follow up so the person knows what happens next."
    )


class SkillAssessmentContentTests(unittest.TestCase):
    def test_assessment_bank_is_internally_consistent(self) -> None:
        validate_assessment_bank()
        self.assertEqual(len(SKILLS), 12)
        self.assertEqual(len(QUESTION_BANK), 60)
        self.assertEqual(
            {skill.skill_id for skill in SKILLS},
            EXPECTED_SKILL_IDS,
        )

    def test_question_ids_are_unique_and_stable(self) -> None:
        question_ids = [question.question_id for question in QUESTION_BANK]
        self.assertEqual(len(question_ids), len(set(question_ids)))
        for question in QUESTION_BANK:
            with self.subTest(question_id=question.question_id):
                self.assertTrue(
                    question.question_id.startswith(question.skill_id + "_")
                )
                self.assertNotIn(" ", question.question_id)

    def test_each_skill_has_knowledge_and_practical_questions(self) -> None:
        for skill in SKILLS:
            with self.subTest(skill=skill.skill_id):
                questions = [
                    question
                    for question in QUESTION_BANK
                    if question.skill_id == skill.skill_id
                ]
                knowledge = [
                    question
                    for question in questions
                    if question.question_type == KNOWLEDGE
                ]
                practical = [
                    question
                    for question in questions
                    if question.question_type == PRACTICAL
                ]
                self.assertGreaterEqual(len(knowledge), 4)
                self.assertGreaterEqual(len(practical), 1)

    def test_knowledge_questions_have_valid_marking_data(self) -> None:
        for question in QUESTION_BANK:
            if question.question_type != KNOWLEDGE:
                continue
            with self.subTest(question_id=question.question_id):
                self.assertGreaterEqual(len(question.options), 2)
                option_ids = {
                    option.option_id for option in question.options
                }
                self.assertEqual(
                    len(option_ids),
                    len(question.options),
                )
                self.assertIn(
                    question.correct_option_id,
                    option_ids,
                )
                self.assertTrue(question.explanation.strip())
                self.assertFalse(question.marking_criteria)

    def test_practical_questions_have_criteria_and_expected_elements(self) -> None:
        for question in QUESTION_BANK:
            if question.question_type != PRACTICAL:
                continue
            with self.subTest(question_id=question.question_id):
                self.assertTrue(question.marking_criteria)
                self.assertTrue(question.expected_elements)
                self.assertEqual(question.options, ())
                self.assertIsNone(question.correct_option_id)

    def test_career_areas_cover_every_skill_once(self) -> None:
        area_skill_ids = [
            skill_id
            for area in CAREER_AREAS
            for skill_id in area.skill_ids
        ]
        self.assertEqual(
            sorted(area_skill_ids),
            sorted(EXPECTED_SKILL_IDS),
        )
        self.assertEqual(len(area_skill_ids), len(set(area_skill_ids)))

    def test_assessable_skills_are_in_the_existing_skill_groups(self) -> None:
        existing = {
            skill.casefold()
            for group in SKILL_GROUPS.values()
            for skill in group
        }
        for label in ASSESSABLE_SKILL_LABELS:
            with self.subTest(skill=label):
                self.assertIn(label.casefold(), existing)

    def test_build_plan_filters_by_target_and_method(self) -> None:
        skill_knowledge = build_plan(
            TARGET_SKILL, "computer_literacy", KNOWLEDGE
        )
        self.assertEqual(len(skill_knowledge.questions), 4)
        self.assertEqual(len(skill_knowledge.practical_questions), 0)
        self.assertTrue(skill_knowledge.is_scored)

        skill_practical = build_plan(
            TARGET_SKILL, "computer_literacy", PRACTICAL
        )
        self.assertEqual(len(skill_practical.questions), 1)
        self.assertEqual(len(skill_practical.knowledge_questions), 0)
        self.assertFalse(skill_practical.is_scored)

        skill_both = build_plan(
            TARGET_SKILL, "computer_literacy", COMBINED
        )
        self.assertEqual(len(skill_both.knowledge_questions), 4)
        self.assertEqual(len(skill_both.practical_questions), 1)
        self.assertEqual(len(skill_both.questions), 5)

        area_both = build_plan(
            TARGET_CAREER_AREA, "digital_technical", COMBINED
        )
        self.assertEqual(len(area_both.knowledge_questions), 12)
        self.assertEqual(len(area_both.practical_questions), 3)
        self.assertEqual(len(area_both.questions), 15)

    def test_invalid_plan_choices_are_rejected(self) -> None:
        with self.assertRaises(SkillAssessmentValidationError):
            build_plan(TARGET_SKILL, "missing_skill", KNOWLEDGE)
        with self.assertRaises(SkillAssessmentValidationError):
            build_plan(TARGET_CAREER_AREA, "missing_area", KNOWLEDGE)
        with self.assertRaises(SkillAssessmentValidationError):
            build_plan(TARGET_SKILL, "computer_literacy", "essay")

    def test_correct_and_incorrect_knowledge_marking(self) -> None:
        plan = build_plan(TARGET_SKILL, "computer_literacy", KNOWLEDGE)
        question = plan.knowledge_questions[0]

        correct = score_knowledge_question(
            question, question.correct_option_id
        )
        self.assertTrue(correct["is_correct"])
        self.assertEqual(correct["score_awarded"], 1.0)
        self.assertEqual(
            correct["feedback"]["correct_option_text"],
            next(
                option.text
                for option in question.options
                if option.option_id == question.correct_option_id
            ),
        )
        self.assertTrue(correct["feedback"]["explanation"])

        incorrect = score_knowledge_question(
            question, wrong_option(question)
        )
        self.assertFalse(incorrect["is_correct"])
        self.assertEqual(incorrect["score_awarded"], 0.0)
        self.assertIn("not correct", incorrect["feedback"]["message"].casefold())

        with self.assertRaises(SkillAssessmentValidationError):
            score_knowledge_question(question, "")

    def test_proficiency_band_boundaries(self) -> None:
        expected = {
            0: "Needs development",
            39: "Needs development",
            40: "Developing",
            59: "Developing",
            60: "Competent foundation",
            79: "Competent foundation",
            80: "Strong foundation",
            100: "Strong foundation",
        }
        for score, label in expected.items():
            with self.subTest(score=score):
                band = proficiency_band(score)
                self.assertIsNotNone(band)
                self.assertEqual(band["label"], label)
        self.assertIsNone(proficiency_band(None))

    def test_score_percentage_calculation(self) -> None:
        self.assertEqual(score_to_percentage(3, 4), 75)
        self.assertEqual(score_to_percentage(2, 4), 50)
        self.assertEqual(score_to_percentage(0, 4), 0)
        self.assertEqual(score_to_percentage(4, 4), 100)
        self.assertIsNone(score_to_percentage(0, 0))
        self.assertEqual(score_to_percentage(9, 4), 100)

    def test_practical_responses_are_not_automatically_scored(self) -> None:
        plan = build_plan(TARGET_SKILL, "customer_care", PRACTICAL)
        question = plan.practical_questions[0]
        result = evaluate_practical_response(question, practical_text())
        self.assertIsNone(result["is_correct"])
        self.assertIsNone(result["score_awarded"])
        self.assertTrue(result["feedback"]["marking_criteria"])
        self.assertTrue(result["feedback"]["expected_elements"])
        self.assertIn("not automatically scored", result["feedback"]["message"])

        with self.assertRaises(SkillAssessmentValidationError):
            evaluate_practical_response(question, "Too short.")


class SkillAssessmentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        initialize_database(self.db_path)
        self.profile = create_profile(
            SAMPLE_PROFILE, db_path=self.db_path
        )
        self.other_profile = create_profile(
            OTHER_PROFILE, db_path=self.db_path
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_plan(self, skill_id="computer_literacy", method=KNOWLEDGE):
        return build_plan(TARGET_SKILL, skill_id, method)

    def answer_all_knowledge(
        self,
        assessment: dict,
        plan,
        *,
        correct: bool,
    ) -> None:
        for question in plan.knowledge_questions:
            selected = (
                question.correct_option_id
                if correct
                else wrong_option(question)
            )
            save_response(
                assessment["assessment_id"],
                self.profile["profile_id"],
                question.question_id,
                selected_answer=selected,
                db_path=self.db_path,
            )

    def test_create_and_get_assessment(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )

        self.assertEqual(assessment["status"], STATUS_IN_PROGRESS)
        self.assertEqual(assessment["assessment_key"], "skill:computer_literacy")
        self.assertEqual(assessment["assessment_type"], KNOWLEDGE)
        self.assertEqual(assessment["content_version"], CONTENT_VERSION)
        self.assertEqual(len(assessment["question_ids"]), 4)
        self.assertEqual(assessment["response_count"], 0)
        self.assertIsNone(assessment["score"])
        self.assertIsNone(assessment["proficiency_level"])

        loaded = get_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["assessment_id"], assessment["assessment_id"])
        self.assertIsNone(
            get_assessment(
                assessment["assessment_id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )
        )

    def test_save_correct_and_incorrect_responses(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        questions = plan.knowledge_questions

        first = save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            questions[0].question_id,
            selected_answer=questions[0].correct_option_id,
            db_path=self.db_path,
        )
        self.assertTrue(first["is_correct"])
        self.assertEqual(first["score_awarded"], 1.0)
        self.assertEqual(first["question_text"], questions[0].question)
        self.assertTrue(first["feedback"]["explanation"])

        second = save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            questions[1].question_id,
            selected_answer=wrong_option(questions[1]),
            db_path=self.db_path,
        )
        self.assertFalse(second["is_correct"])
        self.assertEqual(second["score_awarded"], 0.0)

        loaded = get_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            questions[0].question_id,
            db_path=self.db_path,
        )
        self.assertEqual(loaded["response_id"], first["response_id"])

    def test_duplicate_response_is_rejected(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        question = plan.knowledge_questions[0]

        save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            question.question_id,
            selected_answer=question.correct_option_id,
            db_path=self.db_path,
        )
        with self.assertRaises(DuplicateAssessmentResponse):
            save_response(
                assessment["assessment_id"],
                self.profile["profile_id"],
                question.question_id,
                selected_answer=question.correct_option_id,
                db_path=self.db_path,
            )

    def test_completion_requires_every_answer(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        question = plan.knowledge_questions[0]
        save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            question.question_id,
            selected_answer=question.correct_option_id,
            db_path=self.db_path,
        )

        with self.assertRaises(SkillAssessmentValidationError):
            complete_assessment(
                assessment["assessment_id"],
                self.profile["profile_id"],
                db_path=self.db_path,
            )

        history = list_assessments(
            self.profile["profile_id"], db_path=self.db_path
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], STATUS_IN_PROGRESS)
        self.assertEqual(history[0]["response_count"], 1)
        self.assertIsNone(history[0]["score"])

    def test_complete_scores_and_sets_proficiency_band(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        self.answer_all_knowledge(assessment, plan, correct=True)

        completed = complete_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(completed["status"], STATUS_COMPLETED)
        self.assertEqual(completed["score"], 100.0)
        self.assertEqual(
            completed["proficiency_level"],
            "Strong foundation",
        )
        self.assertIsNotNone(completed["completed_at"])

        repeated = complete_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(repeated["status"], STATUS_COMPLETED)
        self.assertEqual(repeated["score"], 100.0)

    def test_partial_score_uses_indicative_band(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        for index, question in enumerate(plan.knowledge_questions):
            selected = (
                question.correct_option_id
                if index < 2
                else wrong_option(question)
            )
            save_response(
                assessment["assessment_id"],
                self.profile["profile_id"],
                question.question_id,
                selected_answer=selected,
                db_path=self.db_path,
            )
        completed = complete_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(completed["score"], 50.0)
        self.assertEqual(completed["proficiency_level"], "Developing")

    def test_practical_only_assessment_has_no_score(self) -> None:
        plan = self.create_plan("customer_care", PRACTICAL)
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        question = plan.practical_questions[0]
        saved = save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            question.question_id,
            response_text=practical_text(),
            db_path=self.db_path,
        )
        self.assertIsNone(saved["is_correct"])
        self.assertIsNone(saved["score_awarded"])
        self.assertTrue(saved["feedback"]["marking_criteria"])

        completed = complete_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(completed["status"], STATUS_COMPLETED)
        self.assertIsNone(completed["score"])
        self.assertIsNone(completed["proficiency_level"])

        questions = get_assessment_questions(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        responses = get_responses(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        summary = build_result_summary(completed, questions, responses)
        self.assertFalse(summary["is_scored"])
        self.assertEqual(summary["practical_answered"], 1)
        self.assertEqual(len(summary["practical_review"]), 1)
        self.assertIsNone(summary["score_percent"])
        self.assertIsNone(summary["proficiency_label"])

    def test_combined_assessment_scores_knowledge_only(self) -> None:
        plan = self.create_plan("communication", COMBINED)
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        for index, question in enumerate(plan.knowledge_questions):
            save_response(
                assessment["assessment_id"],
                self.profile["profile_id"],
                question.question_id,
                selected_answer=(
                    question.correct_option_id
                    if index < 2
                    else wrong_option(question)
                ),
                db_path=self.db_path,
            )
        practical = plan.practical_questions[0]
        save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            practical.question_id,
            response_text=practical_text(),
            db_path=self.db_path,
        )
        completed = complete_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        self.assertEqual(completed["score"], 50.0)
        self.assertEqual(completed["proficiency_level"], "Developing")

        questions = get_assessment_questions(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        responses = get_responses(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        summary = build_result_summary(completed, questions, responses)
        self.assertEqual(summary["knowledge_total"], 4)
        self.assertEqual(summary["knowledge_correct"], 2)
        self.assertEqual(summary["practical_answered"], 1)
        self.assertEqual(summary["score_percent"], 50)

    def test_multiple_attempts_and_history(self) -> None:
        plan = self.create_plan()
        first = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        self.answer_all_knowledge(first, plan, correct=True)
        complete_assessment(
            first["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )

        second = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        self.answer_all_knowledge(second, plan, correct=False)
        complete_assessment(
            second["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )

        history = list_assessments(
            self.profile["profile_id"], db_path=self.db_path
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(
            {attempt["score"] for attempt in history},
            {0.0, 100.0},
        )

        comparable = list_comparable_assessments(
            self.profile["profile_id"],
            "skill:computer_literacy",
            KNOWLEDGE,
            CONTENT_VERSION,
            db_path=self.db_path,
        )
        self.assertEqual(len(comparable), 2)
        self.assertEqual(
            {attempt["score"] for attempt in comparable},
            {0.0, 100.0},
        )

    def test_filters_and_profile_isolation(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        self.assertEqual(
            list_assessments(
                self.profile["profile_id"],
                status=STATUS_IN_PROGRESS,
                assessment_key="skill:computer_literacy",
                assessment_type=KNOWLEDGE,
                content_version=CONTENT_VERSION,
                db_path=self.db_path,
            )[0]["assessment_id"],
            assessment["assessment_id"],
        )
        self.assertEqual(
            list_assessments(
                self.profile["profile_id"],
                status=STATUS_COMPLETED,
                db_path=self.db_path,
            ),
            [],
        )
        self.assertEqual(
            list_assessments(
                self.other_profile["profile_id"],
                db_path=self.db_path,
            ),
            [],
        )

        question = plan.knowledge_questions[0]
        with self.assertRaises(SkillAssessmentNotFound):
            save_response(
                assessment["assessment_id"],
                self.other_profile["profile_id"],
                question.question_id,
                selected_answer=question.correct_option_id,
                db_path=self.db_path,
            )
        with self.assertRaises(SkillAssessmentNotFound):
            complete_assessment(
                assessment["assessment_id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )
        with self.assertRaises(SkillAssessmentNotFound):
            delete_assessment(
                assessment["assessment_id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )

    def test_profile_delete_cascades_assessments_and_responses(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        question = plan.knowledge_questions[0]
        save_response(
            assessment["assessment_id"],
            self.profile["profile_id"],
            question.question_id,
            selected_answer=question.correct_option_id,
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
            assessment_count = connection.execute(
                "SELECT COUNT(*) FROM skill_assessments WHERE profile_id = ?",
                (self.profile["profile_id"],),
            ).fetchone()[0]
            response_count = connection.execute(
                "SELECT COUNT(*) FROM skill_assessment_responses WHERE assessment_id = ?",
                (assessment["assessment_id"],),
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(assessment_count, 0)
        self.assertEqual(response_count, 0)

    def test_practical_short_response_is_rejected(self) -> None:
        plan = self.create_plan("customer_care", PRACTICAL)
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        question = plan.practical_questions[0]
        with self.assertRaises(SkillAssessmentValidationError):
            save_response(
                assessment["assessment_id"],
                self.profile["profile_id"],
                question.question_id,
                response_text="Too short.",
                db_path=self.db_path,
            )
        self.assertEqual(
            get_responses(
                assessment["assessment_id"],
                self.profile["profile_id"],
                db_path=self.db_path,
            ),
            [],
        )

    def test_result_summary_explains_incorrect_answers(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        for index, question in enumerate(plan.knowledge_questions):
            save_response(
                assessment["assessment_id"],
                self.profile["profile_id"],
                question.question_id,
                selected_answer=(
                    question.correct_option_id
                    if index < 3
                    else wrong_option(question)
                ),
                db_path=self.db_path,
            )
        completed = complete_assessment(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        questions = get_assessment_questions(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        responses = get_responses(
            assessment["assessment_id"],
            self.profile["profile_id"],
            db_path=self.db_path,
        )
        summary = build_result_summary(completed, questions, responses)

        self.assertEqual(summary["score_percent"], 75)
        self.assertEqual(summary["proficiency_label"], "Competent foundation")
        self.assertEqual(len(summary["incorrect_answers"]), 1)
        self.assertTrue(summary["incorrect_answers"][0]["correct_answer"])
        self.assertTrue(summary["incorrect_answers"][0]["explanation"])
        self.assertEqual(summary["improve_areas"], ["Computer literacy"])
        self.assertEqual(summary["strong_areas"], [])
        self.assertTrue(summary["next_steps"])
        self.assertTrue(summary["pathway_names"])

    def test_migration_is_repeatable_and_preserves_existing_records(self) -> None:
        plan = self.create_plan()
        assessment = create_assessment(
            self.profile["profile_id"], plan, db_path=self.db_path
        )
        initialize_database(self.db_path)
        initialize_database(self.db_path)

        self.assertEqual(
            get_assessment(
                assessment["assessment_id"],
                self.profile["profile_id"],
                db_path=self.db_path,
            )["assessment_id"],
            assessment["assessment_id"],
        )

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
        finally:
            connection.close()

        self.assertIn("skill_assessments", tables)
        self.assertIn("skill_assessment_responses", tables)
        self.assertIn("idx_skill_assessments_profile_started", indexes)
        self.assertIn("idx_skill_assessments_profile_status", indexes)
        self.assertIn("idx_skill_assessments_target", indexes)
        self.assertIn("idx_skill_assessment_responses_order", indexes)


if __name__ == "__main__":
    unittest.main()
