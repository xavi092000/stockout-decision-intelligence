from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import pandas as pd

from simulation.world.inventory_engine import (
    DailyInventoryEngine,
    InventoryEngineError,
)


class InventoryRunnerError(RuntimeError):
    """Raised when the daily inventory simulation cannot continue."""


class InventorySimulationRunner:
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
            raise InventoryRunnerError(
                f"Initial world not found: {self.initial_world_path}"
            )
        try:
            world = json.loads(
                self.initial_world_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise InventoryRunnerError(
                f"Invalid initial world JSON: {exc}"
            ) from exc

        required = {"inventory", "products", "stores", "financials"}
        missing = sorted(required.difference(world))
        if missing:
            raise InventoryRunnerError(
                "Initial world is missing: " + ", ".join(missing)
            )
        return world

    def _load_scenarios(self) -> pd.DataFrame:
        if not self.scenarios_path.is_file():
            raise InventoryRunnerError(
                f"Scenario file not found: {self.scenarios_path}"
            )
        scenarios = pd.read_csv(self.scenarios_path)
        required = {
            "synthetic_date",
            "expected_demand_units",
            "final_demand_multiplier",
            "category",
            "department",
            "store",
        }
        missing = sorted(required.difference(scenarios.columns))
        if missing:
            raise InventoryRunnerError(
                "Scenario CSV is missing: " + ", ".join(missing)
            )
        return scenarios

    def run(self, days: int) -> dict[str, Any]:
        if days <= 0:
            raise InventoryRunnerError("days must be greater than zero.")

        world = deepcopy(self._load_world())
        scenarios = self._load_scenarios()

        if len(scenarios) < days:
            raise InventoryRunnerError(
                f"Only {len(scenarios)} scenarios available for {days} days."
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        engine = DailyInventoryEngine(seed=self.seed)

        all_movements: list[dict[str, Any]] = []
        daily_metrics: list[dict[str, Any]] = []

        initial_on_hand = sum(
            int(row["on_hand"]) for row in world["inventory"]
        )

        for index in range(days):
            simulation_day = index + 1
            scenario = scenarios.iloc[index].to_dict()
            current_date = str(scenario["synthetic_date"])

            movements = engine.allocate_daily_demand(
                world=world,
                scenario=scenario,
                simulation_day=simulation_day,
                current_date=current_date,
            )
            movement_rows = [movement.to_dict() for movement in movements]
            all_movements.extend(movement_rows)

            requested = sum(row["requested_units"] for row in movement_rows)
            applied = sum(
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
            ending_on_hand = sum(
                int(row["on_hand"]) for row in world["inventory"]
            )
            zero_positions = sum(
                1 for row in world["inventory"]
                if int(row["on_hand"]) == 0
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
                    "requested_units": requested,
                    "fulfilled_units": applied,
                    "unmet_units": unmet,
                    "expired_units": expired,
                    "ending_on_hand_units": ending_on_hand,
                    "zero_stock_positions": zero_positions,
                    "positions_below_reorder_point": below_reorder,
                    "fill_rate": (
                        round(applied / requested, 6)
                        if requested > 0
                        else 1.0
                    ),
                }
            )

            world["simulation_day"] = simulation_day
            world["current_date"] = current_date

            snapshot_path = (
                self.output_dir
                / f"inventory_day_{simulation_day:03d}.csv"
            )
            pd.DataFrame(world["inventory"]).to_csv(
                snapshot_path,
                index=False,
            )

        world.setdefault("metadata", {})
        world["metadata"]["world_status"] = "INVENTORY_ADVANCED"
        world["metadata"]["inventory_engine_seed"] = self.seed
        world["metadata"]["inventory_days_processed"] = days

        final_world_path = (
            self.output_dir / f"world_state_day_{days:03d}.json"
        )
        final_world_path.write_text(
            json.dumps(world, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        movements_path = self.output_dir / "inventory_movements.csv"
        metrics_path = self.output_dir / "inventory_daily_metrics.csv"

        pd.DataFrame(all_movements).to_csv(
            movements_path,
            index=False,
        )
        pd.DataFrame(daily_metrics).to_csv(metrics_path, index=False)

        ending_on_hand = sum(
            int(row["on_hand"]) for row in world["inventory"]
        )
        total_fulfilled = sum(
            row["fulfilled_units"] for row in daily_metrics
        )
        total_unmet = sum(row["unmet_units"] for row in daily_metrics)
        total_expired = sum(row["expired_units"] for row in daily_metrics)

        expected_ending = (
            initial_on_hand - total_fulfilled - total_expired
        )
        if ending_on_hand != expected_ending:
            raise InventoryEngineError(
                "Inventory conservation check failed: "
                f"expected {expected_ending}, got {ending_on_hand}."
            )

        return {
            "days_processed": days,
            "initial_on_hand_units": initial_on_hand,
            "ending_on_hand_units": ending_on_hand,
            "fulfilled_units": total_fulfilled,
            "unmet_units": total_unmet,
            "expired_units": total_expired,
            "movement_count": len(all_movements),
            "final_world_path": str(final_world_path.resolve()),
            "movements_path": str(movements_path.resolve()),
            "metrics_path": str(metrics_path.resolve()),
        }
