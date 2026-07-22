from __future__ import annotations

import unittest

from simulation.application.policy_comparison_runner_v2 import (
    PolicyComparisonRunnerV2,
)
from simulation.decision.policies_v2 import POLICIES


class PolicyComparisonTests(unittest.TestCase):
    def test_all_policy_definitions_are_valid(self) -> None:
        for policy in POLICIES.values():
            policy.validate()

    def test_score_penalizes_service_violation(self) -> None:
        compliant = PolicyComparisonRunnerV2._score(
            profit=10000.0,
            fill_rate=0.99,
            minimum_service_level=0.98,
        )
        violation = PolicyComparisonRunnerV2._score(
            profit=10000.0,
            fill_rate=0.95,
            minimum_service_level=0.98,
        )

        self.assertEqual(compliant, 10000.0)
        self.assertLess(violation, compliant)


if __name__ == "__main__":
    unittest.main()
