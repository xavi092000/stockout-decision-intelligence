from __future__ import annotations

import unittest

from simulation.decision.adaptive_policy_v2 import (
    AdaptivePolicyEngineV2,
)


class AdaptivePolicyTests(unittest.TestCase):
    def test_valid_policy_names(self) -> None:
        self.assertEqual(
            AdaptivePolicyEngineV2.VALID_POLICIES,
            {"lean", "balanced", "service_first"},
        )

    def test_no_future_inputs_in_signature(self) -> None:
        parameters = (
            AdaptivePolicyEngineV2.choose.__annotations__
        )
        self.assertIn("world", parameters)
        self.assertIn("scenario", parameters)
        self.assertIn("trailing_metrics", parameters)
        self.assertNotIn("future_scenarios", parameters)


if __name__ == "__main__":
    unittest.main()
