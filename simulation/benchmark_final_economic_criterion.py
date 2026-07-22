from __future__ import annotations

"""Final validation protocol for V2 criterion 5: economic usefulness.

Protocol
--------
1. Calibrate policy hyperparameters on dedicated calibration seeds.
2. Keep only configurations meeting the service floor on calibration data.
3. Select the feasible configuration with the highest average business value.
4. Freeze it.
5. Compare the frozen policy against the simulator's existing rule-based policy
   on completely unseen evaluation seeds.

The separation of calibration and evaluation seeds prevents evaluation leakage.
"""

from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from statistics import mean, stdev
from time import perf_counter
import json
import math

from simulation.config import SimulationConfig
from simulation.economic_constrained_policy import (
    EconomicConstrainedConfig,
    EconomicConstrainedPolicy,
)
from simulation.engine import SimulationEngine


@dataclass(frozen=True)
class EpisodeResult:
    seed: int
    policy: str
    service_level: float
    business_value: float
    total_cost: float
    unmet_demand: int
    stockouts: int
    runtime_seconds: float


@dataclass(frozen=True)
class CandidateSummary:
    target_days_of_cover: float
    expedite_trigger_days: float
    average_service_level: float
    minimum_service_level: float
    average_business_value: float
    feasible: bool


def _run_engine(seed: int, config: EconomicConstrainedConfig | None) -> EpisodeResult:
    engine = SimulationEngine(
        config=SimulationConfig(random_seed=seed),
        export_dataset=False,
    )
    engine.initialize()
    policy_name = "rule_based"
    if config is not None:
        engine.decision_policy = EconomicConstrainedPolicy(config)
        policy_name = "economic_constrained"

    started = perf_counter()
    engine.run(verbose=False)
    runtime = perf_counter() - started
    economics = engine.cumulative_economics
    return EpisodeResult(
        seed=seed,
        policy=policy_name,
        service_level=engine.cumulative_service_level,
        business_value=economics.business_value,
        total_cost=economics.total_cost,
        unmet_demand=engine.cumulative_unmet_demand,
        stockouts=engine.cumulative_stockouts,
        runtime_seconds=runtime,
    )


def _run_many(
    seeds: list[int],
    config: EconomicConstrainedConfig | None,
    workers: int,
) -> list[EpisodeResult]:
    rows: list[EpisodeResult] = []
    with ProcessPoolExecutor(max_workers=min(workers, len(seeds))) as executor:
        futures = {executor.submit(_run_engine, seed, config): seed for seed in seeds}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row.seed)
    return rows


