from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class ScenarioValidationError(RuntimeError):
    pass


def validate_scenarios(
    output_dir: str | Path,
    expected_days: int,
) -> dict:
    output = Path(output_dir)
    required = (
        "synthetic_scenarios.json",
        "synthetic_scenarios.jsonl",
        "synthetic_scenarios_summary.csv",
    )

    missing = [name for name in required if not (output / name).is_file()]
    if missing:
        raise ScenarioValidationError(
            "Missing scenario output(s): " + ", ".join(missing)
        )

    scenarios = json.loads(
        (output / "synthetic_scenarios.json").read_text(
            encoding="utf-8"
        )
    )
    summary = pd.read_csv(output / "synthetic_scenarios_summary.csv")

    if len(scenarios) != expected_days:
        raise ScenarioValidationError(
            f"Expected {expected_days} scenarios, got {len(scenarios)}."
        )
    if len(summary) != expected_days:
        raise ScenarioValidationError(
            f"CSV expected {expected_days} rows, got {len(summary)}."
        )
    if summary["scenario_id"].duplicated().any():
        raise ScenarioValidationError("Duplicate scenario IDs detected.")
    if summary["synthetic_date"].duplicated().any():
        raise ScenarioValidationError(
            "Duplicate synthetic dates detected."
        )
    if not summary["final_demand_multiplier"].gt(0).all():
        raise ScenarioValidationError(
            "Non-positive demand multiplier detected."
        )
    if not summary["final_supply_multiplier"].gt(0).all():
        raise ScenarioValidationError(
            "Non-positive supply multiplier detected."
        )
    if not summary["logistics_cost_multiplier"].gt(0).all():
        raise ScenarioValidationError(
            "Non-positive logistics multiplier detected."
        )
    if not summary["expected_demand_units"].ge(0).all():
        raise ScenarioValidationError(
            "Negative expected demand detected."
        )

    for scenario in scenarios:
        metadata = scenario.get("metadata", {})
        if metadata.get("synthetic") is not True:
            raise ScenarioValidationError(
                "A scenario is not marked synthetic."
            )
        if metadata.get("historical_trajectory_used") is not False:
            raise ScenarioValidationError(
                "Historical trajectory leakage detected."
            )

    regime_share = (
        summary["economic_regime"]
        .value_counts(normalize=True)
        .sort_index()
        .to_dict()
    )

    return {
        "status": "PASSED",
        "checked_files": len(required),
        "scenario_count": len(scenarios),
        "date_count": summary["synthetic_date"].nunique(),
        "promotion_days": int(summary["promotion_active"].sum()),
        "weather_event_days": int(
            summary["weather_event_count"].gt(0).sum()
        ),
        "operational_event_days": int(
            summary["operational_event_count"].gt(0).sum()
        ),
        "economic_regime_share": regime_share,
        "leakage_guard": "PASSED",
    }
