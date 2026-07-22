from __future__ import annotations

"""
Generate many independent simulation episodes for model training.

Each episode:
- uses a distinct random seed;
- starts from a fresh initialized world;
- runs for 365 days;
- exports one leakage-safe CSV;
- preserves episode boundaries for train/validation/test splitting.

Usage:
    python -m simulation.multi_episode_runner
    python -m simulation.multi_episode_runner --episodes 100
    python -m simulation.multi_episode_runner --episodes 100 --start-seed 1
"""

from argparse import ArgumentParser
from csv import DictWriter
from dataclasses import dataclass, asdict
from pathlib import Path
from time import perf_counter

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine


@dataclass(frozen=True)
class EpisodeSummary:
    episode_index: int
    seed: int
    dataset_path: str
    dataset_rows: int
    service_level: float
    total_demand: int
    fulfilled_demand: int
    unmet_demand: int
    stockout_events: int
    units_received: int
    ending_stock: int
    revenue: float
    total_cost: float
    net_business_value: float
    runtime_seconds: float


def parse_args() -> tuple[int, int, Path]:
    parser = ArgumentParser(
        description=(
            "Generate independent stockout simulation episodes "
            "for leakage-safe ML training."
        )
    )

    parser.add_argument(
        "--episodes",
        type=int,
        default=100,
        help="Number of independent 365-day episodes.",
    )
    parser.add_argument(
        "--start-seed",
        type=int,
        default=1,
        help="First random seed to use.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/training/multi_episode"),
        help="Directory for per-seed datasets and episode summary.",
    )

    args = parser.parse_args()

    if args.episodes <= 0:
        parser.error("--episodes must be greater than zero.")

    if args.start_seed < 0:
        parser.error("--start-seed cannot be negative.")

    return args.episodes, args.start_seed, args.output_dir


def run_episode(
    *,
    episode_index: int,
    seed: int,
    output_dir: Path,
) -> EpisodeSummary:
    config = SimulationConfig(
        random_seed=seed,
    )

    engine = SimulationEngine(
        config=config,
        dataset_output_directory=output_dir,
        export_dataset=True,
    )

    started = perf_counter()

    engine.initialize()
    engine.run(verbose=False)

    runtime_seconds = perf_counter() - started

    state = engine._require_state()
    economics = engine.cumulative_economics

    if engine.last_dataset_path is None:
        raise RuntimeError(
            f"Episode seed={seed} completed without exporting a dataset."
        )

    expected_rows = (
        config.number_of_days
        * config.number_of_products
        * config.number_of_stores
    )

    actual_rows = engine.dataset_builder.row_count

    if actual_rows != expected_rows:
        raise RuntimeError(
            f"Episode seed={seed} produced {actual_rows:,} rows; "
            f"expected {expected_rows:,}."
        )

    return EpisodeSummary(
        episode_index=episode_index,
        seed=seed,
        dataset_path=str(engine.last_dataset_path),
        dataset_rows=actual_rows,
        service_level=engine.cumulative_service_level,
        total_demand=engine.cumulative_demand,
        fulfilled_demand=engine.cumulative_fulfilled_demand,
        unmet_demand=engine.cumulative_unmet_demand,
        stockout_events=engine.cumulative_stockouts,
        units_received=engine.cumulative_units_received,
        ending_stock=state.total_stock,
        revenue=economics.revenue,
        total_cost=economics.total_cost,
        net_business_value=economics.business_value,
        runtime_seconds=runtime_seconds,
    )


def write_summary(
    *,
    output_dir: Path,
    summaries: list[EpisodeSummary],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "episode_summary.csv"

    with summary_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = DictWriter(
            file,
            fieldnames=list(
                EpisodeSummary.__dataclass_fields__.keys()
            ),
        )
        writer.writeheader()

        for summary in summaries:
            writer.writerow(asdict(summary))

    return summary_path


def print_episode_progress(
    summary: EpisodeSummary,
    total_episodes: int,
) -> None:
    print(
        f"Episode {summary.episode_index:03d}/{total_episodes:03d} "
        f"| Seed: {summary.seed} "
        f"| Rows: {summary.dataset_rows:,} "
        f"| Service: {summary.service_level:.2%} "
        f"| Value: ${summary.net_business_value:,.2f} "
        f"| Runtime: {summary.runtime_seconds:.2f}s"
    )


def print_final_summary(
    *,
    summaries: list[EpisodeSummary],
    summary_path: Path,
    total_runtime_seconds: float,
) -> None:
    total_rows = sum(
        summary.dataset_rows
        for summary in summaries
    )

    average_service_level = sum(
        summary.service_level
        for summary in summaries
    ) / len(summaries)

    average_business_value = sum(
        summary.net_business_value
        for summary in summaries
    ) / len(summaries)

    minimum_business_value = min(
        summary.net_business_value
        for summary in summaries
    )

    maximum_business_value = max(
        summary.net_business_value
        for summary in summaries
    )

    print()
    print("MULTI-EPISODE GENERATION COMPLETE")
    print("=================================")
    print(f"Episodes               : {len(summaries):,}")
    print(f"Total Training Rows    : {total_rows:,}")
    print(f"Average Service Level  : {average_service_level:.2%}")
    print(f"Average Business Value : ${average_business_value:,.2f}")
    print(f"Minimum Business Value : ${minimum_business_value:,.2f}")
    print(f"Maximum Business Value : ${maximum_business_value:,.2f}")
    print(f"Total Runtime          : {total_runtime_seconds:.2f}s")
    print(f"Episode Summary        : {summary_path}")
    print()
    print(
        "Episode boundaries were preserved. "
        "Split train/validation/test by complete seeds only."
    )


def main() -> None:
    episodes, start_seed, output_dir = parse_args()

    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[EpisodeSummary] = []
    started = perf_counter()

    for offset in range(episodes):
        seed = start_seed + offset

        summary = run_episode(
            episode_index=offset + 1,
            seed=seed,
            output_dir=output_dir,
        )

        summaries.append(summary)
        print_episode_progress(
            summary,
            total_episodes=episodes,
        )

    total_runtime_seconds = perf_counter() - started

    summary_path = write_summary(
        output_dir=output_dir,
        summaries=summaries,
    )

    print_final_summary(
        summaries=summaries,
        summary_path=summary_path,
        total_runtime_seconds=total_runtime_seconds,
    )


if __name__ == "__main__":
    main()
