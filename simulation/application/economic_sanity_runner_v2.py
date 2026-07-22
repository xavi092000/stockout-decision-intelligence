from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from simulation.engines.economic_sanity_v2 import (
    EconomicAssumptions,
    EconomicSanityEngineV2,
)


class EconomicSanityRunnerError(RuntimeError):
    """Raised when economic sanity inputs are missing or malformed."""


class EconomicSanityRunnerV2:
    def __init__(
        self,
        financial_summary_path: str | Path,
        sales_metrics_path: str | Path,
        output_dir: str | Path,
    ) -> None:
        self.financial_summary_path = Path(financial_summary_path)
        self.sales_metrics_path = Path(sales_metrics_path)
        self.output_dir = Path(output_dir)

    def run(self) -> dict[str, Any]:
        if not self.financial_summary_path.is_file():
            raise EconomicSanityRunnerError(
                f"Missing financial summary: "
                f"{self.financial_summary_path}"
            )
        if not self.sales_metrics_path.is_file():
            raise EconomicSanityRunnerError(
                f"Missing sales metrics: {self.sales_metrics_path}"
            )

        financial_summary = json.loads(
            self.financial_summary_path.read_text(encoding="utf-8")
        )
        sales_metrics = pd.read_csv(self.sales_metrics_path)

        if "financial_kpis" not in financial_summary:
            raise EconomicSanityRunnerError(
                "financial_kpis missing from financial summary."
            )
        if "sold_units" not in sales_metrics.columns:
            raise EconomicSanityRunnerError(
                "sold_units missing from sales metrics."
            )

        sold_units = int(
            pd.to_numeric(
                sales_metrics["sold_units"],
                errors="coerce",
            ).fillna(0).sum()
        )

        assumptions = EconomicAssumptions()
        report = EconomicSanityEngineV2(
            assumptions=assumptions
        ).evaluate(
            financial_kpis=financial_summary["financial_kpis"],
            sold_units=sold_units,
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        result = {
            "status": report.status,
            "schema_version": "2.0.0",
            "sold_units": sold_units,
            "assumptions": assumptions.to_dict(),
            "economic_sanity": report.to_dict(),
            "original_operating_cost": financial_summary[
                "financial_kpis"
            ]["operating_cost"],
            "operating_cost_model": (
                "revenue_share_plus_per_unit_variable_cost"
            ),
            "holding_cost_model": (
                "target_share_of_average_inventory_value"
            ),
            "source_revenue_reused": True,
            "duplicate_revenue_calculation": False,
        }

        json_path = (
            self.output_dir / "economic_sanity_report_v2.json"
        )
        json_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        pd.DataFrame(
            [
                {"metric": key, "value": value}
                for key, value in report.to_dict().items()
                if key != "violations"
            ]
        ).to_csv(
            self.output_dir / "economic_sanity_kpis_v2.csv",
            index=False,
        )

        return result
