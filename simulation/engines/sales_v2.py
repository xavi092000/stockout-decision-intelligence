from __future__ import annotations

from dataclasses import asdict, dataclass
from random import Random
from typing import Any
import math

from simulation.application.contracts import DailyScenario
from simulation.domain.models import WorldState


class SalesEngineV2Error(RuntimeError):
    """Raised when sales generation violates domain invariants."""


@dataclass(frozen=True)
class SalesEvent:
    sales_event_id: str
    simulation_day: int
    date: str
    store_id: str
    sku_id: str
    requested_units: int
    sold_units: int
    lost_units: int
    unit_price: float
    unit_cost: float
    realized_revenue: float
    lost_revenue: float
    cost_of_goods_sold: float
    gross_margin: float
    stock_before: int
    stock_after: int
    stockout_occurred: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StockoutEvent:
    stockout_event_id: str
    simulation_day: int
    date: str
    store_id: str
    sku_id: str
    requested_units: int
    available_units: int
    lost_units: int
    lost_revenue: float
    penalty_cost: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SalesEngineV2:
    def __init__(
        self,
        seed: int = 42,
        demand_scale: float = 18.0,
    ) -> None:
        if demand_scale <= 0:
            raise ValueError("demand_scale must be greater than zero.")
        self.random = Random(seed)
        self.demand_scale = float(demand_scale)

    def _allocate_demand(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> list[int]:
        target_units = max(
            1,
            int(
                round(
                    # expected_demand_units is already the calibrated
                    # baseline multiplied by final_demand_multiplier in
                    # the scenario generator. Applying that multiplier
                    # again would square every demand shock.
                    scenario.expected_demand_units
                    * self.demand_scale
                )
            ),
        )

        product_index = {
            item.sku_id: item for item in world.products
        }

        weights: list[float] = []
        for position in world.inventory:
            product = product_index[position.sku_id]
            weight = self.random.lognormvariate(0.0, 0.80)

            if product.category == scenario.category:
                weight *= 2.2
            if product.department == scenario.department:
                weight *= 1.6
            if position.store_id == scenario.store:
                weight *= 2.5

            weights.append(weight)

        total_weight = sum(weights)
        if total_weight <= 0:
            raise SalesEngineV2Error(
                "Demand allocation produced zero total weight."
            )

        raw_allocations = [
            target_units * weight / total_weight
            for weight in weights
        ]
        allocations = [
            int(math.floor(value))
            for value in raw_allocations
        ]

        remainder = target_units - sum(allocations)
        ranked = sorted(
            range(len(raw_allocations)),
            key=lambda idx: (
                raw_allocations[idx] - allocations[idx]
            ),
            reverse=True,
        )

        for idx in ranked[:remainder]:
            allocations[idx] += 1

        return allocations

    def apply(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> dict[str, Any]:
        world.validate()

        product_index = {
            item.sku_id: item for item in world.products
        }
        allocations = self._allocate_demand(world, scenario)

        sales_events: list[SalesEvent] = []
        stockout_events: list[StockoutEvent] = []

        requested_total = 0
        sold_total = 0
        lost_total = 0
        realized_revenue = 0.0
        lost_revenue = 0.0
        cost_of_goods_sold = 0.0
        gross_margin = 0.0

        event_counter = 0
        stockout_counter = 0

        for position, requested in zip(world.inventory, allocations):
            if requested <= 0:
                continue

            product = product_index[position.sku_id]
            before = position.on_hand
            available = position.available
            sold = min(requested, available)
            lost = requested - sold

            position.on_hand -= sold
            position.last_updated_day = scenario.simulation_day
            position.validate()

            revenue = round(sold * product.unit_price, 2)
            lost_rev = round(lost * product.unit_price, 2)
            cogs = round(sold * product.unit_cost, 2)
            margin = round(revenue - cogs, 2)

            event_counter += 1
            sales_events.append(
                SalesEvent(
                    sales_event_id=(
                        f"SALE-{scenario.simulation_day:04d}-"
                        f"{event_counter:06d}"
                    ),
                    simulation_day=scenario.simulation_day,
                    date=scenario.synthetic_date,
                    store_id=position.store_id,
                    sku_id=position.sku_id,
                    requested_units=requested,
                    sold_units=sold,
                    lost_units=lost,
                    unit_price=product.unit_price,
                    unit_cost=product.unit_cost,
                    realized_revenue=revenue,
                    lost_revenue=lost_rev,
                    cost_of_goods_sold=cogs,
                    gross_margin=margin,
                    stock_before=before,
                    stock_after=position.on_hand,
                    stockout_occurred=lost > 0,
                )
            )

            if lost > 0:
                stockout_counter += 1
                stockout_events.append(
                    StockoutEvent(
                        stockout_event_id=(
                            f"STO-{scenario.simulation_day:04d}-"
                            f"{stockout_counter:06d}"
                        ),
                        simulation_day=scenario.simulation_day,
                        date=scenario.synthetic_date,
                        store_id=position.store_id,
                        sku_id=position.sku_id,
                        requested_units=requested,
                        available_units=available,
                        lost_units=lost,
                        lost_revenue=lost_rev,
                        penalty_cost=round(
                            lost
                            * product.stockout_penalty_per_unit,
                            2,
                        ),
                    )
                )

            requested_total += requested
            sold_total += sold
            lost_total += lost
            realized_revenue += revenue
            lost_revenue += lost_rev
            cost_of_goods_sold += cogs
            gross_margin += margin

        world.validate()

        fill_rate = (
            sold_total / requested_total
            if requested_total > 0
            else 1.0
        )

        return {
            "requested_units": requested_total,
            "sold_units": sold_total,
            "lost_units": lost_total,
            "fill_rate": round(fill_rate, 6),
            "realized_revenue": round(realized_revenue, 2),
            "lost_revenue": round(lost_revenue, 2),
            "cost_of_goods_sold": round(
                cost_of_goods_sold,
                2,
            ),
            "gross_margin": round(gross_margin, 2),
            "sales_events": sales_events,
            "stockout_events": stockout_events,
        }
