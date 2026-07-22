from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from simulation.calibration_repository import (
    CalibrationRepository,
    CalibrationRepositoryError,
)
from simulation.scenario_engine import ScenarioEngine, ScenarioEngineError
from simulation.scenario_exporter import ScenarioExporter
from simulation.validation.scenario_validation import (
    ScenarioValidationError,
    validate_scenarios,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Generate leakage-safe synthetic retail scenarios."
    )
    result.add_argument("--days", type=int, default=365)
    result.add_argument("--seed", type=int, default=42)
    result.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=date(2027, 1, 1),
    )
    result.add_argument(
        "--demand-dir",
        type=Path,
        default=Path(
            "reality_calibration/data/processed/calibration"
        ),
    )
    result.add_argument(
        "--weather-dir",
        type=Path,
        default=Path(
            "reality_calibration/data/processed/weather_calibration"
        ),
    )
    result.add_argument(
        "--economic-dir",
        type=Path,
        default=Path(
            "reality_calibration/data/processed/economic_calibration"
        ),
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation/output/scenarios"),
    )
    return result


def main() -> int:
    args = parser().parse_args()

    try:
        calibrations = CalibrationRepository(
            demand_dir=args.demand_dir,
            weather_dir=args.weather_dir,
            economic_dir=args.economic_dir,
        ).load()

        engine = ScenarioEngine(
            calibrations=calibrations,
            seed=args.seed,
            start_date=args.start_date,
        )
        scenarios = engine.generate_days(args.days)
        export = ScenarioExporter(args.output_dir).export(scenarios)
        validation = validate_scenarios(
            args.output_dir,
            expected_days=args.days,
        )

    except (
        CalibrationRepositoryError,
        ScenarioEngineError,
        ScenarioValidationError,
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
        "days": args.days,
        "seed": args.seed,
        "start_date": args.start_date.isoformat(),
        "end_date": scenarios[-1].synthetic_date,
        "export": export,
        "validation": validation,
    }

    summary_path = args.output_dir / "scenario_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 62)
    print("SPRINT 6 — SYNTHETIC SCENARIO ENGINE")
    print("=" * 62)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 62)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