def confidence_interval_95(values: list[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("values cannot be empty")
    center = mean(values)
    if len(values) == 1:
        return center, center
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return center - margin, center + margin


def paired_deltas(
    candidate_rows: list[EpisodeResult],
    baseline_rows: list[EpisodeResult],
    field: str,
) -> list[float]:
    baseline_by_seed = {row.seed: row for row in baseline_rows}
    if {row.seed for row in candidate_rows} != set(baseline_by_seed):
        raise ValueError("Candidate and baseline seeds must match")
    return [
        float(getattr(row, field)) - float(getattr(baseline_by_seed[row.seed], field))
        for row in candidate_rows
    ]


def calibrate(
    seeds: list[int],
    workers: int,
    service_floor: float,
    days_cover_grid: list[float],
    expedite_grid: list[float],
) -> tuple[EconomicConstrainedConfig, list[CandidateSummary]]:
    summaries: list[CandidateSummary] = []
    for days_cover, expedite_trigger in product(days_cover_grid, expedite_grid):
        if expedite_trigger > days_cover:
            continue
        config = EconomicConstrainedConfig(
            target_days_of_cover=days_cover,
            expedite_trigger_days=expedite_trigger,
        )
        rows = _run_many(seeds, config, workers)
        avg_service = mean(row.service_level for row in rows)
        min_service = min(row.service_level for row in rows)
        avg_value = mean(row.business_value for row in rows)
        summaries.append(
            CandidateSummary(
                target_days_of_cover=days_cover,
                expedite_trigger_days=expedite_trigger,
                average_service_level=avg_service,
                minimum_service_level=min_service,
                average_business_value=avg_value,
                feasible=avg_service >= service_floor,
            )
        )
        print(
            f"Calibration cover={days_cover:>4.0f} expedite<{expedite_trigger:>4.0f}d | "
            f"service={avg_service:.2%} | min={min_service:.2%} | "
            f"value=${avg_value:,.2f} | {'FEASIBLE' if avg_service >= service_floor else 'reject'}",
            flush=True,
        )

    feasible = [summary for summary in summaries if summary.feasible]
    if not feasible:
        best_service = max(summaries, key=lambda item: item.average_service_level)
        raise RuntimeError(
            "No calibrated configuration reached the service floor. "
            f"Best average service was {best_service.average_service_level:.2%} "
            f"at cover={best_service.target_days_of_cover}, "
            f"expedite={best_service.expedite_trigger_days}."
        )

    winner = max(
        feasible,
        key=lambda item: (
            item.average_business_value,
            item.minimum_service_level,
            -item.target_days_of_cover,
        ),
    )
    return (
        EconomicConstrainedConfig(
            target_days_of_cover=winner.target_days_of_cover,
            expedite_trigger_days=winner.expedite_trigger_days,
        ),
        summaries,
    )


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        "--calibration-seeds",
        nargs="+",
        type=int,
        default=[201, 202, 203, 204, 205, 206, 207, 208],
    )
    parser.add_argument(
        "--evaluation-seeds",
        nargs="+",
        type=int,
        default=list(range(301, 331)),
    )
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--service-floor", type=float, default=0.95)
    parser.add_argument("--minimum-value-win-rate", type=float, default=0.60)
    parser.add_argument("--minimum-joint-win-rate", type=float, default=0.50)
    parser.add_argument("--minimum-episodes", type=int, default=30)
    parser.add_argument(
        "--days-cover-grid",
        nargs="+",
        type=float,
        default=[14, 18, 21, 24, 28, 32, 36, 40, 45],
    )
    parser.add_argument(
        "--expedite-grid",
        nargs="+",
        type=float,
        default=[3, 5, 7, 10, 14, 21, 30, 45],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/policy_training/final_economic_criterion/summary.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if set(args.calibration_seeds) & set(args.evaluation_seeds):
        raise ValueError("Calibration and evaluation seeds must be disjoint")
    if len(args.evaluation_seeds) < args.minimum_episodes:
        raise ValueError(
            f"At least {args.minimum_episodes} evaluation episodes are required"
        )

    print("V2 CRITERION 5 — FINAL ECONOMIC VALIDATION")
    print("==========================================")
    print(f"Calibration seeds : {args.calibration_seeds}")
    print(f"Evaluation seeds  : {args.evaluation_seeds}")
    print(f"Service floor     : {args.service_floor:.2%}")
    print()

    started = perf_counter()
    selected_config, calibration = calibrate(
        seeds=args.calibration_seeds,
        workers=args.workers,
        service_floor=args.service_floor,
        days_cover_grid=args.days_cover_grid,
        expedite_grid=args.expedite_grid,
    )

    print()
    print("FROZEN POLICY")
    print("=============")
    print(f"Target days of cover : {selected_config.target_days_of_cover:.0f}")
    print(f"Expedite below       : {selected_config.expedite_trigger_days:.0f} days")
    print()
    print("Running final unseen evaluation...")

    candidate_rows = _run_many(args.evaluation_seeds, selected_config, args.workers)
    baseline_rows = _run_many(args.evaluation_seeds, None, args.workers)

    value_deltas = paired_deltas(candidate_rows, baseline_rows, "business_value")
    service_deltas = paired_deltas(candidate_rows, baseline_rows, "service_level")
    value_ci = confidence_interval_95(value_deltas)
    service_ci = confidence_interval_95(service_deltas)

    candidate_service = mean(row.service_level for row in candidate_rows)
    candidate_value = mean(row.business_value for row in candidate_rows)
    baseline_service = mean(row.service_level for row in baseline_rows)
    baseline_value = mean(row.business_value for row in baseline_rows)
    value_win_rate = mean(delta > 0 for delta in value_deltas)
    service_win_rate = mean(delta >= 0 for delta in service_deltas)
    joint_win_rate = mean(
        value_delta > 0 and service_delta >= 0
        for value_delta, service_delta in zip(value_deltas, service_deltas)
    )

    checks = {
        "minimum_episodes": len(candidate_rows) >= args.minimum_episodes,
        "service_floor": candidate_service >= args.service_floor,
        "positive_average_value_delta": mean(value_deltas) > 0,
        "value_ci95_above_zero": value_ci[0] > 0,
        "minimum_value_win_rate": value_win_rate >= args.minimum_value_win_rate,
        "minimum_joint_win_rate": joint_win_rate >= args.minimum_joint_win_rate,
    }
    accepted = all(checks.values())

    result = {
        "protocol": "calibrate_then_freeze_then_evaluate",
        "criterion": "V2 criterion 5 — economic usefulness under service constraint",
        "anti_leakage": {
            "calibration_and_evaluation_seeds_disjoint": True,
            "policy_uses_decision_time_information_only": True,
            "evaluation_configuration_frozen_before_evaluation": True,
        },
        "thresholds": {
            "service_floor": args.service_floor,
            "minimum_value_win_rate": args.minimum_value_win_rate,
            "minimum_joint_win_rate": args.minimum_joint_win_rate,
            "minimum_episodes": args.minimum_episodes,
        },
        "selected_config": asdict(selected_config),
        "calibration_seeds": args.calibration_seeds,
        "evaluation_seeds": args.evaluation_seeds,
        "calibration": [asdict(row) for row in calibration],
        "evaluation": {
            "candidate_average_service_level": candidate_service,
            "candidate_average_business_value": candidate_value,
            "baseline_average_service_level": baseline_service,
            "baseline_average_business_value": baseline_value,
            "average_service_delta": mean(service_deltas),
            "service_delta_ci95": service_ci,
            "average_value_delta": mean(value_deltas),
            "value_delta_ci95": value_ci,
            "value_win_rate": value_win_rate,
            "service_non_degradation_rate": service_win_rate,
            "joint_win_rate": joint_win_rate,
            "candidate_runs": [asdict(row) for row in candidate_rows],
            "baseline_runs": [asdict(row) for row in baseline_rows],
        },
        "checks": checks,
        "accepted": accepted,
        "wall_clock_seconds": perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print()
    print("FINAL RESULT")
    print("============")
    print(f"Candidate service  : {candidate_service:.2%}")
    print(f"Baseline service   : {baseline_service:.2%}")
    print(f"Candidate value    : ${candidate_value:,.2f}")
    print(f"Baseline value     : ${baseline_value:,.2f}")
    print(f"Average value gain : ${mean(value_deltas):,.2f}")
    print(f"Value CI95         : ${value_ci[0]:,.2f} .. ${value_ci[1]:,.2f}")
    print(f"Value win rate     : {value_win_rate:.2%}")
    print(f"Joint win rate     : {joint_win_rate:.2%}")
    print()
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print()
    print(f"CRITERION 5        : {'PASS' if accepted else 'FAIL'}")
    print(f"Report             : {args.output.resolve()}")

    if not accepted:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
