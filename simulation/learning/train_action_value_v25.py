from __future__ import annotations

"""Train the V25 delta action-value model on the representative-state expanded-quantity dataset.

Same pipeline architecture as the V23 delta model (ColumnTransformer +
OneHotEncoder + RandomForestRegressor), target = delta_value_vs_wait.
Never overwrites model_based_delta or model_based_v23 artifacts.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
from statistics import mean, median
import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, validate_model_features

CATEGORICAL = ["store_id", "sku_id", "weather_condition", "action_type", "source_store_id"]
NUMERIC = [x for x in MODEL_FEATURES if x not in CATEGORICAL]


def _matrix(rows):
    return [[r["features"][c] for c in MODEL_FEATURES] for r in rows]


def _target(rows):
    return [float(r["labels"]["delta_value_vs_wait"]) for r in rows]


def main():
    p = ArgumentParser()
    p.add_argument("--dataset", type=Path, default=Path("artifacts/model_based_v25/counterfactual_dataset.json"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/model_based_v25"))
    args = p.parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "stockout_counterfactual_action_value_v25":
        raise RuntimeError("Not a V24 dataset")
    features = tuple(payload["metadata"]["model_features"])
    validate_model_features(features)
    if features != MODEL_FEATURES:
        raise RuntimeError("Dataset feature contract does not match V2 code")
    train = [r for r in payload["rows"] if r["split"] == "train"]
    val = [r for r in payload["rows"] if r["split"] == "validation"]
    if not train or not val:
        raise RuntimeError("Both train and validation rows are required")
    train_seeds = set(payload["metadata"]["train_episode_seeds"])
    val_seeds = set(payload["metadata"]["validation_episode_seeds"])
    if train_seeds & val_seeds:
        raise RuntimeError("Seed leakage between train and validation")

    cat_idx = [MODEL_FEATURES.index(c) for c in CATEGORICAL]
    num_idx = [MODEL_FEATURES.index(c) for c in NUMERIC]
    prep = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat_idx),
        ("num", "passthrough", num_idx),
    ])
    model = Pipeline([
        ("features", prep),
        ("regressor", RandomForestRegressor(
            n_estimators=300, min_samples_leaf=3, random_state=20260929, n_jobs=-1
        )),
    ])
    model.fit(_matrix(train), _target(train))
    pred = model.predict(_matrix(val))
    mae = float(mean_absolute_error(_target(val), pred))

    groups = {}
    for row, pval in zip(val, pred):
        f = row["features"]
        obs_key = (
            row["episode_seed"], row["future_seed"], f["store_id"], f["sku_id"],
            f["simulation_day"],
        )
        groups.setdefault(obs_key, []).append((row, float(pval)))
    regrets = []
    exact_type = 0
    exact_type_qty = 0
    for items in groups.values():
        chosen = max(items, key=lambda x: x[1])[0]
        best = max(items, key=lambda x: float(x[0]["labels"]["delta_value_vs_wait"]))[0]
        regret = float(best["labels"]["delta_value_vs_wait"]) - float(chosen["labels"]["delta_value_vs_wait"])
        regrets.append(regret)
        same_type = chosen["features"]["action_type"] == best["features"]["action_type"]
        exact_type += same_type
        exact_type_qty += same_type and chosen["features"]["action_quantity"] == best["features"]["action_quantity"]

    artifact = {
        "schema_version": "stockout_action_value_model_v25",
        "model_features": list(MODEL_FEATURES),
        "target": "delta_value_vs_wait",
        "train_episode_seeds": sorted(train_seeds),
        "validation_episode_seeds": sorted(val_seeds),
        "counterfactual_horizon": payload["metadata"]["horizon"],
        "future_outcomes_are_labels_only": True,
        "validation": {
            "mae_delta_value": mae,
            "mean_action_regret": mean(regrets) if regrets else None,
            "median_action_regret": median(regrets) if regrets else None,
            "p95_action_regret": float(np.percentile(regrets, 95)) if regrets else None,
            "action_type_exact_rate": exact_type / len(groups) if groups else None,
            "action_type_quantity_exact_rate": exact_type_qty / len(groups) if groups else None,
            "groups": len(groups),
        },
        "claim_status": "V25_REPRESENTATIVE_STATE_PILOT_NOT_PRODUCTION_APPROVED",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metadata": artifact}, args.output_dir / "action_value_model.joblib")
    (args.output_dir / "training_report.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact["validation"], indent=2))


if __name__ == "__main__":
    main()
