from __future__ import annotations

"""
Analyze the 100-episode training corpus before model training.

Usage:
    python -m simulation.multi_episode_audit

Optional:
    python -m simulation.multi_episode_audit ^
        --data-dir data/training/parallel_multi_episode
"""

from argparse import ArgumentParser
from collections import Counter
from csv import DictReader
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median, pstdev
import math


EXPECTED_EPISODES = 100
EXPECTED_ROWS_PER_EPISODE = 36_500
EXPECTED_TOTAL_ROWS = (
    EXPECTED_EPISODES * EXPECTED_ROWS_PER_EPISODE
)

EXPECTED_ACTIONS = {
    "DO_NOTHING",
    "ORDER_NORMAL",
    "ORDER_EXPEDITE",
    "TRANSFER_STOCK",
}


@dataclass
class RunningStats:
    count: int = 0
    total: float = 0.0
    total_sq: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.total_sq += value * value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    @property
    def average(self) -> float:
        return self.total / self.count if self.count else 0.0

    @property
    def stddev(self) -> float:
        if self.count == 0:
            return 0.0

        variance = (
            self.total_sq / self.count
            - self.average * self.average
        )

        return math.sqrt(max(0.0, variance))


def parse_args():
    parser = ArgumentParser(
        description=(
            "Audit and summarize the multi-episode "
            "training corpus."
        )
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(
            "data/training/parallel_multi_episode"
        ),
    )

    return parser.parse_args()


def read_episode_summary(
    summary_path: Path,
) -> list[dict[str, str]]:
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Episode summary not found: "
            f"{summary_path.resolve()}"
        )

    with summary_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(DictReader(file))


def print_episode_analysis(
    summaries: list[dict[str, str]],
) -> None:
    service_levels = [
        float(row["service_level"])
        for row in summaries
    ]
    business_values = [
        float(row["net_business_value"])
        for row in summaries
    ]
    runtimes = [
        float(row["runtime_seconds"])
        for row in summaries
    ]

    print("EPISODE-LEVEL ANALYSIS")
    print("======================")
    print(f"Episodes                : {len(summaries):,}")
    print(
        f"Average Service Level   : "
        f"{mean(service_levels):.2%}"
    )
    print(
        f"Median Service Level    : "
        f"{median(service_levels):.2%}"
    )
    print(
        f"Service Std Dev         : "
        f"{pstdev(service_levels):.2%}"
    )
    print(
        f"Minimum Service Level   : "
        f"{min(service_levels):.2%}"
    )
    print(
        f"Maximum Service Level   : "
        f"{max(service_levels):.2%}"
    )
    print()
    print(
        f"Average Business Value  : "
        f"${mean(business_values):,.2f}"
    )
    print(
        f"Median Business Value   : "
        f"${median(business_values):,.2f}"
    )
    print(
        f"Business Value Std Dev  : "
        f"${pstdev(business_values):,.2f}"
    )
    print(
        f"Minimum Business Value  : "
        f"${min(business_values):,.2f}"
    )
    print(
        f"Maximum Business Value  : "
        f"${max(business_values):,.2f}"
    )
    print()
    print(
        f"Average Episode Runtime : "
        f"{mean(runtimes):.2f}s"
    )
    print()


