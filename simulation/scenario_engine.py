from __future__ import annotations

from datetime import date, timedelta
from random import Random
from typing import Any
import hashlib
import math
import uuid

from simulation.scenario_models import DayScenario, Promotion, ScenarioEvent


SEASON_BY_MONTH = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}


class ScenarioEngineError(RuntimeError):
    """Raised when the scenario engine cannot generate a safe scenario."""


class ScenarioEngine:
    def __init__(
        self,
        calibrations: dict[str, Any],
        seed: int = 42,
        start_date: date = date(2027, 1, 1),
    ) -> None:
        self.calibrations = calibrations
        self.random = Random(seed)
        self.seed = seed
        self.start_date = start_date
        self._economic_regime_cache: dict[tuple[int, int], dict[str, Any]] = {}

        self._validate_calibrations()

    def _validate_calibrations(self) -> None:
        required_lists = (
            "category_profiles",
            "department_profiles",
            "store_profiles",
            "state_profiles",
            "demand_class_profiles",
            "weekday_profiles",
        )
        for key in required_lists:
            value = self.calibrations.get(key)
            if not isinstance(value, list) or not value:
                raise ScenarioEngineError(
                    f"Calibration list is missing or empty: {key}"
                )

        weather = self.calibrations.get("weather_profile", {})
        if not weather.get("monthly_profiles"):
            raise ScenarioEngineError("Monthly weather profiles are missing.")
        if not weather.get("event_profiles"):
            raise ScenarioEngineError("Weather event profiles are missing.")

        economic = self.calibrations.get("economic_profile", {})
        if not economic.get("regime_profiles"):
            raise ScenarioEngineError("Economic regimes are missing.")

        category_names = {
            str(profile.get("source_group"))
            for profile in self.calibrations["category_profiles"]
        }
        for profile in self.calibrations["department_profiles"]:
            department = str(profile.get("source_group", ""))
            parent_category = self._parent_category_from_department(department)
            if parent_category not in category_names:
                raise ScenarioEngineError(
                    "Department calibration has no matching category: "
                    f"{department} -> {parent_category}"
                )

        state_names = {
            str(profile.get("source_group"))
            for profile in self.calibrations["state_profiles"]
        }
        for profile in self.calibrations["store_profiles"]:
            store = str(profile.get("source_group", ""))
            parent_state = self._state_from_store(store)
            if parent_state not in state_names:
                raise ScenarioEngineError(
                    "Store calibration has no matching state: "
                    f"{store} -> {parent_state}"
                )

    def _weighted_choice(
        self,
        items: list[dict[str, Any]],
        weight_key: str | None = None,
    ) -> dict[str, Any]:
        if weight_key is None:
            return self.random.choice(items)

        weights = []
        for item in items:
            value: Any = item
            for part in weight_key.split("."):
                if not isinstance(value, dict):
                    value = 0.0
                    break
                value = value.get(part, 0.0)
            weights.append(max(0.0, float(value or 0.0)))

        if sum(weights) <= 0:
            return self.random.choice(items)

        threshold = self.random.random() * sum(weights)
        cumulative = 0.0
        for item, weight in zip(items, weights):
            cumulative += weight
            if cumulative >= threshold:
                return item
        return items[-1]

    @staticmethod
    def _parent_category_from_department(department: str) -> str:
        """Return the M5 category encoded by a department identifier."""
        value = department.strip()
        if "_" not in value:
            raise ScenarioEngineError(
                f"Invalid department identifier: {department!r}"
            )
        return value.rsplit("_", 1)[0]

    @staticmethod
    def _state_from_store(store: str) -> str:
        """Return the M5 state encoded by a store identifier."""
        value = store.strip()
        if "_" not in value:
            raise ScenarioEngineError(
                f"Invalid store identifier: {store!r}"
            )
        return value.split("_", 1)[0]

    def _sample_product_hierarchy(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Sample category first, then a compatible department.

        This preserves the calibrated category marginal while preventing
        impossible category/department combinations.
        """
        category = self._weighted_choice(
            self.calibrations["category_profiles"],
            "metadata.sampling_weight",
        )
        category_name = str(category["source_group"])
        compatible_departments = [
            profile
            for profile in self.calibrations["department_profiles"]
            if self._parent_category_from_department(
                str(profile.get("source_group", ""))
            ) == category_name
        ]
        if not compatible_departments:
            raise ScenarioEngineError(
                f"No department profiles found for category {category_name}."
            )
        department = self._weighted_choice(
            compatible_departments,
            "metadata.sampling_weight",
        )
        return category, department

    def _sample_location_hierarchy(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Sample a store and derive its compatible state profile.

        Store weights already encode the observed geographic mix. Deriving
        the state from the selected store preserves that mix without creating
        impossible store/state pairs.
        """
        store = self._weighted_choice(
            self.calibrations["store_profiles"],
            "metadata.sampling_weight",
        )
        state_name = self._state_from_store(str(store["source_group"]))
        state = next(
            (
                profile
                for profile in self.calibrations["state_profiles"]
                if str(profile.get("source_group")) == state_name
            ),
            None,
        )
        if state is None:
            raise ScenarioEngineError(
                f"No state profile found for store {store['source_group']}."
            )
        return store, state

    def _weekday_factor(self, weekday_name: str) -> float:
        profiles = self.calibrations["weekday_profiles"]
        for profile in profiles:
            if str(profile.get("weekday")).lower() == weekday_name.lower():
                return max(0.01, float(profile.get("factor", 1.0)))
        return 1.0

    def _sample_weather(
        self,
        month: int,
    ) -> tuple[float, float, float, float, list[str]]:
        monthly_profiles = self.calibrations[
            "weather_profile"
        ]["monthly_profiles"]
        monthly = next(
            (
                profile
                for profile in monthly_profiles
                if int(profile["month"]) == month
            ),
            None,
        )
        if monthly is None:
            raise ScenarioEngineError(
                f"No weather profile found for month {month}."
            )

        mean = float(monthly["temperature_mean_c"])
        std = max(0.1, float(monthly["temperature_std_c"]))
        temperature = self.random.gauss(mean, std)

        precip_probability = min(
            1.0,
            max(0.0, float(monthly["precipitation_probability"])),
        )
        snow_probability = min(
            1.0,
            max(0.0, float(monthly["snow_probability"])),
        )

        precipitation = 0.0
        snowfall = 0.0

        if self.random.random() < precip_probability:
            mean_precip = max(
                0.1,
                float(monthly.get("precipitation_mean_mm", 1.0)),
            )
            precipitation = self.random.expovariate(1.0 / mean_precip)

        if self.random.random() < snow_probability:
            snowfall = self.random.expovariate(1.0 / 3.0)

        wind_mean = max(
            1.0,
            float(monthly.get("wind_speed_mean_kmh", 15.0)),
        )
        wind = max(0.0, self.random.gauss(wind_mean, wind_mean * 0.35))

        events = []
        event_profiles = self.calibrations[
            "weather_profile"
        ]["event_profiles"]

        for event_name, profile in event_profiles.items():
            probability = min(
                1.0,
                max(0.0, float(profile.get("annual_probability", 0.0))),
            )
            if self.random.random() < probability:
                events.append(event_name)

        if "extreme_cold" in events:
            temperature -= self.random.uniform(5.0, 12.0)
        if "extreme_heat" in events:
            temperature += self.random.uniform(4.0, 9.0)
        if "heavy_precipitation" in events:
            precipitation += self.random.uniform(10.0, 30.0)
        if "heavy_snow" in events:
            snowfall += self.random.uniform(5.0, 20.0)
        if "high_wind" in events:
            wind += self.random.uniform(25.0, 60.0)

        return (
            round(temperature, 2),
            round(precipitation, 2),
            round(snowfall, 2),
            round(wind, 2),
            events,
        )

    def _sample_economic_regime_for_month(
        self,
        year: int,
        month: int,
    ) -> dict[str, Any]:
        """Sample one synthetic economic regime per calendar month.

        Economic calibration is monthly. Reusing the sampled regime for every
        day in the same synthetic month prevents unrealistic day-to-day regime
        switching while keeping historical monthly trajectories inaccessible.
        A month-specific deterministic random stream makes results independent
        of the order in which simulation days are requested.
        """
        key = (year, month)
        cached = self._economic_regime_cache.get(key)
        if cached is not None:
            return cached

        regimes = self.calibrations[
            "economic_profile"
        ]["regime_profiles"]
        seed_material = f"{self.seed}:economic:{year:04d}-{month:02d}"
        digest = hashlib.sha256(seed_material.encode("utf-8")).digest()
        month_rng = Random(int.from_bytes(digest[:8], "big"))

        weights = [
            max(0.0, float(item.get("regime_probability", 0.0) or 0.0))
            for item in regimes
        ]
        if sum(weights) <= 0:
            selected = month_rng.choice(regimes)
        else:
            selected = month_rng.choices(regimes, weights=weights, k=1)[0]

        self._economic_regime_cache[key] = selected
        return selected

    def _sample_promotion(self) -> Promotion | None:
        if self.random.random() >= 0.14:
            return None

        promotion_type = self.random.choice(
            ["percentage_discount", "buy_more_save_more", "featured_display"]
        )

        if promotion_type == "percentage_discount":
            discount = self.random.choice([0.05, 0.10, 0.15, 0.20])
            multiplier = 1.0 + discount * self.random.uniform(1.4, 2.3)
        elif promotion_type == "buy_more_save_more":
            discount = self.random.choice([0.05, 0.08, 0.12])
            multiplier = self.random.uniform(1.10, 1.30)
        else:
            discount = 0.0
            multiplier = self.random.uniform(1.05, 1.18)

        return Promotion(
            promotion_type=promotion_type,
            discount_rate=round(discount, 4),
            demand_multiplier=round(multiplier, 4),
        )

    def _sample_operational_events(self) -> list[ScenarioEvent]:
        event_specs = [
            (
                "supplier_delay",
                0.025,
                (0.98, 1.03),
                (0.60, 0.90),
                (1.03, 1.12),
                "Supplier lead time increased unexpectedly.",
            ),
            (
                "truck_breakdown",
                0.010,
                (0.98, 1.02),
                (0.40, 0.75),
                (1.08, 1.22),
                "Inbound truck experienced a mechanical failure.",
            ),
            (
                "warehouse_capacity_constraint",
                0.018,
                (0.97, 1.02),
                (0.70, 0.92),
                (1.02, 1.10),
                "Warehouse throughput was temporarily constrained.",
            ),
            (
                "competitor_promotion",
                0.030,
                (0.82, 0.96),
                (0.98, 1.00),
                (1.00, 1.02),
                "A competitor launched an aggressive promotion.",
            ),
            (
                "local_event_demand_spike",
                0.022,
                (1.12, 1.45),
                (0.98, 1.00),
                (1.00, 1.04),
                "A local event increased store demand.",
            ),
            (
                "inventory_count_error",
                0.012,
                (0.98, 1.02),
                (0.75, 0.95),
                (1.01, 1.06),
                "A temporary inventory accuracy issue occurred.",
            ),
        ]

        events: list[ScenarioEvent] = []
        for (
            event_type,
            probability,
            demand_range,
            supply_range,
            logistics_range,
            description,
        ) in event_specs:
            if self.random.random() < probability:
                severity = self.random.uniform(0.2, 1.0)
                events.append(
                    ScenarioEvent(
                        event_type=event_type,
                        severity=round(severity, 4),
                        demand_multiplier=round(
                            self.random.uniform(*demand_range),
                            4,
                        ),
                        supply_multiplier=round(
                            self.random.uniform(*supply_range),
                            4,
                        ),
                        logistics_cost_multiplier=round(
                            self.random.uniform(*logistics_range),
                            4,
                        ),
                        description=description,
                    )
                )
        return events

    @staticmethod
    def _weather_demand_multiplier(
        temperature_c: float,
        precipitation_mm: float,
        snowfall_cm: float,
        weather_events: list[str],
    ) -> float:
        multiplier = 1.0

        if temperature_c <= -15:
            multiplier *= 1.05
        elif temperature_c >= 28:
            multiplier *= 1.06

        if precipitation_mm >= 15:
            multiplier *= 0.94
        if snowfall_cm >= 8:
            multiplier *= 1.07

        if "extreme_cold" in weather_events:
            multiplier *= 1.04
        if "extreme_heat" in weather_events:
            multiplier *= 1.05
        if "heavy_precipitation" in weather_events:
            multiplier *= 0.95
        if "heavy_snow" in weather_events:
            multiplier *= 1.08
        if "high_wind" in weather_events:
            multiplier *= 0.97

        return multiplier

    def generate_day(self, simulation_day: int) -> DayScenario:
        synthetic_date = self.start_date + timedelta(days=simulation_day - 1)
        weekday = synthetic_date.strftime("%A")
        month = synthetic_date.month
        season = SEASON_BY_MONTH[month]

        category, department = self._sample_product_hierarchy()
        store, state = self._sample_location_hierarchy()
        demand_class = self._weighted_choice(
            self.calibrations["demand_class_profiles"],
            "series_share",
        )

        temperature, precipitation, snowfall, wind, weather_events = (
            self._sample_weather(month)
        )
        economic = self._sample_economic_regime_for_month(
            synthetic_date.year,
            synthetic_date.month,
        )
        promotion = self._sample_promotion()
        operational_events = self._sample_operational_events()

        weekday_factor = self._weekday_factor(weekday)
        weather_multiplier = self._weather_demand_multiplier(
            temperature,
            precipitation,
            snowfall,
            weather_events,
        )
        promotion_multiplier = (
            promotion.demand_multiplier if promotion else 1.0
        )
        economic_multiplier = float(
            economic.get("demand_multiplier", 1.0)
        )

        operational_demand_multiplier = math.prod(
            event.demand_multiplier for event in operational_events
        ) if operational_events else 1.0
        supply_multiplier = math.prod(
            event.supply_multiplier for event in operational_events
        ) if operational_events else 1.0
        logistics_multiplier = float(
            economic.get("logistics_cost_multiplier", 1.0)
        ) * (
            math.prod(
                event.logistics_cost_multiplier
                for event in operational_events
            )
            if operational_events
            else 1.0
        )

        base_distribution = category["distribution"]
        occurrence_probability = min(
            1.0,
            max(
                0.0,
                float(base_distribution["occurrence_probability"]),
            ),
        )
        positive_mean = max(
            0.0,
            float(base_distribution["positive_demand_mean"]),
        )

        final_demand_multiplier = (
            weekday_factor
            * weather_multiplier
            * promotion_multiplier
            * economic_multiplier
            * operational_demand_multiplier
        )

        expected_demand = (
            occurrence_probability
            * positive_mean
            * final_demand_multiplier
        )

        scenario_id = (
            f"scn-{simulation_day:05d}-"
            f"{uuid.UUID(int=self.random.getrandbits(128)).hex[:10]}"
        )

        return DayScenario(
            scenario_id=scenario_id,
            simulation_day=simulation_day,
            synthetic_date=synthetic_date.isoformat(),
            weekday=weekday,
            month=month,
            season=season,
            demand_profile_id=str(category["profile_id"]),
            category=str(category["source_group"]),
            department=str(department["source_group"]),
            store=str(store["source_group"]),
            state=str(state["source_group"]),
            demand_class=str(demand_class["demand_class"]),
            baseline_occurrence_probability=round(
                occurrence_probability,
                6,
            ),
            baseline_positive_demand_mean=round(positive_mean, 6),
            weekday_factor=round(weekday_factor, 6),
            temperature_c=temperature,
            precipitation_mm=precipitation,
            snowfall_cm=snowfall,
            wind_kmh=wind,
            weather_events=weather_events,
            economic_regime=str(economic["regime_name"]),
            economic_demand_multiplier=round(
                economic_multiplier,
                6,
            ),
            logistics_cost_multiplier=round(
                logistics_multiplier,
                6,
            ),
            promotion=promotion,
            operational_events=operational_events,
            final_demand_multiplier=round(
                final_demand_multiplier,
                6,
            ),
            final_supply_multiplier=round(
                supply_multiplier,
                6,
            ),
            expected_demand_units=round(expected_demand, 6),
            metadata={
                "synthetic": True,
                "seed": self.seed,
                "historical_trajectory_used": False,
                "hierarchy_sampling": {
                    "product": "category_then_compatible_department",
                    "location": "store_then_derived_state",
                },
                "weather_multiplier": round(weather_multiplier, 6),
                "promotion_multiplier": round(promotion_multiplier, 6),
                "operational_demand_multiplier": round(
                    operational_demand_multiplier,
                    6,
                ),
                "economic_regime_sampling": (
                    "one_synthetic_regime_per_calendar_month"
                ),
            },
        )

    def generate_days(self, days: int) -> list[DayScenario]:
        if days <= 0:
            raise ScenarioEngineError("days must be greater than zero.")
        return [
            self.generate_day(simulation_day)
            for simulation_day in range(1, days + 1)
        ]
