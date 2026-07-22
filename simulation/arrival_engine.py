from __future__ import annotations

from dataclasses import dataclass

from simulation.pending_operation import (
    PendingOperationStatus,
    PendingOperationType,
)
from simulation.state import SimulationState


@dataclass(frozen=True)
class ArrivalSummary:
    operations_completed: int
    units_received: int

    def summary(self) -> str:
        return (
            f"Operations Completed : {self.operations_completed}\n"
            f"Units Received       : {self.units_received}"
        )


class ArrivalEngine:
    """
    Executes every pending operation whose arrival day
    is equal to the current simulation day.
    """

    def process(
        self,
        state: SimulationState,
    ) -> ArrivalSummary:

        completed = 0
        units = 0

        for operation in state.due_operations():

            inventory = state.get_inventory(
                operation.destination_store_id,
                operation.sku_id,
            )

            inventory.stock_level += operation.quantity

            operation.mark_completed()

            completed += 1
            units += operation.quantity

        return ArrivalSummary(
            operations_completed=completed,
            units_received=units,
        )