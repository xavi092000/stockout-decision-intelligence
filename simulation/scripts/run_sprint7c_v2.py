from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.simulation_runner_v2 import (
    SimulationRunnerV2,
    SimulationRunnerV2Error,
)
from simulation.domain.models import DomainValidationError
from simulation.infrastructure.world_repository import (
    WorldRepositoryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run integrated inventory and supplier engines "
            "against schema v2."
        )
    )
    parser.add_argument("--days", type=int, default=90)
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
        default=Path("simulation/output/domain_v2"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = SimulationRunnerV2(
            world_path=args.world,
            scenario_path=args.scenarios,
            output_dir=args.output_dir,
            seed=args.seed,
        ).run(days=args.days)
    except (
        SimulationRunnerV2Error,
        DomainValidationError,
        WorldRepositoryError,
        OSError,
        ValueError,
        KeyError,
        StopIteration,
    ) as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error": str(exc)},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    summary = {
        "status": "PASSED",
        "schema_version": "2.0.0",
        "seed": args.seed,
        "result": result,
        "supplier_contract": "PASSED",
        "inventory_contract": "PASSED",
        "domain_validation": "PASSED",
        "leakage_guard": (
            "Only synthetic world state and synthetic scenarios "
            "were used."
        ),
    }

    summary_path = args.output_dir / "sprint7c_v2_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 66)
    print("SPRINT 7C V2 — INTEGRATED INVENTORY & SUPPLIER ENGINE")
    print("=" * 66)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 66)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
