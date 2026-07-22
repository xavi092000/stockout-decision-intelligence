from __future__ import annotations

from dataclasses import dataclass
from random import Random

from simulation.entities import Product, Store
from simulation.scenario import DayScenario
from simulation.scenario_profile import ScenarioProfile


@dataclass(frozen=True)
class DemandForecast:
    """
    Demand information available at decision time.

    This object must never contain future realized demand.
    """

    store_id: str
    sku_id: str
    forecast_daily_demand: float
    forecast_next_3d: float
    weekday_multiplier: float
    promotion_multiplier: float
    weather_multiplier: float

    def __post_init__(self) -> None:
        if self.forecast_daily_demand < 0:
            raise ValueError(
                "forecast_daily_demand cannot be negative."
            )

        if self.forecast_next_3d < 0:
            raise ValueError(
                "forecast_next_3d cannot be negative."
            )


@dataclass(frozen=True)
class RealizedDemand:
    """
    Demand observed after the decision.

    This object is a simulation outcome, not a model feature.
    """

    store_id: str
    sku_id: str
    forecast_daily_demand: float
    actual_demand: int
    forecast_error: float

    def __post_init__(self) -> None:
        if self.actual_demand < 0:
            raise ValueError("actual_demand cannot be negative.")


@dataclass
class DemandEngine:
    profile: ScenarioProfile
    random_seed: int = 42

    def __post_init__(self) -> None:
        if self.random_seed < 0:
            raise ValueError("random_seed cannot be negative.")

        self._rng = Random(self.random_seed)

    def create_forecast(
        self,
        product: Product,
        store: Store,
        scenario: DayScenario,
    ) -> DemandForecast:
        """
        Create the demand forecast visible at decision time.

        Only currently known information is used:
        - product baseline
        - store traffic
        - weekday
        - active promotion
        - current weather
        """
        weekday_multiplier = self._weekday_multiplier(
            scenario=scenario,
        )

        promotion_multiplier = (
            scenario.get_promotion_multiplier(
                store_id=store.store_id,
                sku_id=product.sku_id,
            )
        )

        weather_multiplier = self._weather_multiplier(
            product=product,
            scenario=scenario,
        )

        forecast_daily_demand = (
            product.base_daily_demand
            * store.traffic_multiplier
            * weekday_multiplier
            * promotion_multiplier
            * weather_multiplier
        )

        forecast_daily_demand = round(
            max(0.0, forecast_daily_demand),
            2,
        )

        forecast_next_3d = round(
            forecast_daily_demand * 3,
            2,
        )

        return DemandForecast(
            store_id=store.store_id,
            sku_id=product.sku_id,
            forecast_daily_demand=forecast_daily_demand,
            forecast_next_3d=forecast_next_3d,
            weekday_multiplier=weekday_multiplier,
            promotion_multiplier=promotion_multiplier,
            weather_multiplier=weather_multiplier,
        )

    def realize_demand(
        self,
        forecast: DemandForecast,
        demand_noise_std_ratio: float = 0.12,
    ) -> RealizedDemand:
        """
        Generate future realized demand after the decision.

        This value must never be exposed as an input feature.
        """
        if demand_noise_std_ratio < 0:
            raise ValueError(
                "demand_noise_std_ratio cannot be negative."
            )

        standard_deviation = (
            forecast.forecast_daily_demand
            * demand_noise_std_ratio
        )

        sampled_demand = self._rng.gauss(
            forecast.forecast_daily_demand,
            standard_deviation,
        )

        actual_demand = max(
            0,
            round(sampled_demand),
        )

        forecast_error = round(
            actual_demand - forecast.forecast_daily_demand,
            2,
        )

        return RealizedDemand(
            store_id=forecast.store_id,
            sku_id=forecast.sku_id,
            forecast_daily_demand=(
                forecast.forecast_daily_demand
            ),
            actual_demand=actual_demand,
            forecast_error=forecast_error,
        )

    def _weekday_multiplier(
        self,
        scenario: DayScenario,
    ) -> float:
        weekday_index = scenario.scenario_date.weekday()

        multipliers = self.profile.calendar_effects[
            "weekday_multipliers"
        ]

        return float(
            multipliers[str(weekday_index)]
        )

    def _weather_multiplier(
        self,
        product: Product,
        scenario: DayScenario,
    ) -> float:
        weather_effects = (
            self.profile.category_weather_effects
        )

        condition_effects = weather_effects.get(
            scenario.weather_condition,
            {},
        )

        return float(
            condition_effects.get(
                product.category,
                1.0,
            )
        )