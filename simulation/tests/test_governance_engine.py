from __future__ import annotations

import unittest

from simulation.decision_intelligence.governance import (
    GovernanceConfig,
    GovernanceContext,
    GovernanceDecision,
    GovernanceEngine,
    GovernanceEngineError,
    governance_context_from_mapping,
)
from simulation.decision_intelligence.models import (
    ConfidenceAnalysis,
    ConfidenceLevel,
    GovernanceStatus,
    RiskAssessment,
    RiskLevel,
)


def confidence(
    level: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> ConfidenceAnalysis:
    values = {
        ConfidenceLevel.VERY_LOW: (0.26, 0.25),
        ConfidenceLevel.LOW: (0.35, 0.30),
        ConfidenceLevel.MEDIUM: (0.55, 0.30),
        ConfidenceLevel.HIGH: (0.80, 0.15),
        ConfidenceLevel.VERY_HIGH: (0.95, 0.03),
    }

    predicted, second_best = values[level]
    margin = round(predicted - second_best, 6)

    return ConfidenceAnalysis(
        predicted_probability=predicted,
        second_best_probability=second_best,
        probability_margin=margin,
        normalized_entropy=round(
            max(0.0, 1.0 - predicted),
            6,
        ),
        confidence_score=predicted,
        confidence_level=level,
        explanation="Deterministic test confidence.",
        predicted_policy="balanced",
        second_best_policy="service_first",
    )


def risk(
    overall: RiskLevel = RiskLevel.LOW,
    model: RiskLevel = RiskLevel.LOW,
) -> RiskAssessment:
    return RiskAssessment(
        operational_risk=overall,
        economic_risk=overall,
        model_risk=model,
        data_quality_risk=RiskLevel.LOW,
        overall_risk=overall,
        reasons=("Deterministic test risk.",),
        risk_score=0.10,
    )


def context(
    *,
    registered: bool = True,
    approved: bool = True,
    champion: bool = True,
) -> GovernanceContext:
    return GovernanceContext(
        policy_name="balanced",
        registered=registered,
        policy_approved=approved,
        champion=champion,
        experiment_id="experiment-42",
        model_version="model-2.1.0",
        policy_version="policy-3.0.0",
        approval_date=(
            "2026-07-21"
            if approved
            else None
        ),
        evaluator="governance-engine-test",
        registry_reference="registry://policies/balanced/3.0.0",
    )


class GovernanceEngineTest(unittest.TestCase):
    def test_approves_registered_approved_low_risk_policy(
        self,
    ) -> None:
        engine = GovernanceEngine()

        result = engine.evaluate(
            context=context(),
            confidence=confidence(ConfidenceLevel.HIGH),
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.APPROVED,
        )
        self.assertTrue(result.approved)
        self.assertTrue(result.champion)
        self.assertEqual(
            result.experiment_id,
            "experiment-42",
        )

    def test_low_confidence_requires_review(self) -> None:
        engine = GovernanceEngine()

        result = engine.evaluate(
            context=context(),
            confidence=confidence(ConfidenceLevel.LOW),
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.PENDING,
        )
        self.assertFalse(result.approved)

    def test_missing_confidence_requires_review(self) -> None:
        engine = GovernanceEngine()

        decision = engine.decide(
            context=context(),
            confidence=None,
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            decision.status,
            GovernanceStatus.PENDING,
        )
        self.assertIn(
            "Confidence analysis is unavailable.",
            decision.reasons,
        )

    def test_critical_risk_is_rejected(self) -> None:
        engine = GovernanceEngine()

        decision = engine.decide(
            context=context(),
            confidence=confidence(ConfidenceLevel.VERY_HIGH),
            risk=risk(RiskLevel.CRITICAL),
        )

        self.assertEqual(
            decision.status,
            GovernanceStatus.REJECTED,
        )
        self.assertFalse(decision.approved)
        self.assertIn(
            "Overall decision risk is CRITICAL.",
            decision.reasons,
        )

    def test_unregistered_policy_is_rejected(self) -> None:
        engine = GovernanceEngine()

        result = engine.evaluate(
            context=context(
                registered=False,
                approved=False,
                champion=False,
            ),
            confidence=confidence(ConfidenceLevel.HIGH),
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.REJECTED,
        )
        self.assertFalse(result.approved)

    def test_unapproved_policy_is_pending(self) -> None:
        engine = GovernanceEngine()

        result = engine.evaluate(
            context=context(
                registered=True,
                approved=False,
                champion=False,
            ),
            confidence=confidence(ConfidenceLevel.HIGH),
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.PENDING,
        )
        self.assertFalse(result.approved)

    def test_high_risk_is_pending_by_default(self) -> None:
        engine = GovernanceEngine()

        result = engine.evaluate(
            context=context(),
            confidence=confidence(ConfidenceLevel.HIGH),
            risk=risk(RiskLevel.HIGH),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.PENDING,
        )

    def test_high_model_risk_can_be_rejected(self) -> None:
        engine = GovernanceEngine(
            GovernanceConfig(
                reject_high_model_risk=True,
            )
        )

        result = engine.evaluate(
            context=context(),
            confidence=confidence(ConfidenceLevel.HIGH),
            risk=risk(
                overall=RiskLevel.MEDIUM,
                model=RiskLevel.HIGH,
            ),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.REJECTED,
        )

    def test_champion_requirement(self) -> None:
        engine = GovernanceEngine(
            GovernanceConfig(
                require_champion_for_auto_approval=True,
            )
        )

        result = engine.evaluate(
            context=context(
                registered=True,
                approved=True,
                champion=False,
            ),
            confidence=confidence(ConfidenceLevel.HIGH),
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.PENDING,
        )

    def test_missing_confidence_can_be_allowed(self) -> None:
        engine = GovernanceEngine(
            GovernanceConfig(
                allow_missing_confidence=True,
            )
        )

        result = engine.evaluate(
            context=context(),
            confidence=None,
            risk=risk(RiskLevel.LOW),
        )

        self.assertEqual(
            result.status,
            GovernanceStatus.APPROVED,
        )

    def test_context_rejects_invalid_champion(self) -> None:
        with self.assertRaises(ValueError):
            GovernanceContext(
                policy_name="balanced",
                registered=True,
                policy_approved=False,
                champion=True,
            )

    def test_mapping_factory(self) -> None:
        result = governance_context_from_mapping(
            {
                "policy_name": "balanced",
                "registered": True,
                "policy_approved": True,
                "champion": True,
                "experiment_id": "experiment-42",
            }
        )

        self.assertEqual(
            result.policy_name,
            "balanced",
        )
        self.assertTrue(result.registered)
        self.assertTrue(result.policy_approved)
        self.assertTrue(result.champion)

    def test_invalid_input_type_is_rejected(self) -> None:
        engine = GovernanceEngine()

        with self.assertRaises(GovernanceEngineError):
            engine.evaluate(
                context=context(),
                confidence=confidence(),
                risk="LOW",
            )

    def test_governance_decision_consistency(self) -> None:
        with self.assertRaises(ValueError):
            GovernanceDecision(
                status=GovernanceStatus.APPROVED,
                approved=False,
                reasons=("Invalid state.",),
            )


if __name__ == "__main__":
    unittest.main()

