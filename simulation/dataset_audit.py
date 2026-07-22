from __future__ import annotations

"""
Dataset quality, leakage, and reward-reconciliation audit.

Usage:
    python -m simulation.dataset_audit
"""

from collections import Counter, defaultdict
from pathlib import Path
import csv
import math
import sys

from simulation.dataset_builder import (
    FEATURE_COLUMNS,
    FORBIDDEN_FEATURE_COLUMNS,
)


DEFAULT_DATASET_PATH = Path(
    "data/training/"
    "stockout_decision_simulator_seed_42_rulebased.csv"
)

EXPECTED_ACTIONS = {
    "DO_NOTHING",
    "ORDER_NORMAL",
    "ORDER_EXPEDITE",
    "TRANSFER_STOCK",
}

KEY_COLUMNS = (
    "episode_seed",
    "day",
    "store_id",
    "sku_id",
)

REWARD_COLUMNS = {
    "local_revenue",
    "normal_order_cost",
    "expedite_order_cost",
    "transfer_cost",
    "holding_cost",
    "lost_sales_cost",
    "stockout_penalty",
    "immediate_reward",
}

REQUIRED_COLUMNS = {
    "simulation_id",
    "episode_seed",
    "day",
    "date",
    "store_id",
    "sku_id",
    *FEATURE_COLUMNS,
    "chosen_action",
    "action_quantity",
    "source_store_id",
    "actual_demand",
    "fulfilled_units",
    "unmet_units",
    "ending_stock",
    "stockout_occurred",
    *REWARD_COLUMNS,
}


class AuditFailure(RuntimeError):
    pass


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path.resolve()}"
        )

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise AuditFailure("Dataset has no header.")

        return list(reader), list(reader.fieldnames)


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def parse_float(
    value: str,
    column: str,
    row_number: int,
) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise AuditFailure(
            f"Invalid numeric value in column '{column}' "
            f"at CSV row {row_number}: {value!r}"
        ) from exc

    if not math.isfinite(result):
        raise AuditFailure(
            f"Non-finite numeric value in column '{column}' "
            f"at CSV row {row_number}: {value!r}"
        )

    return result


def print_check(
    name: str,
    passed: bool,
    detail: str,
) -> None:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {detail}")


