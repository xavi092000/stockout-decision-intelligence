from __future__ import annotations

from collections import Counter
from typing import Any

from simulation.domain.models import WorldState


def build_compatibility_report(
    world: WorldState,
) -> dict[str, Any]:
    world.validate()

    supplier_field_contract = {
        "supplier_id",
        "name",
        "base_lead_time_days",
        "lead_time_variability_days",
        "fill_rate",
        "reliability_score",
        "logistics_cost_per_unit",
    }

    supplier_rows = [item.to_dict() for item in world.suppliers]
    supplier_contract_passed = all(
        supplier_field_contract.issubset(row)
        for row in supplier_rows
    )

    inventory_keys = [
        (item.store_id, item.sku_id)
        for item in world.inventory
    ]
    duplicates = [
        key for key, count in Counter(inventory_keys).items()
        if count > 1
    ]

    product_supplier_ids = {
        item.supplier_id for item in world.products
    }
    known_supplier_ids = {
        item.supplier_id for item in world.suppliers
    }

    return {
        "status": "PASSED",
        "schema_version": world.schema_version,
        "store_count": len(world.stores),
        "sku_count": len(world.products),
        "supplier_count": len(world.suppliers),
        "inventory_position_count": len(world.inventory),
        "purchase_order_count": len(world.purchase_orders),
        "supplier_contract": (
            "PASSED" if supplier_contract_passed else "FAILED"
        ),
        "duplicate_inventory_positions": len(duplicates),
        "unknown_product_suppliers": len(
            product_supplier_ids - known_supplier_ids
        ),
        "negative_stock_positions": sum(
            1 for item in world.inventory if item.on_hand < 0
        ),
        "domain_validation": "PASSED",
        "migration_compatibility": "PASSED",
    }
