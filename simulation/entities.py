from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    sku_id: str
    name: str
    category: str
    unit_cost: float
    unit_price: float
    base_daily_demand: float
    safety_stock: int
    reorder_point: int
    supplier_id: str

    def __post_init__(self) -> None:
        if not self.sku_id:
            raise ValueError("sku_id cannot be empty.")
        if not self.name:
            raise ValueError("name cannot be empty.")
        if not self.category:
            raise ValueError("category cannot be empty.")
        if self.unit_cost < 0:
            raise ValueError("unit_cost cannot be negative.")
        if self.unit_price < 0:
            raise ValueError("unit_price cannot be negative.")
        if self.unit_price < self.unit_cost:
            raise ValueError("unit_price cannot be lower than unit_cost.")
        if self.base_daily_demand < 0:
            raise ValueError("base_daily_demand cannot be negative.")
        if self.safety_stock < 0:
            raise ValueError("safety_stock cannot be negative.")
        if self.reorder_point < self.safety_stock:
            raise ValueError(
                "reorder_point must be greater than or equal to safety_stock."
            )
        if not self.supplier_id:
            raise ValueError("supplier_id cannot be empty.")


@dataclass(frozen=True)
class Store:
    store_id: str
    name: str
    region: str
    capacity: int
    traffic_multiplier: float

    def __post_init__(self) -> None:
        if not self.store_id:
            raise ValueError("store_id cannot be empty.")
        if not self.name:
            raise ValueError("name cannot be empty.")
        if not self.region:
            raise ValueError("region cannot be empty.")
        if self.capacity <= 0:
            raise ValueError("capacity must be greater than zero.")
        if self.traffic_multiplier <= 0:
            raise ValueError("traffic_multiplier must be greater than zero.")


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    lead_time_days: int
    delay_probability: float
    reliability_score: float

    def __post_init__(self) -> None:
        if not self.supplier_id:
            raise ValueError("supplier_id cannot be empty.")
        if not self.name:
            raise ValueError("name cannot be empty.")
        if self.lead_time_days <= 0:
            raise ValueError("lead_time_days must be greater than zero.")
        if not 0.0 <= self.delay_probability <= 1.0:
            raise ValueError(
                "delay_probability must be between 0 and 1."
            )
        if not 0.0 <= self.reliability_score <= 1.0:
            raise ValueError(
                "reliability_score must be between 0 and 1."
            )


@dataclass
class Inventory:
    store_id: str
    sku_id: str
    stock_level: int
    reserved_stock: int = 0
    incoming_stock: int = 0

    def __post_init__(self) -> None:
        if not self.store_id:
            raise ValueError("store_id cannot be empty.")
        if not self.sku_id:
            raise ValueError("sku_id cannot be empty.")
        if self.stock_level < 0:
            raise ValueError("stock_level cannot be negative.")
        if self.reserved_stock < 0:
            raise ValueError("reserved_stock cannot be negative.")
        if self.incoming_stock < 0:
            raise ValueError("incoming_stock cannot be negative.")
        if self.reserved_stock > self.stock_level:
            raise ValueError(
                "reserved_stock cannot exceed stock_level."
            )

    @property
    def available_stock(self) -> int:
        return self.stock_level - self.reserved_stock