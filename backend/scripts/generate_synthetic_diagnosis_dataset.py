import asyncio
import json
import math
import random
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.llm import get_llm
from app.modules.diagnosis.dataset import build_training_record
from app.modules.diagnosis.taxonomy import load_diagnosis_taxonomy, normalize_topic_key


SCENARIOS = [
    {
        "name": "correct_concise",
        "learner_level": "intermediate",
        "missing_prerequisites": [],
        "misconception_labels": [],
        "recommended_teaching_strategy": "formal_definition_first",
        "confidence": "high",
        "generation_brief": "The student is solid and mathematically correct, but concise rather than verbose.",
    },
    {
        "name": "correct_intuitive",
        "learner_level": "beginner_intermediate",
        "missing_prerequisites": [],
        "misconception_labels": [],
        "recommended_teaching_strategy": "intuition_first",
        "confidence": "medium",
        "generation_brief": "The student mostly understands the topic, but explains ideas informally and leans on intuition.",
    },
    {
        "name": "partial",
        "learner_level": "beginner_intermediate",
        "missing_prerequisites": ["definition_confusion_placeholder"],
        "misconception_labels": ["definition_confusion"],
        "recommended_teaching_strategy": "example_first",
        "confidence": "low",
        "generation_brief": "The student knows fragments of the topic, but misses formal details and cannot state full definitions cleanly.",
    },
    {
        "name": "misconception",
        "learner_level": "beginner",
        "missing_prerequisites": ["gap_placeholder"],
        "misconception_labels": ["wrong_implication"],
        "recommended_teaching_strategy": "prerequisite_micro_lesson_first",
        "confidence": "low",
        "generation_brief": "The student sounds somewhat confident, but makes a clear conceptual mistake that should surface in at least one answer.",
    },
    {
        "name": "vague_guessing",
        "learner_level": "beginner",
        "missing_prerequisites": ["gap_placeholder"],
        "misconception_labels": ["intuition_gap"],
        "recommended_teaching_strategy": "example_first",
        "confidence": "low",
        "generation_brief": "The student is unsure, vague, and often asks for examples rather than giving precise mathematical answers.",
    },
    {
        "name": "advanced_proof_oriented",
        "learner_level": "advanced",
        "missing_prerequisites": [],
        "misconception_labels": [],
        "recommended_teaching_strategy": "proof_first",
        "confidence": "high",
        "generation_brief": "The student is mathematically mature, writes clean proofs, cites theorems precisely, and wants the rigorous proof before anything else.",
    },
    {
        "name": "advanced_formal",
        "learner_level": "advanced",
        "missing_prerequisites": [],
        "misconception_labels": [],
        "recommended_teaching_strategy": "formal_definition_first",
        "confidence": "high",
        "generation_brief": "The student has strong formal background, uses epsilon-delta or abstract notation naturally, and prefers formal definitions over intuition.",
    },
]

PREFERENCE_RESPONSES = {
    "intuition_first": ["I want intuition first.", "Please start with the intuition."],
    "example_first": ["A worked example first would help.", "Show me an example first."],
    "formal_definition_first": ["Start with the formal definition.", "I prefer the formal statement first."],
    "proof_first": ["I want the proof first.", "Start with the proof."],
    "prerequisite_micro_lesson_first": [
        "Please review the prerequisites first.",
        "I need a quick prerequisite refresher first.",
    ],
}

ALLOWED_CONFIDENCE = {"high", "medium", "low"}

SYNTHETIC_BATCH_PROMPT = """You are generating synthetic diagnosis training data for a university mathematics tutor.

Return ONLY a valid JSON array with exactly {count} objects.

Each object must have exactly these keys:
- "answers": an array of exactly {question_count} strings, in the same order as the diagnosis questions
- "response_times_sec": an array of exactly {question_count} positive numbers
- "confidence_self_report": one of "high", "medium", or "low"

Context:
- subject_area: {subject_area}
- topic: {topic}
- topic_family: {topic_family}
- scenario_name: {scenario_name}
- scenario_brief: {scenario_brief}
- required diagnosis labels for every generated example: {label_plan_json}

Exact diagnosis questions and template metadata:
{question_templates_json}

Rules:
1. Each object should represent one coherent student profile.
2. The answers must match the required diagnosis labels and the scenario brief.
3. If missing_prerequisites or misconception_labels are non-empty, make those weaknesses visible in at least one answer.
4. The preference answer must align with recommended_teaching_strategy.
5. Do not copy the reference answers verbatim in every example. Vary phrasing naturally across the array.
6. Keep answers short to medium length, suitable for a quick diagnosis interaction.
7. Keep response_times_sec realistic, roughly between 4 and 40 seconds.
8. Use ASCII only. Do not include markdown or commentary.

Return only the JSON array."""


