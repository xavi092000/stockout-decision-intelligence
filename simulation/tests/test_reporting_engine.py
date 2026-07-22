from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from simulation.decision_intelligence.analyzer import (
    MLDecisionAnalyzerV2,
)
from simulation.decision_intelligence.counterfactual import (
    CounterfactualEngine,
    MappingPolicyOutcomeEvaluator,
    PolicyOutcome,
)
from simulation.decision_intelligence.governance import (
    GovernanceContext,
    GovernanceEngine,
)
from simulation.decision_intelligence.reporting import (
    ExecutiveDecisionReport,
    ExecutiveReportingEngine,
    ReportSection,
    ReportingEngineError,
)


class ReportingAdapter:
    def predict_with_details(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        del snapshot

        return {
            "policy": "balanced",
            "latency_ms": 2.5,
            "feature_count": 18,
            "probabilities": {
                "balanced": 0.92,
                "service_first": 0.05,
                "lean": 0.03,
            },
        }


def build_analysis():
    evaluator = MappingPolicyOutcomeEvaluator(
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

    analyzer = MLDecisionAnalyzerV2(
        adapter=ReportingAdapter(),
        counterfactual_engine=CounterfactualEngine(
            evaluator=evaluator,
        ),
        governance_engine=GovernanceEngine(),
    )

    return analyzer.analyze(
        snapshot={
            "stockout_rate": 0.01,
            "below_reorder_share": 0.05,
            "inventory_position_count": 100,
            "demand_multiplier": 1.0,
            "supply_multiplier": 1.0,
        },
        simulation_day=12,
        snapshot_id="snapshot-42-012",
        episode_seed=42,
        decision_id="decision-42-012",
        governance_context=GovernanceContext(
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
        ),
    )


class ExecutiveReportingEngineTest(unittest.TestCase):
    def test_generates_complete_report(self) -> None:
        analysis = build_analysis()
        engine = ExecutiveReportingEngine()

        report = engine.generate(
            analysis,
            report_id="report-001",
            generated_at=datetime(
                2026,
                7,
                21,
                22,
                45,
                tzinfo=timezone.utc,
            ),
        )

        self.assertIsInstance(
            report,
            ExecutiveDecisionReport,
        )
        self.assertEqual(
            report.report_id,
            "report-001",
        )
        self.assertEqual(
            report.decision_id,
            "decision-42-012",
        )
        self.assertEqual(
            report.selected_policy,
            "balanced",
        )
        self.assertEqual(
            report.recommendation_status,
            "APPROVE_WITH_MONITORING",
        )
        self.assertEqual(
            len(report.sections),
            6,
        )

    def test_report_contains_business_opportunity_cost(
        self,
    ) -> None:
        report = ExecutiveReportingEngine().generate(
            build_analysis()
        )

        business_section = next(
            section
            for section in report.sections
            if section.title == "Business Impact"
        )

        values = dict(business_section.entries)

        self.assertEqual(
            values["Opportunity cost"],
            "80.00",
        )
        self.assertEqual(
            values["Best rejected alternative"],
            "service_first",
        )

    def test_report_contains_governance_metadata(
        self,
    ) -> None:
        report = ExecutiveReportingEngine().generate(
            build_analysis()
        )

        governance_section = next(
            section
            for section in report.sections
            if section.title == "Governance"
        )

        values = dict(governance_section.entries)

        self.assertEqual(values["Status"], "APPROVED")
        self.assertEqual(values["Approved"], "Yes")
        self.assertEqual(values["Champion"], "Yes")
        self.assertEqual(
            values["Experiment ID"],
            "experiment-42",
        )
        self.assertEqual(
            values["Policy version"],
            "policy-3.0.0",
        )

    def test_markdown_output_is_human_readable(self) -> None:
        report = ExecutiveReportingEngine().generate(
            build_analysis()
        )

        markdown = report.to_markdown()

        self.assertIn(
            "# Policy balanced approved with an economic trade-off",
            markdown,
        )
        self.assertIn(
            "## Executive Recommendation",
            markdown,
        )
        self.assertIn(
            "## Governance",
            markdown,
        )
        self.assertIn(
            "**Opportunity cost:** 80.00",
            markdown,
        )
        self.assertIn(
            "**Episode seed:** 42",
            markdown,
        )

    def test_report_serializes_to_dictionary(self) -> None:
        report = ExecutiveReportingEngine().generate(
            build_analysis()
        )

        payload = report.to_dict()

        self.assertEqual(
            payload["selected_policy"],
            "balanced",
        )
        self.assertIsInstance(
            payload["sections"],
            list,
        )
        self.assertEqual(
            payload["sections"][0]["title"],
            "Executive Summary",
        )

    def test_default_report_id_uses_decision_id(self) -> None:
        report = ExecutiveReportingEngine().generate(
            build_analysis()
        )

        self.assertEqual(
            report.report_id,
            "report-decision-42-012",
        )

    def test_rejects_invalid_analysis_type(self) -> None:
        with self.assertRaises(ReportingEngineError):
            ExecutiveReportingEngine().generate(
                analysis="invalid",
            )

    def test_rejects_naive_generated_datetime(self) -> None:
        with self.assertRaises(ReportingEngineError):
            ExecutiveReportingEngine().generate(
                build_analysis(),
                generated_at=datetime(2026, 7, 21, 22, 45),
            )

    def test_report_section_validation(self) -> None:
        with self.assertRaises(ValueError):
            ReportSection(
                title="",
                entries=(("Status", "OK"),),
            )

        with self.assertRaises(ValueError):
            ReportSection(
                title="Summary",
                entries=(),
            )


if __name__ == "__main__":
    unittest.main()

