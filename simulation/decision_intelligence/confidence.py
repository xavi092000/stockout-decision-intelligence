from __future__ import annotations

from math import isfinite, log
from typing import Mapping

from simulation.decision_intelligence.models import (
    ConfidenceAnalysis,
    ConfidenceLevel,
)


class ConfidenceEngineError(ValueError):
    """Raised when prediction probabilities cannot be analyzed."""


class ConfidenceEngine:
    """
    Converts policy probabilities into a confidence analysis.

    Confidence combines:
    - top predicted probability;
    - probability margin over the second-best policy;
    - inverse normalized entropy.
    """

    def analyze(
        self,
        probabilities: Mapping[str, float],
        selected_policy: str | None = None,
    ) -> ConfidenceAnalysis:
        normalized_probabilities = self._validate_and_normalize(
            probabilities
        )

        ranked = sorted(
            normalized_probabilities.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        predicted_policy, predicted_probability = ranked[0]

        if selected_policy is not None:
            selected_policy = selected_policy.strip()

            if not selected_policy:
                raise ConfidenceEngineError(
                    "selected_policy cannot be empty."
                )

            if selected_policy not in normalized_probabilities:
                raise ConfidenceEngineError(
                    "selected_policy is absent from probabilities: "
                    f"{selected_policy}"
                )

            if selected_policy != predicted_policy:
                raise ConfidenceEngineError(
                    "selected_policy does not match the policy with "
                    "the highest probability. "
                    f"Selected={selected_policy}, "
                    f"Predicted={predicted_policy}"
                )

        second_best_policy: str | None = None
        second_best_probability = 0.0

        if len(ranked) > 1:
            second_best_policy = ranked[1][0]
            second_best_probability = ranked[1][1]

        probability_margin = (
            predicted_probability - second_best_probability
        )

        normalized_entropy = self._normalized_entropy(
            tuple(normalized_probabilities.values())
        )

        confidence_score = self._confidence_score(
            predicted_probability=predicted_probability,
            probability_margin=probability_margin,
            normalized_entropy=normalized_entropy,
        )

        confidence_level = self._confidence_level(
            confidence_score
        )

        explanation = self._build_explanation(
            predicted_policy=predicted_policy,
            predicted_probability=predicted_probability,
            second_best_policy=second_best_policy,
            probability_margin=probability_margin,
            normalized_entropy=normalized_entropy,
            confidence_level=confidence_level,
        )

        rounded_predicted_probability = round(
            predicted_probability,
            6,
        )
        rounded_second_best_probability = round(
            second_best_probability,
            6,
        )
        rounded_probability_margin = round(
            rounded_predicted_probability
            - rounded_second_best_probability,
            6,
        )

        return ConfidenceAnalysis(
            predicted_probability=(
                rounded_predicted_probability
            ),
            second_best_probability=(
                rounded_second_best_probability
            ),
            probability_margin=rounded_probability_margin,
            normalized_entropy=round(
                normalized_entropy,
                6,
            ),
            confidence_score=round(
                confidence_score,
                6,
            ),
            confidence_level=confidence_level,
            explanation=explanation,
            predicted_policy=predicted_policy,
            second_best_policy=second_best_policy,
        )

    @staticmethod
    def _validate_and_normalize(
        probabilities: Mapping[str, float],
    ) -> dict[str, float]:
        if not probabilities:
            raise ConfidenceEngineError(
                "probabilities cannot be empty."
            )

        cleaned: dict[str, float] = {}

        for policy_name, probability in probabilities.items():
            clean_name = str(policy_name).strip()

            if not clean_name:
                raise ConfidenceEngineError(
                    "Probability policy names cannot be empty."
                )

            try:
                numeric_probability = float(probability)
            except (TypeError, ValueError) as error:
                raise ConfidenceEngineError(
                    "Probability values must be numeric. "
                    f"Received {probability!r} for {clean_name}."
                ) from error

            if not isfinite(numeric_probability):
                raise ConfidenceEngineError(
                    "Probability values must be finite. "
                    f"Received {numeric_probability} for {clean_name}."
                )

            if not 0.0 <= numeric_probability <= 1.0:
                raise ConfidenceEngineError(
                    "Each probability must be between 0.0 and 1.0. "
                    f"Received {numeric_probability} for {clean_name}."
                )

            if clean_name in cleaned:
                raise ConfidenceEngineError(
                    f"Duplicate policy name: {clean_name}"
                )

            cleaned[clean_name] = numeric_probability

        total = sum(cleaned.values())

        if total <= 0.0:
            raise ConfidenceEngineError(
                "The sum of probabilities must be greater than zero."
            )

        if abs(total - 1.0) > 0.05:
            raise ConfidenceEngineError(
                "Probabilities must sum approximately to 1.0. "
                f"Received total={total:.6f}."
            )

        return {
            policy_name: probability / total
            for policy_name, probability in cleaned.items()
        }

    @staticmethod
    def _normalized_entropy(
        probabilities: tuple[float, ...],
    ) -> float:
        if len(probabilities) <= 1:
            return 0.0

        entropy = -sum(
            probability * log(probability)
            for probability in probabilities
            if probability > 0.0
        )

        maximum_entropy = log(len(probabilities))

        if maximum_entropy <= 0.0:
            return 0.0

        return min(
            max(entropy / maximum_entropy, 0.0),
            1.0,
        )

    @staticmethod
    def _confidence_score(
        predicted_probability: float,
        probability_margin: float,
        normalized_entropy: float,
    ) -> float:
        score = (
            0.45 * predicted_probability
            + 0.35 * probability_margin
            + 0.20 * (1.0 - normalized_entropy)
        )

        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _confidence_level(
        confidence_score: float,
    ) -> ConfidenceLevel:
        if confidence_score >= 0.85:
            return ConfidenceLevel.VERY_HIGH

        if confidence_score >= 0.70:
            return ConfidenceLevel.HIGH

        if confidence_score >= 0.50:
            return ConfidenceLevel.MEDIUM

        if confidence_score >= 0.30:
            return ConfidenceLevel.LOW

        return ConfidenceLevel.VERY_LOW

    @staticmethod
    def _build_explanation(
        predicted_policy: str,
        predicted_probability: float,
        second_best_policy: str | None,
        probability_margin: float,
        normalized_entropy: float,
        confidence_level: ConfidenceLevel,
    ) -> str:
        if second_best_policy is None:
            comparison = (
                "No competing policy probability was provided."
            )
        else:
            comparison = (
                f"The leading policy exceeds {second_best_policy} "
                f"by {probability_margin:.1%}."
            )

        return (
            f"{predicted_policy} is selected with "
            f"{predicted_probability:.1%} probability. "
            f"{comparison} "
            f"Distribution uncertainty is "
            f"{normalized_entropy:.1%}. "
            f"Overall confidence is {confidence_level.value}."
        )

