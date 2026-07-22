from __future__ import annotations

import pandas as pd
import pytest

from simulation.feature_contract import MODEL_FEATURE_COLUMNS
from simulation.ml_decision_policy import FeatureValidationError, validate_feature_frame


def _valid_frame() -> pd.DataFrame:
    values = {
        "current_stock": 10,
        "available_stock": 9,
        "pending_normal_units": 0,
        "pending_expedite_units": 0,
        "forecast_daily_demand": 3,
        "forecast_next_3d": 9,
        "projected_stock_gap": 2,
        "temperature_c": 20.0,
        "promotion_flag": 0,
        "holiday_flag": 0,
        "supplier_lead_time_days": 2,
        "neighbor_surplus_units": 5,
        "store_id": "STORE_1",
        "sku_id": "SKU_1",
        "weather_condition": "clear",
    }
    return pd.DataFrame([values], columns=list(MODEL_FEATURE_COLUMNS))


def test_valid_feature_frame_passes() -> None:
    validate_feature_frame(_valid_frame())


def test_missing_feature_is_rejected() -> None:
    frame = _valid_frame().drop(columns=["current_stock"])
    with pytest.raises(FeatureValidationError, match="Missing"):
        validate_feature_frame(frame)


def test_extra_feature_is_rejected() -> None:
    frame = _valid_frame()
    frame["unexpected"] = 1
    with pytest.raises(FeatureValidationError, match="extra"):
        validate_feature_frame(frame)


def test_nan_is_rejected() -> None:
    frame = _valid_frame()
    frame.loc[0, "temperature_c"] = float("nan")
    with pytest.raises(FeatureValidationError, match="NaN"):
        validate_feature_frame(frame)


def test_negative_inventory_is_rejected() -> None:
    frame = _valid_frame()
    frame.loc[0, "available_stock"] = -1
    with pytest.raises(FeatureValidationError, match="Negative"):
        validate_feature_frame(frame)
