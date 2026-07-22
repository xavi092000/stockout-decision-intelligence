# Sprint 5 — Economic Calibration Engine

## Goal

Convert public monthly economic indicators into simulator-safe distributions,
regime priors and operational multipliers.

## Required CSV

A monthly CSV containing a date column and at least two of:

- inflation or CPI;
- fuel or gasoline price;
- retail sales.

The installer searches `Downloads` automatically.

## Install

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT5.ps1
```

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT5.ps1
```

## Outputs

`reality_calibration/data/processed/economic_calibration/`

- `normalized_economic_data.csv`
- `economic_calibration_profile.json`
- `economic_calibration_summary.json`

## Economic regimes

- `cost_pressure`
- `expansion`
- `inflationary_growth`
- `stable`

Each regime produces:

- a calibrated probability;
- a demand multiplier;
- a logistics-cost multiplier.

## Leakage boundary

The simulator receives distributions, regime priors and operational
multipliers. It does not receive the historical monthly economic path.
