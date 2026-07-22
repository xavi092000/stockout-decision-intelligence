# Sprint 7D V2 — Sales & Stockout Engine

This delivery adds explicit sales and stockout behavior to the shared
domain-v2 simulation.

## Daily sequence

1. Receive supplier deliveries due today.
2. Generate and allocate synthetic customer demand.
3. Sell available inventory.
4. Record lost units when demand exceeds availability.
5. Calculate realized revenue, lost revenue, cost of goods sold and gross
   margin.
6. Create replenishment orders.
7. Validate and persist the shared `WorldState`.

## Outputs

`simulation/output/sales_v2/`

- `sales_events_v2.csv`
- `stockout_events_v2.csv`
- `purchase_orders_v2.csv`
- `supplier_receipts_v2.csv`
- `sales_daily_metrics_v2.csv`
- `world_state_v2_day_180.json`
- `sprint7d_v2_summary.json`

## Key metrics

- requested units;
- sold units;
- lost units;
- fill rate;
- realized revenue;
- lost revenue;
- gross margin;
- stockout-event count.
