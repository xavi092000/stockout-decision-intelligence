# Sprint 7B — Daily Inventory Engine

Sprint 7B advances the persistent synthetic world for 30 days.

## Capabilities

- daily demand allocation across all 1,000 store/SKU positions;
- inventory consumption;
- optional synthetic expiration;
- unmet-demand recording;
- no negative inventory;
- immutable movement ledger;
- one inventory snapshot per day;
- final persistent world state;
- inventory conservation checks.

## Deliberate boundary

Supplier purchase orders and receipts are not created yet. They belong to
Sprint 7C. Stock therefore decreases during this validation run.

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT7B.ps1
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7B.ps1
```

## Outputs

`simulation/output/inventory/`

- `inventory_day_001.csv` through `inventory_day_030.csv`
- `inventory_movements.csv`
- `inventory_daily_metrics.csv`
- `world_state_day_030.json`
- `inventory_run_summary.json`
