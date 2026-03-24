import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shared import load_records as _load_records, resolve_path as _resolve_path, topic_split as _topic_split  # noqa: E402
from app.modules.diagnosis.ml import _classes_for_model  # noqa: E402


def _load_model_bundle(model_dir: Path) -> tuple[dict, dict[str, object]]:
    manifest_path = model_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Model manifest not found: {manifest_path}")

    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)

    if manifest.get("model_type") != "sklearn_text_baseline":
        raise SystemExit(f"Unsupported model_type in {manifest_path}: {manifest.get('model_type')}")

    models: dict[str, object] = {}
    for task_name, task_meta in dict(manifest.get("tasks", {})).items():
        model_file = task_meta.get("model_file")
        if not model_file:
            continue
        with open(model_dir / model_file, "rb") as handle:
            models[task_name] = pickle.load(handle)

    return manifest, models


def _predict_multiclass(model: object, texts: list[str]) -> tuple[list[str], list[float] | None]:
    probabilities = getattr(model, "predict_proba", None)
    if probabilities is None:
        labels = model.predict(texts)
        return [str(label) for label in labels], None

    score_rows = probabilities(texts)
    classes = [str(item) for item in _classes_for_model(model)]
    predictions: list[str] = []
    confidences: list[float] = []
    for row in score_rows:
        scores = row.tolist() if hasattr(row, "tolist") else list(row)
        if not scores or not classes:
            predictions.append("")
            confidences.append(0.0)
            continue
        best_index = max(range(len(scores)), key=scores.__getitem__)
        predictions.append(classes[best_index])
        confidences.append(float(scores[best_index]))
    return predictions, confidences


def _predict_multilabel(
    model: object,
    texts: list[str],
    *,
    threshold: float,
    label_names: list[str],
) -> tuple[list[list[str]], list[list[float]] | None]:
    probabilities = getattr(model, "predict_proba", None)
    if probabilities is None:
        matrix = model.predict(texts)
        predictions: list[list[str]] = []
        for row in matrix:
            values = row.tolist() if hasattr(row, "tolist") else list(row)
            predictions.append([label_names[index] for index, value in enumerate(values) if value])
        return predictions, None

    score_rows = probabilities(texts)
    predictions: list[list[str]] = []
    confidence_rows: list[list[float]] = []
    for row in score_rows:
        scores = row.tolist() if hasattr(row, "tolist") else list(row)
        chosen = [
            label_names[index]
            for index, score in enumerate(scores[: len(label_names)])
            if float(score) >= threshold
        ]
        predictions.append(chosen)
        confidence_rows.append([float(score) for score in scores[: len(label_names)]])
    return predictions, confidence_rows


def _binarize_label_lists(label_lists: list[list[str]], label_names: list[str]) -> list[list[int]]:
    label_index = {label: index for index, label in enumerate(label_names)}
    matrix: list[list[int]] = []
    for labels in label_lists:
        row = [0] * len(label_names)
        for label in labels:
            if label in label_index:
                row[label_index[label]] = 1
        matrix.append(row)
    return matrix


def _format_metric(value: float) -> str:
    return f"{value:.4f}"


def _print_metric_block(title: str, metrics: dict[str, float]) -> None:
    print(title)
    for key, value in metrics.items():
        print(f"  {key}: {_format_metric(value)}")
    print()


def _print_confusion_matrix(labels: list[str], matrix: list[list[int]]) -> None:
    print("Learner Level Confusion Matrix")
    header = ["actual\\pred", *labels]
    widths = [max(len(str(item)) for item in [header[index], *([row[index - 1] if index else labels[row_i] for row_i, row in enumerate(matrix)] if index else labels)]) for index in range(len(header))]
    print("  " + " | ".join(str(item).ljust(widths[index]) for index, item in enumerate(header)))
    print("  " + "-+-".join("-" * width for width in widths))
    for row_index, actual_label in enumerate(labels):
        row_values = [actual_label, *[str(value) for value in matrix[row_index]]]
        print("  " + " | ".join(str(item).ljust(widths[index]) for index, item in enumerate(row_values)))
    print()


def _print_per_label_report(title: str, label_rows: list[dict[str, str]]) -> None:
    print(title)
    header = ["label", "precision", "recall", "f1", "support"]
    widths = [len(column) for column in header]
    for row in label_rows:
        widths[0] = max(widths[0], len(row["label"]))
        widths[1] = max(widths[1], len(row["precision"]))
        widths[2] = max(widths[2], len(row["recall"]))
        widths[3] = max(widths[3], len(row["f1"]))
        widths[4] = max(widths[4], len(row["support"]))

    print("  " + " | ".join(header[index].ljust(widths[index]) for index in range(len(header))))
    print("  " + "-+-".join("-" * width for width in widths))
    for row in label_rows:
        values = [row["label"], row["precision"], row["recall"], row["f1"], row["support"]]
        print("  " + " | ".join(values[index].ljust(widths[index]) for index in range(len(values))))
    print()


