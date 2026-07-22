from __future__ import annotations

import unittest
from typing import Any

from simulation.decision_intelligence import (
    ConfidenceLevel,
    MLDecisionAnalyzerError,
    MLDecisionAnalyzerV2,
)


class FakeAdapter:
    def __init__(
        self,
        result: dict[str, Any],
    ) -> None:
        self.result = result

    def predict_with_details(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        return dict(self.result)


class MLDecisionAnalyzerV2Test(unittest.TestCase):
    def test_builds_analysis_from_ml_prediction(self) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=FakeAdapter(
                {
                    "policy": "balanced",
                    "latency_ms": 3.7,
                    "feature_count": 18,
                    "probabilities": {
                        "balanced": 0.82,
                        "service_first": 0.13,
                        "lean": 0.05,
                    },
                }
            )
        )

        analysis = analyzer.analyze(
            snapshot={
                "snapshot_id": "snapshot-42-001",
                "stockout_rate": 0.04,
            },
            simulation_day=1,
            snapshot_id="snapshot-42-001",
            episode_seed=42,
            decision_id="decision-42-001",
        )

        self.assertEqual(
            analysis.selected_policy,
            "balanced",
        )
        self.assertIsNotNone(
            analysis.confidence,
        )
        self.assertEqual(
            analysis.confidence.predicted_policy,
            "balanced",
        )
        self.assertIn(
            analysis.confidence.confidence_level,
            {
                ConfidenceLevel.MEDIUM,
                ConfidenceLevel.HIGH,
                ConfidenceLevel.VERY_HIGH,
            },
        )
        self.assertEqual(
            len(analysis.alternatives),
            2,
        )
        self.assertEqual(
            analysis.alternatives[0].policy_name,
            "service_first",
        )
        self.assertEqual(
            analysis.trace.source,
            "ML_POLICY_ADAPTER_V2",
        )
        self.assertIsNotNone(
            analysis.risk,
        )
        self.assertIn(
            "risk-analyzed",
            analysis.tags,
        )

    def test_supports_models_without_probabilities(self) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=FakeAdapter(
                {
                    "policy": "lean",
                    "latency_ms": 1.2,
                    "feature_count": 12,
                    "probabilities": None,
                }
            )
        )

        analysis = analyzer.analyze(
            snapshot={},
            simulation_day=5,
            snapshot_id="snapshot-5",
            episode_seed=99,
        )

        self.assertEqual(
            analysis.selected_policy,
            "lean",
        )
        self.assertIsNone(
            analysis.confidence,
        )
        self.assertEqual(
            analysis.alternatives,
            (),
        )
        self.assertIn(
            "confidence-unavailable",
            analysis.tags,
        )
        self.assertIsNotNone(
            analysis.risk,
        )

    def test_empty_policy_is_rejected(self) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=FakeAdapter(
                {
                    "policy": "",
                    "latency_ms": 1.0,
                    "feature_count": 10,
                    "probabilities": None,
                }
            )
        )

        with self.assertRaises(
            MLDecisionAnalyzerError
        ):
            analyzer.analyze(
                snapshot={},
                simulation_day=1,
                snapshot_id="snapshot-1",
                episode_seed=42,
            )

    def test_prediction_probability_mismatch_is_rejected(
        self,
    ) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=FakeAdapter(
                {
                    "policy": "lean",
                    "latency_ms": 1.0,
                    "feature_count": 10,
                    "probabilities": {
                        "balanced": 0.80,
                        "lean": 0.20,
                    },
                }
            )
        )

        with self.assertRaises(
            MLDecisionAnalyzerError
        ):
            analyzer.analyze(
                snapshot={},
                simulation_day=1,
                snapshot_id="snapshot-1",
                episode_seed=42,
            )


if __name__ == "__main__":
    unittest.main()

