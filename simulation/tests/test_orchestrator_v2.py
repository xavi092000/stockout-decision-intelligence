from __future__ import annotations

import unittest

from simulation.engines.economic_sanity_v2 import (
    EconomicSanityEngineV2,
)


class OrchestratorContractTests(unittest.TestCase):
    def test_final_sanity_uses_existing_revenue(self) -> None:
        report = EconomicSanityEngineV2().evaluate(
            financial_kpis={
                "realized_revenue": 300000.0,
                "cost_of_goods_sold": 190000.0,
                "average_inventory_value": 700000.0,
                "logistics_cost": 2000.0,
                "procurement_cost": 120000.0,
                "stockout_penalty_cost": 20.0,
            },
            sold_units=6000,
        )

        self.assertEqual(report.realized_revenue, 300000.0)
        self.assertEqual(report.status, "PASSED")


if __name__ == "__main__":
    unittest.main()
