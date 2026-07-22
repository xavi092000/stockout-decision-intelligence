from __future__ import annotations

from pathlib import Path
from typing import Any

from simulation.application.orchestrator_v2 import (
    SimulationOrchestratorV2,
)
from simulation.decision.policies_v2 import (
    InventoryPolicyApplier,
)
from simulation.governance.champion_resolver import (
    ChampionPolicyResolver,
)
from simulation.governance.policy_registry import (
    PolicyRegistry,
)
from simulation.infrastructure.world_repository import (
    JsonWorldRepository,
)


class GovernedSimulationRunnerV2Error(RuntimeError):
    """Raised when a governed simulation cannot start safely."""


class GovernedSimulationRunnerV2:
    """
    Run one episode with a champion policy resolved before day one.

    Leakage safety:
    - champion resolution occurs before scenario iteration;
    - the resolver receives no scenarios or outcomes;
    - the selected policy remains frozen for the full episode;
    - simulation results cannot alter the active policy.
    """

    def __init__(
        self,
        *,
        world_path: str | Path,
        scenario_path: str | Path,
        output_dir: str | Path,
        registry_path: str | Path,
        seed: int = 42,
    ) -> None:
        self.world_path = Path(world_path)
        self.scenario_path = Path(scenario_path)
        self.output_dir = Path(output_dir)
        self.registry_path = Path(registry_path)
        self.seed = seed

    def run(self, days: int = 365) -> dict[str, Any]:
        if days <= 0:
            raise GovernedSimulationRunnerV2Error(
                "days must be greater than zero."
            )

        if not self.world_path.is_file():
            raise GovernedSimulationRunnerV2Error(
                f"World file not found: {self.world_path}"
            )

        if not self.scenario_path.is_file():
            raise GovernedSimulationRunnerV2Error(
                f"Scenario file not found: {self.scenario_path}"
            )

        registry = PolicyRegistry(self.registry_path)

        resolved = ChampionPolicyResolver(
            registry
        ).resolve()

        repository = JsonWorldRepository()
        world = repository.load(self.world_path)

        policy_applier = InventoryPolicyApplier()
        actions = policy_applier.apply(
            world,
            resolved.executable_policy,
        )

        world.metadata["governance_enabled"] = True
        world.metadata["champion_policy_id"] = (
            resolved.registry_policy.policy_id
        )
        world.metadata["champion_policy_name"] = (
            resolved.registry_policy.name
        )
        world.metadata["champion_policy_version"] = (
            resolved.registry_policy.version
        )
        world.metadata["champion_resolved_before_episode"] = True
        world.metadata["policy_frozen_for_episode"] = True

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        governed_world_path = (
            self.output_dir
            / "world_state_governed_day_000.json"
        )
        repository.save(
            world,
            governed_world_path,
        )

        result = SimulationOrchestratorV2(
            world_path=governed_world_path,
            scenario_path=self.scenario_path,
            output_dir=self.output_dir,
            seed=self.seed,
        ).run(days=days)

        return {
            **result,
            "governance": {
                "enabled": True,
                "champion_policy_id": (
                    resolved.registry_policy.policy_id
                ),
                "champion_policy_name": (
                    resolved.registry_policy.name
                ),
                "champion_policy_version": (
                    resolved.registry_policy.version
                ),
                "approved_by": (
                    resolved.registry_policy.approval.approved_by
                ),
                "resolved_before_episode": True,
                "policy_frozen_for_episode": True,
                "future_information_used": False,
                "policy_actions_applied": len(actions),
            },
            "governed_world_path": str(
                governed_world_path.resolve()
            ),
        }
