from __future__ import annotations

import unittest

from simulation.domain.models import (
    InventoryPosition,
    Product,
    Store,
    Supplier,
)


class SupplierInventoryContractTests(unittest.TestCase):
    def test_supplier_has_required_lead_time_fields(self) -> None:
        supplier = Supplier(
            supplier_id="SUP-001",
            name="Supplier",
            base_lead_time_days=4,
            lead_time_variability_days=2,
            fill_rate=0.95,
            reliability_score=0.97,
            logistics_cost_per_unit=0.25,
        )
        supplier.validate()

    def test_inventory_position_calculation(self) -> None:
        position = InventoryPosition(
            store_id="STORE-001",
            sku_id="SKU-001",
            on_hand=20,
            reserved=3,
            in_transit=5,
            reorder_point=12,
            target_stock=30,
            safety_stock=5,
        )
        self.assertEqual(position.available, 17)
        self.assertEqual(position.inventory_position, 22)
        position.validate()


if __name__ == "__main__":
    unittest.main()
