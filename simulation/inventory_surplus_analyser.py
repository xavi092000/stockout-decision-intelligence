from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from csv import DictReader, DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass(frozen=True)
class StoreTransferProfile:
    store_id: str
    transfers_out: int
    units_out: int
    transfers_in: int
    units_in: int
    net_units: int
    share_of_all_transfer_units_out: float

def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/analysis/inventory_surplus"),
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

def ratio(a: float, b: float) -> float:
    return a / b if b > 0 else 0.0

def main() -> None:
    args = parse_args()
    data_dir = resolve_data_dir(args.data_dir)
    files = episode_files(data_dir)

    count_out = Counter()
    units_out = Counter()
    count_in = Counter()
    units_in = Counter()
    directed = Counter()

    day1_coverage_total = 0.0
    day1_coverage_count = 0
    all_coverage_total = 0.0
    all_coverage_count = 0
    neighbor_forecast_total = 0.0
    neighbor_forecast_count = 0
    neighbor_gap_total = 0.0
    neighbor_gap_count = 0
    reverse_units = 0
    total_rows = 0

    required = {
        "day", "store_id", "sku_id", "current_stock",
        "forecast_next_3d", "projected_stock_gap",
        "neighbor_surplus_units", "chosen_action",
        "action_quantity", "source_store_id",
    }

    for index, path in enumerate(files, start=1):
        episode_flows = Counter()

        with path.open("r", encoding="utf-8", newline="") as file:
            reader = DictReader(file)
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise RuntimeError(
                    f"{path.name} missing: {', '.join(sorted(missing))}"
                )

            for row in reader:
                total_rows += 1
                day = int(row["day"])
                store = row["store_id"]
                sku = row["sku_id"]
                stock = float(row["current_stock"])
                forecast = float(row["forecast_next_3d"])
                gap = float(row["projected_stock_gap"])
                neighbor = float(row["neighbor_surplus_units"])

                coverage = ratio(stock, forecast)
                all_coverage_total += coverage
                all_coverage_count += 1
                if day == 1:
                    day1_coverage_total += coverage
                    day1_coverage_count += 1

                if row["chosen_action"] != "TRANSFER_STOCK":
                    continue

                source = row["source_store_id"].strip()
                quantity = int(float(row["action_quantity"]))

                count_out[source] += 1
                units_out[source] += quantity
                count_in[store] += 1
                units_in[store] += quantity

                neighbor_forecast_total += ratio(neighbor, forecast)
                neighbor_forecast_count += 1
                neighbor_gap_total += ratio(neighbor, max(gap, 1.0))
                neighbor_gap_count += 1

                key = (source, store, sku)
                episode_flows[key] += quantity
                directed[key] += quantity

        seen = set()
        for (source, destination, sku), units in episode_flows.items():
            normalized = (
                min(source, destination),
                max(source, destination),
                sku,
            )
            if normalized in seen:
                continue
            reverse_units += min(
                units,
                episode_flows.get((destination, source, sku), 0),
            )
            seen.add(normalized)

        if index == 1 or index % 10 == 0 or index == len(files):
            print(
                f"Processed {index:03d}/{len(files):03d} files "
                f"| Rows: {total_rows:,}"
            )

    stores = sorted(
        set(count_out) | set(units_out) | set(count_in) | set(units_in)
    )
    total_transfer_units = sum(units_out.values())

    profiles = [
        StoreTransferProfile(
            store_id=store,
            transfers_out=count_out[store],
            units_out=units_out[store],
            transfers_in=count_in[store],
            units_in=units_in[store],
            net_units=units_in[store] - units_out[store],
            share_of_all_transfer_units_out=ratio(
                units_out[store],
                total_transfer_units,
            ),
        )
        for store in stores
    ]
    profiles.sort(key=lambda p: p.units_out, reverse=True)

    print("\nINVENTORY SURPLUS AND TRANSFER ANALYSIS")
    print("=======================================")
    print(f"Corpus directory             : {data_dir.resolve()}")
    print(f"Episode files                : {len(files)}")
    print(f"Rows analyzed                : {total_rows:,}")
    print(
        f"Average day-1 stock coverage : "
        f"{ratio(day1_coverage_total, day1_coverage_count):.2f}x"
    )
    print(
        f"Average all-day coverage     : "
        f"{ratio(all_coverage_total, all_coverage_count):.2f}x"
    )
    print(
        f"Neighbor surplus / forecast  : "
        f"{ratio(neighbor_forecast_total, neighbor_forecast_count):.2f}x"
    )
    print(
        f"Neighbor surplus / gap       : "
        f"{ratio(neighbor_gap_total, neighbor_gap_count):.2f}x"
    )
    print(f"Total transferred units      : {total_transfer_units:,}")
    print(f"Estimated reverse-flow units : {reverse_units:,}")
    print(
        f"Reverse-flow rate            : "
        f"{ratio(reverse_units, total_transfer_units):.2%}"
    )

    print("\nSTORE TRANSFER PROFILES")
    print("=======================")
    for p in profiles:
        direction = "NET RECEIVER" if p.net_units > 0 else "NET DONOR"
        print(
            f"{p.store_id:<12} "
            f"| Out: {p.units_out:>10,} "
            f"| In: {p.units_in:>10,} "
            f"| Net: {p.net_units:>11,} "
            f"| Share Out: {p.share_of_all_transfer_units_out:>6.2%} "
            f"| {direction}"
        )

    print("\nTOP TRANSFER CORRIDORS")
    print("======================")
    for (source, destination, sku), units in directed.most_common(15):
        print(
            f"{source} -> {destination} "
            f"| SKU: {sku} | Units: {units:,}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "store_transfer_profiles.csv"
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = DictWriter(
            file,
            fieldnames=list(
                StoreTransferProfile.__dataclass_fields__.keys()
            ),
        )
        writer.writeheader()
        for profile in profiles:
            writer.writerow(asdict(profile))

    print(f"\nStore profiles exported to: {output}")

if __name__ == "__main__":
    main()
