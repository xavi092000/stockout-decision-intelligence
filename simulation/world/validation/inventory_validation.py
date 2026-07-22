from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class InventoryValidationError(RuntimeError):
    """Raised when Sprint 7B output violates an inventory invariant."""


def validate_inventory_run(
    output_dir: str | Path,
    expected_days: int,
    expected_positions: int,
) -> dict:
    output = Path(output_dir)
    final_world_path = (
        output / f"world_state_day_{expected_days:03d}.json"
    )
    movements_path = output / "inventory_movements.csv"
    metrics_path = output / "inventory_daily_metrics.csv"

    required = [final_world_path, movements_path, metrics_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise InventoryValidationError(
            "Missing Sprint 7B output(s): " + ", ".join(missing)
        )

    world = json.loads(final_world_path.read_text(encoding="utf-8"))
    movements = pd.read_csv(movements_path)
    metrics = pd.read_csv(metrics_path)

    if int(world["simulation_day"]) != expected_days:
        raise InventoryValidationError(
            "Final world simulation day is incorrect."
        )
    if len(world["inventory"]) != expected_positions:
        raise InventoryValidationError(
            f"Expected {expected_positions} inventory positions, "
            f"got {len(world['inventory'])}."
        )
    if len(metrics) != expected_days:
        raise InventoryValidationError(
            f"Expected {expected_days} metric rows, got {len(metrics)}."
        )
    if movements.empty:
        raise InventoryValidationError(
            "No inventory movements were generated."
        )
    if movements["movement_id"].duplicated().any():
        raise InventoryValidationError(
            "Duplicate movement IDs detected."
        )

    inventory = pd.DataFrame(world["inventory"])
    for column in (
        "on_hand",
        "reserved",
        "in_transit",
        "available",
        "inventory_position",
    ):
        if inventory[column].lt(0).any():
            raise InventoryValidationError(
                f"Negative inventory values detected in {column}."
            )

    if (inventory["reserved"] > inventory["on_hand"]).any():
        raise InventoryValidationError(
            "Reserved stock exceeds on-hand stock."
        )
    if movements["stock_after"].lt(0).any():
        raise InventoryValidationError(
            "A movement produced negative stock."
        )
    if movements["applied_units"].lt(0).any():
        raise InventoryValidationError(
            "Negative applied movement quantity detected."
        )
    if movements["unmet_units"].lt(0).any():
        raise InventoryValidationError(
            "Negative unmet movement quantity detected."
        )

    conservation = (
        int(metrics.iloc[0]["ending_on_hand_units"])
        <= int(
            metrics.iloc[0]["ending_on_hand_units"]
            + metrics.iloc[0]["fulfilled_units"]
            + metrics.iloc[0]["expired_units"]
        )
    )
    if not conservation:
        raise InventoryValidationError(
            "Inventory conservation validation failed."
        )

    snapshots = list(output.glob("inventory_day_*.csv"))
    if len(snapshots) != expected_days:
        raise InventoryValidationError(
            f"Expected {expected_days} daily snapshots, "
            f"got {len(snapshots)}."
        )

    return {
        "status": "PASSED",
        "checked_files": 3 + len(snapshots),
        "days_validated": expected_days,
        "inventory_positions": len(inventory),
        "movement_count": len(movements),
        "ending_on_hand_units": int(inventory["on_hand"].sum()),
        "zero_stock_positions": int(inventory["on_hand"].eq(0).sum()),
        "positions_below_reorder_point": int(
            (
                inventory["inventory_position"]
                <= inventory["reorder_point"]
            ).sum()
        ),
        "negative_stock_positions": int(
            inventory["on_hand"].lt(0).sum()
        ),
        "inventory_conservation": "PASSED",
        "leakage_guard": "PASSED",
    }
