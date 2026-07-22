# V2 Scientific Hardening — Batch 4

## Objective
Strengthen ML validation and prevent seed leakage between model development and closed-loop benchmarking.

## Changes
- Added a centralized `EpisodeSeedSplit` contract.
- Preserved complete-episode train/validation/test boundaries.
- Added explicit overlap validation for development splits.
- Added a hard guard preventing benchmark seeds from overlapping seeds 1–100 used for training, validation, or testing.
- Added uniqueness, non-empty, and non-negative seed checks.
- Reused the same split contract in both training and robust benchmarking code.

## Criteria improved
- Validation ML
- Reproducibility
- Anti-leakage

## Compatibility
No architecture rewrite. Existing seed boundaries remain unchanged.
