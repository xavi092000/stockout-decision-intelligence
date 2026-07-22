from __future__ import annotations

import unittest

from simulation.domain.models import (
    DomainValidationError,
    InventoryPosition,
    Supplier,
)


class DomainContractTests(unittest.TestCase):
    def test_supplier_contract_accepts_valid_supplier(self) -> None:
        supplier = Supplier(
            supplier_id="SUP-001",
            name="Supplier",
            base_lead_time_days=5,
            lead_time_variability_days=2,
            fill_rate=0.95,
            reliability_score=0.96,
            logistics_cost_per_unit=0.4,
        )
        supplier.validate()

    def test_supplier_contract_rejects_missing_lead_time(self) -> None:
        supplier = Supplier(
            supplier_id="SUP-001",
            name="Supplier",
            base_lead_time_days=0,
            lead_time_variability_days=2,
            fill_rate=0.95,
            reliability_score=0.96,
            logistics_cost_per_unit=0.4,
        )
        with self.assertRaises(DomainValidationError):
            supplier.validate()

    def test_inventory_contract_rejects_negative_stock(self) -> None:
        position = InventoryPosition(
            store_id="STORE-001",
            sku_id="SKU-001",
            on_hand=-1,
            reserved=0,
            in_transit=0,
            reorder_point=10,
            target_stock=20,
            safety_stock=5,
        )
        with self.assertRaises(DomainValidationError):
            position.validate()


if __name__ == "__main__":
    unittest.main()
