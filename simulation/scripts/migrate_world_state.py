from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.compatibility_check import (
    build_compatibility_report,
)
from simulation.domain.models import DomainValidationError
from simulation.infrastructure.world_repository import (
    JsonWorldRepository,
    WorldRepositoryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate an existing Sprint 7 world state to the unified "
            "schema."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(
            "simulation/output/world/world_state_day_000.json"
        ),
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path(
            "simulation/output/core/world_state_v2_day_000.json"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "simulation/output/core/"
            "architecture_compatibility_report.json"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repository = JsonWorldRepository()

    try:
        world = repository.load(args.source)
        destination = repository.save(world, args.destination)
        report = build_compatibility_report(world)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except (
        WorldRepositoryError,
        DomainValidationError,
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
        "source": str(args.source.resolve()),
        "destination": str(destination.resolve()),
        "report": str(args.report.resolve()),
        "compatibility": report,
    }

    print("\n" + "=" * 66)
    print("SPRINT 7 CORE — DOMAIN & CONTRACT REFACTOR")
    print("=" * 66)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 66)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
