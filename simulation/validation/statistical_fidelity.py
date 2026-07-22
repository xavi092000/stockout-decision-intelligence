from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from simulation.scenario_models import DayScenario


class StatisticalFidelityError(ValueError):
    """Raised when a statistical fidelity contract is malformed."""


@dataclass(frozen=True)
class FidelityThresholds:
    categorical_total_variation_max: float = 0.08
    probability_absolute_error_max: float = 0.05
    normalized_mean_error_max: float = 0.20
    hierarchy_violation_rate_max: float = 0.0
    minimum_scenarios: int = 3_650

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if name == "minimum_scenarios":
                if not isinstance(value, int) or value <= 0:
                    raise StatisticalFidelityError(
                        "minimum_scenarios must be a positive integer."
                    )
            elif not 0.0 <= float(value) <= 1.0:
                raise StatisticalFidelityError(
                    f"{name} must be between 0 and 1."
                )


@dataclass(frozen=True)
class MetricResult:
    name: str
    metric: str
    observed: Any
    expected: Any
    error: float
    threshold: float
    passed: bool
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StatisticalFidelityReport:
    passed: bool
    sample_size: int
    metrics: tuple[MetricResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "sample_size": self.sample_size,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }

    def failed_metrics(self) -> tuple[MetricResult, ...]:
        return tuple(metric for metric in self.metrics if not metric.passed)


def _normalized_weights(
    profiles: Iterable[dict[str, Any]],
    label_key: str,
    weight_path: tuple[str, ...],
) -> dict[str, float]:
    raw: dict[str, float] = {}
    for profile in profiles:
        label = str(profile[label_key])
        value: Any = profile
        for part in weight_path:
            if not isinstance(value, dict):
                value = 0.0
                break
            value = value.get(part, 0.0)
        raw[label] = max(0.0, float(value or 0.0))
    total = sum(raw.values())
    if total <= 0:
        if not raw:
            raise StatisticalFidelityError("Cannot normalize empty profiles.")
        equal = 1.0 / len(raw)
        return {label: equal for label in raw}
    return {label: weight / total for label, weight in raw.items()}


def _observed_distribution(values: Iterable[str]) -> tuple[dict[str, float], int]:
    counts = Counter(values)
    total = sum(counts.values())
    if total <= 0:
        return {}, 0
    return ({key: value / total for key, value in counts.items()}, total)


def _total_variation(
    observed: dict[str, float], expected: dict[str, float]
) -> float:
    labels = set(observed) | set(expected)
    return 0.5 * sum(
        abs(observed.get(label, 0.0) - expected.get(label, 0.0))
        for label in labels
    )


def _categorical_metric(
    name: str,
    values: Iterable[str],
    expected: dict[str, float],
    threshold: float,
) -> MetricResult:
    observed, sample_size = _observed_distribution(values)
    error = _total_variation(observed, expected)
    return MetricResult(
        name=name,
        metric="total_variation_distance",
        observed=observed,
        expected=expected,
        error=round(error, 8),
        threshold=threshold,
        passed=error <= threshold,
        sample_size=sample_size,
    )


def _probability_metric(
    name: str,
    successes: int,
    total: int,
    expected: float,
    threshold: float,
) -> MetricResult:
    observed = successes / total if total else 0.0
    error = abs(observed - expected)
    return MetricResult(
        name=name,
        metric="absolute_probability_error",
        observed=round(observed, 8),
        expected=round(expected, 8),
        error=round(error, 8),
        threshold=threshold,
        passed=error <= threshold,
        sample_size=total,
    )


def _mean_metric(
    name: str,
    values: list[float],
    expected_mean: float,
    expected_std: float,
    threshold: float,
) -> MetricResult:
    observed = sum(values) / len(values) if values else 0.0
    denominator = max(abs(expected_std), 1.0)
    error = abs(observed - expected_mean) / denominator
    return MetricResult(
        name=name,
        metric="normalized_mean_error",
        observed=round(observed, 8),
        expected=round(expected_mean, 8),
        error=round(error, 8),
        threshold=threshold,
        passed=error <= threshold,
        sample_size=len(values),
    )


