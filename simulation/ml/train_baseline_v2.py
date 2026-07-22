from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.tree import DecisionTreeClassifier

from simulation.ml.experiment_manager_v2 import ExperimentManagerV2


class BaselineTrainingV2Error(RuntimeError):
    """Raised when baseline training cannot be completed safely."""


@dataclass(frozen=True)
class SplitData:
    X: pd.DataFrame
    y: pd.Series
    metadata: pd.DataFrame
    feature_path: Path
    label_path: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train reproducible policy-classification baselines from episode-safe splits."
    )
    parser.add_argument(
        "--multi-episode-dir",
        type=Path,
        default=Path("simulation/output/multi_episode_v2"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation/output/experiments_v2"),
    )
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--experiment-name", default="policy_baseline_v2")
    return parser


def resolve_frame(base: Path) -> Path:
    for suffix in (".parquet", ".csv"):
        candidate = base.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    raise BaselineTrainingV2Error(f"Missing dataset: {base}.parquet or {base}.csv")


def read_frame(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def load_split(root: Path, split: str) -> SplitData:
    feature_path = resolve_frame(root / "splits" / f"{split}_features_v2")
    label_path = resolve_frame(root / "splits" / f"{split}_labels_v2")
    features = read_frame(feature_path)
    labels = read_frame(label_path)

    required_features = {"state_snapshot_id", "dataset_split"}
    required_labels = {
        "state_snapshot_id",
        "state_episode_id",
        "action_selected_policy",
        "dataset_split",
    }
    if missing := required_features - set(features.columns):
        raise BaselineTrainingV2Error(f"{split} features missing columns: {sorted(missing)}")
    if missing := required_labels - set(labels.columns):
        raise BaselineTrainingV2Error(f"{split} labels missing columns: {sorted(missing)}")
    if features["state_snapshot_id"].duplicated().any() or labels["state_snapshot_id"].duplicated().any():
        raise BaselineTrainingV2Error(f"Duplicate snapshot IDs in {split} split.")

    joined = features.merge(
        labels,
        on=["state_snapshot_id", "dataset_split"],
        how="inner",
        validate="one_to_one",
    )
    if len(joined) != len(features) or len(joined) != len(labels):
        raise BaselineTrainingV2Error(f"Feature/label alignment failed for {split}.")
    if set(joined["dataset_split"].astype(str)) != {split}:
        raise BaselineTrainingV2Error(f"Unexpected split marker inside {split} files.")

    feature_columns = [c for c in features.columns if c.startswith("state_") and c != "state_snapshot_id"]
    if not feature_columns:
        raise BaselineTrainingV2Error("No model feature columns found.")
    X = joined[feature_columns].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(X.to_numpy(dtype=float)).all():
        raise BaselineTrainingV2Error(f"Non-finite values detected in {split} features.")
    y = joined["action_selected_policy"].astype(str)
    metadata = joined[["state_snapshot_id", "state_episode_id", "dataset_split"]].copy()
    return SplitData(X, y, metadata, feature_path.resolve(), label_path.resolve())


def evaluate(model: Any, data: SplitData, labels: list[str]) -> tuple[dict[str, Any], np.ndarray]:
    pred = model.predict(data.X)
    metrics = {
        "rows": int(len(data.y)),
        "episodes": int(data.metadata["state_episode_id"].nunique()),
        "accuracy": float(accuracy_score(data.y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(data.y, pred)),
        "f1_macro": float(f1_score(data.y, pred, labels=labels, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(data.y, pred, labels=labels, average="weighted", zero_division=0)),
        "precision_macro": float(precision_score(data.y, pred, labels=labels, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(data.y, pred, labels=labels, average="macro", zero_division=0)),
        "classification_report": classification_report(
            data.y, pred, labels=labels, output_dict=True, zero_division=0
        ),
    }
    return metrics, np.asarray(pred)


def feature_importance_frame(model: Any, columns: list[str]) -> pd.DataFrame:
    values = getattr(model, "feature_importances_", None)
    if values is None:
        values = np.zeros(len(columns), dtype=float)
    return (
        pd.DataFrame({"feature": columns, "importance": values})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def main() -> int:
    args = build_parser().parse_args()
    started = perf_counter()
    try:
        train = load_split(args.multi_episode_dir, "train")
        validation = load_split(args.multi_episode_dir, "validation")
        test = load_split(args.multi_episode_dir, "test")

        if list(train.X.columns) != list(validation.X.columns) or list(train.X.columns) != list(test.X.columns):
            raise BaselineTrainingV2Error("Feature schemas differ across splits.")
        episode_sets = [set(d.metadata["state_episode_id"].astype(str)) for d in (train, validation, test)]
        if episode_sets[0] & episode_sets[1] or episode_sets[0] & episode_sets[2] or episode_sets[1] & episode_sets[2]:
            raise BaselineTrainingV2Error("Episode leakage detected across splits.")

        classes = sorted(set(train.y) | set(validation.y) | set(test.y))
        candidates: dict[str, Any] = {
            "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
            "decision_tree": DecisionTreeClassifier(
                max_depth=12,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=args.random_state,
            ),
            "random_forest": RandomForestClassifier(
                n_estimators=250,
                max_depth=16,
                min_samples_leaf=2,
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=args.random_state,
            ),
        }

        candidate_metrics: dict[str, Any] = {}
        fitted: dict[str, Any] = {}
        for name, estimator in candidates.items():
            model = clone(estimator).fit(train.X, train.y)
            fitted[name] = model
            train_metrics, _ = evaluate(model, train, classes)
            validation_metrics, _ = evaluate(model, validation, classes)
            candidate_metrics[name] = {
                "train": train_metrics,
                "validation": validation_metrics,
            }
            print(
                f"{name:<20} | validation macro-F1 {validation_metrics['f1_macro']:.4f} "
                f"| balanced accuracy {validation_metrics['balanced_accuracy']:.4f}",
                flush=True,
            )

        selected_name = max(
            candidate_metrics,
            key=lambda name: (
                candidate_metrics[name]["validation"]["f1_macro"],
                candidate_metrics[name]["validation"]["balanced_accuracy"],
                candidate_metrics[name]["validation"]["accuracy"],
            ),
        )
        selected_model = fitted[selected_name]
        test_metrics, test_pred = evaluate(selected_model, test, classes)

        manager = ExperimentManagerV2(args.output_dir, args.experiment_name)
        config = {
            "schema_version": "2.0.0",
            "random_state": args.random_state,
            "selection_metric": "validation_f1_macro",
            "candidate_models": {
                name: estimator.get_params(deep=False) for name, estimator in candidates.items()
            },
            "feature_columns": list(train.X.columns),
            "target": "action_selected_policy",
            "class_labels": classes,
            "leakage_guard": "Complete episodes are disjoint across train, validation, and test.",
        }
        paths = manager.create(config)
        cm = pd.DataFrame(
            confusion_matrix(test.y, test_pred, labels=classes),
            index=[f"actual_{label}" for label in classes],
            columns=[f"predicted_{label}" for label in classes],
        )
        predictions = test.metadata.copy()
        predictions["actual_action"] = test.y.to_numpy()
        predictions["predicted_action"] = test_pred
        predictions["is_correct"] = predictions["actual_action"] == predictions["predicted_action"]

        metrics = {
            "status": "PASSED",
            "selection_metric": "validation_f1_macro",
            "selected_model": selected_name,
            "candidates": candidate_metrics,
            "test": test_metrics,
            "runtime_seconds": round(perf_counter() - started, 3),
        }
        manifest = manager.save(
            paths=paths,
            model=selected_model,
            config=config,
            metrics=metrics,
            feature_importance=feature_importance_frame(selected_model, list(train.X.columns)),
            confusion_matrix=cm,
            predictions=predictions,
            input_files={
                "train_features": str(train.feature_path),
                "train_labels": str(train.label_path),
                "validation_features": str(validation.feature_path),
                "validation_labels": str(validation.label_path),
                "test_features": str(test.feature_path),
                "test_labels": str(test.label_path),
            },
        )
        summary = {
            "status": "PASSED",
            "experiment_id": paths.experiment_id,
            "selected_model": selected_name,
            "validation_f1_macro": candidate_metrics[selected_name]["validation"]["f1_macro"],
            "test_f1_macro": test_metrics["f1_macro"],
            "test_balanced_accuracy": test_metrics["balanced_accuracy"],
            "experiment_dir": paths.root_dir,
            "manifest": manifest,
        }
        print("\n" + "=" * 72)
        print("BASELINE TRAINING V2")
        print("=" * 72)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print("=" * 72)
        print("STATUS: PASSED")
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
