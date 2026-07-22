from __future__ import annotations

from copy import deepcopy

from simulation.application.contracts import DailyScenario
from simulation.domain.models import (
    FinancialLedger,
    InventoryPosition,
    Product,
    SCHEMA_VERSION,
    Store,
    Supplier,
    WorldState,
)
from simulation.engines.sales_v2 import SalesEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2
from simulation.validation.causal_protocol import validate_business_causality


def make_world(on_hand: int = 80) -> WorldState:
    world = WorldState(
        schema_version=SCHEMA_VERSION,
        simulation_day=0,
        current_date="2027-01-01",
        seed=7,
        stores=[Store("STORE_1", "CA", "Store", 10000, 0.0, 0.95)],
        products=[Product(
            "SKU_1", "FOODS", "FOODS_1", "SUP_1",
            2.0, 4.0, 0.01, 1.0,
        )],
        suppliers=[Supplier("SUP_1", "Supplier", 4, 0, 0.8, 1.0, 0.2)],
        inventory=[InventoryPosition(
            "STORE_1", "SKU_1", on_hand, 0, 0, 20, 100, 10,
        )],
        financials=FinancialLedger(),
    )
    world.validate()
    return world


def scenario(**overrides: float) -> DailyScenario:
    payload = dict(
        simulation_day=1,
        synthetic_date="2027-01-02",
        expected_demand_units=40.0,
        final_demand_multiplier=1.0,
        final_supply_multiplier=1.0,
        logistics_cost_multiplier=1.0,
        category="FOODS",
        department="FOODS_1",
        store="STORE_1",
        state="CA",
        economic_regime="stable",
    )
    payload.update(overrides)
    return DailyScenario(**payload)


def test_paired_causal_protocol_passes() -> None:
    report = validate_business_causality(make_world(), scenario())
    assert report.passed
    assert len(report.checks) == 5


def test_higher_demand_increases_requested_and_lost_units_when_constrained() -> None:
    low = SalesEngineV2(seed=3, demand_scale=1.0).apply(
        make_world(on_hand=20), scenario(expected_demand_units=10.0)
    )
    high = SalesEngineV2(seed=3, demand_scale=1.0).apply(
        make_world(on_hand=20), scenario(expected_demand_units=50.0)
    )
    assert high["requested_units"] > low["requested_units"]
    assert high["lost_units"] > low["lost_units"]


def test_supply_multiplier_controls_quantity_and_lead_time_monotonically() -> None:
    low_world = make_world(on_hand=0)
    high_world = make_world(on_hand=0)
    low = SupplierEngineV2(seed=4).create_orders(
        low_world, scenario(final_supply_multiplier=0.5)
    )[0]
    high = SupplierEngineV2(seed=4).create_orders(
        high_world, scenario(final_supply_multiplier=1.5)
    )[0]
    assert high.expected_units >= low.expected_units
    assert (
        high.expected_delivery_day - high.order_day
        <= low.expected_delivery_day - low.order_day
    )


def test_logistics_multiplier_propagates_to_order_cost() -> None:
    normal = SupplierEngineV2(seed=4).create_orders(
        make_world(on_hand=0), scenario(logistics_cost_multiplier=1.0)
    )[0]
    stressed = SupplierEngineV2(seed=4).create_orders(
        make_world(on_hand=0), scenario(logistics_cost_multiplier=2.0)
    )[0]
    assert stressed.logistics_cost_per_unit == 2 * normal.logistics_cost_per_unit


def test_order_receipt_inventory_conservation_across_days() -> None:
    world = make_world(on_hand=0)
    engine = SupplierEngineV2(seed=9)
    first = scenario(final_supply_multiplier=1.0)
    order = engine.create_orders(world, first)[0]
    assert world.inventory[0].in_transit == order.expected_units

    due = DailyScenario(
        simulation_day=order.expected_delivery_day,
        synthetic_date=order.expected_delivery_date,
        expected_demand_units=0.0,
        final_demand_multiplier=1.0,
        final_supply_multiplier=1.0,
        logistics_cost_multiplier=1.0,
        category="FOODS",
        department="FOODS_1",
        store="STORE_1",
        state="CA",
        economic_regime="stable",
    )
    before = world.inventory[0].on_hand + world.inventory[0].in_transit
    receipts = engine.receive_due_orders(world, due)
    after = world.inventory[0].on_hand + world.inventory[0].in_transit
    assert receipts
    assert after == before
