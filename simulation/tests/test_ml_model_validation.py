from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from simulation.ml.feature_contract import FEATURE_COLUMNS
from simulation.ml_decision_policy import (
    MLDecisionPolicy,
    ModelValidationError,
)


ARTIFACT_DIR = Path("artifacts/policy_training")
MODEL_PATH = ARTIFACT_DIR / "decision_tree.joblib"
METADATA_PATH = ARTIFACT_DIR / "training_metadata.json"


def _copy_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    model_path = tmp_path / "decision_tree.joblib"
    metadata_path = tmp_path / "training_metadata.json"
    shutil.copy2(MODEL_PATH, model_path)
    shutil.copy2(METADATA_PATH, metadata_path)
    return model_path, metadata_path


def test_current_model_satisfies_v2_contract() -> None:
    policy = MLDecisionPolicy(
        model_path=MODEL_PATH,
        metadata_path=METADATA_PATH,
    )
    assert tuple(policy.pipeline.feature_names_in_) == FEATURE_COLUMNS


def test_missing_model_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="model not found"):
        MLDecisionPolicy(
            model_path=tmp_path / "missing.joblib",
            metadata_path=METADATA_PATH,
        )


def test_missing_metadata_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="metadata not found"):
        MLDecisionPolicy(
            model_path=MODEL_PATH,
            metadata_path=tmp_path / "missing.json",
        )


def test_metadata_feature_mismatch_is_rejected(tmp_path: Path) -> None:
    model_path, metadata_path = _copy_artifacts(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["feature_columns"] = [*FEATURE_COLUMNS, "future_leak"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(
        ModelValidationError,
        match="Metadata feature contract mismatch",
    ):
        MLDecisionPolicy(model_path, metadata_path)


def test_metadata_action_mismatch_is_rejected(tmp_path: Path) -> None:
    model_path, metadata_path = _copy_artifacts(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["expected_actions"] = ["DO_NOTHING"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(
        ModelValidationError,
        match="Metadata action classes mismatch",
    ):
        MLDecisionPolicy(model_path, metadata_path)
