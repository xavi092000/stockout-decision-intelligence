from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd


class MLPolicyAdapterV2Error(RuntimeError):
    """Raised when an online policy prediction cannot be produced safely."""


class MLPolicyAdapterV2:
    """
    Leakage-safe online adapter for the V2 policy classifier.

    The adapter receives one pre-decision snapshot, recreates the exact
    feature vector used by ``train_baseline_v2.py``, and returns one of the
    trained policy labels (for example ``balanced``, ``lean`` or
    ``service_first``).

    It does not mutate the simulation, inventory, orders, or KPIs.
    """

    SNAPSHOT_EXCLUDED_FIELDS = {"inventory_positions", "captured_at_utc"}

    def __init__(
        self,
        *,
        model_path: str | Path,
        training_config_path: str | Path,
        strict: bool = True,
    ) -> None:
        self.model_path = Path(model_path)
        self.training_config_path = Path(training_config_path)
        self.strict = bool(strict)

        if not self.model_path.is_file():
            raise MLPolicyAdapterV2Error(f"Model file not found: {self.model_path}")
        if not self.training_config_path.is_file():
            raise MLPolicyAdapterV2Error(
                f"Training config not found: {self.training_config_path}"
            )

        try:
            self.model = joblib.load(self.model_path)
        except Exception as exc:  # joblib may wrap many deserialization failures
            raise MLPolicyAdapterV2Error(
                f"Unable to load model from {self.model_path}: {exc}"
            ) from exc

        try:
            self.training_config = json.loads(
                self.training_config_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise MLPolicyAdapterV2Error(
                f"Unable to read training config {self.training_config_path}: {exc}"
            ) from exc

        columns = self.training_config.get("feature_columns")
        if not isinstance(columns, list) or not columns:
            raise MLPolicyAdapterV2Error(
                "training_config.json must contain a non-empty feature_columns list."
            )
        if len(columns) != len(set(columns)):
            raise MLPolicyAdapterV2Error("Duplicate feature names exist in training config.")
        if any(not isinstance(column, str) or not column.startswith("state_") for column in columns):
            raise MLPolicyAdapterV2Error(
                "Every online model feature must be a string prefixed with 'state_'."
            )

        self.feature_columns: tuple[str, ...] = tuple(columns)
        labels = self.training_config.get("class_labels", [])
        self.class_labels: tuple[str, ...] = tuple(str(label) for label in labels)

        model_features = getattr(self.model, "feature_names_in_", None)
        if model_features is not None:
            model_columns = tuple(str(column) for column in model_features)
            if model_columns != self.feature_columns:
                raise MLPolicyAdapterV2Error(
                    "Model feature_names_in_ does not match training_config feature order."
                )

        n_features = getattr(self.model, "n_features_in_", None)
        if n_features is not None and int(n_features) != len(self.feature_columns):
            raise MLPolicyAdapterV2Error(
                "Model n_features_in_ does not match training_config feature count."
            )

    def predict(self, snapshot: Any) -> str:
        """Return the policy predicted for one pre-decision snapshot."""
        frame = self.build_feature_frame(snapshot)
        try:
            prediction = self.model.predict(frame)
        except Exception as exc:
            raise MLPolicyAdapterV2Error(f"Model prediction failed: {exc}") from exc

        if len(prediction) != 1:
            raise MLPolicyAdapterV2Error(
                f"Expected exactly one prediction; received {len(prediction)}."
            )

        policy = str(prediction[0])
        if self.class_labels and policy not in self.class_labels:
            raise MLPolicyAdapterV2Error(
                f"Model returned unknown policy {policy!r}; expected {self.class_labels}."
            )
        return policy

    def predict_with_details(self, snapshot: Any) -> dict[str, Any]:
        """Return policy, latency, and optional class probabilities."""
        started = perf_counter()
        frame = self.build_feature_frame(snapshot)
        try:
            prediction = self.model.predict(frame)
        except Exception as exc:
            raise MLPolicyAdapterV2Error(f"Model prediction failed: {exc}") from exc

        policy = str(prediction[0])
        probabilities: dict[str, float] | None = None
        if hasattr(self.model, "predict_proba"):
            try:
                proba = self.model.predict_proba(frame)[0]
                classes = [str(value) for value in getattr(self.model, "classes_", [])]
                if len(classes) == len(proba):
                    probabilities = {
                        label: float(value) for label, value in zip(classes, proba)
                    }
            except Exception:
                probabilities = None

        return {
            "policy": policy,
            "latency_ms": round((perf_counter() - started) * 1000.0, 3),
            "feature_count": len(self.feature_columns),
            "probabilities": probabilities,
        }

    def build_feature_frame(self, snapshot: Any) -> pd.DataFrame:
        """Create a one-row DataFrame in the exact training feature order."""
        flattened = self.flatten_snapshot(snapshot)
        row: dict[str, float] = {}
        unresolved: list[str] = []

        for encoded_column in self.feature_columns:
            if encoded_column in flattened:
                row[encoded_column] = self._to_numeric(
                    flattened[encoded_column], encoded_column
                )
                continue

            raw_column, category = self._split_dummy_column(encoded_column, flattened)
            if raw_column is not None:
                raw_value = flattened[raw_column]
                row[encoded_column] = float(
                    self._category_equals(raw_value, category)
                )
                continue

            unresolved.append(encoded_column)
            row[encoded_column] = 0.0

        if unresolved and self.strict:
            raise MLPolicyAdapterV2Error(
                "Snapshot cannot reconstruct required features: "
                + ", ".join(unresolved[:20])
                + (" ..." if len(unresolved) > 20 else "")
            )

        frame = pd.DataFrame([row], columns=list(self.feature_columns))
        frame = frame.apply(pd.to_numeric, errors="raise")
        values = frame.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise MLPolicyAdapterV2Error("Online feature vector contains non-finite values.")
        return frame

    @classmethod
    def flatten_snapshot(cls, snapshot: Any) -> dict[str, Any]:
        """Mirror TrainingDatasetBuilderV2._flatten_state(prefix='state_')."""
        payload = cls._snapshot_to_mapping(snapshot)
        flattened: dict[str, Any] = {}

        for key, value in payload.items():
            if key in cls.SNAPSHOT_EXCLUDED_FIELDS:
                continue
            if isinstance(value, (dict, list, tuple, set)):
                continue
            flattened[f"state_{key}"] = value

        positions = payload.get("inventory_positions", []) or []
        if not isinstance(positions, Sequence) or isinstance(positions, (str, bytes)):
            raise MLPolicyAdapterV2Error("inventory_positions must be a sequence.")

        flattened["state_inventory_position_count"] = len(positions)
        flattened["state_positions_below_reorder_point"] = sum(
            1
            for item in positions
            if isinstance(item, Mapping) and bool(item.get("below_reorder_point", False))
        )
        flattened["state_total_stock_gap_to_target"] = sum(
            int(item.get("stock_gap_to_target", 0))
            for item in positions
            if isinstance(item, Mapping)
        )
        return flattened

    @staticmethod
    def _snapshot_to_mapping(snapshot: Any) -> dict[str, Any]:
        if isinstance(snapshot, Mapping):
            return dict(snapshot)
        if is_dataclass(snapshot):
            return asdict(snapshot)
        to_dict = getattr(snapshot, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, Mapping):
                return dict(payload)
        raise MLPolicyAdapterV2Error(
            "snapshot must be a mapping, dataclass, or expose to_dict()."
        )

    @staticmethod
    def _split_dummy_column(
        encoded_column: str,
        flattened: Mapping[str, Any],
    ) -> tuple[str | None, str | None]:
        # Find the longest matching raw prefix. This safely handles '=' inside values.
        candidates = [
            raw_column
            for raw_column in flattened
            if encoded_column.startswith(raw_column + "=")
        ]
        if not candidates:
            return None, None
        raw_column = max(candidates, key=len)
        return raw_column, encoded_column[len(raw_column) + 1 :]

    @staticmethod
    def _category_equals(raw_value: Any, category: str | None) -> bool:
        if category is None:
            return False
        if isinstance(raw_value, (bool, np.bool_)):
            return str(bool(raw_value)).lower() == str(category).lower()
        if raw_value is None:
            return str(category).lower() in {"none", "nan", "<na>"}
        return str(raw_value) == str(category)

    @staticmethod
    def _to_numeric(value: Any, column: str) -> float:
        if isinstance(value, (bool, np.bool_)):
            return float(bool(value))
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise MLPolicyAdapterV2Error(
                f"Feature {column!r} expected numeric data; received {value!r}."
            ) from exc
        if not np.isfinite(numeric):
            raise MLPolicyAdapterV2Error(
                f"Feature {column!r} contains a non-finite value: {value!r}."
            )
        return numeric


def _load_snapshot(path: Path, line_number: int) -> dict[str, Any]:
    if not path.is_file():
        raise MLPolicyAdapterV2Error(f"Snapshot file not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise MLPolicyAdapterV2Error("JSON snapshot must be an object.")
        return payload
    if path.suffix.lower() == ".jsonl":
        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if line_number < 1 or line_number > len(rows):
            raise MLPolicyAdapterV2Error(
                f"JSONL line must be between 1 and {len(rows)}; received {line_number}."
            )
        payload = json.loads(rows[line_number - 1])
        if not isinstance(payload, dict):
            raise MLPolicyAdapterV2Error("JSONL snapshot must be an object.")
        return payload
    raise MLPolicyAdapterV2Error("Snapshot file must end in .json or .jsonl.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test one online daily policy prediction from a V2 snapshot."
    )
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--training-config", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--line", type=int, default=1, help="1-based JSONL line number")
    parser.add_argument(
        "--allow-missing-features",
        action="store_true",
        help="Fill unreconstructable features with zero instead of failing.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        adapter = MLPolicyAdapterV2(
            model_path=args.model_path,
            training_config_path=args.training_config,
            strict=not args.allow_missing_features,
        )
        snapshot = _load_snapshot(args.snapshot, args.line)
        result = adapter.predict_with_details(snapshot)
        print("=" * 72)
        print("ML POLICY ADAPTER V2")
        print("=" * 72)
        print(json.dumps({"status": "PASSED", **result}, indent=2))
        print("=" * 72)
        print("STATUS: PASSED")
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
