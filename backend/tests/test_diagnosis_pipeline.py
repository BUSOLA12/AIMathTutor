import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["DEBUG"] = "false"

from fastapi import HTTPException

from app.api.routes.diagnosis import get_questions, submit_answers
from app.models.schemas import (
    DiagnosticAnswerRequest,
    DiagnosisResult,
    LearnerLevel,
    SessionState,
    TeachingStrategy,
)
from app.modules.diagnosis.background import _process_generated_question_analysis
from app.modules.diagnosis.dataset import build_training_record
from app.modules.diagnosis.handler import DiagnosticQuestionBatchPayload
from app.modules.diagnosis.ml import ShadowDiagnosisOutput
from app.modules.diagnosis.taxonomy import (
    build_probe_features,
    canonicalize_question,
    canonicalize_question_with_overlay,
)


class DiagnosisTaxonomyTests(unittest.TestCase):
    def test_canonicalize_question_matches_topic_template(self):
        match = canonicalize_question(
            "real_analysis",
            "uniform continuity",
            "What is the difference between pointwise and uniform continuity?",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.template_id, "uc.pointwise_vs_uniform")
        self.assertEqual(match.topic_family, "continuity")

    def test_probe_features_include_skill_and_misconception_weights(self):
        matches = [
            canonicalize_question(
                "real_analysis",
                "convergent sequence implies bounded",
                "What does it mean for a sequence to be bounded?",
            ),
            canonicalize_question(
                "real_analysis",
                "convergent sequence implies bounded",
                "Do you think a convergent sequence could be unbounded? Why or why not?",
            ),
        ]

        features = build_probe_features("real_analysis", "convergent sequence implies bounded", matches)
        self.assertIn("boundedness", features)
        self.assertIn("misconception::wrong_implication", features)
        self.assertGreater(features["boundedness"], 0.0)


class OverlayTaxonomyTests(unittest.IsolatedAsyncioTestCase):
    async def test_overlay_template_is_checked_before_file_taxonomy(self):
        overlay_template = SimpleNamespace(
            template_id="overlay.uniform.special",
            topic_key="uniform_continuity",
            topic_family="continuity",
            question_role="concept_check",
            text="What is the difference between pointwise and uniform continuity?",
            skills={"uniform_continuity": 1.0},
            misconception_probes={"quantifier_confusion": 0.8},
            reference_answers=["A good answer distinguishes the two notions."],
        )

        with patch(
            "app.modules.diagnosis.taxonomy.list_overlay_templates",
            AsyncMock(return_value=[(overlay_template, ["How is pointwise continuity different from uniform continuity?"])]),
        ):
            match = await canonicalize_question_with_overlay(
                object(),
                "real_analysis",
                "uniform continuity",
                "What is the difference between pointwise and uniform continuity?",
            )

        self.assertIsNotNone(match)
        self.assertEqual(match.template_id, "overlay.uniform.special")
        self.assertEqual(match.template_source, "overlay")


class DiagnosisDatasetTests(unittest.TestCase):
    def test_build_training_record_derives_canonical_ids_and_combined_text(self):
        record = build_training_record(
            {
                "session_id": "sess-1",
                "subject_area": "real_analysis",
                "topic": "uniform continuity",
                "questions": [
                    "What is the definition of continuity at a point?",
                    "Would you like intuition first or the formal definition first?",
                ],
                "answers": [
                    "It means close inputs give close outputs.",
                    "Intuition first.",
                ],
                "response_times_sec": [9.4, 5.2],
                "confidence_self_report": "low confidence",
                "labels": {
                    "learner_level": "beginner_intermediate",
                    "missing_prerequisites": ["continuity"],
                    "misconception_labels": ["definition_confusion"],
                    "recommended_teaching_strategy": "intuition_first",
                },
            }
        )

        self.assertEqual(record["canonical_question_ids"][0], "uc.continuity.point_definition")
        self.assertEqual(record["confidence_bucket"], "low")
        self.assertIn("qid:uc.continuity.point_definition", record["combined_text"])
        self.assertIn("continuity", record["probe_features"])


class DiagnosisBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_question_analysis_auto_promotes_high_confidence_questions(self):
        batch = SimpleNamespace(
            id=11,
            subject_area="real_analysis",
            topic="uniform continuity",
            topic_key="uniform_continuity",
            questions=["What is the difference between pointwise and uniform continuity?"],
            canonicalization_status="pending",
        )
        db = AsyncMock()
        overlay = SimpleNamespace(id=7, template_id="overlay.compactness.abc123")

        with patch(
            "app.modules.diagnosis.background.get_question_batch",
            AsyncMock(return_value=batch),
        ), patch(
            "app.modules.diagnosis.background.find_best_question_match_with_overlay",
            AsyncMock(return_value=None),
        ), patch(
            "app.modules.diagnosis.background.create_overlay_template",
            AsyncMock(return_value=overlay),
        ) as create_overlay_mock, patch(
            "app.modules.diagnosis.background.upsert_canonicalization_audit",
            AsyncMock(),
        ), patch(
            "app.modules.diagnosis.background.update_question_batch_canonicalization",
            AsyncMock(),
        ) as update_batch_mock, patch(
            "app.modules.diagnosis.background.settings.diagnosis_overlay_auto_promote_threshold",
            0.85,
        ), patch(
            "app.modules.diagnosis.background.settings.diagnosis_overlay_review_threshold",
            0.75,
        ):
            await _process_generated_question_analysis(db, batch.id)

        create_overlay_mock.assert_awaited_once()
        self.assertTrue(create_overlay_mock.await_args.kwargs["active"])
        self.assertEqual(create_overlay_mock.await_args.kwargs["promotion_mode"], "auto")
        self.assertEqual(update_batch_mock.await_args.kwargs["canonicalization_status"], "completed")

    async def test_generated_question_analysis_leaves_low_confidence_questions_unresolved(self):
        batch = SimpleNamespace(
            id=12,
            subject_area="real_analysis",
            topic="unknown topic",
            topic_key="unknown_topic",
            questions=["Explain the vibes of this topic."],
            canonicalization_status="pending",
        )
        db = AsyncMock()

        with patch(
            "app.modules.diagnosis.background.get_question_batch",
            AsyncMock(return_value=batch),
        ), patch(
            "app.modules.diagnosis.background.find_best_question_match_with_overlay",
            AsyncMock(return_value=None),
        ), patch(
            "app.modules.diagnosis.background.create_overlay_template",
            AsyncMock(),
        ) as create_overlay_mock, patch(
            "app.modules.diagnosis.background.upsert_canonicalization_audit",
            AsyncMock(),
        ), patch(
            "app.modules.diagnosis.background.update_question_batch_canonicalization",
            AsyncMock(),
        ) as update_batch_mock, patch(
            "app.modules.diagnosis.background.settings.diagnosis_overlay_auto_promote_threshold",
            0.95,
        ), patch(
            "app.modules.diagnosis.background.settings.diagnosis_overlay_review_threshold",
            0.8,
        ):
            await _process_generated_question_analysis(db, batch.id)

        create_overlay_mock.assert_not_awaited()
        self.assertEqual(update_batch_mock.await_args.kwargs["canonicalization_status"], "unresolved")
        self.assertEqual(update_batch_mock.await_args.kwargs["canonical_question_ids"], [None])


class DiagnosisRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_questions_persists_llm_batch_and_enqueues_background_analysis(self):
        state = SessionState(
            session_id="sess-1",
            topic="compactness",
            target_type="concept",
            subject_area="real_analysis",
            phase="diagnosing",
        )
        batch = SimpleNamespace(id=41, questions=["Q1?", "Q2?", "Q3?", "Q4?"], status="issued")
        db = AsyncMock()

        with patch(
            "app.api.routes.diagnosis.get_session_state",
            AsyncMock(return_value=state),
        ), patch(
            "app.api.routes.diagnosis.get_diagnosis_question_batch_ref",
            AsyncMock(return_value=None),
        ), patch(
            "app.api.routes.diagnosis.get_latest_issued_question_batch",
            AsyncMock(return_value=None),
        ), patch(
            "app.api.routes.diagnosis.generate_diagnostic_question_batch",
            AsyncMock(return_value=DiagnosticQuestionBatchPayload(
                questions=["Q1?", "Q2?", "Q3?", "Q4?"],
                source="llm_generated",
            )),
        ), patch(
            "app.api.routes.diagnosis.create_question_batch",
            AsyncMock(return_value=batch),
        ) as create_batch_mock, patch(
            "app.api.routes.diagnosis.save_diagnosis_question_batch_ref",
            AsyncMock(),
        ) as save_ref_mock, patch(
            "app.api.routes.diagnosis.enqueue_diagnosis_background_job",
            AsyncMock(return_value=(SimpleNamespace(id=91), True)),
        ) as enqueue_mock:
            response = await get_questions("sess-1", db=db)

        self.assertEqual(response.questions, ["Q1?", "Q2?", "Q3?", "Q4?"])
        create_batch_mock.assert_awaited_once()
        self.assertEqual(create_batch_mock.await_args.kwargs["source"], "llm_generated")
        save_ref_mock.assert_awaited_once_with("sess-1", 41)
        enqueue_mock.assert_awaited_once()
        self.assertEqual(enqueue_mock.await_args.kwargs["question_batch_id"], 41)
        db.commit.assert_awaited_once()

    async def test_submit_answers_reuses_stored_batch_and_logs_it(self):
        request = DiagnosticAnswerRequest(
            session_id="sess-1",
            answers=[
                "It means the sequence gets close to a limit.",
                "A bounded sequence can still oscillate.",
                "For every epsilon there is a delta.",
                "Example first.",
            ],
            response_times_sec=[8.0, 12.0, 14.0, 6.0],
            confidence_self_report="medium",
        )
        state = SessionState(
            session_id="sess-1",
            topic="uniform continuity",
            target_type="concept",
            subject_area="real_analysis",
            phase="diagnosing",
        )
        live_result = DiagnosisResult(
            session_id="sess-1",
            learner_level=LearnerLevel.beginner_intermediate,
            missing_prerequisites=["continuity"],
            misconception_labels=["definition_confusion"],
            recommended_teaching_strategy=TeachingStrategy.example_first,
            diagnostic_confidence=0.81,
        )
        shadow = ShadowDiagnosisOutput(
            source="sklearn_text_baseline",
            status="ready",
            prediction={
                "learner_level": "beginner_intermediate",
                "missing_prerequisites": ["continuity"],
                "misconception_labels": ["definition_confusion"],
                "recommended_teaching_strategy": "example_first",
                "diagnostic_confidence": 0.74,
            },
            confidence=0.74,
        )
        batch = SimpleNamespace(
            id=55,
            subject_area="real_analysis",
            source="llm_generated",
            status="issued",
            questions=[
                "What is the definition of continuity at a point?",
                "What is the difference between pointwise and uniform continuity?",
                "Can you give an example of a continuous function that is not uniformly continuous?",
                "Would you like intuition first or the formal definition first?",
            ],
            canonical_question_ids=[
                "uc.continuity.point_definition",
                "uc.pointwise_vs_uniform",
                None,
                None,
            ],
        )
        run = SimpleNamespace(id=77)
        db = AsyncMock()

        with patch(
            "app.api.routes.diagnosis.get_session_state",
            AsyncMock(return_value=state),
        ), patch(
            "app.api.routes.diagnosis.get_diagnosis_question_batch_ref",
            AsyncMock(return_value=55),
        ), patch(
            "app.api.routes.diagnosis.get_question_batch",
            AsyncMock(return_value=batch),
        ), patch(
            "app.api.routes.diagnosis.get_latest_issued_question_batch",
            AsyncMock(),
        ) as latest_issued_mock, patch(
            "app.api.routes.diagnosis.get_latest_question_batch",
            AsyncMock(),
        ) as latest_any_mock, patch(
            "app.api.routes.diagnosis.run_diagnosis_with_shadow",
            AsyncMock(return_value=(live_result, "llm_fast", shadow)),
        ), patch(
            "app.api.routes.diagnosis.persist_diagnosis_submission",
            AsyncMock(return_value=run),
        ) as persist_mock, patch(
            "app.api.routes.diagnosis.mark_question_batch_submitted",
            AsyncMock(),
        ) as mark_batch_mock, patch(
            "app.api.routes.diagnosis.delete_diagnosis_question_batch_ref",
            AsyncMock(),
        ) as delete_ref_mock, patch(
            "app.api.routes.diagnosis.enqueue_diagnosis_background_job",
            AsyncMock(return_value=(SimpleNamespace(id=92), True)),
        ) as enqueue_mock, patch(
            "app.api.routes.diagnosis.save_session_state",
            AsyncMock(),
        ) as save_mock:
            result = await submit_answers(request, db=db)

        self.assertEqual(result.learner_level, LearnerLevel.beginner_intermediate)
        latest_issued_mock.assert_not_awaited()
        latest_any_mock.assert_not_awaited()
        persist_mock.assert_awaited_once()
        persisted = persist_mock.await_args.kwargs
        self.assertEqual(persisted["question_batch_id"], 55)
        self.assertEqual(
            persisted["questions"],
            batch.questions,
        )
        self.assertEqual(
            persisted["canonical_question_ids"],
            [
                "uc.continuity.point_definition",
                "uc.pointwise_vs_uniform",
                None,
                None,
            ],
        )
        mark_batch_mock.assert_awaited_once_with(db, batch)
        delete_ref_mock.assert_awaited_once_with("sess-1")
        enqueue_mock.assert_awaited_once()
        self.assertEqual(enqueue_mock.await_args.kwargs["diagnosis_run_id"], 77)
        save_mock.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_submit_answers_rejects_missing_batch_instead_of_regenerating(self):
        request = DiagnosticAnswerRequest(
            session_id="sess-404",
            answers=["a", "b", "c", "d"],
        )
        state = SessionState(
            session_id="sess-404",
            topic="new topic",
            target_type="concept",
            subject_area="real_analysis",
            phase="diagnosing",
        )
        db = AsyncMock()

        with patch(
            "app.api.routes.diagnosis.get_session_state",
            AsyncMock(return_value=state),
        ), patch(
            "app.api.routes.diagnosis.get_diagnosis_question_batch_ref",
            AsyncMock(return_value=None),
        ), patch(
            "app.api.routes.diagnosis.get_latest_issued_question_batch",
            AsyncMock(return_value=None),
        ), patch(
            "app.api.routes.diagnosis.get_latest_question_batch",
            AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as context:
                await submit_answers(request, db=db)

        self.assertEqual(context.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
