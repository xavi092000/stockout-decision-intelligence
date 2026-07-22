from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


class FinancialEngineV2Error(RuntimeError):
    """Raised when financial aggregation inputs are inconsistent."""


@dataclass(frozen=True)
class FinancialKpis:
    realized_revenue: float
    lost_revenue: float
    cost_of_goods_sold: float
    gross_margin: float
    stockout_penalty_cost: float
    procurement_cost: float
    logistics_cost: float
    holding_cost: float
    operating_cost: float
    net_operating_profit: float
    average_inventory_value: float
    inventory_turnover: float
    gmroi: float
    fill_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FinancialEngineV2:
    """
    Aggregates existing operational events.

    It does not regenerate or duplicate sales. Sales, stockout, order,
    receipt and inventory files are the system of record.
    """

    @staticmethod
    def _sum(frame: pd.DataFrame, column: str) -> float:
        if frame.empty or column not in frame.columns:
            return 0.0
        return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())

    def aggregate(
        self,
        sales: pd.DataFrame,
        stockouts: pd.DataFrame,
        receipts: pd.DataFrame,
        products: pd.DataFrame,
        inventory_daily: pd.DataFrame,
        stores: pd.DataFrame,
        days: int,
    ) -> FinancialKpis:
        if days <= 0:
            raise FinancialEngineV2Error("days must be greater than zero.")
        if sales.empty:
            raise FinancialEngineV2Error("Sales events are required.")
        if products.empty:
            raise FinancialEngineV2Error("Product master is required.")
        if stores.empty:
            raise FinancialEngineV2Error("Store master is required.")

        realized_revenue = self._sum(sales, "realized_revenue")
        lost_revenue = self._sum(sales, "lost_revenue")
        cogs = self._sum(sales, "cost_of_goods_sold")
        gross_margin = realized_revenue - cogs

        stockout_penalty = self._sum(stockouts, "penalty_cost")
        procurement_cost = self._sum(receipts, "procurement_cost")
        logistics_cost = self._sum(receipts, "logistics_cost")

        product_cost = products.set_index("sku_id")["unit_cost"].to_dict()
        holding_rate = products.set_index("sku_id")[
            "holding_cost_per_unit_day"
        ].to_dict()

        average_inventory_value = 0.0
        holding_cost = 0.0

        if not inventory_daily.empty:
            required = {"sku_id", "on_hand"}
            if not required.issubset(inventory_daily.columns):
                raise FinancialEngineV2Error(
                    "Inventory history must contain sku_id and on_hand."
                )

            inventory_daily = inventory_daily.copy()
            inventory_daily["unit_cost"] = inventory_daily["sku_id"].map(
                product_cost
            ).fillna(0.0)
            inventory_daily["holding_rate"] = inventory_daily["sku_id"].map(
                holding_rate
            ).fillna(0.0)

            inventory_daily["inventory_value"] = (
                inventory_daily["on_hand"] * inventory_daily["unit_cost"]
            )
            inventory_daily["holding_cost"] = (
                inventory_daily["on_hand"] * inventory_daily["holding_rate"]
            )

            if "simulation_day" in inventory_daily.columns:
                daily_value = (
                    inventory_daily.groupby("simulation_day")["inventory_value"]
                    .sum()
                )
                average_inventory_value = float(daily_value.mean())
            else:
                average_inventory_value = float(
                    inventory_daily["inventory_value"].sum()
                )

            holding_cost = float(inventory_daily["holding_cost"].sum())

        operating_cost_per_day = self._sum(
            stores,
            "operating_cost_per_day",
        )
        operating_cost = operating_cost_per_day * days

        requested_units = self._sum(sales, "requested_units")
        sold_units = self._sum(sales, "sold_units")
        fill_rate = (
            sold_units / requested_units if requested_units > 0 else 1.0
        )

        inventory_turnover = (
            cogs / average_inventory_value
            if average_inventory_value > 0
            else 0.0
        )
        gmroi = (
            gross_margin / average_inventory_value
            if average_inventory_value > 0
            else 0.0
        )

        net_operating_profit = (
            gross_margin
            - stockout_penalty
            - logistics_cost
            - holding_cost
            - operating_cost
        )

        return FinancialKpis(
            realized_revenue=round(realized_revenue, 2),
            lost_revenue=round(lost_revenue, 2),
            cost_of_goods_sold=round(cogs, 2),
            gross_margin=round(gross_margin, 2),
            stockout_penalty_cost=round(stockout_penalty, 2),
            procurement_cost=round(procurement_cost, 2),
            logistics_cost=round(logistics_cost, 2),
            holding_cost=round(holding_cost, 2),
            operating_cost=round(operating_cost, 2),
            net_operating_profit=round(net_operating_profit, 2),
            average_inventory_value=round(average_inventory_value, 2),
            inventory_turnover=round(inventory_turnover, 6),
            gmroi=round(gmroi, 6),
            fill_rate=round(fill_rate, 6),
        )
