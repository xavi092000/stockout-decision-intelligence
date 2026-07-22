from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "2.0.0"


class DomainValidationError(ValueError):
    """Raised when a domain object violates a core invariant."""


@dataclass
class Supplier:
    supplier_id: str
    name: str
    base_lead_time_days: int
    lead_time_variability_days: int
    fill_rate: float
    reliability_score: float
    logistics_cost_per_unit: float

    def validate(self) -> None:
        if not self.supplier_id:
            raise DomainValidationError("supplier_id is required.")
        if self.base_lead_time_days < 1:
            raise DomainValidationError(
                "base_lead_time_days must be >= 1."
            )
        if self.lead_time_variability_days < 0:
            raise DomainValidationError(
                "lead_time_variability_days must be >= 0."
            )
        if not 0.0 < self.fill_rate <= 1.0:
            raise DomainValidationError(
                "fill_rate must be in (0, 1]."
            )
        if not 0.0 < self.reliability_score <= 1.0:
            raise DomainValidationError(
                "reliability_score must be in (0, 1]."
            )
        if self.logistics_cost_per_unit < 0:
            raise DomainValidationError(
                "logistics_cost_per_unit must be non-negative."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Store:
    store_id: str
    state_id: str
    name: str
    capacity_units: int
    operating_cost_per_day: float
    service_level_target: float

    def validate(self) -> None:
        if not self.store_id:
            raise DomainValidationError("store_id is required.")
        if self.capacity_units <= 0:
            raise DomainValidationError(
                "capacity_units must be positive."
            )
        if self.operating_cost_per_day < 0:
            raise DomainValidationError(
                "operating_cost_per_day must be non-negative."
            )
        if not 0.0 < self.service_level_target <= 1.0:
            raise DomainValidationError(
                "service_level_target must be in (0, 1]."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Product:
    sku_id: str
    category: str
    department: str
    supplier_id: str
    unit_cost: float
    unit_price: float
    holding_cost_per_unit_day: float
    stockout_penalty_per_unit: float
    shelf_life_days: int | None = None

    def validate(self) -> None:
        if not self.sku_id:
            raise DomainValidationError("sku_id is required.")
        if not self.supplier_id:
            raise DomainValidationError("supplier_id is required.")
        if self.unit_cost < 0:
            raise DomainValidationError(
                "unit_cost must be non-negative."
            )
        if self.unit_price < self.unit_cost:
            raise DomainValidationError(
                "unit_price must be >= unit_cost."
            )
        if self.holding_cost_per_unit_day < 0:
            raise DomainValidationError(
                "holding cost must be non-negative."
            )
        if self.stockout_penalty_per_unit < 0:
            raise DomainValidationError(
                "stockout penalty must be non-negative."
            )
        if self.shelf_life_days is not None and self.shelf_life_days <= 0:
            raise DomainValidationError(
                "shelf_life_days must be positive when provided."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InventoryPosition:
    store_id: str
    sku_id: str
    on_hand: int
    reserved: int
    in_transit: int
    reorder_point: int
    target_stock: int
    safety_stock: int
    last_updated_day: int = 0

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved)

    @property
    def inventory_position(self) -> int:
        return self.available + self.in_transit

    def validate(self) -> None:
        integer_fields = {
            "on_hand": self.on_hand,
            "reserved": self.reserved,
            "in_transit": self.in_transit,
            "reorder_point": self.reorder_point,
            "target_stock": self.target_stock,
            "safety_stock": self.safety_stock,
        }
        for name, value in integer_fields.items():
            if value < 0:
                raise DomainValidationError(
                    f"{name} must be non-negative."
                )
        if self.reserved > self.on_hand:
            raise DomainValidationError(
                "reserved stock cannot exceed on_hand."
            )
        if self.reorder_point < self.safety_stock:
            raise DomainValidationError(
                "reorder_point cannot be below safety_stock."
            )
        if self.target_stock < self.reorder_point:
            raise DomainValidationError(
                "target_stock cannot be below reorder_point."
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["available"] = self.available
        payload["inventory_position"] = self.inventory_position
        return payload


@dataclass
class PurchaseOrder:
    order_id: str
    store_id: str
    sku_id: str
    supplier_id: str
    order_day: int
    order_date: str
    ordered_units: int
    expected_units: int
    received_units: int
    expected_delivery_day: int
    expected_delivery_date: str
    status: str
    unit_cost: float
    logistics_cost_per_unit: float

    @property
    def open_units(self) -> int:
        return max(0, self.expected_units - self.received_units)

    def validate(self) -> None:
        if self.ordered_units <= 0:
            raise DomainValidationError(
                "ordered_units must be positive."
            )
        if self.expected_units <= 0:
            raise DomainValidationError(
                "expected_units must be positive."
            )
        if self.expected_units > self.ordered_units:
            raise DomainValidationError(
                "expected_units cannot exceed ordered_units."
            )
        if not 0 <= self.received_units <= self.expected_units:
            raise DomainValidationError(
                "received_units is inconsistent."
            )
        if self.expected_delivery_day < self.order_day:
            raise DomainValidationError(
                "delivery day cannot precede order day."
            )
        if self.status not in {
            "OPEN",
            "PARTIALLY_RECEIVED",
            "RECEIVED",
            "CANCELLED",
        }:
            raise DomainValidationError(
                f"Invalid purchase-order status: {self.status}"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["open_units"] = self.open_units
        return payload


@dataclass
class FinancialLedger:
    revenue: float = 0.0
    cost_of_goods_sold: float = 0.0
    holding_cost: float = 0.0
    stockout_cost: float = 0.0
    logistics_cost: float = 0.0
    procurement_cost: float = 0.0
    operating_cost: float = 0.0
    gross_profit: float = 0.0
    initial_inventory_value: float = 0.0

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if value < 0 and name != "gross_profit":
                raise DomainValidationError(
                    f"{name} must be non-negative."
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorldState:
    schema_version: str
    simulation_day: int
    current_date: str
    seed: int
    stores: list[Store]
    products: list[Product]
    suppliers: list[Supplier]
    inventory: list[InventoryPosition]
    purchase_orders: list[PurchaseOrder] = field(default_factory=list)
    financials: FinancialLedger = field(default_factory=FinancialLedger)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise DomainValidationError(
                f"Expected schema {SCHEMA_VERSION}, "
                f"got {self.schema_version}."
            )
        if self.simulation_day < 0:
            raise DomainValidationError(
                "simulation_day must be non-negative."
            )

        for collection in (
            self.stores,
            self.products,
            self.suppliers,
            self.inventory,
            self.purchase_orders,
        ):
            for item in collection:
                item.validate()

        self.financials.validate()

        store_ids = [item.store_id for item in self.stores]
        sku_ids = [item.sku_id for item in self.products]
        supplier_ids = [item.supplier_id for item in self.suppliers]

        if len(store_ids) != len(set(store_ids)):
            raise DomainValidationError("Duplicate store IDs.")
        if len(sku_ids) != len(set(sku_ids)):
            raise DomainValidationError("Duplicate SKU IDs.")
        if len(supplier_ids) != len(set(supplier_ids)):
            raise DomainValidationError("Duplicate supplier IDs.")

        supplier_set = set(supplier_ids)
        for product in self.products:
            if product.supplier_id not in supplier_set:
                raise DomainValidationError(
                    f"Unknown supplier for SKU {product.sku_id}."
                )

        store_set = set(store_ids)
        sku_set = set(sku_ids)
        position_keys: set[tuple[str, str]] = set()
        for position in self.inventory:
            key = (position.store_id, position.sku_id)
            if key in position_keys:
                raise DomainValidationError(
                    f"Duplicate inventory position {key}."
                )
            position_keys.add(key)
            if position.store_id not in store_set:
                raise DomainValidationError(
                    f"Unknown store in inventory: {position.store_id}."
                )
            if position.sku_id not in sku_set:
                raise DomainValidationError(
                    f"Unknown SKU in inventory: {position.sku_id}."
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "simulation_day": self.simulation_day,
            "current_date": self.current_date,
            "seed": self.seed,
            "stores": [item.to_dict() for item in self.stores],
            "products": [item.to_dict() for item in self.products],
            "suppliers": [item.to_dict() for item in self.suppliers],
            "inventory": [item.to_dict() for item in self.inventory],
            "purchase_orders": [
                item.to_dict() for item in self.purchase_orders
            ],
            "financials": self.financials.to_dict(),
            "metadata": self.metadata,
        }
