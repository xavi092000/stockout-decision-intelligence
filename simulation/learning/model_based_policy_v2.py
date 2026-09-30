from __future__ import annotations

"""Frozen model-based action-value policy V2."""
import math
from pathlib import Path
import joblib

from simulation.action import ActionType, InventoryAction
from simulation.decision_policy import DecisionResult
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, model_row, validate_model_features


class ModelBasedInventoryPolicyV2:
    def __init__(self, artifact_path: Path | str):
        payload = joblib.load(artifact_path)
        self.model = payload["model"]
        self.metadata = payload["metadata"]
        validate_model_features(tuple(self.metadata["model_features"]))
        if tuple(self.metadata["model_features"]) != MODEL_FEATURES:
            raise RuntimeError("V2 model feature contract mismatch")
        self._fallback = EconomicConstrainedPolicy(
            EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3)
        )

    @staticmethod
    def _pending(state, store_id, sku_id):
        return sum(op.quantity for op in state.pending_operations
                   if op.is_pending and op.destination_store_id == store_id and op.sku_id == sku_id)

    def _candidates(self, *, state, inventory, product, store, supplier, forecast, forecasts_by_key):
        pending = self._pending(state, store.store_id, product.sku_id)
        daily = max(float(forecast.forecast_daily_demand), 1e-6)
        target = daily * 14.0 + product.safety_stock
        gap = max(0, math.ceil(target - inventory.available_stock - pending))
        actions = [InventoryAction(ActionType.DO_NOTHING, store.store_id, product.sku_id, 0)]
        if gap > 0:
            # Quantity is a feasibility/control variable and is itself a model feature.
            actions += [
                InventoryAction(ActionType.ORDER_NORMAL, store.store_id, product.sku_id, gap),
                InventoryAction(ActionType.ORDER_EXPEDITE, store.store_id, product.sku_id, gap),
            ]
            for donor in state.inventories:
                if donor.sku_id != product.sku_id or donor.store_id == store.store_id:
                    continue
                donor_fc = forecasts_by_key.get((donor.store_id, donor.sku_id))
                if donor_fc is None:
                    continue
                surplus = math.floor(
                    donor.available_stock - donor_fc.forecast_next_3d - product.safety_stock
                )
                if surplus > 0:
                    actions.append(InventoryAction(
                        ActionType.TRANSFER_STOCK, store.store_id, product.sku_id,
                        min(gap, surplus), donor.store_id
                    ))
        return actions

    def decide(self, *, state, inventory, product, store, supplier, forecast, forecasts_by_key):
        actions = self._candidates(
            state=state, inventory=inventory, product=product, store=store,
            supplier=supplier, forecast=forecast, forecasts_by_key=forecasts_by_key
        )
        pending = self._pending(state, store.store_id, product.sku_id)
        base = {
            "store_id": store.store_id, "sku_id": product.sku_id,
            "current_stock": inventory.available_stock, "pending_units": pending,
            "forecast_daily_demand": forecast.forecast_daily_demand,
            "forecast_next_3d": forecast.forecast_next_3d,
            "lead_time_days": supplier.lead_time_days, "safety_stock": product.safety_stock,
            "temperature_c": state.temperature_c, "weather_condition": state.weather_condition,
            "simulation_day": state.current_day,
        }
        rows = []
        for a in actions:
            rows.append(model_row({
                **base, "action_type": a.action_type.value, "action_quantity": a.quantity,
                "source_store_id": a.source_store_id or "",
            }))
        matrix = [[r[c] for c in MODEL_FEATURES] for r in rows]
        values = self.model.predict(matrix)
        idx = max(range(len(actions)), key=lambda i: (float(values[i]), -i))
        action = actions[idx]
        projected = max(
            0.0, float(forecast.forecast_daily_demand) * 14.0 + product.safety_stock
            - inventory.available_stock - pending
        )
        return DecisionResult(
            action=action,
            reason=f"Model-based V2 predicted {float(values[idx]):.2f} horizon business value",
            forecast_daily_demand=forecast.forecast_daily_demand,
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(projected, 2),
        )
