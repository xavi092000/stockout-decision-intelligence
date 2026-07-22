from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    DO_NOTHING = "DO_NOTHING"
    TRANSFER_STOCK = "TRANSFER_STOCK"
    ORDER_NORMAL = "ORDER_NORMAL"
    ORDER_EXPEDITE = "ORDER_EXPEDITE"


@dataclass(frozen=True)
class InventoryAction:
    action_type: ActionType
    destination_store_id: str
    sku_id: str
    quantity: int = 0
    source_store_id: str | None = None

    def __post_init__(self) -> None:
        if not self.destination_store_id.strip():
            raise ValueError(
                "destination_store_id cannot be empty."
            )

        if not self.sku_id.strip():
            raise ValueError("sku_id cannot be empty.")

        if self.quantity < 0:
            raise ValueError("quantity cannot be negative.")

        if self.action_type == ActionType.DO_NOTHING:
            if self.quantity != 0:
                raise ValueError(
                    "DO_NOTHING must have quantity=0."
                )

            if self.source_store_id is not None:
                raise ValueError(
                    "DO_NOTHING cannot have a source_store_id."
                )

        if self.action_type == ActionType.TRANSFER_STOCK:
            if not self.source_store_id:
                raise ValueError(
                    "TRANSFER_STOCK requires source_store_id."
                )

            if self.source_store_id == self.destination_store_id:
                raise ValueError(
                    "Transfer source and destination must differ."
                )

            if self.quantity <= 0:
                raise ValueError(
                    "TRANSFER_STOCK requires quantity > 0."
                )

        if self.action_type in {
            ActionType.ORDER_NORMAL,
            ActionType.ORDER_EXPEDITE,
        }:
            if self.source_store_id is not None:
                raise ValueError(
                    "Supplier orders cannot have source_store_id."
                )

            if self.quantity <= 0:
                raise ValueError(
                    "Supplier orders require quantity > 0."
                )