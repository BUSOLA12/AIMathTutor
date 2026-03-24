import json
import pickle
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shared import load_records as _load_records, resolve_path as _resolve_path, topic_split as _topic_split  # noqa: E402
from app.modules.diagnosis.features import (  # noqa: E402
    BEHAVIOR_THRESHOLD_DEFAULT,
    PROBE_THRESHOLD_DEFAULT,
    extract_behavior_features,
    extract_dense_features,
    get_candidate_skills,
)


def _tune_thresholds_per_label(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    label_names: list[str],
    fallback: float = 0.45,
) -> dict[str, float]:
    """Find the F1-maximising threshold per label on the provided set."""
    from sklearn.metrics import precision_recall_curve

    thresholds: dict[str, float] = {}
    for i, label in enumerate(label_names):
        if y_true[:, i].sum() == 0:
            thresholds[label] = fallback
            continue
        precision, recall, t_values = precision_recall_curve(y_true[:, i], y_proba[:, i])
        f1 = 2 * (precision[:-1] * recall[:-1]) / (precision[:-1] + recall[:-1] + 1e-10)
        thresholds[label] = float(t_values[np.argmax(f1)]) if len(f1) > 0 else fallback
    return thresholds


def _binarize_label_lists(label_lists: list[list[str]], label_names: list[str]) -> np.ndarray:
    idx = {label: i for i, label in enumerate(label_names)}
    matrix = []
    for labels in label_lists:
        row = [0] * len(label_names)
        for label in labels:
            if label in idx:
                row[idx[label]] = 1
        matrix.append(row)
    return np.array(matrix, dtype=int)


def _build_X(
    records: list[dict],
    tfidf,
    scaler,
    probe_keys: list[str],
    *,
    fit: bool = False,
) -> sp.csr_matrix:
    texts = [r["combined_text"] for r in records]
    if fit:
        X_text = tfidf.fit_transform(texts)
        X_dense = scaler.fit_transform(extract_dense_features(records, probe_keys))
    else:
        X_text = tfidf.transform(texts)
        X_dense = scaler.transform(extract_dense_features(records, probe_keys))
    return sp.hstack([X_text, sp.csr_matrix(X_dense)])


