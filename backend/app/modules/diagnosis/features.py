"""Shared feature extraction for diagnosis ML models — used by both training scripts and inference."""
import numpy as np

CONF_MAP: dict[str, float] = {"high": 0.0, "medium": 0.5, "low": 1.0}
PROBE_THRESHOLD_DEFAULT: float = 0.70
BEHAVIOR_THRESHOLD_DEFAULT: float = 0.45


def extract_dense_features(records: list[dict], probe_keys: list[str]) -> np.ndarray:
    """
    Extract a fixed-length dense feature vector from each record.

    Features (in order):
      - probe_features scores for every key in probe_keys  (topic-level skill/misconception weights)
      - reference_similarity: mean, std, min, max          (answer quality vs. reference)
      - response_times_sec:   mean/40, std/40, max/40      (normalised to [0,1])
      - confidence_bucket:    0=high, 0.5=medium, 1=low    (self-report)
      - answer_lengths:       per-question word counts     (verbosity signal)
    """
    rows = []
    for r in records:
        pf = r.get("probe_features") or {}
        ref_sims = list(r.get("reference_similarity") or [0.5] * 4)
        times = list(r.get("response_times_sec") or [15.0] * 4)
        lengths = list((r.get("answer_lengths") or [10] * 4))[:4]
        conf = CONF_MAP.get(r.get("confidence_bucket") or "medium", 0.5)

        probe_vec = [float(pf.get(k, 0.0)) for k in probe_keys]
        sim_feats = [
            float(np.mean(ref_sims)),
            float(np.std(ref_sims)),
            float(min(ref_sims)),
            float(max(ref_sims)),
        ]
        time_feats = [
            float(np.mean(times)) / 40.0,
            float(np.std(times)) / 40.0,
            float(max(times)) / 40.0,
        ]
        length_feats = [float(v) for v in lengths]
        rows.append(probe_vec + sim_feats + time_feats + [conf] + length_feats)
    return np.array(rows, dtype=np.float32)


def extract_behavior_features(records: list[dict]) -> np.ndarray:
    """
    Behavioral feature vector used by the missing_prerequisites behavior gate.

    These features are topic-agnostic (no probe_keys needed), so they generalise
    to any topic including ones not present in the training taxonomy.

    Features: mean/std/min/max ref_sim, mean/std/max response_time, confidence, mean_length.
    """
    rows = []
    for r in records:
        ref_sims = list(r.get("reference_similarity") or [0.5] * 4)
        times = list(r.get("response_times_sec") or [15.0] * 4)
        conf = CONF_MAP.get(r.get("confidence_bucket") or "medium", 0.5)
        lengths = list((r.get("answer_lengths") or [10] * 4))[:4]
        rows.append([
            float(np.mean(ref_sims)),
            float(np.std(ref_sims)),
            float(min(ref_sims)),
            float(max(ref_sims)),
            float(np.mean(times)) / 40.0,
            float(np.std(times)) / 40.0,
            float(max(times)) / 40.0,
            conf,
            float(np.mean(lengths)),
        ])
    return np.array(rows, dtype=np.float32)


def get_candidate_skills(
    probe_features: dict,
    probe_threshold: float = PROBE_THRESHOLD_DEFAULT,
) -> list[str]:
    """
    Stage 1 of the hybrid missing_prerequisites predictor.

    Returns prerequisite skill names whose probe score meets the threshold.
    Misconception keys (prefixed 'misconception::') are excluded.

    For topics NOT in the taxonomy, probe_features will be empty → returns [].
    The caller (ml.py) treats an empty candidate list as 'unknown topic' and
    falls back to the LLM diagnosis for missing_prerequisites.
    """
    return [
        k
        for k, v in probe_features.items()
        if not k.startswith("misconception::") and float(v) >= probe_threshold
    ]
