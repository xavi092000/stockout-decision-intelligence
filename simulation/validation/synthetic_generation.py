from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from typing import Any, Iterable

from simulation.scenario_models import DayScenario


class SyntheticGenerationError(ValueError):
    """Raised when a synthetic-generation validation contract is invalid."""


@dataclass(frozen=True)
class SyntheticGenerationThresholds:
    minimum_scenarios: int = 3_650
    minimum_unique_fingerprint_ratio: float = 0.55
    maximum_duplicate_scenario_id_rate: float = 0.0
    maximum_hierarchy_violation_rate: float = 0.0
    maximum_temporal_violation_rate: float = 0.0
    maximum_historical_trajectory_rate: float = 0.0
    require_full_calibration_coverage: bool = True
    require_all_declared_event_types: bool = True
    require_reproducibility_match: bool = True

    def validate(self) -> None:
        if not isinstance(self.minimum_scenarios, int) or self.minimum_scenarios <= 0:
            raise SyntheticGenerationError(
                "minimum_scenarios must be a positive integer."
            )
        for name in (
            "minimum_unique_fingerprint_ratio",
            "maximum_duplicate_scenario_id_rate",
            "maximum_hierarchy_violation_rate",
            "maximum_temporal_violation_rate",
            "maximum_historical_trajectory_rate",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise SyntheticGenerationError(f"{name} must be between 0 and 1.")


@dataclass(frozen=True)
class GenerationMetric:
    name: str
    observed: Any
    expected: Any
    passed: bool
    sample_size: int
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SyntheticGenerationReport:
    passed: bool
    sample_size: int
    digest: str
    metrics: tuple[GenerationMetric, ...]

    def failed_metrics(self) -> tuple[GenerationMetric, ...]:
        return tuple(metric for metric in self.metrics if not metric.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "sample_size": self.sample_size,
            "digest": self.digest,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


def scenario_digest(scenarios: Iterable[DayScenario]) -> str:
    """Return a stable digest that excludes the random scenario identifier.

    The identifier itself is validated for uniqueness. Excluding it here makes
    the reproducibility proof focus on the generated business world.
    """
    digest = sha256()
    for row in scenarios:
        payload = row.to_dict()
        payload.pop("scenario_id", None)
        digest.update(repr(sorted(payload.items())).encode("utf-8"))
    return digest.hexdigest()


def _calibration_labels(
    calibrations: dict[str, Any], key: str, label_key: str
) -> set[str]:
    return {str(item[label_key]) for item in calibrations[key]}


def _declared_weather_events(calibrations: dict[str, Any]) -> set[str]:
    return set(
        str(name)
        for name, profile in calibrations["weather_profile"][
            "event_profiles"
        ].items()
        if float(profile.get("annual_probability", 0.0) or 0.0) > 0.0
    )


DECLARED_OPERATIONAL_EVENTS = {
    "supplier_delay",
    "truck_breakdown",
    "warehouse_capacity_constraint",
    "competitor_promotion",
    "local_event_demand_spike",
    "inventory_count_error",
}


class SyntheticGenerationValidator:
    """Validate coverage, diversity, temporal coherence and reproducibility.

    Statistical distribution fidelity is intentionally handled by the Batch 6
    validator. This class focuses on whether the generator creates a complete,
    coherent, reproducible and non-degenerate synthetic world.
    """

    def __init__(
        self,
        calibrations: dict[str, Any],
        thresholds: SyntheticGenerationThresholds | None = None,
    ) -> None:
        self.calibrations = calibrations
        self.thresholds = thresholds or SyntheticGenerationThresholds()
        self.thresholds.validate()

    def evaluate(
        self,
        scenarios: Iterable[DayScenario],
        *,
        reproducibility_reference: Iterable[DayScenario] | None = None,
        enforce_minimum_sample: bool = True,
    ) -> SyntheticGenerationReport:
        rows = list(scenarios)
        if not rows:
            raise SyntheticGenerationError("No scenarios supplied.")
        if enforce_minimum_sample and len(rows) < self.thresholds.minimum_scenarios:
            raise SyntheticGenerationError(
                "Synthetic generation validation requires at least "
                f"{self.thresholds.minimum_scenarios} scenarios; got {len(rows)}."
            )

        metrics: list[GenerationMetric] = []
        total = len(rows)

        # 1. Scenario IDs must be unique.
        id_counts = Counter(row.scenario_id for row in rows)
        duplicate_count = sum(count - 1 for count in id_counts.values() if count > 1)
        duplicate_rate = duplicate_count / total
        metrics.append(GenerationMetric(
            name="scenario_id_uniqueness",
            observed=round(duplicate_rate, 8),
            expected=f"<= {self.thresholds.maximum_duplicate_scenario_id_rate}",
            passed=duplicate_rate <= self.thresholds.maximum_duplicate_scenario_id_rate,
            sample_size=total,
            details={"duplicate_count": duplicate_count},
        ))

        # 2. Business-state diversity must not collapse to a small set of rows.
        fingerprints = {
            (
                row.category,
                row.department,
                row.store,
                row.state,
                row.demand_class,
                row.month,
                row.economic_regime,
                row.promotion.promotion_type if row.promotion else "none",
                tuple(sorted(row.weather_events)),
                tuple(sorted(event.event_type for event in row.operational_events)),
                round(row.temperature_c, 1),
                round(row.final_demand_multiplier, 2),
                round(row.final_supply_multiplier, 2),
            )
            for row in rows
        }
        diversity_ratio = len(fingerprints) / total
        metrics.append(GenerationMetric(
            name="business_state_diversity",
            observed=round(diversity_ratio, 8),
            expected=f">= {self.thresholds.minimum_unique_fingerprint_ratio}",
            passed=diversity_ratio >= self.thresholds.minimum_unique_fingerprint_ratio,
            sample_size=total,
            details={"unique_fingerprints": len(fingerprints)},
        ))

        # 3. Every calibration dimension must be reachable.
        coverage_specs = {
            "category": (
                {row.category for row in rows},
                _calibration_labels(self.calibrations, "category_profiles", "source_group"),
            ),
            "department": (
                {row.department for row in rows},
                _calibration_labels(self.calibrations, "department_profiles", "source_group"),
            ),
            "store": (
                {row.store for row in rows},
                _calibration_labels(self.calibrations, "store_profiles", "source_group"),
            ),
            "state": (
                {row.state for row in rows},
                _calibration_labels(self.calibrations, "state_profiles", "source_group"),
            ),
            "demand_class": (
                {row.demand_class for row in rows},
                _calibration_labels(self.calibrations, "demand_class_profiles", "demand_class"),
            ),
            "economic_regime": (
                {row.economic_regime for row in rows},
                {
                    str(item["regime_name"])
                    for item in self.calibrations["economic_profile"]["regime_profiles"]
                    if float(item.get("regime_probability", 0.0) or 0.0) > 0.0
                },
            ),
        }
        for dimension, (observed, expected) in coverage_specs.items():
            missing = sorted(expected - observed)
            passed = not missing if self.thresholds.require_full_calibration_coverage else True
            metrics.append(GenerationMetric(
                name=f"calibration_coverage:{dimension}",
                observed=sorted(observed),
                expected=sorted(expected),
                passed=passed,
                sample_size=total,
                details={"missing": missing, "coverage_ratio": round(len(observed & expected) / max(len(expected), 1), 8)},
            ))

        calendar_observed = {
            "month": {row.month for row in rows},
            "season": {row.season for row in rows},
            "weekday": {row.weekday for row in rows},
        }
        calendar_expected = {
            "month": set(range(1, 13)),
            "season": {"winter", "spring", "summer", "autumn"},
            "weekday": {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"},
        }
        for dimension in calendar_expected:
            missing = sorted(calendar_expected[dimension] - calendar_observed[dimension])
            metrics.append(GenerationMetric(
                name=f"calendar_coverage:{dimension}",
                observed=sorted(calendar_observed[dimension]),
                expected=sorted(calendar_expected[dimension]),
                passed=not missing,
                sample_size=total,
                details={"missing": missing},
            ))

        # 4. Declared event types must actually be generated in a long campaign.
        observed_weather_events = {
            event for row in rows for event in row.weather_events
        }
        expected_weather_events = _declared_weather_events(self.calibrations)
        missing_weather = sorted(expected_weather_events - observed_weather_events)
        metrics.append(GenerationMetric(
            name="event_coverage:weather",
            observed=sorted(observed_weather_events),
            expected=sorted(expected_weather_events),
            passed=(not missing_weather) if self.thresholds.require_all_declared_event_types else True,
            sample_size=total,
            details={"missing": missing_weather},
        ))

        observed_operational_events = {
            event.event_type for row in rows for event in row.operational_events
        }
        missing_operational = sorted(
            DECLARED_OPERATIONAL_EVENTS - observed_operational_events
        )
        metrics.append(GenerationMetric(
            name="event_coverage:operational",
            observed=sorted(observed_operational_events),
            expected=sorted(DECLARED_OPERATIONAL_EVENTS),
            passed=(not missing_operational) if self.thresholds.require_all_declared_event_types else True,
            sample_size=total,
            details={"missing": missing_operational},
        ))

        # 5. Hierarchy integrity.
        hierarchy_violations = 0
        hierarchy_examples: list[str] = []
        for row in rows:
            expected_category = row.department.rsplit("_", 1)[0]
            expected_state = row.store.split("_", 1)[0]
            if row.category != expected_category or row.state != expected_state:
                hierarchy_violations += 1
                if len(hierarchy_examples) < 5:
                    hierarchy_examples.append(
                        f"{row.category}/{row.department};{row.state}/{row.store}"
                    )
        hierarchy_rate = hierarchy_violations / total
        metrics.append(GenerationMetric(
            name="hierarchy_integrity",
            observed=round(hierarchy_rate, 8),
            expected=f"<= {self.thresholds.maximum_hierarchy_violation_rate}",
            passed=hierarchy_rate <= self.thresholds.maximum_hierarchy_violation_rate,
            sample_size=total,
            details={"violations": hierarchy_violations, "examples": hierarchy_examples},
        ))

        # 6. Temporal coherence: contiguous dates/days and one regime per month.
        temporal_violations = 0
        examples: list[str] = []
        sorted_rows = sorted(rows, key=lambda row: row.simulation_day)
        previous: DayScenario | None = None
        monthly_regimes: dict[tuple[int, int], set[str]] = defaultdict(set)
        for row in sorted_rows:
            current_date = date.fromisoformat(row.synthetic_date)
            monthly_regimes[(current_date.year, current_date.month)].add(row.economic_regime)
            if previous is not None:
                previous_date = date.fromisoformat(previous.synthetic_date)
                if row.simulation_day != previous.simulation_day + 1 or (current_date - previous_date).days != 1:
                    temporal_violations += 1
                    if len(examples) < 5:
                        examples.append(
                            f"{previous.simulation_day}:{previous.synthetic_date} -> "
                            f"{row.simulation_day}:{row.synthetic_date}"
                        )
            previous = row
        multi_regime_months = {
            f"{year:04d}-{month:02d}": sorted(regimes)
            for (year, month), regimes in monthly_regimes.items()
            if len(regimes) != 1
        }
        temporal_violations += len(multi_regime_months)
        temporal_rate = temporal_violations / max(total, 1)
        metrics.append(GenerationMetric(
            name="temporal_coherence",
            observed=round(temporal_rate, 8),
            expected=f"<= {self.thresholds.maximum_temporal_violation_rate}",
            passed=temporal_rate <= self.thresholds.maximum_temporal_violation_rate,
            sample_size=total,
            details={
                "violations": temporal_violations,
                "examples": examples,
                "multi_regime_months": multi_regime_months,
            },
        ))

        # 7. Explicit leakage guard metadata.
        historical_count = sum(
            bool(row.metadata.get("historical_trajectory_used", False))
            for row in rows
        )
        historical_rate = historical_count / total
        metadata_contract_count = sum(
            row.metadata.get("synthetic") is True
            and row.metadata.get("historical_trajectory_used") is False
            for row in rows
        )
        metrics.append(GenerationMetric(
            name="synthetic_leakage_guard",
            observed=round(historical_rate, 8),
            expected=f"<= {self.thresholds.maximum_historical_trajectory_rate}",
            passed=(
                historical_rate <= self.thresholds.maximum_historical_trajectory_rate
                and metadata_contract_count == total
            ),
            sample_size=total,
            details={
                "historical_trajectory_rows": historical_count,
                "metadata_contract_rows": metadata_contract_count,
            },
        ))

        # 8. Reproducibility proof against an independently generated campaign.
        digest = scenario_digest(rows)
        if reproducibility_reference is None:
            reproducibility_passed = not self.thresholds.require_reproducibility_match
            reference_digest = None
        else:
            reference_rows = list(reproducibility_reference)
            reference_digest = scenario_digest(reference_rows)
            reproducibility_passed = (
                len(reference_rows) == total and reference_digest == digest
            )
        metrics.append(GenerationMetric(
            name="seed_reproducibility",
            observed=digest,
            expected=reference_digest if reference_digest is not None else "reference required",
            passed=reproducibility_passed,
            sample_size=total,
            details={"reference_supplied": reproducibility_reference is not None},
        ))

        return SyntheticGenerationReport(
            passed=all(metric.passed for metric in metrics),
            sample_size=total,
            digest=digest,
            metrics=tuple(metrics),
        )
