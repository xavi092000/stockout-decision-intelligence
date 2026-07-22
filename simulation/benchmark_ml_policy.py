from __future__ import annotations

"""
Closed-loop economic benchmark:
RuleBasedDecisionPolicy vs MLDecisionPolicy on unseen seeds.

Usage:
    python -m simulation.benchmark_ml_policy

Example with fewer seeds:
    python -m simulation.benchmark_ml_policy --seeds 101 102 103
"""

from argparse import ArgumentParser
from csv import DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.ml_decision_policy import MLDecisionPolicy


@dataclass(frozen=True)
class BenchmarkRow:
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


def parse_args():
    parser = ArgumentParser()

    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=list(range(101, 111)),
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
        "--output",
        type=Path,
        default=Path(
            "artifacts/policy_training/"
            "closed_loop_benchmark.csv"
        ),
    )

    return parser.parse_args()


def run_policy(
    *,
    seed: int,
    policy_name: str,
    model_path: Path,
) -> BenchmarkRow:
    engine = SimulationEngine(
        config=SimulationConfig(random_seed=seed),
        export_dataset=False,
    )

    engine.initialize()

    ml_policy = None

    if policy_name == "ML_DECISION_TREE":
        ml_policy = MLDecisionPolicy(
            model_path=model_path
        )
        engine.decision_policy = ml_policy

    started = perf_counter()
    engine.run(verbose=False)
    runtime = perf_counter() - started

    state = engine._require_state()
    economics = engine.cumulative_economics

    return BenchmarkRow(
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
    )


def main() -> None:
    args = parse_args()

    rows: list[BenchmarkRow] = []

    for index, seed in enumerate(
        args.seeds,
        start=1,
    ):
        print(
            f"Benchmark seed {seed} "
            f"({index}/{len(args.seeds)})",
            flush=True,
        )

        for policy_name in (
            "RULE_BASED",
            "ML_DECISION_TREE",
        ):
            row = run_policy(
                seed=seed,
                policy_name=policy_name,
                model_path=args.model_path,
            )
            rows.append(row)

            print(
                f"  {policy_name:<18} "
                f"| Service: {row.service_level:.2%} "
                f"| Value: "
                f"${row.net_business_value:,.2f} "
                f"| Stockouts: "
                f"{row.stockout_events:,} "
                f"| Fallbacks: "
                f"{row.ml_fallback_count:,}"
            )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = DictWriter(
            file,
            fieldnames=list(
                BenchmarkRow.__dataclass_fields__.keys()
            ),
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(asdict(row))

    print()
    print("CLOSED-LOOP BENCHMARK SUMMARY")
    print("=============================")

    for policy_name in (
        "RULE_BASED",
        "ML_DECISION_TREE",
    ):
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
            f"Average Stockouts     : "
            f"{mean(row.stockout_events for row in selected):,.2f}"
        )
        print(
            f"Average Unmet Demand  : "
            f"{mean(row.unmet_demand for row in selected):,.2f}"
        )
        print(
            f"Average Total Cost    : "
            f"${mean(row.total_cost for row in selected):,.2f}"
        )

    rule_rows = {
        row.seed: row
        for row in rows
        if row.policy == "RULE_BASED"
    }
    ml_rows = {
        row.seed: row
        for row in rows
        if row.policy == "ML_DECISION_TREE"
    }

    value_deltas = [
        (
            ml_rows[seed].net_business_value
            - rule_rows[seed].net_business_value
        )
        for seed in args.seeds
    ]

    service_deltas = [
        (
            ml_rows[seed].service_level
            - rule_rows[seed].service_level
        )
        for seed in args.seeds
    ]

    print()
    print("ML MINUS RULE-BASED")
    print("-------------------")
    print(
        f"Average Value Delta  : "
        f"${mean(value_deltas):,.2f}"
    )
    print(
        f"Average Service Delta: "
        f"{mean(service_deltas):+.2%}"
    )
    print()
    print(f"Results exported to: {args.output}")


if __name__ == "__main__":
    main()
