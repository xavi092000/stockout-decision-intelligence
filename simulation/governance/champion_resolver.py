from __future__ import annotations

from dataclasses import dataclass

from simulation.decision.policies_v2 import (
    PolicyDefinition,
    PolicyValidationError,
)
from simulation.governance.policy_models import (
    PolicyGovernanceError,
    RegisteredPolicy,
)
from simulation.governance.policy_registry import (
    PolicyRegistry,
)


@dataclass(frozen=True)
class ResolvedChampion:
    registry_policy: RegisteredPolicy
    executable_policy: PolicyDefinition


class ChampionPolicyResolver:
    """
    Resolve the approved registry champion into an executable policy.

    The resolver has no access to simulation states, scenarios, rewards,
    sales, future inventory levels, or benchmark results.
    """

    REQUIRED_CONFIGURATION_KEYS = {
        "reorder_multiplier",
        "target_multiplier",
        "minimum_service_level",
    }

    def __init__(self, registry: PolicyRegistry) -> None:
        self.registry = registry

    def resolve(self) -> ResolvedChampion:
        champion = self.registry.get_champion()

        if champion is None:
            raise PolicyGovernanceError(
                "No champion policy is registered."
            )

        if champion.approval is None:
            raise PolicyGovernanceError(
                "Champion policy is not approved."
            )

        missing_keys = (
            self.REQUIRED_CONFIGURATION_KEYS
            - set(champion.configuration)
        )

        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise PolicyGovernanceError(
                "Champion configuration is incomplete. "
                f"Missing: {missing}"
            )

        try:
            executable_policy = PolicyDefinition(
                name=champion.name,
                reorder_multiplier=float(
                    champion.configuration[
                        "reorder_multiplier"
                    ]
                ),
                target_multiplier=float(
                    champion.configuration[
                        "target_multiplier"
                    ]
                ),
                minimum_service_level=float(
                    champion.configuration[
                        "minimum_service_level"
                    ]
                ),
                description=champion.description,
            )
            executable_policy.validate()
        except (
            KeyError,
            TypeError,
            ValueError,
            PolicyValidationError,
        ) as exc:
            raise PolicyGovernanceError(
                "Champion configuration contains invalid values."
            ) from exc

        return ResolvedChampion(
            registry_policy=champion,
            executable_policy=executable_policy,
        )
