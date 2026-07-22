from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


class TrainingDatasetBuilderV2Error(RuntimeError):
    """Raised when the V2 training dataset cannot be built safely."""


@dataclass(frozen=True)
class TrainingDatasetBuildResult:
    rows_created: int
    terminal_rows: int
    output_path: str
    csv_fallback_path: str | None
    leakage_checks_passed: bool
    schema_version: str = "2.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_created": self.rows_created,
            "terminal_rows": self.terminal_rows,
            "output_path": self.output_path,
            "csv_fallback_path": self.csv_fallback_path,
            "leakage_checks_passed": self.leakage_checks_passed,
            "schema_version": self.schema_version,
        }


class TrainingDatasetBuilderV2:
    """
    Builds one transition row per simulated day:

        state S + action A + reward R + next state S'

    Sources:
      - pre_decision_snapshots_v2.jsonl
      - decision_history_v2.csv
      - adaptive_daily_kpis_v2.csv

    The final day is retained as a terminal transition with next-state fields
    set to null and is_terminal=True.
    """

    REQUIRED_DECISION_COLUMNS = {
        "simulation_day",
        "selected_policy",
    }

    REQUIRED_KPI_COLUMNS = {
        "simulation_day",
        "requested_units",
        "sold_units",
        "lost_units",
        "fill_rate",
        "orders_created",
        "receipts_created",
        "ending_on_hand_units",
        "ending_in_transit_units",
        "cumulative_revenue",
        "calibrated_net_operating_profit",
    }

    FORBIDDEN_STATE_TOKENS = (
        "sold_units",
        "lost_units",
        "realized_revenue",
        "revenue_after",
        "fill_rate_after",
        "ending_on_hand",
        "ending_in_transit",
        "stock_after_sales",
        "future_",
    )

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def build(
        self,
        *,
        snapshots_path: str | Path | None = None,
        decisions_path: str | Path | None = None,
        daily_kpis_path: str | Path | None = None,
        output_path: str | Path | None = None,
    ) -> TrainingDatasetBuildResult:
        snapshots_path = Path(
            snapshots_path
            or self.output_dir / "pre_decision_snapshots_v2.jsonl"
        )
        decisions_path = Path(
            decisions_path
            or self.output_dir / "decision_history_v2.csv"
        )
        daily_kpis_path = Path(
            daily_kpis_path
            or self.output_dir / "adaptive_daily_kpis_v2.csv"
        )
        output_path = Path(
            output_path
            or self.output_dir / "training_dataset_v2.parquet"
        )

        for path in (
            snapshots_path,
            decisions_path,
            daily_kpis_path,
        ):
            if not path.is_file():
                raise TrainingDatasetBuilderV2Error(
                    f"Required input file not found: {path}"
                )

        snapshots = self._load_snapshots(snapshots_path)
        decisions = pd.read_csv(decisions_path)
        daily_kpis = pd.read_csv(daily_kpis_path)

        self._validate_source_frames(
            snapshots=snapshots,
            decisions=decisions,
            daily_kpis=daily_kpis,
        )

        decisions = self._normalize_decisions(decisions)
        daily_kpis = self._normalize_kpis(daily_kpis)

        rows: list[dict[str, Any]] = []

        for index, snapshot in enumerate(snapshots):
            day = int(snapshot["simulation_day"])

            decision_row = decisions.loc[
                decisions["simulation_day"] == day
            ]
            kpi_row = daily_kpis.loc[
                daily_kpis["simulation_day"] == day
            ]

            if len(decision_row) != 1:
                raise TrainingDatasetBuilderV2Error(
                    f"Expected exactly one decision for day {day}; "
                    f"found {len(decision_row)}."
                )
            if len(kpi_row) != 1:
                raise TrainingDatasetBuilderV2Error(
                    f"Expected exactly one KPI row for day {day}; "
                    f"found {len(kpi_row)}."
                )

            decision = decision_row.iloc[0].to_dict()
            kpi = kpi_row.iloc[0].to_dict()

            next_snapshot = (
                snapshots[index + 1]
                if index + 1 < len(snapshots)
                else None
            )

            if next_snapshot is not None:
                expected_next_day = day + 1
                actual_next_day = int(
                    next_snapshot["simulation_day"]
                )
                if actual_next_day != expected_next_day:
                    raise TrainingDatasetBuilderV2Error(
                        "Snapshot sequence is not contiguous: "
                        f"day {day} is followed by {actual_next_day}."
                    )

            row = self._build_transition_row(
                snapshot=snapshot,
                decision=decision,
                kpi=kpi,
                next_snapshot=next_snapshot,
            )
            rows.append(row)

        dataset = pd.DataFrame(rows)
        self._validate_final_dataset(dataset)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        csv_fallback_path: Path | None = None
        try:
            dataset.to_parquet(
                output_path,
                index=False,
            )
        except (ImportError, ModuleNotFoundError, ValueError):
            csv_fallback_path = output_path.with_suffix(".csv")
            dataset.to_csv(
                csv_fallback_path,
                index=False,
            )

        return TrainingDatasetBuildResult(
            rows_created=len(dataset),
            terminal_rows=int(dataset["is_terminal"].sum()),
            output_path=str(output_path.resolve()),
            csv_fallback_path=(
                str(csv_fallback_path.resolve())
                if csv_fallback_path is not None
                else None
            ),
            leakage_checks_passed=True,
        )

    @staticmethod
    def _load_snapshots(
        path: Path,
    ) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []

        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue

                try:
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise TrainingDatasetBuilderV2Error(
                        f"Invalid JSON on line {line_number}: {exc}"
                    ) from exc

                if not isinstance(row, dict):
                    raise TrainingDatasetBuilderV2Error(
                        f"Snapshot line {line_number} is not an object."
                    )

                snapshots.append(row)

        if not snapshots:
            raise TrainingDatasetBuilderV2Error(
                f"No snapshots found in {path}."
            )

        snapshots.sort(
            key=lambda row: int(row["simulation_day"])
        )
        return snapshots

    def _validate_source_frames(
        self,
        *,
        snapshots: list[dict[str, Any]],
        decisions: pd.DataFrame,
        daily_kpis: pd.DataFrame,
    ) -> None:
        required_snapshot_columns = {
            "snapshot_id",
            "episode_id",
            "episode_seed",
            "simulation_day",
            "synthetic_date",
            "expected_demand_units",
            "final_demand_multiplier",
            "final_supply_multiplier",
            "logistics_cost_multiplier",
            "economic_regime",
            "total_on_hand_units",
            "total_available_units",
            "total_in_transit_units",
            "total_inventory_position_units",
            "inventory_value",
            "open_purchase_orders",
            "open_purchase_order_units",
            "rolling_fill_rate_7d",
            "rolling_requested_units_7d",
            "rolling_sold_units_7d",
            "rolling_lost_units_7d",
        }

        snapshot_columns = set(snapshots[0])
        missing_snapshot = (
            required_snapshot_columns - snapshot_columns
        )
        if missing_snapshot:
            raise TrainingDatasetBuilderV2Error(
                "Snapshots are missing required fields: "
                f"{sorted(missing_snapshot)}"
            )

        missing_decision = (
            self.REQUIRED_DECISION_COLUMNS
            - set(decisions.columns)
        )
        if missing_decision:
            raise TrainingDatasetBuilderV2Error(
                "Decision history is missing required columns: "
                f"{sorted(missing_decision)}"
            )

        missing_kpi = (
            self.REQUIRED_KPI_COLUMNS
            - set(daily_kpis.columns)
        )
        if missing_kpi:
            raise TrainingDatasetBuilderV2Error(
                "Daily KPI file is missing required columns: "
                f"{sorted(missing_kpi)}"
            )

        days = [int(row["simulation_day"]) for row in snapshots]
        if len(days) != len(set(days)):
            raise TrainingDatasetBuilderV2Error(
                "Duplicate simulation_day values exist in snapshots."
            )

        snapshot_ids = [
            str(row["snapshot_id"]) for row in snapshots
        ]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise TrainingDatasetBuilderV2Error(
                "Duplicate snapshot_id values exist."
            )

        self._validate_snapshot_leakage(snapshot_columns)

    def _validate_snapshot_leakage(
        self,
        snapshot_columns: set[str],
    ) -> None:
        suspicious = sorted(
            column
            for column in snapshot_columns
            if any(
                token in column.lower()
                for token in self.FORBIDDEN_STATE_TOKENS
            )
            and not column.lower().startswith(
                (
                    "rolling_sold_units",
                    "rolling_lost_units",
                    "previous_ending_on_hand",
                    "previous_ending_in_transit",
                )
            )
        )

        if suspicious:
            raise TrainingDatasetBuilderV2Error(
                "Potential post-decision leakage fields detected "
                f"in state snapshots: {suspicious}"
            )

    @staticmethod
    def _normalize_decisions(
        decisions: pd.DataFrame,
    ) -> pd.DataFrame:
        normalized = decisions.copy()
        normalized["simulation_day"] = (
            normalized["simulation_day"].astype(int)
        )

        if normalized["simulation_day"].duplicated().any():
            duplicates = normalized.loc[
                normalized["simulation_day"].duplicated(),
                "simulation_day",
            ].tolist()
            raise TrainingDatasetBuilderV2Error(
                f"Duplicate decision days found: {duplicates}"
            )

        return normalized

    @staticmethod
    def _normalize_kpis(
        daily_kpis: pd.DataFrame,
    ) -> pd.DataFrame:
        normalized = daily_kpis.copy()
        normalized["simulation_day"] = (
            normalized["simulation_day"].astype(int)
        )

        if normalized["simulation_day"].duplicated().any():
            duplicates = normalized.loc[
                normalized["simulation_day"].duplicated(),
                "simulation_day",
            ].tolist()
            raise TrainingDatasetBuilderV2Error(
                f"Duplicate KPI days found: {duplicates}"
            )

        normalized = normalized.sort_values(
            "simulation_day"
        ).reset_index(drop=True)

        normalized["daily_revenue"] = (
            normalized["cumulative_revenue"]
            .astype(float)
            .diff()
            .fillna(
                normalized["cumulative_revenue"].astype(float)
            )
        )

        normalized["daily_operating_profit"] = (
            normalized["calibrated_net_operating_profit"]
            .astype(float)
            .diff()
            .fillna(
                normalized[
                    "calibrated_net_operating_profit"
                ].astype(float)
            )
        )

        return normalized

    @staticmethod
    def _flatten_state(
        snapshot: dict[str, Any],
        *,
        prefix: str,
    ) -> dict[str, Any]:
        excluded = {
            "inventory_positions",
            "captured_at_utc",
        }

        flattened: dict[str, Any] = {}
        for key, value in snapshot.items():
            if key in excluded:
                continue

            if isinstance(value, (dict, list, tuple)):
                continue

            flattened[f"{prefix}{key}"] = value

        inventory_positions = snapshot.get(
            "inventory_positions",
            [],
        )
        flattened[
            f"{prefix}inventory_position_count"
        ] = len(inventory_positions)

        flattened[
            f"{prefix}positions_below_reorder_point"
        ] = sum(
            1
            for row in inventory_positions
            if bool(row.get("below_reorder_point", False))
        )

        flattened[
            f"{prefix}total_stock_gap_to_target"
        ] = sum(
            int(row.get("stock_gap_to_target", 0))
            for row in inventory_positions
        )

        return flattened

    def _build_transition_row(
        self,
        *,
        snapshot: dict[str, Any],
        decision: dict[str, Any],
        kpi: dict[str, Any],
        next_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        row = self._flatten_state(
            snapshot,
            prefix="state_",
        )

        row.update(
            {
                "action_selected_policy": str(
                    decision["selected_policy"]
                ),
                "reward_daily_operating_profit": round(
                    float(kpi["daily_operating_profit"]),
                    6,
                ),
                "reward_daily_revenue": round(
                    float(kpi["daily_revenue"]),
                    6,
                ),
                "outcome_requested_units": int(
                    kpi["requested_units"]
                ),
                "outcome_sold_units": int(
                    kpi["sold_units"]
                ),
                "outcome_lost_units": int(
                    kpi["lost_units"]
                ),
                "outcome_fill_rate": float(
                    kpi["fill_rate"]
                ),
                "outcome_orders_created": int(
                    kpi["orders_created"]
                ),
                "outcome_receipts_created": int(
                    kpi["receipts_created"]
                ),
                "outcome_ending_on_hand_units": int(
                    kpi["ending_on_hand_units"]
                ),
                "outcome_ending_in_transit_units": int(
                    kpi["ending_in_transit_units"]
                ),
                "is_terminal": next_snapshot is None,
            }
        )

        if next_snapshot is None:
            row["next_snapshot_id"] = None
            row["next_simulation_day"] = None
        else:
            row.update(
                self._flatten_state(
                    next_snapshot,
                    prefix="next_state_",
                )
            )
            row["next_snapshot_id"] = str(
                next_snapshot["snapshot_id"]
            )
            row["next_simulation_day"] = int(
                next_snapshot["simulation_day"]
            )

        return row

    @staticmethod
    def _validate_final_dataset(
        dataset: pd.DataFrame,
    ) -> None:
        if dataset.empty:
            raise TrainingDatasetBuilderV2Error(
                "The generated training dataset is empty."
            )

        if dataset["state_snapshot_id"].duplicated().any():
            raise TrainingDatasetBuilderV2Error(
                "Duplicate state_snapshot_id values exist "
                "in the final dataset."
            )

        terminal_count = int(dataset["is_terminal"].sum())
        if terminal_count != 1:
            raise TrainingDatasetBuilderV2Error(
                "Expected exactly one terminal transition; "
                f"found {terminal_count}."
            )

        non_terminal = dataset.loc[
            ~dataset["is_terminal"]
        ]
        if non_terminal["next_snapshot_id"].isna().any():
            raise TrainingDatasetBuilderV2Error(
                "A non-terminal transition is missing next state."
            )

        required_non_null = [
            "state_snapshot_id",
            "state_simulation_day",
            "action_selected_policy",
            "reward_daily_operating_profit",
            "outcome_fill_rate",
        ]
        missing_counts = (
            dataset[required_non_null].isna().sum()
        )
        invalid = missing_counts[
            missing_counts > 0
        ].to_dict()
        if invalid:
            raise TrainingDatasetBuilderV2Error(
                "Required training fields contain null values: "
                f"{invalid}"
            )


def main() -> None:
    output_dir = Path(
        "simulation/output/adaptive_policy_v2"
    )

    result = TrainingDatasetBuilderV2(
        output_dir=output_dir
    ).build()

    print("=" * 72)
    print("TRAINING DATASET V2")
    print("=" * 72)
    print(json.dumps(result.to_dict(), indent=2))
    print("=" * 72)
    print("STATUS: PASSED")


if __name__ == "__main__":
    main()