def _evaluate_bundle(manifest: dict, models: dict[str, object], records: list[dict]) -> dict:
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    if not records:
        raise SystemExit("No evaluation records matched the selected split.")

    texts = [record["combined_text"] for record in records]

    learner_true = [str(record["labels"]["learner_level"]) for record in records]
    learner_pred, _ = _predict_multiclass(models["learner_level"], texts)
    learner_labels = sorted(set(learner_true) | set(learner_pred))
    learner_matrix = confusion_matrix(learner_true, learner_pred, labels=learner_labels).tolist()

    strategy_true = [str(record["labels"]["recommended_teaching_strategy"]) for record in records]
    strategy_pred, _ = _predict_multiclass(models["recommended_teaching_strategy"], texts)

    label_sets = dict(manifest.get("label_sets", {}))
    missing_label_names = list(label_sets.get("missing_prerequisites", [])) or sorted(
        {label for record in records for label in record["labels"].get("missing_prerequisites", [])}
    )
    misconception_label_names = list(label_sets.get("misconception_labels", [])) or sorted(
        {label for record in records for label in record["labels"].get("misconception_labels", [])}
    )

    thresholds = dict(manifest.get("thresholds", {}))
    missing_true_lists = [list(record["labels"].get("missing_prerequisites", [])) for record in records]
    missing_pred_lists, _ = _predict_multilabel(
        models["missing_prerequisites"],
        texts,
        threshold=float(thresholds.get("missing_prerequisites", 0.45)),
        label_names=missing_label_names,
    )
    misconception_true_lists = [list(record["labels"].get("misconception_labels", [])) for record in records]
    misconception_pred_lists, _ = _predict_multilabel(
        models["misconception_labels"],
        texts,
        threshold=float(thresholds.get("misconception_labels", 0.45)),
        label_names=misconception_label_names,
    )

    missing_true = _binarize_label_lists(missing_true_lists, missing_label_names)
    missing_pred = _binarize_label_lists(missing_pred_lists, missing_label_names)
    misconception_true = _binarize_label_lists(misconception_true_lists, misconception_label_names)
    misconception_pred = _binarize_label_lists(misconception_pred_lists, misconception_label_names)

    missing_precision, missing_recall, missing_f1, missing_support = precision_recall_fscore_support(
        missing_true,
        missing_pred,
        average=None,
        zero_division=0,
    )
    misconception_precision, misconception_recall, misconception_f1, misconception_support = precision_recall_fscore_support(
        misconception_true,
        misconception_pred,
        average=None,
        zero_division=0,
    )

    return {
        "summary": {
            "learner_level_macro_f1": float(f1_score(learner_true, learner_pred, average="macro")),
            "learner_level_balanced_accuracy": float(balanced_accuracy_score(learner_true, learner_pred)),
            "teaching_strategy_macro_f1": float(f1_score(strategy_true, strategy_pred, average="macro")),
            "teaching_strategy_balanced_accuracy": float(balanced_accuracy_score(strategy_true, strategy_pred)),
            "missing_prerequisites_micro_f1": float(f1_score(missing_true, missing_pred, average="micro", zero_division=0)),
            "missing_prerequisites_macro_f1": float(f1_score(missing_true, missing_pred, average="macro", zero_division=0)),
            "misconception_labels_micro_f1": float(f1_score(misconception_true, misconception_pred, average="micro", zero_division=0)),
            "misconception_labels_macro_f1": float(f1_score(misconception_true, misconception_pred, average="macro", zero_division=0)),
        },
        "learner": {
            "labels": learner_labels,
            "matrix": learner_matrix,
        },
        "missing_prerequisites": {
            "rows": [
                {
                    "label": label_name,
                    "precision": _format_metric(float(missing_precision[index])),
                    "recall": _format_metric(float(missing_recall[index])),
                    "f1": _format_metric(float(missing_f1[index])),
                    "support": str(int(missing_support[index])),
                }
                for index, label_name in enumerate(missing_label_names)
            ],
        },
        "misconception_labels": {
            "rows": [
                {
                    "label": label_name,
                    "precision": _format_metric(float(misconception_precision[index])),
                    "recall": _format_metric(float(misconception_recall[index])),
                    "f1": _format_metric(float(misconception_f1[index])),
                    "support": str(int(misconception_support[index])),
                }
                for index, label_name in enumerate(misconception_label_names)
            ],
        },
    }


