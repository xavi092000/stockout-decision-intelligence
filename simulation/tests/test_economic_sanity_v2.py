from __future__ import annotations

import unittest

from simulation.engines.economic_sanity_v2 import (
    EconomicSanityEngineV2,
)


class EconomicSanityTests(unittest.TestCase):
    def test_recalibration_uses_existing_revenue(self) -> None:
        report = EconomicSanityEngineV2().evaluate(
            financial_kpis={
                "realized_revenue": 100000.0,
                "cost_of_goods_sold": 60000.0,
                "average_inventory_value": 200000.0,
                "logistics_cost": 1000.0,
                "procurement_cost": 50000.0,
                "stockout_penalty_cost": 100.0,
            },
            sold_units=5000,
        )

        self.assertEqual(report.realized_revenue, 100000.0)
        self.assertEqual(report.gross_margin, 40000.0)
        self.assertEqual(
            report.recalibrated_operating_cost,
            19750.0,
        )

    def test_sanity_ratios_pass_for_valid_case(self) -> None:
        report = EconomicSanityEngineV2().evaluate(
            financial_kpis={
                "realized_revenue": 200000.0,
                "cost_of_goods_sold": 130000.0,
                "average_inventory_value": 800000.0,
                "logistics_cost": 1500.0,
                "procurement_cost": 90000.0,
                "stockout_penalty_cost": 20.0,
            },
            sold_units=4500,
        )

        self.assertEqual(report.status, "PASSED")
        self.assertEqual(report.violations, [])


if __name__ == "__main__":
    unittest.main()
