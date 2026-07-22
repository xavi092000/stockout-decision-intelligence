from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest

from simulation.calibration_repository import CalibrationRepository
from simulation.scenario_engine import ScenarioEngine
from simulation.validation.synthetic_generation import (
    SyntheticGenerationError,
    SyntheticGenerationThresholds,
    SyntheticGenerationValidator,
    scenario_digest,
)


@pytest.fixture(scope="module")
def calibrations():
    return CalibrationRepository(
        "reality_calibration/data/processed/calibration",
        "reality_calibration/data/processed/weather_calibration",
        "reality_calibration/data/processed/economic_calibration",
    ).load()


@pytest.fixture(scope="module")
def campaign(calibrations):
    return ScenarioEngine(
        calibrations=calibrations,
        seed=42,
        start_date=date(2027, 1, 1),
    ).generate_days(18_250)


def test_full_synthetic_generation_campaign_passes(calibrations, campaign):
    reference = ScenarioEngine(
        calibrations=calibrations,
        seed=42,
        start_date=date(2027, 1, 1),
    ).generate_days(18_250)
    report = SyntheticGenerationValidator(calibrations).evaluate(
        campaign,
        reproducibility_reference=reference,
    )
    assert report.passed, [metric.to_dict() for metric in report.failed_metrics()]
    assert report.sample_size == 18_250


def test_same_seed_reproduces_business_world(calibrations):
    first = ScenarioEngine(calibrations, seed=777).generate_days(365)
    second = ScenarioEngine(calibrations, seed=777).generate_days(365)
    different = ScenarioEngine(calibrations, seed=778).generate_days(365)
    assert scenario_digest(first) == scenario_digest(second)
    assert scenario_digest(first) != scenario_digest(different)


def test_validator_detects_broken_hierarchy(calibrations, campaign):
    broken = list(campaign[:100])
    broken[0] = replace(broken[0], state="INVALID")
    report = SyntheticGenerationValidator(
        calibrations,
        SyntheticGenerationThresholds(
            minimum_scenarios=1,
            require_full_calibration_coverage=False,
            require_all_declared_event_types=False,
            require_reproducibility_match=False,
        ),
    ).evaluate(broken, enforce_minimum_sample=False)
    failed = {metric.name for metric in report.failed_metrics()}
    assert "hierarchy_integrity" in failed


def test_validator_detects_temporal_break(calibrations, campaign):
    broken = list(campaign[:100])
    broken[1] = replace(broken[1], simulation_day=99)
    report = SyntheticGenerationValidator(
        calibrations,
        SyntheticGenerationThresholds(
            minimum_scenarios=1,
            require_full_calibration_coverage=False,
            require_all_declared_event_types=False,
            require_reproducibility_match=False,
        ),
    ).evaluate(broken, enforce_minimum_sample=False)
    failed = {metric.name for metric in report.failed_metrics()}
    assert "temporal_coherence" in failed


def test_validator_rejects_too_small_campaign(calibrations, campaign):
    with pytest.raises(SyntheticGenerationError):
        SyntheticGenerationValidator(calibrations).evaluate(campaign[:10])
