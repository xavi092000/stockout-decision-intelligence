from __future__ import annotations

"""Fast full-year service-ceiling probe.

Runs only five unseen seeds by default so the first diagnostic is much faster than the
30-episode economic robustness campaign. Expand only if the result is close to 95%.
"""

from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
import json

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.service_ceiling_policy import ServiceCeilingConfig, ServiceCeilingPolicy


@dataclass(frozen=True)
class CeilingRun:
    seed: int
    service_level: float
    business_value: float
    total_cost: float
    unmet_demand: int
    stockouts: int
    runtime_seconds: float


def run_seed(seed: int, days_cover: float) -> CeilingRun:
    engine = SimulationEngine(
        config=SimulationConfig(random_seed=seed),
        export_dataset=False,
    )
    engine.initialize()
    engine.decision_policy = ServiceCeilingPolicy(
        ServiceCeilingConfig(target_days_of_cover=days_cover)
    )
    started = perf_counter()
    engine.run(verbose=False)
    runtime = perf_counter() - started
    economics = engine.cumulative_economics
    return CeilingRun(
        seed=seed,
        service_level=engine.cumulative_service_level,
        business_value=economics.business_value,
        total_cost=economics.total_cost,
        unmet_demand=engine.cumulative_unmet_demand,
        stockouts=engine.cumulative_stockouts,
        runtime_seconds=runtime,
    )


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=[131, 132, 133, 134, 135])
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--days-cover", type=float, default=45.0)
    parser.add_argument("--service-target", type=float, default=0.95)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/policy_training/service_ceiling_fast/summary.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("FAST SERVICE-CEILING PROBE")
    print("==========================")
    print(f"Seeds       : {args.seeds}")
    print(f"Episodes    : {len(args.seeds)}")
    print(f"Workers     : {args.workers}")
    print(f"Days cover  : {args.days_cover:.0f}")
    print(f"Target      : {args.service_target:.2%}")
    print()

    rows: list[CeilingRun] = []
    started = perf_counter()
    with ProcessPoolExecutor(max_workers=min(args.workers, len(args.seeds))) as executor:
        futures = {executor.submit(run_seed, seed, args.days_cover): seed for seed in args.seeds}
        for index, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            rows.append(row)
            print(
                f"Completed {index:02d}/{len(args.seeds):02d} | Seed {row.seed} | "
                f"Service {row.service_level:.2%} | Cost ${row.total_cost:,.2f}",
                flush=True,
            )

    rows.sort(key=lambda row: row.seed)
    average_service = mean(row.service_level for row in rows)
    minimum_service = min(row.service_level for row in rows)
    maximum_service = max(row.service_level for row in rows)
    target_reached = average_service >= args.service_target
    result = {
        "protocol": "fast_service_ceiling_probe",
        "warning": (
            "This is an aggressive non-production policy, not a clairvoyant mathematical oracle. "
            "It estimates whether the simulator can approach the target when service is prioritized."
        ),
        "seeds": args.seeds,
        "target_days_of_cover": args.days_cover,
        "service_target": args.service_target,
        "average_service_level": average_service,
        "minimum_service_level": minimum_service,
        "maximum_service_level": maximum_service,
        "target_reached_on_average": target_reached,
        "wall_clock_seconds": perf_counter() - started,
        "runs": [asdict(row) for row in rows],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print()
    print("RESULT")
    print("======")
    print(f"Average service : {average_service:.2%}")
    print(f"Range           : {minimum_service:.2%} .. {maximum_service:.2%}")
    print(f"95% target      : {'REACHED' if target_reached else 'NOT REACHED'}")
    print(f"Report          : {args.output.resolve()}")
    print()
    if average_service >= 0.93:
        print("Interpretation: close enough to justify a larger 30-seed confirmation.")
    elif average_service >= 0.85:
        print("Interpretation: 95% may be difficult; tune the probe before changing the threshold.")
    else:
        print("Interpretation: the simulator constraints likely dominate; inspect supply capacity and lead times.")


if __name__ == "__main__":
    main()
