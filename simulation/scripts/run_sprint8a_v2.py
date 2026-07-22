from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.policy_comparison_runner_v2 import (
    PolicyComparisonError,
    PolicyComparisonRunnerV2,
)
from simulation.decision.policies_v2 import (
    PolicyValidationError,
)
from simulation.domain.models import DomainValidationError
from simulation.infrastructure.world_repository import (
    WorldRepositoryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare replenishment policies on identical scenarios."
    )
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--world",
        type=Path,
        default=Path(
            "simulation/output/core/world_state_v2_day_000.json"
        ),
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path(
            "simulation/output/scenarios/"
            "synthetic_scenarios_summary.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "simulation/output/policy_comparison_v2"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = PolicyComparisonRunnerV2(
            base_world_path=args.world,
            scenario_path=args.scenarios,
            output_dir=args.output_dir,
            seed=args.seed,
        ).run(days=args.days)
    except (
        PolicyComparisonError,
        PolicyValidationError,
        DomainValidationError,
        WorldRepositoryError,
        OSError,
        ValueError,
        KeyError,
        StopIteration,
    ) as exc:
        print(json.dumps(
            {"status": "FAILED", "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        ))
        return 1

    print("\n" + "=" * 72)
    print("SPRINT 8A V2 — POLICY COMPARISON ENGINE")
    print("=" * 72)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 72)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
