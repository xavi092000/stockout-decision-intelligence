from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from simulation.application.contracts import DailyScenario
from simulation.domain.models import WorldState


class AdaptivePolicyError(RuntimeError):
    """Raised when the adaptive policy cannot produce a valid decision."""


@dataclass(frozen=True)
class AdaptiveDecision:
    simulation_day: int
    date: str
    selected_policy: str
    reason: str
    stockout_rate: float
    below_reorder_share: float
    in_transit_share: float
    open_order_count: int
    scenario_supply_multiplier: float
    scenario_demand_multiplier: float
    economic_regime: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptivePolicyEngineV2:
    """
    Chooses a policy using current-state signals only.

    No future scenario rows, future deliveries or future demand are used.
    """

    VALID_POLICIES = {"lean", "balanced", "service_first"}

    def choose(
        self,
        world: WorldState,
        scenario: DailyScenario,
        trailing_metrics: list[dict[str, Any]],
    ) -> AdaptiveDecision:
        world.validate()

        position_count = max(1, len(world.inventory))
        zero_stock_count = sum(
            1 for item in world.inventory if item.on_hand == 0
        )
        below_reorder_count = sum(
            1
            for item in world.inventory
            if item.inventory_position <= item.reorder_point
        )
        total_inventory_position = sum(
            item.inventory_position for item in world.inventory
        )
        total_in_transit = sum(
            item.in_transit for item in world.inventory
        )
        open_order_count = sum(
            1
            for order in world.purchase_orders
            if order.status in {"OPEN", "PARTIALLY_RECEIVED"}
        )

        stockout_rate = zero_stock_count / position_count
        below_reorder_share = below_reorder_count / position_count
        in_transit_share = (
            total_in_transit / total_inventory_position
            if total_inventory_position > 0 else 0.0
        )

        recent_fill_rate = 1.0
        recent_lost_units = 0
        if trailing_metrics:
            window = trailing_metrics[-14:]
            requested = sum(
                int(row.get("requested_units", 0))
                for row in window
            )
            sold = sum(
                int(row.get("sold_units", 0))
                for row in window
            )
            recent_lost_units = sum(
                int(row.get("lost_units", 0))
                for row in window
            )
            recent_fill_rate = (
                sold / requested if requested > 0 else 1.0
            )

        supply_pressure = (
            scenario.final_supply_multiplier < 0.90
            or scenario.logistics_cost_multiplier > 1.10
        )
        demand_pressure = (
            scenario.final_demand_multiplier > 1.15
        )

        if (
            stockout_rate >= 0.01
            or below_reorder_share >= 0.18
            or recent_fill_rate < 0.995
            or recent_lost_units >= 3
            or (supply_pressure and demand_pressure)
        ):
            selected = "service_first"
            reason = (
                "Service protection triggered by current stock, "
                "recent fill rate or same-day supply/demand pressure."
            )
        elif (
            stockout_rate == 0
            and below_reorder_share <= 0.08
            and recent_fill_rate >= 0.999
            and not demand_pressure
            and in_transit_share <= 0.12
        ):
            selected = "lean"
            reason = (
                "Inventory and service are healthy, allowing lower "
                "working-capital exposure."
            )
        else:
            selected = "balanced"
            reason = (
                "Current operational signals favor the calibrated "
                "cost-service baseline."
            )

        if selected not in self.VALID_POLICIES:
            raise AdaptivePolicyError(
                f"Invalid selected policy: {selected}"
            )

        return AdaptiveDecision(
            simulation_day=scenario.simulation_day,
            date=scenario.synthetic_date,
            selected_policy=selected,
            reason=reason,
            stockout_rate=round(stockout_rate, 6),
            below_reorder_share=round(
                below_reorder_share,
                6,
            ),
            in_transit_share=round(in_transit_share, 6),
            open_order_count=open_order_count,
            scenario_supply_multiplier=round(
                scenario.final_supply_multiplier,
                6,
            ),
            scenario_demand_multiplier=round(
                scenario.final_demand_multiplier,
                6,
            ),
            economic_regime=scenario.economic_regime,
        )
