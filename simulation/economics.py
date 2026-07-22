from __future__ import annotations

from dataclasses import dataclass

from simulation.action import ActionType
from simulation.decision_policy import DecisionResult
from simulation.state_transition import DailyTransitionOutcome


@dataclass(frozen=True)
class EconomicConfig:
    """
    Centralized MVP unit economics.

    These values can later be replaced by SKU-, store-, or supplier-
    specific parameters without changing the calculation engine.
    """

    selling_price_per_unit: float = 20.00

    normal_order_cost_per_unit: float = 8.00
    expedite_order_cost_per_unit: float = 12.00
    transfer_cost_per_unit: float = 2.00

    holding_cost_per_unit_per_day: float = 0.05
    lost_sale_cost_per_unit: float = 6.00
    stockout_penalty_per_event: float = 25.00

    def __post_init__(self) -> None:
        values = (
            self.selling_price_per_unit,
            self.normal_order_cost_per_unit,
            self.expedite_order_cost_per_unit,
            self.transfer_cost_per_unit,
            self.holding_cost_per_unit_per_day,
            self.lost_sale_cost_per_unit,
            self.stockout_penalty_per_event,
        )

        if any(value < 0 for value in values):
            raise ValueError(
                "Economic configuration values cannot be negative."
            )
        if self.selling_price_per_unit <= 0:
            raise ValueError(
                "selling_price_per_unit must be greater than zero."
            )
        if (
            self.expedite_order_cost_per_unit
            < self.normal_order_cost_per_unit
        ):
            raise ValueError(
                "Expedited ordering cannot be cheaper than normal ordering."
            )


@dataclass(frozen=True)
class DailyEconomicOutcome:
    revenue: float

    normal_order_cost: float
    expedite_order_cost: float
    transfer_cost: float
    holding_cost: float

    lost_sales_cost: float
    stockout_penalty: float

    fulfilled_units: int
    unmet_units: int
    ending_stock_units: int
    stockout_events: int

    normal_order_units: int
    expedite_order_units: int
    transferred_units: int


    @property
    def service_level(self) -> float:
        demand = self.fulfilled_units + self.unmet_units
        if demand == 0:
            return 1.0
        return self.fulfilled_units / demand

    @property
    def total_operating_cost(self) -> float:
        return (
            self.normal_order_cost
            + self.expedite_order_cost
            + self.transfer_cost
            + self.holding_cost
        )

    @property
    def total_service_failure_cost(self) -> float:
        return self.lost_sales_cost + self.stockout_penalty

    @property
    def total_cost(self) -> float:
        return (
            self.total_operating_cost
            + self.total_service_failure_cost
        )

    @property
    def business_value(self) -> float:
        return self.revenue - self.total_cost


