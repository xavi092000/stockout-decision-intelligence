from __future__ import annotations

"""
Parallel multi-episode generator.

Important:
- Days remain strictly sequential inside every 365-day episode.
- Only independent episodes/seeds run in parallel.
- Designed for Windows with ProcessPoolExecutor.

Examples:
    python -m simulation.parallel_multi_episode_runner --episodes 10 --workers 4
    python -m simulation.parallel_multi_episode_runner --episodes 100 --workers 6
"""

from argparse import ArgumentParser
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed,
)
from csv import DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
import os

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


def run_episode_worker(
    episode_index: int,
    seed: int,
    output_dir_text: str,
) -> EpisodeSummary:
    """
    Execute one complete episode in one worker process.

    The 365 days inside this function remain strictly sequential.
    """
    output_dir = Path(output_dir_text)

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

    if engine.last_dataset_path is None:
        raise RuntimeError(
            f"Seed {seed} completed without exporting a dataset."
        )

    expected_rows = (
        config.number_of_days
        * config.number_of_products
        * config.number_of_stores
    )
    actual_rows = engine.dataset_builder.row_count

    if actual_rows != expected_rows:
        raise RuntimeError(
            f"Seed {seed} produced {actual_rows:,} rows; "
            f"expected {expected_rows:,}."
        )

    state = engine._require_state()
    economics = engine.cumulative_economics

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


def parse_args():
    cpu_count = os.cpu_count() or 2
    recommended_workers = max(1, min(6, cpu_count - 1))

    parser = ArgumentParser(
        description=(
            "Generate independent 365-day episodes in parallel "
            "while keeping each episode internally sequential."
        )
    )

    parser.add_argument(
        "--episodes",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--start-seed",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=recommended_workers,
        help=(
            "Parallel episode processes. Default is a conservative "
            f"{recommended_workers} for this machine."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/training/parallel_multi_episode"
        ),
    )

    args = parser.parse_args()

    if args.episodes <= 0:
        parser.error("--episodes must be greater than zero.")

    if args.start_seed < 0:
        parser.error("--start-seed cannot be negative.")

    if args.workers <= 0:
        parser.error("--workers must be greater than zero.")

    return args


def write_summary(
    output_dir: Path,
    summaries: list[EpisodeSummary],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / "episode_summary.csv"

    with path.open(
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

        for summary in sorted(
            summaries,
            key=lambda item: item.episode_index,
        ):
            writer.writerow(asdict(summary))

    return path


def print_result(
    summary: EpisodeSummary,
    completed: int,
    total: int,
) -> None:
    print(
        f"Completed {completed:03d}/{total:03d} "
        f"| Episode: {summary.episode_index:03d} "
        f"| Seed: {summary.seed} "
        f"| Rows: {summary.dataset_rows:,} "
        f"| Service: {summary.service_level:.2%} "
        f"| Value: ${summary.net_business_value:,.2f} "
        f"| Worker runtime: {summary.runtime_seconds:.2f}s",
        flush=True,
    )


def print_final_summary(
    summaries: list[EpisodeSummary],
    summary_path: Path,
    total_runtime_seconds: float,
    workers: int,
) -> None:
    total_rows = sum(
        item.dataset_rows
        for item in summaries
    )
    average_service = sum(
        item.service_level
        for item in summaries
    ) / len(summaries)
    average_value = sum(
        item.net_business_value
        for item in summaries
    ) / len(summaries)

    print()
    print("PARALLEL MULTI-EPISODE GENERATION COMPLETE")
    print("==========================================")
    print(f"Episodes               : {len(summaries):,}")
    print(f"Parallel Workers       : {workers}")
    print(f"Total Training Rows    : {total_rows:,}")
    print(f"Average Service Level  : {average_service:.2%}")
    print(f"Average Business Value : ${average_value:,.2f}")
    print(f"Wall-Clock Runtime     : {total_runtime_seconds:.2f}s")
    print(f"Episode Summary        : {summary_path}")
    print()
    print(
        "Every episode remained sequential from day 1 to day 365. "
        "Only independent seeds were executed in parallel."
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    tasks = [
        (
            offset + 1,
            args.start_seed + offset,
            str(args.output_dir),
        )
        for offset in range(args.episodes)
    ]

    summaries: list[EpisodeSummary] = []
    started = perf_counter()

    print(
        f"Launching {args.episodes} independent episodes "
        f"with {args.workers} parallel workers.",
        flush=True,
    )
    print(
        "Each worker still runs its 365 days sequentially.",
        flush=True,
    )
    print()

    with ProcessPoolExecutor(
        max_workers=args.workers,
    ) as executor:
        future_to_seed = {
            executor.submit(
                run_episode_worker,
                episode_index,
                seed,
                output_dir,
            ): seed
            for episode_index, seed, output_dir in tasks
        }

        for completed, future in enumerate(
            as_completed(future_to_seed),
            start=1,
        ):
            seed = future_to_seed[future]

            try:
                summary = future.result()
            except Exception as exc:
                raise RuntimeError(
                    f"Parallel episode failed for seed {seed}."
                ) from exc

            summaries.append(summary)
            print_result(
                summary=summary,
                completed=completed,
                total=args.episodes,
            )

    total_runtime_seconds = perf_counter() - started

    summary_path = write_summary(
        output_dir=args.output_dir,
        summaries=summaries,
    )

    print_final_summary(
        summaries=summaries,
        summary_path=summary_path,
        total_runtime_seconds=total_runtime_seconds,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
