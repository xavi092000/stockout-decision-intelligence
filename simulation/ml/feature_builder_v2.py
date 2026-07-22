from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


class FeatureBuilderV2Error(RuntimeError):
    """Raised when leakage-safe model features cannot be created."""


@dataclass(frozen=True)
class FeatureBuildResult:
    rows_created: int
    raw_state_features: int
    encoded_features: int
    actions: list[str]
    episode_count: int
    feature_output_path: str
    label_output_path: str
    manifest_output_path: str
    leakage_checks_passed: bool
    schema_version: str = "2.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_created": self.rows_created,
            "raw_state_features": self.raw_state_features,
            "encoded_features": self.encoded_features,
            "actions": self.actions,
            "episode_count": self.episode_count,
            "feature_output_path": self.feature_output_path,
            "label_output_path": self.label_output_path,
            "manifest_output_path": self.manifest_output_path,
            "leakage_checks_passed": self.leakage_checks_passed,
            "schema_version": self.schema_version,
        }


class FeatureBuilderV2:
    """
    Converts the transition dataset into a leakage-safe supervised-learning
    matrix.

    Only columns prefixed with ``state_`` are eligible as model inputs.
    The action label is ``action_selected_policy``.

    Explicitly excluded from X:
      - reward_*
      - outcome_*
      - next_state_*
      - next_snapshot_id
      - next_simulation_day
      - is_terminal
      - action_*
    """

    LABEL_COLUMN = "action_selected_policy"

    NON_MODEL_STATE_COLUMNS = {
        "state_snapshot_id",
        "state_episode_id",
        "state_synthetic_date",
        "state_captured_at_utc",
        "state_schema_version",
    }

    IDENTIFIER_COLUMNS = {
        "state_episode_seed",
        "state_simulation_day",
    }

    FORBIDDEN_PREFIXES = (
        "reward_",
        "outcome_",
        "next_state_",
        "action_",
    )

    FORBIDDEN_EXACT_COLUMNS = {
        "next_snapshot_id",
        "next_simulation_day",
        "is_terminal",
    }

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def build(
        self,
        *,
        dataset_path: str | Path | None = None,
    ) -> FeatureBuildResult:
        dataset_path = Path(
            dataset_path
            or self.output_dir / "training_dataset_v2.parquet"
        )

        if not dataset_path.is_file():
            csv_fallback = dataset_path.with_suffix(".csv")
            if csv_fallback.is_file():
                dataset_path = csv_fallback
            else:
                raise FeatureBuilderV2Error(
                    f"Training dataset not found: {dataset_path}"
                )

        dataset = self._read_dataset(dataset_path)
        self._validate_dataset(dataset)

        state_columns = sorted(
            column
            for column in dataset.columns
            if column.startswith("state_")
            and column not in self.NON_MODEL_STATE_COLUMNS
            and column not in self.IDENTIFIER_COLUMNS
        )

        if not state_columns:
            raise FeatureBuilderV2Error(
                "No eligible state features were found."
            )

        raw_features = dataset[state_columns].copy()
        labels = dataset[
            [
                "state_snapshot_id",
                "state_episode_id",
                "state_episode_seed",
                "state_simulation_day",
                self.LABEL_COLUMN,
            ]
        ].copy()

        self._validate_feature_columns(raw_features.columns)

        categorical_columns = sorted(
            column
            for column in raw_features.columns
            if (
                pd.api.types.is_object_dtype(
                    raw_features[column]
                )
                or pd.api.types.is_string_dtype(
                    raw_features[column]
                )
                or pd.api.types.is_bool_dtype(
                    raw_features[column]
                )
            )
        )

        numeric_columns = sorted(
            column
            for column in raw_features.columns
            if column not in categorical_columns
        )

        for column in numeric_columns:
            raw_features[column] = pd.to_numeric(
                raw_features[column],
                errors="raise",
            )

        if raw_features[numeric_columns].isna().any().any():
            missing = (
                raw_features[numeric_columns]
                .isna()
                .sum()
            )
            invalid = missing[missing > 0].to_dict()
            raise FeatureBuilderV2Error(
                "Numeric state features contain missing values: "
                f"{invalid}"
            )

        encoded = pd.get_dummies(
            raw_features,
            columns=categorical_columns,
            prefix=categorical_columns,
            prefix_sep="=",
            dtype=int,
        )

        encoded.insert(
            0,
            "state_snapshot_id",
            dataset["state_snapshot_id"].astype(str),
        )

        if encoded.columns.duplicated().any():
            duplicates = encoded.columns[
                encoded.columns.duplicated()
            ].tolist()
            raise FeatureBuilderV2Error(
                f"Duplicate encoded feature names: {duplicates}"
            )

        feature_output_path = (
            self.output_dir / "model_features_v2.parquet"
        )
        label_output_path = (
            self.output_dir / "model_labels_v2.parquet"
        )
        manifest_output_path = (
            self.output_dir / "feature_manifest_v2.json"
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        feature_output_path = self._write_frame(
            encoded,
            feature_output_path,
        )
        label_output_path = self._write_frame(
            labels,
            label_output_path,
        )

        actions = sorted(
            labels[self.LABEL_COLUMN]
            .astype(str)
            .unique()
            .tolist()
        )
        episode_count = int(
            labels["state_episode_id"].nunique()
        )

        manifest = {
            "schema_version": "2.0.0",
            "source_dataset": str(dataset_path.resolve()),
            "row_count": len(dataset),
            "label_column": self.LABEL_COLUMN,
            "raw_state_columns": state_columns,
            "excluded_identifier_columns": sorted(
                self.IDENTIFIER_COLUMNS
                | self.NON_MODEL_STATE_COLUMNS
            ),
            "categorical_columns": categorical_columns,
            "numeric_columns": numeric_columns,
            "encoded_feature_columns": [
                column
                for column in encoded.columns
                if column != "state_snapshot_id"
            ],
            "actions": actions,
            "episode_count": episode_count,
            "training_readiness": (
                "MULTI_EPISODE_READY"
                if episode_count >= 3
                else "SINGLE_EPISODE_ONLY"
            ),
            "leakage_checks_passed": True,
        }

        manifest_output_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return FeatureBuildResult(
            rows_created=len(encoded),
            raw_state_features=len(state_columns),
            encoded_features=len(encoded.columns) - 1,
            actions=actions,
            episode_count=episode_count,
            feature_output_path=str(
                feature_output_path.resolve()
            ),
            label_output_path=str(
                label_output_path.resolve()
            ),
            manifest_output_path=str(
                manifest_output_path.resolve()
            ),
            leakage_checks_passed=True,
        )

    @staticmethod
    def _read_dataset(path: Path) -> pd.DataFrame:
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)

        raise FeatureBuilderV2Error(
            f"Unsupported dataset format: {path.suffix}"
        )

    def _validate_dataset(
        self,
        dataset: pd.DataFrame,
    ) -> None:
        if dataset.empty:
            raise FeatureBuilderV2Error(
                "Training dataset is empty."
            )

        required = {
            "state_snapshot_id",
            "state_episode_id",
            "state_episode_seed",
            "state_simulation_day",
            self.LABEL_COLUMN,
        }
        missing = required - set(dataset.columns)
        if missing:
            raise FeatureBuilderV2Error(
                "Training dataset is missing required columns: "
                f"{sorted(missing)}"
            )

        if dataset["state_snapshot_id"].duplicated().any():
            raise FeatureBuilderV2Error(
                "Duplicate state_snapshot_id values exist."
            )

        if dataset[self.LABEL_COLUMN].isna().any():
            raise FeatureBuilderV2Error(
                "Action labels contain missing values."
            )

        unknown_non_state = sorted(
            column
            for column in dataset.columns
            if (
                not column.startswith("state_")
                and not column.startswith(
                    self.FORBIDDEN_PREFIXES
                )
                and column
                not in self.FORBIDDEN_EXACT_COLUMNS
            )
        )
        if unknown_non_state:
            raise FeatureBuilderV2Error(
                "Unexpected transition columns were found: "
                f"{unknown_non_state}"
            )

    def _validate_feature_columns(
        self,
        columns: Any,
    ) -> None:
        invalid = sorted(
            column
            for column in columns
            if (
                not column.startswith("state_")
                or column.startswith(
                    self.FORBIDDEN_PREFIXES
                )
                or column
                in self.FORBIDDEN_EXACT_COLUMNS
            )
        )
        if invalid:
            raise FeatureBuilderV2Error(
                "Forbidden model feature columns detected: "
                f"{invalid}"
            )

    @staticmethod
    def _write_frame(
        frame: pd.DataFrame,
        preferred_path: Path,
    ) -> Path:
        try:
            frame.to_parquet(
                preferred_path,
                index=False,
            )
            return preferred_path
        except (ImportError, ModuleNotFoundError, ValueError):
            fallback = preferred_path.with_suffix(".csv")
            frame.to_csv(
                fallback,
                index=False,
            )
            return fallback


def main() -> None:
    output_dir = Path(
        "simulation/output/adaptive_policy_v2"
    )

    result = FeatureBuilderV2(
        output_dir=output_dir
    ).build()

    print("=" * 72)
    print("FEATURE BUILDER V2")
    print("=" * 72)
    print(json.dumps(result.to_dict(), indent=2))
    print("=" * 72)

    if result.episode_count < 3:
        print(
            "TRAINING READINESS: SINGLE_EPISODE_ONLY"
        )
        print(
            "Generate multiple independent episodes before "
            "performing a trustworthy train/validation/test split."
        )
    else:
        print("TRAINING READINESS: MULTI_EPISODE_READY")

    print("STATUS: PASSED")


if __name__ == "__main__":
    main()
