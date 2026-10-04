from __future__ import annotations

"""V24 CLOSED-LOOP SMOKE TEST — 1 held-out seed x 60 days.

Arms on identical seed:
- BASELINE: EconomicConstrainedPolicy(14, 3)
- A CURRENT-STYLE: V24 delta model, single quantity ~1.0x gap per action type
  (runtime _candidates behavior)
- B V24 EXPANDED: V24 delta model, full action+quantity grid
  (build_v24_candidates)

No guards, no retraining, n_jobs=1.
"""
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SEED = 13003
HORIZON_DAYS = 60
MODEL_PATH = ROOT / "artifacts" / "model_based_v24" / "action_value_model.joblib"
OUT_DIR = ROOT / "artifacts" / "model_based_v24"

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import (
    EconomicConstrainedConfig, EconomicConstrainedPolicy)
from simulation.learning.counterfactual_dataset_v24 import (
    build_v24_candidates, runtime_gap)
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, model_row
from simulation.learning.model_based_policy_v2 import ModelBasedInventoryPolicyV2


class QuantityTrackingMixin:
    def _track(self, action):
        self._quantities.setdefault(action.action_type.value, []).append(action.quantity)


class CurrentStylePolicy(ModelBasedInventoryPolicyV2, QuantityTrackingMixin):
    """A — V24 model, current-style single quantity per action type."""

    def __init__(self, artifact_path):
        super().__init__(artifact_path)
        self.model.named_steps["regressor"].n_jobs = 1
        self._quantities = {}

    def decide(self, **kw):
        result = super().decide(**kw)
        self._track(result.action)
        return result


class ExpandedV24Policy(QuantityTrackingMixin):
    """B — V24 model, expanded action+quantity candidates."""

    def __init__(self, artifact_path):
        self._inner = ModelBasedInventoryPolicyV2(artifact_path)
        self._inner.model.named_steps["regressor"].n_jobs = 1
        self._quantities = {}

    def decide(self, *, state, inventory, product, store, supplier, forecast,
               forecasts_by_key):
        import math as _math
        from simulation.decision_policy import DecisionResult
        inner = self._inner
        pending = inner._pending(state, store.store_id, product.sku_id)
        gap = runtime_gap(forecast.forecast_daily_demand, product.safety_stock,
                          inventory.available_stock, pending)
        donor_surpluses = []
        for donor in state.inventories:
            if donor.sku_id != product.sku_id or donor.store_id == store.store_id:
                continue
            donor_fc = forecasts_by_key.get((donor.store_id, donor.sku_id))
            if donor_fc is None:
                continue
            surplus = _math.floor(
                donor.available_stock - donor_fc.forecast_next_3d - product.safety_stock)
            if surplus > 0:
                donor_surpluses.append((donor.store_id, surplus))
        actions = build_v24_candidates(store.store_id, product.sku_id, gap,
                                       donor_surpluses)
        base = {
            "store_id": store.store_id, "sku_id": product.sku_id,
            "current_stock": inventory.available_stock, "pending_units": pending,
            "forecast_daily_demand": forecast.forecast_daily_demand,
            "forecast_next_3d": forecast.forecast_next_3d,
            "lead_time_days": supplier.lead_time_days,
            "safety_stock": product.safety_stock,
            "temperature_c": state.temperature_c,
            "weather_condition": state.weather_condition,
            "simulation_day": state.current_day,
        }
        rows = [model_row({**base, "action_type": a.action_type.value,
                           "action_quantity": a.quantity,
                           "source_store_id": a.source_store_id or ""})
                for a in actions]
        matrix = [[r[c] for c in MODEL_FEATURES] for r in rows]
        values = inner.model.predict(matrix)
        idx = max(range(len(actions)), key=lambda i: (float(values[i]), -i))
        action = actions[idx]
        self._track(action)
        projected = max(0.0, float(gap))
        return DecisionResult(
            action=action,
            reason=f"V24 expanded predicted {float(values[idx]):.2f} delta value",
            forecast_daily_demand=forecast.forecast_daily_demand,
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(projected, 2),
        )


def run(name, policy):
    t0 = time.perf_counter()
    engine = SimulationEngine(
        config=SimulationConfig(random_seed=SEED, number_of_days=HORIZON_DAYS),
        export_dataset=False)
    engine.initialize()
    engine.decision_policy = policy
    engine.run(verbose=False)
    elapsed = time.perf_counter() - t0
    econ = engine.cumulative_economics
    counts = engine.cumulative_action_counts
    qs = getattr(policy, "_quantities", {})
    avg = {k: sum(v) / len(v) for k, v in qs.items() if v}
    return {
        "name": name,
        "business_value": float(econ.business_value),
        "service_level": float(engine.cumulative_service_level),
        "stockouts": int(engine.cumulative_stockouts),
        "unmet_units": int(engine.cumulative_unmet_demand),
        "total_cost": float(econ.total_cost),
        "normal_order_cost": float(econ.normal_order_cost),
        "expedite_order_cost": float(econ.expedite_order_cost),
        "transfer_cost": float(econ.transfer_cost),
        "holding_cost": float(econ.holding_cost),
        "ORDER_NORMAL": int(counts.get("ORDER_NORMAL", 0)),
        "ORDER_EXPEDITE": int(counts.get("ORDER_EXPEDITE", 0)),
        "TRANSFER_STOCK": int(counts.get("TRANSFER_STOCK", 0)),
        "DO_NOTHING": int(counts.get("DO_NOTHING", 0)),
        "normal_order_units": int(econ.normal_order_units),
        "expedite_order_units": int(econ.expedite_order_units),
        "transferred_units": int(econ.transferred_units),
        "avg_qty_ORDER_NORMAL": avg.get("ORDER_NORMAL"),
        "avg_qty_ORDER_EXPEDITE": avg.get("ORDER_EXPEDITE"),
        "runtime_s": round(elapsed, 2),
    }


