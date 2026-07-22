from __future__ import annotations

"""
Robust paired closed-loop benchmark for Rule-Based vs ML policy.

Scientific design:
- same unseen seed for both policies;
- complete 365-day episodes;
- paired deltas by seed;
- mean, median, standard deviation, 95% confidence interval;
- win rate and downside rate;
- each episode remains sequential;
- independent seeds may run in parallel.

Usage:
    python -m simulation.benchmark_ml_policy_robust

Example:
    python -m simulation.benchmark_ml_policy_robust ^
        --start-seed 101 ^
        --episodes 30 ^
        --workers 6
"""

from argparse import ArgumentParser
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed,
)
from csv import DictWriter
from dataclasses import asdict, dataclass
from math import sqrt
from pathlib import Path
from statistics import mean, median, stdev
from time import perf_counter
import json

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.ml_decision_policy import MLDecisionPolicy
from simulation.validation.ml_protocol import DEFAULT_EPISODE_SPLIT
from simulation.validation.economic_protocol import (
    EconomicAcceptanceCriteria,
    evaluate_economic_superiority,
)
from simulation.validation.economic_robustness import (
    DEFAULT_ECONOMIC_SCENARIOS,
    OperationalEconomics,
    evaluate_robustness_campaign,
)


@dataclass(frozen=True)
class PolicyRun:
    seed: int
    policy: str
    service_level: float
    net_business_value: float
    total_cost: float
    revenue: float
    unmet_demand: int
    stockout_events: int
    ending_stock: int
    pending_operations: int
    runtime_seconds: float
    ml_fallback_count: int
    fulfilled_units: int
    ending_stock_unit_days: int
    normal_order_units: int
    expedite_order_units: int
    transferred_units: int


@dataclass(frozen=True)
class PairedDelta:
    seed: int
    value_delta: float
    service_delta: float
    cost_delta: float
    unmet_demand_delta: int
    stockout_delta: int
    ml_fallback_count: int


def parse_args():
    parser = ArgumentParser(
        description=(
            "Run a statistically stronger paired closed-loop "
            "benchmark on unseen simulation seeds."
        )
    )
    parser.add_argument(
        "--start-seed",
        type=int,
        default=101,
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path(
            "artifacts/policy_training/"
            "decision_tree.joblib"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "artifacts/policy_training/"
            "robust_benchmark"
        ),
    )
    return parser.parse_args()


def run_single_policy(
    *,
    seed: int,
    policy_name: str,
    model_path_text: str,
) -> PolicyRun:
    engine = SimulationEngine(
        config=SimulationConfig(
            random_seed=seed,
        ),
        export_dataset=False,
    )
    engine.initialize()

    ml_policy = None

    if policy_name == "ML_DECISION_TREE":
        ml_policy = MLDecisionPolicy(
            model_path=Path(model_path_text)
        )
        engine.decision_policy = ml_policy

    started = perf_counter()
    engine.run(verbose=False)
    runtime = perf_counter() - started

    state = engine._require_state()
    economics = engine.cumulative_economics

    return PolicyRun(
        seed=seed,
        policy=policy_name,
        service_level=engine.cumulative_service_level,
        net_business_value=economics.business_value,
        total_cost=economics.total_cost,
        revenue=economics.revenue,
        unmet_demand=engine.cumulative_unmet_demand,
        stockout_events=engine.cumulative_stockouts,
        ending_stock=state.total_stock,
        pending_operations=(
            state.pending_operation_count
        ),
        runtime_seconds=runtime,
        ml_fallback_count=(
            ml_policy.fallback_count
            if ml_policy is not None
            else 0
        ),
        fulfilled_units=economics.fulfilled_units,
        ending_stock_unit_days=economics.ending_stock_unit_days,
        normal_order_units=economics.normal_order_units,
        expedite_order_units=economics.expedite_order_units,
        transferred_units=economics.transferred_units,
    )


def run_seed_pair(
    seed: int,
    model_path_text: str,
) -> tuple[PolicyRun, PolicyRun]:
    rule = run_single_policy(
        seed=seed,
        policy_name="RULE_BASED",
        model_path_text=model_path_text,
    )
    ml = run_single_policy(
        seed=seed,
        policy_name="ML_DECISION_TREE",
        model_path_text=model_path_text,
    )
    return rule, ml


