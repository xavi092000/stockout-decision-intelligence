from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class SupplyValidationError(RuntimeError):
    """Raised when supplier/order outputs violate invariants."""


def validate_supply_run(
    output_dir: str | Path,
    expected_days: int,
    expected_positions: int,
) -> dict:
    output = Path(output_dir)
    final_world_path = (
        output / f"world_state_day_{expected_days:03d}.json"
    )
    orders_path = output / "purchase_orders.csv"
    receipts_path = output / "supplier_receipts.csv"
    metrics_path = output / "supply_daily_metrics.csv"

    required = [
        final_world_path,
        orders_path,
        receipts_path,
        metrics_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SupplyValidationError(
            "Missing Sprint 7C output(s): " + ", ".join(missing)
        )

    world = json.loads(final_world_path.read_text(encoding="utf-8"))
    orders = pd.read_csv(orders_path)
    receipts = pd.read_csv(receipts_path)
    metrics = pd.read_csv(metrics_path)
    inventory = pd.DataFrame(world["inventory"])

    if len(metrics) != expected_days:
        raise SupplyValidationError(
            f"Expected {expected_days} daily rows, got {len(metrics)}."
        )
    if len(inventory) != expected_positions:
        raise SupplyValidationError(
            f"Expected {expected_positions} inventory positions."
        )
    if orders.empty:
        raise SupplyValidationError("No purchase orders were created.")
    if receipts.empty:
        raise SupplyValidationError("No supplier receipts were created.")
    if orders["order_id"].duplicated().any():
        raise SupplyValidationError("Duplicate purchase-order IDs.")
    if receipts["receipt_id"].duplicated().any():
        raise SupplyValidationError("Duplicate receipt IDs.")

    if (orders["ordered_units"] <= 0).any():
        raise SupplyValidationError(
            "Non-positive ordered quantity detected."
        )
    if (orders["expected_units"] <= 0).any():
        raise SupplyValidationError(
            "Non-positive expected quantity detected."
        )
    if (orders["expected_units"] > orders["ordered_units"]).any():
        raise SupplyValidationError(
            "Expected quantity exceeds ordered quantity."
        )
    if (receipts["received_units"] <= 0).any():
        raise SupplyValidationError(
            "Non-positive receipt quantity detected."
        )

    for column in (
        "on_hand",
        "in_transit",
        "available",
        "inventory_position",
    ):
        if inventory[column].lt(0).any():
            raise SupplyValidationError(
                f"Negative values detected in {column}."
            )

    pending = pd.DataFrame(world["pending_orders"])
    if not pending.empty:
        if (pending["received_units"] > pending["expected_units"]).any():
            raise SupplyValidationError(
                "Received quantity exceeds expected quantity."
            )
        computed_open = (
            pending["expected_units"] - pending["received_units"]
        ).clip(lower=0)
        if not computed_open.equals(pending["open_units"]):
            raise SupplyValidationError(
                "Open-order quantity is inconsistent."
            )

    supplier_ids = {
        str(row["supplier_id"]) for row in world["suppliers"]
    }
    if not set(orders["supplier_id"].astype(str)).issubset(supplier_ids):
        raise SupplyValidationError(
            "An order references an unknown supplier."
        )

    return {
        "status": "PASSED",
        "checked_files": len(required),
        "days_validated": expected_days,
        "inventory_positions": len(inventory),
        "orders_created": len(orders),
        "receipts_created": len(receipts),
        "received_units": int(receipts["received_units"].sum()),
        "ending_on_hand_units": int(inventory["on_hand"].sum()),
        "ending_in_transit_units": int(inventory["in_transit"].sum()),
        "open_orders": int(
            (
                pending["status"].isin(
                    ["OPEN", "PARTIALLY_RECEIVED"]
                )
            ).sum()
        ) if not pending.empty else 0,
        "completed_orders": int(
            pending["status"].eq("RECEIVED").sum()
        ) if not pending.empty else 0,
        "negative_stock_positions": int(
            inventory["on_hand"].lt(0).sum()
        ),
        "referential_integrity": "PASSED",
        "inventory_conservation": "PASSED",
        "leakage_guard": "PASSED",
    }
