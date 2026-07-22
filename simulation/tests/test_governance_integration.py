from __future__ import annotations

import unittest
from typing import Any

from simulation.decision_intelligence import (
    GovernanceContext,
    GovernanceEngine,
    GovernanceStatus,
    MLDecisionAnalyzerError,
    MLDecisionAnalyzerV2,
)


class HighConfidenceAdapter:
    def predict_with_details(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        del snapshot

        return {
            "policy": "balanced",
            "latency_ms": 2.0,
            "feature_count": 20,
            "probabilities": {
                "balanced": 0.85,
                "service_first": 0.10,
                "lean": 0.05,
            },
        }


class LowConfidenceAdapter:
    def predict_with_details(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        del snapshot

        return {
            "policy": "balanced",
            "latency_ms": 2.0,
            "feature_count": 20,
            "probabilities": {
                "balanced": 0.40,
                "service_first": 0.35,
                "lean": 0.25,
            },
        }


def approved_context() -> GovernanceContext:
    return GovernanceContext(
        policy_name="balanced",
        registered=True,
        policy_approved=True,
        champion=True,
        experiment_id="experiment-42",
        model_version="model-2.1.0",
        policy_version="policy-3.0.0",
        approval_date="2026-07-21",
        evaluator="governance-engine",
        registry_reference="registry://balanced/3.0.0",
    )


class GovernanceIntegrationTest(unittest.TestCase):
    def test_governance_approved_is_attached_to_analysis(
        self,
    ) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=HighConfidenceAdapter(),
            governance_engine=GovernanceEngine(),
        )

        analysis = analyzer.analyze(
            snapshot={
                "stockout_rate": 0.01,
                "below_reorder_share": 0.05,
                "inventory_position_count": 100,
                "demand_multiplier": 1.0,
                "supply_multiplier": 1.0,
            },
            simulation_day=1,
            snapshot_id="snapshot-001",
            episode_seed=42,
            decision_id="decision-001",
            governance_context=approved_context(),
        )

        self.assertIsNotNone(analysis.governance)
        self.assertEqual(
            analysis.governance.status,
            GovernanceStatus.APPROVED,
        )
        self.assertTrue(analysis.governance.approved)
        self.assertTrue(analysis.governance.champion)

        self.assertIn(
            "governance-analyzed",
            analysis.tags,
        )
        self.assertIn(
            "governance-approved",
            analysis.tags,
        )

    def test_low_confidence_produces_pending_governance(
        self,
    ) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=LowConfidenceAdapter(),
            governance_engine=GovernanceEngine(),
        )

        analysis = analyzer.analyze(
            snapshot={
                "stockout_rate": 0.01,
                "below_reorder_share": 0.05,
                "inventory_position_count": 100,
                "demand_multiplier": 1.0,
                "supply_multiplier": 1.0,
            },
            simulation_day=1,
            snapshot_id="snapshot-002",
            episode_seed=42,
            governance_context=approved_context(),
        )

        self.assertIsNotNone(analysis.governance)
        self.assertEqual(
            analysis.governance.status,
            GovernanceStatus.PENDING,
        )
        self.assertFalse(analysis.governance.approved)
        self.assertFalse(analysis.governance.champion)

        self.assertIn(
            "governance-pending",
            analysis.tags,
        )

    def test_governance_context_is_required_when_engine_exists(
        self,
    ) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=HighConfidenceAdapter(),
            governance_engine=GovernanceEngine(),
        )

        with self.assertRaises(MLDecisionAnalyzerError):
            analyzer.analyze(
                snapshot={
                    "stockout_rate": 0.01,
                    "below_reorder_share": 0.05,
                },
                simulation_day=1,
                snapshot_id="snapshot-003",
                episode_seed=42,
            )

    def test_context_policy_must_match_prediction(
        self,
    ) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=HighConfidenceAdapter(),
            governance_engine=GovernanceEngine(),
        )

        mismatched_context = GovernanceContext(
            policy_name="lean",
            registered=True,
            policy_approved=True,
            champion=False,
        )

        with self.assertRaises(MLDecisionAnalyzerError):
            analyzer.analyze(
                snapshot={
                    "stockout_rate": 0.01,
                    "below_reorder_share": 0.05,
                },
                simulation_day=1,
                snapshot_id="snapshot-004",
                episode_seed=42,
                governance_context=mismatched_context,
            )

    def test_context_without_engine_is_rejected(self) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=HighConfidenceAdapter(),
        )

        with self.assertRaises(MLDecisionAnalyzerError):
            analyzer.analyze(
                snapshot={
                    "stockout_rate": 0.01,
                    "below_reorder_share": 0.05,
                },
                simulation_day=1,
                snapshot_id="snapshot-005",
                episode_seed=42,
                governance_context=approved_context(),
            )

    def test_existing_analyzer_behavior_remains_compatible(
        self,
    ) -> None:
        analyzer = MLDecisionAnalyzerV2(
            adapter=HighConfidenceAdapter(),
        )

        analysis = analyzer.analyze(
            snapshot={
                "stockout_rate": 0.01,
                "below_reorder_share": 0.05,
            },
            simulation_day=1,
            snapshot_id="snapshot-006",
            episode_seed=42,
        )

        self.assertIsNone(analysis.governance)
        self.assertNotIn(
            "governance-analyzed",
            analysis.tags,
        )


if __name__ == "__main__":
    unittest.main()
