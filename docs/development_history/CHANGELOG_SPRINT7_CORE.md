# Sprint 7 Core Changelog

## Added

- Central domain package.
- Versioned world-state schema 2.0.0.
- Backward-compatible world-state factory.
- Strict supplier contract including `base_lead_time_days`.
- Purchase-order contract.
- Financial-ledger contract.
- JSON world repository.
- Daily scenario application contract.
- Compatibility report.
- Unit tests for critical invariants.

## Architectural effect

Future inventory, supplier, sales and financial engines must import the same
domain objects rather than redefining their own dictionaries or data classes.
