# Sprint 2 — Demand Intelligence Engine

## Purpose

Extract empirical demand laws from the original M5 Walmart dataset without
training directly on Walmart trajectories.

## Installation

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT2.ps1
```

## Execution

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT2.ps1
```

## Generated outputs

Located in:

`reality_calibration/data/processed/demand/`

- `series_demand_profiles.csv`
- `category_demand_profiles.csv`
- `department_demand_profiles.csv`
- `store_demand_profiles.csv`
- `state_demand_profiles.csv`
- `weekday_demand_profile.csv`
- `global_daily_demand.csv`
- `demand_analysis_summary.json`

## Demand taxonomy

The analyzer uses the Syntetos–Boylan ADI/CV² taxonomy:

- smooth
- intermittent
- erratic
- lumpy

These profiles will later calibrate the synthetic Demand Engine. They are not
used to replay Walmart sales trajectories.
