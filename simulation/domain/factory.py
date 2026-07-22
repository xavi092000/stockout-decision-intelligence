from __future__ import annotations

from typing import Any

from simulation.domain.models import (
    FinancialLedger,
    InventoryPosition,
    Product,
    PurchaseOrder,
    SCHEMA_VERSION,
    Store,
    Supplier,
    WorldState,
)


class WorldFactory:
    """Creates validated domain objects from persisted dictionaries."""

    @staticmethod
    def supplier(row: dict[str, Any]) -> Supplier:
        # Backward-compatible aliases for previous Sprint 7A files.
        base_lead = row.get(
            "base_lead_time_days",
            row.get("lead_time_days", row.get("base_lead_days", 5)),
        )
        variability = row.get(
            "lead_time_variability_days",
            row.get("variability_days", row.get("lead_time_variability", 2)),
        )
        logistics_cost = row.get(
            "logistics_cost_per_unit",
            row.get("shipping_cost_per_unit", 0.25),
        )

        return Supplier(
            supplier_id=str(row["supplier_id"]),
            name=str(row.get("name", row["supplier_id"])),
            base_lead_time_days=int(base_lead),
            lead_time_variability_days=int(variability),
            fill_rate=float(row.get("fill_rate", 0.95)),
            reliability_score=float(
                row.get("reliability_score", row.get("reliability", 0.95))
            ),
            logistics_cost_per_unit=float(logistics_cost),
        )

    @staticmethod
    def store(row: dict[str, Any]) -> Store:
        return Store(
            store_id=str(row["store_id"]),
            state_id=str(row.get("state_id", "UNKNOWN_STATE")),
            name=str(row.get("name", row["store_id"])),
            capacity_units=int(row.get("capacity_units", 10000)),
            operating_cost_per_day=float(
                row.get("operating_cost_per_day", 0.0)
            ),
            service_level_target=float(
                row.get("service_level_target", 0.95)
            ),
        )

    @staticmethod
    def product(row: dict[str, Any]) -> Product:
        shelf_life = row.get("shelf_life_days")
        return Product(
            sku_id=str(row["sku_id"]),
            category=str(row.get("category", "UNKNOWN_CATEGORY")),
            department=str(
                row.get("department", "UNKNOWN_DEPARTMENT")
            ),
            supplier_id=str(row["supplier_id"]),
            unit_cost=float(row.get("unit_cost", 0.0)),
            unit_price=float(row.get("unit_price", row.get("unit_cost", 0.0))),
            holding_cost_per_unit_day=float(
                row.get("holding_cost_per_unit_day", 0.0)
            ),
            stockout_penalty_per_unit=float(
                row.get("stockout_penalty_per_unit", 0.0)
            ),
            shelf_life_days=(
                int(shelf_life) if shelf_life not in (None, "", "null") else None
            ),
        )

    @staticmethod
    def inventory(row: dict[str, Any]) -> InventoryPosition:
        return InventoryPosition(
            store_id=str(row["store_id"]),
            sku_id=str(row["sku_id"]),
            on_hand=int(row.get("on_hand", 0)),
            reserved=int(row.get("reserved", 0)),
            in_transit=int(row.get("in_transit", 0)),
            reorder_point=int(row.get("reorder_point", 0)),
            target_stock=int(row.get("target_stock", 0)),
            safety_stock=int(row.get("safety_stock", 0)),
            last_updated_day=int(row.get("last_updated_day", 0)),
        )

    @staticmethod
    def purchase_order(row: dict[str, Any]) -> PurchaseOrder:
        return PurchaseOrder(
            order_id=str(row["order_id"]),
            store_id=str(row["store_id"]),
            sku_id=str(row["sku_id"]),
            supplier_id=str(row["supplier_id"]),
            order_day=int(row["order_day"]),
            order_date=str(row["order_date"]),
            ordered_units=int(row["ordered_units"]),
            expected_units=int(row["expected_units"]),
            received_units=int(row.get("received_units", 0)),
            expected_delivery_day=int(row["expected_delivery_day"]),
            expected_delivery_date=str(row["expected_delivery_date"]),
            status=str(row.get("status", "OPEN")),
            unit_cost=float(row.get("unit_cost", 0.0)),
            logistics_cost_per_unit=float(
                row.get("logistics_cost_per_unit", 0.0)
            ),
        )

    @staticmethod
    def financials(row: dict[str, Any]) -> FinancialLedger:
        allowed = {
            "revenue",
            "cost_of_goods_sold",
            "holding_cost",
            "stockout_cost",
            "logistics_cost",
            "procurement_cost",
            "operating_cost",
            "gross_profit",
            "initial_inventory_value",
        }
        normalized = {
            key: float(row.get(key, 0.0))
            for key in allowed
        }
        return FinancialLedger(**normalized)

    @classmethod
    def world(cls, payload: dict[str, Any]) -> WorldState:
        orders = payload.get(
            "purchase_orders",
            payload.get("pending_orders", []),
        )

        world = WorldState(
            schema_version=SCHEMA_VERSION,
            simulation_day=int(payload.get("simulation_day", 0)),
            current_date=str(payload.get("current_date", "2027-01-01")),
            seed=int(payload.get("seed", 42)),
            stores=[cls.store(row) for row in payload.get("stores", [])],
            products=[
                cls.product(row) for row in payload.get("products", [])
            ],
            suppliers=[
                cls.supplier(row) for row in payload.get("suppliers", [])
            ],
            inventory=[
                cls.inventory(row) for row in payload.get("inventory", [])
            ],
            purchase_orders=[
                cls.purchase_order(row) for row in orders
            ],
            financials=cls.financials(
                payload.get("financials", {})
            ),
            metadata={
                **payload.get("metadata", {}),
                "migrated_to_schema": SCHEMA_VERSION,
            },
        )
        world.validate()
        return world
