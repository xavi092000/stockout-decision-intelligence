# Sprint 4 — Weather Calibration Engine

## Goal

Convert public Montreal daily weather observations into simulator-safe
seasonal distributions and rare-event priors.

## Installation

The installer automatically searches `Downloads` for a CSV whose header
contains a date and temperature field. It then copies the selected file to the
project's weather data directory.

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT4.ps1
```

## Execution

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT4.ps1
```

## Outputs

`reality_calibration/data/processed/weather_calibration/`

- `normalized_weather.csv`
- `weather_calibration_profile.json`
- `weather_calibration_summary.json`

## Exported simulation knowledge

- monthly temperature distributions;
- seasonal temperature percentiles;
- precipitation probabilities and intensity;
- snowfall probabilities and intensity;
- high-wind probabilities;
- empirical priors for extreme cold, heat, rain, snow and wind.

## Leakage boundary

The simulation contract contains distributions and event priors. It does not
expose the historical daily weather trajectory to the future simulator.
