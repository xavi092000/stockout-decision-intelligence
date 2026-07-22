from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simulation.application.governed_runner_v2 import (
    GovernedSimulationRunnerV2,
)
from simulation.governance.policy_models import (
    PolicyStatus,
    RegisteredPolicy,
)
from simulation.governance.policy_registry import (
    PolicyRegistry,
)


class GovernedSimulationRunnerV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)

        self.world_path = self.root / "world.json"
        self.scenario_path = self.root / "scenarios.csv"
        self.output_dir = self.root / "output"
        self.registry_path = self.root / "policy_registry.json"

        self.world_path.write_text(
            "{}",
            encoding="utf-8",
        )
        self.scenario_path.write_text(
            "simulation_day,synthetic_date\n"
            "1,2026-01-01\n",
            encoding="utf-8",
        )

        registry = PolicyRegistry(self.registry_path)

        policy = RegisteredPolicy.create(
            name="balanced",
            version="1.0.0",
            policy_type="RULE_BASED",
            description="Governed balanced policy.",
            configuration={
                "reorder_multiplier": 1.0,
                "target_multiplier": 1.0,
                "minimum_service_level": 0.985,
            },
            status=PolicyStatus.CANDIDATE,
        )

        registry.register(policy)
        registry.approve(
            policy_id=policy.policy_id,
            approved_by="platform-owner",
            reason="Scientific validation passed.",
        )
        registry.set_status(
            policy_id=policy.policy_id,
            status=PolicyStatus.CHAMPION,
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @patch(
        "simulation.application.governed_runner_v2."
        "SimulationOrchestratorV2"
    )
    @patch(
        "simulation.application.governed_runner_v2."
        "InventoryPolicyApplier"
    )
    @patch(
        "simulation.application.governed_runner_v2."
        "JsonWorldRepository"
    )
    def test_champion_is_resolved_before_episode(
        self,
        repository_class,
        applier_class,
        orchestrator_class,
    ) -> None:
        world = type(
            "WorldStub",
            (),
            {
                "metadata": {},
            },
        )()

        repository = repository_class.return_value
        repository.load.return_value = world

        applier = applier_class.return_value
        applier.apply.return_value = [
            object(),
            object(),
        ]

        orchestrator = orchestrator_class.return_value
        orchestrator.run.return_value = {
            "status": "PASSED",
            "days_processed": 1,
        }

        result = GovernedSimulationRunnerV2(
            world_path=self.world_path,
            scenario_path=self.scenario_path,
            output_dir=self.output_dir,
            registry_path=self.registry_path,
            seed=42,
        ).run(days=1)

        applier.apply.assert_called_once()

        executable_policy = (
            applier.apply.call_args.args[1]
        )

        self.assertEqual(
            executable_policy.name,
            "balanced",
        )
        self.assertTrue(
            world.metadata[
                "champion_resolved_before_episode"
            ]
        )
        self.assertTrue(
            world.metadata[
                "policy_frozen_for_episode"
            ]
        )
        self.assertFalse(
            result["governance"][
                "future_information_used"
            ]
        )
        self.assertEqual(
            result["governance"][
                "policy_actions_applied"
            ],
            2,
        )
        orchestrator.run.assert_called_once_with(
            days=1
        )

    @patch(
        "simulation.application.governed_runner_v2."
        "SimulationOrchestratorV2"
    )
    @patch(
        "simulation.application.governed_runner_v2."
        "InventoryPolicyApplier"
    )
    @patch(
        "simulation.application.governed_runner_v2."
        "JsonWorldRepository"
    )
    def test_registry_is_not_reconsulted_during_episode(
        self,
        repository_class,
        applier_class,
        orchestrator_class,
    ) -> None:
        world = type(
            "WorldStub",
            (),
            {
                "metadata": {},
            },
        )()

        repository_class.return_value.load.return_value = world
        applier_class.return_value.apply.return_value = []

        orchestrator_class.return_value.run.return_value = {
            "status": "PASSED",
        }

        from simulation.governance.champion_resolver import (
            ChampionPolicyResolver,
        )

        real_resolver = ChampionPolicyResolver(
            PolicyRegistry(self.registry_path)
        )
        resolved = real_resolver.resolve()

        with patch(
            "simulation.application.governed_runner_v2."
            "ChampionPolicyResolver.resolve",
            return_value=resolved,
        ) as resolve_mock:
            GovernedSimulationRunnerV2(
                world_path=self.world_path,
                scenario_path=self.scenario_path,
                output_dir=self.output_dir,
                registry_path=self.registry_path,
            ).run(days=1)

            resolve_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

