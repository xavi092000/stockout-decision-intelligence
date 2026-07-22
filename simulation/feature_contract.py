from __future__ import annotations

"""Single source of truth for the ML policy feature schema."""

FEATURE_SCHEMA_VERSION = "2.0.0"
TARGET_COLUMN = "chosen_action"

NUMERIC_FEATURES = (
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

CATEGORICAL_FEATURES = (
    "store_id",
    "sku_id",
    "weather_condition",
)

MODEL_FEATURE_COLUMNS = (
    *NUMERIC_FEATURES,
    *CATEGORICAL_FEATURES,
)

# Pre-decision columns physically emitted by dataset_builder as feature fields.
# store_id and sku_id remain identifier columns in the CSV schema, while they
# are also consumed by the model through MODEL_FEATURE_COLUMNS.
DATASET_FEATURE_COLUMNS = (
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

EXPECTED_ACTIONS = (
    "DO_NOTHING",
    "ORDER_NORMAL",
    "ORDER_EXPEDITE",
    "TRANSFER_STOCK",
)


def validate_contract() -> None:
    """Fail fast if the in-code schema becomes internally inconsistent."""
    if len(MODEL_FEATURE_COLUMNS) != len(set(MODEL_FEATURE_COLUMNS)):
        raise RuntimeError("Duplicate columns in MODEL_FEATURE_COLUMNS.")

    if len(DATASET_FEATURE_COLUMNS) != len(set(DATASET_FEATURE_COLUMNS)):
        raise RuntimeError("Duplicate columns in DATASET_FEATURE_COLUMNS.")

    if set(NUMERIC_FEATURES) & set(CATEGORICAL_FEATURES):
        raise RuntimeError(
            "Numeric and categorical feature groups must be disjoint."
        )

    if set(MODEL_FEATURE_COLUMNS) != (
        set(NUMERIC_FEATURES) | set(CATEGORICAL_FEATURES)
    ):
        raise RuntimeError(
            "MODEL_FEATURE_COLUMNS does not match its feature groups."
        )


validate_contract()
