# V25 — Decision Intelligence Evidence File

## 1. Objective

Demonstrate that a learned action-value policy, selecting **both action type and quantity** as a function of system state, can outperform a deterministic inventory policy (`EconomicConstrainedPolicy`) on business value in closed-loop simulation, without degrading service.

## 2. Model Architecture

- Pipeline: `ColumnTransformer(OneHotEncoder on categoricals) + RandomForestRegressor(n_estimators=300, min_samples_leaf=3)` (scikit-learn)
- Target: `delta_value_vs_wait` — counterfactual 21-day business-value delta of an action vs doing nothing, under a fixed continuation policy, on identical demand futures (paired labels)
- Features (14, unchanged since V2): `store_id, sku_id, current_stock, pending_units, forecast_daily_demand, forecast_next_3d, lead_time_days, safety_stock, temperature_c, weather_condition, simulation_day, action_type, action_quantity, source_store_id`
- No guard, threshold, or post-hoc heuristic is applied to model output

## 3. Dataset Construction

- Generator: `simulation/learning/counterfactual_dataset_v25.py` — periodic full-trajectory state capture (period 2 days, cap 4 per stratum under economic roll-in, cap 1 under do-nothing roll-in)
- **122 unique states, 2,568 rows, 306 state-future groups**
- Strata coverage (rows): HEALTHY 1,318 / LOW_STOCK 700 / EMERGENCY 370 / HIGH_RISK 180
- `pending_units > 0`: 54.1% of states · `coverage > 14 days`: 46.7% · coverage median 13.6, max 21.7
- Counterfactual action space per state: `DO_NOTHING(0)`; `ORDER_NORMAL`/`ORDER_EXPEDITE` at 25/50/75/100% of the 14-day coverage gap; `TRANSFER_STOCK` at 50/100% of feasible surplus; quantities ceiled, deduplicated, pruned below 1
- Labels: paired outcomes under identical demand futures (2 futures per state, 21-day horizon, EconomicConstrainedPolicy continuation)
- Anti-leakage: future outcomes are labels only; feature contract validated; 0 duplicate rows

## 4. Baseline

`EconomicConstrainedPolicy(target_days_of_cover=14, expedite_trigger_days=3)` — deterministic reorder policy. Identical scenarios, same seed for baseline and V25 in every comparison.

## 5. Experimental Protocol

- Train/validation/test seeds fully disjoint
- No tuning on test seeds; model frozen before the 60-day and 365-day tests
- Benchmarks: paired closed-loop runs, per-seed results saved immediately, resumable
- Statistics: per-seed business-value deltas; 95% CI on the mean (Student t, df=9)

## 6. Held-Out Seed Policy

| Split | Seeds |
|---|---|
| Training | 2000–2003 |
| Offline validation | 4000–4001 |
| Diagnostic/dev (V24 failure analysis) | 13003–13005 |
| **Final held-out test** | **14000–14009** (verified unused anywhere else in the repo) |

## 7. 60-Day Results (10 held-out seeds)

- Mean delta: **+$8,894.00** · median +$9,030.25 · CI95 [+$6,526.32, +$11,261.68]
- Worst +$4,489.30 · best +$15,514.20 · **wins 10/10**
- Service delta +0.0000 · stockout/unmet delta 0 · aggregate +$88,940.00
- Source: `artifacts/model_based_v25/final_60d/`

## 8. 365-Day Results (10 held-out seeds)

- Mean delta: **+$29,824.74** · median +$33,063.42 · CI95 [+$21,773.55, +$37,875.92]
- Worst +$9,803.65 · best +$41,665.45 · **wins 10/10**
- Service delta +0.0000 · stockouts/unmet unchanged on every seed · aggregate +$298,247.35
- Source: `artifacts/model_based_v25/final_365d/`

## 9. Decision Behavior (60-day test, 60,000 decisions)

| Action | Count | Avg quantity |
|---|---:|---:|
| DO_NOTHING | 39,923 | 0 |
| ORDER_NORMAL | 19,323 | 73.5 (56.2–91.2 across seeds) |
| ORDER_EXPEDITE | 754 | 14.7 (9.7–21.1 across seeds) |
| TRANSFER_STOCK | 0 | — |

The policy varies quantity by state and uses expedites sparingly (~1.2%). Zero transfers is an observed outcome in these scenarios, not a rule.

## 10. Statistical Evidence

- 60d: CI95 of the mean paired delta entirely positive: [+$6.5K, +$11.3K]
- 365d: CI95 entirely positive: [+$21.8K, +$37.9K]
- Offline sanity (80 held-out validation groups): mean action regret 50.3, p95 327.1, action-type accuracy 75.0%, action+quantity accuracy 58.8%
- Pre-registered gates were used: 60-day gate (mean>0, wins≥6/10, service≥−0.005, no catastrophic seed) passed; 365-day criterion (CI95>0, service acceptable) passed

## 11. Limitations

- Results hold within this simulator, its demand model, cost structure, and the tested held-out scenarios only
- The baseline is one deterministic policy; superiority over all possible policies is not claimed
- Absolute gain (~+0.3% of annual business value) is modest relative to scenario scale
- Labels are 21-day finite-horizon returns under a fixed continuation policy, not optimal Q-values
- Real-world production performance is **not** demonstrated

## 12. Reproduction Commands

```powershell
& .venv\Scripts\python.exe -m pytest simulation/tests -q
& .venv\Scripts\python.exe -m simulation.learning.counterfactual_dataset_v25 --period 2 --cap-per-stratum 4
& .venv\Scripts\python.exe -m simulation.learning.train_action_value_v25
& .venv\Scripts\python.exe run_v25_60d.py
& .venv\Scripts\python.exe run_v25_365d.py
& .venv\Scripts\python.exe scripts\generate_v25_proof_charts.py
```

Note: `run_v25_60d.py` / `run_v25_365d.py` resume from saved per-seed results; delete `artifacts/model_based_v25/final_*` to force a full re-run. Dataset generator refuses to overwrite an existing dataset.

## 13. Final Verdict

- **Decision intelligence demonstrated in simulation: YES**
- **Economic superiority over the deterministic baseline on tested held-out scenarios: YES**
- **Real-world production performance demonstrated: NO**
