from __future__ import annotations

import unittest

from simulation.decision_intelligence import (
    ConfidenceAnalysis,
    ConfidenceLevel,
    RiskEngine,
    RiskEngineError,
    RiskLevel,
)


class RiskEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RiskEngine()

    def test_low_risk_balanced_decision(self) -> None:
        confidence = ConfidenceAnalysis(
            predicted_probability=0.90,
            second_best_probability=0.07,
            probability_margin=0.83,
            normalized_entropy=0.20,
            confidence_score=0.88,
            confidence_level=ConfidenceLevel.VERY_HIGH,
            explanation="The prediction is stable.",
            predicted_policy="balanced",
            second_best_policy="lean",
        )

        result = self.engine.assess(
            snapshot={
                "stockout_rate": 0.0,
                "below_reorder_share": 0.03,
                "scenario_demand_multiplier": 1.0,
                "scenario_supply_multiplier": 1.0,
            },
            selected_policy="balanced",
            confidence=confidence,
            feature_count=20,
            probabilities_available=True,
        )

        self.assertIn(
            result.overall_risk,
            {
                RiskLevel.LOW,
                RiskLevel.MEDIUM,
            },
        )
        self.assertIsNotNone(
            result.risk_score,
        )

    def test_lean_policy_under_stock_pressure_is_high_risk(
        self,
    ) -> None:
        confidence = ConfidenceAnalysis(
            predicted_probability=0.52,
            second_best_probability=0.43,
            probability_margin=0.09,
            normalized_entropy=0.92,
            confidence_score=0.35,
            confidence_level=ConfidenceLevel.LOW,
            explanation="The prediction is ambiguous.",
            predicted_policy="lean",
            second_best_policy="service_first",
        )

        result = self.engine.assess(
            snapshot={
                "stockout_rate": 0.12,
                "below_reorder_share": 0.40,
                "scenario_demand_multiplier": 1.30,
                "scenario_supply_multiplier": 0.80,
            },
            selected_policy="lean",
            confidence=confidence,
            feature_count=18,
            probabilities_available=True,
        )

        self.assertIn(
            result.overall_risk,
            {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            },
        )
        self.assertGreaterEqual(
            result.risk_score,
            0.50,
        )
        self.assertTrue(
            any(
                "lean" in reason.lower()
                for reason in result.reasons
            )
        )

    def test_missing_probabilities_increase_model_risk(
        self,
    ) -> None:
        result = self.engine.assess(
            snapshot={
                "stockout_rate": 0.0,
            },
            selected_policy="balanced",
            confidence=None,
            feature_count=10,
            probabilities_available=False,
        )

        self.assertIn(
            result.model_risk,
            {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            },
        )

    def test_empty_snapshot_increases_data_quality_risk(
        self,
    ) -> None:
        result = self.engine.assess(
            snapshot={},
            selected_policy="balanced",
            confidence=None,
            feature_count=0,
            probabilities_available=False,
        )

        self.assertEqual(
            result.data_quality_risk,
            RiskLevel.CRITICAL,
        )

    def test_invalid_weights_are_rejected(self) -> None:
        with self.assertRaises(
            RiskEngineError
        ):
            RiskEngine(
                weights={
                    "operational": 1.0,
                }
            )

    def test_negative_feature_count_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            RiskEngineError
        ):
            self.engine.assess(
                snapshot={},
                selected_policy="balanced",
                confidence=None,
                feature_count=-1,
                probabilities_available=False,
            )


if __name__ == "__main__":
    unittest.main()
