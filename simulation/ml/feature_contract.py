from __future__ import annotations

"""Single source of truth for the V2 ML policy feature contract.

The order of ``FEATURE_COLUMNS`` is part of the serialized model contract.
Changing it requires a schema-version increment, dataset regeneration,
model retraining, and a new closed-loop benchmark.
"""

FEATURE_SCHEMA_VERSION = "2.0.0"
TARGET_COLUMN = "chosen_action"

NUMERIC_FEATURES: tuple[str, ...] = (
    "current_stock",
    "available_stock",
    "pending_normal_units",
    "pending_expedite_units",
    "forecast_daily_demand",
    "forecast_next_3d",
    "projected_stock_gap",
    "temperature_c",
    "promotion_flag",
    "holiday_flag",
    "supplier_lead_time_days",
    "neighbor_surplus_units",
)

IDENTIFIER_FEATURES: tuple[str, ...] = (
    "store_id",
    "sku_id",
)

CATEGORICAL_FEATURES: tuple[str, ...] = (
    *IDENTIFIER_FEATURES,
    "weather_condition",
)

FEATURE_COLUMNS: tuple[str, ...] = (
    *NUMERIC_FEATURES,
    *CATEGORICAL_FEATURES,
)

# Features captured in the pre-decision training row. Store and SKU remain
# identifier columns in dataset_builder, but become categorical model inputs.
PRE_DECISION_FEATURE_COLUMNS: tuple[str, ...] = (
    "current_stock",
    "available_stock",
    "pending_normal_units",
    "pending_expedite_units",
    "forecast_daily_demand",
    "forecast_next_3d",
    "projected_stock_gap",
    "temperature_c",
    "weather_condition",
    "promotion_flag",
    "holiday_flag",
    "supplier_lead_time_days",
    "neighbor_surplus_units",
)

EXPECTED_ACTIONS: tuple[str, ...] = (
    "DO_NOTHING",
    "ORDER_NORMAL",
    "ORDER_EXPEDITE",
    "TRANSFER_STOCK",
)


def validate_contract() -> None:
    """Fail fast if the static contract contains an internal inconsistency."""
    collections = {
        "NUMERIC_FEATURES": NUMERIC_FEATURES,
        "CATEGORICAL_FEATURES": CATEGORICAL_FEATURES,
        "FEATURE_COLUMNS": FEATURE_COLUMNS,
        "PRE_DECISION_FEATURE_COLUMNS": PRE_DECISION_FEATURE_COLUMNS,
        "EXPECTED_ACTIONS": EXPECTED_ACTIONS,
    }

    for name, values in collections.items():
        if len(values) != len(set(values)):
            raise RuntimeError(f"Duplicate values detected in {name}.")

    expected = (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)
    if FEATURE_COLUMNS != expected:
        raise RuntimeError(
            "FEATURE_COLUMNS must preserve numeric features followed by "
            "categorical features."
        )

    expected_snapshot = tuple(
        column
        for column in FEATURE_COLUMNS
        if column not in IDENTIFIER_FEATURES
    )
    # Dataset column order intentionally places weather before binary flags.
    if set(PRE_DECISION_FEATURE_COLUMNS) != set(expected_snapshot):
        raise RuntimeError(
            "PRE_DECISION_FEATURE_COLUMNS does not match the model contract."
        )


validate_contract()
