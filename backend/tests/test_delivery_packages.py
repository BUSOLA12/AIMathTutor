import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ["DEBUG"] = "false"

from app.models.schemas import AudioMarker, DeliveryPackage, DeliveryStep, ResumeCursor
from app.modules.tutoring_delivery.delivery import (
    StepGenerationResult,
    _clean_spoken_text,
    _merge_markers,
    _sanitize_steps,
    build_section_package,
    build_resume_package,
)


class DeliveryPackageTests(unittest.IsolatedAsyncioTestCase):
    def test_sanitize_steps_rewrites_invalid_highlight_targets(self):
        steps = _sanitize_steps(
            [
                {
                    "kind": "heading",
                    "display_text": "Heading",
                    "spoken_text": "Heading",
                    "reveal_mode": "token",
                },
                {
                    "kind": "highlight",
                    "display_text": "Focus here",
                    "spoken_text": "Focus here",
                    "reveal_mode": "instant",
                    "target": "previous",
                },
            ],
            section="intro",
            fallback_factory=lambda: [],
        )

        self.assertFalse(steps.used_fallback)
        self.assertEqual(len(steps.steps), 2)
        self.assertEqual(steps.steps[1].target, "intro_step_1")

    def test_sanitize_steps_aligns_text_display_with_spoken_text(self):
        steps = _sanitize_steps(
            [
                {
                    "kind": "text",
                    "display_text": "Short board summary",
                    "spoken_text": "Longer narration that should also appear on the board.",
                    "reveal_mode": "token",
                },
                {
                    "kind": "math",
                    "display_text": "$$H_0(X)=\\mathbb{Z}$$",
                    "spoken_text": "This formula says the zeroth homology group is the integers.",
                    "reveal_mode": "line",
                },
            ],
            section="intro",
            fallback_factory=lambda: [],
        )

        self.assertFalse(steps.used_fallback)
        self.assertEqual(
            steps.steps[0].display_text,
            "Longer narration that should also appear on the board.",
        )
        self.assertEqual(steps.steps[1].display_text, "$$H_0(X)=\\mathbb{Z}$$")

    def test_merge_markers_keeps_step_order_monotonic(self):
        steps = [
            DeliveryStep(step_id="a", kind="text", display_text="A", spoken_text="A", reveal_mode="token"),
            DeliveryStep(step_id="b", kind="text", display_text="B", spoken_text="B", reveal_mode="token"),
            DeliveryStep(step_id="c", kind="math", display_text="$$x$$", spoken_text="x", reveal_mode="line"),
        ]
        merged = _merge_markers(
            steps,
            [
                AudioMarker(name="a", time_ms=900),
                AudioMarker(name="b", time_ms=150),
                AudioMarker(name="c", time_ms=2200),
            ],
            audio_duration_ms=3000,
        )

        self.assertEqual([marker.name for marker in merged], ["a", "b", "c"])
        self.assertLessEqual(merged[0].time_ms, merged[1].time_ms)
        self.assertLessEqual(merged[1].time_ms, merged[2].time_ms)

    def test_clean_spoken_text_removes_raw_latex_markers(self):
        cleaned = _clean_spoken_text(
            "The first homology group is $H_1(X)$ and $$\\mathbb{Z}$$ appears here."
        )
        self.assertNotIn("$", cleaned)
        self.assertNotIn("\\mathbb", cleaned)
        self.assertIn("H sub 1 of X", cleaned)
        self.assertIn("the integers", cleaned)

    async def test_build_section_package_does_not_prefetch_fallback_output(self):
        generated = StepGenerationResult(
            steps=[
                DeliveryStep(step_id="intro_step_1", kind="heading", display_text="Intro", spoken_text="Intro", reveal_mode="token"),
                DeliveryStep(step_id="intro_step_2", kind="text", display_text="Body", spoken_text="Body", reveal_mode="token"),
            ],
            used_fallback=True,
        )

        with patch(
            "app.modules.tutoring_delivery.delivery._generate_steps_with_llm",
            new=AsyncMock(return_value=generated),
        ), patch(
            "app.modules.tutoring_delivery.delivery._finalize_package",
            new=AsyncMock(return_value="pkg"),
        ) as finalize:
            result = await build_section_package(
                session_id="sess-1",
                topic="homology",
                learner_level="beginner",
                teaching_strategy="intuition_first",
                section="intuition",
                messages=[],
                section_index=2,
            )

        self.assertEqual(result, "pkg")
        self.assertIsNone(finalize.await_args.kwargs["section_index"])

    async def test_build_section_package_keeps_prefetch_key_for_generated_output(self):
        generated = StepGenerationResult(
            steps=[
                DeliveryStep(step_id="intro_step_1", kind="heading", display_text="Intro", spoken_text="Intro", reveal_mode="token"),
                DeliveryStep(step_id="intro_step_2", kind="text", display_text="Body", spoken_text="Body", reveal_mode="token"),
            ],
            used_fallback=False,
        )

        with patch(
            "app.modules.tutoring_delivery.delivery._generate_steps_with_llm",
            new=AsyncMock(return_value=generated),
        ), patch(
            "app.modules.tutoring_delivery.delivery._finalize_package",
            new=AsyncMock(return_value="pkg"),
        ) as finalize:
            result = await build_section_package(
                session_id="sess-1",
                topic="homology",
                learner_level="beginner",
                teaching_strategy="intuition_first",
                section="intuition",
                messages=[],
                section_index=2,
            )

        self.assertEqual(result, "pkg")
        self.assertEqual(finalize.await_args.kwargs["section_index"], 2)

    async def test_build_resume_package_keeps_remaining_steps_and_offsets(self):
        original = DeliveryPackage(
            package_id="pkg-1",
            section="intuition",
            steps=[
                DeliveryStep(step_id="s1", kind="heading", display_text="Intro", spoken_text="Intro", reveal_mode="token"),
                DeliveryStep(step_id="s2", kind="text", display_text="Body", spoken_text="Body", reveal_mode="token"),
                DeliveryStep(step_id="s3", kind="math", display_text="$$x_n$$", spoken_text="x n", reveal_mode="line"),
            ],
            audio_url="/api/session/sess/audio/clip-1",
            audio_provider="mock",
            audio_duration_ms=3600,
            markers=[
                AudioMarker(name="s1", time_ms=0),
                AudioMarker(name="s2", time_ms=900),
                AudioMarker(name="s3", time_ms=2100),
            ],
            transcript="Intro\n\nBody\n\nx n",
            resume_cursor=ResumeCursor(
                package_id="pkg-1",
                section="intuition",
                step_id="s1",
                audio_offset_ms=0,
            ),
        )

        async def fake_finalize(session_id, **kwargs):
            return DeliveryPackage(
                package_id="pkg-2",
                section=kwargs["section"],
                steps=list(kwargs["steps"]),
                audio_url=kwargs["audio_url"],
                audio_provider=kwargs.get("audio_provider"),
                audio_duration_ms=kwargs["audio_duration_ms"],
                markers=list(kwargs["markers"]),
                transcript="\n\n".join(step.spoken_text for step in kwargs["steps"]),
                resume_cursor=ResumeCursor(
                    package_id="pkg-2",
                    section=kwargs["section"],
                    step_id=kwargs["steps"][0].step_id,
                    audio_offset_ms=kwargs["base_audio_offset_ms"],
                ),
            )

        with patch(
            "app.modules.tutoring_delivery.delivery.get_delivery_package",
            new=AsyncMock(return_value=original),
        ), patch(
            "app.modules.tutoring_delivery.delivery._finalize_package",
            new=AsyncMock(side_effect=fake_finalize),
        ):
            resumed = await build_resume_package(
                "sess-1",
                ResumeCursor(
                    package_id="pkg-1",
                    section="intuition",
                    step_id="s2",
                    audio_offset_ms=900,
                ),
            )

        self.assertIsNotNone(resumed)
        self.assertEqual([step.step_id for step in resumed.steps], ["s2", "s3"])
        self.assertEqual(resumed.audio_provider, "mock")
        self.assertEqual(resumed.resume_cursor.audio_offset_ms, 900)
        self.assertEqual([marker.time_ms for marker in resumed.markers], [0, 1200])


if __name__ == "__main__":
    unittest.main()
