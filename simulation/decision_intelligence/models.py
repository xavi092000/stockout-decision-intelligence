from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from typing import Any


class ConfidenceLevel(StrEnum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GovernanceStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _validate_probability(
    value: float,
    field_name: str,
) -> None:
    if not isfinite(value):
        raise ValueError(
            f"{field_name} must be finite. Received: {value}"
        )

    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"{field_name} must be between 0.0 and 1.0. "
            f"Received: {value}"
        )


def _validate_finite_number(
    value: float,
    field_name: str,
) -> None:
    if not isfinite(value):
        raise ValueError(
            f"{field_name} must be finite. Received: {value}"
        )


@dataclass(frozen=True, slots=True)
class ConfidenceAnalysis:
    predicted_probability: float
    second_best_probability: float
    probability_margin: float
    normalized_entropy: float
    confidence_score: float
    confidence_level: ConfidenceLevel
    explanation: str
    predicted_policy: str | None = None
    second_best_policy: str | None = None

    def __post_init__(self) -> None:
        _validate_probability(
            self.predicted_probability,
            "predicted_probability",
        )
        _validate_probability(
            self.second_best_probability,
            "second_best_probability",
        )
        _validate_probability(
            self.probability_margin,
            "probability_margin",
        )
        _validate_probability(
            self.normalized_entropy,
            "normalized_entropy",
        )
        _validate_probability(
            self.confidence_score,
            "confidence_score",
        )

        expected_margin = (
            self.predicted_probability
            - self.second_best_probability
        )

        if abs(self.probability_margin - expected_margin) > 1e-6:
            raise ValueError(
                "probability_margin must equal "
                "predicted_probability - second_best_probability."
            )

        if not self.explanation.strip():
            raise ValueError(
                "Confidence explanation cannot be empty."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    operational_risk: RiskLevel
    economic_risk: RiskLevel
    model_risk: RiskLevel
    data_quality_risk: RiskLevel
    overall_risk: RiskLevel
    reasons: tuple[str, ...] = field(default_factory=tuple)
    risk_score: float | None = None

    def __post_init__(self) -> None:
        if self.risk_score is not None:
            _validate_probability(
                self.risk_score,
                "risk_score",
            )

        cleaned_reasons = tuple(
            reason.strip()
            for reason in self.reasons
            if reason.strip()
        )

        if cleaned_reasons != self.reasons:
            object.__setattr__(
                self,
                "reasons",
                cleaned_reasons,
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AlternativePolicy:
    policy_name: str
    rank: int
    expected_business_value: float | None = None
    expected_service_level: float | None = None
    expected_cost: float | None = None
    expected_stockouts: float | None = None
    probability: float | None = None

    def __post_init__(self) -> None:
        if not self.policy_name.strip():
            raise ValueError(
                "policy_name cannot be empty."
            )

        if self.rank < 1:
            raise ValueError(
                "rank must be greater than or equal to 1."
            )

        if self.expected_business_value is not None:
            _validate_finite_number(
                self.expected_business_value,
                "expected_business_value",
            )

        if self.expected_service_level is not None:
            _validate_probability(
                self.expected_service_level,
                "expected_service_level",
            )

        if self.expected_cost is not None:
            _validate_finite_number(
                self.expected_cost,
                "expected_cost",
            )

        if self.expected_stockouts is not None:
            _validate_finite_number(
                self.expected_stockouts,
                "expected_stockouts",
            )

        if self.probability is not None:
            _validate_probability(
                self.probability,
                "probability",
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CounterfactualOutcome:
    policy_name: str
    business_value_delta: float
    service_level_delta: float
    cost_delta: float
    stockout_delta: float
    explanation: str

    def __post_init__(self) -> None:
        if not self.policy_name.strip():
            raise ValueError(
                "policy_name cannot be empty."
            )

        _validate_finite_number(
            self.business_value_delta,
            "business_value_delta",
        )
        _validate_finite_number(
            self.service_level_delta,
            "service_level_delta",
        )
        _validate_finite_number(
            self.cost_delta,
            "cost_delta",
        )
        _validate_finite_number(
            self.stockout_delta,
            "stockout_delta",
        )

        if not self.explanation.strip():
            raise ValueError(
                "Counterfactual explanation cannot be empty."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CounterfactualAnalysis:
    chosen_policy: str
    alternatives: tuple[CounterfactualOutcome, ...]
    best_alternative: str | None
    opportunity_cost: float
    explanation: str

    def __post_init__(self) -> None:
        if not self.chosen_policy.strip():
            raise ValueError(
                "chosen_policy cannot be empty."
            )

        _validate_finite_number(
            self.opportunity_cost,
            "opportunity_cost",
        )

        if not self.explanation.strip():
            raise ValueError(
                "Counterfactual explanation cannot be empty."
            )

        alternative_names = {
            item.policy_name
            for item in self.alternatives
        }

        if (
            self.best_alternative is not None
            and self.best_alternative not in alternative_names
        ):
            raise ValueError(
                "best_alternative must be present in alternatives."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GovernanceAnalysis:
    status: GovernanceStatus
    experiment_id: str | None = None
    model_version: str | None = None
    policy_version: str | None = None
    champion: bool = False
    approved: bool = False
    approval_date: str | None = None
    evaluator: str | None = None
    registry_reference: str | None = None

    def __post_init__(self) -> None:
        if self.approved and self.status != GovernanceStatus.APPROVED:
            raise ValueError(
                "approved=True requires status=APPROVED."
            )

        if self.champion and not self.approved:
            raise ValueError(
                "A champion policy must be approved."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutiveRecommendation:
    headline: str
    recommendation: str
    rationale: str
    expected_value: float | None
    risks: tuple[str, ...]
    confidence_summary: str
    next_action: str
    recommendation_status: str = "INFORMATIONAL"

    def __post_init__(self) -> None:
        required_fields = {
            "headline": self.headline,
            "recommendation": self.recommendation,
            "rationale": self.rationale,
            "confidence_summary": self.confidence_summary,
            "next_action": self.next_action,
        }

        for field_name, value in required_fields.items():
            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty."
                )

        if self.expected_value is not None:
            _validate_finite_number(
                self.expected_value,
                "expected_value",
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DecisionMetadata:
    decision_id: str
    simulation_day: int
    snapshot_id: str
    episode_seed: int
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError(
                "decision_id cannot be empty."
            )

        if not self.snapshot_id.strip():
            raise ValueError(
                "snapshot_id cannot be empty."
            )

        if self.simulation_day < 1:
            raise ValueError(
                "simulation_day must be greater than or equal to 1."
            )

        if not self.schema_version.strip():
            raise ValueError(
                "schema_version cannot be empty."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    selected_policy: str
    reason: str
    source: str
    feature_count: int
    latency_ms: float
    input_snapshot: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.selected_policy.strip():
            raise ValueError(
                "selected_policy cannot be empty."
            )

        if not self.reason.strip():
            raise ValueError(
                "reason cannot be empty."
            )

        if not self.source.strip():
            raise ValueError(
                "source cannot be empty."
            )

        if self.feature_count < 0:
            raise ValueError(
                "feature_count cannot be negative."
            )

        if self.latency_ms < 0:
            raise ValueError(
                "latency_ms cannot be negative."
            )

        _validate_finite_number(
            self.latency_ms,
            "latency_ms",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DecisionAnalysis:
    metadata: DecisionMetadata
    trace: DecisionTrace
    confidence: ConfidenceAnalysis | None = None
    risk: RiskAssessment | None = None
    alternatives: tuple[AlternativePolicy, ...] = field(
        default_factory=tuple
    )
    counterfactual: CounterfactualAnalysis | None = None
    governance: GovernanceAnalysis | None = None
    executive: ExecutiveRecommendation | None = None
    expected_business_value: float | None = None
    expected_service_level: float | None = None
    expected_cost: float | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.expected_business_value is not None:
            _validate_finite_number(
                self.expected_business_value,
                "expected_business_value",
            )

        if self.expected_service_level is not None:
            _validate_probability(
                self.expected_service_level,
                "expected_service_level",
            )

        if self.expected_cost is not None:
            _validate_finite_number(
                self.expected_cost,
                "expected_cost",
            )

        alternative_names = [
            item.policy_name
            for item in self.alternatives
        ]

        if len(alternative_names) != len(set(alternative_names)):
            raise ValueError(
                "Alternative policies must be unique."
            )

        if self.trace.selected_policy in alternative_names:
            raise ValueError(
                "The selected policy cannot also be an alternative."
            )

    @property
    def selected_policy(self) -> str:
        return self.trace.selected_policy

    @property
    def decision_id(self) -> str:
        return self.metadata.decision_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)