# Sprint 7C V2 — Integrated Inventory and Supplier Engine

This delivery is the first engine package fully migrated to the shared
domain schema `2.0.0`.

## Architecture

Both engines operate on the same in-memory `WorldState` object:

1. due purchase orders are received;
2. synthetic demand consumes inventory;
3. positions below reorder point create purchase orders;
4. in-transit stock is updated;
5. the world is validated after every day;
6. the final world is persisted through `JsonWorldRepository`.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT7C_V2.ps1
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7C_V2.ps1
```

## Outputs

`simulation/output/domain_v2/`

- `world_state_v2_day_090.json`
- `inventory_movements_v2.csv`
- `purchase_orders_v2.csv`
- `supplier_receipts_v2.csv`
- `daily_metrics_v2.csv`
- `sprint7c_v2_summary.json`
