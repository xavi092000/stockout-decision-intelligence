from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from simulation.application.contracts import DailyScenario
from simulation.engines.economic_sanity_v2 import (
    EconomicAssumptions,
    EconomicSanityEngineV2,
)
from simulation.engines.sales_v2 import SalesEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2
from simulation.infrastructure.world_repository import JsonWorldRepository


class OrchestratorV2Error(RuntimeError):
    """Raised when the annual simulation cannot complete safely."""


class SimulationOrchestratorV2:
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

    def run(self, days: int = 365) -> dict[str, Any]:
        if days <= 0:
            raise OrchestratorV2Error("days must be greater than zero.")

        repository = JsonWorldRepository()
        world = repository.load(self.world_path)

        if not self.scenario_path.is_file():
            raise OrchestratorV2Error(
                f"Scenario file not found: {self.scenario_path}"
            )

        scenarios = pd.read_csv(self.scenario_path)
        if len(scenarios) < days:
            raise OrchestratorV2Error(
                f"Only {len(scenarios)} scenarios available for {days} days."
            )

        sales_engine = SalesEngineV2(seed=self.seed)
        supplier_engine = SupplierEngineV2(seed=self.seed + 101)
        sanity_engine = EconomicSanityEngineV2(
            assumptions=EconomicAssumptions()
        )

        product_index = {
            item.sku_id: item for item in world.products
        }

        sales_rows: list[dict[str, Any]] = []
        stockout_rows: list[dict[str, Any]] = []
        order_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []
        daily_rows: list[dict[str, Any]] = []

        initial_on_hand = sum(item.on_hand for item in world.inventory)
        cumulative_revenue = 0.0
        cumulative_cogs = 0.0
        cumulative_stockout_penalty = 0.0
        cumulative_procurement = 0.0
        cumulative_logistics = 0.0
        cumulative_holding = 0.0

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
                event.to_dict()
                for event in sales_result["sales_events"]
            )
            stockout_rows.extend(
                event.to_dict()
                for event in sales_result["stockout_events"]
            )
            receipt_rows.extend(
                event.to_dict()
                for event in receipts
            )
            order_rows.extend(
                event.to_dict()
                for event in orders
            )

            daily_procurement = sum(
                event.procurement_cost for event in receipts
            )
            daily_logistics = sum(
                event.logistics_cost for event in receipts
            )
            daily_stockout_penalty = sum(
                event.penalty_cost
                for event in sales_result["stockout_events"]
            )
            daily_holding = sum(
                position.on_hand
                * product_index[position.sku_id].holding_cost_per_unit_day
                for position in world.inventory
            )

            cumulative_revenue += sales_result["realized_revenue"]
            cumulative_cogs += sales_result["cost_of_goods_sold"]
            cumulative_stockout_penalty += daily_stockout_penalty
            cumulative_procurement += daily_procurement
            cumulative_logistics += daily_logistics
            cumulative_holding += daily_holding

            world.financials.revenue = round(cumulative_revenue, 2)
            world.financials.cost_of_goods_sold = round(cumulative_cogs, 2)
            world.financials.stockout_cost = round(
                cumulative_stockout_penalty,
                2,
            )
            world.financials.procurement_cost = round(
                cumulative_procurement,
                2,
            )
            world.financials.logistics_cost = round(
                cumulative_logistics,
                2,
            )
            world.financials.holding_cost = round(
                cumulative_holding,
                2,
            )
            world.financials.gross_profit = round(
                cumulative_revenue - cumulative_cogs,
                2,
            )

            world.simulation_day = scenario.simulation_day
            world.current_date = scenario.synthetic_date
            world.metadata["world_status"] = "ORCHESTRATED_365"
            world.metadata["orchestrator_version"] = "2.0.0"

            average_inventory_value = sum(
                position.on_hand
                * product_index[position.sku_id].unit_cost
                for position in world.inventory
            )

            sanity_report = sanity_engine.evaluate(
                financial_kpis={
                    "realized_revenue": cumulative_revenue,
                    "cost_of_goods_sold": cumulative_cogs,
                    "average_inventory_value": average_inventory_value,
                    "logistics_cost": cumulative_logistics,
                    "procurement_cost": cumulative_procurement,
                    "stockout_penalty_cost": cumulative_stockout_penalty,
                },
                sold_units=sum(
                    row["sold_units"] for row in sales_rows
                ),
            )

            daily_rows.append(
                {
                    "simulation_day": scenario.simulation_day,
                    "date": scenario.synthetic_date,
                    "requested_units": sales_result["requested_units"],
                    "sold_units": sales_result["sold_units"],
                    "lost_units": sales_result["lost_units"],
                    "fill_rate": sales_result["fill_rate"],
                    "realized_revenue": sales_result["realized_revenue"],
                    "lost_revenue": sales_result["lost_revenue"],
                    "orders_created": len(orders),
                    "receipts_created": len(receipts),
                    "ending_on_hand_units": sum(
                        item.on_hand for item in world.inventory
                    ),
                    "ending_in_transit_units": sum(
                        item.in_transit for item in world.inventory
                    ),
                    "open_orders": sum(
                        1
                        for order in world.purchase_orders
                        if order.status in {
                            "OPEN",
                            "PARTIALLY_RECEIVED",
                        }
                    ),
                    "cumulative_revenue": round(
                        cumulative_revenue,
                        2,
                    ),
                    "cumulative_cogs": round(
                        cumulative_cogs,
                        2,
                    ),
                    "cumulative_procurement_cost": round(
                        cumulative_procurement,
                        2,
                    ),
                    "cumulative_logistics_cost": round(
                        cumulative_logistics,
                        2,
                    ),
                    "cumulative_holding_cost": round(
                        cumulative_holding,
                        2,
                    ),
                    "calibrated_net_operating_profit": (
                        sanity_report.calibrated_net_operating_profit
                    ),
                    "economic_sanity_status": sanity_report.status,
                }
            )

            world.validate()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        final_world_path = (
            self.output_dir
            / f"world_state_v2_day_{days:03d}.json"
        )
        repository.save(world, final_world_path)

        pd.DataFrame(sales_rows).to_csv(
            self.output_dir / "sales_events_365_v2.csv",
            index=False,
        )
        pd.DataFrame(stockout_rows).to_csv(
            self.output_dir / "stockout_events_365_v2.csv",
            index=False,
        )
        pd.DataFrame(order_rows).to_csv(
            self.output_dir / "purchase_orders_365_v2.csv",
            index=False,
        )
        pd.DataFrame(receipt_rows).to_csv(
            self.output_dir / "supplier_receipts_365_v2.csv",
            index=False,
        )
        pd.DataFrame(daily_rows).to_csv(
            self.output_dir / "daily_kpis_365_v2.csv",
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
            raise OrchestratorV2Error(
                "Inventory conservation failed: "
                f"expected {expected_ending}, got {ending_on_hand}."
            )

        final_sanity = sanity_engine.evaluate(
            financial_kpis={
                "realized_revenue": cumulative_revenue,
                "cost_of_goods_sold": cumulative_cogs,
                "average_inventory_value": sum(
                    position.on_hand
                    * product_index[position.sku_id].unit_cost
                    for position in world.inventory
                ),
                "logistics_cost": cumulative_logistics,
                "procurement_cost": cumulative_procurement,
                "stockout_penalty_cost": cumulative_stockout_penalty,
            },
            sold_units=total_sold,
        )

        return {
            "days_processed": days,
            "initial_on_hand_units": initial_on_hand,
            "ending_on_hand_units": ending_on_hand,
            "ending_in_transit_units": sum(
                item.in_transit for item in world.inventory
            ),
            "requested_units": sum(
                row["requested_units"] for row in daily_rows
            ),
            "sold_units": total_sold,
            "lost_units": sum(
                row["lost_units"] for row in daily_rows
            ),
            "overall_fill_rate": round(
                total_sold
                / max(
                    1,
                    sum(
                        row["requested_units"]
                        for row in daily_rows
                    ),
                ),
                6,
            ),
            "orders_created": len(order_rows),
            "receipts_created": len(receipt_rows),
            "open_orders": sum(
                1
                for order in world.purchase_orders
                if order.status in {
                    "OPEN",
                    "PARTIALLY_RECEIVED",
                }
            ),
            "completed_orders": sum(
                1
                for order in world.purchase_orders
                if order.status == "RECEIVED"
            ),
            "realized_revenue": round(cumulative_revenue, 2),
            "cost_of_goods_sold": round(cumulative_cogs, 2),
            "gross_margin": round(
                cumulative_revenue - cumulative_cogs,
                2,
            ),
            "procurement_cost": round(cumulative_procurement, 2),
            "logistics_cost": round(cumulative_logistics, 2),
            "holding_cost": round(cumulative_holding, 2),
            "calibrated_net_operating_profit": (
                final_sanity.calibrated_net_operating_profit
            ),
            "economic_sanity_status": final_sanity.status,
            "inventory_conservation": "PASSED",
            "domain_validation": "PASSED",
            "final_world_path": str(final_world_path.resolve()),
            "daily_kpis_path": str(
                (self.output_dir / "daily_kpis_365_v2.csv").resolve()
            ),
        }
