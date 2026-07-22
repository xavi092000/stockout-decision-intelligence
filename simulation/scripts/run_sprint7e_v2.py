from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.financial_runner_v2 import (
    FinancialRunnerV2,
    FinancialRunnerV2Error,
)
from simulation.engines.financial_v2 import FinancialEngineV2Error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate domain-v2 financial KPIs."
    )
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument(
        "--sales-dir",
        type=Path,
        default=Path("simulation/output/sales_v2"),
    )
    parser.add_argument(
        "--world-dir",
        type=Path,
        default=Path("simulation/output/world"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation/output/financial_v2"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        summary = FinancialRunnerV2(
            sales_dir=args.sales_dir,
            world_dir=args.world_dir,
            output_dir=args.output_dir,
        ).run(days=args.days)
    except (
        FinancialRunnerV2Error,
        FinancialEngineV2Error,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        print(json.dumps(
            {"status": "FAILED", "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        ))
        return 1

    print("\n" + "=" * 68)
    print("SPRINT 7E V2 — FINANCIAL ANALYTICS ENGINE")
    print("=" * 68)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 68)
    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
