from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.sales_runner_v2 import (
    SalesRunnerV2Error,
    SalesSimulationRunnerV2,
)
from simulation.domain.models import DomainValidationError
from simulation.engines.sales_v2 import SalesEngineV2Error
from simulation.engines.supplier_v2 import SupplierEngineV2Error
from simulation.infrastructure.world_repository import (
    WorldRepositoryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the domain-v2 sales, stockout and supplier engines."
        )
    )
    parser.add_argument("--days", type=int, default=180)
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
        default=Path("simulation/output/sales_v2"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = SalesSimulationRunnerV2(
            world_path=args.world,
            scenario_path=args.scenarios,
            output_dir=args.output_dir,
            seed=args.seed,
        ).run(days=args.days)
    except (
        SalesRunnerV2Error,
        SalesEngineV2Error,
        SupplierEngineV2Error,
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
        "sales_contract": "PASSED",
        "stockout_contract": "PASSED",
        "supplier_contract": "PASSED",
        "domain_validation": "PASSED",
        "leakage_guard": (
            "Sales and stockout events use synthetic scenarios "
            "and the current synthetic world state only."
        ),
    }

    summary_path = (
        args.output_dir / "sprint7d_v2_summary.json"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 68)
    print("SPRINT 7D V2 — SALES & STOCKOUT ENGINE")
    print("=" * 68)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 68)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
