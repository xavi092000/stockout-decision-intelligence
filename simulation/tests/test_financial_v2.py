from __future__ import annotations

import unittest

import pandas as pd

from simulation.engines.financial_v2 import FinancialEngineV2


class FinancialEngineTests(unittest.TestCase):
    def test_revenue_is_aggregated_not_recomputed(self) -> None:
        sales = pd.DataFrame([
            {
                "requested_units": 2,
                "sold_units": 2,
                "realized_revenue": 20.0,
                "lost_revenue": 0.0,
                "cost_of_goods_sold": 12.0,
            }
        ])
        products = pd.DataFrame([
            {
                "sku_id": "SKU-1",
                "unit_cost": 6.0,
                "holding_cost_per_unit_day": 0.01,
            }
        ])
        stores = pd.DataFrame([
            {
                "store_id": "STORE-1",
                "operating_cost_per_day": 1.0,
            }
        ])
        inventory = pd.DataFrame([
            {
                "simulation_day": 1,
                "sku_id": "SKU-1",
                "on_hand": 10,
            }
        ])

        kpis = FinancialEngineV2().aggregate(
            sales=sales,
            stockouts=pd.DataFrame(),
            receipts=pd.DataFrame(),
            products=products,
            inventory_daily=inventory,
            stores=stores,
            days=1,
        )

        self.assertEqual(kpis.realized_revenue, 20.0)
        self.assertEqual(kpis.cost_of_goods_sold, 12.0)
        self.assertEqual(kpis.gross_margin, 8.0)


if __name__ == "__main__":
    unittest.main()
