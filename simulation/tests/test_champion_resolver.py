from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simulation.governance.champion_resolver import (
    ChampionPolicyResolver,
)
from simulation.governance.policy_models import (
    PolicyGovernanceError,
    PolicyStatus,
    RegisteredPolicy,
)
from simulation.governance.policy_registry import (
    PolicyRegistry,
)


class ChampionPolicyResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        registry_path = (
            Path(self.temp_directory.name)
            / "policy_registry.json"
        )
        self.registry = PolicyRegistry(registry_path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def _register_candidate(
        self,
        *,
        name: str = "balanced",
        configuration: dict[str, float] | None = None,
    ) -> RegisteredPolicy:
        policy = RegisteredPolicy.create(
            name=name,
            version="1.0.0",
            policy_type="RULE_BASED",
            description="Governed test policy.",
            configuration=configuration or {
                "reorder_multiplier": 1.0,
                "target_multiplier": 1.0,
                "minimum_service_level": 0.985,
            },
            status=PolicyStatus.CANDIDATE,
        )
        return self.registry.register(policy)

    def _approve_and_promote(
        self,
        policy: RegisteredPolicy,
    ) -> RegisteredPolicy:
        self.registry.approve(
            policy_id=policy.policy_id,
            approved_by="platform-owner",
            reason="Scientific validation passed.",
        )

        return self.registry.set_status(
            policy_id=policy.policy_id,
            status=PolicyStatus.CHAMPION,
        )

    def test_resolves_approved_champion(self) -> None:
        policy = self._register_candidate()
        champion = self._approve_and_promote(policy)

        resolved = ChampionPolicyResolver(
            self.registry
        ).resolve()

        self.assertEqual(
            resolved.registry_policy.policy_id,
            champion.policy_id,
        )
        self.assertEqual(
            resolved.executable_policy.name,
            "balanced",
        )
        self.assertEqual(
            resolved.executable_policy.reorder_multiplier,
            1.0,
        )
        self.assertEqual(
            resolved.executable_policy.minimum_service_level,
            0.985,
        )

    def test_fails_when_no_champion_exists(self) -> None:
        resolver = ChampionPolicyResolver(self.registry)

        with self.assertRaises(PolicyGovernanceError):
            resolver.resolve()

    def test_unapproved_policy_cannot_be_champion(
        self,
    ) -> None:
        policy = self._register_candidate(name="lean")

        with self.assertRaises(PolicyGovernanceError):
            self.registry.set_status(
                policy_id=policy.policy_id,
                status=PolicyStatus.CHAMPION,
            )

    def test_incomplete_configuration_is_rejected(
        self,
    ) -> None:
        policy = self._register_candidate(
            name="invalid",
            configuration={
                "reorder_multiplier": 1.0,
            },
        )
        self._approve_and_promote(policy)

        with self.assertRaises(PolicyGovernanceError):
            ChampionPolicyResolver(
                self.registry
            ).resolve()

    def test_invalid_configuration_is_rejected(
        self,
    ) -> None:
        policy = self._register_candidate(
            name="invalid-negative",
            configuration={
                "reorder_multiplier": -1.0,
                "target_multiplier": 1.0,
                "minimum_service_level": 0.985,
            },
        )
        self._approve_and_promote(policy)

        with self.assertRaises(PolicyGovernanceError):
            ChampionPolicyResolver(
                self.registry
            ).resolve()


if __name__ == "__main__":
    unittest.main()
