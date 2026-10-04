from __future__ import annotations

"""V25 FINAL 60-DAY TEST — 10 fresh held-out seeds (14000-14009).

Paired: EconomicConstrainedPolicy(14,3) vs V25 expanded action+quantity.
Gate ex-ante: mean delta > 0 AND wins >= 6/10 AND mean service delta >= -0.005
AND no catastrophic failure on any seed.
Max 4 workers, n_jobs=1, resume/skip valid results.
"""
import json
import math
import statistics
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SEEDS = list(range(14000, 14010))
MAX_WORKERS = 4
OUT_DIR = ROOT / "artifacts" / "model_based_v25" / "final_60d"
MODEL_PATH = ROOT / "artifacts" / "model_based_v25" / "action_value_model.joblib"


def run_seed(seed):
    import run_v24_smoke as smoke
    from simulation.economic_constrained_policy import (
        EconomicConstrainedConfig, EconomicConstrainedPolicy)
    old_seed = smoke.SEED
    smoke.SEED = seed
    try:
        baseline = smoke.run("baseline", EconomicConstrainedPolicy(
            EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3)))
        v25 = smoke.run("v25", smoke.ExpandedV24Policy(
            ROOT / "artifacts" / "model_based_v25" / "action_value_model.joblib"))
    finally:
        smoke.SEED = old_seed
    return {
        "seed": seed,
        "baseline": baseline,
        "v25": v25,
        "delta": v25["business_value"] - baseline["business_value"],
        "service_delta": v25["service_level"] - baseline["service_level"],
        "stockout_delta": v25["stockouts"] - baseline["stockouts"],
        "unmet_delta": v25["unmet_units"] - baseline["unmet_units"],
    }


REQUIRED = {"seed", "baseline", "v25", "delta", "service_delta",
            "stockout_delta", "unmet_delta"}


def _valid(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(d, dict) and REQUIRED.issubset(d.keys())


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wall0 = time.perf_counter()
    results, pending, failed = {}, [], []
    for seed in SEEDS:
        p = OUT_DIR / f"seed_{seed}.json"
        if p.exists() and _valid(p):
            print(f"SKIP seed {seed} — already complete", flush=True)
            results[seed] = json.loads(p.read_text(encoding="utf-8"))
        else:
            pending.append(seed)

    total = len(SEEDS)
    done = len(results)
    if done:
        print(f"PROGRESS {done}/{total}", flush=True)

    if pending:
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {}
            for seed in pending:
                print(f"START seed {seed}", flush=True)
                futs[pool.submit(run_seed, seed)] = seed
            for fut in as_completed(futs):
                seed = futs[fut]
                try:
                    r = fut.result()
                except Exception as exc:
                    failed.append(seed)
                    print(f"FAILED seed {seed} error={exc!r}", flush=True)
                    traceback.print_exc()
                    continue
                tmp = OUT_DIR / f"seed_{seed}.json.tmp"
                tmp.write_text(json.dumps(r, indent=2), encoding="utf-8")
                tmp.replace(OUT_DIR / f"seed_{seed}.json")
                results[seed] = r
                done += 1
                print(f"DONE seed {seed} delta=${r['delta']:+,.2f}", flush=True)
                print(f"PROGRESS {done}/{total}", flush=True)

    completed = sorted(results.keys())
    deltas = [results[s]["delta"] for s in completed]
    n = len(deltas)
    mean = statistics.fmean(deltas)
    median = statistics.median(deltas)
    std = statistics.stdev(deltas) if n > 1 else 0.0
    half = 2.262 * std / math.sqrt(n) if n == 10 else 0.0
    wins = sum(1 for d in deltas if d > 0)
    mean_svc = statistics.fmean(results[s]["service_delta"] for s in completed)
    worst = min(deltas)
    # catastrophic failure: worst seed loses more than 5% of its baseline bv
    catastrophic = [s for s in completed
                    if results[s]["delta"] < -0.05 * results[s]["baseline"]["business_value"]]

    g1 = mean > 0
    g2 = wins >= 6
    g3 = mean_svc >= -0.005
    g4 = not catastrophic
    verdict = "PASS" if (g1 and g2 and g3 and g4 and n == total) else "FAIL"

    agg = {
        "mean_delta": mean, "median_delta": median, "std": std,
        "ci95": (mean - half, mean + half), "worst": worst, "best": max(deltas),
        "wins": wins, "win_rate": wins / n,
        "mean_service_delta": mean_svc,
        "mean_stockout_delta": statistics.fmean(results[s]["stockout_delta"] for s in completed),
        "mean_unmet_delta": statistics.fmean(results[s]["unmet_delta"] for s in completed),
        "aggregate_economic_gain": sum(deltas),
        "catastrophic_seeds": catastrophic,
        "gate": {"mean_delta_pos": g1, "wins_ge_6": g2,
                 "service_ok": g3, "no_catastrophic": g4},
        "verdict": verdict,
    }

    L = ["V25 FINAL 60-DAY TEST", "", "SEED RESULTS"]
    for s in completed:
        r = results[s]
        b, v = r["baseline"], r["v25"]
        L.append(f"{s} baseline=${b['business_value']:,.2f} v25=${v['business_value']:,.2f} "
                 f"delta=${r['delta']:+,.2f} svc={r['service_delta']:+.4f} "
                 f"stk={r['stockout_delta']:+d} unmet={r['unmet_delta']:+d} "
                 f"actions N={v['ORDER_NORMAL']} E={v['ORDER_EXPEDITE']} "
                 f"T={v['TRANSFER_STOCK']} DN={v['DO_NOTHING']}")
    L += ["", "AGGREGATE",
          f"mean delta: ${mean:+,.2f}", f"median: ${median:+,.2f}",
          f"CI95: [${agg['ci95'][0]:+,.2f}, ${agg['ci95'][1]:+,.2f}]",
          f"worst: ${worst:+,.2f}", f"best: ${agg['best']:+,.2f}",
          f"wins: {wins}/{n}",
          f"mean service delta: {mean_svc:+.4f}",
          f"mean stockout delta: {agg['mean_stockout_delta']:+.2f}",
          f"mean unmet delta: {agg['mean_unmet_delta']:+.2f}",
          f"aggregate economic gain: ${agg['aggregate_economic_gain']:+,.2f}",
          f"catastrophic seeds: {catastrophic}",
          "", "GATE",
          f"mean delta > 0: {'YES' if g1 else 'NO'}",
          f"wins >= 6/10: {'YES' if g2 else 'NO'}",
          f"mean service delta >= -0.005: {'YES' if g3 else 'NO'}",
          f"no catastrophic failure: {'YES' if g4 else 'NO'}",
          f"VERDICT: {verdict}",
          f"failed: {sorted(failed)} wall={time.perf_counter() - wall0:.1f}s"]
    report = "\n".join(L)
    print(report, flush=True)
    (OUT_DIR / "final_60d_report.txt").write_text(report + "\n", encoding="utf-8")
    (OUT_DIR / "aggregate.json").write_text(json.dumps(agg, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
