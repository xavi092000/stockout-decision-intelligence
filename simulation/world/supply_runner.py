from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json

import pandas as pd

from simulation.world.inventory_engine import DailyInventoryEngine
from simulation.world.supplier_engine import SupplierOrderEngine


class SupplyRunnerError(RuntimeError):
    """Raised when the integrated inventory/supply run cannot proceed."""


class SupplySimulationRunner:
    def __init__(
        self,
        initial_world_path: str | Path,
        scenarios_path: str | Path,
        output_dir: str | Path,
        seed: int = 42,
    ) -> None:
        self.initial_world_path = Path(initial_world_path)
        self.scenarios_path = Path(scenarios_path)
        self.output_dir = Path(output_dir)
        self.seed = seed

    def _load_world(self) -> dict[str, Any]:
        if not self.initial_world_path.is_file():
            raise SupplyRunnerError(
                f"Initial world not found: {self.initial_world_path}"
            )
        return json.loads(
            self.initial_world_path.read_text(encoding="utf-8")
        )

    def _load_scenarios(self) -> pd.DataFrame:
        if not self.scenarios_path.is_file():
            raise SupplyRunnerError(
                f"Scenario CSV not found: {self.scenarios_path}"
            )
        scenarios = pd.read_csv(self.scenarios_path)
        if scenarios.empty:
            raise SupplyRunnerError("Scenario CSV is empty.")
        return scenarios

    def run(self, days: int) -> dict[str, Any]:
        if days <= 0:
            raise SupplyRunnerError("days must be greater than zero.")

        world = deepcopy(self._load_world())
        scenarios = self._load_scenarios()
        if len(scenarios) < days:
            raise SupplyRunnerError(
                f"Only {len(scenarios)} scenarios available."
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        inventory_engine = DailyInventoryEngine(seed=self.seed)
        supplier_engine = SupplierOrderEngine(seed=self.seed + 101)

        order_log: list[dict[str, Any]] = []
        receipt_log: list[dict[str, Any]] = []
        movement_log: list[dict[str, Any]] = []
        daily_metrics: list[dict[str, Any]] = []

        initial_on_hand = sum(
            int(row["on_hand"]) for row in world["inventory"]
        )

        for index in range(days):
            simulation_day = index + 1
            scenario = scenarios.iloc[index].to_dict()
            current_date = str(scenario["synthetic_date"])

            receipts = supplier_engine.receive_due_orders(
                world=world,
                simulation_day=simulation_day,
                current_date=current_date,
            )
            receipt_log.extend(receipts)

            movements = inventory_engine.allocate_daily_demand(
                world=world,
                scenario=scenario,
                simulation_day=simulation_day,
                current_date=current_date,
            )
            movement_rows = [movement.to_dict() for movement in movements]
            movement_log.extend(movement_rows)

            orders = supplier_engine.create_replenishment_orders(
                world=world,
                simulation_day=simulation_day,
                current_date=current_date,
                logistics_multiplier=float(
                    scenario.get("logistics_cost_multiplier", 1.0)
                ),
            )
            order_log.extend([order.to_dict() for order in orders])

            fulfilled = sum(
                row["applied_units"]
                for row in movement_rows
                if row["movement_type"] == "SALE_CONSUMPTION"
            )
            unmet = sum(
                row["unmet_units"]
                for row in movement_rows
                if row["movement_type"] == "SALE_CONSUMPTION"
            )
            expired = sum(
                row["applied_units"]
                for row in movement_rows
                if row["movement_type"] == "EXPIRATION"
            )
            received = sum(row["received_units"] for row in receipts)
            on_hand = sum(
                int(row["on_hand"]) for row in world["inventory"]
            )
            in_transit = sum(
                int(row["in_transit"]) for row in world["inventory"]
            )
            open_orders = sum(
                1 for order in world["pending_orders"]
                if order["status"] in {"OPEN", "PARTIALLY_RECEIVED"}
            )
            below_reorder = sum(
                1 for row in world["inventory"]
                if int(row["inventory_position"])
                <= int(row["reorder_point"])
            )

            daily_metrics.append(
                {
                    "simulation_day": simulation_day,
                    "date": current_date,
                    "fulfilled_units": fulfilled,
                    "unmet_units": unmet,
                    "expired_units": expired,
                    "received_units": received,
                    "orders_created": len(orders),
                    "open_orders": open_orders,
                    "ending_on_hand_units": on_hand,
                    "ending_in_transit_units": in_transit,
                    "positions_below_reorder_point": below_reorder,
                }
            )

            world["simulation_day"] = simulation_day
            world["current_date"] = current_date

        world.setdefault("metadata", {})
        world["metadata"]["world_status"] = "SUPPLY_ADVANCED"
        world["metadata"]["supply_days_processed"] = days
        world["metadata"]["supplier_engine_seed"] = self.seed + 101

        final_world_path = (
            self.output_dir / f"world_state_day_{days:03d}.json"
        )
        final_world_path.write_text(
            json.dumps(world, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        orders_path = self.output_dir / "purchase_orders.csv"
        receipts_path = self.output_dir / "supplier_receipts.csv"
        movements_path = self.output_dir / "inventory_movements.csv"
        metrics_path = self.output_dir / "supply_daily_metrics.csv"

        pd.DataFrame(order_log).to_csv(orders_path, index=False)
        pd.DataFrame(receipt_log).to_csv(receipts_path, index=False)
        pd.DataFrame(movement_log).to_csv(movements_path, index=False)
        pd.DataFrame(daily_metrics).to_csv(metrics_path, index=False)

        total_received = sum(row["received_units"] for row in receipt_log)
        total_fulfilled = sum(
            row["fulfilled_units"] for row in daily_metrics
        )
        total_expired = sum(
            row["expired_units"] for row in daily_metrics
        )
        ending_on_hand = sum(
            int(row["on_hand"]) for row in world["inventory"]
        )

        expected_ending = (
            initial_on_hand
            + total_received
            - total_fulfilled
            - total_expired
        )
        if ending_on_hand != expected_ending:
            raise SupplyRunnerError(
                "Inventory conservation failed: "
                f"expected {expected_ending}, got {ending_on_hand}."
            )

        return {
            "days_processed": days,
            "initial_on_hand_units": initial_on_hand,
            "ending_on_hand_units": ending_on_hand,
            "ending_in_transit_units": sum(
                int(row["in_transit"]) for row in world["inventory"]
            ),
            "orders_created": len(order_log),
            "receipts_created": len(receipt_log),
            "received_units": total_received,
            "fulfilled_units": total_fulfilled,
            "unmet_units": sum(
                row["unmet_units"] for row in daily_metrics
            ),
            "open_orders": sum(
                1 for order in world["pending_orders"]
                if order["status"] in {"OPEN", "PARTIALLY_RECEIVED"}
            ),
            "completed_orders": sum(
                1 for order in world["pending_orders"]
                if order["status"] == "RECEIVED"
            ),
            "final_world_path": str(final_world_path.resolve()),
            "orders_path": str(orders_path.resolve()),
            "receipts_path": str(receipts_path.resolve()),
            "metrics_path": str(metrics_path.resolve()),
        }
