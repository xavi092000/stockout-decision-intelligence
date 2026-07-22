from __future__ import annotations

from dataclasses import asdict, dataclass
from random import Random
from typing import Any
import math

from simulation.application.contracts import DailyScenario
from simulation.domain.models import InventoryPosition, WorldState


class InventoryEngineV2Error(RuntimeError):
    """Raised when an inventory transition violates domain invariants."""


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InventoryEngineV2:
    def __init__(
        self,
        seed: int = 42,
        demand_scale: float = 18.0,
    ) -> None:
        if demand_scale <= 0:
            raise ValueError("demand_scale must be greater than zero.")
        self.random = Random(seed)
        self.demand_scale = float(demand_scale)

    def apply(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> dict[str, Any]:
        world.validate()

        target_units = max(
            1,
            int(
                round(
                    # expected_demand_units already includes the final
                    # calibrated demand multiplier.
                    scenario.expected_demand_units
                    * self.demand_scale
                )
            ),
        )

        weights: list[float] = []
        for position in world.inventory:
            product = next(
                item for item in world.products
                if item.sku_id == position.sku_id
            )
            weight = self.random.lognormvariate(0.0, 0.75)

            if product.category == scenario.category:
                weight *= 2.2
            if product.department == scenario.department:
                weight *= 1.6
            if position.store_id == scenario.store:
                weight *= 2.5

            weights.append(weight)

        total_weight = sum(weights)
        if total_weight <= 0:
            raise InventoryEngineV2Error(
                "Demand allocation produced zero total weight."
            )

        raw = [
            target_units * weight / total_weight
            for weight in weights
        ]
        allocated = [int(math.floor(value)) for value in raw]
        remainder = target_units - sum(allocated)

        ranked = sorted(
            range(len(raw)),
            key=lambda idx: raw[idx] - allocated[idx],
            reverse=True,
        )
        for idx in ranked[:remainder]:
            allocated[idx] += 1

        movements: list[InventoryMovement] = []
        fulfilled = 0
        unmet = 0

        counter = 0
        for position, requested in zip(world.inventory, allocated):
            if requested <= 0:
                continue

            counter += 1
            before = position.on_hand
            applied = min(requested, position.available)
            missing = requested - applied

            position.on_hand -= applied
            position.last_updated_day = scenario.simulation_day
            position.validate()

            movements.append(
                InventoryMovement(
                    movement_id=(
                        f"MOV-{scenario.simulation_day:04d}-"
                        f"{counter:06d}"
                    ),
                    simulation_day=scenario.simulation_day,
                    date=scenario.synthetic_date,
                    store_id=position.store_id,
                    sku_id=position.sku_id,
                    movement_type="SALE_CONSUMPTION",
                    requested_units=requested,
                    applied_units=applied,
                    unmet_units=missing,
                    stock_before=before,
                    stock_after=position.on_hand,
                )
            )
            fulfilled += applied
            unmet += missing

        world.validate()

        return {
            "requested_units": target_units,
            "fulfilled_units": fulfilled,
            "unmet_units": unmet,
            "movements": movements,
        }
