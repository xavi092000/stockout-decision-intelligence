from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.world.inventory_engine import InventoryEngineError
from simulation.world.inventory_runner import (
    InventoryRunnerError,
    InventorySimulationRunner,
)
from simulation.world.validation.inventory_validation import (
    InventoryValidationError,
    validate_inventory_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Advance the synthetic world inventory day by day."
    )
    parser.add_argument("--days", type=int, default=30)
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
        default=Path("simulation/output/inventory"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        run = InventorySimulationRunner(
            initial_world_path=args.initial_world,
            scenarios_path=args.scenarios,
            output_dir=args.output_dir,
            seed=args.seed,
        ).run(days=args.days)

        validation = validate_inventory_run(
            output_dir=args.output_dir,
            expected_days=args.days,
            expected_positions=1000,
        )
    except (
        InventoryRunnerError,
        InventoryEngineError,
        InventoryValidationError,
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
            "Inventory transitions use synthetic world state and "
            "synthetic scenarios only."
        ),
    }

    summary_path = args.output_dir / "inventory_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 62)
    print("SPRINT 7B — DAILY INVENTORY ENGINE")
    print("=" * 62)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 62)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
