from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from simulation.application.contracts import DailyScenario
from simulation.engines.sales_v2 import SalesEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2
from simulation.infrastructure.world_repository import (
    JsonWorldRepository,
)


class SalesRunnerV2Error(RuntimeError):
    """Raised when the integrated sales run cannot proceed."""


class SalesSimulationRunnerV2:
    def __init__(
        self,
        world_path: str | Path,
        scenario_path: str | Path,
        output_dir: str | Path,
        seed: int = 42,
    ) -> None:
        self.world_path = Path(world_path)
        self.scenario_path = Path(scenario_path)
        self.output_dir = Path(output_dir)
        self.seed = seed

    def run(self, days: int) -> dict[str, Any]:
        if days <= 0:
            raise SalesRunnerV2Error(
                "days must be greater than zero."
            )

        repository = JsonWorldRepository()
        world = repository.load(self.world_path)

        if not self.scenario_path.is_file():
            raise SalesRunnerV2Error(
                f"Scenario file not found: {self.scenario_path}"
            )

        scenarios = pd.read_csv(self.scenario_path)
        if len(scenarios) < days:
            raise SalesRunnerV2Error(
                f"Only {len(scenarios)} scenarios available."
            )

        sales_engine = SalesEngineV2(seed=self.seed)
        supplier_engine = SupplierEngineV2(seed=self.seed + 101)

        sales_rows: list[dict[str, Any]] = []
        stockout_rows: list[dict[str, Any]] = []
        order_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []
        daily_rows: list[dict[str, Any]] = []

        initial_on_hand = sum(
            item.on_hand for item in world.inventory
        )

        for index in range(days):
            scenario = DailyScenario.from_mapping(
                scenarios.iloc[index].to_dict()
            )

            receipts = supplier_engine.receive_due_orders(
                world,
                scenario,
            )

            sales_result = sales_engine.apply(
                world,
                scenario,
            )

            orders = supplier_engine.create_orders(
                world,
                scenario,
            )

            sales_rows.extend(
                item.to_dict()
                for item in sales_result["sales_events"]
            )
            stockout_rows.extend(
                item.to_dict()
                for item in sales_result["stockout_events"]
            )
            order_rows.extend(
                item.to_dict() for item in orders
            )
            receipt_rows.extend(
                item.to_dict() for item in receipts
            )

            world.simulation_day = scenario.simulation_day
            world.current_date = scenario.synthetic_date
            world.metadata["world_status"] = (
                "SALES_STOCKOUT_ADVANCED"
            )
            world.metadata["sales_engine_version"] = "2.0.0"

            world.financials.revenue += sales_result[
                "realized_revenue"
            ]
            world.financials.cost_of_goods_sold += sales_result[
                "cost_of_goods_sold"
            ]
            world.financials.stockout_cost += sum(
                event.penalty_cost
                for event in sales_result["stockout_events"]
            )
            world.financials.gross_profit = (
                world.financials.revenue
                - world.financials.cost_of_goods_sold
                - world.financials.stockout_cost
            )

            daily_rows.append(
                {
                    "simulation_day": scenario.simulation_day,
                    "date": scenario.synthetic_date,
                    "requested_units": sales_result[
                        "requested_units"
                    ],
                    "sold_units": sales_result["sold_units"],
                    "lost_units": sales_result["lost_units"],
                    "fill_rate": sales_result["fill_rate"],
                    "realized_revenue": sales_result[
                        "realized_revenue"
                    ],
                    "lost_revenue": sales_result[
                        "lost_revenue"
                    ],
                    "gross_margin": sales_result[
                        "gross_margin"
                    ],
                    "stockout_events": len(
                        sales_result["stockout_events"]
                    ),
                    "orders_created": len(orders),
                    "receipts_created": len(receipts),
                    "ending_on_hand_units": sum(
                        item.on_hand
                        for item in world.inventory
                    ),
                    "ending_in_transit_units": sum(
                        item.in_transit
                        for item in world.inventory
                    ),
                }
            )

            world.validate()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        final_world_path = (
            self.output_dir
            / f"world_state_v2_day_{days:03d}.json"
        )
        repository.save(world, final_world_path)

        sales_path = self.output_dir / "sales_events_v2.csv"
        stockout_path = (
            self.output_dir / "stockout_events_v2.csv"
        )
        orders_path = self.output_dir / "purchase_orders_v2.csv"
        receipts_path = (
            self.output_dir / "supplier_receipts_v2.csv"
        )
        daily_path = self.output_dir / "sales_daily_metrics_v2.csv"

        pd.DataFrame(sales_rows).to_csv(
            sales_path,
            index=False,
        )
        pd.DataFrame(stockout_rows).to_csv(
            stockout_path,
            index=False,
        )
        pd.DataFrame(order_rows).to_csv(
            orders_path,
            index=False,
        )
        pd.DataFrame(receipt_rows).to_csv(
            receipts_path,
            index=False,
        )
        pd.DataFrame(daily_rows).to_csv(
            daily_path,
            index=False,
        )

        total_received = sum(
            row["received_units"] for row in receipt_rows
        )
        total_sold = sum(
            row["sold_units"] for row in daily_rows
        )
        ending_on_hand = sum(
            item.on_hand for item in world.inventory
        )

        expected_ending = (
            initial_on_hand + total_received - total_sold
        )
        if expected_ending != ending_on_hand:
            raise SalesRunnerV2Error(
                "Inventory conservation failed: "
                f"expected {expected_ending}, got {ending_on_hand}."
            )

        requested_units = sum(
            row["requested_units"] for row in daily_rows
        )
        sold_units = sum(
            row["sold_units"] for row in daily_rows
        )
        lost_units = sum(
            row["lost_units"] for row in daily_rows
        )

        return {
            "days_processed": days,
            "initial_on_hand_units": initial_on_hand,
            "ending_on_hand_units": ending_on_hand,
            "ending_in_transit_units": sum(
                item.in_transit for item in world.inventory
            ),
            "requested_units": requested_units,
            "sold_units": sold_units,
            "lost_units": lost_units,
            "overall_fill_rate": round(
                sold_units / requested_units
                if requested_units > 0 else 1.0,
                6,
            ),
            "sales_event_count": len(sales_rows),
            "stockout_event_count": len(stockout_rows),
            "realized_revenue": round(
                sum(
                    row["realized_revenue"]
                    for row in daily_rows
                ),
                2,
            ),
            "lost_revenue": round(
                sum(
                    row["lost_revenue"]
                    for row in daily_rows
                ),
                2,
            ),
            "orders_created": len(order_rows),
            "receipts_created": len(receipt_rows),
            "inventory_conservation": "PASSED",
            "domain_validation": "PASSED",
            "final_world_path": str(
                final_world_path.resolve()
            ),
            "daily_metrics_path": str(daily_path.resolve()),
        }
