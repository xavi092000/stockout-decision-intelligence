from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json

import pandas as pd

from simulation.application.orchestrator_v2 import (
    SimulationOrchestratorV2,
)
from simulation.decision.policies_v2 import (
    InventoryPolicyApplier,
    POLICIES,
)
from simulation.infrastructure.world_repository import (
    JsonWorldRepository,
)


class PolicyComparisonError(RuntimeError):
    """Raised when policy benchmarking cannot be completed."""


class PolicyComparisonRunnerV2:
    def __init__(
        self,
        base_world_path: str | Path,
        scenario_path: str | Path,
        output_dir: str | Path,
        seed: int = 42,
    ) -> None:
        self.base_world_path = Path(base_world_path)
        self.scenario_path = Path(scenario_path)
        self.output_dir = Path(output_dir)
        self.seed = seed

    @staticmethod
    def _score(
        profit: float,
        fill_rate: float,
        minimum_service_level: float,
    ) -> float:
        service_penalty = 0.0
        if fill_rate < minimum_service_level:
            service_penalty = (
                minimum_service_level - fill_rate
            ) * 1_000_000.0
        return profit - service_penalty

    def run(self, days: int = 365) -> dict[str, Any]:
        if not self.base_world_path.is_file():
            raise PolicyComparisonError(
                f"Base world not found: {self.base_world_path}"
            )
        if not self.scenario_path.is_file():
            raise PolicyComparisonError(
                f"Scenario file not found: {self.scenario_path}"
            )

        repository = JsonWorldRepository()
        base_world = repository.load(self.base_world_path)
        applier = InventoryPolicyApplier()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        comparison_rows: list[dict[str, Any]] = []
        all_actions: list[dict[str, Any]] = []

        for policy_name, policy in POLICIES.items():
            policy_dir = self.output_dir / policy_name
            policy_dir.mkdir(parents=True, exist_ok=True)

            world = deepcopy(base_world)
            actions = applier.apply(world, policy)
            all_actions.extend(action.to_dict() for action in actions)

            policy_world_path = (
                policy_dir / "world_state_policy_day_000.json"
            )
            repository.save(world, policy_world_path)

            result = SimulationOrchestratorV2(
                world_path=policy_world_path,
                scenario_path=self.scenario_path,
                output_dir=policy_dir,
                seed=self.seed,
            ).run(days=days)

            score = self._score(
                profit=float(
                    result["calibrated_net_operating_profit"]
                ),
                fill_rate=float(result["overall_fill_rate"]),
                minimum_service_level=policy.minimum_service_level,
            )

            comparison_rows.append(
                {
                    "policy_name": policy_name,
                    "description": policy.description,
                    "reorder_multiplier": policy.reorder_multiplier,
                    "target_multiplier": policy.target_multiplier,
                    "minimum_service_level": (
                        policy.minimum_service_level
                    ),
                    "requested_units": result["requested_units"],
                    "sold_units": result["sold_units"],
                    "lost_units": result["lost_units"],
                    "fill_rate": result["overall_fill_rate"],
                    "ending_on_hand_units": (
                        result["ending_on_hand_units"]
                    ),
                    "ending_in_transit_units": (
                        result["ending_in_transit_units"]
                    ),
                    "orders_created": result["orders_created"],
                    "receipts_created": result["receipts_created"],
                    "realized_revenue": result["realized_revenue"],
                    "gross_margin": result["gross_margin"],
                    "holding_cost": result["holding_cost"],
                    "logistics_cost": result["logistics_cost"],
                    "calibrated_net_operating_profit": (
                        result[
                            "calibrated_net_operating_profit"
                        ]
                    ),
                    "economic_sanity_status": (
                        result["economic_sanity_status"]
                    ),
                    "service_constraint_met": (
                        result["overall_fill_rate"]
                        >= policy.minimum_service_level
                    ),
                    "objective_score": round(score, 2),
                }
            )

        comparison = pd.DataFrame(comparison_rows).sort_values(
            ["objective_score", "fill_rate"],
            ascending=[False, False],
        ).reset_index(drop=True)

        comparison["rank"] = range(1, len(comparison) + 1)
        winner = comparison.iloc[0].to_dict()

        comparison_path = (
            self.output_dir / "policy_comparison_v2.csv"
        )
        action_path = self.output_dir / "policy_actions_v2.csv"
        comparison.to_csv(comparison_path, index=False)
        pd.DataFrame(all_actions).to_csv(action_path, index=False)

        result = {
            "status": "PASSED",
            "schema_version": "2.0.0",
            "days_compared": days,
            "seed": self.seed,
            "policies_compared": list(POLICIES),
            "winner": winner,
            "ranking": comparison.to_dict(orient="records"),
            "fair_comparison": {
                "same_initial_world": True,
                "same_scenarios": True,
                "same_seed": True,
                "future_information_used": False,
            },
            "comparison_path": str(comparison_path.resolve()),
            "actions_path": str(action_path.resolve()),
        }

        summary_path = (
            self.output_dir / "policy_comparison_summary_v2.json"
        )
        summary_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return result
