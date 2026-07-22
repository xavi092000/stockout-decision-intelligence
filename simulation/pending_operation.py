from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PendingOperationType(str, Enum):
    TRANSFER = "TRANSFER"
    NORMAL_ORDER = "NORMAL_ORDER"
    EXPEDITE_ORDER = "EXPEDITE_ORDER"


class PendingOperationStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class PendingOperation:
    operation_id: str
    operation_type: PendingOperationType
    sku_id: str
    destination_store_id: str
    quantity: int
    created_day: int
    arrival_day: int
    source_store_id: str | None = None
    supplier_id: str | None = None
    status: PendingOperationStatus = PendingOperationStatus.PENDING

    def __post_init__(self) -> None:
        if not self.operation_id.strip():
            raise ValueError("operation_id cannot be empty.")

        if not self.sku_id.strip():
            raise ValueError("sku_id cannot be empty.")

        if not self.destination_store_id.strip():
            raise ValueError(
                "destination_store_id cannot be empty."
            )

        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero.")

        if self.created_day < 1:
            raise ValueError(
                "created_day must be greater than or equal to 1."
            )

        if self.arrival_day <= self.created_day:
            raise ValueError(
                "arrival_day must be greater than created_day."
            )

        if self.operation_type == PendingOperationType.TRANSFER:
            if not self.source_store_id:
                raise ValueError(
                    "TRANSFER requires source_store_id."
                )

            if self.source_store_id == self.destination_store_id:
                raise ValueError(
                    "Transfer source and destination must differ."
                )

            if self.supplier_id is not None:
                raise ValueError(
                    "TRANSFER cannot have supplier_id."
                )

        if self.operation_type in {
            PendingOperationType.NORMAL_ORDER,
            PendingOperationType.EXPEDITE_ORDER,
        }:
            if not self.supplier_id:
                raise ValueError(
                    "Supplier orders require supplier_id."
                )

            if self.source_store_id is not None:
                raise ValueError(
                    "Supplier orders cannot have source_store_id."
                )

    @property
    def is_pending(self) -> bool:
        return self.status == PendingOperationStatus.PENDING

    def is_due(self, current_day: int) -> bool:
        return (
            self.is_pending
            and current_day >= self.arrival_day
        )

    def mark_completed(self) -> None:
        if not self.is_pending:
            raise ValueError(
                "Only pending operations can be completed."
            )

        self.status = PendingOperationStatus.COMPLETED

    def cancel(self) -> None:
        if not self.is_pending:
            raise ValueError(
                "Only pending operations can be cancelled."
            )

        self.status = PendingOperationStatus.CANCELLED