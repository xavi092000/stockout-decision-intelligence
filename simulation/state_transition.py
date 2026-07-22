from __future__ import annotations

from dataclasses import dataclass

from simulation.action import ActionType, InventoryAction
from simulation.demand_engine import RealizedDemand
from simulation.state import SimulationState


@dataclass(frozen=True)
class InventoryTransition:
    store_id: str
    sku_id: str
    opening_stock: int
    transfer_in: int
    transfer_out: int
    actual_demand: int
    fulfilled_demand: int
    unmet_demand: int
    ending_stock: int
    stockout_occurred: bool

    def __post_init__(self) -> None:
        numeric_values = (
            self.opening_stock,
            self.transfer_in,
            self.transfer_out,
            self.actual_demand,
            self.fulfilled_demand,
            self.unmet_demand,
            self.ending_stock,
        )

        if any(value < 0 for value in numeric_values):
            raise ValueError(
                "Inventory transition quantities cannot be negative."
            )


@dataclass(frozen=True)
class DailyTransitionOutcome:
    transitions: tuple[InventoryTransition, ...]

    @property
    def total_demand(self) -> int:
        return sum(
            transition.actual_demand
            for transition in self.transitions
        )

    @property
    def fulfilled_demand(self) -> int:
        return sum(
            transition.fulfilled_demand
            for transition in self.transitions
        )

    @property
    def unmet_demand(self) -> int:
        return sum(
            transition.unmet_demand
            for transition in self.transitions
        )

    @property
    def stockout_count(self) -> int:
        return sum(
            1
            for transition in self.transitions
            if transition.stockout_occurred
        )

    @property
    def service_level(self) -> float:
        if self.total_demand == 0:
            return 1.0

        return self.fulfilled_demand / self.total_demand

    def summary(self) -> str:
        return (
            f"Transitions       : {len(self.transitions)}\n"
            f"Total Demand     : {self.total_demand}\n"
            f"Demand Fulfilled : {self.fulfilled_demand}\n"
            f"Unmet Demand     : {self.unmet_demand}\n"
            f"Stockouts        : {self.stockout_count}\n"
            f"Service Level    : {self.service_level:.2%}"
        )


class StateTransitionEngine:
    """
    Apply a decision and realized demand to the persistent world state.

    Important:
    - The action is selected before realized demand is known.
    - Realized demand is used only after the decision.
    - Inventory objects are updated in place so consequences persist.
    """

    def transition(
        self,
        current_state: SimulationState,
        actions: list[InventoryAction],
        realized_demands: list[RealizedDemand],
    ) -> DailyTransitionOutcome:
        transfer_in: dict[tuple[str, str], int] = {}
        transfer_out: dict[tuple[str, str], int] = {}

        self._apply_actions(
            current_state=current_state,
            actions=actions,
            transfer_in=transfer_in,
            transfer_out=transfer_out,
        )

        demand_by_key = {
            (demand.store_id, demand.sku_id): demand
            for demand in realized_demands
        }

        transitions: list[InventoryTransition] = []

        for inventory in current_state.inventories:
            key = (inventory.store_id, inventory.sku_id)

            demand_record = demand_by_key.get(key)

            actual_demand = (
                demand_record.actual_demand
                if demand_record is not None
                else 0
            )

            opening_stock = (
                inventory.stock_level
                + transfer_out.get(key, 0)
                - transfer_in.get(key, 0)
            )

            available_stock = inventory.available_stock

            fulfilled_demand = min(
                actual_demand,
                available_stock,
            )

            unmet_demand = max(
                0,
                actual_demand - available_stock,
            )

            inventory.stock_level -= fulfilled_demand

            transitions.append(
                InventoryTransition(
                    store_id=inventory.store_id,
                    sku_id=inventory.sku_id,
                    opening_stock=opening_stock,
                    transfer_in=transfer_in.get(key, 0),
                    transfer_out=transfer_out.get(key, 0),
                    actual_demand=actual_demand,
                    fulfilled_demand=fulfilled_demand,
                    unmet_demand=unmet_demand,
                    ending_stock=inventory.stock_level,
                    stockout_occurred=unmet_demand > 0,
                )
            )

        return DailyTransitionOutcome(
            transitions=tuple(transitions)
        )

    def _apply_actions(
        self,
        current_state: SimulationState,
        actions: list[InventoryAction],
        transfer_in: dict[tuple[str, str], int],
        transfer_out: dict[tuple[str, str], int],
    ) -> None:
        for action in actions:
            if action.action_type == ActionType.DO_NOTHING:
                continue

            if action.action_type == ActionType.TRANSFER_STOCK:
                self._apply_transfer(
                    current_state=current_state,
                    action=action,
                    transfer_in=transfer_in,
                    transfer_out=transfer_out,
                )
                continue

            if action.action_type in {
                ActionType.ORDER_NORMAL,
                ActionType.ORDER_EXPEDITE,
            }:
                raise NotImplementedError(
                    "Supplier orders will be connected to the "
                    "pending-order engine in a later step."
                )

    @staticmethod
    def _apply_transfer(
        current_state: SimulationState,
        action: InventoryAction,
        transfer_in: dict[tuple[str, str], int],
        transfer_out: dict[tuple[str, str], int],
    ) -> None:
        if action.source_store_id is None:
            raise ValueError(
                "Transfer action requires a source store."
            )

        source_inventory = current_state.get_inventory(
            store_id=action.source_store_id,
            sku_id=action.sku_id,
        )

        destination_inventory = current_state.get_inventory(
            store_id=action.destination_store_id,
            sku_id=action.sku_id,
        )

        if source_inventory.available_stock < action.quantity:
            raise ValueError(
                "Transfer quantity exceeds available source stock."
            )

        source_inventory.stock_level -= action.quantity
        destination_inventory.stock_level += action.quantity

        source_key = (
            action.source_store_id,
            action.sku_id,
        )
        destination_key = (
            action.destination_store_id,
            action.sku_id,
        )

        transfer_out[source_key] = (
            transfer_out.get(source_key, 0)
            + action.quantity
        )

        transfer_in[destination_key] = (
            transfer_in.get(destination_key, 0)
            + action.quantity
        )