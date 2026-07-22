from __future__ import annotations

"""
Benchmark runner for the Stockout Decision Intelligence Platform.

This file compares:
- DO_NOTHING baseline
- RuleBasedDecisionPolicy

using the exact same SimulationConfig and random seed.
"""

from simulation.action import ActionType, InventoryAction
from simulation.config import SimulationConfig
from simulation.decision_policy import DecisionResult, RuleBasedDecisionPolicy
from simulation.engine import SimulationEngine


class DoNothingDecisionPolicy:
    def decide(self, **kwargs):
        inventory = kwargs["inventory"]
        forecast = kwargs["forecast"]

        return DecisionResult(
            action=InventoryAction(
                action_type=ActionType.DO_NOTHING,
                destination_store_id=inventory.store_id,
                sku_id=inventory.sku_id,
                quantity=0,
            ),
            reason="Benchmark baseline",
            forecast_daily_demand=forecast.forecast_daily_demand,
            forecast_next_3d=forecast.forecast_next_3d,
            projected_stock_gap=0,
        )


def run_policy(name, policy):
    engine = SimulationEngine(config=SimulationConfig())
    engine.initialize()
    engine.decision_policy = policy
    engine.run(verbose=False)

    econ = engine.cumulative_economics

    return {
        "name": name,
        "service_level": engine.cumulative_service_level,
        "business_value": econ.business_value,
        "revenue": econ.revenue,
        "total_cost": econ.total_cost,
        "stockouts": engine.cumulative_stockouts,
        "unmet": engine.cumulative_unmet_demand,
    }


def main():
    baseline = run_policy("DO_NOTHING", DoNothingDecisionPolicy())
    challenger = run_policy("RULE_BASED", RuleBasedDecisionPolicy())

    print("=" * 60)
    print("STOCKOUT POLICY BENCHMARK")
    print("=" * 60)

    for result in (baseline, challenger):
        print()
        print(result["name"])
        print("-" * len(result["name"]))
        print(f"Service Level : {result['service_level']:.2%}")
        print(f"Business Value: ${result['business_value']:,.2f}")
        print(f"Revenue       : ${result['revenue']:,.2f}")
        print(f"Total Cost    : ${result['total_cost']:,.2f}")
        print(f"Stockouts     : {result['stockouts']:,}")
        print(f"Unmet Demand  : {result['unmet']:,}")

    print()
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(
        f"Incremental Business Value : "
        f"${challenger['business_value']-baseline['business_value']:,.2f}"
    )
    print(
        f"Service Level Gain         : "
        f"{challenger['service_level']-baseline['service_level']:+.2%}"
    )


if __name__ == "__main__":
    main()
