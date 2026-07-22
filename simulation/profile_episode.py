from __future__ import annotations

"""
Profile one complete simulation episode without modifying engine.py.

Usage:
    python -m simulation.profile_episode
    python -m simulation.profile_episode --seed 1
    python -m simulation.profile_episode --seed 5 --top 40

Outputs:
- console summary of the slowest functions;
- full profiling report in data/profiling/.
"""

from argparse import ArgumentParser
from cProfile import Profile
from datetime import datetime
from pathlib import Path
from pstats import SortKey, Stats

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine


def parse_args():
    parser = ArgumentParser(
        description=(
            "Profile one 365-day simulation episode without "
            "changing the simulation engine."
        )
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--top", type=int, default=35)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/profiling"),
    )
    return parser.parse_args()


def run_profile(seed: int, top: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = SimulationEngine(
        config=SimulationConfig(random_seed=seed),
        export_dataset=False,
    )

    profiler = Profile()
    profiler.enable()
    engine.initialize()
    engine.run(verbose=False)
    profiler.disable()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / (
        f"simulation_profile_seed_{seed}_{timestamp}.txt"
    )

    with report_path.open("w", encoding="utf-8") as file:
        stats = Stats(profiler, stream=file)
        stats.strip_dirs()
        stats.sort_stats(SortKey.CUMULATIVE)
        stats.print_stats()

    print()
    print("SIMULATION PERFORMANCE PROFILE")
    print("==============================")
    print(f"Seed                 : {seed}")
    print(f"Days Completed       : {engine.completed_days}")
    print(
        f"Pending Operations   : "
        f"{engine._require_state().pending_operation_count}"
    )
    print(
        f"Service Level        : "
        f"{engine.cumulative_service_level:.2%}"
    )
    print(
        f"Net Business Value   : "
        f"${engine.cumulative_economics.business_value:,.2f}"
    )
    print()
    print(f"TOP {top} FUNCTIONS BY CUMULATIVE TIME")
    print("=" * 45)

    console_stats = Stats(profiler)
    console_stats.strip_dirs()
    console_stats.sort_stats(SortKey.CUMULATIVE)
    console_stats.print_stats(top)

    print()
    print(f"Full report: {report_path}")
    return report_path


def main() -> None:
    args = parse_args()

    if args.seed < 0:
        raise ValueError("--seed cannot be negative.")

    if args.top <= 0:
        raise ValueError("--top must be greater than zero.")

    run_profile(
        seed=args.seed,
        top=args.top,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
