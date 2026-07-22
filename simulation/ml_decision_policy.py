from __future__ import annotations

"""
ML-backed decision policy with operational safety guardrails.

The model predicts only the action class:
- DO_NOTHING
- ORDER_NORMAL
- ORDER_EXPEDITE
- TRANSFER_STOCK

Action quantities and transfer feasibility remain deterministic.
Only information available at decision time is used.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math
import time

import joblib
import pandas as pd

from simulation.action import ActionType, InventoryAction
from simulation.decision_policy import DecisionResult
from simulation.demand_engine import DemandForecast
from simulation.entities import Inventory, Product, Store, Supplier
from simulation.feature_contract import (
    EXPECTED_ACTIONS,
    FEATURE_SCHEMA_VERSION,
    MODEL_FEATURE_COLUMNS,
)
from simulation.pending_operation import PendingOperationType
from simulation.state import SimulationState



class FeatureValidationError(ValueError):
    """Raised when runtime model inputs violate the feature contract."""


def validate_feature_frame(frame: pd.DataFrame) -> None:
    """Validate one inference frame before calling the model."""
    actual = tuple(str(column) for column in frame.columns)
    if actual != MODEL_FEATURE_COLUMNS:
        missing = [name for name in MODEL_FEATURE_COLUMNS if name not in actual]
        extra = [name for name in actual if name not in MODEL_FEATURE_COLUMNS]
        raise FeatureValidationError(
            "Runtime feature contract mismatch. "
            f"Missing={missing!r}; extra={extra!r}; order={list(actual)!r}."
        )
    if len(frame) != 1:
        raise FeatureValidationError(
            f"ML policy expects exactly one feature row; received {len(frame)}."
        )
    if frame.isna().any().any():
        bad = frame.columns[frame.isna().any()].tolist()
        raise FeatureValidationError(f"NaN values detected in features: {bad!r}.")
    for column in frame.select_dtypes(include=["number"]).columns:
        value = frame.iloc[0][column]
        if not math.isfinite(float(value)):
            raise FeatureValidationError(
                f"Non-finite numeric value for feature {column!r}: {value!r}."
            )
    non_negative = (
        "current_stock", "available_stock", "pending_normal_units",
        "pending_expedite_units", "forecast_daily_demand",
        "forecast_next_3d", "projected_stock_gap",
        "supplier_lead_time_days", "neighbor_surplus_units",
    )
    invalid = [name for name in non_negative if float(frame.iloc[0][name]) < 0]
    if invalid:
        raise FeatureValidationError(
            f"Negative values are not allowed for features: {invalid!r}."
        )


class ModelValidationError(RuntimeError):
    """Raised when a model artifact does not match the feature contract."""


def _as_string_tuple(values: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ModelValidationError(
            f"Metadata field {field_name!r} must be a list."
        )
    return tuple(str(value) for value in values)



@dataclass
class MLDecisionPolicy:
    model_path: Path | str = Path(
        "artifacts/policy_training/decision_tree.joblib"
    )
    metadata_path: Path | str | None = None

    def __post_init__(self) -> None:
        self.model_path = Path(self.model_path)
        self.metadata_path = (
            Path(self.metadata_path)
            if self.metadata_path is not None
            else self.model_path.with_name("training_metadata.json")
        )

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"ML policy model not found: "
                f"{self.model_path.resolve()}"
            )

        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"ML policy metadata not found: "
                f"{self.metadata_path.resolve()}"
            )

        started_at = time.perf_counter()
        self.pipeline: Any = joblib.load(self.model_path)
        self.model_load_seconds = time.perf_counter() - started_at
        self.metadata = self._load_metadata()
        self._validate_artifacts()
        self.fallback_count = 0
        self.prediction_counts: dict[str, int] = {}
        self.prediction_error_count = 0
        self.total_prediction_seconds = 0.0

    def _load_metadata(self) -> dict[str, Any]:
        try:
            payload = json.loads(
                self.metadata_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise ModelValidationError(
                f"Invalid JSON metadata: {self.metadata_path.resolve()}"
            ) from exc

        if not isinstance(payload, dict):
            raise ModelValidationError(
                "Training metadata must contain a JSON object."
            )
        return payload

    def _validate_artifacts(self) -> None:
        metadata_features = _as_string_tuple(
            self.metadata.get("feature_columns"),
            field_name="feature_columns",
        )
        if metadata_features != MODEL_FEATURE_COLUMNS:
            raise ModelValidationError(
                "Metadata feature contract mismatch: expected "
                f"{list(MODEL_FEATURE_COLUMNS)!r}, found "
                f"{list(metadata_features)!r}."
            )

        schema_version = self.metadata.get("feature_schema_version")
        if schema_version != FEATURE_SCHEMA_VERSION:
            raise ModelValidationError(
                "Feature schema version mismatch: expected "
                f"{FEATURE_SCHEMA_VERSION!r}, found {schema_version!r}."
            )

        metadata_actions = _as_string_tuple(
            self.metadata.get("expected_actions"),
            field_name="expected_actions",
        )
        if set(metadata_actions) != set(EXPECTED_ACTIONS):
            raise ModelValidationError(
                "Metadata action classes mismatch: expected "
                f"{sorted(EXPECTED_ACTIONS)!r}, found "
                f"{sorted(metadata_actions)!r}."
            )

        model_features = getattr(self.pipeline, "feature_names_in_", None)
        if model_features is not None:
            model_feature_tuple = tuple(str(value) for value in model_features)
            if model_feature_tuple != MODEL_FEATURE_COLUMNS:
                raise ModelValidationError(
                    "Loaded model feature order does not match the "
                    "runtime feature contract."
                )

        estimator = (
            self.pipeline.named_steps.get("model")
            if hasattr(self.pipeline, "named_steps")
            else self.pipeline
        )
        model_classes = getattr(estimator, "classes_", None)
        if model_classes is None:
            raise ModelValidationError(
                "Loaded classifier does not expose trained classes_."
            )

        class_tuple = tuple(str(value) for value in model_classes)
        if set(class_tuple) != set(EXPECTED_ACTIONS):
            raise ModelValidationError(
                "Loaded model classes do not match the action contract: "
                f"{sorted(class_tuple)!r}."
            )

    def decide(
        self,
        state: SimulationState,
        inventory: Inventory,
        product: Product,
        store: Store,
        supplier: Supplier,
        forecast: DemandForecast,
        forecasts_by_key: dict[
            tuple[str, str],
            DemandForecast,
        ],
    ) -> DecisionResult:
        pending_normal = self._pending_units(
            state=state,
            store_id=store.store_id,
            sku_id=product.sku_id,
            operation_type=PendingOperationType.NORMAL_ORDER,
        )
        pending_expedite = self._pending_units(
            state=state,
            store_id=store.store_id,
            sku_id=product.sku_id,
            operation_type=PendingOperationType.EXPEDITE_ORDER,
        )
        pending_inbound = pending_normal + pending_expedite

        projected_available_stock = (
            inventory.available_stock + pending_inbound
        )

        lead_time_demand = (
            forecast.forecast_daily_demand
            * supplier.lead_time_days
        )

        required_stock = max(
            forecast.forecast_next_3d,
            lead_time_demand,
        ) + product.safety_stock

        projected_stock_gap = max(
            0.0,
            required_stock - projected_available_stock,
        )

        feature_row = pd.DataFrame(
            [
                {
                    "current_stock": int(
                        inventory.stock_level
                    ),
                    "available_stock": int(
                        inventory.available_stock
                    ),
                    "pending_normal_units": pending_normal,
                    "pending_expedite_units": (
                        pending_expedite
                    ),
                    "forecast_daily_demand": int(
                        forecast.forecast_daily_demand
                    ),
                    "forecast_next_3d": int(
                        forecast.forecast_next_3d
                    ),
                    "projected_stock_gap": int(
                        round(projected_stock_gap)
                    ),
                    "temperature_c": float(
                        state.temperature_c
                    ),
                    "promotion_flag": int(
                        (
                            store.store_id,
                            product.sku_id,
                        )
                        in state.active_promotions
                    ),
                    "holiday_flag": int(
                        bool(
                            getattr(
                                state,
                                "is_holiday",
                                False,
                            )
                        )
                    ),
                    "supplier_lead_time_days": int(
                        supplier.lead_time_days
                    ),
                    "neighbor_surplus_units": (
                        self._neighbor_surplus_units(
                            state=state,
                            destination_store_id=(
                                store.store_id
                            ),
                            sku_id=product.sku_id,
                        )
                    ),
                    "store_id": store.store_id,
                    "sku_id": product.sku_id,
                    "weather_condition": str(
                        state.weather_condition
                    ),
                }
            ],
            columns=list(MODEL_FEATURE_COLUMNS),
        )

        validate_feature_frame(feature_row)
        prediction_started_at = time.perf_counter()
        try:
            predicted_action = str(self.pipeline.predict(feature_row)[0])
        except Exception:
            self.prediction_error_count += 1
            raise
        finally:
            self.total_prediction_seconds += (
                time.perf_counter() - prediction_started_at
            )

        if predicted_action not in EXPECTED_ACTIONS:
            self.prediction_error_count += 1
            raise RuntimeError(
                f"Model returned unsupported action: {predicted_action!r}."
            )

        self.prediction_counts[predicted_action] = (
            self.prediction_counts.get(
                predicted_action,
                0,
            )
            + 1
        )

        quantity = max(
            1,
            round(projected_stock_gap),
        )

        if predicted_action == ActionType.DO_NOTHING.value:
            action = InventoryAction(
                action_type=ActionType.DO_NOTHING,
                destination_store_id=store.store_id,
                sku_id=product.sku_id,
                quantity=0,
            )
            reason = "ML policy predicted DO_NOTHING."

        elif predicted_action == ActionType.TRANSFER_STOCK.value:
            transfer = self._find_safe_transfer(
                state=state,
                destination_inventory=inventory,
                product=product,
                required_quantity=quantity,
                forecasts_by_key=forecasts_by_key,
            )

            if transfer is not None:
                action = transfer
                reason = (
                    "ML policy predicted TRANSFER_STOCK and "
                    "a safe donor was available."
                )
            else:
                self.fallback_count += 1
                action = self._supplier_order_fallback(
                    store=store,
                    product=product,
                    supplier=supplier,
                    projected_available_stock=(
                        projected_available_stock
                    ),
                    forecast=forecast,
                    quantity=quantity,
                )
                reason = (
                    "ML predicted TRANSFER_STOCK, but no safe "
                    "donor was available; deterministic supplier "
                    "order fallback applied."
                )

        elif predicted_action == ActionType.ORDER_EXPEDITE.value:
            action = InventoryAction(
                action_type=ActionType.ORDER_EXPEDITE,
                destination_store_id=store.store_id,
                sku_id=product.sku_id,
                quantity=quantity,
            )
            reason = "ML policy predicted ORDER_EXPEDITE."

        elif predicted_action == ActionType.ORDER_NORMAL.value:
            action = InventoryAction(
                action_type=ActionType.ORDER_NORMAL,
                destination_store_id=store.store_id,
                sku_id=product.sku_id,
                quantity=quantity,
            )
            reason = "ML policy predicted ORDER_NORMAL."

        else:
            raise RuntimeError(
                f"Unsupported ML action: {predicted_action!r}"
            )

        return DecisionResult(
            action=action,
            reason=reason,
            forecast_daily_demand=(
                forecast.forecast_daily_demand
            ),
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(
                projected_stock_gap,
                2,
            ),
        )

    def metrics_snapshot(self) -> dict[str, Any]:
        """Return lightweight operational metrics for monitoring."""
        prediction_total = sum(self.prediction_counts.values())
        average_ms = (
            self.total_prediction_seconds / prediction_total * 1000.0
            if prediction_total else 0.0
        )
        return {
            "model_path": str(self.model_path),
            "metadata_path": str(self.metadata_path),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "model_load_seconds": round(self.model_load_seconds, 6),
            "prediction_total": prediction_total,
            "prediction_error_count": self.prediction_error_count,
            "fallback_count": self.fallback_count,
            "average_prediction_ms": round(average_ms, 6),
            "prediction_counts": dict(self.prediction_counts),
        }

    @staticmethod
    def _pending_units(
        *,
        state: SimulationState,
        store_id: str,
        sku_id: str,
        operation_type: PendingOperationType,
    ) -> int:
        cached = getattr(
            state,
            "_pending_by_type",
            None,
        )

        if cached is not None:
            return cached.get(
                (
                    store_id,
                    sku_id,
                    operation_type,
                ),
                0,
            )

        return sum(
            operation.quantity
            for operation in state.pending_operations
            if (
                operation.is_pending
                and operation.operation_type
                == operation_type
                and operation.destination_store_id
                == store_id
                and operation.sku_id == sku_id
            )
        )

    @staticmethod
    def _neighbor_surplus_units(
        *,
        state: SimulationState,
        destination_store_id: str,
        sku_id: str,
    ) -> int:
        # Matches the feature definition used during training.
        return sum(
            int(candidate.available_stock)
            for candidate in state.inventories
            if (
                candidate.sku_id == sku_id
                and candidate.store_id
                != destination_store_id
            )
        )

    def _find_safe_transfer(
        self,
        *,
        state: SimulationState,
        destination_inventory: Inventory,
        product: Product,
        required_quantity: int,
        forecasts_by_key: dict[
            tuple[str, str],
            DemandForecast,
        ],
    ) -> InventoryAction | None:
        candidates: list[
            tuple[int, Inventory]
        ] = []

        for candidate in state.inventories:
            if (
                candidate.sku_id
                != destination_inventory.sku_id
            ):
                continue

            if (
                candidate.store_id
                == destination_inventory.store_id
            ):
                continue

            candidate_forecast = forecasts_by_key.get(
                (
                    candidate.store_id,
                    candidate.sku_id,
                )
            )

            if candidate_forecast is None:
                continue

            pending_inbound = (
                self._pending_units(
                    state=state,
                    store_id=candidate.store_id,
                    sku_id=candidate.sku_id,
                    operation_type=(
                        PendingOperationType.NORMAL_ORDER
                    ),
                )
                + self._pending_units(
                    state=state,
                    store_id=candidate.store_id,
                    sku_id=candidate.sku_id,
                    operation_type=(
                        PendingOperationType.EXPEDITE_ORDER
                    ),
                )
            )

            donor_required_stock = (
                candidate_forecast.forecast_next_3d
                + product.safety_stock
            )

            transferable_surplus = max(
                0,
                round(
                    candidate.available_stock
                    + pending_inbound
                    - donor_required_stock
                ),
            )

            if transferable_surplus > 0:
                candidates.append(
                    (
                        transferable_surplus,
                        candidate,
                    )
                )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        surplus, source = candidates[0]
        transfer_quantity = min(
            required_quantity,
            surplus,
        )

        if transfer_quantity <= 0:
            return None

        return InventoryAction(
            action_type=ActionType.TRANSFER_STOCK,
            source_store_id=source.store_id,
            destination_store_id=(
                destination_inventory.store_id
            ),
            sku_id=destination_inventory.sku_id,
            quantity=transfer_quantity,
        )

    @staticmethod
    def _supplier_order_fallback(
        *,
        store: Store,
        product: Product,
        supplier: Supplier,
        projected_available_stock: float,
        forecast: DemandForecast,
        quantity: int,
    ) -> InventoryAction:
        days_of_cover = (
            float("inf")
            if forecast.forecast_daily_demand <= 0
            else (
                projected_available_stock
                / forecast.forecast_daily_demand
            )
        )

        action_type = (
            ActionType.ORDER_EXPEDITE
            if days_of_cover < supplier.lead_time_days
            else ActionType.ORDER_NORMAL
        )

        return InventoryAction(
            action_type=action_type,
            destination_store_id=store.store_id,
            sku_id=product.sku_id,
            quantity=quantity,
        )

