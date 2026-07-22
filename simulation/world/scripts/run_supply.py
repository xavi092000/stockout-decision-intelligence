from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.world.supplier_engine import SupplierEngineError
from simulation.world.supply_runner import (
    SupplyRunnerError,
    SupplySimulationRunner,
)
from simulation.world.validation.supply_validation import (
    SupplyValidationError,
    validate_supply_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run inventory and supplier replenishment together."
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--initial-world",
        type=Path,
        default=Path(
            "simulation/output/world/world_state_day_000.json"
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
        default=Path("simulation/output/supply"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        run = SupplySimulationRunner(
            initial_world_path=args.initial_world,
            scenarios_path=args.scenarios,
            output_dir=args.output_dir,
            seed=args.seed,
        ).run(days=args.days)

        validation = validate_supply_run(
            output_dir=args.output_dir,
            expected_days=args.days,
            expected_positions=1000,
        )
    except (
        SupplyRunnerError,
        SupplierEngineError,
        SupplyValidationError,
        OSError,
        ValueError,
        KeyError,
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
        "schema_version": "1.0.0",
        "seed": args.seed,
        "run": run,
        "validation": validation,
        "leakage_guard": (
            "Supplier decisions use current synthetic inventory state, "
            "supplier contracts and current-day scenario factors only."
        ),
    }

    summary_path = args.output_dir / "supply_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 62)
    print("SPRINT 7C — SUPPLIER & ORDERS ENGINE")
    print("=" * 62)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 62)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
