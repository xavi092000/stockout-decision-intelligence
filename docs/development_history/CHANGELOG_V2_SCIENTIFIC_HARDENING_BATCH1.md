# V2 Scientific Hardening — Batch 1

## Scope
Targeted corrections against the five acceptance criteria, without redesigning V2.

## Changes
- Removed duplicate application of `final_demand_multiplier` in both V2 demand-consumption engines. `expected_demand_units` already contains that calibrated multiplier upstream.
- Replaced the embedded `18.0` expression with an explicit, validated `demand_scale` constructor parameter while preserving `18.0` as the backward-compatible default.
- Propagated `final_supply_multiplier` into purchase-order expected quantities, bounded to valid domain limits.
- Added strict validation for negative demand and non-positive scenario multipliers.
- Added regression tests covering demand causality, supply causality, bounds, and invalid inputs.

## Criteria improved
1. Synthetic generation: scenario magnitudes now have one unambiguous application point.
2. Statistical fidelity: calibrated demand shocks are no longer squared downstream.
3. Business causality: supply disruptions now affect expected receipts.
4. ML validation: invalid scenario rows fail fast instead of silently contaminating datasets.
5. Economic validation: demand and supply magnitudes now flow consistently into sales and procurement outcomes.
