from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from simulation.config import SimulationConfig
from simulation.entities import Inventory, Product, Store, Supplier


@dataclass
class SimulationWorld:
    config: SimulationConfig
    products: list[Product] = field(default_factory=list)
    stores: list[Store] = field(default_factory=list)
    suppliers: list[Supplier] = field(default_factory=list)
    inventories: list[Inventory] = field(default_factory=list)

    def initialize(self) -> None:
        """
        Create the complete initial simulation world.

        This method is deterministic when the same random seed is used.
        """
        self._reset()
        rng = Random(self.config.random_seed)

        self.suppliers = self._create_suppliers(rng)
        self.products = self._create_products(rng)
        self.stores = self._create_stores(rng)
        self.inventories = self._create_inventories(rng)

        self._validate_world()

    def _reset(self) -> None:
        self.products.clear()
        self.stores.clear()
        self.suppliers.clear()
        self.inventories.clear()

    def _create_suppliers(self, rng: Random) -> list[Supplier]:
        suppliers: list[Supplier] = []

        for index in range(1, self.config.number_of_suppliers + 1):
            lead_time_days = rng.randint(2, 6)
            delay_probability = round(rng.uniform(0.04, 0.18), 3)
            reliability_score = round(1.0 - delay_probability, 3)

            suppliers.append(
                Supplier(
                    supplier_id=f"SUP_{index:03d}",
                    name=f"Supplier {index}",
                    lead_time_days=lead_time_days,
                    delay_probability=delay_probability,
                    reliability_score=reliability_score,
                )
            )

        return suppliers

    def _create_products(self, rng: Random) -> list[Product]:
        categories = (
            "beverages",
            "dairy",
            "frozen",
            "snacks",
            "household",
        )

        supplier_ids = [
            supplier.supplier_id
            for supplier in self.suppliers
        ]

        products: list[Product] = []

        for index in range(1, self.config.number_of_products + 1):
            base_daily_demand = round(rng.uniform(6.0, 30.0), 2)
            safety_stock = max(
                1,
                round(base_daily_demand * rng.uniform(1.5, 3.0)),
            )
            reorder_point = safety_stock + round(
                base_daily_demand * rng.uniform(1.0, 2.5)
            )

            unit_cost = round(rng.uniform(1.0, 20.0), 2)
            markup_multiplier = rng.uniform(1.25, 2.2)
            unit_price = round(unit_cost * markup_multiplier, 2)

            products.append(
                Product(
                    sku_id=f"SKU_{index:03d}",
                    name=f"Product {index}",
                    category=rng.choice(categories),
                    unit_cost=unit_cost,
                    unit_price=unit_price,
                    base_daily_demand=base_daily_demand,
                    safety_stock=safety_stock,
                    reorder_point=reorder_point,
                    supplier_id=rng.choice(supplier_ids),
                )
            )

        return products

    def _create_stores(self, rng: Random) -> list[Store]:
        regions = (
            "Montreal",
            "Laval",
            "Quebec",
            "Sherbrooke",
            "Gatineau",
        )

        stores: list[Store] = []

        for index in range(1, self.config.number_of_stores + 1):
            stores.append(
                Store(
                    store_id=f"STORE_{index:03d}",
                    name=f"Store {index}",
                    region=regions[(index - 1) % len(regions)],
                    capacity=rng.randint(6_000, 15_000),
                    traffic_multiplier=round(
                        rng.uniform(0.75, 1.45),
                        2,
                    ),
                )
            )

        return stores

    def _create_inventories(self, rng: Random) -> list[Inventory]:
        inventories: list[Inventory] = []

        for store in self.stores:
            for product in self.products:
                average_daily_demand = (
                    product.base_daily_demand
                    * store.traffic_multiplier
                )

                target_stock = round(
                    average_daily_demand
                    * self.config.initial_inventory_days
                )

                stock_level = max(
                    product.safety_stock,
                    round(target_stock * rng.uniform(0.8, 1.2)),
                )

                inventories.append(
                    Inventory(
                        store_id=store.store_id,
                        sku_id=product.sku_id,
                        stock_level=stock_level,
                    )
                )

        return inventories

    def _validate_world(self) -> None:
        expected_inventories = (
            self.config.number_of_products
            * self.config.number_of_stores
        )

        if len(self.products) != self.config.number_of_products:
            raise RuntimeError(
                "Product initialization count does not match the config."
            )

        if len(self.stores) != self.config.number_of_stores:
            raise RuntimeError(
                "Store initialization count does not match the config."
            )

        if len(self.suppliers) != self.config.number_of_suppliers:
            raise RuntimeError(
                "Supplier initialization count does not match the config."
            )

        if len(self.inventories) != expected_inventories:
            raise RuntimeError(
                "Inventory initialization count does not match the "
                "product-store combinations."
            )

        inventory_keys = {
            (inventory.store_id, inventory.sku_id)
            for inventory in self.inventories
        }

        if len(inventory_keys) != expected_inventories:
            raise RuntimeError(
                "Duplicate store-SKU inventory combinations detected."
            )

    def summary(self) -> str:
        return (
            "Simulation World Initialized\n"
            f"Products      : {len(self.products)}\n"
            f"Stores        : {len(self.stores)}\n"
            f"Suppliers     : {len(self.suppliers)}\n"
            f"Inventories   : {len(self.inventories)}"
        )


def main() -> None:
    config = SimulationConfig()
    world = SimulationWorld(config=config)
    world.initialize()

    print(world.summary())


if __name__ == "__main__":
    main()