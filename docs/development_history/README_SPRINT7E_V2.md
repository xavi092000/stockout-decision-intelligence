# Sprint 7E V2 — Financial Analytics Engine

This engine aggregates existing operational events. It does not regenerate
sales or duplicate revenue logic.

## Sources of truth

- `sales_events_v2.csv`
- `stockout_events_v2.csv`
- `supplier_receipts_v2.csv`
- `products.csv`
- `stores.csv`
- inventory snapshots or final world state

## KPIs

- realized revenue
- lost revenue
- cost of goods sold
- gross margin
- stockout penalty cost
- procurement cost
- logistics cost
- holding cost
- operating cost
- net operating profit
- average inventory value
- inventory turnover
- GMROI
- fill rate

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT7E_V2.ps1
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7E_V2.ps1
```
