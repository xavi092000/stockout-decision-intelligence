from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from simulation.governance.experiment_models import (
    ExperimentRecord,
    ExperimentRegistryError,
    ExperimentStatus,
)


class ExperimentRegistry:
    """
    Persistent catalogue of governed experiments.

    This registry stores experiment metadata. Large artifacts remain managed
    by ExperimentManagerV2 and are referenced through manifest_path.
    """

    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        registry_path: str | Path = (
            "simulation/output/governance/"
            "experiment_registry.json"
        ),
    ) -> None:
        self.registry_path = Path(registry_path)

    def register(
        self,
        experiment: ExperimentRecord,
    ) -> ExperimentRecord:
        registry = self._load()

        if experiment.experiment_id in registry["experiments"]:
            raise ExperimentRegistryError(
                "Experiment ID already registered: "
                f"{experiment.experiment_id}"
            )

        existing_fingerprint = next(
            (
                payload["experiment_id"]
                for payload in registry["experiments"].values()
                if payload.get("fingerprint")
                == experiment.fingerprint
            ),
            None,
        )

        if existing_fingerprint is not None:
            raise ExperimentRegistryError(
                "Equivalent experiment already registered: "
                f"{existing_fingerprint}"
            )

        registry["experiments"][
            experiment.experiment_id
        ] = experiment.to_dict()

        self._save(registry)
        return experiment

    def get(
        self,
        experiment_id: str,
    ) -> ExperimentRecord:
        registry = self._load()
        payload = registry["experiments"].get(
            experiment_id
        )

        if payload is None:
            raise ExperimentRegistryError(
                f"Unknown experiment: {experiment_id}"
            )

        return self._deserialize(payload)

    def find_by_fingerprint(
        self,
        fingerprint: str,
    ) -> ExperimentRecord | None:
        registry = self._load()

        for payload in registry["experiments"].values():
            if payload.get("fingerprint") == fingerprint:
                return self._deserialize(payload)

        return None

    def list_experiments(
        self,
        *,
        policy_id: str | None = None,
        status: ExperimentStatus | None = None,
    ) -> list[ExperimentRecord]:
        registry = self._load()

        experiments = [
            self._deserialize(payload)
            for payload in registry["experiments"].values()
        ]

        if policy_id is not None:
            experiments = [
                experiment
                for experiment in experiments
                if experiment.policy_id == policy_id
            ]

        if status is not None:
            experiments = [
                experiment
                for experiment in experiments
                if experiment.status == status
            ]

        return sorted(
            experiments,
            key=lambda experiment: (
                experiment.created_at_utc,
                experiment.experiment_id,
            ),
        )

    def mark_running(
        self,
        experiment_id: str,
    ) -> ExperimentRecord:
        experiment = self.get(experiment_id)

        if experiment.status != ExperimentStatus.CREATED:
            raise ExperimentRegistryError(
                "Only CREATED experiments may enter RUNNING."
            )

        updated = replace(
            experiment,
            status=ExperimentStatus.RUNNING,
        )
        self._replace(updated)
        return updated

    def complete(
        self,
        *,
        experiment_id: str,
        metrics: Mapping[str, Any],
        manifest_path: str | None = None,
        status: ExperimentStatus = ExperimentStatus.PASSED,
    ) -> ExperimentRecord:
        experiment = self.get(experiment_id)

        if experiment.status not in {
            ExperimentStatus.CREATED,
            ExperimentStatus.RUNNING,
        }:
            raise ExperimentRegistryError(
                "Only CREATED or RUNNING experiments "
                "may be completed."
            )

        if status not in {
            ExperimentStatus.PASSED,
            ExperimentStatus.FAILED,
            ExperimentStatus.REJECTED,
        }:
            raise ExperimentRegistryError(
                "Completion status must be PASSED, FAILED "
                "or REJECTED."
            )

        updated = replace(
            experiment,
            metrics=dict(metrics),
            status=status,
            completed_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            manifest_path=(
                manifest_path
                if manifest_path is not None
                else experiment.manifest_path
            ),
        )

        self._replace(updated)
        return updated

    def _replace(
        self,
        experiment: ExperimentRecord,
    ) -> None:
        registry = self._load()

        if experiment.experiment_id not in (
            registry["experiments"]
        ):
            raise ExperimentRegistryError(
                "Unknown experiment: "
                f"{experiment.experiment_id}"
            )

        registry["experiments"][
            experiment.experiment_id
        ] = experiment.to_dict()

        self._save(registry)

    def _load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "schema_version": self.SCHEMA_VERSION,
                "experiments": {},
            }

        try:
            payload = json.loads(
                self.registry_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ExperimentRegistryError(
                f"Unable to read experiment registry: {exc}"
            ) from exc

        if payload.get("schema_version") != (
            self.SCHEMA_VERSION
        ):
            raise ExperimentRegistryError(
                "Unsupported experiment registry schema."
            )

        experiments = payload.get("experiments")
        if not isinstance(experiments, dict):
            raise ExperimentRegistryError(
                "Registry experiments must be an object."
            )

        return payload

    def _save(
        self,
        payload: dict[str, Any],
    ) -> None:
        self.registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.registry_path.with_suffix(
            ".tmp"
        )

        temporary_path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(self.registry_path)

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> ExperimentRecord:
        return ExperimentRecord(
            experiment_id=str(payload["experiment_id"]),
            fingerprint=str(payload["fingerprint"]),
            experiment_name=str(
                payload["experiment_name"]
            ),
            policy_id=str(payload["policy_id"]),
            dataset_id=str(payload["dataset_id"]),
            seeds=tuple(
                int(seed)
                for seed in payload.get("seeds", [])
            ),
            configuration=dict(
                payload.get("configuration", {})
            ),
            metrics=dict(payload.get("metrics", {})),
            status=ExperimentStatus(payload["status"]),
            created_at_utc=str(
                payload["created_at_utc"]
            ),
            completed_at_utc=payload.get(
                "completed_at_utc"
            ),
            manifest_path=payload.get("manifest_path"),
            notes=str(payload.get("notes", "")),
            leakage_safe=bool(
                payload.get("leakage_safe", True)
            ),
            reproducible=bool(
                payload.get("reproducible", True)
            ),
            metadata=dict(payload.get("metadata", {})),
        )
