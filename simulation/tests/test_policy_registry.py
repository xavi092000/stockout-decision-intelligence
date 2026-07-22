from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simulation.governance.policy_models import (
    PolicyGovernanceError,
    PolicyStatus,
    RegisteredPolicy,
)
from simulation.governance.policy_registry import (
    PolicyRegistry,
)


class PolicyRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        registry_path = (
            Path(self.temp_directory.name)
            / "policy_registry.json"
        )
        self.registry = PolicyRegistry(registry_path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def _policy(
        *,
        name: str = "balanced",
        version: str = "1.0.0",
    ) -> RegisteredPolicy:
        return RegisteredPolicy.create(
            name=name,
            version=version,
            policy_type="RULE_BASED",
            description="Test policy.",
            configuration={
                "reorder_multiplier": 1.0,
                "target_multiplier": 1.0,
                "minimum_service_level": 0.985,
            },
            status=PolicyStatus.CANDIDATE,
        )

    def _approve(
        self,
        policy: RegisteredPolicy,
    ) -> None:
        self.registry.approve(
            policy_id=policy.policy_id,
            approved_by="platform-owner",
            reason="Validation passed.",
        )

    def test_register_and_retrieve_policy(self) -> None:
        policy = self._policy()

        self.registry.register(policy)
        retrieved = self.registry.get(policy.policy_id)

        self.assertEqual(
            retrieved.policy_id,
            policy.policy_id,
        )
        self.assertEqual(
            retrieved.status,
            PolicyStatus.CANDIDATE,
        )

    def test_duplicate_policy_is_rejected(self) -> None:
        policy = self._policy()
        self.registry.register(policy)

        with self.assertRaises(PolicyGovernanceError):
            self.registry.register(policy)

    def test_only_one_champion_remains(self) -> None:
        first = self._policy(name="balanced")
        second = self._policy(name="service_first")

        self.registry.register(first)
        self.registry.register(second)

        self._approve(first)
        self._approve(second)

        self.registry.set_status(
            policy_id=first.policy_id,
            status=PolicyStatus.CHAMPION,
        )
        self.registry.set_status(
            policy_id=second.policy_id,
            status=PolicyStatus.CHAMPION,
        )

        self.assertEqual(
            self.registry.get(first.policy_id).status,
            PolicyStatus.RETIRED,
        )
        self.assertEqual(
            self.registry.get_champion().policy_id,
            second.policy_id,
        )

    def test_candidate_can_be_approved(self) -> None:
        policy = self._policy()
        self.registry.register(policy)

        approved = self.registry.approve(
            policy_id=policy.policy_id,
            approved_by="platform-owner",
            reason="Validation criteria passed.",
        )

        self.assertIsNotNone(approved.approval)
        self.assertEqual(
            approved.approval.approved_by,
            "platform-owner",
        )

    def test_unapproved_policy_cannot_be_champion(
        self,
    ) -> None:
        policy = self._policy()
        self.registry.register(policy)

        with self.assertRaises(PolicyGovernanceError):
            self.registry.set_status(
                policy_id=policy.policy_id,
                status=PolicyStatus.CHAMPION,
            )


if __name__ == "__main__":
    unittest.main()
