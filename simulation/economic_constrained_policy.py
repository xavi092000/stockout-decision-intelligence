from __future__ import annotations

"""Cost-aware inventory policy constrained by a service objective.

The policy uses only information available at decision time: current inventory,
pending operations, product safety stock, and the demand forecast supplied by the
simulator. It never reads future realized demand or future scenario events.
"""

from dataclasses import dataclass

from simulation.action import ActionType, InventoryAction
from simulation.decision_policy import DecisionResult
from simulation.demand_engine import DemandForecast
from simulation.entities import Inventory, Product, Store, Supplier
from simulation.state import SimulationState


@dataclass(frozen=True)
class EconomicConstrainedConfig:
    target_days_of_cover: float = 21.0
    expedite_trigger_days: float = 7.0
    minimum_order_quantity: int = 1

    def __post_init__(self) -> None:
        if self.target_days_of_cover <= 0:
            raise ValueError("target_days_of_cover must be positive")
        if self.expedite_trigger_days < 0:
            raise ValueError("expedite_trigger_days cannot be negative")
        if self.expedite_trigger_days > self.target_days_of_cover:
            raise ValueError("expedite_trigger_days cannot exceed target_days_of_cover")
        if self.minimum_order_quantity <= 0:
            raise ValueError("minimum_order_quantity must be positive")


class EconomicConstrainedPolicy:
    """Hybrid normal/expedited replenishment policy.

    Normal orders protect the target stock level at lower cost. Expedite is used
    only when current projected days of cover falls below a calibrated emergency
    threshold. Pending orders are included to avoid duplicate replenishment.
    """

    def __init__(self, config: EconomicConstrainedConfig | None = None) -> None:
        self.config = config or EconomicConstrainedConfig()

    def decide(
        self,
        state: SimulationState,
        inventory: Inventory,
        product: Product,
        store: Store,
        supplier: Supplier,
        forecast: DemandForecast,
        forecasts_by_key: dict[tuple[str, str], DemandForecast],
    ) -> DecisionResult:
        del supplier, forecasts_by_key

        pending = sum(
            operation.quantity
            for operation in state.pending_operations
            if (
                operation.is_pending
                and operation.destination_store_id == store.store_id
                and operation.sku_id == product.sku_id
            )
        )

        projected_available = inventory.available_stock + pending
        daily_demand = max(float(forecast.forecast_daily_demand), 1e-9)
        projected_days_cover = projected_available / daily_demand
        target_stock = (
            daily_demand * self.config.target_days_of_cover
            + product.safety_stock
        )
        gap = max(0.0, target_stock - projected_available)

        if gap <= 0:
            return DecisionResult(
                action=InventoryAction(
                    action_type=ActionType.DO_NOTHING,
                    destination_store_id=store.store_id,
                    sku_id=product.sku_id,
                    quantity=0,
                ),
                reason="Target inventory cover is already protected.",
                forecast_daily_demand=forecast.forecast_daily_demand,
                forecast_next_3d=forecast.forecast_next_3d,
                projected_stock_gap=0.0,
            )

        action_type = (
            ActionType.ORDER_EXPEDITE
            if projected_days_cover < self.config.expedite_trigger_days
            else ActionType.ORDER_NORMAL
        )
        quantity = max(self.config.minimum_order_quantity, round(gap))

        return DecisionResult(
            action=InventoryAction(
                action_type=action_type,
                destination_store_id=store.store_id,
                sku_id=product.sku_id,
                quantity=quantity,
            ),
            reason=(
                "Economic constrained replenishment: "
                f"{projected_days_cover:.1f} projected days of cover; "
                f"target {self.config.target_days_of_cover:.1f}; "
                f"emergency threshold {self.config.expedite_trigger_days:.1f}."
            ),
            forecast_daily_demand=forecast.forecast_daily_demand,
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(gap, 2),
        )
