# Sprint 7G V2 — 365-Day Simulation Orchestrator

This delivery assembles the validated domain-v2 engines into one annual
simulation loop.

## Daily order

1. Load the current `WorldState`.
2. Read the synthetic scenario for the day.
3. Receive supplier deliveries.
4. Generate sales and stockout events.
5. Create replenishment orders.
6. Update financial ledgers.
7. Run economic sanity checks.
8. Validate the domain.
9. Persist daily KPIs.
10. Advance to the next day.

## Outputs

`simulation/output/orchestrator_v2/`

- `world_state_v2_day_365.json`
- `sales_events_365_v2.csv`
- `stockout_events_365_v2.csv`
- `purchase_orders_365_v2.csv`
- `supplier_receipts_365_v2.csv`
- `daily_kpis_365_v2.csv`
- `sprint7g_v2_summary.json`

## Purpose

This is the stable annual baseline required before introducing a decision
policy or learning agent.
