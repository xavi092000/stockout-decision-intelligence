from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class EconomicSanityError(RuntimeError):
    """Raised when financial assumptions or outputs are implausible."""


@dataclass(frozen=True)
class EconomicAssumptions:
    fixed_operating_cost_share_of_revenue: float = 0.18
    variable_operating_cost_per_unit: float = 0.35
    target_holding_cost_share_of_inventory: float = 0.03
    minimum_gross_margin_rate: float = 0.10
    maximum_operating_cost_share_of_revenue: float = 0.45
    maximum_holding_cost_share_of_inventory: float = 0.08
    maximum_logistics_share_of_procurement: float = 0.15

    def validate(self) -> None:
        values = asdict(self)
        for name, value in values.items():
            if value < 0:
                raise EconomicSanityError(
                    f"{name} must be non-negative."
                )
        if self.fixed_operating_cost_share_of_revenue > 1:
            raise EconomicSanityError(
                "Fixed operating cost share cannot exceed 100%."
            )
        if self.maximum_operating_cost_share_of_revenue > 1:
            raise EconomicSanityError(
                "Maximum operating cost share cannot exceed 100%."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EconomicSanityReport:
    realized_revenue: float
    gross_margin: float
    recalibrated_operating_cost: float
    recalibrated_holding_cost: float
    logistics_cost: float
    procurement_cost: float
    stockout_penalty_cost: float
    calibrated_net_operating_profit: float
    gross_margin_rate: float
    operating_cost_share_of_revenue: float
    holding_cost_share_of_inventory: float
    logistics_share_of_procurement: float
    inventory_turnover: float
    gmroi: float
    status: str
    violations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EconomicSanityEngineV2:
    def __init__(
        self,
        assumptions: EconomicAssumptions | None = None,
    ) -> None:
        self.assumptions = assumptions or EconomicAssumptions()
        self.assumptions.validate()

    def evaluate(
        self,
        financial_kpis: dict[str, float],
        sold_units: int,
    ) -> EconomicSanityReport:
        revenue = float(financial_kpis["realized_revenue"])
        cogs = float(financial_kpis["cost_of_goods_sold"])
        gross_margin = revenue - cogs
        inventory_value = max(
            0.0,
            float(financial_kpis["average_inventory_value"]),
        )
        logistics_cost = max(
            0.0,
            float(financial_kpis["logistics_cost"]),
        )
        procurement_cost = max(
            0.0,
            float(financial_kpis["procurement_cost"]),
        )
        stockout_cost = max(
            0.0,
            float(financial_kpis["stockout_penalty_cost"]),
        )

        fixed_operating_cost = (
            revenue
            * self.assumptions.fixed_operating_cost_share_of_revenue
        )
        variable_operating_cost = (
            max(0, int(sold_units))
            * self.assumptions.variable_operating_cost_per_unit
        )
        recalibrated_operating_cost = (
            fixed_operating_cost + variable_operating_cost
        )

        recalibrated_holding_cost = (
            inventory_value
            * self.assumptions.target_holding_cost_share_of_inventory
        )

        calibrated_profit = (
            gross_margin
            - recalibrated_operating_cost
            - recalibrated_holding_cost
            - logistics_cost
            - stockout_cost
        )

        gross_margin_rate = (
            gross_margin / revenue if revenue > 0 else 0.0
        )
        operating_share = (
            recalibrated_operating_cost / revenue
            if revenue > 0 else 0.0
        )
        holding_share = (
            recalibrated_holding_cost / inventory_value
            if inventory_value > 0 else 0.0
        )
        logistics_share = (
            logistics_cost / procurement_cost
            if procurement_cost > 0 else 0.0
        )
        inventory_turnover = (
            cogs / inventory_value if inventory_value > 0 else 0.0
        )
        gmroi = (
            gross_margin / inventory_value
            if inventory_value > 0 else 0.0
        )

        violations: list[str] = []

        if gross_margin_rate < self.assumptions.minimum_gross_margin_rate:
            violations.append("gross_margin_rate_below_minimum")
        if (
            operating_share
            > self.assumptions.maximum_operating_cost_share_of_revenue
        ):
            violations.append(
                "operating_cost_share_above_maximum"
            )
        if (
            holding_share
            > self.assumptions.maximum_holding_cost_share_of_inventory
        ):
            violations.append(
                "holding_cost_share_above_maximum"
            )
        if (
            logistics_share
            > self.assumptions.maximum_logistics_share_of_procurement
        ):
            violations.append(
                "logistics_share_above_maximum"
            )

        return EconomicSanityReport(
            realized_revenue=round(revenue, 2),
            gross_margin=round(gross_margin, 2),
            recalibrated_operating_cost=round(
                recalibrated_operating_cost,
                2,
            ),
            recalibrated_holding_cost=round(
                recalibrated_holding_cost,
                2,
            ),
            logistics_cost=round(logistics_cost, 2),
            procurement_cost=round(procurement_cost, 2),
            stockout_penalty_cost=round(stockout_cost, 2),
            calibrated_net_operating_profit=round(
                calibrated_profit,
                2,
            ),
            gross_margin_rate=round(gross_margin_rate, 6),
            operating_cost_share_of_revenue=round(
                operating_share,
                6,
            ),
            holding_cost_share_of_inventory=round(
                holding_share,
                6,
            ),
            logistics_share_of_procurement=round(
                logistics_share,
                6,
            ),
            inventory_turnover=round(
                inventory_turnover,
                6,
            ),
            gmroi=round(gmroi, 6),
            status="PASSED" if not violations else "FAILED",
            violations=violations,
        )
