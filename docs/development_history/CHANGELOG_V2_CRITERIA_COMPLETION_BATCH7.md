# Batch 7 — Business Causality Validation

## Criterion addressed
Business causality.

## Changes
- Supply conditions now affect both expected receipt quantity and lead time.
- Added deterministic paired-counterfactual validation using identical seeds and initial world state.
- Added causal checks for:
  - demand -> requested units;
  - inventory constraint -> lost units;
  - supply capacity -> expected receipts;
  - supply conditions -> lead time;
  - logistics shock -> logistics cost.
- Added multi-day inventory conservation test across order creation and receipt.

## Acceptance evidence
The criterion is accepted only when all causal direction checks and the complete test suite pass.
