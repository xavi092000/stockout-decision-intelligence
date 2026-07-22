from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from simulation.calibration_repository import CalibrationRepository
from simulation.scenario_engine import ScenarioEngine, ScenarioEngineError


ROOT = Path(__file__).resolve().parents[1]


def _load_calibrations() -> dict:
    return CalibrationRepository(
        demand_dir=ROOT / "reality_calibration/data/processed/calibration",
        weather_dir=ROOT / "reality_calibration/data/processed/weather_calibration",
        economic_dir=ROOT / "reality_calibration/data/processed/economic_calibration",
    ).load()


def test_generated_product_hierarchy_is_always_valid() -> None:
    engine = ScenarioEngine(_load_calibrations(), seed=20260717)

    for _ in range(2_000):
        category, department = engine._sample_product_hierarchy()
        category_name = str(category["source_group"])
        department_name = str(department["source_group"])
        assert department_name.rsplit("_", 1)[0] == category_name


def test_generated_location_hierarchy_is_always_valid() -> None:
    engine = ScenarioEngine(_load_calibrations(), seed=20260718)

    for _ in range(2_000):
        store, state = engine._sample_location_hierarchy()
        store_name = str(store["source_group"])
        state_name = str(state["source_group"])
        assert store_name.split("_", 1)[0] == state_name


def test_category_sampling_preserves_calibrated_marginal() -> None:
    calibrations = _load_calibrations()
    engine = ScenarioEngine(calibrations, seed=20260719)
    draws = 20_000
    counts: Counter[str] = Counter()

    for _ in range(draws):
        category, _ = engine._sample_product_hierarchy()
        counts[str(category["source_group"])] += 1

    for profile in calibrations["category_profiles"]:
        name = str(profile["source_group"])
        expected = float(profile["metadata"]["sampling_weight"])
        observed = counts[name] / draws
        assert observed == pytest.approx(expected, abs=0.015)


def test_invalid_hierarchy_contract_is_rejected() -> None:
    calibrations = _load_calibrations()
    calibrations["department_profiles"][0]["source_group"] = "UNKNOWN_1"

    with pytest.raises(ScenarioEngineError, match="no matching category"):
        ScenarioEngine(calibrations, seed=1)
