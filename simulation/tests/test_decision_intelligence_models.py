from __future__ import annotations

import unittest

from simulation.decision_intelligence import (
    AlternativePolicy,
    ConfidenceAnalysis,
    ConfidenceLevel,
    DecisionAnalysis,
    DecisionMetadata,
    DecisionTrace,
    GovernanceAnalysis,
    GovernanceStatus,
    RiskAssessment,
    RiskLevel,
)


class DecisionIntelligenceModelsTest(unittest.TestCase):
    def test_build_complete_decision_analysis(self) -> None:
        metadata = DecisionMetadata(
            decision_id="decision-42-001",
            simulation_day=1,
            snapshot_id="snapshot-42-001",
            episode_seed=42,
        )

        trace = DecisionTrace(
            selected_policy="balanced",
            reason=(
                "Balanced policy preserves service while "
                "controlling inventory exposure."
            ),
            source="ML_POLICY",
            feature_count=18,
            latency_ms=4.2,
            input_snapshot={
                "stockout_rate": 0.08,
                "below_reorder_share": 0.22,
            },
        )

        confidence = ConfidenceAnalysis(
            predicted_probability=0.82,
            second_best_probability=0.13,
            probability_margin=0.69,
            normalized_entropy=0.31,
            confidence_score=0.84,
            confidence_level=ConfidenceLevel.HIGH,
            explanation=(
                "The selected policy has a strong probability "
                "lead over the second-best alternative."
            ),
            predicted_policy="balanced",
            second_best_policy="service_first",
        )

        risk = RiskAssessment(
            operational_risk=RiskLevel.MEDIUM,
            economic_risk=RiskLevel.LOW,
            model_risk=RiskLevel.LOW,
            data_quality_risk=RiskLevel.LOW,
            overall_risk=RiskLevel.MEDIUM,
            reasons=(
                "Inventory pressure is elevated.",
            ),
            risk_score=0.38,
        )

        governance = GovernanceAnalysis(
            status=GovernanceStatus.APPROVED,
            experiment_id="experiment-009",
            model_version="policy-model-2.1.0",
            policy_version="balanced-1.3.0",
            champion=True,
            approved=True,
            evaluator="economic-validation-protocol",
        )

        analysis = DecisionAnalysis(
            metadata=metadata,
            trace=trace,
            confidence=confidence,
            risk=risk,
            alternatives=(
                AlternativePolicy(
                    policy_name="service_first",
                    rank=2,
                    probability=0.13,
                ),
                AlternativePolicy(
                    policy_name="lean",
                    rank=3,
                    probability=0.05,
                ),
            ),
            governance=governance,
            expected_business_value=12500.0,
            expected_service_level=0.96,
            expected_cost=8300.0,
            tags=(
                "adaptive",
                "ml",
                "governed",
            ),
        )

        payload = analysis.to_dict()

        self.assertEqual(
            analysis.selected_policy,
            "balanced",
        )
        self.assertEqual(
            payload["metadata"]["decision_id"],
            "decision-42-001",
        )
        self.assertEqual(
            payload["confidence"]["confidence_level"],
            ConfidenceLevel.HIGH,
        )
        self.assertEqual(
            len(payload["alternatives"]),
            2,
        )

    def test_invalid_probability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ConfidenceAnalysis(
                predicted_probability=1.2,
                second_best_probability=0.1,
                probability_margin=1.1,
                normalized_entropy=0.1,
                confidence_score=0.9,
                confidence_level=ConfidenceLevel.HIGH,
                explanation="Invalid probability test.",
            )

    def test_selected_policy_cannot_be_alternative(self) -> None:
        metadata = DecisionMetadata(
            decision_id="decision-1",
            simulation_day=1,
            snapshot_id="snapshot-1",
            episode_seed=42,
        )

        trace = DecisionTrace(
            selected_policy="balanced",
            reason="Balanced policy selected.",
            source="RULE_ENGINE",
            feature_count=0,
            latency_ms=0.1,
        )

        with self.assertRaises(ValueError):
            DecisionAnalysis(
                metadata=metadata,
                trace=trace,
                alternatives=(
                    AlternativePolicy(
                        policy_name="balanced",
                        rank=1,
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()