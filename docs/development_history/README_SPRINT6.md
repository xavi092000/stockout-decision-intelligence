# Sprint 6 — Synthetic Scenario Engine

## Goal

Combine demand, weather and economic calibration contracts into coherent
synthetic retail days.

## Install

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT6.ps1
```

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT6.ps1
```

The default run generates 365 synthetic days using seed `42`.

## Outputs

`simulation/output/scenarios/`

- `synthetic_scenarios.json`
- `synthetic_scenarios.jsonl`
- `synthetic_scenarios_summary.csv`
- `scenario_run_summary.json`

## Scenario contents

Each day includes:

- synthetic date and weekday;
- sampled demand profile;
- category, department, store and state;
- demand class;
- synthetic weather;
- economic regime;
- optional promotion;
- optional operational disruptions;
- final demand multiplier;
- final supply multiplier;
- logistics-cost multiplier;
- expected demand units.

## Leakage boundary

The engine reads only calibration contracts. Every scenario is marked:

- `synthetic = true`
- `historical_trajectory_used = false`

The historical M5, weather and economic paths are not read by this engine.
