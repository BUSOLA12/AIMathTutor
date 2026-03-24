Place trained diagnosis model artifacts here.

Expected files for the runtime shadow loader:

- `manifest.json`
- `learner_level.pkl`
- `recommended_teaching_strategy.pkl`
- `missing_prerequisites.pkl`
- `misconception_labels.pkl`

The baseline trainer at `backend/scripts/train_diagnosis_baseline.py` writes this layout.

Useful data-generation commands:

- Generate synthetic diagnosis data with the default LLM-backed generator:
  `python scripts/generate_synthetic_diagnosis_dataset.py --target-count 800 --output data/training/synthetic_diagnosis.jsonl`
- Generate synthetic data with LLM generation and a rule-based fallback if an LLM request fails:
  `python scripts/generate_synthetic_diagnosis_dataset.py --generator llm --fallback-generator rule --target-count 800 --output data/training/synthetic_diagnosis.jsonl`
- Generate synthetic data with the old rule-based generator only:
  `python scripts/generate_synthetic_diagnosis_dataset.py --generator rule --target-count 800 --output data/training/synthetic_diagnosis.jsonl`

Useful follow-up commands:

- Train a baseline:
  `python scripts/train_diagnosis_baseline.py --dataset data/training/synthetic_diagnosis.jsonl --output-dir data/models/diagnosis`
- Evaluate one trained model:
  `python scripts/evaluate_diagnosis_models.py --dataset data/training/synthetic_diagnosis.jsonl --model-dir data/models/diagnosis`
- Compare two trained models on the same holdout split:
  `python scripts/evaluate_diagnosis_models.py --dataset data/training/synthetic_diagnosis.jsonl --model-dir data/models/diagnosis --compare-model-dir data/models/diagnosis_candidate`
