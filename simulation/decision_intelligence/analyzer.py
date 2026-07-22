from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from simulation.decision_intelligence.confidence import (
    ConfidenceEngine,
)
from simulation.decision_intelligence.counterfactual import (
    CounterfactualEngine,
)
from simulation.decision_intelligence.governance import (
    GovernanceContext,
    GovernanceEngine,
)
from simulation.decision_intelligence.models import (
    AlternativePolicy,
    DecisionAnalysis,
    DecisionMetadata,
    DecisionTrace,
)
from simulation.decision_intelligence.risk import (
    RiskEngine,
)


class PolicyPredictionAdapter(Protocol):
    def predict_with_details(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        ...


class MLDecisionAnalyzerError(RuntimeError):
    """Raised when an ML decision cannot be analyzed safely."""


class MLDecisionAnalyzerV2:
    """
    Build a DecisionAnalysis from one leakage-safe snapshot.

    The analyzer enriches an ML policy prediction with confidence, risk,
    rejected alternatives, counterfactual estimates, trace metadata, and
    validation. It does not mutate the simulation.
    """

    def __init__(
        self,
        adapter: PolicyPredictionAdapter,
        confidence_engine: ConfidenceEngine | None = None,
        risk_engine: RiskEngine | None = None,
        counterfactual_engine: CounterfactualEngine | None = None,
        governance_engine: GovernanceEngine | None = None,
    ) -> None:
        self.adapter = adapter
        self.confidence_engine = (
            confidence_engine or ConfidenceEngine()
        )
        self.risk_engine = (
            risk_engine or RiskEngine()
        )
        self.counterfactual_engine = counterfactual_engine
        self.governance_engine = governance_engine

    def analyze(
        self,
        *,
        snapshot: Any,
        simulation_day: int,
        snapshot_id: str,
        episode_seed: int,
        decision_id: str | None = None,
        reason: str | None = None,
        governance_context: GovernanceContext | None = None,
    ) -> DecisionAnalysis:
        prediction = self.adapter.predict_with_details(snapshot)

        if not isinstance(prediction, dict):
            raise MLDecisionAnalyzerError(
                "The policy adapter must return a dictionary."
            )

        selected_policy = str(
            prediction.get("policy", "")
        ).strip()

        if not selected_policy:
            raise MLDecisionAnalyzerError(
                "The policy adapter returned an empty policy."
            )

        latency_ms = self._non_negative_float(
            prediction.get("latency_ms", 0.0),
            "latency_ms",
        )

        feature_count = self._non_negative_int(
            prediction.get("feature_count", 0),
            "feature_count",
        )

        raw_probabilities = prediction.get("probabilities")
        confidence = None
        alternatives: tuple[AlternativePolicy, ...] = ()

        if raw_probabilities is not None:
            if not isinstance(raw_probabilities, dict):
                raise MLDecisionAnalyzerError(
                    "probabilities must be a dictionary or None."
                )

            try:
                confidence = self.confidence_engine.analyze(
                    probabilities=raw_probabilities,
                    selected_policy=selected_policy,
                )
            except ValueError as error:
                raise MLDecisionAnalyzerError(
                    f"Confidence analysis failed: {error}"
                ) from error

            ranked = sorted(
                (
                    (
                        str(policy_name).strip(),
                        float(probability),
                    )
                    for policy_name, probability
                    in raw_probabilities.items()
                    if str(policy_name).strip()
                    != selected_policy
                ),
                key=lambda item: item[1],
                reverse=True,
            )

            alternatives = tuple(
                AlternativePolicy(
                    policy_name=policy_name,
                    rank=index + 2,
                    probability=probability,
                )
                for index, (
                    policy_name,
                    probability,
                ) in enumerate(ranked)
            )

        snapshot_payload = self._snapshot_payload(snapshot)

        try:
            risk = self.risk_engine.assess(
                snapshot=snapshot_payload,
                selected_policy=selected_policy,
                confidence=confidence,
                feature_count=feature_count,
                probabilities_available=(
                    raw_probabilities is not None
                ),
            )
        except ValueError as error:
            raise MLDecisionAnalyzerError(
                f"Risk analysis failed: {error}"
            ) from error

        counterfactual = None

        if self.counterfactual_engine is not None:
            try:
                counterfactual = (
                    self.counterfactual_engine.analyze(
                        snapshot=snapshot,
                        chosen_policy=selected_policy,
                        alternative_policies=tuple(
                            item.policy_name
                            for item in alternatives
                        ),
                    )
                )
            except Exception as error:
                raise MLDecisionAnalyzerError(
                    f"Counterfactual analysis failed: {error}"
                ) from error

        governance = None

        if self.governance_engine is not None:
            if governance_context is None:
                raise MLDecisionAnalyzerError(
                    "governance_context is required when a "
                    "GovernanceEngine is configured."
                )

            if governance_context.policy_name != selected_policy:
                raise MLDecisionAnalyzerError(
                    "Governance context policy does not match the "
                    "selected policy."
                )

            try:
                governance = self.governance_engine.evaluate(
                    context=governance_context,
                    confidence=confidence,
                    risk=risk,
                )
            except Exception as error:
                raise MLDecisionAnalyzerError(
                    f"Governance analysis failed: {error}"
                ) from error

        elif governance_context is not None:
            raise MLDecisionAnalyzerError(
                "A governance_context was supplied without a "
                "GovernanceEngine."
            )

        resolved_reason = (
            reason.strip()
            if reason is not None and reason.strip()
            else (
                "ML policy selected from the current leakage-safe "
                "pre-decision snapshot."
            )
        )

        metadata = DecisionMetadata(
            decision_id=(
                decision_id.strip()
                if decision_id is not None
                and decision_id.strip()
                else f"decision-{uuid4()}"
            ),
            simulation_day=simulation_day,
            snapshot_id=snapshot_id,
            episode_seed=episode_seed,
        )

        trace = DecisionTrace(
            selected_policy=selected_policy,
            reason=resolved_reason,
            source="ML_POLICY_ADAPTER_V2",
            feature_count=feature_count,
            latency_ms=latency_ms,
            input_snapshot=snapshot_payload,
        )

        tags = [
            "ml-policy",
            "leakage-safe",
            "risk-analyzed",
        ]

        if confidence is not None:
            tags.append("confidence-analyzed")
        else:
            tags.append("confidence-unavailable")

        if counterfactual is not None:
            tags.append("counterfactual-analyzed")

        if governance is not None:
            tags.append("governance-analyzed")
            tags.append(
                f"governance-{governance.status.value.lower()}"
            )

        return DecisionAnalysis(
            metadata=metadata,
            trace=trace,
            confidence=confidence,
            risk=risk,
            alternatives=alternatives,
            counterfactual=counterfactual,
            governance=governance,
            tags=tuple(tags),
        )

    @staticmethod
    def _snapshot_payload(
        snapshot: Any,
    ) -> dict[str, Any]:
        if isinstance(snapshot, dict):
            return dict(snapshot)

        to_dict = getattr(snapshot, "to_dict", None)

        if callable(to_dict):
            payload = to_dict()

            if not isinstance(payload, dict):
                raise MLDecisionAnalyzerError(
                    "snapshot.to_dict() must return a dictionary."
                )

            return dict(payload)

        raw_values = getattr(snapshot, "__dict__", None)

        if isinstance(raw_values, dict):
            return dict(raw_values)

        raise MLDecisionAnalyzerError(
            "snapshot must be a dictionary or expose to_dict()."
        )

    @staticmethod
    def _non_negative_float(
        value: Any,
        field_name: str,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise MLDecisionAnalyzerError(
                f"{field_name} must be numeric."
            ) from error

        if number < 0:
            raise MLDecisionAnalyzerError(
                f"{field_name} cannot be negative."
            )

        return number

    @staticmethod
    def _non_negative_int(
        value: Any,
        field_name: str,
    ) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as error:
            raise MLDecisionAnalyzerError(
                f"{field_name} must be an integer."
            ) from error

        if number < 0:
            raise MLDecisionAnalyzerError(
                f"{field_name} cannot be negative."
            )

        return number


