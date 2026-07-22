from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from random import Random
from typing import Any

from simulation.application.contracts import DailyScenario
from simulation.domain.models import PurchaseOrder, WorldState


class SupplierEngineV2Error(RuntimeError):
    """Raised when supplier transitions violate domain invariants."""


@dataclass(frozen=True)
class SupplierReceipt:
    receipt_id: str
    order_id: str
    simulation_day: int
    date: str
    store_id: str
    sku_id: str
    supplier_id: str
    received_units: int
    procurement_cost: float
    logistics_cost: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SupplierEngineV2:
    def __init__(self, seed: int = 143) -> None:
        self.random = Random(seed)
        self.order_counter = 0
        self.receipt_counter = 0

    def receive_due_orders(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> list[SupplierReceipt]:
        receipts: list[SupplierReceipt] = []

        inventory_index = {
            (item.store_id, item.sku_id): item
            for item in world.inventory
        }

        for order in world.purchase_orders:
            if order.status not in {"OPEN", "PARTIALLY_RECEIVED"}:
                continue
            if order.expected_delivery_day > scenario.simulation_day:
                continue
            if order.open_units <= 0:
                order.status = "RECEIVED"
                continue

            received_now = order.open_units
            if (
                received_now >= 4
                and order.status == "OPEN"
                and self.random.random() < 0.18
            ):
                received_now = max(
                    1,
                    int(round(
                        received_now
                        * self.random.uniform(0.45, 0.75)
                    )),
                )

            key = (order.store_id, order.sku_id)
            if key not in inventory_index:
                raise SupplierEngineV2Error(
                    f"Missing inventory position for order {order.order_id}."
                )

            position = inventory_index[key]
            position.on_hand += received_now
            position.in_transit = max(
                0,
                position.in_transit - received_now,
            )
            position.last_updated_day = scenario.simulation_day

            order.received_units += received_now
            if order.open_units == 0:
                order.status = "RECEIVED"
            else:
                order.status = "PARTIALLY_RECEIVED"
                order.expected_delivery_day = (
                    scenario.simulation_day + 1
                )
                order.expected_delivery_date = (
                    date.fromisoformat(scenario.synthetic_date)
                    + timedelta(days=1)
                ).isoformat()

            self.receipt_counter += 1
            receipts.append(
                SupplierReceipt(
                    receipt_id=(
                        f"REC-{scenario.simulation_day:04d}-"
                        f"{self.receipt_counter:06d}"
                    ),
                    order_id=order.order_id,
                    simulation_day=scenario.simulation_day,
                    date=scenario.synthetic_date,
                    store_id=order.store_id,
                    sku_id=order.sku_id,
                    supplier_id=order.supplier_id,
                    received_units=received_now,
                    procurement_cost=round(
                        received_now * order.unit_cost,
                        2,
                    ),
                    logistics_cost=round(
                        received_now
                        * order.logistics_cost_per_unit,
                        2,
                    ),
                )
            )

        world.validate()
        return receipts

    def create_orders(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> list[PurchaseOrder]:
        product_index = {
            item.sku_id: item for item in world.products
        }
        supplier_index = {
            item.supplier_id: item for item in world.suppliers
        }
        open_keys = {
            (order.store_id, order.sku_id)
            for order in world.purchase_orders
            if order.status in {"OPEN", "PARTIALLY_RECEIVED"}
            and order.open_units > 0
        }

        created: list[PurchaseOrder] = []

        for position in world.inventory:
            key = (position.store_id, position.sku_id)

            if position.inventory_position > position.reorder_point:
                continue
            if key in open_keys:
                continue

            product = product_index[position.sku_id]
            supplier = supplier_index[product.supplier_id]

            ordered_units = max(
                1,
                position.target_stock - position.inventory_position,
            )
            effective_fill_rate = min(
                1.0,
                max(
                    0.01,
                    supplier.fill_rate
                    * scenario.final_supply_multiplier,
                ),
            )
            expected_units = max(
                1,
                min(
                    ordered_units,
                    int(round(ordered_units * effective_fill_rate)),
                ),
            )

            delay = self.random.randint(
                0,
                supplier.lead_time_variability_days,
            )
            if self.random.random() > supplier.reliability_score:
                delay += self.random.randint(
                    1,
                    max(
                        2,
                        supplier.lead_time_variability_days + 2,
                    ),
                )

            # Supply conditions affect both the expected quantity and
            # the delivery timing. A multiplier below 1.0 represents
            # constrained capacity / disruption and therefore lengthens
            # lead time; a multiplier above 1.0 represents expedited or
            # resilient supply and may shorten it, never below one day.
            supply_timing_factor = max(
                0.25,
                min(2.0, scenario.final_supply_multiplier),
            )
            adjusted_base_lead_time = max(
                1,
                int(round(
                    supplier.base_lead_time_days / supply_timing_factor
                )),
            )
            lead_time = max(
                1,
                adjusted_base_lead_time + delay,
            )

            self.order_counter += 1
            order = PurchaseOrder(
                order_id=(
                    f"PO-{scenario.simulation_day:04d}-"
                    f"{self.order_counter:06d}"
                ),
                store_id=position.store_id,
                sku_id=position.sku_id,
                supplier_id=supplier.supplier_id,
                order_day=scenario.simulation_day,
                order_date=scenario.synthetic_date,
                ordered_units=ordered_units,
                expected_units=expected_units,
                received_units=0,
                expected_delivery_day=(
                    scenario.simulation_day + lead_time
                ),
                expected_delivery_date=(
                    date.fromisoformat(scenario.synthetic_date)
                    + timedelta(days=lead_time)
                ).isoformat(),
                status="OPEN",
                unit_cost=product.unit_cost,
                logistics_cost_per_unit=round(
                    supplier.logistics_cost_per_unit
                    * max(
                        0.01,
                        scenario.logistics_cost_multiplier,
                    ),
                    6,
                ),
            )
            order.validate()

            world.purchase_orders.append(order)
            position.in_transit += expected_units
            position.last_updated_day = scenario.simulation_day
            position.validate()

            created.append(order)
            open_keys.add(key)

        world.validate()
        return created

    def apply(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> dict[str, Any]:
        receipts = self.receive_due_orders(world, scenario)
        orders = self.create_orders(world, scenario)

        return {
            "receipts": receipts,
            "orders_created": orders,
        }
