from __future__ import annotations

"""V24 counterfactual dataset generator — expanded action+quantity search.

Same anti-leakage contract, strata, labels, and paired-futures protocol as V23,
but candidate quantities are fractions of the runtime 14-day coverage gap:
- ORDER_NORMAL / ORDER_EXPEDITE: 0.25, 0.50, 0.75, 1.00 x gap
- TRANSFER_STOCK: 0.50, 1.00 x min(gap, surplus)
- DO_NOTHING: qty = 0
Quantities are ceiled, deduplicated, and pruned below 1.
Does not modify or reuse V23 artifacts.
"""
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
from random import Random
import time

from simulation.action import ActionType, InventoryAction
from simulation.benchmark import DoNothingDecisionPolicy
from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy
from simulation.learning.experiments import ScenarioTape
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, model_row

ORDER_FRACTIONS = (0.25, 0.5, 0.75, 1.0)
TRANSFER_FRACTIONS = (0.5, 1.0)

STRATA_THRESHOLDS = {
    "HEALTHY": 14.0,
    "LOW_STOCK": 7.0,
    "HIGH_RISK": 3.0,
    "EMERGENCY": 0.0,
}
STATE_SAMPLING_MODE = "first_stratum_crossing"
FORECAST_SOURCE = "previous_day_decision_forecast"
FORECAST_STALENESS_DAYS = 1


def runtime_gap(forecast_daily_demand: float, safety_stock: float,
                available_stock: float, pending_units: float) -> int:
    """Same gap formula as the runtime policy (_candidates)."""
    return max(0, math.ceil(
        forecast_daily_demand * 14.0 + safety_stock - available_stock - pending_units
    ))


def fraction_quantities(gap: int, fractions) -> list[int]:
    """Ceiled gap fractions, deduplicated, pruned below 1."""
    return sorted({q for f in fractions if (q := math.ceil(gap * f)) >= 1})


def build_v24_candidates(store_id: str, sku_id: str, gap: int,
                         donor_surpluses: list[tuple[str, int]]) -> list[InventoryAction]:
    """Expanded action+quantity candidate set, deduplicated."""
    actions = [InventoryAction(ActionType.DO_NOTHING, store_id, sku_id, 0)]
    if gap > 0:
        for kind in (ActionType.ORDER_NORMAL, ActionType.ORDER_EXPEDITE):
            for q in fraction_quantities(gap, ORDER_FRACTIONS):
                actions.append(InventoryAction(kind, store_id, sku_id, q))
        for donor_id, surplus in donor_surpluses:
            cap = min(gap, surplus)
            for q in fraction_quantities(cap, TRANSFER_FRACTIONS):
                actions.append(InventoryAction(
                    ActionType.TRANSFER_STOCK, store_id, sku_id, q, donor_id))
    seen = set()
    unique = []
    for a in actions:
        key = (a.action_type, a.quantity, a.source_store_id)
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def validate_seed_split(train_seeds, validation_seeds) -> None:
    if set(train_seeds) & set(validation_seeds):
        raise ValueError("train and validation seeds must be disjoint")


def _policy(name: str):
    if name == "donothing":
        return DoNothingDecisionPolicy()
    if name == "economic":
        return EconomicConstrainedPolicy(
            EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3)
        )
    raise ValueError(name)


def _stratum(coverage: float) -> str:
    for name, threshold in STRATA_THRESHOLDS.items():
        if coverage >= threshold:
            return name
    return "EMERGENCY"


def _pending_units(state, store_id: str, sku_id: str) -> int:
    return sum(
        operation.quantity
        for operation in state.pending_operations
        if operation.is_pending
        and operation.destination_store_id == store_id
        and operation.sku_id == sku_id
    )


def _previous_day_forecast(engine, store_id: str, sku_id: str):
    for decision in reversed(engine.last_decisions):
        action = decision.action
        if action.destination_store_id == store_id and action.sku_id == sku_id:
            return decision
    return None