class StatisticalFidelityValidator:
    """Compare generated scenarios with calibration contracts.

    This validator intentionally evaluates only properties that have an
    explicit calibration or declared generator probability. It does not use
    historical trajectories and therefore preserves the simulator's leakage
    guard.
    """

    PROMOTION_PROBABILITY = 0.14
    OPERATIONAL_EVENT_PROBABILITIES = {
        "supplier_delay": 0.025,
        "truck_breakdown": 0.010,
        "warehouse_capacity_constraint": 0.018,
        "competitor_promotion": 0.030,
        "local_event_demand_spike": 0.022,
        "inventory_count_error": 0.012,
    }

    def __init__(
        self,
        calibrations: dict[str, Any],
        thresholds: FidelityThresholds | None = None,
    ) -> None:
        self.calibrations = calibrations
        self.thresholds = thresholds or FidelityThresholds()
        self.thresholds.validate()

    def evaluate(
        self,
        scenarios: Iterable[DayScenario],
        *,
        enforce_minimum_sample: bool = True,
    ) -> StatisticalFidelityReport:
        rows = list(scenarios)
        if enforce_minimum_sample and len(rows) < self.thresholds.minimum_scenarios:
            raise StatisticalFidelityError(
                "Statistical validation requires at least "
                f"{self.thresholds.minimum_scenarios} scenarios; got {len(rows)}."
            )
        if not rows:
            raise StatisticalFidelityError("No scenarios supplied.")

        metrics: list[MetricResult] = []
        cat_threshold = self.thresholds.categorical_total_variation_max
        prob_threshold = self.thresholds.probability_absolute_error_max

        metrics.append(_categorical_metric(
            "category_distribution",
            (row.category for row in rows),
            _normalized_weights(
                self.calibrations["category_profiles"],
                "source_group",
                ("metadata", "sampling_weight"),
            ),
            cat_threshold,
        ))
        metrics.append(_categorical_metric(
            "store_distribution",
            (row.store for row in rows),
            _normalized_weights(
                self.calibrations["store_profiles"],
                "source_group",
                ("metadata", "sampling_weight"),
            ),
            cat_threshold,
        ))
        metrics.append(_categorical_metric(
            "demand_class_distribution",
            (row.demand_class for row in rows),
            _normalized_weights(
                self.calibrations["demand_class_profiles"],
                "demand_class",
                ("series_share",),
            ),
            cat_threshold,
        ))

        economic_expected = _normalized_weights(
            self.calibrations["economic_profile"]["regime_profiles"],
            "regime_name",
            ("regime_probability",),
        )
        # Economic regimes persist for a month. Count one observation per
        # synthetic month instead of overweighting longer months.
        monthly_regimes: dict[tuple[int, int], str] = {}
        for row in rows:
            year, month, _ = map(int, row.synthetic_date.split("-"))
            monthly_regimes[(year, month)] = row.economic_regime
        metrics.append(_categorical_metric(
            "economic_regime_distribution_by_month",
            monthly_regimes.values(),
            economic_expected,
            cat_threshold,
        ))

        metrics.append(_probability_metric(
            "promotion_frequency",
            sum(row.promotion is not None for row in rows),
            len(rows),
            self.PROMOTION_PROBABILITY,
            prob_threshold,
        ))

        event_counts = Counter(
            event.event_type
            for row in rows
            for event in row.operational_events
        )
        for event_name, expected in self.OPERATIONAL_EVENT_PROBABILITIES.items():
            metrics.append(_probability_metric(
                f"operational_event_frequency:{event_name}",
                event_counts[event_name],
                len(rows),
                expected,
                prob_threshold,
            ))

        weather_months: dict[int, list[DayScenario]] = defaultdict(list)
        for row in rows:
            weather_months[row.month].append(row)
        monthly_profiles = {
            int(profile["month"]): profile
            for profile in self.calibrations["weather_profile"]["monthly_profiles"]
        }
        for month, month_rows in sorted(weather_months.items()):
            profile = monthly_profiles[month]
            metrics.append(_mean_metric(
                f"temperature_mean_month:{month:02d}",
                [row.temperature_c for row in month_rows],
                float(profile["temperature_mean_c"]),
                float(profile["temperature_std_c"]),
                self.thresholds.normalized_mean_error_max,
            ))
            metrics.append(_probability_metric(
                f"precipitation_frequency_month:{month:02d}",
                sum(row.precipitation_mm > 0 for row in month_rows),
                len(month_rows),
                float(profile["precipitation_probability"]),
                prob_threshold,
            ))
            metrics.append(_probability_metric(
                f"snow_frequency_month:{month:02d}",
                sum(row.snowfall_cm > 0 for row in month_rows),
                len(month_rows),
                float(profile["snow_probability"]),
                prob_threshold,
            ))

        product_violations = sum(
            row.department.rsplit("_", 1)[0] != row.category for row in rows
        )
        location_violations = sum(
            row.store.split("_", 1)[0] != row.state for row in rows
        )
        for name, violations in (
            ("product_hierarchy_violation_rate", product_violations),
            ("location_hierarchy_violation_rate", location_violations),
        ):
            rate = violations / len(rows)
            metrics.append(MetricResult(
                name=name,
                metric="violation_rate",
                observed=round(rate, 8),
                expected=0.0,
                error=round(rate, 8),
                threshold=self.thresholds.hierarchy_violation_rate_max,
                passed=rate <= self.thresholds.hierarchy_violation_rate_max,
                sample_size=len(rows),
            ))

        return StatisticalFidelityReport(
            passed=all(metric.passed for metric in metrics),
            sample_size=len(rows),
            metrics=tuple(metrics),
        )
