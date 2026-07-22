from __future__ import annotations

"""
Decision-level reward engine for the Stockout Decision Intelligence Platform.

Important scientific distinction:
- This engine calculates an IMMEDIATE LOCAL REWARD for each store-SKU decision.
- It does not yet claim full causal credit for delayed supplier arrivals or
  downstream transfer effects.
- Multi-day discounted returns can be built later from these atomic rewards.

Reward formula per decision:
    revenue
    - normal_order_cost
    - expedite_order_cost
    - transfer_cost
    - holding_cost
    - lost_sales_cost
    - stockout_penalty
"""

from dataclasses import dataclass

from simulation.action import ActionType
from simulation.decision_policy import DecisionResult
from simulation.economics import EconomicConfig
from simulation.state_transition import (
    DailyTransitionOutcome,
    InventoryTransition,
)


@dataclass(frozen=True)
class DecisionReward:
    day: int
    store_id: str
    sku_id: str
    action_type: str
    action_quantity: int
    source_store_id: str

    fulfilled_units: int
    unmet_units: int
    ending_stock: int
    stockout_occurred: int

    revenue: float
    normal_order_cost: float
    expedite_order_cost: float
    transfer_cost: float
    holding_cost: float
    lost_sales_cost: float
    stockout_penalty: float

    immediate_reward: float

    def __post_init__(self) -> None:
        if self.day < 1:
            raise ValueError("day must be greater than or equal to 1.")

        if self.action_quantity < 0:
            raise ValueError(
                "action_quantity cannot be negative."
            )

        if self.fulfilled_units < 0:
            raise ValueError(
                "fulfilled_units cannot be negative."
            )

        if self.unmet_units < 0:
            raise ValueError(
                "unmet_units cannot be negative."
            )

        if self.ending_stock < 0:
            raise ValueError(
                "ending_stock cannot be negative."
            )

        if self.stockout_occurred not in {0, 1}:
            raise ValueError(
                "stockout_occurred must be 0 or 1."
            )

    @property
    def total_cost(self) -> float:
        return (
            self.normal_order_cost
            + self.expedite_order_cost
            + self.transfer_cost
            + self.holding_cost
            + self.lost_sales_cost
            + self.stockout_penalty
        )


class DecisionRewardEngine:
    """
    Calculate one leakage-safe immediate reward per decision.

    The reward is calculated only after:
    1. the action has been frozen;
    2. realized demand has been generated;
    3. the state transition has completed.

    Therefore, reward values are labels/outcomes and must never be used
    as decision-time features.
    """

    def __init__(
        self,
        config: EconomicConfig | None = None,
    ) -> None:
        self.config = config or EconomicConfig()

    def evaluate_day(
        self,
        *,
        day: int,
        decisions: list[DecisionResult],
        outcome: DailyTransitionOutcome,
    ) -> list[DecisionReward]:
        transitions_by_key = {
            (
                transition.store_id,
                transition.sku_id,
            ): transition
            for transition in outcome.transitions
        }

        rewards: list[DecisionReward] = []

        for decision in decisions:
            action = decision.action
            key = (
                action.destination_store_id,
                action.sku_id,
            )

            transition = transitions_by_key.get(key)

            if transition is None:
                raise RuntimeError(
                    "No transition found for decision "
                    f"store={action.destination_store_id}, "
                    f"sku={action.sku_id}."
                )

            rewards.append(
                self._evaluate_decision(
                    day=day,
                    decision=decision,
                    transition=transition,
                )
            )

        if len(rewards) != len(decisions):
            raise RuntimeError(
                "Reward count does not match decision count."
            )

        return rewards

    def _evaluate_decision(
        self,
        *,
        day: int,
        decision: DecisionResult,
        transition: InventoryTransition,
    ) -> DecisionReward:
        action = decision.action

        normal_order_cost = 0.0
        expedite_order_cost = 0.0
        transfer_cost = 0.0

        if action.action_type == ActionType.ORDER_NORMAL:
            normal_order_cost = (
                action.quantity
                * self.config.normal_order_cost_per_unit
            )

        elif action.action_type == ActionType.ORDER_EXPEDITE:
            expedite_order_cost = (
                action.quantity
                * self.config.expedite_order_cost_per_unit
            )

        elif action.action_type == ActionType.TRANSFER_STOCK:
            transfer_cost = (
                action.quantity
                * self.config.transfer_cost_per_unit
            )

        revenue = (
            transition.fulfilled_demand
            * self.config.selling_price_per_unit
        )

        holding_cost = (
            transition.ending_stock
            * self.config.holding_cost_per_unit_per_day
        )

        lost_sales_cost = (
            transition.unmet_demand
            * self.config.lost_sale_cost_per_unit
        )

        stockout_penalty = (
            self.config.stockout_penalty_per_event
            if transition.stockout_occurred
            else 0.0
        )

        total_cost = (
            normal_order_cost
            + expedite_order_cost
            + transfer_cost
            + holding_cost
            + lost_sales_cost
            + stockout_penalty
        )

        immediate_reward = revenue - total_cost

        return DecisionReward(
            day=day,
            store_id=action.destination_store_id,
            sku_id=action.sku_id,
            action_type=action.action_type.value,
            action_quantity=action.quantity,
            source_store_id=action.source_store_id or "",
            fulfilled_units=transition.fulfilled_demand,
            unmet_units=transition.unmet_demand,
            ending_stock=transition.ending_stock,
            stockout_occurred=int(
                transition.stockout_occurred
            ),
            revenue=revenue,
            normal_order_cost=normal_order_cost,
            expedite_order_cost=expedite_order_cost,
            transfer_cost=transfer_cost,
            holding_cost=holding_cost,
            lost_sales_cost=lost_sales_cost,
            stockout_penalty=stockout_penalty,
            immediate_reward=immediate_reward,
        )


def validate_reward_total(
    *,
    rewards: list[DecisionReward],
    expected_daily_business_value: float,
    tolerance: float = 1e-6,
) -> None:
    """
    Verify that the sum of decision-level immediate rewards equals the
    existing daily economic value.

    This protects against double counting or missing costs.
    """
    calculated = sum(
        reward.immediate_reward
        for reward in rewards
    )

    difference = abs(
        calculated - expected_daily_business_value
    )

    if difference > tolerance:
        raise RuntimeError(
            "Decision rewards do not reconcile with daily economics: "
            f"calculated={calculated:.6f}, "
            f"expected={expected_daily_business_value:.6f}, "
            f"difference={difference:.6f}."
        )
