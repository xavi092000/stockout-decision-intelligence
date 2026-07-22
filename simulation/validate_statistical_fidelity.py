from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from simulation.calibration_repository import CalibrationRepository
from simulation.scenario_engine import ScenarioEngine
from simulation.validation.statistical_fidelity import (
    FidelityThresholds,
    StatisticalFidelityValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate synthetic scenarios against calibration contracts."
    )
    parser.add_argument("--days", type=int, default=18_250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/statistical_validation/report.json"),
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
    calibrations = CalibrationRepository(
        args.demand_dir, args.weather_dir, args.economic_dir
    ).load()
    scenarios = ScenarioEngine(
        calibrations=calibrations,
        seed=args.seed,
        start_date=date(2027, 1, 1),
    ).generate_days(args.days)
    report = StatisticalFidelityValidator(
        calibrations,
        FidelityThresholds(minimum_scenarios=min(3_650, args.days)),
    ).evaluate(scenarios)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Statistical fidelity: {'PASS' if report.passed else 'FAIL'}")
    print(f"Scenarios: {report.sample_size}")
    print(f"Report: {args.output}")
    for metric in report.failed_metrics():
        print(
            f"FAIL {metric.name}: error={metric.error:.6f} "
            f"> threshold={metric.threshold:.6f}"
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
