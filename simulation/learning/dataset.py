from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedPolicy, EconomicConstrainedConfig
from simulation.learning.experiments import collect


def build_dataset(
    episode_seeds: list[int],
    warmup_days: list[int],
    horizon: int,
    future_count: int,
) -> dict:
    rows = []

    policy = EconomicConstrainedPolicy(
        EconomicConstrainedConfig(
            target_days_of_cover=14,
            expedite_trigger_days=3,
        )
    )

    for episode_seed in episode_seeds:
        for warmup in warmup_days:

            engine = SimulationEngine(
                SimulationConfig(
                    random_seed=episode_seed,
                    number_of_days=warmup + horizon,
                ),
                export_dataset=False,
            )
            engine.initialize()
            engine.decision_policy = policy

            for _ in range(warmup):
                engine.run_day()
                engine.advance_day()

            future_seeds = [
                episode_seed * 100000 + warmup * 100 + i
                for i in range(1, future_count + 1)
            ]

            experiment = collect(
                engine=engine,
                horizon=horizon,
                future_seeds=future_seeds,
            )

            observation = experiment["observation"]

            for result in experiment["experiments"]:
                action = result["action"]
                labels = result["labels"]

                rows.append(
                    {
                        "episode_seed": episode_seed,
                        "decision_day": observation["simulation_day"],

                        "store_id": observation["store_id"],
                        "sku_id": observation["sku_id"],
                        "current_stock": observation["current_stock"],
                        "pending_units": observation["pending_units"],
                        "forecast_daily_demand": observation[
                            "forecast_daily_demand"
                        ],
                        "forecast_next_3d": observation[
                            "forecast_next_3d"
                        ],
                        "lead_time_days": observation["lead_time_days"],
                        "safety_stock": observation["safety_stock"],
                        "temperature_c": observation["temperature_c"],
                        "weather_condition": observation[
                            "weather_condition"
                        ],

                        "action_type": action["action_type"],
                        "action_quantity": action["quantity"],
                        "source_store_id": action["source_store_id"],

                        # Metadata only. Must never enter model features.
                        "future_seed": result["future_seed"],

                        # Learning target / evaluation labels.
                        "network_business_value": labels[
                            "network_business_value"
                        ],
                        "network_fill_rate": labels[
                            "network_fill_rate"
                        ],
                        "unmet_units": labels["unmet_units"],
                        "stockout_events": labels[
                            "stockout_events"
                        ],
                        "value_delta_vs_wait": labels[
                            "value_delta_vs_wait"
                        ],
                    }
                )

    return {
        "schema_version": "learning_dataset_v1",
        "metadata": {
            "episode_seeds": episode_seeds,
            "warmup_days": warmup_days,
            "horizon": horizon,
            "future_count": future_count,
            "future_seed_is_feature": False,
            "trained_model": False,
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default="artifacts/learning/dataset_v1.json",
    )
    parser.add_argument("--horizon", type=int, default=14)
    parser.add_argument("--futures", type=int, default=3)

    args = parser.parse_args()

    output = Path(args.output)

    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing dataset: {output}"
        )

    dataset = build_dataset(
        episode_seeds=[401, 402, 403],
        warmup_days=[0, 5, 10, 15, 20],
        horizon=args.horizon,
        future_count=args.futures,
    )

    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(dataset, indent=2),
        encoding="utf-8",
    )

    print(
        f"Saved {len(dataset['rows'])} learning rows "
        f"to {output}"
    )


if __name__ == "__main__":
    main()


