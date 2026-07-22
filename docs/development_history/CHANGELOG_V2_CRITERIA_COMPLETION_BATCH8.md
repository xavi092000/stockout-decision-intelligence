# Batch 8 — Synthetic Generation Completion

## Criterion completed
Synthetic generation quality is now measured independently from statistical fidelity.

## Added
- `simulation/validation/synthetic_generation.py`
- `simulation/validate_synthetic_generation.py`
- `tests/test_v2_synthetic_generation_batch8.py`
- `RUN_SYNTHETIC_GENERATION_VALIDATION.ps1`

## Objective acceptance gates
The campaign fails unless it demonstrates:
- unique scenario identifiers;
- non-degenerate business-state diversity;
- full coverage of calibrated categories, departments, stores, states, demand classes and economic regimes;
- full calendar and declared-event coverage;
- zero hierarchy violations;
- contiguous dates and simulation days;
- one economic regime per synthetic month;
- no historical-trajectory usage;
- exact same-seed reproducibility.

## Validation campaign
The default runner evaluates 18,250 synthetic days (50 years) and writes:

`artifacts/synthetic_generation/report.json`
