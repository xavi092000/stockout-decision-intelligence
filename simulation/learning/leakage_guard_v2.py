from __future__ import annotations

"""Leakage contract for model-based decision learning V2."""

DECISION_FEATURES = (
    "store_id", "sku_id", "current_stock", "pending_units",
    "forecast_daily_demand", "forecast_next_3d", "lead_time_days",
    "safety_stock", "temperature_c", "weather_condition", "simulation_day",
)
ACTION_FEATURES = ("action_type", "action_quantity", "source_store_id")
MODEL_FEATURES = DECISION_FEATURES + ACTION_FEATURES

FORBIDDEN_FEATURE_TOKENS = (
    "future_seed", "network_business_value", "network_fill_rate",
    "unmet_units", "stockout_events", "value_delta_vs_wait",
    "future_demand", "realized_future", "ending_stock", "business_value",
)

def validate_model_features(names) -> None:
    names = tuple(names)
    unknown = set(names) - set(MODEL_FEATURES)
    if unknown:
        raise ValueError(f"Unapproved model features: {sorted(unknown)}")
    bad = [n for n in names if any(tok in n.lower() for tok in FORBIDDEN_FEATURE_TOKENS)]
    if bad:
        raise ValueError(f"Leakage-prone model features: {bad}")

def model_row(row: dict) -> dict:
    validate_model_features(MODEL_FEATURES)
    missing = [name for name in MODEL_FEATURES if name not in row]
    if missing:
        raise KeyError(f"Missing model features: {missing}")
    return {name: row[name] for name in MODEL_FEATURES}
