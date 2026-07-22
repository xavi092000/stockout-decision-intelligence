# V2 Criteria Completion — Batch 6: Statistical Fidelity

## Objective
Turn statistical fidelity from a qualitative claim into an executable validation contract.

## Added
- `simulation/validation/statistical_fidelity.py`
  - categorical distribution validation using total variation distance;
  - calibrated weather mean and event-frequency validation by month;
  - calibrated economic regime validation at the correct monthly persistence level;
  - promotion and operational event frequency checks;
  - product and location hierarchy integrity checks;
  - configurable thresholds and minimum sample-size guard;
  - machine-readable pass/fail report.
- `simulation/validate_statistical_fidelity.py`
  - command-line campaign generating 18,250 synthetic days by default;
  - JSON report under `artifacts/statistical_validation/report.json`;
  - non-zero exit code when any fidelity metric fails.
- `tests/test_v2_statistical_fidelity_batch6.py`
  - threshold-contract tests;
  - minimum-sample enforcement;
  - hierarchy proof;
  - full 50-year statistical campaign.

## Acceptance evidence in the build environment
- Dedicated Batch 6 tests: `4 passed`
- Full reconstructed repository suite: `48 passed`
- Statistical campaign: `PASS` on 18,250 scenarios

## Scientific boundary
The validator proves conformance to calibration contracts and declared generator probabilities. It does not claim that manually declared probabilities are externally calibrated unless their source data says so.
