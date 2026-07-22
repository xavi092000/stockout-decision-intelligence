from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from simulation.entities import Inventory
from simulation.pending_operation import PendingOperation


@dataclass
class SimulationState:
    current_day: int
    current_date: date
    temperature_c: float
    weather_condition: str
    is_holiday: bool = False
    active_promotions: set[tuple[str, str]] = field(default_factory=set)
    active_events: list[dict[str, Any]] = field(default_factory=list)
    pending_operations: list[PendingOperation] = field(default_factory=list)
    inventories: list[Inventory] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.current_day < 1:
            raise ValueError(
                "current_day must be greater than or equal to 1."
            )

        if not self.weather_condition.strip():
            raise ValueError("weather_condition cannot be empty.")

        if self.temperature_c < -60 or self.temperature_c > 60:
            raise ValueError(
                "temperature_c must remain between -60 and 60."
            )

        self._validate_inventory_keys()
        self._validate_pending_operation_ids()

    def _validate_inventory_keys(self) -> None:
        inventory_keys = {
            (inventory.store_id, inventory.sku_id)
            for inventory in self.inventories
        }

        if len(inventory_keys) != len(self.inventories):
            raise ValueError(
                "Duplicate store-SKU inventory combinations detected."
            )

    def _validate_pending_operation_ids(self) -> None:
        operation_ids = {
            operation.operation_id
            for operation in self.pending_operations
        }

        if len(operation_ids) != len(self.pending_operations):
            raise ValueError(
                "Duplicate pending operation IDs detected."
            )

    def get_inventory(
        self,
        store_id: str,
        sku_id: str,
    ) -> Inventory:
        for inventory in self.inventories:
            if (
                inventory.store_id == store_id
                and inventory.sku_id == sku_id
            ):
                return inventory

        raise KeyError(
            f"Inventory not found for store_id={store_id}, "
            f"sku_id={sku_id}."
        )

    def is_promotion_active(
        self,
        store_id: str,
        sku_id: str,
    ) -> bool:
        return (store_id, sku_id) in self.active_promotions

    def add_promotion(
        self,
        store_id: str,
        sku_id: str,
    ) -> None:
        self.active_promotions.add((store_id, sku_id))

    def remove_promotion(
        self,
        store_id: str,
        sku_id: str,
    ) -> None:
        self.active_promotions.discard((store_id, sku_id))

    def add_event(self, event: dict[str, Any]) -> None:
        self.active_events.append(event)

    def add_pending_operation(
        self,
        operation: PendingOperation,
    ) -> None:
        existing_ids = {
            item.operation_id
            for item in self.pending_operations
        }

        if operation.operation_id in existing_ids:
            raise ValueError(
                f"Duplicate pending operation id: "
                f"{operation.operation_id}."
            )

        self.pending_operations.append(operation)

    def due_operations(self) -> list[PendingOperation]:
        return [
            operation
            for operation in self.pending_operations
            if operation.is_due(self.current_day)
        ]

    @property
    def pending_operation_count(self) -> int:
        return sum(
            1
            for operation in self.pending_operations
            if operation.is_pending
        )

    @property
    def total_stock(self) -> int:
        return sum(
            inventory.stock_level
            for inventory in self.inventories
        )

    @property
    def total_available_stock(self) -> int:
        return sum(
            inventory.available_stock
            for inventory in self.inventories
        )

    @property
    def stockout_count(self) -> int:
        return sum(
            1
            for inventory in self.inventories
            if inventory.available_stock == 0
        )

    def summary(self) -> str:
        return (
            f"Simulation Day     : {self.current_day}\n"
            f"Simulation Date    : {self.current_date.isoformat()}\n"
            f"Weather            : {self.weather_condition}\n"
            f"Temperature        : {self.temperature_c:.1f} C\n"
            f"Holiday            : {self.is_holiday}\n"
            f"Promotions         : {len(self.active_promotions)}\n"
            f"Active Events      : {len(self.active_events)}\n"
            f"Pending Operations : {self.pending_operation_count}\n"
            f"Inventory Records  : {len(self.inventories)}\n"
            f"Total Stock        : {self.total_stock}\n"
            f"Available Stock    : {self.total_available_stock}\n"
            f"Stockouts          : {self.stockout_count}"
        )