# Hardening V2 — Sprint 1

This patch is behavior-preserving: it centralizes the ML feature contract and
adds fail-fast validation for the serialized model and its metadata.

## Changes

- Added `simulation/ml/feature_contract.py` as the single source of truth for:
  - numeric features
  - categorical features
  - ordered model feature columns
  - pre-decision dataset features
  - target column
  - expected action classes
  - feature schema version
- Updated dataset generation, training, and inference to import the shared contract.
- Added model startup validation against:
  - `training_metadata.json`
  - model `feature_names_in_`
  - classifier `classes_`
  - optional schema version and expected actions
- Added tests for contract consistency and invalid artifacts.
- Updated the existing metadata with schema/action declarations.

## Validation

```text
python -m pytest -q simulation/tests
22 passed
```

No decision logic, quantity calculation, transfer guardrail, simulation rule,
or economic calculation was changed in this sprint.
