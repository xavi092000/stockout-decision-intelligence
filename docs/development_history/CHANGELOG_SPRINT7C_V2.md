# Sprint 7C V2 Changelog

## Added

- Inventory engine using domain objects.
- Supplier engine using domain objects.
- Purchase-order creation through shared `PurchaseOrder`.
- Supplier receipts through shared `WorldState`.
- Integrated 90-day runner.
- Validation after every simulated day.
- Inventory conservation check.
- Domain-v2 output files.
- Contract tests for supplier and inventory fields.

## Removed architectural weakness

The engines no longer read or write arbitrary supplier dictionaries.
All supplier lead-time fields come from the central `Supplier` model.
