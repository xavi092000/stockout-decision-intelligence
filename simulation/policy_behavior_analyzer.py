from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from csv import DictReader, DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path
import math

ACTIONS = ("DO_NOTHING", "ORDER_NORMAL", "ORDER_EXPEDITE", "TRANSFER_STOCK")
FEATURES = (
    "current_stock", "available_stock", "pending_normal_units",
    "pending_expedite_units", "forecast_daily_demand",
    "forecast_next_3d", "projected_stock_gap", "temperature_c",
    "promotion_flag", "holiday_flag", "supplier_lead_time_days",
    "neighbor_surplus_units", "action_quantity", "immediate_reward",
)

@dataclass
class Stats:
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

@dataclass(frozen=True)
class ActionProfile:
    action: str
    count: int
    percentage: float
    avg_current_stock: float
    avg_forecast_next_3d: float
    avg_projected_stock_gap: float
    avg_neighbor_surplus_units: float
    avg_pending_normal_units: float
    avg_pending_expedite_units: float
    avg_supplier_lead_time_days: float
    avg_action_quantity: float
    promotion_rate: float
    avg_immediate_reward: float
    positive_reward_rate: float
    negative_reward_rate: float

def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/analysis/policy_behavior"),
    )
    return parser.parse_args()

def episode_files(data_dir: Path) -> list[Path]:
    return sorted(
        p for p in data_dir.glob("*.csv")
        if p.name != "episode_summary.csv"
    )

def resolve_data_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise FileNotFoundError(explicit.resolve())
        return explicit

    candidates = []
    for summary in Path("data/training").rglob("episode_summary.csv"):
        files = episode_files(summary.parent)
        if files:
            candidates.append(
                (summary.stat().st_mtime, summary.parent, len(files))
            )

    if not candidates:
        raise FileNotFoundError(
            "No complete multi-episode corpus found under data/training."
        )

    candidates.sort(reverse=True)
    _, selected, count = candidates[0]
    print(
        f"Auto-selected corpus: {selected.resolve()} "
        f"({count} episode files)\n"
    )
    return selected

def main() -> None:
    args = parse_args()
    data_dir = resolve_data_dir(args.data_dir)
    files = episode_files(data_dir)

    action_stats = {
        action: {feature: Stats() for feature in FEATURES}
        for action in ACTIONS
    }
    action_counts = Counter()
    positive = Counter()
    negative = Counter()
    total_rows = 0

    for index, path in enumerate(files, start=1):
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = DictReader(file)
            required = {"chosen_action", *FEATURES}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise RuntimeError(
                    f"{path.name} missing: {', '.join(sorted(missing))}"
                )

            for row in reader:
                action = row["chosen_action"]
                if action not in action_stats:
                    continue
                total_rows += 1
                action_counts[action] += 1
                for feature in FEATURES:
                    action_stats[action][feature].add(float(row[feature]))
                reward = float(row["immediate_reward"])
                if reward > 0:
                    positive[action] += 1
                elif reward < 0:
                    negative[action] += 1

        if index == 1 or index % 10 == 0 or index == len(files):
            print(
                f"Processed {index:03d}/{len(files):03d} files "
                f"| Rows: {total_rows:,}"
            )

    profiles = []
    for action in ACTIONS:
        count = action_counts[action]
        if not count:
            continue
        stats = action_stats[action]
        profiles.append(
            ActionProfile(
                action=action,
                count=count,
                percentage=count / total_rows,
                avg_current_stock=stats["current_stock"].average,
                avg_forecast_next_3d=stats["forecast_next_3d"].average,
                avg_projected_stock_gap=stats["projected_stock_gap"].average,
                avg_neighbor_surplus_units=stats["neighbor_surplus_units"].average,
                avg_pending_normal_units=stats["pending_normal_units"].average,
                avg_pending_expedite_units=stats["pending_expedite_units"].average,
                avg_supplier_lead_time_days=stats["supplier_lead_time_days"].average,
                avg_action_quantity=stats["action_quantity"].average,
                promotion_rate=stats["promotion_flag"].average,
                avg_immediate_reward=stats["immediate_reward"].average,
                positive_reward_rate=positive[action] / count,
                negative_reward_rate=negative[action] / count,
            )
        )

    print("\nPOLICY BEHAVIOR ANALYSIS")
    print("========================")
    print(f"Corpus: {data_dir.resolve()}")
    for p in profiles:
        print(f"\n{p.action}\n{'-' * len(p.action)}")
        print(f"Count                    : {p.count:,} ({p.percentage:.2%})")
        print(f"Average Current Stock    : {p.avg_current_stock:,.2f}")
        print(f"Average Forecast Next 3d : {p.avg_forecast_next_3d:,.2f}")
        print(f"Average Projected Gap    : {p.avg_projected_stock_gap:,.2f}")
        print(f"Average Neighbor Surplus : {p.avg_neighbor_surplus_units:,.2f}")
        print(f"Average Pending Normal   : {p.avg_pending_normal_units:,.2f}")
        print(f"Average Pending Expedite : {p.avg_pending_expedite_units:,.2f}")
        print(f"Average Lead Time        : {p.avg_supplier_lead_time_days:,.2f}")
        print(f"Average Action Quantity  : {p.avg_action_quantity:,.2f}")
        print(f"Average Immediate Reward : ${p.avg_immediate_reward:,.2f}")
        print(f"Positive Reward Rate     : {p.positive_reward_rate:.2%}")
        print(f"Negative Reward Rate     : {p.negative_reward_rate:.2%}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "action_profiles.csv"
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = DictWriter(
            file,
            fieldnames=list(ActionProfile.__dataclass_fields__.keys()),
        )
        writer.writeheader()
        for profile in profiles:
            writer.writerow(asdict(profile))

    print(f"\nAction profiles exported to: {output}")

if __name__ == "__main__":
    main()
