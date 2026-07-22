from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from random import Random
from typing import Any


class SupplierEngineError(RuntimeError):
    """Raised when supplier or purchase-order state becomes invalid."""


@dataclass
class PurchaseOrder:
    order_id: str
    store_id: str
    sku_id: str
    supplier_id: str
    order_day: int
    order_date: str
    ordered_units: int
    expected_units: int
    received_units: int
    expected_delivery_day: int
    expected_delivery_date: str
    status: str
    unit_cost: float
    logistics_cost_per_unit: float
    supplier_fill_rate: float
    supplier_reliability_score: float

    @property
    def open_units(self) -> int:
        return max(0, self.expected_units - self.received_units)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["open_units"] = self.open_units
        return payload


class SupplierOrderEngine:
    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.random = Random(seed)
        self._order_counter = 0

    @staticmethod
    def _supplier_index(
        world: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return {
            str(row["supplier_id"]): row
            for row in world["suppliers"]
        }

    @staticmethod
    def _product_index(
        world: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return {
            str(row["sku_id"]): row
            for row in world["products"]
        }

    @staticmethod
    def _open_order_keys(
        pending_orders: list[dict[str, Any]],
    ) -> set[tuple[str, str]]:
        return {
            (str(order["store_id"]), str(order["sku_id"]))
            for order in pending_orders
            if str(order.get("status")) in {"OPEN", "PARTIALLY_RECEIVED"}
            and int(order.get("open_units", 0)) > 0
        }

    def create_replenishment_orders(
        self,
        world: dict[str, Any],
        simulation_day: int,
        current_date: str,
        logistics_multiplier: float,
    ) -> list[PurchaseOrder]:
        suppliers = self._supplier_index(world)
        products = self._product_index(world)
        pending_orders = world.setdefault("pending_orders", [])
        open_keys = self._open_order_keys(pending_orders)

        created: list[PurchaseOrder] = []

        for position in world["inventory"]:
            store_id = str(position["store_id"])
            sku_id = str(position["sku_id"])
            key = (store_id, sku_id)

            inventory_position = int(position["inventory_position"])
            reorder_point = int(position["reorder_point"])
            target_stock = int(position["target_stock"])

            if inventory_position > reorder_point or key in open_keys:
                continue

            product = products[sku_id]
            supplier = suppliers[str(product["supplier_id"])]

            ordered_units = max(1, target_stock - inventory_position)
            fill_rate = float(supplier["fill_rate"])
            expected_units = max(
                1,
                int(round(ordered_units * fill_rate)),
            )

            base_lead = int(supplier["base_lead_time_days"])
            variability = int(supplier["lead_time_variability_days"])
            reliability = float(supplier["reliability_score"])

            delay = self.random.randint(0, max(0, variability))
            if self.random.random() > reliability:
                delay += self.random.randint(1, max(2, variability + 2))

            lead_time = max(1, base_lead + delay)
            delivery_day = simulation_day + lead_time
            delivery_date = (
                date.fromisoformat(current_date) + timedelta(days=lead_time)
            ).isoformat()

            self._order_counter += 1
            order = PurchaseOrder(
                order_id=f"PO-{simulation_day:04d}-{self._order_counter:06d}",
                store_id=store_id,
                sku_id=sku_id,
                supplier_id=str(product["supplier_id"]),
                order_day=simulation_day,
                order_date=current_date,
                ordered_units=ordered_units,
                expected_units=expected_units,
                received_units=0,
                expected_delivery_day=delivery_day,
                expected_delivery_date=delivery_date,
                status="OPEN",
                unit_cost=float(product["unit_cost"]),
                logistics_cost_per_unit=round(
                    float(supplier["logistics_cost_per_unit"])
                    * max(0.01, logistics_multiplier),
                    6,
                ),
                supplier_fill_rate=fill_rate,
                supplier_reliability_score=reliability,
            )
            created.append(order)
            pending_orders.append(order.to_dict())
            position["in_transit"] = (
                int(position["in_transit"]) + expected_units
            )
            position["inventory_position"] = (
                int(position["available"]) + int(position["in_transit"])
            )
            open_keys.add(key)

        return created

    def receive_due_orders(
        self,
        world: dict[str, Any],
        simulation_day: int,
        current_date: str,
    ) -> list[dict[str, Any]]:
        inventory_index = {
            (str(row["store_id"]), str(row["sku_id"])): row
            for row in world["inventory"]
        }
        receipts: list[dict[str, Any]] = []

        for order in world.setdefault("pending_orders", []):
            if str(order.get("status")) not in {
                "OPEN",
                "PARTIALLY_RECEIVED",
            }:
                continue

            open_units = max(
                0,
                int(order["expected_units"])
                - int(order["received_units"]),
            )
            if open_units <= 0:
                order["status"] = "RECEIVED"
                order["open_units"] = 0
                continue

            if int(order["expected_delivery_day"]) > simulation_day:
                order["open_units"] = open_units
                continue

            key = (str(order["store_id"]), str(order["sku_id"]))
            if key not in inventory_index:
                raise SupplierEngineError(
                    f"Order references missing inventory position: {key}"
                )

            # Some due orders are delivered in two parts.
            if (
                open_units >= 4
                and order["status"] == "OPEN"
                and self.random.random() < 0.18
            ):
                received_now = max(
                    1,
                    int(round(open_units * self.random.uniform(0.45, 0.75))),
                )
            else:
                received_now = open_units

            position = inventory_index[key]
            stock_before = int(position["on_hand"])
            in_transit_before = int(position["in_transit"])

            position["on_hand"] = stock_before + received_now
            position["in_transit"] = max(
                0,
                in_transit_before - received_now,
            )
            position["available"] = max(
                0,
                int(position["on_hand"]) - int(position["reserved"]),
            )
            position["inventory_position"] = (
                int(position["available"]) + int(position["in_transit"])
            )
            position["last_updated_day"] = simulation_day

            order["received_units"] = (
                int(order["received_units"]) + received_now
            )
            remaining = max(
                0,
                int(order["expected_units"])
                - int(order["received_units"]),
            )
            order["open_units"] = remaining

            if remaining == 0:
                order["status"] = "RECEIVED"
            else:
                order["status"] = "PARTIALLY_RECEIVED"
                order["expected_delivery_day"] = simulation_day + 1
                order["expected_delivery_date"] = (
                    date.fromisoformat(current_date) + timedelta(days=1)
                ).isoformat()

            receipts.append(
                {
                    "receipt_id": (
                        f"REC-{simulation_day:04d}-"
                        f"{len(receipts) + 1:06d}"
                    ),
                    "order_id": str(order["order_id"]),
                    "simulation_day": simulation_day,
                    "date": current_date,
                    "store_id": str(order["store_id"]),
                    "sku_id": str(order["sku_id"]),
                    "supplier_id": str(order["supplier_id"]),
                    "received_units": received_now,
                    "stock_before": stock_before,
                    "stock_after": int(position["on_hand"]),
                    "in_transit_before": in_transit_before,
                    "in_transit_after": int(position["in_transit"]),
                    "order_status_after": str(order["status"]),
                    "procurement_cost": round(
                        received_now * float(order["unit_cost"]),
                        2,
                    ),
                    "logistics_cost": round(
                        received_now
                        * float(order["logistics_cost_per_unit"]),
                        2,
                    ),
                }
            )

        return receipts
