import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import scipy.sparse as sp

from app.core.config import settings
from app.modules.diagnosis.dataset import build_training_record
from app.modules.diagnosis.features import (
    BEHAVIOR_THRESHOLD_DEFAULT,
    extract_behavior_features,
    extract_dense_features,
    get_candidate_skills,
)


ROOT_DIR = Path(__file__).resolve().parents[3]
_RUNTIME_CACHE: dict[str, tuple[dict, dict[str, object]]] = {}


@dataclass
class ShadowDiagnosisOutput:
    source: str | None
    status: str
    prediction: dict | None
    confidence: float | None


def _model_dir() -> Path:
    configured = Path(settings.diagnosis_model_dir)
    if configured.is_absolute():
        return configured
    return ROOT_DIR / configured


def _load_runtime() -> tuple[dict, dict[str, object]] | None:
    model_dir = _model_dir()
    manifest_path = model_dir / "manifest.json"
    if not manifest_path.exists():
        return None

    cache_key = str(manifest_path.resolve())
    if cache_key in _RUNTIME_CACHE:
        return _RUNTIME_CACHE[cache_key]

    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)

    # v1 manifests had a single root-level model_type; v2 has it per task.
    version = manifest.get("version", 1)
    if version < 2 and manifest.get("model_type") != "sklearn_text_baseline":
        return None

    models: dict[str, object] = {}
    for task_name, task_meta in dict(manifest.get("tasks", {})).items():
        model_file = task_meta.get("model_file")
        if not model_file:
            continue
        model_path = model_dir / model_file
        if not model_path.exists():
            continue
        with open(model_path, "rb") as handle:
            models[task_name] = pickle.load(handle)

    _RUNTIME_CACHE[cache_key] = (manifest, models)
    return manifest, models


# ── v2 inference helpers (bundled tuple format) ───────────────────────────────

def _build_X(record: dict, tfidf, scaler, probe_keys: list[str]) -> sp.csr_matrix:
    X_text = tfidf.transform([record["combined_text"]])
    X_dense = scaler.transform(extract_dense_features([record], probe_keys))
    return sp.hstack([X_text, sp.csr_matrix(X_dense)])


def _predict_multiclass_v2(
    bundle: tuple,
    record: dict,
) -> tuple[str | None, float | None]:
    tfidf, scaler, probe_keys, clf = bundle
    X = _build_X(record, tfidf, scaler, probe_keys)
    if not hasattr(clf, "predict_proba"):
        label = clf.predict(X)
        return (str(label[0]) if len(label) else None, None)
    scores = clf.predict_proba(X)[0].tolist()
    classes = list(clf.classes_)
    if not scores or not classes:
        return None, None
    best = max(range(len(scores)), key=scores.__getitem__)
    return str(classes[best]), float(scores[best])


def _predict_multilabel_v2(
    bundle: tuple,
    record: dict,
    thresholds: dict[str, float] | float,
    label_names: list[str],
) -> tuple[list[str], float]:
    tfidf, scaler, probe_keys, ovr = bundle
    X = _build_X(record, tfidf, scaler, probe_keys)
    proba = ovr.predict_proba(X)[0].tolist()
    if isinstance(thresholds, dict):
        chosen = [label for i, label in enumerate(label_names) if float(proba[i]) >= thresholds.get(label, 0.45)]
    else:
        chosen = [label for i, label in enumerate(label_names) if float(proba[i]) >= float(thresholds)]
    confidence = max((float(v) for v in proba), default=0.0)
    return chosen, confidence


def _predict_missing_prerequisites_v2(
    bundle: tuple,
    record: dict,
    behavior_threshold: float = BEHAVIOR_THRESHOLD_DEFAULT,
) -> tuple[list[str], float]:
    """
    Hybrid Stage 1 (rule) + Stage 2 (behavior gate) inference.

    Unknown topics have empty probe_features → returns ([], 0.0) so the
    caller's aggregate confidence stays low and the LLM result takes priority.
    """
    candidates = get_candidate_skills(record.get("probe_features") or {})
    if not candidates:
        return [], 0.0

    behavior_scaler, behavior_clf = bundle
    feats = behavior_scaler.transform(extract_behavior_features([record]))
    prob = float(behavior_clf.predict_proba(feats)[0][1])
    return (candidates if prob >= behavior_threshold else []), prob


# ── v1 inference helpers (legacy sklearn Pipeline format) ─────────────────────

def _classes_for_model(model: object) -> list:
    classes = getattr(model, "classes_", None)
    if classes is not None:
        return list(classes)
    named_steps = getattr(model, "named_steps", {})
    classifier = named_steps.get("clf") if isinstance(named_steps, dict) else None
    if classifier is None:
        return []
    classes = getattr(classifier, "classes_", None)
    return list(classes) if classes is not None else []


