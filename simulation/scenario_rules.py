from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from simulation.scenario import DayScenario, ScenarioEvent


@dataclass(frozen=True)
class ScenarioValidationResult:
    is_valid: bool
    errors: tuple[str, ...] = ()


class ScenarioValidator:
    """
    Validate that a DayScenario remains temporally and logically coherent.
    """

    VALID_SEASONS = {
        "winter",
        "spring",
        "summer",
        "autumn",
    }

    VALID_WEATHER_BY_SEASON = {
        "winter": {
            "clear",
            "cloudy",
            "snow",
            "snowstorm",
            "freezing_rain",
        },
        "spring": {
            "clear",
            "cloudy",
            "rain",
            "storm",
        },
        "summer": {
            "clear",
            "cloudy",
            "rain",
            "storm",
            "heatwave",
        },
        "autumn": {
            "clear",
            "cloudy",
            "rain",
            "storm",
        },
    }

    TEMPERATURE_RANGES = {
        "winter": (-35.0, 10.0),
        "spring": (-5.0, 28.0),
        "summer": (8.0, 42.0),
        "autumn": (-10.0, 25.0),
    }

    WEATHER_TEMPERATURE_RULES = {
        "snow": (-35.0, 3.0),
        "snowstorm": (-35.0, 2.0),
        "freezing_rain": (-10.0, 2.0),
        "heatwave": (30.0, 42.0),
    }

    def validate(
        self,
        scenario: DayScenario,
    ) -> ScenarioValidationResult:
        errors: list[str] = []

        self._validate_season(scenario, errors)
        self._validate_weather(scenario, errors)
        self._validate_temperature(scenario, errors)
        self._validate_promotions(scenario, errors)
        self._validate_events(scenario, errors)

        return ScenarioValidationResult(
            is_valid=not errors,
            errors=tuple(errors),
        )

    def validate_or_raise(
        self,
        scenario: DayScenario,
    ) -> None:
        result = self.validate(scenario)

        if not result.is_valid:
            message = "\n".join(
                f"- {error}"
                for error in result.errors
            )

            raise ValueError(
                "Scenario validation failed:\n"
                f"{message}"
            )

    def _validate_season(
        self,
        scenario: DayScenario,
        errors: list[str],
    ) -> None:
        season = scenario.season.strip().lower()

        if season not in self.VALID_SEASONS:
            errors.append(
                f"Unsupported season: {scenario.season!r}."
            )
            return

        expected_season = self.season_for_date(
            scenario.scenario_date
        )

        if season != expected_season:
            errors.append(
                "Scenario season does not match the scenario date: "
                f"expected {expected_season!r}, got {season!r}."
            )

    def _validate_weather(
        self,
        scenario: DayScenario,
        errors: list[str],
    ) -> None:
        season = scenario.season.strip().lower()
        weather = scenario.weather_condition.strip().lower()

        allowed_weather = self.VALID_WEATHER_BY_SEASON.get(
            season,
            set(),
        )

        if weather not in allowed_weather:
            errors.append(
                f"Weather {weather!r} is not valid for season "
                f"{season!r}."
            )

    def _validate_temperature(
        self,
        scenario: DayScenario,
        errors: list[str],
    ) -> None:
        season = scenario.season.strip().lower()
        temperature = scenario.temperature_c

        if season in self.TEMPERATURE_RANGES:
            minimum, maximum = self.TEMPERATURE_RANGES[season]

            if not minimum <= temperature <= maximum:
                errors.append(
                    f"Temperature {temperature:.1f} C is outside "
                    f"the expected range for {season}: "
                    f"{minimum:.1f} to {maximum:.1f} C."
                )

        weather = scenario.weather_condition.strip().lower()

        if weather in self.WEATHER_TEMPERATURE_RULES:
            minimum, maximum = (
                self.WEATHER_TEMPERATURE_RULES[weather]
            )

            if not minimum <= temperature <= maximum:
                errors.append(
                    f"Temperature {temperature:.1f} C is incompatible "
                    f"with weather {weather!r}: expected "
                    f"{minimum:.1f} to {maximum:.1f} C."
                )

    def _validate_promotions(
        self,
        scenario: DayScenario,
        errors: list[str],
    ) -> None:
        seen_keys: set[tuple[str, str]] = set()

        for promotion in scenario.promotions:
            key = (
                promotion.store_id,
                promotion.sku_id,
            )

            if key in seen_keys:
                errors.append(
                    "Duplicate promotion detected for "
                    f"store={promotion.store_id}, "
                    f"sku={promotion.sku_id}."
                )

            seen_keys.add(key)

            if promotion.demand_multiplier > 3.0:
                errors.append(
                    "Promotion demand_multiplier is unrealistically "
                    f"high for store={promotion.store_id}, "
                    f"sku={promotion.sku_id}: "
                    f"{promotion.demand_multiplier:.2f}."
                )

    def _validate_events(
        self,
        scenario: DayScenario,
        errors: list[str],
    ) -> None:
        for event in scenario.events:
            self._validate_event_compatibility(
                scenario,
                event,
                errors,
            )

    def _validate_event_compatibility(
        self,
        scenario: DayScenario,
        event: ScenarioEvent,
        errors: list[str],
    ) -> None:
        event_type = event.event_type.strip().upper()
        weather = scenario.weather_condition.strip().lower()
        season = scenario.season.strip().lower()

        if (
            event_type == "HEATWAVE"
            and weather != "heatwave"
        ):
            errors.append(
                "HEATWAVE event requires weather_condition='heatwave'."
            )

        if (
            event_type == "SNOWSTORM"
            and weather != "snowstorm"
        ):
            errors.append(
                "SNOWSTORM event requires "
                "weather_condition='snowstorm'."
            )

        if (
            event_type == "HEATWAVE"
            and season != "summer"
        ):
            errors.append(
                "HEATWAVE event is only valid during summer."
            )

        if (
            event_type == "SNOWSTORM"
            and season != "winter"
        ):
            errors.append(
                "SNOWSTORM event is only valid during winter."
            )

        if (
            event_type == "HOLIDAY_SURGE"
            and not scenario.is_holiday
        ):
            errors.append(
                "HOLIDAY_SURGE event requires is_holiday=True."
            )

    @staticmethod
    def season_for_date(value: date) -> str:
        month = value.month

        if month in {12, 1, 2}:
            return "winter"

        if month in {3, 4, 5}:
            return "spring"

        if month in {6, 7, 8}:
            return "summer"

        return "autumn"