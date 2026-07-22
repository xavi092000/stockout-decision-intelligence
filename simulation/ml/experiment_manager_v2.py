from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import joblib
import pandas as pd


class ExperimentManagerV2Error(RuntimeError):
    """Raised when an experiment artifact cannot be persisted safely."""


@dataclass(frozen=True)
class ExperimentPaths:
    experiment_id: str
    root_dir: str
    model_path: str
    manifest_path: str
    metrics_path: str
    config_path: str
    feature_importance_path: str
    confusion_matrix_path: str
    predictions_path: str


class ExperimentManagerV2:
    """Small local experiment registry with reproducibility metadata."""

    SCHEMA_VERSION = "2.0.0"

    def __init__(
        self,
        output_root: Path | str = Path("simulation/output/experiments_v2"),
        experiment_name: str = "policy_baseline",
    ) -> None:
        self.output_root = Path(output_root)
        self.experiment_name = self._slug(experiment_name)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
        cleaned = "_".join(part for part in cleaned.split("_") if part)
        return cleaned or "experiment"

    def create(self, config: Mapping[str, Any]) -> ExperimentPaths:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        digest = hashlib.sha256(
            json.dumps(dict(config), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:8]
        experiment_id = f"{timestamp}_{self.experiment_name}_{digest}"
        root = self.output_root / experiment_id
        root.mkdir(parents=True, exist_ok=False)
        return ExperimentPaths(
            experiment_id=experiment_id,
            root_dir=str(root.resolve()),
            model_path=str((root / "model.joblib").resolve()),
            manifest_path=str((root / "manifest.json").resolve()),
            metrics_path=str((root / "metrics.json").resolve()),
            config_path=str((root / "training_config.json").resolve()),
            feature_importance_path=str((root / "feature_importance.csv").resolve()),
            confusion_matrix_path=str((root / "confusion_matrix.csv").resolve()),
            predictions_path=str((root / "test_predictions.csv").resolve()),
        )

    @staticmethod
    def write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
        Path(path).write_text(
            json.dumps(dict(payload), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def save(
        self,
        *,
        paths: ExperimentPaths,
        model: Any,
        config: Mapping[str, Any],
        metrics: Mapping[str, Any],
        feature_importance: pd.DataFrame,
        confusion_matrix: pd.DataFrame,
        predictions: pd.DataFrame,
        input_files: Mapping[str, str],
        status: str = "PASSED",
    ) -> dict[str, Any]:
        joblib.dump(model, paths.model_path)
        self.write_json(paths.config_path, config)
        self.write_json(paths.metrics_path, metrics)
        feature_importance.to_csv(paths.feature_importance_path, index=False)
        confusion_matrix.to_csv(paths.confusion_matrix_path, index=True)
        predictions.to_csv(paths.predictions_path, index=False)

        manifest = {
            "status": status,
            "schema_version": self.SCHEMA_VERSION,
            "experiment_id": paths.experiment_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
            },
            "input_files": dict(input_files),
            "artifacts": asdict(paths),
            "selection_metric": metrics.get("selection_metric"),
            "selected_model": metrics.get("selected_model"),
            "test_metrics": metrics.get("test"),
        }
        self.write_json(paths.manifest_path, manifest)
        return manifest