def _pick_gap(template: dict) -> str:
    skills = sorted(dict(template.get("skills", {})).items(), key=lambda item: item[1], reverse=True)
    return skills[0][0] if skills else "notation"


def _pick_misconception(template: dict) -> str:
    probes = sorted(
        dict(template.get("misconception_probes", {})).items(),
        key=lambda item: item[1],
        reverse=True,
    )
    return probes[0][0] if probes else "definition_confusion"


def _resolve_label_plan(taxonomy: dict, question_templates: list[dict], scenario: dict) -> dict:
    missing_prerequisites = list(scenario["missing_prerequisites"])
    if missing_prerequisites and missing_prerequisites[0] == "definition_confusion_placeholder":
        missing_prerequisites = [_pick_gap(question_templates[0])]
    if missing_prerequisites and missing_prerequisites[0] == "gap_placeholder":
        missing_prerequisites = [_pick_gap(question_templates[min(1, len(question_templates) - 1)])]

    misconception_labels = list(scenario["misconception_labels"])
    if misconception_labels == ["wrong_implication"] and "wrong_implication" not in taxonomy["misconception_labels"]:
        misconception_labels = [_pick_misconception(question_templates[0])]

    return {
        "learner_level": scenario["learner_level"],
        "missing_prerequisites": missing_prerequisites,
        "misconception_labels": misconception_labels,
        "recommended_teaching_strategy": scenario["recommended_teaching_strategy"],
        "confidence_self_report": scenario["confidence"],
    }


def _answer_for_template(template: dict, scenario: dict) -> str:
    role = template.get("question_role", "concept_check")
    reference_answers = list(template.get("reference_answers", []))
    reference = reference_answers[0] if reference_answers else "I am not completely sure."
    misconception = _pick_misconception(template)

    if role == "preference":
        strategy = scenario["recommended_teaching_strategy"]
        options = PREFERENCE_RESPONSES.get(strategy, ["Intuition first."])
        return random.choice(options)

    if scenario["name"] == "correct_concise":
        return reference

    if scenario["name"] == "correct_intuitive":
        return reference.replace("arbitrarily close", "really close").replace("delta", "a small input window")

    if scenario["name"] == "partial":
        if role in {"definition_probe", "concept_check"}:
            return "I know the basic idea, but I cannot state the full definition carefully."
        return "I think it is mostly true, but I am not sure how to justify it."

    if scenario["name"] == "misconception":
        if misconception == "wrong_implication":
            return "Yes, that should always be true because the condition looks strong enough."
        if misconception == "quantifier_confusion":
            return "You choose epsilon after seeing delta, so the order is flexible."
        if misconception == "notation_confusion":
            return "I mix up the symbols, but I think they mean almost the same thing."
        return "I think the definition says roughly the opposite direction."

    return "I am guessing a little here and would need an example first."


def _build_rule_payload(
    *,
    args,
    question_templates: list[dict],
    scenario: dict,
    label_plan: dict,
    serial: int,
    topic_key: str,
) -> dict:
    return {
        "session_id": f"synthetic-{normalize_topic_key(topic_key)}-{serial}",
        "subject_area": args.subject_area,
        "topic": topic_key.replace("_", " "),
        "canonical_question_ids": [template["template_id"] for template in question_templates],
        "questions": [template["text"] for template in question_templates],
        "answers": [_answer_for_template(template, scenario) for template in question_templates],
        "response_times_sec": [
            round(random.uniform(5.0, 12.0), 2) if scenario["confidence"] == "high"
            else round(random.uniform(8.0, 30.0), 2)
            for _ in question_templates
        ],
        "confidence_self_report": label_plan["confidence_self_report"],
        "labels": {
            "learner_level": label_plan["learner_level"],
            "missing_prerequisites": list(label_plan["missing_prerequisites"]),
            "misconception_labels": list(label_plan["misconception_labels"]),
            "recommended_teaching_strategy": label_plan["recommended_teaching_strategy"],
        },
    }


def _clamp_time(value, default_seconds: float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = default_seconds

    if not math.isfinite(seconds):
        seconds = default_seconds
    return round(min(60.0, max(3.0, seconds)), 2)


def _sanitize_generated_example(
    payload: dict,
    *,
    question_count: int,
    default_confidence: str,
) -> dict | None:
    if not isinstance(payload, dict):
        return None

    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, list):
        return None
    answers = [str(item).strip() for item in raw_answers if str(item).strip()]
    if not answers:
        return None
    if len(answers) < question_count:
        answers.extend(["I am not fully sure."] * (question_count - len(answers)))
    answers = answers[:question_count]

    raw_times = payload.get("response_times_sec")
    if isinstance(raw_times, list):
        response_times = [
            _clamp_time(raw_times[index] if index < len(raw_times) else None, 12.0 + (index * 1.5))
            for index in range(question_count)
        ]
    else:
        response_times = [_clamp_time(None, 12.0 + (index * 1.5)) for index in range(question_count)]

    confidence = str(payload.get("confidence_self_report") or default_confidence).strip().lower()
    if confidence not in ALLOWED_CONFIDENCE:
        confidence = default_confidence

    return {
        "answers": answers,
        "response_times_sec": response_times,
        "confidence_self_report": confidence,
    }