class InterventionV24:
    """Single intervention on day one with expanded action+quantity candidates."""

    def __init__(self, continuation, target, action=None):
        self.continuation = continuation
        self.target = target
        self.action = action
        self.observation = None
        self.candidates = None
        self.done = False

    def decide(self, **kw):
        baseline = self.continuation.decide(**kw)
        inv, state, forecast = kw['inventory'], kw['state'], kw['forecast']
        if self.done or (inv.store_id, inv.sku_id) != self.target:
            return baseline
        self.done = True
        pending = sum(o.quantity for o in state.pending_operations
                      if o.is_pending and (o.destination_store_id, o.sku_id) == self.target)
        self.observation = {
            'store_id': inv.store_id, 'sku_id': inv.sku_id,
            'current_stock': inv.available_stock, 'pending_units': pending,
            'forecast_daily_demand': forecast.forecast_daily_demand,
            'forecast_next_3d': forecast.forecast_next_3d,
            'lead_time_days': kw['supplier'].lead_time_days,
            'safety_stock': kw['product'].safety_stock,
            'temperature_c': state.temperature_c, 'weather_condition': state.weather_condition,
            'simulation_day': state.current_day,
        }
        gap = runtime_gap(forecast.forecast_daily_demand, kw['product'].safety_stock,
                          inv.available_stock, pending)
        donor_surpluses = []
        for donor in state.inventories:
            if donor.sku_id != inv.sku_id or donor.store_id == inv.store_id:
                continue
            donor_forecast = kw['forecasts_by_key'][(donor.store_id, donor.sku_id)]
            surplus = max(0, math.floor(
                donor.available_stock - donor_forecast.forecast_next_3d
                - kw['product'].safety_stock))
            if surplus:
                donor_surpluses.append((donor.store_id, surplus))
        actions = build_v24_candidates(inv.store_id, inv.sku_id, gap, donor_surpluses)
        if baseline.action not in actions:
            actions.append(baseline.action)
        self.candidates = actions
        action = self.action or actions[0]
        if action not in actions:
            raise ValueError('Intervention is not feasible in this observation')
        return replace(baseline, action=action, reason='V24 learning experiment: single intervention')


def collect_v24(engine, *, horizon, future_seeds, target=None):
    """Paired multi-day experiments with V24 expanded candidates.

    Same protocol as experiments.collect: identical exogenous demand per future
    seed, frozen scenario tape, continuation policy untouched, input engine
    never mutated. Adds a delta_value_vs_wait label per future seed.
    """
    from simulation.learning.experiments import collect as _unused  # noqa: F401  (contract anchor)
    if engine.state is None or engine.completed_days != engine.clock.current_day - 1:
        raise ValueError('Expected initialized engine at start of an unexecuted day')
    if horizon < 1 or horizon > engine.clock.remaining_days + 1:
        raise ValueError('Invalid horizon')
    seeds = tuple(future_seeds)
    if not seeds or len(set(seeds)) != len(seeds) or any(not isinstance(s, int) or s < 0 for s in seeds):
        raise ValueError('Future seeds must be nonempty, unique nonnegative integers')
    first = engine.state.inventories[0]
    target = target or (first.store_id, first.sku_id)
    engine.state.get_inventory(*target)
    probe = deepcopy(engine)
    probe.decision_policy = InterventionV24(deepcopy(engine.decision_policy), target)
    probe.run_day()
    observed = probe.decision_policy.observation
    candidates = probe.decision_policy.candidates
    if observed is None:
        raise RuntimeError('Target decision was not observed')
    rows = []
    for seed in seeds:
        reference = deepcopy(engine)
        reference.decision_policy = InterventionV24(deepcopy(engine.decision_policy), target)
        reference.demand_engine._rng = Random(seed)
        scenarios = []
        for offset in range(horizon):
            if offset:
                reference.advance_day()
            reference.run_day()
            scenarios.append(deepcopy(reference.last_scenario))
            if offset == 0:
                reference.scenario_generator._rng = Random(seed + 1000003)
        reference_demand = None
        for action in candidates:
            branch = deepcopy(engine)
            wrapper = InterventionV24(deepcopy(engine.decision_policy), target, action)
            branch.decision_policy = wrapper
            branch.export_dataset = False
            branch.scenario_generator = ScenarioTape(scenarios)
            branch.demand_engine._rng = Random(seed)
            value = 0.0
            demand, sold, unmet, stockouts = 0, 0, 0, 0
            demand_path = []
            for offset in range(horizon):
                if offset:
                    branch.advance_day()
                outcome = branch.run_day()
                if offset == 0:
                    if wrapper.observation != observed:
                        raise RuntimeError('Decision-time observation changed between branches')
                    actual = next(d.action for d in branch.last_decisions
                                  if (d.action.destination_store_id, d.action.sku_id) == target)
                    if actual != action:
                        raise RuntimeError('Simulator adjusted intervention; do not mislabel it')
                    branch.scenario_generator._rng = Random(seed + 1000003)
                value += branch.last_economic_outcome.business_value
                demand += outcome.total_demand
                sold += outcome.fulfilled_demand
                unmet += outcome.unmet_demand
                stockouts += outcome.stockout_count
                demand_path.extend((t.store_id, t.sku_id, t.actual_demand) for t in outcome.transitions)
            digest = hashlib.sha256(json.dumps(demand_path).encode()).hexdigest()
            if reference_demand is not None and digest != reference_demand:
                raise RuntimeError('Unpaired demand trajectories')
            reference_demand = digest
            rows.append({'action': asdict(action), 'future_seed': seed,
                         'demand_path_sha256': digest,
                         'labels': {'network_business_value': round(value, 6),
                                    'network_fill_rate': sold / demand if demand else 1.0,
                                    'unmet_units': unmet, 'stockout_events': stockouts,
                                    'ending_stock': sum(i.stock_level for i in branch.state.inventories),
                                    'pending_units': sum(o.quantity for o in branch.state.pending_operations if o.is_pending)}})
    for seed in seeds:
        reference = next(r for r in rows if r['future_seed'] == seed
                         and r['action']['action_type'] == ActionType.DO_NOTHING)
        for row in rows:
            if row['future_seed'] == seed:
                row['labels']['delta_value_vs_wait'] = round(
                    row['labels']['network_business_value']
                    - reference['labels']['network_business_value'], 6)
    return {'observation': observed, 'experiments': rows}


