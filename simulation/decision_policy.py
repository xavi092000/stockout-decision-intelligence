from __future__ import annotations

from dataclasses import dataclass

from simulation.action import ActionType, InventoryAction
from simulation.demand_engine import DemandForecast
from simulation.entities import Inventory, Product, Store, Supplier
from simulation.state import SimulationState


@dataclass(frozen=True)
class DecisionResult:
    action: InventoryAction
    reason: str
    forecast_daily_demand: float
    forecast_next_3d: float
    projected_stock_gap: float


class RuleBasedDecisionPolicy:
    """
    Deterministic business-policy baseline.

    Leakage safeguards:
    - uses only current inventory;
    - uses only forecasts available at decision time;
    - uses supplier lead time;
    - uses pending inbound quantities;
    - uses current neighboring inventory;
    - never uses realized future demand, future cost, reward,
      regret, or future best action.

    Transfer safeguard:
    A donor store may transfer only stock that remains after
    protecting its own forecast demand and safety stock.
    """

    def decide(
        self,
        state: SimulationState,
        inventory: Inventory,
        product: Product,
        store: Store,
        supplier: Supplier,
        forecast: DemandForecast,
        forecasts_by_key: dict[
            tuple[str, str],
            DemandForecast,
        ],
    ) -> DecisionResult:
        pending_inbound = self._pending_inbound_quantity(
            state=state,
            store_id=store.store_id,
            sku_id=product.sku_id,
        )

        projected_available_stock = (
            inventory.available_stock
            + pending_inbound
        )

        lead_time_demand = (
            forecast.forecast_daily_demand
            * supplier.lead_time_days
        )

        required_stock = max(
            forecast.forecast_next_3d,
            lead_time_demand,
        ) + product.safety_stock

        projected_stock_gap = max(
            0.0,
            required_stock - projected_available_stock,
        )

        if projected_stock_gap <= 0:
            return self._do_nothing(
                inventory=inventory,
                forecast=forecast,
                projected_stock_gap=projected_stock_gap,
                reason=(
                    "Current and incoming inventory cover expected "
                    "demand and safety stock."
                ),
            )

        transfer_action = self._find_transfer_action(
            state=state,
            destination_inventory=inventory,
            product=product,
            required_quantity=round(projected_stock_gap),
            forecasts_by_key=forecasts_by_key,
        )

        if transfer_action is not None:
            return DecisionResult(
                action=transfer_action,
                reason=(
                    "A neighboring store has transferable stock "
                    "after protecting its own forecast demand and "
                    "safety stock."
                ),
                forecast_daily_demand=(
                    forecast.forecast_daily_demand
                ),
                forecast_next_3d=forecast.forecast_next_3d,
                projected_stock_gap=round(
                    projected_stock_gap,
                    2,
                ),
            )

        days_of_cover = self._days_of_cover(
            available_stock=projected_available_stock,
            forecast_daily_demand=(
                forecast.forecast_daily_demand
            ),
        )

        quantity = max(
            1,
            round(projected_stock_gap),
        )

        if days_of_cover < supplier.lead_time_days:
            return DecisionResult(
                action=InventoryAction(
                    action_type=ActionType.ORDER_EXPEDITE,
                    destination_store_id=store.store_id,
                    sku_id=product.sku_id,
                    quantity=quantity,
                ),
                reason=(
                    "Projected inventory will be exhausted before a "
                    "normal supplier order could arrive."
                ),
                forecast_daily_demand=(
                    forecast.forecast_daily_demand
                ),
                forecast_next_3d=forecast.forecast_next_3d,
                projected_stock_gap=round(
                    projected_stock_gap,
                    2,
                ),
            )

        return DecisionResult(
            action=InventoryAction(
                action_type=ActionType.ORDER_NORMAL,
                destination_store_id=store.store_id,
                sku_id=product.sku_id,
                quantity=quantity,
            ),
            reason=(
                "Projected inventory is below the required level, "
                "but a normal order can arrive before exhaustion."
            ),
            forecast_daily_demand=(
                forecast.forecast_daily_demand
            ),
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(
                projected_stock_gap,
                2,
            ),
        )

    @staticmethod
    def _pending_inbound_quantity(
        state: SimulationState,
        store_id: str,
        sku_id: str,
    ) -> int:
        cached = getattr(
            state,
            "_pending_inbound_by_key",
            None,
        )

        if cached is not None:
            return cached.get(
                (store_id, sku_id),
                0,
            )

        return sum(
            operation.quantity
            for operation in state.pending_operations
            if (
                operation.is_pending
                and operation.destination_store_id == store_id
                and operation.sku_id == sku_id
            )
        )

    @staticmethod
    def _days_of_cover(
        available_stock: float,
        forecast_daily_demand: float,
    ) -> float:
        if forecast_daily_demand <= 0:
            return float("inf")

        return available_stock / forecast_daily_demand

    def _find_transfer_action(
        self,
        state: SimulationState,
        destination_inventory: Inventory,
        product: Product,
        required_quantity: int,
        forecasts_by_key: dict[
            tuple[str, str],
            DemandForecast,
        ],
    ) -> InventoryAction | None:
        if required_quantity <= 0:
            return None

        candidates: list[
            tuple[int, Inventory]
        ] = []

        for candidate in state.inventories:
            if candidate.sku_id != destination_inventory.sku_id:
                continue

            if candidate.store_id == destination_inventory.store_id:
                continue

            candidate_forecast = forecasts_by_key.get(
                (
                    candidate.store_id,
                    candidate.sku_id,
                )
            )

            if candidate_forecast is None:
                continue

            candidate_pending_inbound = (
                self._pending_inbound_quantity(
                    state=state,
                    store_id=candidate.store_id,
                    sku_id=candidate.sku_id,
                )
            )

            donor_required_stock = (
                candidate_forecast.forecast_next_3d
                + product.safety_stock
            )

            donor_projected_available = (
                candidate.available_stock
                + candidate_pending_inbound
            )

            transferable_surplus = max(
                0,
                round(
                    donor_projected_available
                    - donor_required_stock
                ),
            )

            if transferable_surplus <= 0:
                continue

            candidates.append(
                (
                    transferable_surplus,
                    candidate,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        largest_surplus, source_inventory = candidates[0]

        transfer_quantity = min(
            required_quantity,
            largest_surplus,
        )

        if transfer_quantity <= 0:
            return None

        return InventoryAction(
            action_type=ActionType.TRANSFER_STOCK,
            source_store_id=source_inventory.store_id,
            destination_store_id=(
                destination_inventory.store_id
            ),
            sku_id=destination_inventory.sku_id,
            quantity=transfer_quantity,
        )

    @staticmethod
    def _do_nothing(
        inventory: Inventory,
        forecast: DemandForecast,
        projected_stock_gap: float,
        reason: str,
    ) -> DecisionResult:
        return DecisionResult(
            action=InventoryAction(
                action_type=ActionType.DO_NOTHING,
                destination_store_id=inventory.store_id,
                sku_id=inventory.sku_id,
                quantity=0,
            ),
            reason=reason,
            forecast_daily_demand=(
                forecast.forecast_daily_demand
            ),
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(
                projected_stock_gap,
                2,
            ),
        )