def main() -> None:
    import argparse

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score, classification_report, f1_score
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler

    parser = argparse.ArgumentParser(description="Train TF-IDF + LogisticRegression diagnosis baselines.")
    parser.add_argument(
        "--dataset",
        default="data/training/synthetic_diagnosis.jsonl",
        help="Input JSONL dataset relative to the backend root.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/models/diagnosis",
        help="Artifact directory relative to the backend root.",
    )
    args = parser.parse_args()

    dataset_path = _resolve_path(args.dataset)
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = _load_records(dataset_path)
    if len(records) < 8:
        raise SystemExit("Need at least 8 records to train the baseline.")

    train_records, valid_records, holdout_topics = _topic_split(records)

    # Probe keys: sorted union across all records (deterministic order for inference)
    probe_keys = sorted({k for r in records for k in (r.get("probe_features") or {})})

    # ── Shared TF-IDF + StandardScaler ──────────────────────────────────────────
    tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)
    scaler = StandardScaler()
    X_train = _build_X(train_records, tfidf, scaler, probe_keys, fit=True)
    X_valid = _build_X(valid_records, tfidf, scaler, probe_keys)

    # ── Task A: learner_level ────────────────────────────────────────────────────
    learner_y_train = [r["labels"]["learner_level"] for r in train_records]
    learner_y_valid = [r["labels"]["learner_level"] for r in valid_records]
    learner_clf = LogisticRegression(max_iter=600, class_weight="balanced")
    learner_clf.fit(X_train, learner_y_train)
    learner_pred = learner_clf.predict(X_valid)

    # ── Task D: recommended_teaching_strategy ────────────────────────────────────
    strategy_y_train = [r["labels"]["recommended_teaching_strategy"] for r in train_records]
    strategy_y_valid = [r["labels"]["recommended_teaching_strategy"] for r in valid_records]
    strategy_clf = LogisticRegression(max_iter=600, class_weight="balanced")
    strategy_clf.fit(X_train, strategy_y_train)
    strategy_pred = strategy_clf.predict(X_valid)

    # ── Task C: misconception_labels (per-label threshold tuning) ────────────────
    misconception_label_names = sorted({
        label for r in records for label in r["labels"].get("misconception_labels", [])
    })
    misconception_binarizer = MultiLabelBinarizer(classes=misconception_label_names)
    misconception_y_train = misconception_binarizer.fit_transform(
        [r["labels"]["misconception_labels"] for r in train_records]
    )
    misconception_y_valid = misconception_binarizer.transform(
        [r["labels"]["misconception_labels"] for r in valid_records]
    )
    misconception_ovr = OneVsRestClassifier(LogisticRegression(max_iter=600, class_weight="balanced"))
    misconception_ovr.fit(X_train, misconception_y_train)

    # Tune thresholds on training predictions (avoid leaking holdout)
    misconception_train_proba = misconception_ovr.predict_proba(X_train)
    misconception_thresholds = _tune_thresholds_per_label(
        misconception_y_train, misconception_train_proba, misconception_label_names
    )
    misconception_valid_proba = misconception_ovr.predict_proba(X_valid)
    misconception_pred = np.array([
        [
            1 if float(misconception_valid_proba[i, j]) >= misconception_thresholds.get(label, 0.45) else 0
            for j, label in enumerate(misconception_label_names)
        ]
        for i in range(len(valid_records))
    ])

    # ── Task B: missing_prerequisites (hybrid rule + behavior gate) ──────────────
    #
    # Stage 1 (rule): probe_features from taxonomy → candidate skills with score ≥ threshold.
    #   Works for any topic in the taxonomy; returns [] for unknown topics.
    #
    # Stage 2 (ML gate): single binary classifier on behavior features
    #   (response times, answer quality, confidence) decides whether candidates
    #   are actually missing. Topic-agnostic → generalises across topics.
    #
    # For topics NOT in the taxonomy (unknown topics at inference time):
    #   get_candidate_skills returns [] → missing_prerequisites = [] with low
    #   confidence → handler naturally falls back to LLM output.

    behavior_train = extract_behavior_features(train_records)
    X_beh_rows: list[np.ndarray] = []
    y_gap: list[int] = []
    for i, r in enumerate(train_records):
        candidates = get_candidate_skills(r.get("probe_features") or {})
        missing_set = set(r["labels"].get("missing_prerequisites", []))
        if not candidates:
            continue
        for skill in candidates:
            X_beh_rows.append(behavior_train[i])
            y_gap.append(1 if skill in missing_set else 0)

    behavior_scaler = StandardScaler()
    X_beh = behavior_scaler.fit_transform(np.array(X_beh_rows, dtype=np.float32))
    behavior_clf = LogisticRegression(max_iter=600, class_weight="balanced")
    behavior_clf.fit(X_beh, np.array(y_gap, dtype=int))

    # Evaluate on valid set
    behavior_valid = extract_behavior_features(valid_records)
    missing_pred_lists: list[list[str]] = []
    for i, r in enumerate(valid_records):
        candidates = get_candidate_skills(r.get("probe_features") or {})
        if not candidates:
            missing_pred_lists.append([])
            continue
        feats = behavior_scaler.transform(behavior_valid[i : i + 1])
        prob = float(behavior_clf.predict_proba(feats)[0][1])
        missing_pred_lists.append(candidates if prob >= BEHAVIOR_THRESHOLD_DEFAULT else [])

    missing_true_lists = [list(r["labels"].get("missing_prerequisites", [])) for r in valid_records]
    missing_label_names = sorted({
        label for r in records for label in r["labels"].get("missing_prerequisites", [])
    })
    missing_true_bin = _binarize_label_lists(missing_true_lists, missing_label_names)
    missing_pred_bin = _binarize_label_lists(missing_pred_lists, missing_label_names)

    # ── Print metrics ────────────────────────────────────────────────────────────
    print("Holdout topics:", ", ".join(holdout_topics))
    print(
        "Learner level: macro_f1=%.4f balanced_accuracy=%.4f"
        % (
            f1_score(learner_y_valid, learner_pred, average="macro"),
            balanced_accuracy_score(learner_y_valid, learner_pred),
        )
    )
    print(
        "Teaching strategy: macro_f1=%.4f balanced_accuracy=%.4f"
        % (
            f1_score(strategy_y_valid, strategy_pred, average="macro"),
            balanced_accuracy_score(strategy_y_valid, strategy_pred),
        )
    )
    print(
        "Missing prerequisites: micro_f1=%.4f macro_f1=%.4f"
        % (
            f1_score(missing_true_bin, missing_pred_bin, average="micro", zero_division=0),
            f1_score(missing_true_bin, missing_pred_bin, average="macro", zero_division=0),
        )
    )
    print(
        "Misconceptions: micro_f1=%.4f macro_f1=%.4f"
        % (
            f1_score(misconception_y_valid, misconception_pred, average="micro", zero_division=0),
            f1_score(misconception_y_valid, misconception_pred, average="macro", zero_division=0),
        )
    )
    print(classification_report(learner_y_valid, learner_pred, zero_division=0))

    # ── Save artifacts ───────────────────────────────────────────────────────────
    # Bundled format: (tfidf, scaler, probe_keys, clf) — loaded by ml.py
    for task_name, clf in [
        ("learner_level", learner_clf),
        ("recommended_teaching_strategy", strategy_clf),
    ]:
        with open(output_dir / f"{task_name}.pkl", "wb") as handle:
            pickle.dump((tfidf, scaler, probe_keys, clf), handle)

    with open(output_dir / "misconception_labels.pkl", "wb") as handle:
        pickle.dump((tfidf, scaler, probe_keys, misconception_ovr), handle)

    # Behavior gate: (behavior_scaler, behavior_clf)
    with open(output_dir / "missing_prerequisites_behavior.pkl", "wb") as handle:
        pickle.dump((behavior_scaler, behavior_clf), handle)

    # ── Manifest ─────────────────────────────────────────────────────────────────
    manifest = {
        "version": 2,
        "source": "sklearn_text_baseline_v2",
        "model_type": "sklearn_text_baseline",
        "holdout_topics": holdout_topics,
        "probe_keys": probe_keys,
        "thresholds": {
            "missing_prerequisites": {
                "probe_threshold": PROBE_THRESHOLD_DEFAULT,
                "behavior_threshold": BEHAVIOR_THRESHOLD_DEFAULT,
            },
            "misconception_labels": misconception_thresholds,
        },
        "label_sets": {
            "missing_prerequisites": missing_label_names,
            "misconception_labels": misconception_label_names,
        },
        "metrics": {
            "learner_level": {
                "macro_f1": round(f1_score(learner_y_valid, learner_pred, average="macro"), 4),
                "balanced_accuracy": round(balanced_accuracy_score(learner_y_valid, learner_pred), 4),
            },
            "recommended_teaching_strategy": {
                "macro_f1": round(f1_score(strategy_y_valid, strategy_pred, average="macro"), 4),
                "balanced_accuracy": round(balanced_accuracy_score(strategy_y_valid, strategy_pred), 4),
            },
            "missing_prerequisites": {
                "micro_f1": round(f1_score(missing_true_bin, missing_pred_bin, average="micro", zero_division=0), 4),
                "macro_f1": round(f1_score(missing_true_bin, missing_pred_bin, average="macro", zero_division=0), 4),
            },
            "misconception_labels": {
                "micro_f1": round(f1_score(misconception_y_valid, misconception_pred, average="micro", zero_division=0), 4),
                "macro_f1": round(f1_score(misconception_y_valid, misconception_pred, average="macro", zero_division=0), 4),
            },
        },
        "tasks": {
            "learner_level": {"model_file": "learner_level.pkl", "model_type": "bundled"},
            "recommended_teaching_strategy": {
                "model_file": "recommended_teaching_strategy.pkl",
                "model_type": "bundled",
            },
            "missing_prerequisites": {
                "model_file": "missing_prerequisites_behavior.pkl",
                "model_type": "hybrid_rule_behavior",
            },
            "misconception_labels": {"model_file": "misconception_labels.pkl", "model_type": "bundled"},
        },
    }
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    print(f"Saved baseline artifacts to {output_dir}")


if __name__ == "__main__":
    main()
