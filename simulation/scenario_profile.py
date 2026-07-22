from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScenarioProfile:
    profile_name: str
    version: str
    description: str
    weather: dict[str, Any]
    promotions: dict[str, Any]
    supplier_events: dict[str, Any]
    inventory_events: dict[str, Any]
    calendar_effects: dict[str, Any]
    category_weather_effects: dict[str, Any]
    validation_limits: dict[str, Any]


class ScenarioProfileLoader:
    REQUIRED_SEASONS = {
        "winter",
        "spring",
        "summer",
        "autumn",
    }

    REQUIRED_TOP_LEVEL_KEYS = {
        "profile_name",
        "version",
        "description",
        "weather",
        "promotions",
        "supplier_events",
        "inventory_events",
        "calendar_effects",
        "category_weather_effects",
        "validation_limits",
    }

    def load(self, path: str | Path) -> ScenarioProfile:
        profile_path = Path(path)

        if not profile_path.exists():
            raise FileNotFoundError(
                f"Scenario profile not found: {profile_path}"
            )

        if not profile_path.is_file():
            raise ValueError(
                f"Scenario profile path is not a file: {profile_path}"
            )

        try:
            raw_data = json.loads(
                profile_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in scenario profile: {exc}"
            ) from exc

        if not isinstance(raw_data, dict):
            raise ValueError(
                "Scenario profile root must be a JSON object."
            )

        self._validate(raw_data)

        return ScenarioProfile(
            profile_name=raw_data["profile_name"],
            version=raw_data["version"],
            description=raw_data["description"],
            weather=raw_data["weather"],
            promotions=raw_data["promotions"],
            supplier_events=raw_data["supplier_events"],
            inventory_events=raw_data["inventory_events"],
            calendar_effects=raw_data["calendar_effects"],
            category_weather_effects=(
                raw_data["category_weather_effects"]
            ),
            validation_limits=raw_data["validation_limits"],
        )

    def _validate(self, data: dict[str, Any]) -> None:
        self._validate_required_keys(data)
        self._validate_identity(data)
        self._validate_weather(data["weather"])
        self._validate_promotions(data["promotions"])
        self._validate_supplier_events(data["supplier_events"])
        self._validate_inventory_events(data["inventory_events"])
        self._validate_calendar_effects(data["calendar_effects"])
        self._validate_validation_limits(data["validation_limits"])

    def _validate_required_keys(
        self,
        data: dict[str, Any],
    ) -> None:
        missing_keys = self.REQUIRED_TOP_LEVEL_KEYS - set(data)

        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ValueError(
                f"Scenario profile is missing required keys: {missing}"
            )

    @staticmethod
    def _validate_identity(data: dict[str, Any]) -> None:
        for key in ("profile_name", "version", "description"):
            value = data[key]

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{key} must be a non-empty string."
                )

    def _validate_weather(
        self,
        weather: dict[str, Any],
    ) -> None:
        if not isinstance(weather, dict):
            raise ValueError("weather must be a JSON object.")

        missing_seasons = self.REQUIRED_SEASONS - set(weather)

        if missing_seasons:
            missing = ", ".join(sorted(missing_seasons))
            raise ValueError(
                f"Weather configuration is missing seasons: {missing}"
            )

        for season in self.REQUIRED_SEASONS:
            season_config = weather[season]

            self._require_numeric(
                season_config,
                "temperature_mean_c",
                section=f"weather.{season}",
            )
            self._require_positive_numeric(
                season_config,
                "temperature_std_c",
                section=f"weather.{season}",
            )

            weights = season_config.get("condition_weights")

            if not isinstance(weights, dict) or not weights:
                raise ValueError(
                    f"weather.{season}.condition_weights "
                    "must be a non-empty object."
                )

            total_weight = 0.0

            for condition, weight in weights.items():
                if not isinstance(condition, str) or not condition.strip():
                    raise ValueError(
                        f"weather.{season} contains an invalid "
                        "weather condition name."
                    )

                self._validate_probability(
                    weight,
                    field_name=(
                        f"weather.{season}."
                        f"condition_weights.{condition}"
                    ),
                )

                total_weight += float(weight)

            if abs(total_weight - 1.0) > 0.0001:
                raise ValueError(
                    f"Weather condition weights for {season} "
                    f"must sum to 1.0, got {total_weight:.6f}."
                )

    def _validate_promotions(
        self,
        promotions: dict[str, Any],
    ) -> None:
        self._validate_probability(
            promotions.get(
                "start_probability_per_store_sku_day"
            ),
            "promotions.start_probability_per_store_sku_day",
        )

        self._validate_integer_range(
            promotions,
            minimum_key="duration_days_min",
            maximum_key="duration_days_max",
            section="promotions",
            minimum_allowed=1,
        )

        self._validate_numeric_range(
            promotions,
            minimum_key="demand_multiplier_min",
            maximum_key="demand_multiplier_max",
            section="promotions",
            minimum_allowed=1.0,
        )

        minimum_ratio = promotions.get(
            "minimum_available_stock_ratio"
        )

        self._validate_probability(
            minimum_ratio,
            "promotions.minimum_available_stock_ratio",
        )

    def _validate_supplier_events(
        self,
        supplier_events: dict[str, Any],
    ) -> None:
        probability_keys = (
            "delay_probability_per_due_delivery",
            "partial_delivery_probability_per_delivery",
            "supplier_outage_probability_per_supplier_day",
        )

        for key in probability_keys:
            self._validate_probability(
                supplier_events.get(key),
                f"supplier_events.{key}",
            )

        self._validate_integer_range(
            supplier_events,
            "delay_days_min",
            "delay_days_max",
            "supplier_events",
            minimum_allowed=1,
        )

        self._validate_integer_range(
            supplier_events,
            "supplier_outage_duration_days_min",
            "supplier_outage_duration_days_max",
            "supplier_events",
            minimum_allowed=1,
        )

        self._validate_numeric_range(
            supplier_events,
            "partial_delivery_ratio_min",
            "partial_delivery_ratio_max",
            "supplier_events",
            minimum_allowed=0.0,
            maximum_allowed=1.0,
        )

    def _validate_inventory_events(
        self,
        inventory_events: dict[str, Any],
    ) -> None:
        probability_keys = (
            "damage_probability_per_store_sku_day",
            "inventory_error_probability_per_store_sku_day",
        )

        for key in probability_keys:
            self._validate_probability(
                inventory_events.get(key),
                f"inventory_events.{key}",
            )

        self._validate_numeric_range(
            inventory_events,
            "damage_ratio_min",
            "damage_ratio_max",
            "inventory_events",
            minimum_allowed=0.0,
            maximum_allowed=1.0,
        )

        self._validate_numeric_range(
            inventory_events,
            "inventory_error_ratio_min",
            "inventory_error_ratio_max",
            "inventory_events",
            minimum_allowed=-1.0,
            maximum_allowed=1.0,
        )

    def _validate_calendar_effects(
        self,
        calendar_effects: dict[str, Any],
    ) -> None:
        weekday_multipliers = calendar_effects.get(
            "weekday_multipliers"
        )

        if not isinstance(weekday_multipliers, dict):
            raise ValueError(
                "calendar_effects.weekday_multipliers "
                "must be an object."
            )

        expected_days = {str(day) for day in range(7)}

        if set(weekday_multipliers) != expected_days:
            raise ValueError(
                "weekday_multipliers must contain keys 0 through 6."
            )

        for day, multiplier in weekday_multipliers.items():
            if not isinstance(multiplier, (int, float)):
                raise ValueError(
                    f"Weekday multiplier {day} must be numeric."
                )

            if multiplier <= 0:
                raise ValueError(
                    f"Weekday multiplier {day} must be positive."
                )

        self._validate_numeric_range(
            calendar_effects,
            "holiday_demand_multiplier_min",
            "holiday_demand_multiplier_max",
            "calendar_effects",
            minimum_allowed=1.0,
        )

    def _validate_validation_limits(
        self,
        validation_limits: dict[str, Any],
    ) -> None:
        maximum_promotion_multiplier = validation_limits.get(
            "maximum_promotion_multiplier"
        )

        if (
            not isinstance(
                maximum_promotion_multiplier,
                (int, float),
            )
            or maximum_promotion_multiplier < 1.0
        ):
            raise ValueError(
                "validation_limits.maximum_promotion_multiplier "
                "must be numeric and at least 1.0."
            )

        maximum_events = validation_limits.get(
            "maximum_simultaneous_events_per_day"
        )

        if not isinstance(maximum_events, int) or maximum_events < 0:
            raise ValueError(
                "maximum_simultaneous_events_per_day "
                "must be a non-negative integer."
            )

        minimum_temperature = validation_limits.get(
            "minimum_temperature_c"
        )
        maximum_temperature = validation_limits.get(
            "maximum_temperature_c"
        )

        if not isinstance(minimum_temperature, (int, float)):
            raise ValueError(
                "minimum_temperature_c must be numeric."
            )

        if not isinstance(maximum_temperature, (int, float)):
            raise ValueError(
                "maximum_temperature_c must be numeric."
            )

        if minimum_temperature >= maximum_temperature:
            raise ValueError(
                "minimum_temperature_c must be lower than "
                "maximum_temperature_c."
            )

    @staticmethod
    def _validate_probability(
        value: Any,
        field_name: str,
    ) -> None:
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"{field_name} must be numeric."
            )

        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(
                f"{field_name} must be between 0 and 1."
            )

    @staticmethod
    def _require_numeric(
        data: dict[str, Any],
        key: str,
        section: str,
    ) -> None:
        value = data.get(key)

        if not isinstance(value, (int, float)):
            raise ValueError(
                f"{section}.{key} must be numeric."
            )

    @staticmethod
    def _require_positive_numeric(
        data: dict[str, Any],
        key: str,
        section: str,
    ) -> None:
        value = data.get(key)

        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(
                f"{section}.{key} must be greater than zero."
            )

    @staticmethod
    def _validate_integer_range(
        data: dict[str, Any],
        minimum_key: str,
        maximum_key: str,
        section: str,
        minimum_allowed: int,
    ) -> None:
        minimum_value = data.get(minimum_key)
        maximum_value = data.get(maximum_key)

        if not isinstance(minimum_value, int):
            raise ValueError(
                f"{section}.{minimum_key} must be an integer."
            )

        if not isinstance(maximum_value, int):
            raise ValueError(
                f"{section}.{maximum_key} must be an integer."
            )

        if minimum_value < minimum_allowed:
            raise ValueError(
                f"{section}.{minimum_key} must be at least "
                f"{minimum_allowed}."
            )

        if maximum_value < minimum_value:
            raise ValueError(
                f"{section}.{maximum_key} cannot be lower than "
                f"{section}.{minimum_key}."
            )

    @staticmethod
    def _validate_numeric_range(
        data: dict[str, Any],
        minimum_key: str,
        maximum_key: str,
        section: str,
        minimum_allowed: float,
        maximum_allowed: float | None = None,
    ) -> None:
        minimum_value = data.get(minimum_key)
        maximum_value = data.get(maximum_key)

        if not isinstance(minimum_value, (int, float)):
            raise ValueError(
                f"{section}.{minimum_key} must be numeric."
            )

        if not isinstance(maximum_value, (int, float)):
            raise ValueError(
                f"{section}.{maximum_key} must be numeric."
            )

        if minimum_value < minimum_allowed:
            raise ValueError(
                f"{section}.{minimum_key} must be at least "
                f"{minimum_allowed}."
            )

        if maximum_value < minimum_value:
            raise ValueError(
                f"{section}.{maximum_key} cannot be lower than "
                f"{section}.{minimum_key}."
            )

        if (
            maximum_allowed is not None
            and maximum_value > maximum_allowed
        ):
            raise ValueError(
                f"{section}.{maximum_key} cannot exceed "
                f"{maximum_allowed}."
            )