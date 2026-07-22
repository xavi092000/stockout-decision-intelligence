from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from simulation.domain.models import WorldState


@dataclass(frozen=True)
class DailyScenario:
    simulation_day: int
    synthetic_date: str
    expected_demand_units: float
    final_demand_multiplier: float
    final_supply_multiplier: float
    logistics_cost_multiplier: float
    category: str
    department: str
    store: str
    state: str
    economic_regime: str

    def __post_init__(self) -> None:
        if self.simulation_day <= 0:
            raise ValueError("simulation_day must be positive.")
        if self.expected_demand_units < 0:
            raise ValueError("expected_demand_units must be non-negative.")
        for name, value in (
            ("final_demand_multiplier", self.final_demand_multiplier),
            ("final_supply_multiplier", self.final_supply_multiplier),
            ("logistics_cost_multiplier", self.logistics_cost_multiplier),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero.")

    @classmethod
    def from_mapping(
        cls,
        row: dict[str, Any],
    ) -> "DailyScenario":
        return cls(
            simulation_day=int(row["simulation_day"]),
            synthetic_date=str(row["synthetic_date"]),
            expected_demand_units=float(
                row.get("expected_demand_units", 0.0)
            ),
            final_demand_multiplier=float(
                row.get("final_demand_multiplier", 1.0)
            ),
            final_supply_multiplier=float(
                row.get("final_supply_multiplier", 1.0)
            ),
            logistics_cost_multiplier=float(
                row.get("logistics_cost_multiplier", 1.0)
            ),
            category=str(row.get("category", "")),
            department=str(row.get("department", "")),
            store=str(row.get("store", "")),
            state=str(row.get("state", "")),
            economic_regime=str(
                row.get("economic_regime", "stable")
            ),
        )


class DailyEngine(Protocol):
    def apply(
        self,
        world: WorldState,
        scenario: DailyScenario,
    ) -> dict[str, Any]:
        ...
