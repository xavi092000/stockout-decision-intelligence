from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simulation.decision_intelligence.models import (
    ConfidenceAnalysis,
    ConfidenceLevel,
    GovernanceAnalysis,
    GovernanceStatus,
    RiskAssessment,
    RiskLevel,
)


class GovernanceEngineError(RuntimeError):
    """Raised when governance evaluation cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class GovernanceConfig:
    """
    Deterministic governance thresholds.

    Governance does not select a policy. It evaluates whether the selected
    policy is eligible for automatic approval, requires human review, or
    must be rejected.
    """

    require_registered_policy: bool = True
    require_policy_approval: bool = True
    require_champion_for_auto_approval: bool = False
    allow_missing_confidence: bool = False
    reject_critical_risk: bool = True
    reject_high_model_risk: bool = False
    minimum_auto_approval_confidence: ConfidenceLevel = (
        ConfidenceLevel.HIGH
    )
    maximum_auto_approval_risk: RiskLevel = RiskLevel.MEDIUM

    def __post_init__(self) -> None:
        if not isinstance(
            self.minimum_auto_approval_confidence,
            ConfidenceLevel,
        ):
            raise TypeError(
                "minimum_auto_approval_confidence must be a "
                "ConfidenceLevel."
            )

        if not isinstance(
            self.maximum_auto_approval_risk,
            RiskLevel,
        ):
            raise TypeError(
                "maximum_auto_approval_risk must be a RiskLevel."
            )


@dataclass(frozen=True, slots=True)
class GovernanceContext:
    """
    Registry and experiment metadata available at governance time.

    This object is intentionally independent from a concrete registry
    implementation. A future adapter can populate it from the Policy
    Registry and Experiment Registry without changing the engine.
    """

    policy_name: str
    registered: bool
    policy_approved: bool
    champion: bool = False
    experiment_id: str | None = None
    model_version: str | None = None
    policy_version: str | None = None
    approval_date: str | None = None
    evaluator: str | None = None
    registry_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.policy_name.strip():
            raise ValueError("policy_name cannot be empty.")

        optional_text_fields = {
            "experiment_id": self.experiment_id,
            "model_version": self.model_version,
            "policy_version": self.policy_version,
            "approval_date": self.approval_date,
            "evaluator": self.evaluator,
            "registry_reference": self.registry_reference,
        }

        for field_name, value in optional_text_fields.items():
            if value is not None and not value.strip():
                raise ValueError(
                    f"{field_name} cannot be blank when provided."
                )

        if self.champion and not self.policy_approved:
            raise ValueError(
                "A champion policy must already be approved."
            )

        if self.policy_approved and not self.registered:
            raise ValueError(
                "An approved policy must be registered."
            )


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    """
    Internal deterministic result with explicit reasons.

    GovernanceAnalysis remains the public model attached to a decision.
    """

    status: GovernanceStatus
    approved: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved and self.status != GovernanceStatus.APPROVED:
            raise ValueError(
                "approved=True requires status=APPROVED."
            )

        if self.status == GovernanceStatus.APPROVED and not self.approved:
            raise ValueError(
                "status=APPROVED requires approved=True."
            )

        cleaned = tuple(
            reason.strip()
            for reason in self.reasons
            if reason.strip()
        )

        if cleaned != self.reasons:
            object.__setattr__(self, "reasons", cleaned)

        if not self.reasons:
            raise ValueError(
                "GovernanceDecision requires at least one reason."
            )


class GovernanceEngine:
    """
    Apply deterministic policy-governance rules.

    Evaluation priority:
    1. registry and approval requirements;
    2. critical or prohibited risk;
    3. missing or insufficient confidence;
    4. champion requirement;
    5. automatic approval.

    REJECTED is reserved for explicit governance violations or dangerous
    risk. PENDING means human review is required.
    """

    _CONFIDENCE_ORDER = {
        ConfidenceLevel.VERY_LOW: 0,
        ConfidenceLevel.LOW: 1,
        ConfidenceLevel.MEDIUM: 2,
        ConfidenceLevel.HIGH: 3,
        ConfidenceLevel.VERY_HIGH: 4,
    }

    _RISK_ORDER = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }

    def __init__(
        self,
        config: GovernanceConfig | None = None,
    ) -> None:
        self.config = config or GovernanceConfig()

    def evaluate(
        self,
        *,
        context: GovernanceContext,
        confidence: ConfidenceAnalysis | None,
        risk: RiskAssessment,
    ) -> GovernanceAnalysis:
        decision = self._decide(
            context=context,
            confidence=confidence,
            risk=risk,
        )

        return GovernanceAnalysis(
            status=decision.status,
            experiment_id=context.experiment_id,
            model_version=context.model_version,
            policy_version=context.policy_version,
            champion=(
                context.champion
                and decision.approved
            ),
            approved=decision.approved,
            approval_date=(
                context.approval_date
                if decision.approved
                else None
            ),
            evaluator=context.evaluator,
            registry_reference=context.registry_reference,
        )

    def decide(
        self,
        *,
        context: GovernanceContext,
        confidence: ConfidenceAnalysis | None,
        risk: RiskAssessment,
    ) -> GovernanceDecision:
        """
        Return the detailed governance result, including reasons.
        """

        return self._decide(
            context=context,
            confidence=confidence,
            risk=risk,
        )

    def _decide(
        self,
        *,
        context: GovernanceContext,
        confidence: ConfidenceAnalysis | None,
        risk: RiskAssessment,
    ) -> GovernanceDecision:
        self._validate_inputs(
            context=context,
            confidence=confidence,
            risk=risk,
        )

        rejection_reasons: list[str] = []
        pending_reasons: list[str] = []

        if (
            self.config.require_registered_policy
            and not context.registered
        ):
            rejection_reasons.append(
                "The selected policy is not registered."
            )

        if (
            self.config.require_policy_approval
            and not context.policy_approved
        ):
            pending_reasons.append(
                "The selected policy has not received registry approval."
            )

        if (
            self.config.reject_critical_risk
            and risk.overall_risk == RiskLevel.CRITICAL
        ):
            rejection_reasons.append(
                "Overall decision risk is CRITICAL."
            )

        if (
            self.config.reject_high_model_risk
            and risk.model_risk
            in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        ):
            rejection_reasons.append(
                "Model risk exceeds the permitted governance level."
            )

        maximum_risk_rank = self._RISK_ORDER[
            self.config.maximum_auto_approval_risk
        ]
        current_risk_rank = self._RISK_ORDER[
            risk.overall_risk
        ]

        if current_risk_rank > maximum_risk_rank:
            pending_reasons.append(
                "Overall risk exceeds the automatic-approval threshold."
            )

        if confidence is None:
            if not self.config.allow_missing_confidence:
                pending_reasons.append(
                    "Confidence analysis is unavailable."
                )
        else:
            required_confidence_rank = self._CONFIDENCE_ORDER[
                self.config.minimum_auto_approval_confidence
            ]
            current_confidence_rank = self._CONFIDENCE_ORDER[
                confidence.confidence_level
            ]

            if current_confidence_rank < required_confidence_rank:
                pending_reasons.append(
                    "Decision confidence is below the "
                    "automatic-approval threshold."
                )

        if (
            self.config.require_champion_for_auto_approval
            and not context.champion
        ):
            pending_reasons.append(
                "Only the production champion may be "
                "automatically approved."
            )

        if rejection_reasons:
            return GovernanceDecision(
                status=GovernanceStatus.REJECTED,
                approved=False,
                reasons=tuple(rejection_reasons),
            )

        if pending_reasons:
            return GovernanceDecision(
                status=GovernanceStatus.PENDING,
                approved=False,
                reasons=tuple(pending_reasons),
            )

        return GovernanceDecision(
            status=GovernanceStatus.APPROVED,
            approved=True,
            reasons=(
                "The policy satisfies all automatic-governance rules.",
            ),
        )

    @staticmethod
    def _validate_inputs(
        *,
        context: GovernanceContext,
        confidence: ConfidenceAnalysis | None,
        risk: RiskAssessment,
    ) -> None:
        if not isinstance(context, GovernanceContext):
            raise GovernanceEngineError(
                "context must be a GovernanceContext."
            )

        if (
            confidence is not None
            and not isinstance(confidence, ConfidenceAnalysis)
        ):
            raise GovernanceEngineError(
                "confidence must be a ConfidenceAnalysis or None."
            )

        if not isinstance(risk, RiskAssessment):
            raise GovernanceEngineError(
                "risk must be a RiskAssessment."
            )


def governance_context_from_mapping(
    payload: dict[str, Any],
) -> GovernanceContext:
    """
    Build a validated GovernanceContext from registry-style metadata.
    """

    if not isinstance(payload, dict):
        raise TypeError("payload must be a dictionary.")

    try:
        return GovernanceContext(
            policy_name=str(payload["policy_name"]),
            registered=bool(payload["registered"]),
            policy_approved=bool(payload["policy_approved"]),
            champion=bool(payload.get("champion", False)),
            experiment_id=_optional_text(
                payload.get("experiment_id")
            ),
            model_version=_optional_text(
                payload.get("model_version")
            ),
            policy_version=_optional_text(
                payload.get("policy_version")
            ),
            approval_date=_optional_text(
                payload.get("approval_date")
            ),
            evaluator=_optional_text(
                payload.get("evaluator")
            ),
            registry_reference=_optional_text(
                payload.get("registry_reference")
            ),
        )
    except KeyError as error:
        raise ValueError(
            f"Missing governance context field: {error.args[0]}"
        ) from error


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)

