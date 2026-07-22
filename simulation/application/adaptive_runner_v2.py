from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from simulation.application.contracts import DailyScenario
from simulation.decision.adaptive_policy_applier_v2 import (
    AdaptivePolicyApplierV2,
)
from simulation.decision.adaptive_policy_v2 import (
    AdaptivePolicyEngineV2,
)
from simulation.engines.economic_sanity_v2 import (
    EconomicAssumptions,
    EconomicSanityEngineV2,
)
from simulation.engines.sales_v2 import SalesEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2
from simulation.infrastructure.world_repository import (
    JsonWorldRepository,
)
from simulation.ml.pre_decision_snapshot_v2 import (
    PreDecisionSnapshotBuilderV2,
)


class AdaptiveRunnerV2Error(RuntimeError):
    """Raised when the adaptive annual simulation cannot complete."""


class AdaptiveSimulationRunnerV2:
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
        repository = JsonWorldRepository()
        world = repository.load(self.world_path)

        if not self.scenario_path.is_file():
            raise AdaptiveRunnerV2Error(
                f"Scenario file not found: {self.scenario_path}"
            )

        scenarios = pd.read_csv(self.scenario_path)
        if len(scenarios) < days:
            raise AdaptiveRunnerV2Error(
                f"Only {len(scenarios)} scenarios available."
            )

        decision_engine = AdaptivePolicyEngineV2()
        policy_applier = AdaptivePolicyApplierV2(world)
        sales_engine = SalesEngineV2(seed=self.seed)
        supplier_engine = SupplierEngineV2(
            seed=self.seed + 101
        )
        sanity_engine = EconomicSanityEngineV2(
            EconomicAssumptions()
        )
        snapshot_builder = PreDecisionSnapshotBuilderV2(
            trailing_window_days=7
        )

        product_index = {
            item.sku_id: item for item in world.products
        }

        decision_rows: list[dict[str, Any]] = []
        action_rows: list[dict[str, Any]] = []
        daily_rows: list[dict[str, Any]] = []
        sales_rows: list[dict[str, Any]] = []
        stockout_rows: list[dict[str, Any]] = []
        order_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []

        cumulative_revenue = 0.0
        cumulative_cogs = 0.0
        cumulative_procurement = 0.0
        cumulative_logistics = 0.0
        cumulative_stockout = 0.0
        cumulative_holding = 0.0

        initial_on_hand = sum(
            item.on_hand for item in world.inventory
        )

        for index in range(days):
            scenario = DailyScenario.from_mapping(
                scenarios.iloc[index].to_dict()
            )

            # Deliveries due today are applied before observation.
            receipts = supplier_engine.receive_due_orders(
                world,
                scenario,
            )

            # Leakage-safe snapshot: post-receipt, pre-decision,
            # pre-sales and pre-new-orders.
            snapshot = snapshot_builder.build(
                world=world,
                scenario=scenario,
                trailing_metrics=daily_rows,
                episode_seed=self.seed,
            )
            snapshot_rows.append(snapshot.to_dict())

            decision = decision_engine.choose(
                world=world,
                scenario=scenario,
                trailing_metrics=daily_rows,
            )
            decision_rows.append(decision.to_dict())

            actions = policy_applier.apply(
                world,
                decision.selected_policy,
            )
            for action in actions:
                action["simulation_day"] = (
                    scenario.simulation_day
                )
                action["date"] = scenario.synthetic_date
                action["snapshot_id"] = snapshot.snapshot_id
            action_rows.extend(actions)

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
            order_rows.extend(
                event.to_dict() for event in orders
            )
            receipt_rows.extend(
                event.to_dict() for event in receipts
            )

            daily_procurement = sum(
                event.procurement_cost for event in receipts
            )
            daily_logistics = sum(
                event.logistics_cost for event in receipts
            )
            daily_stockout = sum(
                event.penalty_cost
                for event in sales_result["stockout_events"]
            )
            daily_holding = sum(
                item.on_hand
                * product_index[item.sku_id].holding_cost_per_unit_day
                for item in world.inventory
            )

            cumulative_revenue += sales_result[
                "realized_revenue"
            ]
            cumulative_cogs += sales_result[
                "cost_of_goods_sold"
            ]
            cumulative_procurement += daily_procurement
            cumulative_logistics += daily_logistics
            cumulative_stockout += daily_stockout
            cumulative_holding += daily_holding

            world.simulation_day = scenario.simulation_day
            world.current_date = scenario.synthetic_date
            world.metadata["world_status"] = (
                "ADAPTIVE_POLICY_ADVANCED"
            )
            world.metadata["adaptive_policy_version"] = (
                "2.0.0"
            )

            inventory_value = sum(
                item.on_hand
                * product_index[item.sku_id].unit_cost
                for item in world.inventory
            )

            sanity = sanity_engine.evaluate(
                financial_kpis={
                    "realized_revenue": cumulative_revenue,
                    "cost_of_goods_sold": cumulative_cogs,
                    "average_inventory_value": inventory_value,
                    "logistics_cost": cumulative_logistics,
                    "procurement_cost": cumulative_procurement,
                    "stockout_penalty_cost": cumulative_stockout,
                },
                sold_units=sum(
                    row["sold_units"] for row in sales_rows
                ),
            )

            daily_rows.append(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "simulation_day": scenario.simulation_day,
                    "date": scenario.synthetic_date,
                    "selected_policy": (
                        decision.selected_policy
                    ),
                    "requested_units": sales_result[
                        "requested_units"
                    ],
                    "sold_units": sales_result["sold_units"],
                    "lost_units": sales_result["lost_units"],
                    "fill_rate": sales_result["fill_rate"],
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
                    "cumulative_revenue": round(
                        cumulative_revenue,
                        2,
                    ),
                    "calibrated_net_operating_profit": (
                        sanity.calibrated_net_operating_profit
                    ),
                    "economic_sanity_status": sanity.status,
                }
            )

            world.validate()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        final_world_path = (
            self.output_dir
            / f"world_state_adaptive_day_{days:03d}.json"
        )
        repository.save(world, final_world_path)

        outputs = {
            "decision_history": (
                self.output_dir / "decision_history_v2.csv"
            ),
            "policy_actions": (
                self.output_dir / "adaptive_policy_actions_v2.csv"
            ),
            "daily_kpis": (
                self.output_dir / "adaptive_daily_kpis_v2.csv"
            ),
            "sales_events": (
                self.output_dir / "adaptive_sales_events_v2.csv"
            ),
            "stockout_events": (
                self.output_dir / "adaptive_stockout_events_v2.csv"
            ),
            "purchase_orders": (
                self.output_dir / "adaptive_purchase_orders_v2.csv"
            ),
            "supplier_receipts": (
                self.output_dir / "adaptive_supplier_receipts_v2.csv"
            ),
            "pre_decision_snapshots": (
                self.output_dir / "pre_decision_snapshots_v2.jsonl"
            ),
        }

        pd.DataFrame(decision_rows).to_csv(
            outputs["decision_history"],
            index=False,
        )
        pd.DataFrame(action_rows).to_csv(
            outputs["policy_actions"],
            index=False,
        )
        pd.DataFrame(daily_rows).to_csv(
            outputs["daily_kpis"],
            index=False,
        )
        pd.DataFrame(sales_rows).to_csv(
            outputs["sales_events"],
            index=False,
        )
        pd.DataFrame(stockout_rows).to_csv(
            outputs["stockout_events"],
            index=False,
        )
        pd.DataFrame(order_rows).to_csv(
            outputs["purchase_orders"],
            index=False,
        )
        pd.DataFrame(receipt_rows).to_csv(
            outputs["supplier_receipts"],
            index=False,
        )

        with outputs["pre_decision_snapshots"].open(
            "w",
            encoding="utf-8",
        ) as handle:
            for row in snapshot_rows:
                handle.write(
                    json.dumps(
                        row,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                handle.write("\n")

        requested = sum(
            row["requested_units"] for row in daily_rows
        )
        sold = sum(row["sold_units"] for row in daily_rows)
        lost = sum(row["lost_units"] for row in daily_rows)
        total_received = sum(
            row["received_units"] for row in receipt_rows
        )
        ending_on_hand = sum(
            item.on_hand for item in world.inventory
        )

        expected_ending = (
            initial_on_hand + total_received - sold
        )
        if expected_ending != ending_on_hand:
            raise AdaptiveRunnerV2Error(
                "Inventory conservation failed: "
                f"expected {expected_ending}, got {ending_on_hand}."
            )

        if len(snapshot_rows) != days:
            raise AdaptiveRunnerV2Error(
                "Snapshot count mismatch: "
                f"expected {days}, got {len(snapshot_rows)}."
            )

        final_sanity = sanity_engine.evaluate(
            financial_kpis={
                "realized_revenue": cumulative_revenue,
                "cost_of_goods_sold": cumulative_cogs,
                "average_inventory_value": sum(
                    item.on_hand
                    * product_index[item.sku_id].unit_cost
                    for item in world.inventory
                ),
                "logistics_cost": cumulative_logistics,
                "procurement_cost": cumulative_procurement,
                "stockout_penalty_cost": cumulative_stockout,
            },
            sold_units=sold,
        )

        policy_counts = (
            pd.Series(
                [row["selected_policy"] for row in decision_rows]
            )
            .value_counts()
            .to_dict()
        )

        return {
            "days_processed": days,
            "requested_units": requested,
            "sold_units": sold,
            "lost_units": lost,
            "overall_fill_rate": round(
                sold / requested if requested > 0 else 1.0,
                6,
            ),
            "realized_revenue": round(
                cumulative_revenue,
                2,
            ),
            "gross_margin": round(
                cumulative_revenue - cumulative_cogs,
                2,
            ),
            "calibrated_net_operating_profit": (
                final_sanity.calibrated_net_operating_profit
            ),
            "economic_sanity_status": final_sanity.status,
            "policy_day_counts": policy_counts,
            "ending_on_hand_units": ending_on_hand,
            "ending_in_transit_units": sum(
                item.in_transit for item in world.inventory
            ),
            "orders_created": len(order_rows),
            "receipts_created": len(receipt_rows),
            "snapshots_created": len(snapshot_rows),
            "inventory_conservation": "PASSED",
            "domain_validation": "PASSED",
            "future_information_used": False,
            "final_world_path": str(
                final_world_path.resolve()
            ),
            "decision_history_path": str(
                outputs["decision_history"].resolve()
            ),
            "pre_decision_snapshots_path": str(
                outputs["pre_decision_snapshots"].resolve()
            ),
        }
