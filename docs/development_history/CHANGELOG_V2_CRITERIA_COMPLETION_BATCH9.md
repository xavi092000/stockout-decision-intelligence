# Batch 9 — Economic Robustness

## Objective
Close the economic validation criterion with a formal multi-scenario sensitivity protocol.

## Added
- Economic revaluation of paired operational trajectories without rerunning the simulator.
- Five mandatory economic scenarios: nominal, compressed margin, high holding cost, high service-failure cost, and high logistics cost.
- Per-scenario paired mean value delta, 95% confidence interval, value win rate, joint value/service win rate, and service-floor checks.
- A global robust-acceptance verdict that fails when any mandatory scenario fails.
- Economic robustness results embedded in the benchmark `summary.json`.
- Regression tests covering robust acceptance, stress rejection, service degradation, and invalid scenario definitions.

## Important
Installing this batch validates the protocol and code. A real policy is economically accepted only after running the 30+ unseen-seed benchmark and obtaining `economic_robustness.accepted = true` in the generated summary.
