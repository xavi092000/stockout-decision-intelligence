from __future__ import annotations

from dataclasses import dataclass, replace
from math import sqrt
from statistics import mean, stdev

from simulation.economics import EconomicConfig
from simulation.validation.economic_protocol import (
    EconomicAcceptanceCriteria,
    EconomicValidationResult,
    evaluate_economic_superiority,
)


@dataclass(frozen=True)
class EconomicSensitivityScenario:
    name: str
    selling_price_multiplier: float = 1.0
    normal_order_cost_multiplier: float = 1.0
    expedite_order_cost_multiplier: float = 1.0
    transfer_cost_multiplier: float = 1.0
    holding_cost_multiplier: float = 1.0
    lost_sale_cost_multiplier: float = 1.0
    stockout_penalty_multiplier: float = 1.0
    mandatory: bool = True

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if field_name in {"name", "mandatory"}:
                continue
            if value <= 0:
                raise ValueError(f"{field_name} must be greater than zero.")

    def apply(self, base: EconomicConfig | None = None) -> EconomicConfig:
        base = base or EconomicConfig()
        return replace(
            base,
            selling_price_per_unit=(
                base.selling_price_per_unit * self.selling_price_multiplier
            ),
            normal_order_cost_per_unit=(
                base.normal_order_cost_per_unit
                * self.normal_order_cost_multiplier
            ),
            expedite_order_cost_per_unit=(
                base.expedite_order_cost_per_unit
                * self.expedite_order_cost_multiplier
            ),
            transfer_cost_per_unit=(
                base.transfer_cost_per_unit * self.transfer_cost_multiplier
            ),
            holding_cost_per_unit_per_day=(
                base.holding_cost_per_unit_per_day
                * self.holding_cost_multiplier
            ),
            lost_sale_cost_per_unit=(
                base.lost_sale_cost_per_unit
                * self.lost_sale_cost_multiplier
            ),
            stockout_penalty_per_event=(
                base.stockout_penalty_per_event
                * self.stockout_penalty_multiplier
            ),
        )


DEFAULT_ECONOMIC_SCENARIOS = (
    EconomicSensitivityScenario(name="nominal"),
    EconomicSensitivityScenario(
        name="compressed_margin",
        selling_price_multiplier=0.90,
        normal_order_cost_multiplier=1.10,
        expedite_order_cost_multiplier=1.10,
    ),
    EconomicSensitivityScenario(
        name="high_holding_cost",
        holding_cost_multiplier=2.00,
    ),
    EconomicSensitivityScenario(
        name="high_service_failure_cost",
        lost_sale_cost_multiplier=1.50,
        stockout_penalty_multiplier=1.50,
    ),
    EconomicSensitivityScenario(
        name="high_logistics_cost",
        normal_order_cost_multiplier=1.20,
        expedite_order_cost_multiplier=1.30,
        transfer_cost_multiplier=1.30,
    ),
)


@dataclass(frozen=True)
class OperationalEconomics:
    fulfilled_units: int
    unmet_units: int
    ending_stock_unit_days: int
    stockout_events: int
    normal_order_units: int
    expedite_order_units: int
    transferred_units: int

    @property
    def service_level(self) -> float:
        total = self.fulfilled_units + self.unmet_units
        return 1.0 if total == 0 else self.fulfilled_units / total

    def business_value(self, config: EconomicConfig) -> float:
        revenue = self.fulfilled_units * config.selling_price_per_unit
        total_cost = (
            self.normal_order_units * config.normal_order_cost_per_unit
            + self.expedite_order_units * config.expedite_order_cost_per_unit
            + self.transferred_units * config.transfer_cost_per_unit
            + self.ending_stock_unit_days
            * config.holding_cost_per_unit_per_day
            + self.unmet_units * config.lost_sale_cost_per_unit
            + self.stockout_events * config.stockout_penalty_per_event
        )
        return revenue - total_cost


