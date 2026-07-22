from __future__ import annotations

import unittest
from typing import Any

from simulation.decision_intelligence import (
    CounterfactualEngine,
    CounterfactualEngineError,
    MLDecisionAnalyzerV2,
    MappingPolicyOutcomeEvaluator,
    PolicyOutcome,
)


class FakeAdapter:
    def predict_with_details(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        del snapshot

        return {
            "policy": "balanced",
            "latency_ms": 2.4,
            "feature_count": 18,
            "probabilities": {
                "balanced": 0.70,
                "service_first": 0.20,
                "lean": 0.10,
            },
        }


class CounterfactualEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = MappingPolicyOutcomeEvaluator(
            {
                "balanced": PolicyOutcome(
                    policy_name="balanced",
                    business_value=1000.0,
                    service_level=0.985,
                    total_cost=500.0,
                    stockouts=10.0,
                ),
                "service_first": PolicyOutcome(
                    policy_name="service_first",
                    business_value=1080.0,
                    service_level=0.995,
                    total_cost=560.0,
                    stockouts=4.0,
                ),
                "lean": PolicyOutcome(
                    policy_name="lean",
                    business_value=920.0,
                    service_level=0.960,
                    total_cost=430.0,
                    stockouts=22.0,
                ),
            }
        )

        self.engine = CounterfactualEngine(
            evaluator=self.evaluator,
        )

    def test_compares_rejected_policies(self) -> None:
        analysis = self.engine.analyze(
            snapshot={"stockout_rate": 0.05},
            chosen_policy="balanced",
            alternative_policies=(
                "service_first",
                "lean",
            ),
        )

        self.assertEqual(
            analysis.chosen_policy,
            "balanced",
        )
        self.assertEqual(
            len(analysis.alternatives),
            2,
        )
        self.assertEqual(
            analysis.best_alternative,
            "service_first",
        )
        self.assertEqual(
            analysis.opportunity_cost,
            80.0,
        )

        service_first = analysis.alternatives[0]

        self.assertEqual(
            service_first.business_value_delta,
            80.0,
        )
        self.assertAlmostEqual(
            service_first.service_level_delta,
            0.01,
        )
        self.assertEqual(
            service_first.cost_delta,
            60.0,
        )
        self.assertEqual(
            service_first.stockout_delta,
            -6.0,
        )

    def test_opportunity_cost_is_zero_when_chosen_is_best(
        self,
    ) -> None:
        analysis = self.engine.analyze(
            snapshot={},
            chosen_policy="service_first",
            alternative_policies=(
                "balanced",
                "lean",
            ),
        )

        self.assertEqual(
            analysis.opportunity_cost,
            0.0,
        )
        self.assertEqual(
            analysis.best_alternative,
            "balanced",
        )

    def test_supports_no_alternatives(self) -> None:
        analysis = self.engine.analyze(
            snapshot={},
            chosen_policy="balanced",
            alternative_policies=(),
        )

        self.assertEqual(
            analysis.alternatives,
            (),
        )
        self.assertIsNone(
            analysis.best_alternative,
        )
        self.assertEqual(
            analysis.opportunity_cost,
            0.0,
        )

    def test_rejects_chosen_policy_as_alternative(self) -> None:
        with self.assertRaises(
            CounterfactualEngineError,
        ):
            self.engine.analyze(
                snapshot={},
                chosen_policy="balanced",
                alternative_policies=(
                    "balanced",
                ),
            )

    def test_rejects_duplicate_alternatives(self) -> None:
        with self.assertRaises(
            CounterfactualEngineError,
        ):
            self.engine.analyze(
                snapshot={},
                chosen_policy="balanced",
                alternative_policies=(
                    "lean",
                    "lean",
                ),
            )

    def test_rejects_missing_outcome(self) -> None:
        with self.assertRaises(
            CounterfactualEngineError,
        ):
            self.engine.analyze(
                snapshot={},
                chosen_policy="balanced",
                alternative_policies=(
                    "unknown",
                ),
            )

    def test_policy_outcome_validation(self) -> None:
        with self.assertRaises(ValueError):
            PolicyOutcome(
                policy_name="lean",
                business_value=100.0,
                service_level=1.2,
                total_cost=50.0,
                stockouts=1.0,
            )

    def test_integrates_with_ml_decision_analyzer(self) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=FakeAdapter(),
            counterfactual_engine=self.engine,
        )

        analysis = analyzer.analyze(
            snapshot={
                "snapshot_id": "snapshot-42-001",
                "stockout_rate": 0.05,
                "below_reorder_share": 0.20,
            },
            simulation_day=1,
            snapshot_id="snapshot-42-001",
            episode_seed=42,
            decision_id="decision-42-001",
        )

        self.assertIsNotNone(
            analysis.counterfactual,
        )
        self.assertEqual(
            analysis.counterfactual.chosen_policy,
            "balanced",
        )
        self.assertEqual(
            analysis.counterfactual.best_alternative,
            "service_first",
        )
        self.assertEqual(
            analysis.counterfactual.opportunity_cost,
            80.0,
        )
        self.assertIn(
            "counterfactual-analyzed",
            analysis.tags,
        )


if __name__ == "__main__":
    unittest.main()