def confidence_interval_95(
    values: list[float],
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)

    average = mean(values)

    if len(values) == 1:
        return (average, average)

    standard_error = (
        stdev(values) / sqrt(len(values))
    )
    margin = 1.96 * standard_error

    return (
        average - margin,
        average + margin,
    )


def metric_summary(
    values: list[float],
) -> dict[str, float]:
    low, high = confidence_interval_95(values)

    return {
        "count": len(values),
        "mean": mean(values),
        "median": median(values),
        "standard_deviation": (
            stdev(values)
            if len(values) > 1
            else 0.0
        ),
        "ci95_low": low,
        "ci95_high": high,
        "minimum": min(values),
        "maximum": max(values),
    }


def build_deltas(
    rows: list[PolicyRun],
) -> list[PairedDelta]:
    by_seed: dict[int, dict[str, PolicyRun]] = {}

    for row in rows:
        by_seed.setdefault(
            row.seed,
            {},
        )[row.policy] = row

    deltas: list[PairedDelta] = []

    for seed in sorted(by_seed):
        pair = by_seed[seed]

        rule = pair.get("RULE_BASED")
        ml = pair.get("ML_DECISION_TREE")

        if rule is None or ml is None:
            raise RuntimeError(
                f"Incomplete policy pair for seed {seed}."
            )

        deltas.append(
            PairedDelta(
                seed=seed,
                value_delta=(
                    ml.net_business_value
                    - rule.net_business_value
                ),
                service_delta=(
                    ml.service_level
                    - rule.service_level
                ),
                cost_delta=(
                    ml.total_cost
                    - rule.total_cost
                ),
                unmet_demand_delta=(
                    ml.unmet_demand
                    - rule.unmet_demand
                ),
                stockout_delta=(
                    ml.stockout_events
                    - rule.stockout_events
                ),
                ml_fallback_count=(
                    ml.ml_fallback_count
                ),
            )
        )

    return deltas


