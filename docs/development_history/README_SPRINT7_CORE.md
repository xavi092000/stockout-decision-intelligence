# Sprint 7 Core — Domain and Contract Refactor

This delivery consolidates Sprint 7 around a single versioned domain model.

## Why

The original Sprint 7 components exchanged JSON through implicit field
contracts. The first supplier integration exposed that weakness through a
missing `base_lead_time_days` field.

## Added

- unified `Supplier`, `Store`, `Product`, `InventoryPosition`,
  `PurchaseOrder`, `FinancialLedger` and `WorldState` models;
- schema version `2.0.0`;
- strict domain invariants;
- backward-compatible migration aliases;
- one JSON repository for loading and saving world state;
- explicit application contracts;
- compatibility report;
- unit tests.

## Migration

The current file:

`simulation/output/world/world_state_day_000.json`

is loaded through the compatibility factory and written as:

`simulation/output/core/world_state_v2_day_000.json`

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SPRINT7_CORE.ps1
powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7_CORE.ps1
```

## Expected result

The compatibility report must show:

- schema version `2.0.0`;
- supplier contract `PASSED`;
- domain validation `PASSED`;
- migration compatibility `PASSED`;
- zero duplicate inventory positions;
- zero unknown product suppliers;
- zero negative stock positions.
