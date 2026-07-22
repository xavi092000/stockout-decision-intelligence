from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from simulation.application.contracts import DailyScenario
from simulation.domain.models import WorldState
from simulation.engines.sales_v2 import SalesEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2


class CausalValidationError(AssertionError):
    """Raised when a required business-causal relation is violated."""


@dataclass(frozen=True)
class CausalCheck:
    name: str
    baseline: float
    intervention: float
    expected_relation: str
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CausalValidationReport:
    checks: tuple[CausalCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "checks": [check.to_dict() for check in self.checks],
        }

    def assert_passed(self) -> None:
        failed = [check.name for check in self.checks if not check.passed]
        if failed:
            raise CausalValidationError(
                "Business-causal validation failed: " + ", ".join(failed)
            )


def _replace_scenario(
    scenario: DailyScenario,
    **changes: Any,
) -> DailyScenario:
    payload = asdict(scenario)
    payload.update(changes)
    return DailyScenario(**payload)


def validate_business_causality(
    world: WorldState,
    scenario: DailyScenario,
    *,
    sales_seed: int = 17,
    supplier_seed: int = 29,
) -> CausalValidationReport:
    """Run paired counterfactual checks on identical initial worlds.

    Each intervention changes one causal input while keeping seeds and all
    other state fixed. This makes the checks deterministic and guards the
    intended direction of the business relationships.
    """

    checks: list[CausalCheck] = []

    # Demand intervention -> requested units must increase.
    low_demand = _replace_scenario(
        scenario,
        expected_demand_units=max(0.1, scenario.expected_demand_units * 0.75),
    )
    high_demand = _replace_scenario(
        scenario,
        expected_demand_units=max(0.2, scenario.expected_demand_units * 1.25),
    )
    low_sales = SalesEngineV2(seed=sales_seed, demand_scale=1.0).apply(
        deepcopy(world), low_demand
    )
    high_sales = SalesEngineV2(seed=sales_seed, demand_scale=1.0).apply(
        deepcopy(world), high_demand
    )
    checks.append(CausalCheck(
        name="demand_increase_raises_requested_units",
        baseline=float(low_sales["requested_units"]),
        intervention=float(high_sales["requested_units"]),
        expected_relation="intervention > baseline",
        passed=high_sales["requested_units"] > low_sales["requested_units"],
    ))

    # Lower starting inventory -> lost units must not improve under same demand.
    stocked_world = deepcopy(world)
    constrained_world = deepcopy(world)
    for position in constrained_world.inventory:
        position.on_hand = min(position.on_hand, position.reserved)
    stocked_sales = SalesEngineV2(seed=sales_seed, demand_scale=1.0).apply(
        stocked_world, high_demand
    )
    constrained_sales = SalesEngineV2(seed=sales_seed, demand_scale=1.0).apply(
        constrained_world, high_demand
    )
    checks.append(CausalCheck(
        name="inventory_constraint_raises_lost_units",
        baseline=float(stocked_sales["lost_units"]),
        intervention=float(constrained_sales["lost_units"]),
        expected_relation="intervention >= baseline",
        passed=constrained_sales["lost_units"] >= stocked_sales["lost_units"],
    ))

    # Supply intervention -> expected quantity and delivery timing respond.
    low_supply_world = deepcopy(world)
    high_supply_world = deepcopy(world)
    for position in low_supply_world.inventory + high_supply_world.inventory:
        position.on_hand = 0
        position.in_transit = 0
    low_supply = _replace_scenario(scenario, final_supply_multiplier=0.5)
    high_supply = _replace_scenario(scenario, final_supply_multiplier=1.5)
    low_orders = SupplierEngineV2(seed=supplier_seed).create_orders(
        low_supply_world, low_supply
    )
    high_orders = SupplierEngineV2(seed=supplier_seed).create_orders(
        high_supply_world, high_supply
    )
    low_expected = sum(order.expected_units for order in low_orders)
    high_expected = sum(order.expected_units for order in high_orders)
    low_lead = sum(
        order.expected_delivery_day - order.order_day for order in low_orders
    )
    high_lead = sum(
        order.expected_delivery_day - order.order_day for order in high_orders
    )
    checks.append(CausalCheck(
        name="supply_improvement_raises_expected_receipts",
        baseline=float(low_expected),
        intervention=float(high_expected),
        expected_relation="intervention >= baseline",
        passed=high_expected >= low_expected,
    ))
    checks.append(CausalCheck(
        name="supply_improvement_shortens_lead_time",
        baseline=float(low_lead),
        intervention=float(high_lead),
        expected_relation="intervention <= baseline",
        passed=high_lead <= low_lead,
    ))

    # Logistics multiplier -> unit logistics cost is monotonic.
    normal_cost_world = deepcopy(world)
    stressed_cost_world = deepcopy(world)
    for position in normal_cost_world.inventory + stressed_cost_world.inventory:
        position.on_hand = 0
        position.in_transit = 0
    normal_cost = _replace_scenario(scenario, logistics_cost_multiplier=1.0)
    stressed_cost = _replace_scenario(scenario, logistics_cost_multiplier=1.8)
    normal_orders = SupplierEngineV2(seed=supplier_seed).create_orders(
        normal_cost_world, normal_cost
    )
    stressed_orders = SupplierEngineV2(seed=supplier_seed).create_orders(
        stressed_cost_world, stressed_cost
    )
    normal_total = sum(
        order.expected_units * order.logistics_cost_per_unit
        for order in normal_orders
    )
    stressed_total = sum(
        order.expected_units * order.logistics_cost_per_unit
        for order in stressed_orders
    )
    checks.append(CausalCheck(
        name="logistics_shock_raises_expected_logistics_cost",
        baseline=float(normal_total),
        intervention=float(stressed_total),
        expected_relation="intervention > baseline",
        passed=stressed_total > normal_total,
    ))

    report = CausalValidationReport(tuple(checks))
    report.assert_passed()
    return report
