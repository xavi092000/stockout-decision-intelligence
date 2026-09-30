from __future__ import annotations

"""Tabular Q-learning policy for closed-loop inventory control.

The agent learns action classes from sequential interaction with SimulationEngine.
Quantities and transfer sources remain deterministic feasibility guardrails.  This
keeps the first RL experiment scientifically interpretable while allowing the
agent to learn *when* to wait, order normally, expedite, or transfer.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from random import Random

from simulation.action import ActionType, InventoryAction
from simulation.decision_policy import DecisionResult
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy


RL_ACTIONS = (
    ActionType.DO_NOTHING,
    ActionType.ORDER_NORMAL,
    ActionType.ORDER_EXPEDITE,
    ActionType.TRANSFER_STOCK,
)


def _bucket(value: float, cuts: tuple[float, ...]) -> int:
    return sum(value > cut for cut in cuts)


@dataclass(frozen=True)
class QLearningConfig:
    alpha: float = 0.15
    gamma: float = 0.97
    epsilon: float = 0.20
    target_days_of_cover: float = 14.0
    minimum_order_quantity: int = 1
    reward_scale: float = 100.0

    def __post_init__(self) -> None:
        if not 0 < self.alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        if not 0 <= self.gamma <= 1:
            raise ValueError("gamma must be in [0, 1]")
        if not 0 <= self.epsilon <= 1:
            raise ValueError("epsilon must be in [0, 1]")
        if self.target_days_of_cover <= 0 or self.minimum_order_quantity <= 0:
            raise ValueError("inventory control parameters must be positive")
        if self.reward_scale <= 0:
            raise ValueError("reward_scale must be positive")


class QLearningInventoryPolicy:
    """Closed-loop epsilon-greedy Q-learning policy.

    Learning is local to each store-SKU trajectory: after a day's reward is
    observed, the TD update is completed when that store-SKU is seen on the next
    day.  No future realized demand is used as a decision-time feature.
    """

    def __init__(self, config: QLearningConfig | None = None, *, seed: int = 0,
                 training: bool = True, q_table: dict | None = None) -> None:
        self.config = config or QLearningConfig()
        self.training = training
        self._rng = Random(seed)
        self.q: dict[str, dict[str, float]] = q_table or {}
        self._pending: dict[tuple[str, str], tuple[str, str]] = {}
        self._rewards: dict[tuple[str, str], float] = {}
        self.decision_count = 0
        self.exploration_count = 0
        self.update_count = 0
        self.fallback_count = 0
        self._fallback = EconomicConstrainedPolicy(EconomicConstrainedConfig(
            target_days_of_cover=self.config.target_days_of_cover, expedite_trigger_days=3
        ))

    def _state_key(self, *, state, inventory, product, supplier, forecast) -> str:
        demand = max(float(forecast.forecast_daily_demand), 1e-6)
        pending = sum(
            op.quantity for op in state.pending_operations
            if op.is_pending and op.destination_store_id == inventory.store_id
            and op.sku_id == inventory.sku_id
        )
        stock_cover = inventory.available_stock / demand
        pending_cover = pending / demand
        trend = float(forecast.forecast_next_3d) / (3.0 * demand)
        safety_cover = product.safety_stock / demand
        promo = int(state.is_promotion_active(inventory.store_id, inventory.sku_id))
        parts = (
            _bucket(stock_cover, (1, 3, 7, 14, 21, 35)),
            _bucket(pending_cover, (0, 1, 3, 7, 14)),
            _bucket(trend, (0.85, 1.0, 1.15)),
            _bucket(safety_cover, (1, 2, 4)),
            _bucket(float(supplier.lead_time_days), (1, 3, 5, 7)),
            promo,
            str(state.weather_condition).lower(),
        )
        return "|".join(map(str, parts))

    def _candidate_actions(self, *, state, inventory, product, store, supplier,
                           forecast, forecasts_by_key) -> dict[ActionType, InventoryAction]:
        pending = sum(
            op.quantity for op in state.pending_operations
            if op.is_pending and op.destination_store_id == store.store_id
            and op.sku_id == product.sku_id
        )
        daily = max(float(forecast.forecast_daily_demand), 1e-6)
        target = daily * self.config.target_days_of_cover + product.safety_stock
        gap = max(0, math.ceil(target - inventory.available_stock - pending))
        projected_cover = (inventory.available_stock + pending) / daily
        critical = gap > 0 and projected_cover <= supplier.lead_time_days + 1
        actions = {}
        if not critical:
            actions[ActionType.DO_NOTHING] = InventoryAction(
                ActionType.DO_NOTHING, store.store_id, product.sku_id, 0
            )
        if gap > 0:
            quantity = max(self.config.minimum_order_quantity, gap)
            actions[ActionType.ORDER_NORMAL] = InventoryAction(
                ActionType.ORDER_NORMAL, store.store_id, product.sku_id, quantity
            )
            actions[ActionType.ORDER_EXPEDITE] = InventoryAction(
                ActionType.ORDER_EXPEDITE, store.store_id, product.sku_id, quantity
            )
            if critical:
                actions.pop(ActionType.ORDER_NORMAL, None)
            donors = []
            for donor in state.inventories:
                if donor.sku_id != product.sku_id or donor.store_id == store.store_id:
                    continue
                donor_fc = forecasts_by_key[(donor.store_id, donor.sku_id)]
                surplus = math.floor(
                    donor.available_stock - donor_fc.forecast_next_3d - product.safety_stock
                )
                if surplus > 0:
                    donors.append((surplus, donor.store_id))
            if donors:
                surplus, donor_id = max(donors)
                actions[ActionType.TRANSFER_STOCK] = InventoryAction(
                    ActionType.TRANSFER_STOCK, store.store_id, product.sku_id,
                    min(gap, surplus), donor_id
                )
        return actions

    def _values(self, state_key: str) -> dict[str, float]:
        return self.q.setdefault(state_key, {a.value: 0.0 for a in RL_ACTIONS})

    def decide(self, *, state, inventory, product, store, supplier, forecast,
               forecasts_by_key) -> DecisionResult:
        key = (store.store_id, product.sku_id)
        state_key = self._state_key(
            state=state, inventory=inventory, product=product,
            supplier=supplier, forecast=forecast
        )
        candidates = self._candidate_actions(
            state=state, inventory=inventory, product=product, store=store,
            supplier=supplier, forecast=forecast, forecasts_by_key=forecasts_by_key
        )
        state_was_known = state_key in self.q
        values = self._values(state_key)

        # Complete yesterday's TD update using today's state as s'.
        if self.training and key in self._pending and key in self._rewards:
            old_state, old_action = self._pending.pop(key)
            reward = self._rewards.pop(key) / self.config.reward_scale
            next_best = max(values[a.value] for a in candidates)
            old_values = self._values(old_state)
            old_q = old_values[old_action]
            old_values[old_action] = old_q + self.config.alpha * (
                reward + self.config.gamma * next_best - old_q
            )
            self.update_count += 1

        feasible = list(candidates)
        explore = self.training and self._rng.random() < self.config.epsilon
        if not self.training and not state_was_known:
            # Safe generalization rule: the learned controller never improvises
            # in a state absent from training. It delegates to the audited
            # deterministic baseline and records the fallback.
            fallback = self._fallback.decide(
                state=state, inventory=inventory, product=product, store=store,
                supplier=supplier, forecast=forecast, forecasts_by_key=forecasts_by_key
            )
            self.fallback_count += 1
            selected = fallback.action.action_type
            action = fallback.action
        else:
            if explore:
                selected = self._rng.choice(feasible)
                self.exploration_count += 1
            else:
                # Stable tie-breaking prevents random evaluation behavior.
                selected = max(feasible, key=lambda a: (values[a.value], -feasible.index(a)))
            action = candidates[selected]
        if self.training:
            self._pending[key] = (state_key, selected.value)
        self.decision_count += 1

        projected = max(
            0.0,
            float(forecast.forecast_daily_demand) * self.config.target_days_of_cover
            + product.safety_stock
            - inventory.available_stock
            - sum(op.quantity for op in state.pending_operations
                  if op.is_pending and op.destination_store_id == store.store_id
                  and op.sku_id == product.sku_id),
        )
        return DecisionResult(
            action=action,
            reason=f"Q-learning policy: {selected.value}; state={state_key}",
            forecast_daily_demand=forecast.forecast_daily_demand,
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=round(projected, 2),
        )

    def observe_day(self, rewards) -> None:
        """Attach realized immediate rewards to the actions just taken."""
        if not self.training:
            return
        for reward in rewards:
            key = (reward.store_id, reward.sku_id)
            if key in self._pending:
                # Engine may reduce a transfer reservation. Learn from the actual
                # executed class, not from an impossible requested transfer.
                state_key, _ = self._pending[key]
                self._pending[key] = (state_key, reward.action_type)
                self._rewards[key] = float(reward.immediate_reward)

    def end_episode(self) -> None:
        """Terminal TD update (no bootstrap value)."""
        if self.training:
            for key, (state_key, action) in list(self._pending.items()):
                if key not in self._rewards:
                    continue
                reward = self._rewards[key] / self.config.reward_scale
                values = self._values(state_key)
                old_q = values[action]
                values[action] = old_q + self.config.alpha * (reward - old_q)
                self.update_count += 1
        self._pending.clear()
        self._rewards.clear()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "stockout_q_learning_v1",
            "config": self.config.__dict__,
            "q_table": self.q,
            "training_stats": {
                "decisions": self.decision_count,
                "explorations": self.exploration_count,
                "updates": self.update_count,
                "states": len(self.q),
            },
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, *, training: bool = False, seed: int = 0):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "stockout_q_learning_v1":
            raise ValueError("Unsupported RL policy artifact")
        return cls(
            QLearningConfig(**payload["config"]), seed=seed,
            training=training, q_table=payload["q_table"]
        )
