from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Promotion:
    store_id: str
    sku_id: str
    demand_multiplier: float

    def __post_init__(self) -> None:
        if not self.store_id:
            raise ValueError("store_id cannot be empty.")

        if not self.sku_id:
            raise ValueError("sku_id cannot be empty.")

        if self.demand_multiplier < 1.0:
            raise ValueError(
                "demand_multiplier must be greater than or equal to 1.0."
            )


@dataclass(frozen=True)
class ScenarioEvent:
    event_type: str
    severity: float
    affected_store_ids: tuple[str, ...] = ()
    affected_sku_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type.strip():
            raise ValueError("event_type cannot be empty.")

        if not 0.0 <= self.severity <= 1.0:
            raise ValueError(
                "severity must be between 0 and 1."
            )


@dataclass
class DayScenario:
    scenario_id: str
    simulation_day: int
    scenario_date: date
    temperature_c: float
    weather_condition: str
    season: str
    is_weekend: bool
    is_holiday: bool = False
    promotions: list[Promotion] = field(default_factory=list)
    events: list[ScenarioEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id cannot be empty.")

        if self.simulation_day < 1:
            raise ValueError(
                "simulation_day must be greater than or equal to 1."
            )

        if not self.weather_condition.strip():
            raise ValueError(
                "weather_condition cannot be empty."
            )

        if not self.season.strip():
            raise ValueError("season cannot be empty.")

        if self.temperature_c < -60 or self.temperature_c > 60:
            raise ValueError(
                "temperature_c must remain between -60 and 60."
            )

        self._validate_unique_promotions()

    def _validate_unique_promotions(self) -> None:
        promotion_keys = {
            (promotion.store_id, promotion.sku_id)
            for promotion in self.promotions
        }

        if len(promotion_keys) != len(self.promotions):
            raise ValueError(
                "Duplicate store-SKU promotions detected."
            )

    def add_promotion(self, promotion: Promotion) -> None:
        key = (promotion.store_id, promotion.sku_id)

        existing_keys = {
            (item.store_id, item.sku_id)
            for item in self.promotions
        }

        if key in existing_keys:
            raise ValueError(
                "A promotion already exists for this store-SKU pair."
            )

        self.promotions.append(promotion)

    def add_event(self, event: ScenarioEvent) -> None:
        self.events.append(event)

    def get_promotion_multiplier(
        self,
        store_id: str,
        sku_id: str,
    ) -> float:
        for promotion in self.promotions:
            if (
                promotion.store_id == store_id
                and promotion.sku_id == sku_id
            ):
                return promotion.demand_multiplier

        return 1.0

    def has_event(self, event_type: str) -> bool:
        normalized_type = event_type.strip().upper()

        return any(
            event.event_type.strip().upper() == normalized_type
            for event in self.events
        )

    def summary(self) -> str:
        return (
            f"Scenario ID      : {self.scenario_id}\n"
            f"Simulation Day   : {self.simulation_day}\n"
            f"Scenario Date    : {self.scenario_date.isoformat()}\n"
            f"Season           : {self.season}\n"
            f"Weather          : {self.weather_condition}\n"
            f"Temperature      : {self.temperature_c:.1f} C\n"
            f"Weekend          : {self.is_weekend}\n"
            f"Holiday          : {self.is_holiday}\n"
            f"Promotions       : {len(self.promotions)}\n"
            f"Events           : {len(self.events)}"
        )