@dataclass(frozen=True)
class ScenarioAcceptance:
    scenario: str
    accepted: bool
    mean_value_delta: float
    value_ci95_low: float
    value_ci95_high: float
    mean_service_delta: float
    candidate_average_service_level: float
    value_win_rate: float
    joint_win_rate: float
    failed_checks: tuple[str, ...]
    mandatory: bool


@dataclass(frozen=True)
class EconomicRobustnessResult:
    accepted: bool
    scenario_results: tuple[ScenarioAcceptance, ...]
    failed_scenarios: tuple[str, ...]
    worst_case_mean_value_delta: float


def confidence_interval_95(values: list[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("At least one paired value is required.")
    average = mean(values)
    if len(values) == 1:
        return average, average
    margin = 1.96 * stdev(values) / sqrt(len(values))
    return average - margin, average + margin


def evaluate_scenario(
    *,
    scenario: EconomicSensitivityScenario,
    rule_runs: list[OperationalEconomics],
    candidate_runs: list[OperationalEconomics],
    criteria: EconomicAcceptanceCriteria | None = None,
    base_config: EconomicConfig | None = None,
) -> ScenarioAcceptance:
    if len(rule_runs) != len(candidate_runs):
        raise ValueError("Paired policy runs must have equal lengths.")
    if not rule_runs:
        raise ValueError("At least one paired policy run is required.")

    config = scenario.apply(base_config)
    value_deltas = [
        candidate.business_value(config) - rule.business_value(config)
        for rule, candidate in zip(rule_runs, candidate_runs, strict=True)
    ]
    service_deltas = [
        candidate.service_level - rule.service_level
        for rule, candidate in zip(rule_runs, candidate_runs, strict=True)
    ]
    low, high = confidence_interval_95(value_deltas)
    value_wins = sum(value > 0 for value in value_deltas) / len(value_deltas)
    joint_wins = sum(
        value > 0 and service >= 0
        for value, service in zip(value_deltas, service_deltas, strict=True)
    ) / len(value_deltas)

    acceptance: EconomicValidationResult = evaluate_economic_superiority(
        episode_count=len(value_deltas),
        candidate_average_service_level=mean(
            run.service_level for run in candidate_runs
        ),
        mean_value_delta=mean(value_deltas),
        value_ci95_low=low,
        mean_service_delta=mean(service_deltas),
        value_win_rate=value_wins,
        joint_value_service_win_rate=joint_wins,
        criteria=criteria,
    )
    return ScenarioAcceptance(
        scenario=scenario.name,
        accepted=acceptance.accepted,
        mean_value_delta=mean(value_deltas),
        value_ci95_low=low,
        value_ci95_high=high,
        mean_service_delta=mean(service_deltas),
        candidate_average_service_level=mean(
            run.service_level for run in candidate_runs
        ),
        value_win_rate=value_wins,
        joint_win_rate=joint_wins,
        failed_checks=acceptance.reasons,
        mandatory=scenario.mandatory,
    )


def evaluate_robustness_campaign(
    *,
    rule_runs: list[OperationalEconomics],
    candidate_runs: list[OperationalEconomics],
    scenarios: tuple[EconomicSensitivityScenario, ...] = DEFAULT_ECONOMIC_SCENARIOS,
    criteria: EconomicAcceptanceCriteria | None = None,
    base_config: EconomicConfig | None = None,
) -> EconomicRobustnessResult:
    if not scenarios:
        raise ValueError("At least one economic scenario is required.")
    names = [scenario.name for scenario in scenarios]
    if len(names) != len(set(names)):
        raise ValueError("Economic scenario names must be unique.")

    results = tuple(
        evaluate_scenario(
            scenario=scenario,
            rule_runs=rule_runs,
            candidate_runs=candidate_runs,
            criteria=criteria,
            base_config=base_config,
        )
        for scenario in scenarios
    )
    failed = tuple(
        result.scenario
        for result in results
        if result.mandatory and not result.accepted
    )
    return EconomicRobustnessResult(
        accepted=not failed,
        scenario_results=results,
        failed_scenarios=failed,
        worst_case_mean_value_delta=min(
            result.mean_value_delta for result in results
        ),
    )