def show(r, baseline_bv):
    print(f"\n{r['name']}  (runtime {r['runtime_s']}s)")
    print(f"  business_value=${r['business_value']:,.2f}  "
          f"delta_vs_baseline=${r['business_value'] - baseline_bv:+,.2f}")
    print(f"  service={r['service_level']:.4f} stockouts={r['stockouts']} "
          f"unmet={r['unmet_units']}")
    print(f"  total=${r['total_cost']:,.2f} normal=${r['normal_order_cost']:,.2f} "
          f"expedite=${r['expedite_order_cost']:,.2f} transfer=${r['transfer_cost']:,.2f} "
          f"holding=${r['holding_cost']:,.2f}")
    print(f"  actions N={r['ORDER_NORMAL']} E={r['ORDER_EXPEDITE']} "
          f"T={r['TRANSFER_STOCK']} DN={r['DO_NOTHING']} | units N={r['normal_order_units']} "
          f"E={r['expedite_order_units']} T={r['transferred_units']} | "
          f"avg qty N={r['avg_qty_ORDER_NORMAL']} E={r['avg_qty_ORDER_EXPEDITE']}")


def main():
    print(f"SEED: {SEED} (held-out: V24 train=2000-2003, val=4000-4001)")
    print(f"HORIZON: {HORIZON_DAYS} days")
    results = {}

    print("\n=== BASELINE ===", flush=True)
    results["baseline"] = run("BASELINE", EconomicConstrainedPolicy(
        EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3)))
    print("=== A CURRENT-STYLE ===", flush=True)
    results["A"] = run("A CURRENT-STYLE", CurrentStylePolicy(MODEL_PATH))
    print("=== B V24 EXPANDED ===", flush=True)
    results["B"] = run("B V24 EXPANDED", ExpandedV24Policy(MODEL_PATH))

    b0 = results["baseline"]["business_value"]
    for k in ("baseline", "A", "B"):
        show(results[k], b0)

    a, b, base = results["A"], results["B"], results["baseline"]
    print("\n=== V24 VS CURRENT (B - A) ===")
    print(f"business value delta: ${b['business_value'] - a['business_value']:+,.2f}")
    print(f"service delta: {b['service_level'] - a['service_level']:+.4f}")
    print(f"stockout delta: {b['stockouts'] - a['stockouts']:+d}")
    print(f"unmet delta: {b['unmet_units'] - a['unmet_units']:+d}")
    print(f"cost delta: ${b['total_cost'] - a['total_cost']:+,.2f}")
    if a["avg_qty_ORDER_NORMAL"] and b["avg_qty_ORDER_NORMAL"]:
        print(f"avg ORDER_NORMAL qty: A={a['avg_qty_ORDER_NORMAL']:.1f} "
              f"B={b['avg_qty_ORDER_NORMAL']:.1f}")
    if a["avg_qty_ORDER_EXPEDITE"] and b["avg_qty_ORDER_EXPEDITE"]:
        print(f"avg ORDER_EXPEDITE qty: A={a['avg_qty_ORDER_EXPEDITE']:.1f} "
              f"B={b['avg_qty_ORDER_EXPEDITE']:.1f}")

    print("\n=== V24 VS BASELINE (B - baseline) ===")
    print(f"business value delta: ${b['business_value'] - base['business_value']:+,.2f}")
    print(f"service delta: {b['service_level'] - base['service_level']:+.4f}")
    print(f"stockout delta: {b['stockouts'] - base['stockouts']:+d}")
    print(f"unmet delta: {b['unmet_units'] - base['unmet_units']:+d}")

    bv_up = b["business_value"] > a["business_value"]
    bv_down = b["business_value"] < a["business_value"]
    svc_drop = (a["service_level"] - b["service_level"]) > 0.01
    if bv_up and not svc_drop:
        verdict = "POSITIVE"
    elif bv_down or svc_drop:
        verdict = "NEGATIVE" if (bv_down or svc_drop) and not bv_up else "MIXED"
        if bv_up and svc_drop:
            verdict = "MIXED"
    else:
        verdict = "MIXED"
    print(f"\nVERDICT: {verdict}")

    out = {"seed": SEED, "horizon_days": HORIZON_DAYS, "results": results,
           "verdict": verdict}
    (OUT_DIR / "closed_loop_smoke.json").write_text(json.dumps(out, indent=2),
                                                    encoding="utf-8")


if __name__ == "__main__":
    main()
