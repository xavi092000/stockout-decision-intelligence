from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simulation.governance.experiment_models import (
    ExperimentRecord,
    ExperimentRegistryError,
    ExperimentStatus,
)
from simulation.governance.experiment_registry import (
    ExperimentRegistry,
)


class ExperimentRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        registry_path = (
            Path(self.temp_directory.name)
            / "experiment_registry.json"
        )
        self.registry = ExperimentRegistry(
            registry_path
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def _experiment(
        *,
        experiment_id: str = "experiment-001",
        seeds: tuple[int, ...] = (101, 102, 103),
        policy_id: str = "balanced:1.0.0",
    ) -> ExperimentRecord:
        return ExperimentRecord.create(
            experiment_id=experiment_id,
            experiment_name="champion_evaluation",
            policy_id=policy_id,
            dataset_id="scenario-bundle-v1",
            seeds=seeds,
            configuration={
                "days": 365,
                "same_initial_world": True,
                "same_scenarios": True,
            },
            notes="Closed-loop policy evaluation.",
        )

    def test_register_and_retrieve_experiment(
        self,
    ) -> None:
        experiment = self._experiment()

        self.registry.register(experiment)
        retrieved = self.registry.get(
            experiment.experiment_id
        )

        self.assertEqual(
            retrieved.experiment_id,
            experiment.experiment_id,
        )
        self.assertEqual(
            retrieved.status,
            ExperimentStatus.CREATED,
        )
        self.assertEqual(
            retrieved.seeds,
            (101, 102, 103),
        )

    def test_same_inputs_create_same_fingerprint(
        self,
    ) -> None:
        first = self._experiment(
            experiment_id="experiment-001"
        )
        second = self._experiment(
            experiment_id="experiment-002"
        )

        self.assertEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_duplicate_fingerprint_is_rejected(
        self,
    ) -> None:
        first = self._experiment(
            experiment_id="experiment-001"
        )
        second = self._experiment(
            experiment_id="experiment-002"
        )

        self.registry.register(first)

        with self.assertRaises(ExperimentRegistryError):
            self.registry.register(second)

    def test_different_seeds_change_fingerprint(
        self,
    ) -> None:
        first = self._experiment(
            experiment_id="experiment-001",
            seeds=(101, 102, 103),
        )
        second = self._experiment(
            experiment_id="experiment-002",
            seeds=(104, 105, 106),
        )

        self.assertNotEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_experiment_can_be_completed(
        self,
    ) -> None:
        experiment = self._experiment()
        self.registry.register(experiment)
        self.registry.mark_running(
            experiment.experiment_id
        )

        completed = self.registry.complete(
            experiment_id=experiment.experiment_id,
            metrics={
                "mean_profit": 125000.0,
                "mean_fill_rate": 0.986,
            },
            manifest_path=(
                "simulation/output/experiments/"
                "experiment-001/manifest.json"
            ),
            status=ExperimentStatus.PASSED,
        )

        self.assertEqual(
            completed.status,
            ExperimentStatus.PASSED,
        )
        self.assertEqual(
            completed.metrics["mean_profit"],
            125000.0,
        )
        self.assertIsNotNone(
            completed.completed_at_utc
        )

    def test_duplicate_seeds_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(ExperimentRegistryError):
            self._experiment(
                seeds=(101, 101, 102),
            )


if __name__ == "__main__":
    unittest.main()