def _print_single_report(name: str, report: dict, holdout_topics: list[str], sample_count: int) -> None:
    print(f"Model: {name}")
    print(f"Holdout topics: {', '.join(holdout_topics) if holdout_topics else '(all topics)'}")
    print(f"Evaluation rows: {sample_count}")
    print()
    _print_metric_block("Summary Metrics", report["summary"])
    _print_confusion_matrix(report["learner"]["labels"], report["learner"]["matrix"])
    _print_per_label_report("Missing Prerequisites: Per-label Precision/Recall", report["missing_prerequisites"]["rows"])
    _print_per_label_report("Misconceptions: Per-label Precision/Recall", report["misconception_labels"]["rows"])


def _print_comparison_report(base_name: str, base_report: dict, compare_name: str, compare_report: dict) -> None:
    metrics = [
        "learner_level_macro_f1",
        "learner_level_balanced_accuracy",
        "teaching_strategy_macro_f1",
        "teaching_strategy_balanced_accuracy",
        "missing_prerequisites_micro_f1",
        "missing_prerequisites_macro_f1",
        "misconception_labels_micro_f1",
        "misconception_labels_macro_f1",
    ]

    print("Comparison Report")
    header = ["metric", base_name, compare_name, "delta", "winner"]
    rows: list[list[str]] = []
    for metric in metrics:
        base_value = float(base_report["summary"][metric])
        compare_value = float(compare_report["summary"][metric])
        delta = compare_value - base_value
        winner = "tie"
        if delta > 1e-9:
            winner = compare_name
        elif delta < -1e-9:
            winner = base_name
        rows.append(
            [
                metric,
                _format_metric(base_value),
                _format_metric(compare_value),
                f"{delta:+.4f}",
                winner,
            ]
        )

    widths = [len(column) for column in header]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    print("  " + " | ".join(header[index].ljust(widths[index]) for index in range(len(header))))
    print("  " + "-+-".join("-" * width for width in widths))
    for row in rows:
        print("  " + " | ".join(row[index].ljust(widths[index]) for index in range(len(row))))
    print()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate one or two trained diagnosis model directories.")
    parser.add_argument(
        "--dataset",
        default="data/training/synthetic_diagnosis.jsonl",
        help="Training/evaluation JSONL dataset relative to the backend root.",
    )
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Primary trained model directory relative to the backend root.",
    )
    parser.add_argument(
        "--compare-model-dir",
        default=None,
        help="Optional second trained model directory to compare against the primary one.",
    )
    parser.add_argument(
        "--split",
        choices=["holdout", "all"],
        default="holdout",
        help="Evaluate on the holdout topics recorded in the manifest, or on all rows.",
    )
    parser.add_argument(
        "--holdout-topics",
        default=None,
        help="Optional comma-separated topic_key override for evaluation.",
    )
    args = parser.parse_args()

    dataset_path = _resolve_path(args.dataset)
    model_dir = _resolve_path(args.model_dir)
    compare_model_dir = _resolve_path(args.compare_model_dir) if args.compare_model_dir else None

    records = _load_records(dataset_path)
    manifest, models = _load_model_bundle(model_dir)

    holdout_topics = [item.strip() for item in (args.holdout_topics or "").split(",") if item.strip()]
    if args.split == "holdout":
        if not holdout_topics:
            holdout_topics = list(manifest.get("holdout_topics", []))
        if not holdout_topics:
            _, _, holdout_topics = _topic_split(records)
        eval_records = [record for record in records if record["topic_key"] in set(holdout_topics)]
    else:
        eval_records = records
        holdout_topics = []

    primary_report = _evaluate_bundle(manifest, models, eval_records)
    _print_single_report(str(model_dir), primary_report, holdout_topics, len(eval_records))

    if compare_model_dir is None:
        return

    compare_manifest, compare_models = _load_model_bundle(compare_model_dir)
    compare_report = _evaluate_bundle(compare_manifest, compare_models, eval_records)
    _print_single_report(str(compare_model_dir), compare_report, holdout_topics, len(eval_records))

    compare_holdout_topics = list(compare_manifest.get("holdout_topics", []))
    if args.split == "holdout" and compare_holdout_topics and holdout_topics and compare_holdout_topics != holdout_topics:
        print(
            "Note: comparison model advertises different holdout topics in its manifest, "
            "but both models were evaluated on the primary model's selected holdout rows."
        )
        print()

    _print_comparison_report(str(model_dir), primary_report, str(compare_model_dir), compare_report)


if __name__ == "__main__":
    main()
