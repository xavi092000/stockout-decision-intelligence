from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from simulation.application.adaptive_runner_v2 import AdaptiveSimulationRunnerV2
from simulation.ml.feature_builder_v2 import FeatureBuilderV2
from simulation.ml.training_dataset_builder_v2 import TrainingDatasetBuilderV2


class MultiEpisodeV2Error(RuntimeError):
    """Raised when the multi-episode V2 pipeline cannot complete safely."""


@dataclass(frozen=True)
class EpisodeResult:
    episode_index: int
    episode_id: str
    seed: int
    split: str
    rows_created: int
    snapshots_created: int
    fill_rate: float
    realized_revenue: float
    operating_profit: float
    output_dir: str
    runtime_seconds: float


@dataclass(frozen=True)
class SplitPlan:
    train_episode_ids: tuple[str, ...]
    validation_episode_ids: tuple[str, ...]
    test_episode_ids: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run independent V2 adaptive-policy episodes, build one merged "
            "training dataset, and split it by complete episodes."
        )
    )
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument(
        "--world",
        type=Path,
        default=Path("simulation/output/core/world_state_v2_day_000.json"),
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path(
            "simulation/output/scenarios/synthetic_scenarios_summary.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation/output/multi_episode_v2"),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete the target output directory before running.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.episodes < 3:
        raise MultiEpisodeV2Error(
            "At least 3 episodes are required for train/validation/test."
        )
    if args.days <= 0:
        raise MultiEpisodeV2Error("--days must be positive.")
    if args.start_seed < 0:
        raise MultiEpisodeV2Error("--start-seed cannot be negative.")
    if not 0.0 < args.train_ratio < 1.0:
        raise MultiEpisodeV2Error("--train-ratio must be between 0 and 1.")
    if not 0.0 < args.validation_ratio < 1.0:
        raise MultiEpisodeV2Error(
            "--validation-ratio must be between 0 and 1."
        )
    if args.train_ratio + args.validation_ratio >= 1.0:
        raise MultiEpisodeV2Error(
            "train-ratio + validation-ratio must be less than 1."
        )
    if not args.world.is_file():
        raise MultiEpisodeV2Error(f"World file not found: {args.world}")
    if not args.scenarios.is_file():
        raise MultiEpisodeV2Error(f"Scenario file not found: {args.scenarios}")


def allocate_split_plan(
    episode_ids: list[str],
    train_ratio: float,
    validation_ratio: float,
) -> SplitPlan:
    total = len(episode_ids)
    train_count = max(1, int(total * train_ratio))
    validation_count = max(1, int(total * validation_ratio))

    if train_count + validation_count >= total:
        validation_count = 1
        train_count = total - 2

    return SplitPlan(
        train_episode_ids=tuple(episode_ids[:train_count]),
        validation_episode_ids=tuple(
            episode_ids[train_count : train_count + validation_count]
        ),
        test_episode_ids=tuple(
            episode_ids[train_count + validation_count :]
        ),
    )


def split_name(episode_id: str, plan: SplitPlan) -> str:
    if episode_id in plan.train_episode_ids:
        return "train"
    if episode_id in plan.validation_episode_ids:
        return "validation"
    if episode_id in plan.test_episode_ids:
        return "test"
    raise MultiEpisodeV2Error(f"Episode missing from split plan: {episode_id}")


def read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise MultiEpisodeV2Error(f"Unsupported file format: {path}")


def write_frame(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
        return path
    except (ImportError, ModuleNotFoundError, ValueError):
        fallback = path.with_suffix(".csv")
        frame.to_csv(fallback, index=False)
        return fallback


def build_episode(
    *,
    episode_index: int,
    seed: int,
    split: str,
    days: int,
    world_path: Path,
    scenario_path: Path,
    episodes_dir: Path,
) -> tuple[EpisodeResult, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    episode_id = f"episode-seed-{seed}"
    output_dir = episodes_dir / f"episode_{episode_index:04d}_seed_{seed}"
    started = perf_counter()

    result = AdaptiveSimulationRunnerV2(
        world_path=world_path,
        scenario_path=scenario_path,
        output_dir=output_dir,
        seed=seed,
    ).run(days=days)

    training_result = TrainingDatasetBuilderV2(
        output_dir=output_dir
    ).build()
    feature_result = FeatureBuilderV2(
        output_dir=output_dir
    ).build()

    training_path = Path(training_result.output_path)
    if not training_path.is_file() and training_result.csv_fallback_path:
        training_path = Path(training_result.csv_fallback_path)

    dataset = read_frame(training_path)
    features = read_frame(Path(feature_result.feature_output_path))
    labels = read_frame(Path(feature_result.label_output_path))

    for frame_name, frame in (
        ("training dataset", dataset),
        ("feature matrix", features),
        ("label matrix", labels),
    ):
        if len(frame) != days:
            raise MultiEpisodeV2Error(
                f"{episode_id} {frame_name} has {len(frame)} rows; "
                f"expected {days}."
            )

    # The snapshot builder already derives this identifier from the seed.
    actual_episode_ids = set(dataset["state_episode_id"].astype(str))
    if actual_episode_ids != {episode_id}:
        raise MultiEpisodeV2Error(
            f"Unexpected episode IDs for seed {seed}: {actual_episode_ids}"
        )

    dataset.insert(0, "dataset_split", split)
    features.insert(1, "dataset_split", split)
    labels.insert(0, "dataset_split", split)

    summary = EpisodeResult(
        episode_index=episode_index,
        episode_id=episode_id,
        seed=seed,
        split=split,
        rows_created=len(dataset),
        snapshots_created=int(result["snapshots_created"]),
        fill_rate=float(result["overall_fill_rate"]),
        realized_revenue=float(result["realized_revenue"]),
        operating_profit=float(result["calibrated_net_operating_profit"]),
        output_dir=str(output_dir.resolve()),
        runtime_seconds=round(perf_counter() - started, 3),
    )
    return summary, dataset, features, labels


def validate_merged(
    dataset: pd.DataFrame,
    features: pd.DataFrame,
    labels: pd.DataFrame,
    expected_rows: int,
    plan: SplitPlan,
) -> None:
    if len(dataset) != expected_rows:
        raise MultiEpisodeV2Error(
            f"Merged dataset has {len(dataset)} rows; expected {expected_rows}."
        )
    if len(features) != expected_rows or len(labels) != expected_rows:
        raise MultiEpisodeV2Error(
            "Merged features/labels row counts do not match the dataset."
        )
    if dataset["state_snapshot_id"].duplicated().any():
        raise MultiEpisodeV2Error("Duplicate snapshot IDs in merged dataset.")

    episode_to_split = (
        dataset[["state_episode_id", "dataset_split"]]
        .drop_duplicates()
        .groupby("state_episode_id")["dataset_split"]
        .nunique()
    )
    if (episode_to_split != 1).any():
        raise MultiEpisodeV2Error(
            "At least one episode appears in multiple dataset splits."
        )

    expected = {
        "train": set(plan.train_episode_ids),
        "validation": set(plan.validation_episode_ids),
        "test": set(plan.test_episode_ids),
    }
    for name, ids in expected.items():
        actual = set(
            dataset.loc[
                dataset["dataset_split"] == name,
                "state_episode_id",
            ].astype(str)
        )
        if actual != ids:
            raise MultiEpisodeV2Error(
                f"Split {name!r} episode mismatch: expected {ids}, got {actual}."
            )


def main() -> int:
    args = build_parser().parse_args()

    try:
        validate_args(args)

        if args.output_dir.exists() and args.overwrite:
            shutil.rmtree(args.output_dir)
        args.output_dir.mkdir(parents=True, exist_ok=True)

        episode_ids = [
            f"episode-seed-{args.start_seed + offset}"
            for offset in range(args.episodes)
        ]
        plan = allocate_split_plan(
            episode_ids,
            args.train_ratio,
            args.validation_ratio,
        )

        all_datasets: list[pd.DataFrame] = []
        all_features: list[pd.DataFrame] = []
        all_labels: list[pd.DataFrame] = []
        episode_results: list[EpisodeResult] = []
        started = perf_counter()

        for offset in range(args.episodes):
            seed = args.start_seed + offset
            episode_id = f"episode-seed-{seed}"
            split = split_name(episode_id, plan)
            summary, dataset, features, labels = build_episode(
                episode_index=offset + 1,
                seed=seed,
                split=split,
                days=args.days,
                world_path=args.world,
                scenario_path=args.scenarios,
                episodes_dir=args.output_dir / "episodes",
            )
            episode_results.append(summary)
            all_datasets.append(dataset)
            all_features.append(features)
            all_labels.append(labels)
            print(
                f"Episode {offset + 1:03d}/{args.episodes:03d} "
                f"| Seed {seed} | Split {split:<10} "
                f"| Rows {len(dataset):,} | Fill {summary.fill_rate:.2%} "
                f"| Profit ${summary.operating_profit:,.2f} "
                f"| {summary.runtime_seconds:.2f}s",
                flush=True,
            )

        merged_dataset = pd.concat(all_datasets, ignore_index=True)
        merged_features = pd.concat(all_features, ignore_index=True).fillna(0)
        merged_labels = pd.concat(all_labels, ignore_index=True)

        expected_rows = args.episodes * args.days
        validate_merged(
            merged_dataset,
            merged_features,
            merged_labels,
            expected_rows,
            plan,
        )

        merged_dir = args.output_dir / "merged"
        split_dir = args.output_dir / "splits"

        merged_dataset_path = write_frame(
            merged_dataset,
            merged_dir / "training_dataset_multi_episode_v2.parquet",
        )
        merged_features_path = write_frame(
            merged_features,
            merged_dir / "model_features_multi_episode_v2.parquet",
        )
        merged_labels_path = write_frame(
            merged_labels,
            merged_dir / "model_labels_multi_episode_v2.parquet",
        )

        split_paths: dict[str, dict[str, str]] = {}
        for split in ("train", "validation", "test"):
            dataset_split = merged_dataset.loc[
                merged_dataset["dataset_split"] == split
            ].reset_index(drop=True)
            features_split = merged_features.loc[
                merged_features["dataset_split"] == split
            ].reset_index(drop=True)
            labels_split = merged_labels.loc[
                merged_labels["dataset_split"] == split
            ].reset_index(drop=True)

            split_paths[split] = {
                "dataset": str(
                    write_frame(
                        dataset_split,
                        split_dir / f"{split}_dataset_v2.parquet",
                    ).resolve()
                ),
                "features": str(
                    write_frame(
                        features_split,
                        split_dir / f"{split}_features_v2.parquet",
                    ).resolve()
                ),
                "labels": str(
                    write_frame(
                        labels_split,
                        split_dir / f"{split}_labels_v2.parquet",
                    ).resolve()
                ),
                "rows": len(dataset_split),
                "episodes": int(dataset_split["state_episode_id"].nunique()),
            }

        episode_summary = pd.DataFrame(
            [asdict(item) for item in episode_results]
        )
        episode_summary_path = args.output_dir / "episode_summary_v2.csv"
        episode_summary.to_csv(episode_summary_path, index=False)

        manifest: dict[str, Any] = {
            "status": "PASSED",
            "schema_version": "2.0.0",
            "episodes": args.episodes,
            "days_per_episode": args.days,
            "total_rows": expected_rows,
            "start_seed": args.start_seed,
            "split_strategy": "complete_episode_boundaries",
            "train_episode_ids": list(plan.train_episode_ids),
            "validation_episode_ids": list(plan.validation_episode_ids),
            "test_episode_ids": list(plan.test_episode_ids),
            "merged_dataset_path": str(merged_dataset_path.resolve()),
            "merged_features_path": str(merged_features_path.resolve()),
            "merged_labels_path": str(merged_labels_path.resolve()),
            "episode_summary_path": str(episode_summary_path.resolve()),
            "splits": split_paths,
            "leakage_guard": "No episode is shared across train, validation and test.",
            "runtime_seconds": round(perf_counter() - started, 3),
        }
        manifest_path = args.output_dir / "multi_episode_manifest_v2.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n" + "=" * 72)
        print("MULTI-EPISODE V2 PIPELINE")
        print("=" * 72)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        print("=" * 72)
        print("STATUS: PASSED")
        return 0

    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
