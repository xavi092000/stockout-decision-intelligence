from __future__ import annotations

import unittest

from simulation.domain.models import (
    InventoryPosition,
    Product,
)
from simulation.engines.sales_v2 import SalesEvent


class SalesContractTests(unittest.TestCase):
    def test_stockout_math(self) -> None:
        position = InventoryPosition(
            store_id="STORE-001",
            sku_id="SKU-001",
            on_hand=3,
            reserved=0,
            in_transit=0,
            reorder_point=4,
            target_stock=10,
            safety_stock=2,
        )
        requested = 5
        sold = min(requested, position.available)
        lost = requested - sold

        self.assertEqual(sold, 3)
        self.assertEqual(lost, 2)

    def test_sales_event_financials(self) -> None:
        event = SalesEvent(
            sales_event_id="SALE-0001",
            simulation_day=1,
            date="2027-01-01",
            store_id="STORE-001",
            sku_id="SKU-001",
            requested_units=5,
            sold_units=3,
            lost_units=2,
            unit_price=10.0,
            unit_cost=6.0,
            realized_revenue=30.0,
            lost_revenue=20.0,
            cost_of_goods_sold=18.0,
            gross_margin=12.0,
            stock_before=3,
            stock_after=0,
            stockout_occurred=True,
        )
        self.assertEqual(event.realized_revenue, 30.0)
        self.assertEqual(event.gross_margin, 12.0)
        self.assertTrue(event.stockout_occurred)


if __name__ == "__main__":
    unittest.main()
