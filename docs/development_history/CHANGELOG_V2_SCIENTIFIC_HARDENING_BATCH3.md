# V2 Scientific Hardening — Batch 3

## Scope
Business causality and temporal persistence of economic conditions.

## Changes

- Replaced daily IID economic-regime sampling with one synthetic regime per calendar month.
- Aligned regime persistence with the monthly frequency of the economic calibration source.
- Added deterministic month-specific random streams so results do not depend on the order in which days are generated.
- Preserved calibrated regime marginal probabilities without exposing historical monthly trajectories.
- Added scenario metadata describing the temporal sampling contract.

## Scientific impact

- Prevents unrealistic economic regime changes from one day to the next.
- Makes economic effects on demand and logistics persist throughout a coherent business period.
- Improves causal continuity while retaining synthetic, leakage-safe paths.

## Validation

See `tests/test_v2_causal_persistence_batch3.py`.
