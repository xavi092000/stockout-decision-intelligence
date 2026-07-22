# V2 Scientific Hardening - Batch 2

## Scope
Statistical fidelity and structural consistency of synthetic scenarios.

## Changes

1. Product hierarchy is now sampled coherently:
   - category is sampled from calibrated category weights;
   - department is sampled only among departments belonging to that category.

2. Location hierarchy is now sampled coherently:
   - store is sampled from calibrated store weights;
   - state is derived from the selected store and matched to its calibrated state profile.

3. Calibration contracts are validated at engine startup:
   - every department must map to an existing category;
   - every store must map to an existing state;
   - malformed identifiers fail fast.

4. Scenario metadata now records the hierarchy sampling strategy.

## Scientific effect
- Eliminates impossible category/department combinations.
- Eliminates impossible store/state combinations.
- Preserves the calibrated category marginal distribution.
- Preserves the calibrated store distribution and its implied state mix.
- Does not expose or replay historical trajectories.

## Tests
Four tests cover hierarchy consistency, calibrated category frequencies, and invalid calibration rejection.

Validation in the patch environment:

    19 passed
