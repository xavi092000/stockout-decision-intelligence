from __future__ import annotations

"""V25 counterfactual dataset generator — representative state coverage.

Fixes the V24 structural flaw: instead of `first_stratum_crossing` only,
V25 captures states periodically across FULL episode trajectories, covering
HEALTHY / LOW_STOCK / HIGH_RISK / EMERGENCY, pending>0, and stationary
regimes (coverage up to and beyond 14 days).

Action space, gap fractions, pruning, labels, paired-futures protocol and
feature contract are inherited unchanged from V24.
"""
from argparse import ArgumentParser
from copy import deepcopy
import json
from pathlib import Path
import time

from simulation.benchmark import DoNothingDecisionPolicy
from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy
from simulation.learning.counterfactual_dataset_v24 import (
    ORDER_FRACTIONS, STRATA_THRESHOLDS, TRANSFER_FRACTIONS,
    _pending_units, _previous_day_forecast, _stratum, collect_v24,
    validate_seed_split)
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, model_row

STATE_SAMPLING_MODE = "periodic_full_trajectory"


class CaptureTracker:
    """Periodic per-target capture, capped per stratum."""

    def __init__(self, period: int = 3, cap_per_stratum: int = 3):
        if period < 1 or cap_per_stratum < 1:
            raise ValueError("period and cap_per_stratum must be >= 1")
        self.period = period
        self.cap_per_stratum = cap_per_stratum
        self._last_day = {}
        self._counts = {}

    def should_capture(self, store_id: str, sku_id: str, stratum: str, day: int) -> bool:
        target = (store_id, sku_id)
        last = self._last_day.get(target)
        if last is not None and day - last < self.period:
            return False
        key = (target, stratum)
        if self._counts.get(key, 0) >= self.cap_per_stratum:
            return False
        self._last_day[target] = day
        self._counts[key] = self._counts.get(key, 0) + 1
        return True


def _policy(name: str):
    if name == "donothing":
        return DoNothingDecisionPolicy()
    if name == "economic":
        return EconomicConstrainedPolicy(
            EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3)
        )
    raise ValueError(name)


def _scan_seed(seed: int, policy_name: str, scan_days: int, horizon: int,
               max_targets: int, period: int, cap_per_stratum: int):
    engine = SimulationEngine(
        SimulationConfig(random_seed=seed, number_of_days=scan_days + horizon),
        export_dataset=False,
    )
    engine.initialize()
    engine.decision_policy = _policy(policy_name)
    targets = [(i.store_id, i.sku_id) for i in engine.state.inventories][:max_targets]
    if policy_name == "donothing":
        # DoNothing roll-ins only exist to reach critical strata; cap them hard
        # so they cannot dominate the state distribution.
        tracker = CaptureTracker(period=max(period, 5), cap_per_stratum=1)
    else:
        tracker = CaptureTracker(period=period, cap_per_stratum=cap_per_stratum)
    captured = []
    for _ in range(scan_days):
        engine.run_day()
        engine.advance_day()
        for target_index, target in enumerate(targets):
            decision = _previous_day_forecast(engine, *target)
            if decision is None:
                continue
            inventory = engine.state.get_inventory(*target)
            pending_units = _pending_units(engine.state, *target)
            coverage = (inventory.available_stock + pending_units) / max(
                decision.forecast_daily_demand, 1e-9
            )
            strate = _stratum(coverage)
            if not tracker.should_capture(target[0], target[1], strate,
                                          engine.state.current_day):
                continue
            captured_engine = deepcopy(engine)
            captured_engine.decision_policy = _policy("economic")
            captured.append({
                "target": target,
                "target_index": target_index,
                "strate": strate,
                "captured_day": engine.state.current_day,
                "coverage": round(coverage, 6),
                "pending_units": pending_units,
                "policy": policy_name,
                "engine": captured_engine,
            })
    return captured


