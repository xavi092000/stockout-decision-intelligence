from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.application.economic_sanity_runner_v2 import (
    EconomicSanityRunnerError,
    EconomicSanityRunnerV2,
)
from simulation.engines.economic_sanity_v2 import (
    EconomicSanityError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and recalibrate financial sanity."
    )
    parser.add_argument(
        "--financial-summary",
        type=Path,
        default=Path(
            "simulation/output/financial_v2/"
            "financial_summary_v2.json"
        ),
    )
    parser.add_argument(
        "--sales-metrics",
        type=Path,
        default=Path(
            "simulation/output/sales_v2/"
            "sales_daily_metrics_v2.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "simulation/output/economic_sanity_v2"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = EconomicSanityRunnerV2(
            financial_summary_path=args.financial_summary,
            sales_metrics_path=args.sales_metrics,
            output_dir=args.output_dir,
        ).run()
    except (
        EconomicSanityRunnerError,
        EconomicSanityError,
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

    print("\n" + "=" * 70)
    print("SPRINT 7F V2 — ECONOMIC SANITY & COST CALIBRATION")
    print("=" * 70)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 70)

    if result["status"] != "PASSED":
        print("STATUS: FAILED")
        return 1

    print("STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