def _scan_seed(seed: int, policy_name: str, scan_days: int, horizon: int, max_targets: int):
    engine = SimulationEngine(
        SimulationConfig(random_seed=seed, number_of_days=scan_days + horizon),
        export_dataset=False,
    )
    engine.initialize()
    engine.decision_policy = _policy(policy_name)
    targets = [(i.store_id, i.sku_id) for i in engine.state.inventories][:max_targets]
    captured = []
    seen = set()
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
            key = (target[0], target[1], strate, policy_name)
            if key in seen:
                continue
            seen.add(key)
            captured_engine = deepcopy(engine)
            captured_engine.decision_policy = _policy("economic")
            captured.append({
                "target": target,
                "target_index": target_index,
                "strate": strate,
                "captured_day": engine.state.current_day,
                "coverage": round(coverage, 6),
                "policy": policy_name,
                "engine": captured_engine,
            })
    return captured


def main():
    p = ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("artifacts/model_based_v24/counterfactual_dataset.json"))
    p.add_argument("--train-seed-start", type=int, default=2000)
    p.add_argument("--train-episodes", type=int, default=4)
    p.add_argument("--validation-seed-start", type=int, default=4000)
    p.add_argument("--validation-episodes", type=int, default=2)
    p.add_argument("--scan-days", type=int, default=30)
    p.add_argument("--horizon", type=int, default=21)
    p.add_argument("--futures", type=int, default=2)
    p.add_argument("--max-targets", type=int, default=3)
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
        "model_features": list(MODEL_FEATURES),
        "order_fractions": list(ORDER_FRACTIONS),
        "transfer_fractions": list(TRANSFER_FRACTIONS),
        "quantity_space": "runtime_gap_fractions",
        "future_outcomes_are_labels_only": True,
        "continuation_policy": "EconomicConstrainedPolicy",
        "state_generation_policy": "MIXED_DO_NOTHING_AND_ECONOMIC",
        "state_sampling_mode": STATE_SAMPLING_MODE,
        "forecast_source": FORECAST_SOURCE,
        "forecast_staleness_days": FORECAST_STALENESS_DAYS,
        "claim_status": "V24_EXPANDED_QUANTITY_PILOT",
    }
    payload = {"schema_version": "stockout_counterfactual_action_value_v24",
               "metadata": metadata, "completed_units": [], "rows": []}
    if args.output.exists():
        p.error(f"Output already exists, refusing to overwrite: {args.output}")

    completed = set(payload["completed_units"])
    plan = [("train", s) for s in train] + [("validation", s) for s in val]
    start = time.perf_counter()
    try:
        for split, seed in plan:
            for policy_name in ("donothing", "economic"):
                for capture in _scan_seed(seed, policy_name, args.scan_days, args.horizon, args.max_targets):
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
                          f"strata={capture['strate']} rows={len(payload['rows'])}", flush=True)
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
