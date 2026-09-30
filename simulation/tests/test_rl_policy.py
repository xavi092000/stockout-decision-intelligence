from pathlib import Path

from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.learning.rl_policy import QLearningConfig, QLearningInventoryPolicy


def test_rl_policy_runs_closed_loop_and_updates(tmp_path: Path):
    agent = QLearningInventoryPolicy(
        QLearningConfig(epsilon=0.2), seed=7, training=True
    )
    engine = SimulationEngine(
        SimulationConfig(random_seed=777, number_of_days=4,
                         number_of_products=2, number_of_stores=2),
        export_dataset=False,
    )
    engine.initialize()
    engine.decision_policy = agent
    for day in range(4):
        engine.run_day()
        rewards = engine.reward_engine.evaluate_day(
            day=engine.state.current_day,
            decisions=engine.last_decisions,
            outcome=engine.last_outcome,
        )
        agent.observe_day(rewards)
        if day < 3:
            engine.advance_day()
    agent.end_episode()
    assert agent.decision_count == 16
    assert agent.update_count == 16
    assert len(agent.q) > 0

    path = tmp_path / "q.json"
    agent.save(path)
    frozen = QLearningInventoryPolicy.load(path, training=False)
    assert frozen.q == agent.q


def test_frozen_policy_is_deterministic_for_same_seed(tmp_path: Path):
    path = tmp_path / "q.json"
    QLearningInventoryPolicy(training=False).save(path)
    outputs = []
    for _ in range(2):
        engine = SimulationEngine(
            SimulationConfig(random_seed=888, number_of_days=3,
                             number_of_products=2, number_of_stores=2),
            export_dataset=False,
        )
        engine.initialize()
        engine.decision_policy = QLearningInventoryPolicy.load(path, training=False)
        engine.run(verbose=False)
        outputs.append((engine.cumulative_economics.business_value,
                        tuple(engine.cumulative_action_counts.items())))
    assert outputs[0] == outputs[1]
