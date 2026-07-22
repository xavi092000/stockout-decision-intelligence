from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from simulation.calibration_repository import CalibrationRepository
from simulation.scenario_engine import ScenarioEngine
from simulation.validation.synthetic_generation import (
    SyntheticGenerationThresholds,
    SyntheticGenerationValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate coverage, diversity and coherence of synthetic scenarios."
    )
    parser.add_argument("--days", type=int, default=18_250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/synthetic_generation/report.json"),
    )
    parser.add_argument(
        "--demand-dir",
        type=Path,
        default=Path("reality_calibration/data/processed/calibration"),
    )
    parser.add_argument(
        "--weather-dir",
        type=Path,
        default=Path("reality_calibration/data/processed/weather_calibration"),
    )
    parser.add_argument(
        "--economic-dir",
        type=Path,
        default=Path("reality_calibration/data/processed/economic_calibration"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.days <= 0:
        raise SystemExit("--days must be greater than zero")

    calibrations = CalibrationRepository(
        args.demand_dir, args.weather_dir, args.economic_dir
    ).load()
    start_date = date(2027, 1, 1)
    scenarios = ScenarioEngine(
        calibrations=calibrations,
        seed=args.seed,
        start_date=start_date,
    ).generate_days(args.days)
    reference = ScenarioEngine(
        calibrations=calibrations,
        seed=args.seed,
        start_date=start_date,
    ).generate_days(args.days)

    report = SyntheticGenerationValidator(
        calibrations,
        SyntheticGenerationThresholds(
            minimum_scenarios=min(3_650, args.days)
        ),
    ).evaluate(
        scenarios,
        reproducibility_reference=reference,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Synthetic generation: {'PASS' if report.passed else 'FAIL'}")
    print(f"Scenarios: {report.sample_size}")
    print(f"Digest: {report.digest}")
    print(f"Report: {args.output}")
    for metric in report.failed_metrics():
        print(f"FAIL {metric.name}: {metric.details}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
