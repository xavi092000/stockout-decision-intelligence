from __future__ import annotations

import pytest

from simulation.validation.economic_protocol import EconomicAcceptanceCriteria
from simulation.validation.economic_robustness import (
    DEFAULT_ECONOMIC_SCENARIOS,
    EconomicSensitivityScenario,
    OperationalEconomics,
    evaluate_robustness_campaign,
)


def run(*, fulfilled: int, unmet: int, stock: int, normal: int) -> OperationalEconomics:
    return OperationalEconomics(
        fulfilled_units=fulfilled,
        unmet_units=unmet,
        ending_stock_unit_days=stock,
        stockout_events=1 if unmet else 0,
        normal_order_units=normal,
        expedite_order_units=0,
        transferred_units=0,
    )


def permissive_criteria() -> EconomicAcceptanceCriteria:
    return EconomicAcceptanceCriteria(
        minimum_episodes=3,
        minimum_service_level=0.90,
        minimum_value_win_rate=0.60,
        minimum_joint_win_rate=0.50,
    )


def test_superior_candidate_passes_all_default_stress_scenarios() -> None:
    rule_runs = [run(fulfilled=95, unmet=5, stock=500, normal=100) for _ in range(5)]
    candidate_runs = [run(fulfilled=98, unmet=2, stock=300, normal=95) for _ in range(5)]

    result = evaluate_robustness_campaign(
        rule_runs=rule_runs,
        candidate_runs=candidate_runs,
        criteria=permissive_criteria(),
    )

    assert result.accepted
    assert result.failed_scenarios == ()
    assert result.worst_case_mean_value_delta > 0
    assert len(result.scenario_results) == len(DEFAULT_ECONOMIC_SCENARIOS)


def test_candidate_that_only_wins_under_nominal_costs_is_rejected() -> None:
    rule_runs = [run(fulfilled=96, unmet=4, stock=100, normal=100) for _ in range(5)]
    candidate_runs = [run(fulfilled=97, unmet=3, stock=100, normal=130) for _ in range(5)]
    scenarios = (
        EconomicSensitivityScenario(name="nominal"),
        EconomicSensitivityScenario(
            name="order_cost_stress",
            normal_order_cost_multiplier=3.0,
            expedite_order_cost_multiplier=3.0,
        ),
    )

    result = evaluate_robustness_campaign(
        rule_runs=rule_runs,
        candidate_runs=candidate_runs,
        scenarios=scenarios,
        criteria=permissive_criteria(),
    )

    assert not result.accepted
    assert "order_cost_stress" in result.failed_scenarios


def test_service_degradation_blocks_economic_acceptance() -> None:
    rule_runs = [run(fulfilled=98, unmet=2, stock=500, normal=100) for _ in range(5)]
    candidate_runs = [run(fulfilled=92, unmet=8, stock=10, normal=20) for _ in range(5)]

    result = evaluate_robustness_campaign(
        rule_runs=rule_runs,
        candidate_runs=candidate_runs,
        criteria=permissive_criteria(),
    )

    assert not result.accepted
    assert any(
        "service_not_degraded" in scenario.failed_checks
        for scenario in result.scenario_results
    )


def test_invalid_or_duplicate_scenarios_are_rejected() -> None:
    with pytest.raises(ValueError):
        EconomicSensitivityScenario(name="bad", holding_cost_multiplier=0)

    sample = [run(fulfilled=98, unmet=2, stock=100, normal=100) for _ in range(3)]
    duplicate = (
        EconomicSensitivityScenario(name="same"),
        EconomicSensitivityScenario(name="same"),
    )
    with pytest.raises(ValueError, match="unique"):
        evaluate_robustness_campaign(
            rule_runs=sample,
            candidate_runs=sample,
            scenarios=duplicate,
            criteria=permissive_criteria(),
        )