def audit(path: Path) -> None:
    rows, columns = load_rows(path)

    print()
    print("STOCKOUT DATASET AUDIT")
    print("======================")
    print(f"Dataset: {path.resolve()}")
    print()

    failures: list[str] = []

    expected_rows = 365 * 100
    row_count_ok = len(rows) == expected_rows
    print_check(
        "Row count",
        row_count_ok,
        f"{len(rows):,} rows; expected {expected_rows:,}",
    )
    if not row_count_ok:
        failures.append("Unexpected row count.")

    missing_columns = sorted(
        REQUIRED_COLUMNS - set(columns)
    )
    required_ok = not missing_columns
    print_check(
        "Required columns",
        required_ok,
        (
            "all required columns are present"
            if required_ok
            else "missing: " + ", ".join(missing_columns)
        ),
    )
    if not required_ok:
        failures.append("Missing required columns.")

    forbidden_in_features = sorted(
        set(FEATURE_COLUMNS) & FORBIDDEN_FEATURE_COLUMNS
    )
    leakage_schema_ok = not forbidden_in_features
    print_check(
        "Feature leakage schema",
        leakage_schema_ok,
        (
            "no forbidden future column is listed as a feature"
            if leakage_schema_ok
            else "forbidden features: "
            + ", ".join(forbidden_in_features)
        ),
    )
    if not leakage_schema_ok:
        failures.append("Leakage detected in feature schema.")

    nullable_columns = {"source_store_id"}
    missing_counts: Counter[str] = Counter()

    for row in rows:
        for column in REQUIRED_COLUMNS - nullable_columns:
            if is_blank(row.get(column)):
                missing_counts[column] += 1

    missing_ok = not missing_counts
    print_check(
        "Missing values",
        missing_ok,
        (
            "no unexpected missing values"
            if missing_ok
            else ", ".join(
                f"{column}={count:,}"
                for column, count
                in sorted(missing_counts.items())
            )
        ),
    )
    if not missing_ok:
        failures.append("Unexpected missing values.")

    seen_keys: set[tuple[str, str, str, str]] = set()
    duplicate_count = 0

    for row in rows:
        key = tuple(row[column] for column in KEY_COLUMNS)

        if key in seen_keys:
            duplicate_count += 1
        else:
            seen_keys.add(key)

    unique_ok = duplicate_count == 0
    print_check(
        "Unique decision key",
        unique_ok,
        (
            "every episode/day/store/SKU combination is unique"
            if unique_ok
            else f"{duplicate_count:,} duplicate keys"
        ),
    )
    if not unique_ok:
        failures.append("Duplicate decision keys.")

    action_counts = Counter(
        row["chosen_action"]
        for row in rows
        if not is_blank(row.get("chosen_action"))
    )
    present_actions = set(action_counts)
    missing_actions = sorted(
        EXPECTED_ACTIONS - present_actions
    )
    unknown_actions = sorted(
        present_actions - EXPECTED_ACTIONS
    )

    actions_ok = not missing_actions and not unknown_actions
    print_check(
        "Action classes",
        actions_ok,
        (
            ", ".join(
                f"{action}={action_counts[action]:,}"
                for action in sorted(action_counts)
            )
            if actions_ok
            else (
                f"missing={missing_actions or 'none'}, "
                f"unknown={unknown_actions or 'none'}"
            )
        ),
    )
    if not actions_ok:
        failures.append("Unexpected action classes.")

    action_semantic_errors = 0

    for row_number, row in enumerate(rows, start=2):
        action = row["chosen_action"]
        quantity = int(
            parse_float(
                row["action_quantity"],
                "action_quantity",
                row_number,
            )
        )
        source = row.get("source_store_id", "").strip()

        if action == "DO_NOTHING":
            if quantity != 0 or source:
                action_semantic_errors += 1
        elif action == "TRANSFER_STOCK":
            if quantity <= 0 or not source:
                action_semantic_errors += 1
        elif action in {
            "ORDER_NORMAL",
            "ORDER_EXPEDITE",
        }:
            if quantity <= 0 or source:
                action_semantic_errors += 1

    action_semantics_ok = action_semantic_errors == 0
    print_check(
        "Action semantics",
        action_semantics_ok,
        (
            "action quantities and source-store rules are valid"
            if action_semantics_ok
            else f"{action_semantic_errors:,} invalid rows"
        ),
    )
    if not action_semantics_ok:
        failures.append("Invalid action semantics.")

    demand_accounting_errors = 0

    for row_number, row in enumerate(rows, start=2):
        actual = int(
            parse_float(
                row["actual_demand"],
                "actual_demand",
                row_number,
            )
        )
        fulfilled = int(
            parse_float(
                row["fulfilled_units"],
                "fulfilled_units",
                row_number,
            )
        )
        unmet = int(
            parse_float(
                row["unmet_units"],
                "unmet_units",
                row_number,
            )
        )

        if actual != fulfilled + unmet:
            demand_accounting_errors += 1

    accounting_ok = demand_accounting_errors == 0
    print_check(
        "Demand accounting",
        accounting_ok,
        (
            "actual demand equals fulfilled plus unmet demand"
            if accounting_ok
            else f"{demand_accounting_errors:,} inconsistent rows"
        ),
    )
    if not accounting_ok:
        failures.append(
            "Demand accounting inconsistencies."
        )

    stockout_errors = 0

    for row_number, row in enumerate(rows, start=2):
        unmet = int(
            parse_float(
                row["unmet_units"],
                "unmet_units",
                row_number,
            )
        )
        flag = int(
            parse_float(
                row["stockout_occurred"],
                "stockout_occurred",
                row_number,
            )
        )

        if flag not in {0, 1} or flag != int(unmet > 0):
            stockout_errors += 1

    stockout_ok = stockout_errors == 0
    print_check(
        "Stockout label",
        stockout_ok,
        (
            "stockout flag matches unmet demand"
            if stockout_ok
            else f"{stockout_errors:,} inconsistent rows"
        ),
    )
    if not stockout_ok:
        failures.append(
            "Stockout label inconsistencies."
        )

    reward_formula_errors = 0
    day_reward_totals: defaultdict[int, float] = defaultdict(float)

    for row_number, row in enumerate(rows, start=2):
        local_revenue = parse_float(
            row["local_revenue"],
            "local_revenue",
            row_number,
        )
        costs = sum(
            parse_float(
                row[column],
                column,
                row_number,
            )
            for column in (
                "normal_order_cost",
                "expedite_order_cost",
                "transfer_cost",
                "holding_cost",
                "lost_sales_cost",
                "stockout_penalty",
            )
        )
        immediate_reward = parse_float(
            row["immediate_reward"],
            "immediate_reward",
            row_number,
        )
        expected_reward = local_revenue - costs

        if abs(immediate_reward - expected_reward) > 1e-6:
            reward_formula_errors += 1

        day_reward_totals[int(row["day"])] += (
            immediate_reward
        )

    reward_formula_ok = reward_formula_errors == 0
    print_check(
        "Decision reward formula",
        reward_formula_ok,
        (
            "immediate reward equals local revenue minus local costs"
            if reward_formula_ok
            else f"{reward_formula_errors:,} inconsistent rows"
        ),
    )
    if not reward_formula_ok:
        failures.append(
            "Decision reward formula inconsistencies."
        )

    distinct_reward_values = len(
        {
            row["immediate_reward"]
            for row in rows
        }
    )
    granularity_ok = distinct_reward_values > 365
    print_check(
        "Reward granularity",
        granularity_ok,
        (
            f"{distinct_reward_values:,} distinct decision rewards; "
            "rewards are not merely repeated once per day"
            if granularity_ok
            else (
                f"only {distinct_reward_values:,} distinct rewards; "
                "possible daily-value repetition"
            )
        ),
    )
    if not granularity_ok:
        failures.append(
            "Reward granularity is too coarse."
        )

    daily_reward_coverage_ok = (
        len(day_reward_totals) == 365
        and min(day_reward_totals) == 1
        and max(day_reward_totals) == 365
    )
    print_check(
        "Daily reward coverage",
        daily_reward_coverage_ok,
        (
            "decision rewards aggregate for every day from 1 to 365"
            if daily_reward_coverage_ok
            else (
                f"{len(day_reward_totals):,} days found"
            )
        ),
    )
    if not daily_reward_coverage_ok:
        failures.append(
            "Unexpected daily reward coverage."
        )

    nonnegative_columns = (
        "current_stock",
        "available_stock",
        "pending_normal_units",
        "pending_expedite_units",
        "forecast_daily_demand",
        "forecast_next_3d",
        "supplier_lead_time_days",
        "neighbor_surplus_units",
        "local_revenue",
        "normal_order_cost",
        "expedite_order_cost",
        "transfer_cost",
        "holding_cost",
        "lost_sales_cost",
        "stockout_penalty",
    )

    negative_errors = 0

    for row_number, row in enumerate(rows, start=2):
        for column in nonnegative_columns:
            value = parse_float(
                row[column],
                column,
                row_number,
            )
            if value < 0:
                negative_errors += 1

    nonnegative_ok = negative_errors == 0
    print_check(
        "Observable and economic ranges",
        nonnegative_ok,
        (
            "nonnegative operational and cost fields are valid"
            if nonnegative_ok
            else f"{negative_errors:,} negative values"
        ),
    )
    if not nonnegative_ok:
        failures.append(
            "Invalid operational or economic ranges."
        )

    seeds = sorted(
        {row["episode_seed"] for row in rows}
    )
    days = sorted(
        int(row["day"]) for row in rows
    )

    coverage_ok = (
        len(seeds) == 1
        and min(days) == 1
        and max(days) == 365
        and len(set(days)) == 365
    )

    print_check(
        "Episode coverage",
        coverage_ok,
        (
            f"seed={seeds[0]}, days=1..365"
            if coverage_ok
            else (
                f"seeds={seeds}, "
                f"day_min={min(days) if days else 'n/a'}, "
                f"day_max={max(days) if days else 'n/a'}"
            )
        ),
    )
    if not coverage_ok:
        failures.append(
            "Unexpected episode coverage."
        )

    print()
    print("AUDIT SUMMARY")
    print("=============")

    if failures:
        for failure in failures:
            print(f"- {failure}")

        print()
        print("RESULT: FAILED")
        raise AuditFailure(
            f"Dataset audit failed with "
            f"{len(failures)} issue(s)."
        )

    print("RESULT: PASSED")
    print(
        "The dataset is structurally valid, decision rewards "
        "reconcile at row level, and approved features contain "
        "no post-decision outcome columns."
    )
    print(
        "Important: train/validation/test splitting must still "
        "be performed by complete episode seeds, never by "
        "random rows."
    )


def main() -> None:
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else DEFAULT_DATASET_PATH
    )

    audit(path)


if __name__ == "__main__":
    main()
