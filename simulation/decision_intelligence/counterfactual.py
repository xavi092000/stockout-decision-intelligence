from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Protocol, Sequence

from simulation.decision_intelligence.models import (
    CounterfactualAnalysis,
    CounterfactualOutcome,
)


class CounterfactualEngineError(RuntimeError):
    """Raised when counterfactual evaluation cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    """
    Estimated economic and operational outcome for one policy.

    Values must come from an injected evaluator. The counterfactual engine
    compares outcomes but does not duplicate the economic engine.
    """

    policy_name: str
    business_value: float
    service_level: float
    total_cost: float
    stockouts: float

    def __post_init__(self) -> None:
        if not self.policy_name.strip():
            raise ValueError("policy_name cannot be empty.")

        numeric_values = {
            "business_value": self.business_value,
            "service_level": self.service_level,
            "total_cost": self.total_cost,
            "stockouts": self.stockouts,
        }

        for field_name, value in numeric_values.items():
            if not isfinite(float(value)):
                raise ValueError(
                    f"{field_name} must be finite."
                )

        if not 0.0 <= self.service_level <= 1.0:
            raise ValueError(
                "service_level must be between 0.0 and 1.0."
            )

        if self.total_cost < 0.0:
            raise ValueError("total_cost cannot be negative.")

        if self.stockouts < 0.0:
            raise ValueError("stockouts cannot be negative.")


class PolicyOutcomeEvaluator(Protocol):
    """
    Contract implemented by any component capable of estimating a policy.

    Production adapters may use closed-loop simulation, an economic model,
    or validated experiment results. They must not use unavailable future
    information as decision-time input.
    """

    def evaluate(
        self,
        *,
        snapshot: Any,
        policy_name: str,
    ) -> PolicyOutcome:
        ...


class MappingPolicyOutcomeEvaluator:
    """
    Deterministic evaluator backed by precomputed policy outcomes.

    Useful for unit tests, experiment results, benchmark outputs, and
    validated estimates supplied by another platform component.
    """

    def __init__(
        self,
        outcomes: dict[str, PolicyOutcome | dict[str, Any]],
    ) -> None:
        if not outcomes:
            raise ValueError("outcomes cannot be empty.")

        normalized: dict[str, PolicyOutcome] = {}

        for raw_name, raw_outcome in outcomes.items():
            policy_name = str(raw_name).strip()

            if not policy_name:
                raise ValueError(
                    "Outcome policy names cannot be empty."
                )

            if isinstance(raw_outcome, PolicyOutcome):
                outcome = raw_outcome
            elif isinstance(raw_outcome, dict):
                try:
                    outcome = PolicyOutcome(
                        policy_name=policy_name,
                        business_value=float(
                            raw_outcome["business_value"]
                        ),
                        service_level=float(
                            raw_outcome["service_level"]
                        ),
                        total_cost=float(
                            raw_outcome["total_cost"]
                        ),
                        stockouts=float(
                            raw_outcome["stockouts"]
                        ),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"Invalid outcome for policy {policy_name}: "
                        f"{error}"
                    ) from error
            else:
                raise TypeError(
                    "Each outcome must be a PolicyOutcome or dictionary."
                )

            if outcome.policy_name != policy_name:
                raise ValueError(
                    "Outcome policy_name must match its mapping key."
                )

            normalized[policy_name] = outcome

        self._outcomes = normalized

    def evaluate(
        self,
        *,
        snapshot: Any,
        policy_name: str,
    ) -> PolicyOutcome:
        del snapshot

        clean_name = str(policy_name).strip()

        try:
            return self._outcomes[clean_name]
        except KeyError as error:
            raise CounterfactualEngineError(
                f"No outcome available for policy: {clean_name}"
            ) from error


class CounterfactualEngine:
    """
    Compare the chosen policy with rejected policies.

    Delta convention:
    - business_value_delta = alternative - chosen
    - service_level_delta = alternative - chosen
    - cost_delta = alternative - chosen
    - stockout_delta = alternative - chosen

    Therefore:
    - positive business value delta favors the alternative;
    - positive service delta favors the alternative;
    - negative cost delta favors the alternative;
    - negative stockout delta favors the alternative.
    """

    def __init__(
        self,
        evaluator: PolicyOutcomeEvaluator,
    ) -> None:
        self.evaluator = evaluator

    def analyze(
        self,
        *,
        snapshot: Any,
        chosen_policy: str,
        alternative_policies: Sequence[str],
    ) -> CounterfactualAnalysis:
        chosen_name = str(chosen_policy).strip()

        if not chosen_name:
            raise CounterfactualEngineError(
                "chosen_policy cannot be empty."
            )

        cleaned_alternatives = self._clean_alternatives(
            chosen_policy=chosen_name,
            alternative_policies=alternative_policies,
        )

        try:
            chosen_outcome = self.evaluator.evaluate(
                snapshot=snapshot,
                policy_name=chosen_name,
            )
        except Exception as error:
            if isinstance(error, CounterfactualEngineError):
                raise
            raise CounterfactualEngineError(
                "Chosen policy evaluation failed: "
                f"{error}"
            ) from error

        if chosen_outcome.policy_name != chosen_name:
            raise CounterfactualEngineError(
                "Evaluator returned the wrong chosen policy."
            )

        outcomes: list[CounterfactualOutcome] = []

        for policy_name in cleaned_alternatives:
            try:
                alternative = self.evaluator.evaluate(
                    snapshot=snapshot,
                    policy_name=policy_name,
                )
            except Exception as error:
                if isinstance(error, CounterfactualEngineError):
                    raise
                raise CounterfactualEngineError(
                    f"Alternative policy evaluation failed for "
                    f"{policy_name}: {error}"
                ) from error

            if alternative.policy_name != policy_name:
                raise CounterfactualEngineError(
                    "Evaluator returned the wrong alternative policy."
                )

            business_delta = (
                alternative.business_value
                - chosen_outcome.business_value
            )
            service_delta = (
                alternative.service_level
                - chosen_outcome.service_level
            )
            cost_delta = (
                alternative.total_cost
                - chosen_outcome.total_cost
            )
            stockout_delta = (
                alternative.stockouts
                - chosen_outcome.stockouts
            )

            outcomes.append(
                CounterfactualOutcome(
                    policy_name=policy_name,
                    business_value_delta=round(
                        business_delta,
                        6,
                    ),
                    service_level_delta=round(
                        service_delta,
                        6,
                    ),
                    cost_delta=round(
                        cost_delta,
                        6,
                    ),
                    stockout_delta=round(
                        stockout_delta,
                        6,
                    ),
                    explanation=self._outcome_explanation(
                        policy_name=policy_name,
                        business_value_delta=business_delta,
                        service_level_delta=service_delta,
                        cost_delta=cost_delta,
                        stockout_delta=stockout_delta,
                    ),
                )
            )

        best_outcome = max(
            outcomes,
            key=lambda item: item.business_value_delta,
            default=None,
        )

        best_alternative = (
            best_outcome.policy_name
            if best_outcome is not None
            else None
        )

        opportunity_cost = max(
            0.0,
            (
                best_outcome.business_value_delta
                if best_outcome is not None
                else 0.0
            ),
        )

        return CounterfactualAnalysis(
            chosen_policy=chosen_name,
            alternatives=tuple(outcomes),
            best_alternative=best_alternative,
            opportunity_cost=round(
                opportunity_cost,
                6,
            ),
            explanation=self._analysis_explanation(
                chosen_policy=chosen_name,
                best_alternative=best_alternative,
                opportunity_cost=opportunity_cost,
                alternative_count=len(outcomes),
            ),
        )

    @staticmethod
    def _clean_alternatives(
        *,
        chosen_policy: str,
        alternative_policies: Sequence[str],
    ) -> tuple[str, ...]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for raw_name in alternative_policies:
            policy_name = str(raw_name).strip()

            if not policy_name:
                raise CounterfactualEngineError(
                    "Alternative policy names cannot be empty."
                )

            if policy_name == chosen_policy:
                raise CounterfactualEngineError(
                    "The chosen policy cannot also be an alternative."
                )

            if policy_name in seen:
                raise CounterfactualEngineError(
                    "Alternative policies must be unique."
                )

            seen.add(policy_name)
            cleaned.append(policy_name)

        return tuple(cleaned)

    @staticmethod
    def _outcome_explanation(
        *,
        policy_name: str,
        business_value_delta: float,
        service_level_delta: float,
        cost_delta: float,
        stockout_delta: float,
    ) -> str:
        value_direction = (
            "higher"
            if business_value_delta > 0
            else "lower"
            if business_value_delta < 0
            else "equal"
        )

        return (
            f"Compared with the chosen policy, {policy_name} has "
            f"{value_direction} estimated business value "
            f"({business_value_delta:+.2f}), a service-level delta of "
            f"{service_level_delta:+.4f}, a total-cost delta of "
            f"{cost_delta:+.2f}, and a stockout delta of "
            f"{stockout_delta:+.2f}."
        )

    @staticmethod
    def _analysis_explanation(
        *,
        chosen_policy: str,
        best_alternative: str | None,
        opportunity_cost: float,
        alternative_count: int,
    ) -> str:
        if alternative_count == 0:
            return (
                f"No rejected policy was supplied for comparison with "
                f"{chosen_policy}."
            )

        if opportunity_cost > 0.0:
            return (
                f"{best_alternative} is the strongest rejected policy by "
                f"estimated business value. Selecting {chosen_policy} "
                f"has an estimated opportunity cost of "
                f"{opportunity_cost:.2f}."
            )

        return (
            f"No rejected policy produced greater estimated business "
            f"value than {chosen_policy}. The best rejected policy was "
            f"{best_alternative}, with zero positive opportunity cost."
        )
