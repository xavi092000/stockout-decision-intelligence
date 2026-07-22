# Sprint 7F V2 — Economic Sanity & Cost Calibration

This delivery validates financial orders of magnitude before any decision
agent is trained.

## Important boundary

Revenue is not recalculated. The engine reuses the revenue and cost-of-goods
sold produced by the sales event ledger.

## Corrected cost model

Operating cost is modeled as:

- a fixed share of realized revenue;
- plus a variable cost per sold unit.

Holding cost is modeled as a target share of average inventory value.

## Sanity checks

- gross margin rate;
- operating cost as a share of revenue;
- holding cost as a share of inventory value;
- logistics cost as a share of procurement;
- inventory turnover;
- GMROI.

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT7F_V2.ps1
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7F_V2.ps1
```
