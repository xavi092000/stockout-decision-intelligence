from __future__ import annotations

import unittest

from simulation.decision_intelligence import (
    ConfidenceEngine,
    ConfidenceEngineError,
    ConfidenceLevel,
)


class ConfidenceEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ConfidenceEngine()

    def test_high_confidence_prediction(self) -> None:
        analysis = self.engine.analyze(
            probabilities={
                "balanced": 0.88,
                "service_first": 0.08,
                "lean": 0.04,
            },
            selected_policy="balanced",
        )

        self.assertEqual(
            analysis.predicted_policy,
            "balanced",
        )
        self.assertEqual(
            analysis.second_best_policy,
            "service_first",
        )
        self.assertAlmostEqual(
            analysis.predicted_probability,
            0.88,
            places=6,
        )
        self.assertAlmostEqual(
            analysis.probability_margin,
            0.80,
            places=6,
        )
        self.assertIn(
            analysis.confidence_level,
            {
                ConfidenceLevel.HIGH,
                ConfidenceLevel.VERY_HIGH,
            },
        )

    def test_ambiguous_prediction_has_lower_confidence(self) -> None:
        analysis = self.engine.analyze(
            probabilities={
                "balanced": 0.38,
                "service_first": 0.34,
                "lean": 0.28,
            },
            selected_policy="balanced",
        )

        self.assertLess(
            analysis.probability_margin,
            0.10,
        )
        self.assertGreater(
            analysis.normalized_entropy,
            0.90,
        )
        self.assertIn(
            analysis.confidence_level,
            {
                ConfidenceLevel.VERY_LOW,
                ConfidenceLevel.LOW,
                ConfidenceLevel.MEDIUM,
            },
        )

    def test_probabilities_are_normalized(self) -> None:
        analysis = self.engine.analyze(
            probabilities={
                "balanced": 0.70,
                "lean": 0.29,
            },
            selected_policy="balanced",
        )

        self.assertAlmostEqual(
            analysis.predicted_probability
            + analysis.second_best_probability,
            1.0,
            places=6,
        )

    def test_empty_probabilities_are_rejected(self) -> None:
        with self.assertRaises(ConfidenceEngineError):
            self.engine.analyze({})

    def test_invalid_probability_is_rejected(self) -> None:
        with self.assertRaises(ConfidenceEngineError):
            self.engine.analyze(
                {
                    "balanced": 1.10,
                    "lean": -0.10,
                }
            )

    def test_invalid_probability_sum_is_rejected(self) -> None:
        with self.assertRaises(ConfidenceEngineError):
            self.engine.analyze(
                {
                    "balanced": 0.40,
                    "lean": 0.20,
                }
            )

    def test_selected_policy_must_match_prediction(self) -> None:
        with self.assertRaises(ConfidenceEngineError):
            self.engine.analyze(
                probabilities={
                    "balanced": 0.80,
                    "lean": 0.20,
                },
                selected_policy="lean",
            )

    def test_single_policy_distribution(self) -> None:
        analysis = self.engine.analyze(
            probabilities={
                "balanced": 1.0,
            },
            selected_policy="balanced",
        )

        self.assertEqual(
            analysis.predicted_policy,
            "balanced",
        )
        self.assertIsNone(
            analysis.second_best_policy,
        )
        self.assertEqual(
            analysis.normalized_entropy,
            0.0,
        )
        self.assertEqual(
            analysis.probability_margin,
            1.0,
        )
        self.assertEqual(
            analysis.confidence_level,
            ConfidenceLevel.VERY_HIGH,
        )


if __name__ == "__main__":
    unittest.main()
