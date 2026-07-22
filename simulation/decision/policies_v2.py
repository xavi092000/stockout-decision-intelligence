from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from simulation.domain.models import WorldState


class PolicyValidationError(RuntimeError):
    """Raised when a decision policy produces an invalid action."""


@dataclass(frozen=True)
class PolicyAction:
    policy_name: str
    store_id: str
    sku_id: str
    old_reorder_point: int
    new_reorder_point: int
    old_target_stock: int
    new_target_stock: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDefinition:
    name: str
    reorder_multiplier: float
    target_multiplier: float
    minimum_service_level: float
    description: str

    def validate(self) -> None:
        if self.reorder_multiplier <= 0:
            raise PolicyValidationError(
                "reorder_multiplier must be positive."
            )
        if self.target_multiplier <= 0:
            raise PolicyValidationError(
                "target_multiplier must be positive."
            )
        if not 0 < self.minimum_service_level <= 1:
            raise PolicyValidationError(
                "minimum_service_level must be in (0, 1]."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


POLICIES = {
    "lean": PolicyDefinition(
        name="lean",
        reorder_multiplier=0.85,
        target_multiplier=0.85,
        minimum_service_level=0.97,
        description=(
            "Lower inventory exposure with greater stockout risk."
        ),
    ),
    "balanced": PolicyDefinition(
        name="balanced",
        reorder_multiplier=1.00,
        target_multiplier=1.00,
        minimum_service_level=0.985,
        description=(
            "Current calibrated policy balancing cost and service."
        ),
    ),
    "service_first": PolicyDefinition(
        name="service_first",
        reorder_multiplier=1.20,
        target_multiplier=1.25,
        minimum_service_level=0.995,
        description=(
            "Higher inventory buffers to protect service level."
        ),
    ),
}


class InventoryPolicyApplier:
    def apply(
        self,
        world: WorldState,
        policy: PolicyDefinition,
    ) -> list[PolicyAction]:
        policy.validate()
        actions: list[PolicyAction] = []

        for position in world.inventory:
            old_reorder = position.reorder_point
            old_target = position.target_stock

            new_reorder = max(
                position.safety_stock,
                int(round(old_reorder * policy.reorder_multiplier)),
            )
            new_target = max(
                new_reorder,
                int(round(old_target * policy.target_multiplier)),
            )

            position.reorder_point = new_reorder
            position.target_stock = new_target
            position.validate()

            actions.append(
                PolicyAction(
                    policy_name=policy.name,
                    store_id=position.store_id,
                    sku_id=position.sku_id,
                    old_reorder_point=old_reorder,
                    new_reorder_point=new_reorder,
                    old_target_stock=old_target,
                    new_target_stock=new_target,
                    reason=policy.description,
                )
            )

        world.metadata["active_policy"] = policy.name
        world.metadata["policy_description"] = policy.description
        world.validate()
        return actions
