from __future__ import annotations

import pytest

from simulation.economics import (
    CumulativeEconomicOutcome,
    DailyEconomicOutcome,
    EconomicConfig,
)
from simulation.validation.economic_protocol import (
    EconomicAcceptanceCriteria,
    evaluate_economic_superiority,
)


def test_economic_config_rejects_invalid_cost_ordering() -> None:
    with pytest.raises(ValueError):
        EconomicConfig(
            normal_order_cost_per_unit=12.0,
            expedite_order_cost_per_unit=8.0,
        )


def test_daily_business_value_reconciles_exactly() -> None:
    outcome = DailyEconomicOutcome(
        revenue=1000.0,
        normal_order_cost=100.0,
        expedite_order_cost=50.0,
        transfer_cost=10.0,
        holding_cost=20.0,
        lost_sales_cost=30.0,
        stockout_penalty=25.0,
        fulfilled_units=50,
        unmet_units=5,
        ending_stock_units=100,
        stockout_events=1,
        normal_order_units=10,
        expedite_order_units=5,
        transferred_units=5,
    )
    assert outcome.total_cost == pytest.approx(235.0)
    assert outcome.business_value == pytest.approx(765.0)
    assert outcome.service_level == pytest.approx(50 / 55)


def test_cumulative_economics_reconciles_and_tracks_service() -> None:
    cumulative = CumulativeEconomicOutcome()
    cumulative.add(
        DailyEconomicOutcome(
            revenue=100.0,
            normal_order_cost=10.0,
            expedite_order_cost=0.0,
            transfer_cost=0.0,
            holding_cost=2.0,
            lost_sales_cost=6.0,
            stockout_penalty=25.0,
            fulfilled_units=5,
            unmet_units=1,
            ending_stock_units=40,
            stockout_events=1,
            normal_order_units=1,
            expedite_order_units=0,
            transferred_units=0,
        )
    )
    assert cumulative.total_cost == pytest.approx(43.0)
    assert cumulative.business_value == pytest.approx(57.0)
    assert cumulative.service_level == pytest.approx(5 / 6)


def test_superiority_requires_value_and_service_evidence() -> None:
    result = evaluate_economic_superiority(
        episode_count=30,
        candidate_average_service_level=0.97,
        mean_value_delta=1200.0,
        value_ci95_low=200.0,
        mean_service_delta=0.002,
        value_win_rate=0.70,
        joint_value_service_win_rate=0.60,
    )
    assert result.accepted
    assert not result.reasons


def test_superiority_rejected_when_value_sacrifices_service() -> None:
    result = evaluate_economic_superiority(
        episode_count=30,
        candidate_average_service_level=0.90,
        mean_value_delta=1200.0,
        value_ci95_low=200.0,
        mean_service_delta=-0.03,
        value_win_rate=0.70,
        joint_value_service_win_rate=0.20,
    )
    assert not result.accepted
    assert "service_floor" in result.reasons
    assert "service_not_degraded" in result.reasons


def test_acceptance_criteria_validate_ranges() -> None:
    with pytest.raises(ValueError):
        EconomicAcceptanceCriteria(minimum_value_win_rate=1.1)
