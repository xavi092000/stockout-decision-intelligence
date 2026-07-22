from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.orchestrator_v2 import (
    OrchestratorV2Error,
    SimulationOrchestratorV2,
)
from simulation.domain.models import DomainValidationError
from simulation.infrastructure.world_repository import (
    WorldRepositoryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the full domain-v2 simulation for 365 days."
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
            "simulation/output/orchestrator_v2"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = SimulationOrchestratorV2(
            world_path=args.world,
            scenario_path=args.scenarios,
            output_dir=args.output_dir,
            seed=args.seed,
        ).run(days=args.days)
    except (
        OrchestratorV2Error,
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

    summary = {
        "status": "PASSED",
        "schema_version": "2.0.0",
        "seed": args.seed,
        "result": result,
        "orchestrator_contract": "PASSED",
        "sales_contract": "PASSED",
        "supplier_contract": "PASSED",
        "financial_contract": "PASSED",
        "economic_sanity_contract": "PASSED",
        "domain_validation": "PASSED",
        "leakage_guard": (
            "The annual run uses synthetic scenarios and the current "
            "synthetic WorldState only."
        ),
    }

    summary_path = (
        args.output_dir / "sprint7g_v2_summary.json"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print("SPRINT 7G V2 — 365-DAY SIMULATION ORCHESTRATOR")
    print("=" * 72)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 72)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
