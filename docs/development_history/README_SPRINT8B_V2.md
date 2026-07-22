# Sprint 8B V2 — Adaptive Decision Policy

The adaptive engine chooses `lean`, `balanced` or `service_first` each day.

## Inputs available to the decision

- current inventory state;
- current open orders;
- same-day demand and supply multipliers;
- current economic regime;
- trailing realized sales and fill-rate metrics.

## Forbidden inputs

- future scenarios;
- future demand;
- future deliveries;
- future financial outcomes.

## Outputs

`simulation/output/adaptive_policy_v2/`

- `decision_history_v2.csv`
- `adaptive_policy_actions_v2.csv`
- `adaptive_daily_kpis_v2.csv`
- sales, stockout, order and receipt ledgers
- `world_state_adaptive_day_365.json`
- `sprint8b_v2_summary.json`