def _question_templates_for_prompt(question_templates: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for template in question_templates:
        prepared.append(
            {
                "template_id": template.get("template_id"),
                "text": template.get("text"),
                "question_role": template.get("question_role", "concept_check"),
                "skills": dict(template.get("skills", {})),
                "misconception_probes": dict(template.get("misconception_probes", {})),
                "reference_answers": list(template.get("reference_answers", [])),
            }
        )
    return prepared


def _parse_retry_after(error_msg: str) -> float | None:
    """Extract the retry-after delay (seconds) from a provider rate-limit message."""
    match = re.search(r"(?:try again|retry) in ([\d.]+)(ms|s)", error_msg, re.IGNORECASE)
    if not match:
        return None
    delay = float(match.group(1))
    return delay / 1000 if match.group(2) == "ms" else delay


async def _generate_llm_batch(
    chain,
    *,
    args,
    topic_key: str,
    topic_entry: dict,
    question_templates: list[dict],
    scenario: dict,
    label_plan: dict,
    count: int,
) -> list[dict]:
    question_count = len(question_templates)
    prompt_payload = {
        "subject_area": args.subject_area,
        "topic": topic_key.replace("_", " "),
        "topic_family": topic_entry.get("family", "general"),
        "scenario_name": scenario["name"],
        "scenario_brief": scenario["generation_brief"],
        "label_plan_json": json.dumps(label_plan, ensure_ascii=True),
        "question_templates_json": json.dumps(
            _question_templates_for_prompt(question_templates),
            ensure_ascii=True,
            indent=2,
        ),
        "count": count,
        "question_count": question_count,
    }

    last_error: Exception | None = None
    for _ in range(args.max_retries):
        try:
            result = await chain.ainvoke(prompt_payload)
            if not isinstance(result, list):
                raise ValueError("LLM synthetic generator did not return a JSON list.")

            examples: list[dict] = []
            for item in result:
                example = _sanitize_generated_example(
                    item,
                    question_count=question_count,
                    default_confidence=str(label_plan["confidence_self_report"]),
                )
                if example is not None:
                    examples.append(example)
            if len(examples) >= count:
                return examples[:count]
            if examples:
                return examples
            raise ValueError("LLM synthetic generator returned no usable examples.")
        except Exception as error:  # pragma: no cover - network/provider variability
            last_error = error
            retry_after = _parse_retry_after(str(error))
            if retry_after is not None:
                await asyncio.sleep(retry_after + 1.0)

    if args.fallback_generator == "rule":
        return []
    raise RuntimeError(f"LLM synthetic generation failed for topic '{topic_key}' / scenario '{scenario['name']}'.") from last_error


def _dedupe(records: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen_hashes: set[str] = set()
    for record in records:
        if record["record_hash"] in seen_hashes:
            continue
        combined = record["combined_text"]
        if any(
            record["topic_key"] == existing["topic_key"]
            and SequenceMatcher(None, combined, existing["combined_text"]).ratio() >= 0.96
            for existing in unique
        ):
            continue
        seen_hashes.add(record["record_hash"])
        unique.append(record)
    return unique


def _write_records(output_path: Path, records: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _generate_records_rule(args, taxonomy: dict) -> list[dict]:
    topics = taxonomy.get("topics", {})
    records: list[dict] = []
    serial = 0

    while len(records) < args.target_count:
        for topic_key, topic_entry in topics.items():
            for scenario in SCENARIOS:
                serial += 1
                question_templates = list(topic_entry.get("question_templates", []))
                label_plan = _resolve_label_plan(taxonomy, question_templates, scenario)
                payload = _build_rule_payload(
                    args=args,
                    question_templates=question_templates,
                    scenario=scenario,
                    label_plan=label_plan,
                    serial=serial,
                    topic_key=topic_key,
                )
                records.append(build_training_record(payload))
                if len(records) >= args.target_count:
                    break
            if len(records) >= args.target_count:
                break

    return _dedupe(records)[: args.target_count]


async def _run_pair(
    sem: asyncio.Semaphore,
    chain,
    *,
    args,
    taxonomy: dict,
    topic_key: str,
    topic_entry: dict,
    scenario: dict,
    serial: int,
) -> list[dict]:
    question_templates = list(topic_entry.get("question_templates", []))
    label_plan = _resolve_label_plan(taxonomy, question_templates, scenario)

    async with sem:
        generated_examples = await _generate_llm_batch(
            chain,
            args=args,
            topic_key=topic_key,
            topic_entry=topic_entry,
            question_templates=question_templates,
            scenario=scenario,
            label_plan=label_plan,
            count=args.examples_per_call,
        )

    if not generated_examples:
        if args.fallback_generator == "rule":
            payload = _build_rule_payload(
                args=args,
                question_templates=question_templates,
                scenario=scenario,
                label_plan=label_plan,
                serial=serial,
                topic_key=topic_key,
            )
            return [build_training_record(payload)]
        return []

    built: list[dict] = []
    for example_index, example in enumerate(generated_examples):
        payload = {
            "session_id": f"synthetic-{normalize_topic_key(topic_key)}-{serial}-{example_index + 1}",
            "subject_area": args.subject_area,
            "topic": topic_key.replace("_", " "),
            "canonical_question_ids": [t["template_id"] for t in question_templates],
            "questions": [t["text"] for t in question_templates],
            "answers": list(example["answers"]),
            "response_times_sec": list(example["response_times_sec"]),
            "confidence_self_report": example["confidence_self_report"],
            "labels": {
                "learner_level": label_plan["learner_level"],
                "missing_prerequisites": list(label_plan["missing_prerequisites"]),
                "misconception_labels": list(label_plan["misconception_labels"]),
                "recommended_teaching_strategy": label_plan["recommended_teaching_strategy"],
            },
        }
        built.append(build_training_record(payload))
    return built


async def _generate_records_llm(args, taxonomy: dict) -> list[dict]:
    topics = taxonomy.get("topics", {})
    records: list[dict] = []
    prompt = ChatPromptTemplate.from_template(SYNTHETIC_BATCH_PROMPT)
    chain = prompt | get_llm(args.task_tier) | JsonOutputParser()
    sem = asyncio.Semaphore(args.max_concurrent)

    pairs = [
        (topic_key, topic_entry, scenario)
        for topic_key, topic_entry in topics.items()
        for scenario in SCENARIOS
    ]

    serial_counter = 0
    consecutive_empty_passes = 0

    while len(records) < args.target_count:
        pass_base = serial_counter
        serial_counter += len(pairs)

        tasks = [
            _run_pair(
                sem, chain,
                args=args,
                taxonomy=taxonomy,
                topic_key=topic_key,
                topic_entry=topic_entry,
                scenario=scenario,
                serial=pass_base + i,
            )
            for i, (topic_key, topic_entry, scenario) in enumerate(pairs)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        pass_records: list[dict] = []
        for result in results:
            if isinstance(result, BaseException):
                cause = getattr(result, "__cause__", None)
                detail = f" (caused by: {cause})" if cause else ""
                print(f"  [warn] pair raised: {result}{detail}", file=sys.stderr)
                continue
            pass_records.extend(result)

        if not pass_records:
            consecutive_empty_passes += 1
            if consecutive_empty_passes >= 5:
                print("[error] 5 consecutive empty passes — aborting.", file=sys.stderr)
                break
        else:
            consecutive_empty_passes = 0

        records.extend(pass_records)
        records = _dedupe(records)

    return _dedupe(records)[: args.target_count]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic diagnosis data.")
    parser.add_argument(
        "--subject-area",
        default="real_analysis",
        help="Subject area taxonomy to use.",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=800,
        help="Approximate number of JSONL records to generate.",
    )
    parser.add_argument(
        "--output",
        default="data/training/synthetic_diagnosis.jsonl",
        help="JSONL output path relative to the backend root.",
    )
    parser.add_argument(
        "--generator",
        choices=["llm", "rule"],
        default="llm",
        help="Synthetic session generator to use. 'llm' is the new default; 'rule' keeps the old template-based generator.",
    )
    parser.add_argument(
        "--fallback-generator",
        choices=["none", "rule"],
        default="none",
        help="Optional fallback when an LLM generation request fails.",
    )
    parser.add_argument(
        "--examples-per-call",
        type=int,
        default=4,
        help="Number of synthetic sessions to request per LLM call for one topic/scenario pair.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries for one LLM generation request before failing or using the fallback generator.",
    )
    parser.add_argument(
        "--task-tier",
        choices=["fast", "rich"],
        default="fast",
        help="LLM task tier passed into the shared LLM factory when --generator llm is used.",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Maximum simultaneous LLM requests during parallel generation.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed used for any fallback/rule-based generation.",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    taxonomy = load_diagnosis_taxonomy(args.subject_area)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parents[1] / output_path

    if args.generator == "rule":
        records = _generate_records_rule(args, taxonomy)
    else:
        records = asyncio.run(_generate_records_llm(args, taxonomy))

    _write_records(output_path, records)
    print(f"Wrote {len(records)} synthetic diagnosis records to {output_path}")


if __name__ == "__main__":
    main()
