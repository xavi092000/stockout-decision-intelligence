# Sprint 8A V2 — Policy Comparison Engine

This delivery compares three replenishment policies under fair and
reproducible conditions.

## Policies

- `lean`: lower reorder points and target stock;
- `balanced`: current calibrated baseline;
- `service_first`: larger buffers and higher service protection.

## Fair comparison

Every policy receives:

- the same initial world;
- the same 365 synthetic scenarios;
- the same random seed;
- no access to future scenarios.

## Objective

The ranking uses calibrated net operating profit, with a large penalty when
a policy fails its minimum service-level constraint.

## Outputs

`simulation/output/policy_comparison_v2/`

- `policy_comparison_v2.csv`
- `policy_actions_v2.csv`
- `policy_comparison_summary_v2.json`
- one complete simulation output directory per policy