def main():
    p = ArgumentParser()
    p.add_argument("--output", type=Path,
                   default=Path("artifacts/model_based_v25/counterfactual_dataset.json"))
    p.add_argument("--train-seed-start", type=int, default=2000)
    p.add_argument("--train-episodes", type=int, default=4)
    p.add_argument("--validation-seed-start", type=int, default=4000)
    p.add_argument("--validation-episodes", type=int, default=2)
    p.add_argument("--scan-days", type=int, default=60)
    p.add_argument("--horizon", type=int, default=21)
    p.add_argument("--futures", type=int, default=2)
    p.add_argument("--max-targets", type=int, default=3)
    p.add_argument("--period", type=int, default=3)
    p.add_argument("--cap-per-stratum", type=int, default=3)
    args = p.parse_args()

    train = list(range(args.train_seed_start, args.train_seed_start + args.train_episodes))
    val = list(range(args.validation_seed_start, args.validation_seed_start + args.validation_episodes))
    try:
        validate_seed_split(train, val)
    except ValueError as exc:
        p.error(str(exc))

    metadata = {
        "train_episode_seeds": train,
        "validation_episode_seeds": val,
        "horizon": args.horizon,
        "futures": args.futures,
        "scan_days": args.scan_days,
        "max_targets": args.max_targets,
        "period": args.period,
        "cap_per_stratum": args.cap_per_stratum,
        "model_features": list(MODEL_FEATURES),
        "order_fractions": list(ORDER_FRACTIONS),
        "transfer_fractions": list(TRANSFER_FRACTIONS),
        "quantity_space": "runtime_gap_fractions",
        "future_outcomes_are_labels_only": True,
        "continuation_policy": "EconomicConstrainedPolicy",
        "state_generation_policy": "MIXED_DO_NOTHING_AND_ECONOMIC",
        "state_sampling_mode": STATE_SAMPLING_MODE,
        "forecast_source": "previous_day_decision_forecast",
        "forecast_staleness_days": 1,
        "claim_status": "V25_REPRESENTATIVE_STATE_PILOT",
    }
    payload = {"schema_version": "stockout_counterfactual_action_value_v25",
               "metadata": metadata, "completed_units": [], "rows": []}
    if args.output.exists():
        p.error(f"Output already exists, refusing to overwrite: {args.output}")

    completed = set()
    plan = [("train", s) for s in train] + [("validation", s) for s in val]
    start = time.perf_counter()
    try:
        for split, seed in plan:
            for policy_name in ("donothing", "economic"):
                for capture in _scan_seed(seed, policy_name, args.scan_days,
                                          args.horizon, args.max_targets,
                                          args.period, args.cap_per_stratum):
                    target = capture["target"]
                    target_index = capture["target_index"]
                    unit = f"{split}|{seed}|{capture['policy']}|{capture['captured_day']}|{target_index}|{target[0]}|{target[1]}"
                    if unit in completed:
                        continue
                    future_seeds = tuple(
                        seed * 1_000_000 + capture["captured_day"] * 10_000 + target_index * 100 + i + (50 if capture["policy"] == "economic" else 0)
                        for i in range(1, args.futures + 1)
                    )
                    result_payload = collect_v24(capture["engine"], horizon=args.horizon,
                                                 future_seeds=future_seeds, target=target)
                    obs = result_payload["observation"]
                    for result in result_payload["experiments"]:
                        action = result["action"]
                        labels = result["labels"]
                        full = {
                            **obs,
                            "action_type": action["action_type"],
                            "action_quantity": action["quantity"],
                            "source_store_id": action["source_store_id"] or "",
                        }
                        payload["rows"].append({
                            "split": split,
                            "episode_seed": seed,
                            "future_seed": result["future_seed"],
                            "state_generation_policy": capture["policy"],
                            "strate": capture["strate"],
                            "features": model_row(full),
                            "labels": {
                                "return_business_value": labels["network_business_value"],
                                "delta_value_vs_wait": labels["delta_value_vs_wait"],
                                "fill_rate": labels["network_fill_rate"],
                                "unmet_units": labels["unmet_units"],
                                "stockout_events": labels["stockout_events"],
                            },
                        })
                    payload["completed_units"].append(unit)
                    completed.add(unit)
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                    print(f"[{split}] {policy_name} seed={seed} day={capture['captured_day']} "
                          f"strata={capture['strate']} pend={capture['pending_units']} "
                          f"cov={capture['coverage']:.1f} rows={len(payload['rows'])}", flush=True)
    except KeyboardInterrupt:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise
    payload["metadata"]["generation_complete"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"COMPLETE rows={len(payload['rows'])} output={args.output} "
          f"elapsed={time.perf_counter()-start:.1f}s")


if __name__ == "__main__":
    main()
