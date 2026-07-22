from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from simulation.calibration_repository import CalibrationRepository
from simulation.scenario_engine import ScenarioEngine


ROOT = Path(__file__).resolve().parents[1]


def _load_calibrations() -> dict:
    return CalibrationRepository(
        demand_dir=ROOT / "reality_calibration/data/processed/calibration",
        weather_dir=ROOT / "reality_calibration/data/processed/weather_calibration",
        economic_dir=ROOT / "reality_calibration/data/processed/economic_calibration",
    ).load()


def test_economic_regime_is_persistent_within_calendar_month() -> None:
    engine = ScenarioEngine(
        _load_calibrations(),
        seed=20260720,
        start_date=date(2027, 1, 1),
    )

    january = [engine.generate_day(day) for day in range(1, 32)]

    assert len({scenario.economic_regime for scenario in january}) == 1
    assert all(
        scenario.metadata["economic_regime_sampling"]
        == "one_synthetic_regime_per_calendar_month"
        for scenario in january
    )


def test_monthly_regime_is_independent_of_generation_order() -> None:
    calibrations = _load_calibrations()
    sequential = ScenarioEngine(
        calibrations,
        seed=20260721,
        start_date=date(2027, 1, 1),
    )
    out_of_order = ScenarioEngine(
        calibrations,
        seed=20260721,
        start_date=date(2027, 1, 1),
    )

    sequential_regime = sequential.generate_day(40).economic_regime
    out_of_order.generate_day(200)
    out_of_order.generate_day(5)
    reordered_regime = out_of_order.generate_day(40).economic_regime

    assert reordered_regime == sequential_regime


def test_monthly_regime_sampling_preserves_calibrated_priors() -> None:
    calibrations = _load_calibrations()
    engine = ScenarioEngine(
        calibrations,
        seed=20260722,
        start_date=date(1900, 1, 1),
    )
    counts: Counter[str] = Counter()
    months = 2_400

    for month_index in range(months):
        year = 1900 + month_index // 12
        month = month_index % 12 + 1
        regime = engine._sample_economic_regime_for_month(year, month)
        counts[str(regime["regime_name"])] += 1

    for profile in calibrations["economic_profile"]["regime_profiles"]:
        name = str(profile["regime_name"])
        expected = float(profile["regime_probability"])
        observed = counts[name] / months
        assert observed == pytest.approx(expected, abs=0.025)


def test_days_in_different_months_use_month_level_paths() -> None:
    engine = ScenarioEngine(
        _load_calibrations(),
        seed=20260723,
        start_date=date(2027, 1, 1),
    )

    january = engine.generate_day(15)
    february = engine.generate_day(40)

    assert january.month == 1
    assert february.month == 2
    assert (2027, 1) in engine._economic_regime_cache
    assert (2027, 2) in engine._economic_regime_cache
