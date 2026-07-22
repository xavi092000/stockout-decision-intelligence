# Sprint 7C — Supplier & Orders Engine

Sprint 7C integrates inventory consumption with supplier replenishment for
90 synthetic days.

## Daily sequence

1. Receive purchase orders due today.
2. Apply synthetic customer demand.
3. Detect inventory positions at or below their reorder point.
4. Create purchase orders up to target stock.
5. Add expected units to `in_transit`.
6. Persist order, receipt and daily supply metrics.

## Supplier behavior

Each supplier has:

- base lead time;
- lead-time variability;
- fill rate;
- reliability score;
- logistics cost per unit.

Orders may arrive late or in multiple deliveries.

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT7C.ps1
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7C.ps1
```

## Outputs

`simulation/output/supply/`

- `purchase_orders.csv`
- `supplier_receipts.csv`
- `inventory_movements.csv`
- `supply_daily_metrics.csv`
- `world_state_day_090.json`
- `supply_run_summary.json`
