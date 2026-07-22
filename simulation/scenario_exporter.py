from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from simulation.scenario_models import DayScenario


class ScenarioExporter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def export(self, scenarios: list[DayScenario]) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        payload = [scenario.to_dict() for scenario in scenarios]

        json_path = self.output_dir / "synthetic_scenarios.json"
        jsonl_path = self.output_dir / "synthetic_scenarios.jsonl"
        csv_path = self.output_dir / "synthetic_scenarios_summary.csv"

        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        with jsonl_path.open("w", encoding="utf-8") as stream:
            for row in payload:
                stream.write(
                    json.dumps(row, ensure_ascii=False) + "\n"
                )

        flattened = []
        for row in payload:
            flattened.append(
                {
                    "scenario_id": row["scenario_id"],
                    "simulation_day": row["simulation_day"],
                    "synthetic_date": row["synthetic_date"],
                    "weekday": row["weekday"],
                    "month": row["month"],
                    "season": row["season"],
                    "category": row["category"],
                    "department": row["department"],
                    "store": row["store"],
                    "state": row["state"],
                    "demand_class": row["demand_class"],
                    "temperature_c": row["temperature_c"],
                    "precipitation_mm": row["precipitation_mm"],
                    "snowfall_cm": row["snowfall_cm"],
                    "wind_kmh": row["wind_kmh"],
                    "weather_event_count": len(row["weather_events"]),
                    "economic_regime": row["economic_regime"],
                    "promotion_active": row["promotion"] is not None,
                    "operational_event_count": len(
                        row["operational_events"]
                    ),
                    "final_demand_multiplier": row[
                        "final_demand_multiplier"
                    ],
                    "final_supply_multiplier": row[
                        "final_supply_multiplier"
                    ],
                    "logistics_cost_multiplier": row[
                        "logistics_cost_multiplier"
                    ],
                    "expected_demand_units": row[
                        "expected_demand_units"
                    ],
                }
            )

        pd.DataFrame(flattened).to_csv(csv_path, index=False)

        return {
            "json_path": str(json_path.resolve()),
            "jsonl_path": str(jsonl_path.resolve()),
            "csv_path": str(csv_path.resolve()),
            "scenario_count": len(scenarios),
        }
