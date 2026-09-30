"""Paired multi-day action experiments, without changing the existing engine.

One store-SKU intervention on day one; all later decisions follow a fixed
continuation policy. These are finite-horizon returns under that policy,
not optimal Q-values. Future seeds are label-generation metadata, not features.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
from random import Random

from simulation.action import ActionType, InventoryAction
from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedPolicy, EconomicConstrainedConfig


class ScenarioTape:
    """Freeze a reference scenario path, including stock-dependent promotions."""
    def __init__(self, scenarios):
        self.scenarios = deepcopy(scenarios)
        self.index = 0

    def generate(self, **kwargs):
        scenario = deepcopy(self.scenarios[self.index])
        self.index += 1
        return scenario


class Intervention:
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
        actions = [InventoryAction(ActionType.DO_NOTHING, *self.target)]
        quantities = sorted({max(1, math.ceil(forecast.forecast_daily_demand * d)) for d in (1, 3, 7)})
        for kind in (ActionType.ORDER_NORMAL, ActionType.ORDER_EXPEDITE):
            actions.extend(InventoryAction(kind, *self.target, q) for q in quantities)
        for donor in state.inventories:
            if donor.sku_id != inv.sku_id or donor.store_id == inv.store_id:
                continue
            donor_forecast = kw['forecasts_by_key'][(donor.store_id, donor.sku_id)]
            # Never treat stock still in transit as transferable stock.
            surplus = max(0, math.floor(donor.available_stock - donor_forecast.forecast_next_3d - kw['product'].safety_stock))
            if surplus:
                actions.append(InventoryAction(ActionType.TRANSFER_STOCK, *self.target,
                                               min(surplus, quantities[1 if len(quantities)>1 else 0]), donor.store_id))
        if baseline.action not in actions:
            actions.append(baseline.action)
        self.candidates = actions
        action = self.action or actions[0]
        if action not in actions:
            raise ValueError('Intervention is not feasible in this observation')
        return replace(baseline, action=action, reason='Learning experiment: single intervention')


def collect(engine, *, horizon=14, future_seeds=(10001, 10002, 10003), target=None):
    """Return separate decision-time observations and future outcome labels.

    Input must be initialized at the start of an unexecuted day. The input
    engine, RNGs, histories and continuation policy are never mutated.
    All candidates receive exactly the same exogenous demand per future seed.
    """
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
    probe.decision_policy = Intervention(deepcopy(engine.decision_policy), target)
    probe.run_day()
    observed = probe.decision_policy.observation
    candidates = probe.decision_policy.candidates
    if observed is None:
        raise RuntimeError('Target decision was not observed')
    rows = []
    for seed in seeds:
        # Promotions in the base simulator depend on inventory. Freeze a
        # wait-reference scenario tape so action comparisons have common demand.
        reference = deepcopy(engine)
        reference.decision_policy = Intervention(deepcopy(engine.decision_policy), target)
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
            wrapper = Intervention(deepcopy(engine.decision_policy), target, action)
            branch.decision_policy = wrapper
            branch.export_dataset = False
            branch.scenario_generator = ScenarioTape(scenarios)
            # Today's observed scenario remains fixed; demand is not yet known.
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
        reference = next(r for r in rows if r['future_seed']==seed and r['action']['action_type']==ActionType.DO_NOTHING)
        for row in rows:
            if row['future_seed']==seed:
                row['labels']['value_delta_vs_wait'] = round(row['labels']['network_business_value'] - reference['labels']['network_business_value'], 6)
    return {'schema_version': 'action_experiments_v1',
            'metadata': {'episode_seed': engine.config.random_seed, 'horizon': horizon,
                         'continuation_policy': type(engine.decision_policy).__name__,
                         'continuation_config': asdict(engine.decision_policy.config) if hasattr(engine.decision_policy, 'config') else None,
                         'economic_config': asdict(engine.economic_engine.config),
                         'limitations': ['Finite horizon, no terminal stock valuation',
                                         'Fixed continuation policy; not optimal action values',
                                         'Promotions frozen from wait-reference path; endogenous promotion response excluded',
                                         'Uses existing simulator constraints and economics',
                                         'No trained model or production approval']},
            'observation': observed, 'experiments': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--episode-seed', type=int, default=401)
    parser.add_argument('--warmup-days', type=int, default=10)
    parser.add_argument('--horizon', type=int, default=14)
    parser.add_argument('--futures', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('artifacts/learning/experiments_v1.json'))
    args = parser.parse_args()
    if args.warmup_days < 0 or args.horizon < 1 or args.futures < 1:
        parser.error('Invalid warmup, horizon or futures')
    if args.output.exists():
        parser.error('Output already exists; choose another path to preserve experiments')
    engine = SimulationEngine(SimulationConfig(random_seed=args.episode_seed,
                              number_of_days=args.warmup_days + args.horizon), export_dataset=False)
    engine.initialize()
    engine.decision_policy = EconomicConstrainedPolicy(EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3))
    for _ in range(args.warmup_days):
        engine.run_day()
        engine.advance_day()
    payload = collect(engine, horizon=args.horizon, future_seeds=tuple(range(10001,10001+args.futures)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f"Saved {len(payload['experiments'])} paired outcomes to {args.output}")

if __name__ == '__main__':
    main()
