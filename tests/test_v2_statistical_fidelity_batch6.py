from __future__ import annotations

from datetime import date

import pytest

from simulation.calibration_repository import CalibrationRepository
from simulation.scenario_engine import ScenarioEngine
from simulation.validation.statistical_fidelity import (
    FidelityThresholds,
    StatisticalFidelityError,
    StatisticalFidelityValidator,
)


def _calibrations():
    return CalibrationRepository(
        "reality_calibration/data/processed/calibration",
        "reality_calibration/data/processed/weather_calibration",
        "reality_calibration/data/processed/economic_calibration",
    ).load()


def test_threshold_contract_rejects_invalid_values():
    with pytest.raises(StatisticalFidelityError):
        FidelityThresholds(categorical_total_variation_max=1.1).validate()
    with pytest.raises(StatisticalFidelityError):
        FidelityThresholds(minimum_scenarios=0).validate()


def test_validator_enforces_minimum_sample_size():
    calibrations = _calibrations()
    scenarios = ScenarioEngine(calibrations, seed=7).generate_days(30)
    validator = StatisticalFidelityValidator(
        calibrations, FidelityThresholds(minimum_scenarios=31)
    )
    with pytest.raises(StatisticalFidelityError):
        validator.evaluate(scenarios)


def test_hierarchy_integrity_is_measured_and_passes():
    calibrations = _calibrations()
    scenarios = ScenarioEngine(calibrations, seed=8).generate_days(365)
    report = StatisticalFidelityValidator(
        calibrations, FidelityThresholds(minimum_scenarios=365)
    ).evaluate(scenarios)
    metrics = {metric.name: metric for metric in report.metrics}
    assert metrics["product_hierarchy_violation_rate"].passed
    assert metrics["location_hierarchy_violation_rate"].passed
    assert metrics["product_hierarchy_violation_rate"].observed == 0.0
    assert metrics["location_hierarchy_violation_rate"].observed == 0.0


def test_full_statistical_fidelity_campaign_passes():
    calibrations = _calibrations()
    scenarios = ScenarioEngine(
        calibrations,
        seed=42,
        start_date=date(2027, 1, 1),
    ).generate_days(18_250)
    report = StatisticalFidelityValidator(calibrations).evaluate(scenarios)
    failures = [
        f"{metric.name}: {metric.error} > {metric.threshold}"
        for metric in report.failed_metrics()
    ]
    assert report.passed, failures
