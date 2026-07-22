from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Promotion:
    promotion_type: str
    discount_rate: float
    demand_multiplier: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioEvent:
    event_type: str
    severity: float
    demand_multiplier: float
    supply_multiplier: float
    logistics_cost_multiplier: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DayScenario:
    scenario_id: str
    simulation_day: int
    synthetic_date: str
    weekday: str
    month: int
    season: str

    demand_profile_id: str
    category: str
    department: str
    store: str
    state: str
    demand_class: str

    baseline_occurrence_probability: float
    baseline_positive_demand_mean: float
    weekday_factor: float

    temperature_c: float
    precipitation_mm: float
    snowfall_cm: float
    wind_kmh: float
    weather_events: list[str]

    economic_regime: str
    economic_demand_multiplier: float
    logistics_cost_multiplier: float

    promotion: Promotion | None
    operational_events: list[ScenarioEvent]

    final_demand_multiplier: float
    final_supply_multiplier: float
    expected_demand_units: float

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["promotion"] = (
            self.promotion.to_dict() if self.promotion else None
        )
        payload["operational_events"] = [
            event.to_dict() for event in self.operational_events
        ]
        return payload