def audit_corpus(
    data_dir: Path,
) -> None:
    summary_path = data_dir / "episode_summary.csv"
    summaries = read_episode_summary(summary_path)

    dataset_files = sorted(
        path
        for path in data_dir.glob("*.csv")
        if path.name != "episode_summary.csv"
    )

    print()
    print("MULTI-EPISODE CORPUS AUDIT")
    print("==========================")
    print(f"Directory: {data_dir.resolve()}")
    print()

    print_episode_analysis(summaries)

    action_counts: Counter[str] = Counter()
    reward_stats = RunningStats()
    action_reward_stats = {
        action: RunningStats()
        for action in EXPECTED_ACTIONS
    }

    seed_counts: Counter[str] = Counter()
    file_row_counts: dict[str, int] = {}

    missing_reward_rows = 0
    total_rows = 0

    for index, path in enumerate(
        dataset_files,
        start=1,
    ):
        row_count = 0

        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:
            reader = DictReader(file)

            if reader.fieldnames is None:
                raise RuntimeError(
                    f"Missing header in {path.name}."
                )

            required = {
                "episode_seed",
                "chosen_action",
                "immediate_reward",
            }

            missing = required - set(reader.fieldnames)

            if missing:
                raise RuntimeError(
                    f"{path.name} is missing columns: "
                    + ", ".join(sorted(missing))
                )

            for row in reader:
                row_count += 1
                total_rows += 1

                seed = row["episode_seed"]
                action = row["chosen_action"]
                reward_text = row["immediate_reward"]

                seed_counts[seed] += 1
                action_counts[action] += 1

                if reward_text.strip() == "":
                    missing_reward_rows += 1
                    continue

                reward = float(reward_text)
                reward_stats.add(reward)

                if action not in action_reward_stats:
                    action_reward_stats[action] = RunningStats()

                action_reward_stats[action].add(reward)

        file_row_counts[path.name] = row_count

        if (
            index == 1
            or index % 10 == 0
            or index == len(dataset_files)
        ):
            print(
                f"Processed {index:03d}/"
                f"{len(dataset_files):03d} files "
                f"| Rows: {total_rows:,}"
            )

    print()
    print("CORPUS STRUCTURE")
    print("================")
    print(f"Dataset Files          : {len(dataset_files):,}")
    print(f"Distinct Seeds         : {len(seed_counts):,}")
    print(f"Total Rows             : {total_rows:,}")
    print(
        f"Expected Rows          : "
        f"{EXPECTED_TOTAL_ROWS:,}"
    )
    print(
        f"Missing Reward Rows    : "
        f"{missing_reward_rows:,}"
    )

    invalid_file_counts = {
        name: count
        for name, count in file_row_counts.items()
        if count != EXPECTED_ROWS_PER_EPISODE
    }

    print(
        f"Files With Wrong Size  : "
        f"{len(invalid_file_counts):,}"
    )
    print()

    print("ACTION DISTRIBUTION")
    print("===================")

    for action in sorted(action_counts):
        count = action_counts[action]
        percentage = (
            count / total_rows
            if total_rows
            else 0.0
        )

        print(
            f"{action:<20}: "
            f"{count:>10,} "
            f"({percentage:>6.2%})"
        )

    print()
    print("REWARD DISTRIBUTION")
    print("===================")
    print(
        f"Average Reward         : "
        f"${reward_stats.average:,.2f}"
    )
    print(
        f"Reward Std Dev         : "
        f"${reward_stats.stddev:,.2f}"
    )
    print(
        f"Minimum Reward         : "
        f"${reward_stats.minimum:,.2f}"
    )
    print(
        f"Maximum Reward         : "
        f"${reward_stats.maximum:,.2f}"
    )
    print()

    print("AVERAGE REWARD BY ACTION")
    print("========================")

    for action in sorted(action_reward_stats):
        stats = action_reward_stats[action]

        if stats.count == 0:
            continue

        print(
            f"{action:<20}: "
            f"${stats.average:>12,.2f} "
            f"| n={stats.count:,}"
        )

    print()
    print("AUDIT SUMMARY")
    print("=============")

    failures: list[str] = []

    if len(dataset_files) != EXPECTED_EPISODES:
        failures.append(
            f"Expected {EXPECTED_EPISODES} dataset files, "
            f"found {len(dataset_files)}."
        )

    if len(seed_counts) != EXPECTED_EPISODES:
        failures.append(
            f"Expected {EXPECTED_EPISODES} seeds, "
            f"found {len(seed_counts)}."
        )

    if total_rows != EXPECTED_TOTAL_ROWS:
        failures.append(
            f"Expected {EXPECTED_TOTAL_ROWS:,} rows, "
            f"found {total_rows:,}."
        )

    if invalid_file_counts:
        failures.append(
            f"{len(invalid_file_counts)} files do not contain "
            f"{EXPECTED_ROWS_PER_EPISODE:,} rows."
        )

    if missing_reward_rows:
        failures.append(
            f"{missing_reward_rows:,} rows have no reward."
        )

    missing_actions = EXPECTED_ACTIONS - set(action_counts)

    if missing_actions:
        failures.append(
            "Missing action classes: "
            + ", ".join(sorted(missing_actions))
        )

    if failures:
        print("RESULT: FAILED")

        for failure in failures:
            print(f"- {failure}")

        raise RuntimeError(
            "Multi-episode corpus audit failed."
        )

    print("RESULT: PASSED")
    print(
        "The corpus contains 100 complete independent episodes, "
        "3.65 million labeled decisions, all expected action "
        "classes, and no missing immediate rewards."
    )
    print(
        "The next step can safely split the corpus by complete "
        "episode seeds before training."
    )


def main() -> None:
    args = parse_args()
    audit_corpus(args.data_dir)


if __name__ == "__main__":
    main()
