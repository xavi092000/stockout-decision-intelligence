from __future__ import annotations

import pytest

from simulation.application.contracts import DailyScenario
from simulation.domain.models import (
    FinancialLedger, InventoryPosition, Product, SCHEMA_VERSION,
    Store, Supplier, WorldState,
)
from simulation.engines.inventory_v2 import InventoryEngineV2
from simulation.engines.sales_v2 import SalesEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2


def make_world(on_hand: int = 1000, fill_rate: float = 0.8) -> WorldState:
    world = WorldState(
        schema_version=SCHEMA_VERSION, simulation_day=0,
        current_date="2027-01-01", seed=7,
        stores=[Store("STORE_1", "CA", "Store", 10000, 0.0, 0.95)],
        products=[Product("SKU_1", "FOODS", "FOODS_1", "SUP_1", 2.0, 4.0, 0.01, 1.0)],
        suppliers=[Supplier("SUP_1", "Supplier", 2, 0, fill_rate, 1.0, 0.2)],
        inventory=[InventoryPosition("STORE_1", "SKU_1", on_hand, 0, 0, 20, 100, 10)],
        financials=FinancialLedger(),
    )
    world.validate()
    return world


def scenario(demand: float = 10.0, demand_multiplier: float = 2.0, supply_multiplier: float = 1.0) -> DailyScenario:
    return DailyScenario(
        simulation_day=1, synthetic_date="2027-01-02",
        expected_demand_units=demand,
        final_demand_multiplier=demand_multiplier,
        final_supply_multiplier=supply_multiplier,
        logistics_cost_multiplier=1.0,
        category="FOODS", department="FOODS_1",
        store="STORE_1", state="CA", economic_regime="stable",
    )


def test_sales_does_not_apply_final_demand_multiplier_twice() -> None:
    result = SalesEngineV2(seed=1, demand_scale=1.0).apply(
        make_world(), scenario(demand=10.0, demand_multiplier=2.0)
    )
    assert result["requested_units"] == 10


def test_inventory_engine_uses_same_single_application_contract() -> None:
    result = InventoryEngineV2(seed=1, demand_scale=1.0).apply(
        make_world(), scenario(demand=10.0, demand_multiplier=3.0)
    )
    assert result["requested_units"] == 10


def test_supply_multiplier_reduces_expected_receipts() -> None:
    world = make_world(on_hand=0, fill_rate=0.8)
    orders = SupplierEngineV2(seed=1).create_orders(
        world, scenario(supply_multiplier=0.5)
    )
    assert len(orders) == 1
    assert orders[0].ordered_units == 100
    assert orders[0].expected_units == 40


def test_supply_multiplier_is_capped_at_ordered_quantity() -> None:
    world = make_world(on_hand=0, fill_rate=0.8)
    orders = SupplierEngineV2(seed=1).create_orders(
        world, scenario(supply_multiplier=2.0)
    )
    assert orders[0].expected_units == orders[0].ordered_units


@pytest.mark.parametrize("field,value", [
    ("expected_demand_units", -1.0),
    ("final_demand_multiplier", 0.0),
    ("final_supply_multiplier", 0.0),
    ("logistics_cost_multiplier", 0.0),
])
def test_daily_scenario_rejects_invalid_scientific_inputs(field: str, value: float) -> None:
    payload = dict(
        simulation_day=1, synthetic_date="2027-01-02",
        expected_demand_units=10.0, final_demand_multiplier=1.0,
        final_supply_multiplier=1.0, logistics_cost_multiplier=1.0,
        category="FOODS", department="FOODS_1", store="STORE_1",
        state="CA", economic_regime="stable",
    )
    payload[field] = value
    with pytest.raises(ValueError):
        DailyScenario(**payload)


def test_demand_scale_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SalesEngineV2(demand_scale=0)
    with pytest.raises(ValueError):
        InventoryEngineV2(demand_scale=-1)