@dataclass
class CumulativeEconomicOutcome:
    revenue: float = 0.0

    normal_order_cost: float = 0.0
    expedite_order_cost: float = 0.0
    transfer_cost: float = 0.0
    holding_cost: float = 0.0

    lost_sales_cost: float = 0.0
    stockout_penalty: float = 0.0

    fulfilled_units: int = 0
    unmet_units: int = 0
    ending_stock_unit_days: int = 0
    stockout_events: int = 0

    normal_order_units: int = 0
    expedite_order_units: int = 0
    transferred_units: int = 0

    def add(self, outcome: DailyEconomicOutcome) -> None:
        self.revenue += outcome.revenue

        self.normal_order_cost += outcome.normal_order_cost
        self.expedite_order_cost += outcome.expedite_order_cost
        self.transfer_cost += outcome.transfer_cost
        self.holding_cost += outcome.holding_cost

        self.lost_sales_cost += outcome.lost_sales_cost
        self.stockout_penalty += outcome.stockout_penalty

        self.fulfilled_units += outcome.fulfilled_units
        self.unmet_units += outcome.unmet_units
        self.ending_stock_unit_days += outcome.ending_stock_units
        self.stockout_events += outcome.stockout_events

        self.normal_order_units += outcome.normal_order_units
        self.expedite_order_units += outcome.expedite_order_units
        self.transferred_units += outcome.transferred_units

    @property
    def service_level(self) -> float:
        demand = self.fulfilled_units + self.unmet_units
        if demand == 0:
            return 1.0
        return self.fulfilled_units / demand

    @property
    def total_operating_cost(self) -> float:
        return (
            self.normal_order_cost
            + self.expedite_order_cost
            + self.transfer_cost
            + self.holding_cost
        )

    @property
    def total_service_failure_cost(self) -> float:
        return self.lost_sales_cost + self.stockout_penalty

    @property
    def total_cost(self) -> float:
        return (
            self.total_operating_cost
            + self.total_service_failure_cost
        )

    @property
    def business_value(self) -> float:
        return self.revenue - self.total_cost

    def summary(self) -> str:
        return (
            "ECONOMIC PERFORMANCE\n"
            "====================\n"
            f"Revenue                 : ${self.revenue:,.2f}\n"
            f"Normal Ordering Cost    : ${self.normal_order_cost:,.2f}\n"
            f"Expedite Ordering Cost  : ${self.expedite_order_cost:,.2f}\n"
            f"Transfer Cost           : ${self.transfer_cost:,.2f}\n"
            f"Holding Cost            : ${self.holding_cost:,.2f}\n"
            f"Lost Sales Cost         : ${self.lost_sales_cost:,.2f}\n"
            f"Stockout Penalty        : ${self.stockout_penalty:,.2f}\n"
            f"Total Operating Cost    : ${self.total_operating_cost:,.2f}\n"
            f"Service Failure Cost    : ${self.total_service_failure_cost:,.2f}\n"
            f"Total Cost              : ${self.total_cost:,.2f}\n"
            f"Net Business Value      : ${self.business_value:,.2f}\n"
            "\nECONOMIC VOLUMES\n"
            "----------------\n"
            f"Normal Order Units      : {self.normal_order_units:,}\n"
            f"Expedite Order Units    : {self.expedite_order_units:,}\n"
            f"Transferred Units       : {self.transferred_units:,}\n"
            f"Ending Stock Unit-Days  : {self.ending_stock_unit_days:,}"
        )


class EconomicEngine:
    """
    Evaluate economic consequences only after actions are frozen and
    realized demand has been generated.

    This component never participates in action selection, preventing
    future outcomes from leaking into daily decisions.
    """

    def __init__(
        self,
        config: EconomicConfig | None = None,
    ) -> None:
        self.config = config or EconomicConfig()

    def evaluate_day(
        self,
        decisions: list[DecisionResult],
        outcome: DailyTransitionOutcome,
    ) -> DailyEconomicOutcome:
        normal_order_units = 0
        expedite_order_units = 0
        transferred_units = 0

        for decision in decisions:
            action = decision.action

            if action.action_type == ActionType.ORDER_NORMAL:
                normal_order_units += action.quantity
            elif action.action_type == ActionType.ORDER_EXPEDITE:
                expedite_order_units += action.quantity
            elif action.action_type == ActionType.TRANSFER_STOCK:
                transferred_units += action.quantity

        ending_stock_units = sum(
            transition.ending_stock
            for transition in outcome.transitions
        )

        revenue = (
            outcome.fulfilled_demand
            * self.config.selling_price_per_unit
        )
        normal_order_cost = (
            normal_order_units
            * self.config.normal_order_cost_per_unit
        )
        expedite_order_cost = (
            expedite_order_units
            * self.config.expedite_order_cost_per_unit
        )
        transfer_cost = (
            transferred_units
            * self.config.transfer_cost_per_unit
        )
        holding_cost = (
            ending_stock_units
            * self.config.holding_cost_per_unit_per_day
        )
        lost_sales_cost = (
            outcome.unmet_demand
            * self.config.lost_sale_cost_per_unit
        )
        stockout_penalty = (
            outcome.stockout_count
            * self.config.stockout_penalty_per_event
        )

        return DailyEconomicOutcome(
            revenue=revenue,
            normal_order_cost=normal_order_cost,
            expedite_order_cost=expedite_order_cost,
            transfer_cost=transfer_cost,
            holding_cost=holding_cost,
            lost_sales_cost=lost_sales_cost,
            stockout_penalty=stockout_penalty,
            fulfilled_units=outcome.fulfilled_demand,
            unmet_units=outcome.unmet_demand,
            ending_stock_units=ending_stock_units,
            stockout_events=outcome.stockout_count,
            normal_order_units=normal_order_units,
            expedite_order_units=expedite_order_units,
            transferred_units=transferred_units,
        )
