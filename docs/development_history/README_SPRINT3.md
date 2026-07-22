# Sprint 3 — Demand Calibration Engine

## Purpose

Transform Sprint 2 aggregate demand intelligence into stable, versioned,
simulator-safe calibration contracts.

The simulator never receives historical Walmart daily trajectories. It receives
only aggregate parameters and normalized factors from these JSON contracts.

## Install

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT3.ps1
```

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT3.ps1
```

## Outputs

Generated under:

`reality_calibration/data/processed/calibration/`

- `global_profile.json`
- `category_profiles.json`
- `department_profiles.json`
- `store_profiles.json`
- `state_profiles.json`
- `weekday_profiles.json`
- `demand_class_profiles.json`
- `calibration_summary.json`

## Leakage boundary

The exported contracts contain:

- aggregate moments;
- zero-sale probabilities;
- occurrence probabilities;
- estimated positive-demand parameters;
- category sampling weights;
- demand-class priors;
- normalized weekday factors.

They do not contain the historical 1,913-day demand path for any SKU/store
series. The future synthetic simulator must sample new trajectories.
