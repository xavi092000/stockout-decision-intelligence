from __future__ import annotations

from dataclasses import dataclass
from random import Random

from simulation.clock import SimulationClock
from simulation.scenario import DayScenario, Promotion, ScenarioEvent
from simulation.scenario_profile import ScenarioProfile
from simulation.scenario_rules import ScenarioValidator
from simulation.simulator import SimulationWorld


@dataclass
class ScenarioGenerator:
    profile: ScenarioProfile
    validator: ScenarioValidator
    random_seed: int = 42

    def __post_init__(self) -> None:
        if self.random_seed < 0:
            raise ValueError("random_seed cannot be negative.")

        self._rng = Random(self.random_seed)

    def generate(
        self,
        clock: SimulationClock,
        world: SimulationWorld,
    ) -> DayScenario:
        """
        Generate one coherent daily scenario.

        The same seed and the same generation sequence produce
        the same scenarios.
        """
        season = self.validator.season_for_date(clock.current_date)

        temperature_c = self._generate_temperature(season)

        weather_condition = self._generate_weather(
            season=season,
            temperature_c=temperature_c,
        )

        scenario = DayScenario(
            scenario_id=f"SCN_{clock.current_day:06d}",
            simulation_day=clock.current_day,
            scenario_date=clock.current_date,
            temperature_c=temperature_c,
            weather_condition=weather_condition,
            season=season,
            is_weekend=clock.is_weekend,
            is_holiday=False,
        )

        self._add_weather_event(scenario)

        self._add_promotions(
            scenario=scenario,
            world=world,
        )

        self.validator.validate_or_raise(scenario)

        return scenario

    def _generate_temperature(
        self,
        season: str,
    ) -> float:
        season_config = self.profile.weather[season]

        mean = float(
            season_config["temperature_mean_c"]
        )

        standard_deviation = float(
            season_config["temperature_std_c"]
        )

        season_minimum, season_maximum = (
            self.validator.TEMPERATURE_RANGES[season]
        )

        profile_minimum = float(
            self.profile.validation_limits[
                "minimum_temperature_c"
            ]
        )

        profile_maximum = float(
            self.profile.validation_limits[
                "maximum_temperature_c"
            ]
        )

        minimum_temperature = max(
            season_minimum,
            profile_minimum,
        )

        maximum_temperature = min(
            season_maximum,
            profile_maximum,
        )

        temperature = self._rng.gauss(
            mean,
            standard_deviation,
        )

        temperature = max(
            minimum_temperature,
            min(
                maximum_temperature,
                temperature,
            ),
        )

        return round(temperature, 1)

    def _generate_weather(
        self,
        season: str,
        temperature_c: float,
    ) -> str:
        weights = dict(
            self.profile.weather[season][
                "condition_weights"
            ]
        )

        compatible_weights = {
            condition: weight
            for condition, weight in weights.items()
            if self._weather_is_temperature_compatible(
                condition=condition,
                temperature_c=temperature_c,
            )
        }

        if not compatible_weights:
            return "clear"

        conditions = list(compatible_weights)
        probabilities = list(
            compatible_weights.values()
        )

        return self._rng.choices(
            population=conditions,
            weights=probabilities,
            k=1,
        )[0]

    def _weather_is_temperature_compatible(
        self,
        condition: str,
        temperature_c: float,
    ) -> bool:
        temperature_rule = (
            self.validator
            .WEATHER_TEMPERATURE_RULES
            .get(condition)
        )

        if temperature_rule is None:
            return True

        minimum, maximum = temperature_rule

        return minimum <= temperature_c <= maximum

    def _add_weather_event(
        self,
        scenario: DayScenario,
    ) -> None:
        event_mapping = {
            "heatwave": "HEATWAVE",
            "snowstorm": "SNOWSTORM",
            "freezing_rain": "FREEZING_RAIN",
            "storm": "STORM",
        }

        event_type = event_mapping.get(
            scenario.weather_condition
        )

        if event_type is None:
            return

        severity = self._calculate_weather_severity(
            weather_condition=scenario.weather_condition,
            temperature_c=scenario.temperature_c,
        )

        scenario.add_event(
            ScenarioEvent(
                event_type=event_type,
                severity=severity,
                metadata={
                    "temperature_c": scenario.temperature_c,
                    "weather_condition": (
                        scenario.weather_condition
                    ),
                },
            )
        )

    def _calculate_weather_severity(
        self,
        weather_condition: str,
        temperature_c: float,
    ) -> float:
        if weather_condition == "heatwave":
            severity = (
                temperature_c - 30.0
            ) / 12.0

        elif weather_condition in {
            "snow",
            "snowstorm",
            "freezing_rain",
        }:
            severity = (
                abs(min(temperature_c, 0.0))
                / 35.0
            )

        else:
            severity = 0.5

        return round(
            max(
                0.1,
                min(1.0, severity),
            ),
            3,
        )

    def _add_promotions(
        self,
        scenario: DayScenario,
        world: SimulationWorld,
    ) -> None:
        promotion_config = self.profile.promotions

        start_probability = float(
            promotion_config[
                "start_probability_per_store_sku_day"
            ]
        )

        minimum_multiplier = float(
            promotion_config[
                "demand_multiplier_min"
            ]
        )

        maximum_multiplier = float(
            promotion_config[
                "demand_multiplier_max"
            ]
        )

        minimum_stock_ratio = float(
            promotion_config[
                "minimum_available_stock_ratio"
            ]
        )

        products_by_id = {
            product.sku_id: product
            for product in world.products
        }

        for inventory in world.inventories:
            product = products_by_id[
                inventory.sku_id
            ]

            minimum_required_stock = (
                product.reorder_point
                * minimum_stock_ratio
            )

            if (
                inventory.available_stock
                < minimum_required_stock
            ):
                continue

            if (
                self._rng.random()
                >= start_probability
            ):
                continue

            demand_multiplier = round(
                self._rng.uniform(
                    minimum_multiplier,
                    maximum_multiplier,
                ),
                2,
            )

            scenario.add_promotion(
                Promotion(
                    store_id=inventory.store_id,
                    sku_id=inventory.sku_id,
                    demand_multiplier=demand_multiplier,
                )
            )