from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    simulation_name: str = "stockout_decision_simulator"
    number_of_days: int = 365
    number_of_products: int = 20
    number_of_stores: int = 5
    number_of_suppliers: int = 3
    random_seed: int = 42
    initial_inventory_days: int = 10

    def __post_init__(self) -> None:
        if not self.simulation_name.strip():
            raise ValueError("simulation_name cannot be empty.")

        if self.number_of_days <= 0:
            raise ValueError("number_of_days must be greater than zero.")

        if self.number_of_products <= 0:
            raise ValueError(
                "number_of_products must be greater than zero."
            )

        if self.number_of_stores <= 0:
            raise ValueError(
                "number_of_stores must be greater than zero."
            )

        if self.number_of_suppliers <= 0:
            raise ValueError(
                "number_of_suppliers must be greater than zero."
            )

        if self.random_seed < 0:
            raise ValueError("random_seed cannot be negative.")

        if self.initial_inventory_days <= 0:
            raise ValueError(
                "initial_inventory_days must be greater than zero."
            )

    @property
    def expected_daily_rows(self) -> int:
        return self.number_of_products * self.number_of_stores

    @property
    def expected_total_rows(self) -> int:
        return self.expected_daily_rows * self.number_of_days