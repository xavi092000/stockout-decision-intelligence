from __future__ import annotations

"""Paired unseen-seed benchmark for frozen model-based V2."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean, median

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy
from simulation.learning.model_based_policy_v2 import ModelBasedInventoryPolicyV2

@dataclass(frozen=True)
class Result:
    seed: int; policy: str; business_value: float; service_level: float
    unmet_demand: int; stockouts: int; total_cost: float
    normal_order_units: int; expedite_order_units: int; transferred_units: int

def run(seed, days, policy, name):
    e = SimulationEngine(SimulationConfig(random_seed=seed, number_of_days=days), export_dataset=False)
    e.initialize(); e.decision_policy = policy; e.run(verbose=False); x=e.cumulative_economics
    return Result(seed,name,x.business_value,e.cumulative_service_level,e.cumulative_unmet_demand,
                  e.cumulative_stockouts,x.total_cost,x.normal_order_units,x.expedite_order_units,x.transferred_units)

def main():
    p=ArgumentParser()
    p.add_argument("--model", type=Path, default=Path("artifacts/model_based_v2/action_value_model.joblib"))
    p.add_argument("--test-seed-start", type=int, default=12000)
    p.add_argument("--test-episodes", type=int, default=20)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--output", type=Path, default=Path("artifacts/model_based_v2/benchmark.json"))
    a=p.parse_args()
    learned=ModelBasedInventoryPolicyV2(a.model)
    test=list(range(a.test_seed_start,a.test_seed_start+a.test_episodes))
    used=set(learned.metadata["train_episode_seeds"])|set(learned.metadata["validation_episode_seeds"])
    if used & set(test): p.error("FINAL TEST SEED LEAKAGE: test overlaps train/validation")
    rows=[]
    for i,s in enumerate(test,1):
        b=EconomicConstrainedPolicy(EconomicConstrainedConfig(target_days_of_cover=14,expedite_trigger_days=3))
        rows += [run(s,a.days,b,"BASELINE"), run(s,a.days,ModelBasedInventoryPolicyV2(a.model),"MODEL_BASED_V2")]
        print(f"TEST {i:03d}/{len(test)} seed={s}")
    by={}
    for r in rows: by.setdefault(r.seed,{})[r.policy]=r
    ds=[]
    for s in test:
        b,l=by[s]["BASELINE"],by[s]["MODEL_BASED_V2"]
        ds.append({"seed":s,"business_value_delta":l.business_value-b.business_value,
                   "service_level_delta":l.service_level-b.service_level,
                   "unmet_demand_delta":l.unmet_demand-b.unmet_demand,
                   "stockout_delta":l.stockouts-b.stockouts})
    v=[x["business_value_delta"] for x in ds]; sv=[x["service_level_delta"] for x in ds]
    summary={"schema_version":"stockout_model_based_v2_benchmark",
             "claim_status":"EXPERIMENTAL_NOT_PRODUCTION_APPROVED",
             "testing":{"seeds":test,"paired_unseen_seeds":True,"days":a.days},
             "paired_results":{"mean_business_value_delta":mean(v),"median_business_value_delta":median(v),
                "business_value_win_rate":sum(x>0 for x in v)/len(v),
                "mean_service_level_delta":mean(sv),
                "service_non_degradation_rate":sum(x>=0 for x in sv)/len(sv),
                "minimum_business_value_delta":min(v)},
             "episodes":[asdict(r) for r in rows],"deltas":ds}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print("\n=== MODEL-BASED V2 UNSEEN-SEED BENCHMARK ===")
    print(f"Mean value delta      : ${mean(v):,.2f}")
    print(f"Value win rate        : {sum(x>0 for x in v)/len(v):.1%}")
    print(f"Mean service delta    : {mean(sv):+.3%}")
    print(f"Service non-degrade   : {sum(x>=0 for x in sv)/len(sv):.1%}")
    print(f"Worst value delta     : ${min(v):,.2f}")

if __name__=="__main__": main()
