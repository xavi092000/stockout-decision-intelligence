from __future__ import annotations

"""Leakage-safe, resumable counterfactual dataset generation for V2.

V2.1 changes:
- visible progress + ETA
- checkpoint after every completed target
- safe resume after Ctrl+C / interruption
- smaller PILOT defaults before any large generation
Future simulator outcomes remain labels only.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
import time

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy
from simulation.learning.experiments import collect
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, model_row


def _policy():
    return EconomicConstrainedPolicy(EconomicConstrainedConfig(
        target_days_of_cover=14, expedite_trigger_days=3
    ))


def _snapshot(seed: int, warmup: int, horizon: int):
    engine = SimulationEngine(
        SimulationConfig(random_seed=seed, number_of_days=warmup + horizon),
        export_dataset=False,
    )
    engine.initialize()
    engine.decision_policy = _policy()
    for _ in range(warmup):
        engine.run_day()
        engine.advance_day()
    return engine


def _fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _save_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def main():
    p = ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("artifacts/model_based_v2/counterfactual_dataset.json"))
    p.add_argument("--train-seed-start", type=int, default=2000)
    p.add_argument("--train-episodes", type=int, default=4)
    p.add_argument("--validation-seed-start", type=int, default=4000)
    p.add_argument("--validation-episodes", type=int, default=2)
    p.add_argument("--warmup-days", default="0,14,28")
    p.add_argument("--horizon", type=int, default=21)
    p.add_argument("--futures", type=int, default=2)
    p.add_argument("--max-targets", type=int, default=3)
    p.add_argument("--fresh", action="store_true", help="discard an existing V2.1 checkpoint/output")
    args = p.parse_args()

    train = list(range(args.train_seed_start, args.train_seed_start + args.train_episodes))
    val = list(range(args.validation_seed_start, args.validation_seed_start + args.validation_episodes))
    if set(train) & set(val):
        p.error("train and validation seeds must be disjoint")
    warmups = [int(x) for x in args.warmup_days.split(",") if x.strip()]

    metadata = {
        "train_episode_seeds": train,
        "validation_episode_seeds": val,
        "horizon": args.horizon,
        "futures": args.futures,
        "warmup_days": warmups,
        "max_targets": args.max_targets,
        "model_features": list(MODEL_FEATURES),
        "future_outcomes_are_labels_only": True,
        "continuation_policy": "EconomicConstrainedPolicy",
        "claim_status": "PILOT_BOOTSTRAP_DATA_NOT_FINAL_POLICY_ITERATION",
    }
    payload = {
        "schema_version": "stockout_counterfactual_action_value_v2",
        "metadata": metadata,
        "completed_units": [],
        "rows": [],
    }

    if args.fresh and args.output.exists():
        args.output.unlink()
    if args.output.exists():
        old = json.loads(args.output.read_text(encoding="utf-8"))
        if old.get("metadata") != metadata:
            p.error("existing checkpoint uses different parameters; use --fresh to start over")
        payload = old
        print(f"RESUME: {len(payload.get('completed_units', []))} units already complete, {len(payload.get('rows', []))} rows saved", flush=True)

    completed = set(payload.get("completed_units", []))
    plan = [("train", s, w) for s in train for w in warmups] + [("validation", s, w) for s in val for w in warmups]
    total_units = len(plan) * args.max_targets
    done_before = len(completed)
    start = time.perf_counter()
    done_this_run = 0

    print("=== STOCKOUT MODEL-BASED V2.1 COUNTERFACTUAL PILOT ===", flush=True)
    print(f"Planned units : {total_units} | already done: {done_before}", flush=True)
    print(f"Train seeds   : {train}", flush=True)
    print(f"Validation    : {val}", flush=True)
    print(f"Warmups       : {warmups} | targets/checkpoint: {args.max_targets} | futures: {args.futures} | horizon: {args.horizon}", flush=True)
    print("Checkpoint    : after every target", flush=True)
    print("", flush=True)

    try:
        for split, seed, warmup in plan:
            base = _snapshot(seed, warmup, args.horizon)
            targets = [(i.store_id, i.sku_id) for i in base.state.inventories][:args.max_targets]
            for target_index, target in enumerate(targets):
                unit = f"{split}|{seed}|{warmup}|{target_index}|{target[0]}|{target[1]}"
                if unit in completed:
                    continue
                unit_start = time.perf_counter()
                future_seeds = tuple(
                    seed * 1_000_000 + warmup * 10_000 + target_index * 100 + i
                    for i in range(1, args.futures + 1)
                )
                result_payload = collect(base, horizon=args.horizon, future_seeds=future_seeds, target=target)
                obs = result_payload["observation"]
                new_rows = []
                for result in result_payload["experiments"]:
                    action = result["action"]
                    labels = result["labels"]
                    full = {
                        **obs,
                        "action_type": action["action_type"],
                        "action_quantity": action["quantity"],
                        "source_store_id": action["source_store_id"] or "",
                    }
                    new_rows.append({
                        "split": split,
                        "episode_seed": seed,
                        "future_seed": result["future_seed"],
                        "features": model_row(full),
                        "labels": {
                            "return_business_value": labels["network_business_value"],
                            "fill_rate": labels["network_fill_rate"],
                            "unmet_units": labels["unmet_units"],
                            "stockout_events": labels["stockout_events"],
                        },
                    })
                payload["rows"].extend(new_rows)
                payload["completed_units"].append(unit)
                completed.add(unit)
                _save_checkpoint(args.output, payload)

                done_this_run += 1
                done_total = len(completed)
                elapsed = time.perf_counter() - start
                avg = elapsed / max(1, done_this_run)
                eta = avg * max(0, total_units - done_total)
                unit_sec = time.perf_counter() - unit_start
                print(
                    f"[{split.upper():10}] {done_total:>3}/{total_units} | seed={seed} warmup={warmup:>2} "
                    f"target={target_index + 1}/{args.max_targets} | +{len(new_rows):>3} rows | "
                    f"unit={unit_sec:5.1f}s | rows={len(payload['rows']):>5} | ETA {_fmt(eta)}",
                    flush=True,
                )
    except KeyboardInterrupt:
        _save_checkpoint(args.output, payload)
        print("\nINTERRUPTED - checkpoint saved safely. Re-run the same command to resume.", flush=True)
        raise

    payload["metadata"]["generation_complete"] = True
    _save_checkpoint(args.output, payload)
    print("", flush=True)
    print(f"COMPLETE - Saved {len(payload['rows'])} counterfactual rows to {args.output}", flush=True)
    print(f"Elapsed: {_fmt(time.perf_counter() - start)}", flush=True)


if __name__ == "__main__":
    main()
