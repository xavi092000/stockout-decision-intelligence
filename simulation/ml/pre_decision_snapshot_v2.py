from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence


class PreDecisionSnapshotV2Error(RuntimeError):
    """Raised when a leakage-safe pre-decision snapshot cannot be created."""


@dataclass(frozen=True)
class PreDecisionSnapshotV2:
    snapshot_id: str
    episode_id: str
    episode_seed: int
    simulation_day: int
    synthetic_date: str
    captured_at_utc: str

    expected_demand_units: float
    final_demand_multiplier: float
    final_supply_multiplier: float
    logistics_cost_multiplier: float
    economic_regime: str
    category: str
    department: str
    store: str
    state: str

    total_on_hand_units: int
    total_available_units: int
    total_in_transit_units: int
    total_inventory_position_units: int
    inventory_value: float
    open_purchase_orders: int
    open_purchase_order_units: int

    trailing_days_available: int
    rolling_fill_rate_7d: float
    rolling_requested_units_7d: int
    rolling_sold_units_7d: int
    rolling_lost_units_7d: int
    rolling_orders_created_7d: int
    rolling_receipts_created_7d: int
    rolling_revenue_delta_7d: float
    previous_ending_on_hand_units: int
    previous_ending_in_transit_units: int

    inventory_positions: tuple[dict[str, Any], ...]
    schema_version: str = "2.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PreDecisionSnapshotBuilderV2:
    """Builds immutable snapshots from WorldState, DailyScenario and past KPIs."""

    def __init__(self, trailing_window_days: int = 7) -> None:
        if trailing_window_days <= 0:
            raise ValueError("trailing_window_days must be positive.")
        self.trailing_window_days = trailing_window_days

    def build(
        self,
        *,
        world: Any,
        scenario: Any,
        trailing_metrics: Sequence[Mapping[str, Any]],
        episode_seed: int,
        episode_id: str | None = None,
    ) -> PreDecisionSnapshotV2:
        self._validate_inputs(world, scenario, trailing_metrics, episode_seed)

        simulation_day = int(scenario.simulation_day)
        synthetic_date = str(scenario.synthetic_date)
        resolved_episode_id = episode_id or f"episode-seed-{episode_seed}"

        products = {str(product.sku_id): product for product in world.products}

        inventory_positions: list[dict[str, Any]] = []
        total_on_hand = 0
        total_available = 0
        total_in_transit = 0
        total_inventory_position = 0
        inventory_value = 0.0

        for position in world.inventory:
            sku_id = str(position.sku_id)
            product = products.get(sku_id)
            if product is None:
                raise PreDecisionSnapshotV2Error(
                    f"Missing product definition for sku_id={sku_id!r}."
                )

            on_hand = int(position.on_hand)
            available = int(position.available)
            in_transit = int(position.in_transit)
            inventory_position = int(position.inventory_position)
            reorder_point = int(position.reorder_point)
            target_stock = int(position.target_stock)

            total_on_hand += on_hand
            total_available += available
            total_in_transit += in_transit
            total_inventory_position += inventory_position
            inventory_value += on_hand * float(product.unit_cost)

            inventory_positions.append(
                {
                    "store_id": str(position.store_id),
                    "sku_id": sku_id,
                    "on_hand": on_hand,
                    "available": available,
                    "in_transit": in_transit,
                    "inventory_position": inventory_position,
                    "reorder_point": reorder_point,
                    "target_stock": target_stock,
                    "stock_gap_to_target": target_stock - inventory_position,
                    "below_reorder_point": inventory_position <= reorder_point,
                    "unit_cost": round(float(product.unit_cost), 6),
                    "unit_price": round(float(product.unit_price), 6),
                    "holding_cost_per_unit_day": round(
                        float(product.holding_cost_per_unit_day), 6
                    ),
                    "stockout_penalty_per_unit": round(
                        float(product.stockout_penalty_per_unit), 6
                    ),
                    "category": str(product.category),
                    "department": str(product.department),
                    "supplier_id": str(product.supplier_id),
                }
            )

        inventory_positions.sort(key=lambda row: (row["store_id"], row["sku_id"]))

        open_orders = [
            order
            for order in world.purchase_orders
            if order.status in {"OPEN", "PARTIALLY_RECEIVED"}
            and int(order.open_units) > 0
        ]
        open_purchase_order_units = sum(int(order.open_units) for order in open_orders)

        trailing = list(trailing_metrics[-self.trailing_window_days :])
        trailing_features = self._build_trailing_features(trailing)

        snapshot_id = self._snapshot_id(
            episode_id=resolved_episode_id,
            simulation_day=simulation_day,
            synthetic_date=synthetic_date,
            world=world,
        )

        return PreDecisionSnapshotV2(
            snapshot_id=snapshot_id,
            episode_id=resolved_episode_id,
            episode_seed=int(episode_seed),
            simulation_day=simulation_day,
            synthetic_date=synthetic_date,
            captured_at_utc=datetime.now(timezone.utc).isoformat(),
            expected_demand_units=float(scenario.expected_demand_units),
            final_demand_multiplier=float(scenario.final_demand_multiplier),
            final_supply_multiplier=float(scenario.final_supply_multiplier),
            logistics_cost_multiplier=float(scenario.logistics_cost_multiplier),
            economic_regime=str(scenario.economic_regime),
            category=str(scenario.category),
            department=str(scenario.department),
            store=str(scenario.store),
            state=str(scenario.state),
            total_on_hand_units=total_on_hand,
            total_available_units=total_available,
            total_in_transit_units=total_in_transit,
            total_inventory_position_units=total_inventory_position,
            inventory_value=round(inventory_value, 2),
            open_purchase_orders=len(open_orders),
            open_purchase_order_units=open_purchase_order_units,
            trailing_days_available=trailing_features["trailing_days_available"],
            rolling_fill_rate_7d=trailing_features["rolling_fill_rate_7d"],
            rolling_requested_units_7d=trailing_features["rolling_requested_units_7d"],
            rolling_sold_units_7d=trailing_features["rolling_sold_units_7d"],
            rolling_lost_units_7d=trailing_features["rolling_lost_units_7d"],
            rolling_orders_created_7d=trailing_features["rolling_orders_created_7d"],
            rolling_receipts_created_7d=trailing_features["rolling_receipts_created_7d"],
            rolling_revenue_delta_7d=trailing_features["rolling_revenue_delta_7d"],
            previous_ending_on_hand_units=trailing_features["previous_ending_on_hand_units"],
            previous_ending_in_transit_units=trailing_features["previous_ending_in_transit_units"],
            inventory_positions=tuple(inventory_positions),
        )

    @staticmethod
    def _validate_inputs(
        world: Any,
        scenario: Any,
        trailing_metrics: Sequence[Mapping[str, Any]],
        episode_seed: int,
    ) -> None:
        if int(episode_seed) < 0:
            raise ValueError("episode_seed must be non-negative.")

        required_scenario_fields = (
            "simulation_day",
            "synthetic_date",
            "expected_demand_units",
            "final_demand_multiplier",
            "final_supply_multiplier",
            "logistics_cost_multiplier",
            "category",
            "department",
            "store",
            "state",
            "economic_regime",
        )
        missing = [field for field in required_scenario_fields if not hasattr(scenario, field)]
        if missing:
            raise PreDecisionSnapshotV2Error(
                f"Scenario is missing required fields: {missing}."
            )

        for field in ("inventory", "products", "purchase_orders"):
            if not hasattr(world, field):
                raise PreDecisionSnapshotV2Error(f"WorldState is missing {field}.")

        for index, row in enumerate(trailing_metrics):
            if not isinstance(row, Mapping):
                raise PreDecisionSnapshotV2Error(
                    f"trailing_metrics[{index}] must be a mapping."
                )

    @staticmethod
    def _build_trailing_features(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "trailing_days_available": 0,
                "rolling_fill_rate_7d": 1.0,
                "rolling_requested_units_7d": 0,
                "rolling_sold_units_7d": 0,
                "rolling_lost_units_7d": 0,
                "rolling_orders_created_7d": 0,
                "rolling_receipts_created_7d": 0,
                "rolling_revenue_delta_7d": 0.0,
                "previous_ending_on_hand_units": 0,
                "previous_ending_in_transit_units": 0,
            }

        requested = sum(int(row.get("requested_units", 0)) for row in rows)
        sold = sum(int(row.get("sold_units", 0)) for row in rows)
        lost = sum(int(row.get("lost_units", 0)) for row in rows)
        fill_rate = sold / requested if requested > 0 else 1.0

        first_revenue = float(rows[0].get("cumulative_revenue", 0.0))
        last_revenue = float(rows[-1].get("cumulative_revenue", 0.0))
        revenue_delta = max(0.0, last_revenue - first_revenue)

        return {
            "trailing_days_available": len(rows),
            "rolling_fill_rate_7d": round(fill_rate, 6),
            "rolling_requested_units_7d": requested,
            "rolling_sold_units_7d": sold,
            "rolling_lost_units_7d": lost,
            "rolling_orders_created_7d": sum(int(row.get("orders_created", 0)) for row in rows),
            "rolling_receipts_created_7d": sum(int(row.get("receipts_created", 0)) for row in rows),
            "rolling_revenue_delta_7d": round(revenue_delta, 2),
            "previous_ending_on_hand_units": int(rows[-1].get("ending_on_hand_units", 0)),
            "previous_ending_in_transit_units": int(rows[-1].get("ending_in_transit_units", 0)),
        }

    @staticmethod
    def _snapshot_id(
        *,
        episode_id: str,
        simulation_day: int,
        synthetic_date: str,
        world: Any,
    ) -> str:
        world_version = str(
            getattr(world, "metadata", {}).get("adaptive_policy_version", "unversioned")
        )
        payload = f"{episode_id}|{simulation_day}|{synthetic_date}|{world_version}"
        digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{episode_id}-day-{simulation_day:04d}-{digest}"
