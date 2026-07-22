from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from simulation.decision_intelligence.models import (
    DecisionAnalysis,
    GovernanceStatus,
    RiskLevel,
)


class ReportingEngineError(RuntimeError):
    """Raised when an executive report cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    entries: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Report section title cannot be empty.")

        if not self.entries:
            raise ValueError(
                "A report section requires at least one entry."
            )

        cleaned_entries: list[tuple[str, str]] = []

        for raw_key, raw_value in self.entries:
            key = str(raw_key).strip()
            value = str(raw_value).strip()

            if not key:
                raise ValueError(
                    "Report entry labels cannot be empty."
                )

            if not value:
                raise ValueError(
                    "Report entry values cannot be empty."
                )

            cleaned_entries.append((key, value))

        object.__setattr__(
            self,
            "entries",
            tuple(cleaned_entries),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "entries": {
                key: value
                for key, value in self.entries
            },
        }


@dataclass(frozen=True, slots=True)
class ExecutiveDecisionReport:
    report_id: str
    generated_at: str
    decision_id: str
    selected_policy: str
    headline: str
    recommendation: str
    recommendation_status: str
    sections: tuple[ReportSection, ...]

    def __post_init__(self) -> None:
        required_text = {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "decision_id": self.decision_id,
            "selected_policy": self.selected_policy,
            "headline": self.headline,
            "recommendation": self.recommendation,
            "recommendation_status": self.recommendation_status,
        }

        for field_name, value in required_text.items():
            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty."
                )

        if not self.sections:
            raise ValueError(
                "ExecutiveDecisionReport requires report sections."
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sections"] = [
            section.to_dict()
            for section in self.sections
        ]
        return payload

    def to_markdown(self) -> str:
        lines = [
            f"# {self.headline}",
            "",
            f"**Report ID:** {self.report_id}",
            f"**Generated:** {self.generated_at}",
            f"**Decision ID:** {self.decision_id}",
            f"**Selected policy:** {self.selected_policy}",
            f"**Recommendation status:** "
            f"{self.recommendation_status}",
            "",
            "## Executive Recommendation",
            "",
            self.recommendation,
        ]

        for section in self.sections:
            lines.extend(
                [
                    "",
                    f"## {section.title}",
                    "",
                ]
            )

            for key, value in section.entries:
                lines.append(f"- **{key}:** {value}")

        return "\n".join(lines) + "\n"


class ExecutiveReportingEngine:
    """
    Convert a DecisionAnalysis into a deterministic executive report.

    The engine does not recalculate confidence, risk, economics,
    counterfactuals, or governance. It only communicates results already
    produced by authoritative platform components.
    """

    def generate(
        self,
        analysis: DecisionAnalysis,
        *,
        report_id: str | None = None,
        generated_at: datetime | None = None,
    ) -> ExecutiveDecisionReport:
        if not isinstance(analysis, DecisionAnalysis):
            raise ReportingEngineError(
                "analysis must be a DecisionAnalysis."
            )

        timestamp = generated_at or datetime.now(timezone.utc)

        if timestamp.tzinfo is None:
            raise ReportingEngineError(
                "generated_at must include timezone information."
            )

        selected_policy = analysis.trace.selected_policy
        governance_status = self._governance_status(analysis)

        headline, recommendation, recommendation_status = (
            self._recommendation(
                analysis=analysis,
                governance_status=governance_status,
            )
        )

        sections = (
            self._executive_summary(
                analysis=analysis,
                governance_status=governance_status,
            ),
            self._business_impact(analysis),
            self._confidence_and_risk(analysis),
            self._governance_summary(analysis),
            self._reproducibility(analysis),
            self._technical_trace(analysis),
        )

        resolved_report_id = (
            report_id.strip()
            if report_id is not None
            and report_id.strip()
            else f"report-{analysis.metadata.decision_id}"
        )

        return ExecutiveDecisionReport(
            report_id=resolved_report_id,
            generated_at=timestamp.isoformat(),
            decision_id=analysis.metadata.decision_id,
            selected_policy=selected_policy,
            headline=headline,
            recommendation=recommendation,
            recommendation_status=recommendation_status,
            sections=sections,
        )

    @staticmethod
    def _governance_status(
        analysis: DecisionAnalysis,
    ) -> GovernanceStatus:
        if analysis.governance is None:
            return GovernanceStatus.UNKNOWN

        return analysis.governance.status

    def _recommendation(
        self,
        *,
        analysis: DecisionAnalysis,
        governance_status: GovernanceStatus,
    ) -> tuple[str, str, str]:
        policy = analysis.trace.selected_policy
        risk_level = (
            analysis.risk.overall_risk
            if analysis.risk is not None
            else None
        )

        opportunity_cost = (
            analysis.counterfactual.opportunity_cost
            if analysis.counterfactual is not None
            else 0.0
        )

        if governance_status == GovernanceStatus.REJECTED:
            return (
                f"Deployment rejected for policy {policy}",
                (
                    f"Do not deploy policy {policy}. Governance rejected "
                    "the decision because one or more mandatory controls "
                    "were not satisfied."
                ),
                "DO_NOT_DEPLOY",
            )

        if governance_status == GovernanceStatus.PENDING:
            return (
                f"Human review required for policy {policy}",
                (
                    f"Hold deployment of policy {policy} until an "
                    "authorized reviewer resolves the outstanding "
                    "confidence, risk, approval, or registry controls."
                ),
                "REVIEW_REQUIRED",
            )

        if risk_level == RiskLevel.CRITICAL:
            return (
                f"Critical risk detected for policy {policy}",
                (
                    f"Do not automatically execute policy {policy}. "
                    "Escalate the decision for immediate operational "
                    "and model-risk review."
                ),
                "ESCALATE",
            )

        if opportunity_cost > 0.0:
            best_alternative = (
                analysis.counterfactual.best_alternative
                if analysis.counterfactual is not None
                else None
            )

            return (
                f"Policy {policy} approved with an economic trade-off",
                (
                    f"Policy {policy} may proceed under governance, but "
                    f"{best_alternative} has an estimated business-value "
                    f"advantage of {opportunity_cost:,.2f}. Record the "
                    "trade-off and monitor realized performance."
                ),
                "APPROVE_WITH_MONITORING",
            )

        if governance_status == GovernanceStatus.APPROVED:
            return (
                f"Policy {policy} approved for execution",
                (
                    f"Proceed with policy {policy} under normal "
                    "monitoring. The decision satisfies the configured "
                    "governance controls and no positive economic "
                    "opportunity cost was identified."
                ),
                "APPROVED",
            )

        return (
            f"Informational analysis for policy {policy}",
            (
                f"Policy {policy} has been analyzed, but no formal "
                "governance decision is attached. Treat this report as "
                "informational until registry and approval metadata are "
                "available."
            ),
            "INFORMATIONAL",
        )

    @staticmethod
    def _executive_summary(
        *,
        analysis: DecisionAnalysis,
        governance_status: GovernanceStatus,
    ) -> ReportSection:
        confidence = (
            analysis.confidence.confidence_level.value
            if analysis.confidence is not None
            else "UNAVAILABLE"
        )

        risk = (
            analysis.risk.overall_risk.value
            if analysis.risk is not None
            else "UNAVAILABLE"
        )

        return ReportSection(
            title="Executive Summary",
            entries=(
                (
                    "Selected policy",
                    analysis.trace.selected_policy,
                ),
                (
                    "Governance status",
                    governance_status.value,
                ),
                (
                    "Confidence level",
                    confidence,
                ),
                (
                    "Overall risk",
                    risk,
                ),
                (
                    "Decision rationale",
                    analysis.trace.reason,
                ),
            ),
        )

    @staticmethod
    def _business_impact(
        analysis: DecisionAnalysis,
    ) -> ReportSection:
        if analysis.counterfactual is None:
            return ReportSection(
                title="Business Impact",
                entries=(
                    (
                        "Counterfactual analysis",
                        "Unavailable",
                    ),
                    (
                        "Opportunity cost",
                        "Unavailable",
                    ),
                    (
                        "Best rejected alternative",
                        "Unavailable",
                    ),
                ),
            )

        counterfactual = analysis.counterfactual

        entries: list[tuple[str, str]] = [
            (
                "Opportunity cost",
                f"{counterfactual.opportunity_cost:,.2f}",
            ),
            (
                "Best rejected alternative",
                counterfactual.best_alternative or "None",
            ),
            (
                "Alternatives evaluated",
                str(len(counterfactual.alternatives)),
            ),
        ]

        for outcome in counterfactual.alternatives:
            entries.append(
                (
                    f"{outcome.policy_name} business-value delta",
                    f"{outcome.business_value_delta:+,.2f}",
                )
            )

        return ReportSection(
            title="Business Impact",
            entries=tuple(entries),
        )

    @staticmethod
    def _confidence_and_risk(
        analysis: DecisionAnalysis,
    ) -> ReportSection:
        confidence = analysis.confidence
        risk = analysis.risk

        entries: list[tuple[str, str]] = []

        if confidence is None:
            entries.extend(
                [
                    (
                        "Confidence status",
                        "Unavailable",
                    ),
                    (
                        "Confidence score",
                        "Unavailable",
                    ),
                ]
            )
        else:
            entries.extend(
                [
                    (
                        "Confidence level",
                        confidence.confidence_level.value,
                    ),
                    (
                        "Confidence score",
                        f"{confidence.confidence_score:.4f}",
                    ),
                    (
                        "Predicted probability",
                        f"{confidence.predicted_probability:.4f}",
                    ),
                    (
                        "Probability margin",
                        f"{confidence.probability_margin:.4f}",
                    ),
                    (
                        "Normalized entropy",
                        f"{confidence.normalized_entropy:.4f}",
                    ),
                ]
            )

        if risk is None:
            entries.extend(
                [
                    (
                        "Risk status",
                        "Unavailable",
                    ),
                    (
                        "Risk score",
                        "Unavailable",
                    ),
                ]
            )
        else:
            entries.extend(
                [
                    (
                        "Overall risk",
                        risk.overall_risk.value,
                    ),
                    (
                        "Operational risk",
                        risk.operational_risk.value,
                    ),
                    (
                        "Economic risk",
                        risk.economic_risk.value,
                    ),
                    (
                        "Model risk",
                        risk.model_risk.value,
                    ),
                    (
                        "Data-quality risk",
                        risk.data_quality_risk.value,
                    ),
                    (
                        "Risk score",
                        (
                            f"{risk.risk_score:.4f}"
                            if risk.risk_score is not None
                            else "Unavailable"
                        ),
                    ),
                ]
            )

        return ReportSection(
            title="Confidence and Risk",
            entries=tuple(entries),
        )

    @staticmethod
    def _governance_summary(
        analysis: DecisionAnalysis,
    ) -> ReportSection:
        governance = analysis.governance

        if governance is None:
            return ReportSection(
                title="Governance",
                entries=(
                    (
                        "Status",
                        GovernanceStatus.UNKNOWN.value,
                    ),
                    (
                        "Approved",
                        "No",
                    ),
                    (
                        "Registry reference",
                        "Unavailable",
                    ),
                ),
            )

        return ReportSection(
            title="Governance",
            entries=(
                (
                    "Status",
                    governance.status.value,
                ),
                (
                    "Approved",
                    "Yes" if governance.approved else "No",
                ),
                (
                    "Champion",
                    "Yes" if governance.champion else "No",
                ),
                (
                    "Experiment ID",
                    governance.experiment_id or "Unavailable",
                ),
                (
                    "Model version",
                    governance.model_version or "Unavailable",
                ),
                (
                    "Policy version",
                    governance.policy_version or "Unavailable",
                ),
                (
                    "Approval date",
                    governance.approval_date or "Unavailable",
                ),
                (
                    "Evaluator",
                    governance.evaluator or "Unavailable",
                ),
                (
                    "Registry reference",
                    (
                        governance.registry_reference
                        or "Unavailable"
                    ),
                ),
            ),
        )

    @staticmethod
    def _reproducibility(
        analysis: DecisionAnalysis,
    ) -> ReportSection:
        return ReportSection(
            title="Reproducibility",
            entries=(
                (
                    "Decision ID",
                    analysis.metadata.decision_id,
                ),
                (
                    "Simulation day",
                    str(analysis.metadata.simulation_day),
                ),
                (
                    "Snapshot ID",
                    analysis.metadata.snapshot_id,
                ),
                (
                    "Episode seed",
                    str(analysis.metadata.episode_seed),
                ),
            ),
        )

    @staticmethod
    def _technical_trace(
        analysis: DecisionAnalysis,
    ) -> ReportSection:
        return ReportSection(
            title="Technical Trace",
            entries=(
                (
                    "Decision source",
                    analysis.trace.source,
                ),
                (
                    "Feature count",
                    str(analysis.trace.feature_count),
                ),
                (
                    "Latency",
                    f"{analysis.trace.latency_ms:.4f} ms",
                ),
                (
                    "Alternative policies",
                    str(len(analysis.alternatives)),
                ),
                (
                    "Analysis tags",
                    (
                        ", ".join(analysis.tags)
                        if analysis.tags
                        else "None"
                    ),
                ),
            ),
        )
