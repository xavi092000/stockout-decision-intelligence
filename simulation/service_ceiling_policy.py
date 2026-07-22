from __future__ import annotations

"""Aggressive service-first policy used to probe the simulator's attainable service ceiling.

This is deliberately not a production policy and not a true clairvoyant oracle: it uses only
information available at decision time. Its purpose is to test whether a high service level is
reachable when cost control is deprioritized.
"""

from dataclasses import dataclass

from simulation.action import ActionType, InventoryAction
from simulation.decision_policy import DecisionResult
from simulation.demand_engine import DemandForecast
from simulation.entities import Inventory, Product, Store, Supplier
from simulation.state import SimulationState


@dataclass(frozen=True)
class ServiceCeilingConfig:
    target_days_of_cover: float = 45.0
    minimum_order_quantity: int = 1
    always_expedite: bool = True

    def __post_init__(self) -> None:
        if self.target_days_of_cover <= 0:
            raise ValueError("target_days_of_cover must be positive")
        if self.minimum_order_quantity <= 0:
            raise ValueError("minimum_order_quantity must be positive")


class ServiceCeilingPolicy:
    """Cost-insensitive policy that aggressively protects service level."""

    def __init__(self, config: ServiceCeilingConfig | None = None) -> None:
        self.config = config or ServiceCeilingConfig()

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
        del forecasts_by_key

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
        target_stock = (
            forecast.forecast_daily_demand * self.config.target_days_of_cover
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
                reason="Aggressive service target is already covered.",
                forecast_daily_demand=forecast.forecast_daily_demand,
                forecast_next_3d=forecast.forecast_next_3d,
                projected_stock_gap=0.0,
            )

        quantity = max(self.config.minimum_order_quantity, round(gap))
        action_type = (
            ActionType.ORDER_EXPEDITE
            if self.config.always_expedite
            else ActionType.ORDER_NORMAL
        )

        return DecisionResult(
            action=InventoryAction(
                action_type=action_type,
                destination_store_id=store.store_id,
                sku_id=product.sku_id,
                quantity=quantity,
            ),
            reason=(
                "Service-ceiling probe: aggressively replenishes toward "
                f"{self.config.target_days_of_cover:.0f} days of cover."
            ),
            forecast_daily_demand=forecast.forecast_daily_demand,
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(gap, 2),
        )
