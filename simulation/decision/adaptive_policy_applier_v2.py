from __future__ import annotations

from typing import Any

from simulation.decision.policies_v2 import POLICIES
from simulation.domain.models import WorldState


class AdaptivePolicyApplierV2:
    """
    Applies policy multipliers against immutable baseline stock parameters.

    This avoids compounding a multiplier every day.
    """

    def __init__(self, world: WorldState) -> None:
        self.baseline = {
            (item.store_id, item.sku_id): {
                "reorder_point": item.reorder_point,
                "target_stock": item.target_stock,
            }
            for item in world.inventory
        }

    def apply(
        self,
        world: WorldState,
        policy_name: str,
    ) -> list[dict[str, Any]]:
        if policy_name not in POLICIES:
            raise ValueError(f"Unknown policy: {policy_name}")

        policy = POLICIES[policy_name]
        actions: list[dict[str, Any]] = []

        for position in world.inventory:
            key = (position.store_id, position.sku_id)
            base = self.baseline[key]

            old_reorder = position.reorder_point
            old_target = position.target_stock

            new_reorder = max(
                position.safety_stock,
                int(round(
                    base["reorder_point"]
                    * policy.reorder_multiplier
                )),
            )
            new_target = max(
                new_reorder,
                int(round(
                    base["target_stock"]
                    * policy.target_multiplier
                )),
            )

            position.reorder_point = new_reorder
            position.target_stock = new_target
            position.validate()

            if (
                old_reorder != new_reorder
                or old_target != new_target
            ):
                actions.append(
                    {
                        "policy_name": policy_name,
                        "store_id": position.store_id,
                        "sku_id": position.sku_id,
                        "old_reorder_point": old_reorder,
                        "new_reorder_point": new_reorder,
                        "old_target_stock": old_target,
                        "new_target_stock": new_target,
                    }
                )

        world.metadata["active_policy"] = policy_name
        world.validate()
        return actions