def write_csv(
    path: Path,
    rows,
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(asdict(row))


def print_policy_summary(
    policy_name: str,
    rows: list[PolicyRun],
) -> None:
    selected = [
        row
        for row in rows
        if row.policy == policy_name
    ]

    print()
    print(policy_name)
    print("-" * len(policy_name))
    print(
        f"Average Service Level : "
        f"{mean(row.service_level for row in selected):.2%}"
    )
    print(
        f"Average Business Value: "
        f"${mean(row.net_business_value for row in selected):,.2f}"
    )
    print(
        f"Average Total Cost    : "
        f"${mean(row.total_cost for row in selected):,.2f}"
    )
    print(
        f"Average Stockouts     : "
        f"{mean(row.stockout_events for row in selected):,.2f}"
    )
    print(
        f"Average Unmet Demand  : "
        f"{mean(row.unmet_demand for row in selected):,.2f}"
    )


def print_delta_summary(
    deltas: list[PairedDelta],
) -> dict:
    value_deltas = [
        row.value_delta for row in deltas
    ]
    service_deltas = [
        row.service_delta for row in deltas
    ]
    cost_deltas = [
        row.cost_delta for row in deltas
    ]
    unmet_deltas = [
        float(row.unmet_demand_delta)
        for row in deltas
    ]
    stockout_deltas = [
        float(row.stockout_delta)
        for row in deltas
    ]

    value_summary = metric_summary(
        value_deltas
    )
    service_summary = metric_summary(
        service_deltas
    )

    win_count = sum(
        delta > 0
        for delta in value_deltas
    )
    service_win_count = sum(
        delta > 0
        for delta in service_deltas
    )
    joint_win_count = sum(
        (
            row.value_delta > 0
            and row.service_delta > 0
        )
        for row in deltas
    )

    print()
    print("PAIRED ML MINUS RULE-BASED")
    print("==========================")
    print(
        f"Average Value Delta     : "
        f"${value_summary['mean']:,.2f}"
    )
    print(
        f"Value Delta 95% CI      : "
        f"[${value_summary['ci95_low']:,.2f}, "
        f"${value_summary['ci95_high']:,.2f}]"
    )
    print(
        f"Median Value Delta      : "
        f"${value_summary['median']:,.2f}"
    )
    print(
        f"Average Service Delta   : "
        f"{service_summary['mean']:+.2%}"
    )
    print(
        f"Service Delta 95% CI    : "
        f"[{service_summary['ci95_low']:+.2%}, "
        f"{service_summary['ci95_high']:+.2%}]"
    )
    print(
        f"Value Win Rate          : "
        f"{win_count / len(deltas):.2%}"
    )
    print(
        f"Service Win Rate        : "
        f"{service_win_count / len(deltas):.2%}"
    )
    print(
        f"Joint Value+Service Wins: "
        f"{joint_win_count / len(deltas):.2%}"
    )
    print(
        f"Average Cost Delta      : "
        f"${mean(cost_deltas):,.2f}"
    )
    print(
        f"Average Unmet Delta     : "
        f"{mean(unmet_deltas):,.2f}"
    )
    print(
        f"Average Stockout Delta  : "
        f"{mean(stockout_deltas):,.2f}"
    )

    return {
        "value_delta": value_summary,
        "service_delta": service_summary,
        "cost_delta": metric_summary(
            cost_deltas
        ),
        "unmet_demand_delta": metric_summary(
            unmet_deltas
        ),
        "stockout_delta": metric_summary(
            stockout_deltas
        ),
        "value_win_rate": (
            win_count / len(deltas)
        ),
        "service_win_rate": (
            service_win_count / len(deltas)
        ),
        "joint_value_service_win_rate": (
            joint_win_count / len(deltas)
        ),
    }


def main() -> None:
    args = parse_args()

    if args.episodes <= 0:
        raise ValueError(
            "--episodes must be greater than zero."
        )

    if args.workers <= 0:
        raise ValueError(
            "--workers must be greater than zero."
        )

    if not args.model_path.exists():
        raise FileNotFoundError(
            f"Model not found: "
            f"{args.model_path.resolve()}"
        )

    seeds = list(
        DEFAULT_EPISODE_SPLIT.validate_benchmark_seeds(
            range(
                args.start_seed,
                args.start_seed + args.episodes,
            )
        )
    )

    print("ROBUST CLOSED-LOOP POLICY BENCHMARK")
    print("===================================")
    print(f"Unseen seeds : {seeds[0]}..{seeds[-1]}")
    print(f"Episodes     : {len(seeds)}")
    print(f"Workers      : {args.workers}")
    print()

    rows: list[PolicyRun] = []
    started = perf_counter()

    with ProcessPoolExecutor(
        max_workers=args.workers,
    ) as executor:
        future_to_seed = {
            executor.submit(
                run_seed_pair,
                seed,
                str(args.model_path),
            ): seed
            for seed in seeds
        }

        for completed, future in enumerate(
            as_completed(future_to_seed),
            start=1,
        ):
            seed = future_to_seed[future]
            rule, ml = future.result()
            rows.extend((rule, ml))

            print(
                f"Completed {completed:02d}/"
                f"{len(seeds):02d} "
                f"| Seed {seed} "
                f"| Value Δ: "
                f"${ml.net_business_value - rule.net_business_value:,.2f} "
                f"| Service Δ: "
                f"{ml.service_level - rule.service_level:+.2%}",
                flush=True,
            )

    wall_clock = perf_counter() - started

    rows.sort(
        key=lambda row: (
            row.seed,
            row.policy,
        )
    )
    deltas = build_deltas(rows)

    print()
    print(
        f"Wall-clock runtime: "
        f"{wall_clock:.2f}s"
    )

    print_policy_summary(
        "RULE_BASED",
        rows,
    )
    print_policy_summary(
        "ML_DECISION_TREE",
        rows,
    )
    summary = print_delta_summary(
        deltas
    )

    ml_rows = [
        row for row in rows
        if row.policy == "ML_DECISION_TREE"
    ]
    acceptance = evaluate_economic_superiority(
        episode_count=len(deltas),
        candidate_average_service_level=mean(
            row.service_level for row in ml_rows
        ),
        mean_value_delta=summary["value_delta"]["mean"],
        value_ci95_low=summary["value_delta"]["ci95_low"],
        mean_service_delta=summary["service_delta"]["mean"],
        value_win_rate=summary["value_win_rate"],
        joint_value_service_win_rate=(
            summary["joint_value_service_win_rate"]
        ),
        criteria=EconomicAcceptanceCriteria(),
    )

    by_policy = {
        "RULE_BASED": [
            OperationalEconomics(
                fulfilled_units=row.fulfilled_units,
                unmet_units=row.unmet_demand,
                ending_stock_unit_days=row.ending_stock_unit_days,
                stockout_events=row.stockout_events,
                normal_order_units=row.normal_order_units,
                expedite_order_units=row.expedite_order_units,
                transferred_units=row.transferred_units,
            )
            for row in rows
            if row.policy == "RULE_BASED"
        ],
        "ML_DECISION_TREE": [
            OperationalEconomics(
                fulfilled_units=row.fulfilled_units,
                unmet_units=row.unmet_demand,
                ending_stock_unit_days=row.ending_stock_unit_days,
                stockout_events=row.stockout_events,
                normal_order_units=row.normal_order_units,
                expedite_order_units=row.expedite_order_units,
                transferred_units=row.transferred_units,
            )
            for row in rows
            if row.policy == "ML_DECISION_TREE"
        ],
    }
    robustness = evaluate_robustness_campaign(
        rule_runs=by_policy["RULE_BASED"],
        candidate_runs=by_policy["ML_DECISION_TREE"],
        scenarios=DEFAULT_ECONOMIC_SCENARIOS,
        criteria=EconomicAcceptanceCriteria(),
    )

    print()
    print("ECONOMIC SENSITIVITY ROBUSTNESS")
    print("===============================")
    for scenario_result in robustness.scenario_results:
        verdict = "PASS" if scenario_result.accepted else "FAIL"
        print(
            f"{scenario_result.scenario:28s}: {verdict} "
            f"| Mean value delta ${scenario_result.mean_value_delta:,.2f} "
            f"| CI low ${scenario_result.value_ci95_low:,.2f}"
        )
    print(
        "ROBUST ACCEPTANCE: "
        + ("ACCEPTED" if robustness.accepted else "REJECTED")
    )

    print()
    print("FORMAL ECONOMIC ACCEPTANCE")
    print("==========================")
    print(
        "ACCEPTED" if acceptance.accepted else "REJECTED"
    )
    if acceptance.reasons:
        print(
            "Failed checks: " + ", ".join(acceptance.reasons)
        )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        args.output_dir / "policy_runs.csv",
        rows,
        list(
            PolicyRun.__dataclass_fields__.keys()
        ),
    )
    write_csv(
        args.output_dir / "paired_deltas.csv",
        deltas,
        list(
            PairedDelta.__dataclass_fields__.keys()
        ),
    )

    summary_payload = {
        "start_seed": args.start_seed,
        "episodes": args.episodes,
        "workers": args.workers,
        "model_path": str(
            args.model_path.resolve()
        ),
        "wall_clock_seconds": wall_clock,
        "paired_summary": summary,
        "economic_robustness": {
            "accepted": robustness.accepted,
            "failed_scenarios": list(robustness.failed_scenarios),
            "worst_case_mean_value_delta": robustness.worst_case_mean_value_delta,
            "scenario_results": [asdict(result) for result in robustness.scenario_results],
        },
        "economic_acceptance": {
            "accepted": acceptance.accepted,
            "checks": acceptance.checks,
            "reasons": list(acceptance.reasons),
            "criteria": asdict(EconomicAcceptanceCriteria()),
        },
    }

    summary_path = (
        args.output_dir / "summary.json"
    )
    summary_path.write_text(
        json.dumps(
            summary_payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Results:")
    print(
        f"- {args.output_dir / 'policy_runs.csv'}"
    )
    print(
        f"- {args.output_dir / 'paired_deltas.csv'}"
    )
    print(f"- {summary_path}")
    print()
    print(
        "Do not claim the ML policy is superior unless the "
        "paired confidence interval and win rates support it."
    )


if __name__ == "__main__":
    main()
