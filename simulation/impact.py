from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Impact:
    """
    Represents one explainable multiplier applied to a business value.

    Examples:
    - weekday effect
    - promotion effect
    - weather effect
    - store traffic effect
    """

    name: str
    multiplier: float
    description: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Impact name cannot be empty.")

        if self.multiplier <= 0:
            raise ValueError(
                "Impact multiplier must be greater than zero."
            )

        if not self.description.strip():
            raise ValueError(
                "Impact description cannot be empty."
            )

        if not self.source.strip():
            raise ValueError("Impact source cannot be empty.")

    def apply(self, value: float) -> float:
        if value < 0:
            raise ValueError(
                "Impact cannot be applied to a negative value."
            )

        return value * self.multiplier

    def absolute_change(self, value: float) -> float:
        return self.apply(value) - value

    def percentage_change(self) -> float:
        return (self.multiplier - 1.0) * 100.0

    def summary(self) -> str:
        percentage = self.percentage_change()
        sign = "+" if percentage >= 0 else ""

        return (
            f"{self.name}: x{self.multiplier:.2f} "
            f"({sign}{percentage:.1f}%) — "
            f"{self.description}"
        )