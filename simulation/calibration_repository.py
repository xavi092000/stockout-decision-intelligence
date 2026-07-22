from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CalibrationRepositoryError(RuntimeError):
    """Raised when a calibration contract is missing or malformed."""


class CalibrationRepository:
    def __init__(
        self,
        demand_dir: str | Path,
        weather_dir: str | Path,
        economic_dir: str | Path,
    ) -> None:
        self.demand_dir = Path(demand_dir)
        self.weather_dir = Path(weather_dir)
        self.economic_dir = Path(economic_dir)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise CalibrationRepositoryError(
                f"Calibration file not found: {path}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CalibrationRepositoryError(
                f"Invalid calibration JSON: {path.name}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise CalibrationRepositoryError(
                f"Calibration payload must be an object: {path.name}"
            )
        return payload

    def load(self) -> dict[str, Any]:
        demand_global = self._load_json(
            self.demand_dir / "global_profile.json"
        )
        category = self._load_json(
            self.demand_dir / "category_profiles.json"
        )
        department = self._load_json(
            self.demand_dir / "department_profiles.json"
        )
        store = self._load_json(
            self.demand_dir / "store_profiles.json"
        )
        state = self._load_json(
            self.demand_dir / "state_profiles.json"
        )
        demand_class = self._load_json(
            self.demand_dir / "demand_class_profiles.json"
        )
        weekday = self._load_json(
            self.demand_dir / "weekday_profiles.json"
        )
        weather = self._load_json(
            self.weather_dir / "weather_calibration_profile.json"
        )
        economic = self._load_json(
            self.economic_dir / "economic_calibration_profile.json"
        )

        demand_contract = demand_global.get("simulation_contract", {})
        weather_contract = weather.get("simulation_contract", {})
        economic_contract = economic.get("simulation_contract", {})

        if demand_contract.get("historical_rows_accessible_to_simulator") is not False:
            raise CalibrationRepositoryError(
                "Demand calibration leakage guard failed."
            )
        if weather_contract.get("historical_daily_path_accessible") is not False:
            raise CalibrationRepositoryError(
                "Weather calibration leakage guard failed."
            )
        if economic_contract.get("historical_monthly_path_accessible") is not False:
            raise CalibrationRepositoryError(
                "Economic calibration leakage guard failed."
            )

        return {
            "demand_global": demand_global,
            "category_profiles": category.get("profiles", []),
            "department_profiles": department.get("profiles", []),
            "store_profiles": store.get("profiles", []),
            "state_profiles": state.get("profiles", []),
            "demand_class_profiles": demand_class.get("profiles", []),
            "weekday_profiles": weekday.get("profiles", []),
            "weather_profile": weather,
            "economic_profile": economic,
        }
