import json
from hashlib import sha1

from app.modules.diagnosis.taxonomy import (
    CanonicalQuestionMatch,
    build_probe_features,
    build_probe_features_from_matches,
    canonicalize_questions,
    estimate_reference_similarity,
    normalize_question_text,
    normalize_topic_key,
    response_time_bucket,
    summarize_confidence_text,
)


def _build_training_record(
    *,
    payload: dict,
    matches: list[CanonicalQuestionMatch | None],
    canonical_question_ids: list[str | None],
    canonical_sources: list[str | None] | None = None,
    canonical_confidences: list[float | None] | None = None,
    unresolved_question_indices: list[int] | None = None,
) -> dict:
    subject_area = str(payload.get("subject_area") or "real_analysis")
    topic = str(payload.get("topic") or "")
    questions = [str(item) for item in payload.get("questions", [])]
    answers = [str(item) for item in payload.get("answers", [])]
    response_times = list(payload.get("response_times_sec") or [])
    confidence = summarize_confidence_text(payload.get("confidence_self_report"))
    combined_text_parts = [f"topic:{normalize_topic_key(topic)}", f"confidence:{confidence}"]
    for index, question in enumerate(questions):
        answer = answers[index] if index < len(answers) else ""
        bucket = response_time_bucket(response_times[index] if index < len(response_times) else None)
        canonical_id = canonical_question_ids[index] or f"unknown_q_{index}"
        combined_text_parts.append(
            " ".join(
                [
                    f"qid:{canonical_id}",
                    f"time:{bucket}",
                    f"question:{normalize_question_text(question)}",
                    f"answer:{answer.strip()}",
                ]
            )
        )

    labels = dict(payload.get("labels") or {})
    record = {
        "session_id": str(payload.get("session_id") or ""),
        "subject_area": subject_area,
        "topic": topic,
        "topic_key": normalize_topic_key(topic),
        "questions": questions,
        "answers": answers,
        "canonical_question_ids": canonical_question_ids,
        "canonical_sources": list(canonical_sources or [match.template_source if match else None for match in matches]),
        "canonical_confidences": list(canonical_confidences or [match.score if match else None for match in matches]),
        "response_times_sec": response_times,
        "confidence_bucket": confidence,
        "answer_lengths": [len(answer.split()) for answer in answers],
        "reference_similarity": [
            estimate_reference_similarity(answers[index] if index < len(answers) else "", match.reference_answers)
            if match else 0.0
            for index, match in enumerate(matches)
        ],
        "probe_features": build_probe_features_from_matches(matches),
        "combined_text": "\n".join(combined_text_parts),
        "unresolved_question_indices": list(unresolved_question_indices or []),
        "labels": {
            "learner_level": labels.get("learner_level"),
            "missing_prerequisites": list(labels.get("missing_prerequisites") or []),
            "misconception_labels": list(labels.get("misconception_labels") or []),
            "recommended_teaching_strategy": labels.get("recommended_teaching_strategy"),
        },
    }
    record["record_hash"] = sha1(
        json.dumps(
            {
                "topic": record["topic_key"],
                "canonical_question_ids": canonical_question_ids,
                "answers": answers,
                "labels": record["labels"],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return record


def build_training_record(payload: dict) -> dict:
    subject_area = str(payload.get("subject_area") or "real_analysis")
    topic = str(payload.get("topic") or "")
    questions = [str(item) for item in payload.get("questions", [])]
    payload_question_ids = list(payload.get("canonical_question_ids") or [])

    matches = canonicalize_questions(subject_area, topic, questions)
    canonical_question_ids = [
        match.template_id if match else (payload_question_ids[index] if index < len(payload_question_ids) else None)
        for index, match in enumerate(matches)
    ]
    return _build_training_record(
        payload=payload,
        matches=matches,
        canonical_question_ids=canonical_question_ids,
        canonical_sources=payload.get("canonical_sources"),
        canonical_confidences=payload.get("canonical_confidences"),
        unresolved_question_indices=[
            index for index, canonical_id in enumerate(canonical_question_ids) if not canonical_id
        ],
    )


def build_training_record_from_matches(
    payload: dict,
    *,
    matches: list[CanonicalQuestionMatch | None],
    canonical_question_ids: list[str | None],
    canonical_sources: list[str | None],
    canonical_confidences: list[float | None],
) -> dict:
    return _build_training_record(
        payload=payload,
        matches=matches,
        canonical_question_ids=canonical_question_ids,
        canonical_sources=canonical_sources,
        canonical_confidences=canonical_confidences,
        unresolved_question_indices=[
            index for index, canonical_id in enumerate(canonical_question_ids) if not canonical_id
        ],
    )
