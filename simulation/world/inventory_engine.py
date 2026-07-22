from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import math
import random


class InventoryEngineError(RuntimeError):
    """Raised when an inventory transition violates a world invariant."""


@dataclass(frozen=True)
class InventoryMovement:
    movement_id: str
    simulation_day: int
    date: str
    store_id: str
    sku_id: str
    movement_type: str
    requested_units: int
    applied_units: int
    unmet_units: int
    stock_before: int
    stock_after: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DailyInventoryEngine:
    """
    Applies deterministic daily inventory transitions.

    Sprint 7B deliberately does not create supplier purchase orders.
    Replenishment is added in Sprint 7C.
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.random = random.Random(seed)

    @staticmethod
    def _key(store_id: str, sku_id: str) -> str:
        return f"{store_id}::{sku_id}"

    @staticmethod
    def build_index(
        inventory: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for row in inventory:
            key = DailyInventoryEngine._key(
                str(row["store_id"]),
                str(row["sku_id"]),
            )
            if key in index:
                raise InventoryEngineError(
                    f"Duplicate inventory position: {key}"
                )
            index[key] = row
        return index

    @staticmethod
    def _normalize_position(row: dict[str, Any]) -> None:
        for field in (
            "on_hand",
            "reserved",
            "in_transit",
            "reorder_point",
            "target_stock",
            "safety_stock",
        ):
            row[field] = max(0, int(round(float(row.get(field, 0)))))

        if row["reserved"] > row["on_hand"]:
            row["reserved"] = row["on_hand"]

        row["available"] = max(0, row["on_hand"] - row["reserved"])
        row["inventory_position"] = (
            row["available"] + row["in_transit"]
        )

    def consume(
        self,
        position: dict[str, Any],
        requested_units: int,
        simulation_day: int,
        current_date: str,
        movement_id: str,
        reason: str = "synthetic_customer_demand",
    ) -> InventoryMovement:
        self._normalize_position(position)

        requested = max(0, int(requested_units))
        before = int(position["on_hand"])
        available = int(position["available"])
        applied = min(requested, available)
        unmet = requested - applied

        position["on_hand"] = before - applied
        position["last_updated_day"] = simulation_day
        self._normalize_position(position)

        if position["on_hand"] < 0:
            raise InventoryEngineError(
                "Negative stock produced after consumption."
            )

        return InventoryMovement(
            movement_id=movement_id,
            simulation_day=simulation_day,
            date=current_date,
            store_id=str(position["store_id"]),
            sku_id=str(position["sku_id"]),
            movement_type="SALE_CONSUMPTION",
            requested_units=requested,
            applied_units=applied,
            unmet_units=unmet,
            stock_before=before,
            stock_after=int(position["on_hand"]),
            reason=reason,
        )

    def receive(
        self,
        position: dict[str, Any],
        received_units: int,
        simulation_day: int,
        current_date: str,
        movement_id: str,
        reason: str = "inventory_receipt",
    ) -> InventoryMovement:
        self._normalize_position(position)

        requested = max(0, int(received_units))
        before = int(position["on_hand"])
        applied = requested

        position["on_hand"] = before + applied
        position["in_transit"] = max(
            0,
            int(position["in_transit"]) - applied,
        )
        position["last_updated_day"] = simulation_day
        self._normalize_position(position)

        return InventoryMovement(
            movement_id=movement_id,
            simulation_day=simulation_day,
            date=current_date,
            store_id=str(position["store_id"]),
            sku_id=str(position["sku_id"]),
            movement_type="RECEIPT",
            requested_units=requested,
            applied_units=applied,
            unmet_units=0,
            stock_before=before,
            stock_after=int(position["on_hand"]),
            reason=reason,
        )

    def expire(
        self,
        position: dict[str, Any],
        requested_units: int,
        simulation_day: int,
        current_date: str,
        movement_id: str,
    ) -> InventoryMovement:
        self._normalize_position(position)

        requested = max(0, int(requested_units))
        before = int(position["on_hand"])
        applied = min(requested, before)

        position["on_hand"] = before - applied
        position["last_updated_day"] = simulation_day
        self._normalize_position(position)

        return InventoryMovement(
            movement_id=movement_id,
            simulation_day=simulation_day,
            date=current_date,
            store_id=str(position["store_id"]),
            sku_id=str(position["sku_id"]),
            movement_type="EXPIRATION",
            requested_units=requested,
            applied_units=applied,
            unmet_units=requested - applied,
            stock_before=before,
            stock_after=int(position["on_hand"]),
            reason="synthetic_shelf_life_expiration",
        )

    def allocate_daily_demand(
        self,
        world: dict[str, Any],
        scenario: dict[str, Any],
        simulation_day: int,
        current_date: str,
    ) -> list[InventoryMovement]:
        inventory = world["inventory"]
        products = {
            str(row["sku_id"]): row
            for row in world["products"]
        }

        expected_total = max(
            0.0,
            float(scenario.get("expected_demand_units", 0.0)),
        )
        demand_multiplier = max(
            0.01,
            float(scenario.get("final_demand_multiplier", 1.0)),
        )

        # Scale the scenario-level signal to the complete synthetic world.
        target_units = max(
            1,
            int(round(expected_total * demand_multiplier * 18.0)),
        )

        weights: list[float] = []
        for position in inventory:
            product = products[str(position["sku_id"])]
            category_match = (
                str(product.get("category"))
                == str(scenario.get("category"))
            )
            department_match = (
                str(product.get("department"))
                == str(scenario.get("department"))
            )

            weight = self.random.lognormvariate(0.0, 0.75)
            if category_match:
                weight *= 2.2
            if department_match:
                weight *= 1.6
            if str(position["store_id"]) == str(scenario.get("store")):
                weight *= 2.5
            weights.append(weight)

        total_weight = sum(weights)
        if total_weight <= 0:
            raise InventoryEngineError(
                "Daily demand allocation produced zero total weight."
            )

        raw_allocations = [
            target_units * weight / total_weight
            for weight in weights
        ]
        allocations = [int(math.floor(value)) for value in raw_allocations]
        remainder = target_units - sum(allocations)

        ranked_remainders = sorted(
            range(len(raw_allocations)),
            key=lambda idx: raw_allocations[idx] - allocations[idx],
            reverse=True,
        )
        for idx in ranked_remainders[:remainder]:
            allocations[idx] += 1

        movements: list[InventoryMovement] = []
        movement_counter = 0

        for position, requested in zip(inventory, allocations):
            if requested <= 0:
                continue

            movement_counter += 1
            movement_id = (
                f"MOV-{simulation_day:04d}-"
                f"{movement_counter:06d}"
            )
            movements.append(
                self.consume(
                    position=position,
                    requested_units=requested,
                    simulation_day=simulation_day,
                    current_date=current_date,
                    movement_id=movement_id,
                )
            )

            product = products[str(position["sku_id"])]
            shelf_life = product.get("shelf_life_days")
            if (
                shelf_life is not None
                and int(shelf_life) <= 14
                and int(position["on_hand"]) > 0
                and self.random.random() < 0.003
            ):
                movement_counter += 1
                expire_units = max(
                    1,
                    int(round(position["on_hand"] * 0.02)),
                )
                movements.append(
                    self.expire(
                        position=position,
                        requested_units=expire_units,
                        simulation_day=simulation_day,
                        current_date=current_date,
                        movement_id=(
                            f"MOV-{simulation_day:04d}-"
                            f"{movement_counter:06d}"
                        ),
                    )
                )

        return movements