def _predict_multiclass_v1(model: object, text: str) -> tuple[str | None, float | None]:
    if not hasattr(model, "predict_proba"):
        labels = model.predict([text])
        return (str(labels[0]) if len(labels) else None, None)
    scores = model.predict_proba([text])[0].tolist()
    classes = _classes_for_model(model)
    if not scores or not classes:
        return None, None
    best = max(range(len(scores)), key=scores.__getitem__)
    return str(classes[best]), float(scores[best])


def _predict_multilabel_v1(
    model: object,
    text: str,
    threshold: float,
    label_names: list[str] | None = None,
) -> tuple[list[str], float]:
    classes = list(label_names or _classes_for_model(model))
    if not hasattr(model, "predict_proba"):
        labels = model.predict([text])
        values = labels[0].tolist() if hasattr(labels[0], "tolist") else list(labels[0])
        if len(classes) < len(values):
            classes = [str(i) for i in range(len(values))]
        chosen = [str(classes[i]) for i, v in enumerate(values) if v]
        return chosen, 1.0 if chosen else 0.0
    raw = model.predict_proba([text])
    scores = raw[0].tolist() if hasattr(raw[0], "tolist") else list(raw[0])
    if len(classes) < len(scores):
        classes = [str(i) for i in range(len(scores))]
    chosen = [str(classes[i]) for i, v in enumerate(scores) if float(v) >= threshold]
    return chosen, max((float(v) for v in scores), default=0.0)


# ── Public API ────────────────────────────────────────────────────────────────

async def run_shadow_diagnosis(
    *,
    session_id: str,
    topic: str,
    subject_area: str,
    questions: list[str],
    answers: list[str],
    response_times_sec: list[float] | None,
    confidence_self_report: str | None,
) -> ShadowDiagnosisOutput:
    runtime = _load_runtime()
    if runtime is None:
        return ShadowDiagnosisOutput(source=None, status="unavailable", prediction=None, confidence=None)

    manifest, models = runtime
    required_tasks = {"learner_level", "recommended_teaching_strategy", "missing_prerequisites", "misconception_labels"}
    if not required_tasks.issubset(models):
        return ShadowDiagnosisOutput(
            source=str(manifest.get("source", "sklearn_text_baseline")),
            status="incomplete",
            prediction=None,
            confidence=None,
        )

    record = build_training_record({
        "session_id": session_id,
        "subject_area": subject_area,
        "topic": topic,
        "questions": questions,
        "answers": answers,
        "response_times_sec": response_times_sec or [],
        "confidence_self_report": confidence_self_report,
        "labels": {},
    })

    thresholds = dict(manifest.get("thresholds", {}))
    label_sets = dict(manifest.get("label_sets", {}))
    version = manifest.get("version", 1)

    if version >= 2:
        learner_level, learner_conf = _predict_multiclass_v2(models["learner_level"], record)
        teaching_strategy, strategy_conf = _predict_multiclass_v2(models["recommended_teaching_strategy"], record)

        misconception_threshold = thresholds.get("misconception_labels", 0.45)
        misconception_label_names = list(label_sets.get("misconception_labels", []))
        misconception_labels, misconception_conf = _predict_multilabel_v2(
            models["misconception_labels"], record, misconception_threshold, misconception_label_names
        )

        missing_thresholds = thresholds.get("missing_prerequisites", {})
        behavior_threshold = (
            float(missing_thresholds.get("behavior_threshold", BEHAVIOR_THRESHOLD_DEFAULT))
            if isinstance(missing_thresholds, dict)
            else BEHAVIOR_THRESHOLD_DEFAULT
        )
        missing_prerequisites, missing_conf = _predict_missing_prerequisites_v2(
            models["missing_prerequisites"], record, behavior_threshold
        )
    else:
        text = record["combined_text"]
        learner_level, learner_conf = _predict_multiclass_v1(models["learner_level"], text)
        teaching_strategy, strategy_conf = _predict_multiclass_v1(models["recommended_teaching_strategy"], text)
        missing_prerequisites, missing_conf = _predict_multilabel_v1(
            models["missing_prerequisites"],
            text,
            float(thresholds.get("missing_prerequisites", 0.45)),
            list(label_sets.get("missing_prerequisites", [])) or None,
        )
        misconception_labels, misconception_conf = _predict_multilabel_v1(
            models["misconception_labels"],
            text,
            float(thresholds.get("misconception_labels", 0.45)),
            list(label_sets.get("misconception_labels", [])) or None,
        )

    confidences = [s for s in (learner_conf, strategy_conf, missing_conf, misconception_conf) if s is not None]
    prediction = {
        "learner_level": learner_level,
        "missing_prerequisites": missing_prerequisites,
        "misconception_labels": misconception_labels,
        "recommended_teaching_strategy": teaching_strategy,
        "diagnostic_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
    }
    return ShadowDiagnosisOutput(
        source=str(manifest.get("source", "sklearn_text_baseline")),
        status="ready",
        prediction=prediction,
        confidence=prediction["diagnostic_confidence"],
    )
