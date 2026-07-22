from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from simulation.application.contracts import DailyScenario
from simulation.engines.inventory_v2 import InventoryEngineV2
from simulation.engines.supplier_v2 import SupplierEngineV2
from simulation.infrastructure.world_repository import (
    JsonWorldRepository,
)


class SimulationRunnerV2Error(RuntimeError):
    """Raised when the integrated domain-v2 run cannot proceed."""


class SimulationRunnerV2:
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
            raise SimulationRunnerV2Error(
                "days must be greater than zero."
            )

        repository = JsonWorldRepository()
        world = repository.load(self.world_path)

        if not self.scenario_path.is_file():
            raise SimulationRunnerV2Error(
                f"Scenario file not found: {self.scenario_path}"
            )

        scenarios = pd.read_csv(self.scenario_path)
        if len(scenarios) < days:
            raise SimulationRunnerV2Error(
                f"Only {len(scenarios)} scenarios available."
            )

        inventory_engine = InventoryEngineV2(seed=self.seed)
        supplier_engine = SupplierEngineV2(seed=self.seed + 101)

        movement_rows: list[dict[str, Any]] = []
        order_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, Any]] = []

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

            inventory_result = inventory_engine.apply(
                world,
                scenario,
            )

            orders = supplier_engine.create_orders(
                world,
                scenario,
            )

            movement_rows.extend(
                item.to_dict()
                for item in inventory_result["movements"]
            )
            receipt_rows.extend(item.to_dict() for item in receipts)
            order_rows.extend(item.to_dict() for item in orders)

            world.simulation_day = scenario.simulation_day
            world.current_date = scenario.synthetic_date
            world.metadata["world_status"] = "DOMAIN_V2_ADVANCED"
            world.metadata["runner_version"] = "2.0.0"

            on_hand = sum(item.on_hand for item in world.inventory)
            in_transit = sum(
                item.in_transit for item in world.inventory
            )
            open_orders = sum(
                1
                for order in world.purchase_orders
                if order.status in {"OPEN", "PARTIALLY_RECEIVED"}
            )

            metric_rows.append(
                {
                    "simulation_day": scenario.simulation_day,
                    "date": scenario.synthetic_date,
                    "fulfilled_units": inventory_result[
                        "fulfilled_units"
                    ],
                    "unmet_units": inventory_result["unmet_units"],
                    "received_units": sum(
                        item.received_units for item in receipts
                    ),
                    "orders_created": len(orders),
                    "open_orders": open_orders,
                    "ending_on_hand_units": on_hand,
                    "ending_in_transit_units": in_transit,
                    "positions_below_reorder_point": sum(
                        1
                        for item in world.inventory
                        if item.inventory_position
                        <= item.reorder_point
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

        movements_path = self.output_dir / "inventory_movements_v2.csv"
        orders_path = self.output_dir / "purchase_orders_v2.csv"
        receipts_path = self.output_dir / "supplier_receipts_v2.csv"
        metrics_path = self.output_dir / "daily_metrics_v2.csv"

        pd.DataFrame(movement_rows).to_csv(
            movements_path,
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
        pd.DataFrame(metric_rows).to_csv(
            metrics_path,
            index=False,
        )

        total_received = sum(
            row["received_units"] for row in receipt_rows
        )
        total_fulfilled = sum(
            row["fulfilled_units"] for row in metric_rows
        )
        ending_on_hand = sum(
            item.on_hand for item in world.inventory
        )

        expected_ending = (
            initial_on_hand + total_received - total_fulfilled
        )
        if expected_ending != ending_on_hand:
            raise SimulationRunnerV2Error(
                "Inventory conservation failed: "
                f"expected {expected_ending}, got {ending_on_hand}."
            )

        return {
            "days_processed": days,
            "initial_on_hand_units": initial_on_hand,
            "ending_on_hand_units": ending_on_hand,
            "ending_in_transit_units": sum(
                item.in_transit for item in world.inventory
            ),
            "fulfilled_units": total_fulfilled,
            "unmet_units": sum(
                row["unmet_units"] for row in metric_rows
            ),
            "orders_created": len(order_rows),
            "receipts_created": len(receipt_rows),
            "received_units": total_received,
            "open_orders": sum(
                1
                for order in world.purchase_orders
                if order.status in {"OPEN", "PARTIALLY_RECEIVED"}
            ),
            "completed_orders": sum(
                1
                for order in world.purchase_orders
                if order.status == "RECEIVED"
            ),
            "inventory_conservation": "PASSED",
            "domain_validation": "PASSED",
            "final_world_path": str(final_world_path.resolve()),
            "metrics_path": str(metrics_path.resolve()),
        }
