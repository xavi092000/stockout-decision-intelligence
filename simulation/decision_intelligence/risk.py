from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

from simulation.decision_intelligence.models import (
    ConfidenceAnalysis,
    RiskAssessment,
    RiskLevel,
)


class RiskEngineError(ValueError):
    """Raised when decision risk cannot be calculated safely."""


class RiskEngine:
    """
    Leakage-safe decision risk evaluator.

    The engine uses only the current pre-decision snapshot, selected policy,
    model confidence, and feature metadata. It never consumes future demand,
    future deliveries, future scenarios, or realized future outcomes.
    """

    DEFAULT_WEIGHTS = {
        "operational": 0.35,
        "economic": 0.30,
        "model": 0.25,
        "data_quality": 0.10,
    }

    POLICY_ECONOMIC_BASE_RISK = {
        "lean": 0.45,
        "balanced": 0.25,
        "service_first": 0.55,
    }

    def __init__(
        self,
        *,
        weights: Mapping[str, float] | None = None,
    ) -> None:
        resolved = dict(weights or self.DEFAULT_WEIGHTS)

        required = set(self.DEFAULT_WEIGHTS)
        if set(resolved) != required:
            raise RiskEngineError(
                "weights must contain exactly: "
                + ", ".join(sorted(required))
            )

        for name, value in resolved.items():
            if not isfinite(float(value)) or float(value) < 0.0:
                raise RiskEngineError(
                    f"Weight {name!r} must be finite and non-negative."
                )

        total = sum(float(value) for value in resolved.values())
        if total <= 0.0:
            raise RiskEngineError(
                "At least one risk weight must be greater than zero."
            )

        self.weights = {
            name: float(value) / total
            for name, value in resolved.items()
        }

    def assess(
        self,
        *,
        snapshot: Mapping[str, Any] | None,
        selected_policy: str,
        confidence: ConfidenceAnalysis | None,
        feature_count: int,
        probabilities_available: bool,
    ) -> RiskAssessment:
        policy = str(selected_policy).strip()
        if not policy:
            raise RiskEngineError(
                "selected_policy cannot be empty."
            )

        if feature_count < 0:
            raise RiskEngineError(
                "feature_count cannot be negative."
            )

        payload = dict(snapshot or {})
        reasons: list[str] = []

        operational_score = self._operational_score(
            snapshot=payload,
            selected_policy=policy,
            reasons=reasons,
        )

        economic_score = self._economic_score(
            snapshot=payload,
            selected_policy=policy,
            reasons=reasons,
        )

        model_score = self._model_score(
            confidence=confidence,
            probabilities_available=probabilities_available,
            reasons=reasons,
        )

        data_quality_score = self._data_quality_score(
            snapshot=payload,
            feature_count=feature_count,
            probabilities_available=probabilities_available,
            reasons=reasons,
        )

        overall_score = (
            operational_score * self.weights["operational"]
            + economic_score * self.weights["economic"]
            + model_score * self.weights["model"]
            + data_quality_score * self.weights["data_quality"]
        )

        rounded_score = round(
            self._clamp(overall_score),
            6,
        )

        return RiskAssessment(
            operational_risk=self._to_level(
                operational_score
            ),
            economic_risk=self._to_level(
                economic_score
            ),
            model_risk=self._to_level(
                model_score
            ),
            data_quality_risk=self._to_level(
                data_quality_score
            ),
            overall_risk=self._to_level(
                rounded_score
            ),
            reasons=tuple(dict.fromkeys(reasons)),
            risk_score=rounded_score,
        )

    def _operational_score(
        self,
        *,
        snapshot: Mapping[str, Any],
        selected_policy: str,
        reasons: list[str],
    ) -> float:
        stockout_rate = self._read_ratio(
            snapshot,
            (
                "stockout_rate",
                "state_stockout_rate",
            ),
        )

        below_reorder_share = self._read_ratio(
            snapshot,
            (
                "below_reorder_share",
                "state_below_reorder_share",
            ),
        )

        if below_reorder_share is None:
            count = self._read_number(
                snapshot,
                (
                    "positions_below_reorder_point",
                    "state_positions_below_reorder_point",
                ),
            )
            total = self._read_number(
                snapshot,
                (
                    "inventory_position_count",
                    "state_inventory_position_count",
                ),
            )

            if (
                count is not None
                and total is not None
                and total > 0
            ):
                below_reorder_share = self._clamp(
                    count / total
                )

        demand_multiplier = self._read_number(
            snapshot,
            (
                "scenario_demand_multiplier",
                "final_demand_multiplier",
                "state_final_demand_multiplier",
            ),
        )

        supply_multiplier = self._read_number(
            snapshot,
            (
                "scenario_supply_multiplier",
                "final_supply_multiplier",
                "state_final_supply_multiplier",
            ),
        )

        score = 0.10

        if stockout_rate is not None:
            score += min(
                0.50,
                stockout_rate * 5.0,
            )
            if stockout_rate >= 0.05:
                reasons.append(
                    "Current stockout exposure is elevated."
                )

        if below_reorder_share is not None:
            score += min(
                0.35,
                below_reorder_share * 1.5,
            )
            if below_reorder_share >= 0.20:
                reasons.append(
                    "A significant share of inventory positions is below reorder point."
                )

        if demand_multiplier is not None and demand_multiplier > 1.15:
            score += min(
                0.20,
                (demand_multiplier - 1.0) * 0.5,
            )
            reasons.append(
                "Same-day demand pressure increases service risk."
            )

        if supply_multiplier is not None and supply_multiplier < 0.90:
            score += min(
                0.20,
                (1.0 - supply_multiplier) * 0.8,
            )
            reasons.append(
                "Same-day supply pressure increases replenishment risk."
            )

        if (
            selected_policy == "lean"
            and (
                (stockout_rate or 0.0) > 0.0
                or (below_reorder_share or 0.0) >= 0.10
            )
        ):
            score += 0.25
            reasons.append(
                "The lean policy is aggressive under current inventory pressure."
            )

        return self._clamp(score)

    def _economic_score(
        self,
        *,
        snapshot: Mapping[str, Any],
        selected_policy: str,
        reasons: list[str],
    ) -> float:
        score = self.POLICY_ECONOMIC_BASE_RISK.get(
            selected_policy,
            0.50,
        )

        logistics_multiplier = self._read_number(
            snapshot,
            (
                "logistics_cost_multiplier",
                "state_logistics_cost_multiplier",
            ),
        )

        in_transit_share = self._read_ratio(
            snapshot,
            (
                "in_transit_share",
                "state_in_transit_share",
            ),
        )

        if (
            selected_policy == "service_first"
            and logistics_multiplier is not None
            and logistics_multiplier > 1.10
        ):
            score += 0.20
            reasons.append(
                "Service-first decisions may amplify cost during elevated logistics pricing."
            )

        if (
            selected_policy == "service_first"
            and in_transit_share is not None
            and in_transit_share >= 0.25
        ):
            score += 0.15
            reasons.append(
                "Additional service protection may increase inventory already in transit."
            )

        if selected_policy == "lean":
            stockout_rate = self._read_ratio(
                snapshot,
                (
                    "stockout_rate",
                    "state_stockout_rate",
                ),
            )

            if stockout_rate is not None and stockout_rate > 0.0:
                score += 0.25
                reasons.append(
                    "Lean inventory exposure may increase lost-sales cost."
                )

        if selected_policy not in self.POLICY_ECONOMIC_BASE_RISK:
            reasons.append(
                "The selected policy has no calibrated economic risk baseline."
            )

        return self._clamp(score)

    def _model_score(
        self,
        *,
        confidence: ConfidenceAnalysis | None,
        probabilities_available: bool,
        reasons: list[str],
    ) -> float:
        if confidence is None:
            if not probabilities_available:
                reasons.append(
                    "Model probabilities are unavailable, increasing uncertainty."
                )
            else:
                reasons.append(
                    "Confidence analysis is unavailable."
                )
            return 0.75

        score = (
            0.50 * (1.0 - confidence.confidence_score)
            + 0.30 * confidence.normalized_entropy
            + 0.20 * (1.0 - confidence.probability_margin)
        )

        if confidence.confidence_score < 0.50:
            reasons.append(
                "The model confidence score is low."
            )

        if confidence.probability_margin < 0.15:
            reasons.append(
                "The top two policies have similar probabilities."
            )

        if confidence.normalized_entropy > 0.70:
            reasons.append(
                "The probability distribution is highly uncertain."
            )

        return self._clamp(score)

    def _data_quality_score(
        self,
        *,
        snapshot: Mapping[str, Any],
        feature_count: int,
        probabilities_available: bool,
        reasons: list[str],
    ) -> float:
        score = 0.0

        if not snapshot:
            score += 0.60
            reasons.append(
                "The decision snapshot is empty."
            )

        if feature_count == 0:
            score += 0.50
            reasons.append(
                "No model features were reported."
            )
        elif feature_count < 5:
            score += 0.25
            reasons.append(
                "The model used a very small feature set."
            )

        missing_values = sum(
            1
            for value in snapshot.values()
            if value is None
        )

        if snapshot:
            missing_share = (
                missing_values / len(snapshot)
            )

            score += min(
                0.40,
                missing_share,
            )

            if missing_share >= 0.20:
                reasons.append(
                    "The decision snapshot contains many missing values."
                )

        if not probabilities_available:
            score += 0.15
            reasons.append(
                "Probability metadata is missing from the prediction."
            )

        return self._clamp(score)

    @staticmethod
    def _read_number(
        snapshot: Mapping[str, Any],
        names: tuple[str, ...],
    ) -> float | None:
        for name in names:
            if name not in snapshot:
                continue

            value = snapshot[name]

            if isinstance(value, bool):
                continue

            try:
                number = float(value)
            except (TypeError, ValueError):
                continue

            if isfinite(number):
                return number

        return None

    @classmethod
    def _read_ratio(
        cls,
        snapshot: Mapping[str, Any],
        names: tuple[str, ...],
    ) -> float | None:
        number = cls._read_number(
            snapshot,
            names,
        )

        if number is None:
            return None

        return cls._clamp(number)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(
            0.0,
            min(1.0, float(value)),
        )

    @staticmethod
    def _to_level(score: float) -> RiskLevel:
        value = float(score)

        if value < 0.25:
            return RiskLevel.LOW

        if value < 0.50:
            return RiskLevel.MEDIUM

        if value < 0.75:
            return RiskLevel.HIGH

        return RiskLevel.CRITICAL
