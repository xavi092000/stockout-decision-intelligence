from __future__ import annotations

"""Train and evaluate Stockout's first closed-loop RL policy.

No training seed is reused for final evaluation.  The baseline and frozen RL
policy are evaluated on identical unseen seeds.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean, median

from simulation.config import SimulationConfig
from simulation.economic_constrained_policy import EconomicConstrainedConfig, EconomicConstrainedPolicy
from simulation.engine import SimulationEngine
from simulation.learning.rl_policy import QLearningConfig, QLearningInventoryPolicy


@dataclass(frozen=True)
class EpisodeResult:
    seed: int
    policy: str
    business_value: float
    service_level: float
    unmet_demand: int
    stockouts: int
    total_cost: float
    normal_order_units: int
    expedite_order_units: int
    transferred_units: int


def run_training_episode(agent: QLearningInventoryPolicy, *, seed: int, days: int) -> None:
    engine = SimulationEngine(SimulationConfig(random_seed=seed, number_of_days=days), export_dataset=False)
    engine.initialize()
    engine.decision_policy = agent
    for day in range(days):
        engine.run_day()
        rewards = engine.reward_engine.evaluate_day(
            day=engine.state.current_day, decisions=engine.last_decisions, outcome=engine.last_outcome
        )
        agent.observe_day(rewards)
        if day < days - 1:
            engine.advance_day()
    agent.end_episode()


def run_evaluation(*, seed: int, days: int, policy, name: str) -> EpisodeResult:
    engine = SimulationEngine(SimulationConfig(random_seed=seed, number_of_days=days), export_dataset=False)
    engine.initialize()
    engine.decision_policy = policy
    engine.run(verbose=False)
    econ = engine.cumulative_economics
    return EpisodeResult(
        seed=seed, policy=name, business_value=econ.business_value,
        service_level=engine.cumulative_service_level,
        unmet_demand=engine.cumulative_unmet_demand,
        stockouts=engine.cumulative_stockouts, total_cost=econ.total_cost,
        normal_order_units=econ.normal_order_units,
        expedite_order_units=econ.expedite_order_units,
        transferred_units=econ.transferred_units,
    )


def main() -> None:
    p = ArgumentParser()
    p.add_argument("--train-episodes", type=int, default=60)
    p.add_argument("--train-days", type=int, default=180)
    p.add_argument("--test-episodes", type=int, default=20)
    p.add_argument("--test-days", type=int, default=365)
    p.add_argument("--train-seed-start", type=int, default=1000)
    p.add_argument("--test-seed-start", type=int, default=9000)
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/rl_v1"))
    args = p.parse_args()
    if min(args.train_episodes, args.train_days, args.test_episodes, args.test_days) < 1:
        p.error("episode/day counts must be positive")
    train_seeds = list(range(args.train_seed_start, args.train_seed_start + args.train_episodes))
    test_seeds = list(range(args.test_seed_start, args.test_seed_start + args.test_episodes))
    if set(train_seeds) & set(test_seeds):
        p.error("training and test seeds must be disjoint")

    agent = QLearningInventoryPolicy(QLearningConfig(), seed=20260929, training=True)
    for i, seed in enumerate(train_seeds, 1):
        # Exploration decays, but never vanishes during training.
        eps = max(0.03, 0.20 * (1.0 - (i - 1) / max(1, args.train_episodes)))
        agent.config = QLearningConfig(**{**agent.config.__dict__, "epsilon": eps})
        run_training_episode(agent, seed=seed, days=args.train_days)
        if i == 1 or i % 10 == 0 or i == args.train_episodes:
            print(f"TRAIN {i:03d}/{args.train_episodes} seed={seed} states={len(agent.q)} epsilon={eps:.3f}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "q_policy.json"
    agent.save(model_path)

    rows: list[EpisodeResult] = []
    for i, seed in enumerate(test_seeds, 1):
        baseline = EconomicConstrainedPolicy(EconomicConstrainedConfig(target_days_of_cover=14, expedite_trigger_days=3))
        frozen = QLearningInventoryPolicy.load(model_path, training=False, seed=seed)
        rows.append(run_evaluation(seed=seed, days=args.test_days, policy=baseline, name="ECONOMIC_CONSTRAINED"))
        rows.append(run_evaluation(seed=seed, days=args.test_days, policy=frozen, name="RL_Q_LEARNING"))
        print(f"TEST  {i:03d}/{args.test_episodes} seed={seed}")

    by_seed = {}
    for row in rows:
        by_seed.setdefault(row.seed, {})[row.policy] = row
    deltas = []
    for seed in test_seeds:
        base = by_seed[seed]["ECONOMIC_CONSTRAINED"]
        rl = by_seed[seed]["RL_Q_LEARNING"]
        deltas.append({
            "seed": seed,
            "business_value_delta": rl.business_value - base.business_value,
            "service_level_delta": rl.service_level - base.service_level,
            "unmet_demand_delta": rl.unmet_demand - base.unmet_demand,
            "stockout_delta": rl.stockouts - base.stockouts,
        })

    values = [d["business_value_delta"] for d in deltas]
    services = [d["service_level_delta"] for d in deltas]
    summary = {
        "schema_version": "stockout_rl_benchmark_v1",
        "claim_status": "EXPERIMENTAL_NOT_PRODUCTION_APPROVED",
        "training": {
            "episodes": args.train_episodes, "days_per_episode": args.train_days,
            "seed_start": args.train_seed_start, "seed_end": train_seeds[-1],
            "q_states": len(agent.q), "updates": agent.update_count,
        },
        "testing": {
            "episodes": args.test_episodes, "days_per_episode": args.test_days,
            "seed_start": args.test_seed_start, "seed_end": test_seeds[-1],
            "paired_unseen_seeds": True,
        },
        "paired_results": {
            "mean_business_value_delta": mean(values),
            "median_business_value_delta": median(values),
            "business_value_win_rate": sum(v > 0 for v in values) / len(values),
            "mean_service_level_delta": mean(services),
            "service_non_degradation_rate": sum(v >= 0 for v in services) / len(services),
            "minimum_business_value_delta": min(values),
        },
        "episodes": [asdict(r) for r in rows],
        "deltas": deltas,
    }
    (args.output_dir / "benchmark.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== RL V1 UNSEEN-SEED BENCHMARK ===")
    print(f"Mean value delta      : ${mean(values):,.2f}")
    print(f"Median value delta    : ${median(values):,.2f}")
    print(f"Value win rate        : {summary['paired_results']['business_value_win_rate']:.1%}")
    print(f"Mean service delta    : {mean(services):+.3%}")
    print(f"Service non-degrade   : {summary['paired_results']['service_non_degradation_rate']:.1%}")
    print(f"Worst value delta     : ${min(values):,.2f}")
    print(f"Artifact              : {model_path}")
    print(f"Benchmark             : {args.output_dir / 'benchmark.json'}")


if __name__ == "__main__":
    main()
