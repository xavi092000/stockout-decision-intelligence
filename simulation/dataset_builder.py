from __future__ import annotations

"""
Leakage-safe dataset builder for the Stockout Decision Intelligence Platform.

Design rule:
- Feature snapshots are captured BEFORE an action is selected.
- Outcome labels are attached only AFTER realized demand and state transition.
- Future outcomes are never exposed through FEATURE_COLUMNS.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import csv

from simulation.decision_policy import DecisionResult
from simulation.reward_engine import DecisionReward
from simulation.pending_operation import (
    PendingOperationStatus,
    PendingOperationType,
)
from simulation.state import SimulationState
from simulation.state_transition import DailyTransitionOutcome
from simulation.ml.feature_contract import (
    PRE_DECISION_FEATURE_COLUMNS,
)


IDENTIFIER_COLUMNS = (
    "simulation_id",
    "episode_seed",
    "day",
    "date",
    "store_id",
    "sku_id",
)

FEATURE_COLUMNS = PRE_DECISION_FEATURE_COLUMNS

ACTION_COLUMNS = (
    "chosen_action",
    "action_quantity",
    "source_store_id",
)

OUTCOME_COLUMNS = (
    "actual_demand",
    "fulfilled_units",
    "unmet_units",
    "ending_stock",
    "stockout_occurred",
    "local_revenue",
    "normal_order_cost",
    "expedite_order_cost",
    "transfer_cost",
    "holding_cost",
    "lost_sales_cost",
    "stockout_penalty",
    "immediate_reward",
)

ALL_COLUMNS = (
    *IDENTIFIER_COLUMNS,
    *FEATURE_COLUMNS,
    *ACTION_COLUMNS,
    *OUTCOME_COLUMNS,
)

FORBIDDEN_FEATURE_COLUMNS = frozenset(
    {
        "chosen_action",
        "action_quantity",
        "source_store_id",
        "actual_demand",
        "fulfilled_units",
        "unmet_units",
        "ending_stock",
        "stockout_occurred",
        "local_revenue",
        "normal_order_cost",
        "expedite_order_cost",
        "transfer_cost",
        "holding_cost",
        "lost_sales_cost",
        "stockout_penalty",
        "immediate_reward",
        "reward",
        "regret",
        "best_action",
        "realized_demand",
        "future_stockout",
        "future_cost",
    }
)


@dataclass(frozen=True)
class PreDecisionSnapshot:
    simulation_id: str
    episode_seed: int
    day: int
    date: str
    store_id: str
    sku_id: str

    current_stock: int
    available_stock: int
    pending_normal_units: int
    pending_expedite_units: int

    forecast_daily_demand: int
    forecast_next_3d: int
    projected_stock_gap: int

    temperature_c: float
    weather_condition: str
    promotion_flag: int
    holiday_flag: int

    supplier_lead_time_days: int
    neighbor_surplus_units: int

    def __post_init__(self) -> None:
        numeric_values = (
            self.current_stock,
            self.available_stock,
            self.pending_normal_units,
            self.pending_expedite_units,
            self.forecast_daily_demand,
            self.forecast_next_3d,
            self.supplier_lead_time_days,
            self.neighbor_surplus_units,
        )

        if any(value < 0 for value in numeric_values):
            raise ValueError(
                "Pre-decision quantities cannot be negative."
            )


@dataclass(frozen=True)
class TrainingExample:
    simulation_id: str
    episode_seed: int
    day: int
    date: str
    store_id: str
    sku_id: str

    current_stock: int
    available_stock: int
    pending_normal_units: int
    pending_expedite_units: int

    forecast_daily_demand: int
    forecast_next_3d: int
    projected_stock_gap: int

    temperature_c: float
    weather_condition: str
    promotion_flag: int
    holiday_flag: int

    supplier_lead_time_days: int
    neighbor_surplus_units: int

    chosen_action: str
    action_quantity: int
    source_store_id: str

    actual_demand: int
    fulfilled_units: int
    unmet_units: int
    ending_stock: int
    stockout_occurred: int
    local_revenue: float
    normal_order_cost: float
    expedite_order_cost: float
    transfer_cost: float
    holding_cost: float
    lost_sales_cost: float
    stockout_penalty: float
    immediate_reward: float

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


class LeakageSafeDatasetBuilder:
    """
    Build training rows without allowing post-decision information
    into the model feature set.
    """

    def __init__(
        self,
        simulation_id: str,
        episode_seed: int,
    ) -> None:
        if not simulation_id.strip():
            raise ValueError("simulation_id cannot be empty.")

        self.simulation_id = simulation_id
        self.episode_seed = episode_seed
        self._snapshots: dict[
            tuple[int, str, str],
            PreDecisionSnapshot,
        ] = {}
        self._examples: list[TrainingExample] = []

        self.validate_feature_schema(FEATURE_COLUMNS)

    @property
    def examples(self) -> tuple[TrainingExample, ...]:
        return tuple(self._examples)

    @property
    def row_count(self) -> int:
        return len(self._examples)

    @staticmethod
    def validate_feature_schema(
        feature_columns: Iterable[str],
    ) -> None:
        columns = tuple(feature_columns)
        forbidden = sorted(
            set(columns) & FORBIDDEN_FEATURE_COLUMNS
        )

        if forbidden:
            raise ValueError(
                "Leakage detected in feature schema: "
                + ", ".join(forbidden)
            )

        unknown = sorted(
            set(columns) - set(FEATURE_COLUMNS)
        )

        if unknown:
            raise ValueError(
                "Unapproved feature columns: "
                + ", ".join(unknown)
            )

    def capture_before_decision(
        self,
        *,
        state: SimulationState,
        inventory: Any,
        supplier: Any,
        forecast: Any,
        projected_stock_gap: int,
    ) -> None:
        """
        Capture only information observable before the decision.

        This must be called before realized demand is generated.
        """
        key = (
            state.current_day,
            inventory.store_id,
            inventory.sku_id,
        )

        if key in self._snapshots:
            raise ValueError(
                "A pre-decision snapshot already exists for "
                f"day={state.current_day}, "
                f"store={inventory.store_id}, "
                f"sku={inventory.sku_id}."
            )

        snapshot = PreDecisionSnapshot(
            simulation_id=self.simulation_id,
            episode_seed=self.episode_seed,
            day=state.current_day,
            date=state.current_date.isoformat(),
            store_id=inventory.store_id,
            sku_id=inventory.sku_id,
            current_stock=int(inventory.stock_level),
            available_stock=int(inventory.available_stock),
            pending_normal_units=self._pending_units(
                state=state,
                store_id=inventory.store_id,
                sku_id=inventory.sku_id,
                operation_type=(
                    PendingOperationType.NORMAL_ORDER
                ),
            ),
            pending_expedite_units=self._pending_units(
                state=state,
                store_id=inventory.store_id,
                sku_id=inventory.sku_id,
                operation_type=(
                    PendingOperationType.EXPEDITE_ORDER
                ),
            ),
            forecast_daily_demand=int(
                getattr(
                    forecast,
                    "forecast_daily_demand",
                    0,
                )
            ),
            forecast_next_3d=int(
                getattr(
                    forecast,
                    "forecast_next_3d",
                    0,
                )
            ),
            projected_stock_gap=int(projected_stock_gap),
            temperature_c=float(state.temperature_c),
            weather_condition=str(
                state.weather_condition
            ),
            promotion_flag=int(
                (
                    inventory.store_id,
                    inventory.sku_id,
                )
                in state.active_promotions
            ),
            holiday_flag=int(
                bool(getattr(state, "is_holiday", False))
            ),
            supplier_lead_time_days=int(
                supplier.lead_time_days
            ),
            neighbor_surplus_units=(
                self._neighbor_surplus_units(
                    state=state,
                    destination_store_id=(
                        inventory.store_id
                    ),
                    sku_id=inventory.sku_id,
                )
            ),
        )

        self._snapshots[key] = snapshot

    def finalize_day(
        self,
        *,
        decisions: list[DecisionResult],
        outcome: DailyTransitionOutcome,
        rewards: list[DecisionReward],
    ) -> list[TrainingExample]:
        """
        Attach actions and decision-level post-decision rewards.
        """
        transitions_by_key = {
            (
                transition.store_id,
                transition.sku_id,
            ): transition
            for transition in outcome.transitions
        }

        rewards_by_key = {
            (reward.store_id, reward.sku_id): reward
            for reward in rewards
        }

        created: list[TrainingExample] = []

        for decision in decisions:
            action = decision.action
            key = (
                self._current_snapshot_day(
                    store_id=action.destination_store_id,
                    sku_id=action.sku_id,
                ),
                action.destination_store_id,
                action.sku_id,
            )

            snapshot = self._snapshots.pop(key, None)
            transition = transitions_by_key.get(
                (
                    action.destination_store_id,
                    action.sku_id,
                )
            )
            reward = rewards_by_key.get(
                (
                    action.destination_store_id,
                    action.sku_id,
                )
            )

            if snapshot is None:
                raise RuntimeError(
                    "Missing pre-decision snapshot."
                )

            if transition is None:
                raise RuntimeError(
                    "Missing daily transition."
                )

            if reward is None:
                raise RuntimeError(
                    "Missing decision-level reward."
                )

            example = TrainingExample(
                **asdict(snapshot),
                chosen_action=action.action_type.value,
                action_quantity=action.quantity,
                source_store_id=action.source_store_id or "",
                actual_demand=transition.actual_demand,
                fulfilled_units=transition.fulfilled_demand,
                unmet_units=transition.unmet_demand,
                ending_stock=transition.ending_stock,
                stockout_occurred=int(
                    transition.stockout_occurred
                ),
                local_revenue=reward.revenue,
                normal_order_cost=reward.normal_order_cost,
                expedite_order_cost=reward.expedite_order_cost,
                transfer_cost=reward.transfer_cost,
                holding_cost=reward.holding_cost,
                lost_sales_cost=reward.lost_sales_cost,
                stockout_penalty=reward.stockout_penalty,
                immediate_reward=reward.immediate_reward,
            )

            self._examples.append(example)
            created.append(example)

        return created

    def write_csv(
        self,
        output_path: str | Path,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(ALL_COLUMNS),
            )
            writer.writeheader()

            for example in self._examples:
                writer.writerow(example.as_row())

        return path

    def assert_no_unfinalized_snapshots(self) -> None:
        if self._snapshots:
            raise RuntimeError(
                f"{len(self._snapshots)} pre-decision snapshots "
                "were never finalized."
            )

    def _current_snapshot_day(
        self,
        *,
        store_id: str,
        sku_id: str,
    ) -> int:
        matching_days = [
            day
            for day, snapshot_store, snapshot_sku
            in self._snapshots
            if (
                snapshot_store == store_id
                and snapshot_sku == sku_id
            )
        ]

        if len(matching_days) != 1:
            raise RuntimeError(
                "Expected exactly one open snapshot for "
                f"store={store_id}, sku={sku_id}; "
                f"found {len(matching_days)}."
            )

        return matching_days[0]

    @staticmethod
    def _pending_units(
        *,
        state: SimulationState,
        store_id: str,
        sku_id: str,
        operation_type: PendingOperationType,
    ) -> int:
        cached = getattr(
            state,
            "_pending_by_type",
            None,
        )

        if cached is not None:
            return cached.get(
                (
                    store_id,
                    sku_id,
                    operation_type,
                ),
                0,
            )

        operations = getattr(
            state,
            "pending_operations",
            (),
        )

        return sum(
            operation.quantity
            for operation in operations
            if (
                operation.status
                == PendingOperationStatus.PENDING
                and operation.operation_type
                == operation_type
                and operation.destination_store_id
                == store_id
                and operation.sku_id == sku_id
            )
        )

    @staticmethod
    def _neighbor_surplus_units(
        *,
        state: SimulationState,
        destination_store_id: str,
        sku_id: str,
    ) -> int:
        """
        Conservative observable proxy.

        Total available units of the same SKU in other stores.
        No future demand or future stock is used.
        """
        return sum(
            int(inventory.available_stock)
            for inventory in state.inventories
            if (
                inventory.sku_id == sku_id
                and inventory.store_id
                != destination_store_id
            )
        )


def validate_training_features(
    feature_columns: Iterable[str],
) -> None:
    """
    Public guardrail for model-training pipelines.
    """
    LeakageSafeDatasetBuilder.validate_feature_schema(
        feature_columns
    )
