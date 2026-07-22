from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class ExperimentRegistryError(RuntimeError):
    """Raised when experiment governance rules are violated."""


class ExperimentStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    fingerprint: str
    experiment_name: str
    policy_id: str
    dataset_id: str
    seeds: tuple[int, ...]
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    status: ExperimentStatus
    created_at_utc: str
    completed_at_utc: str | None = None
    manifest_path: str | None = None
    notes: str = ""
    leakage_safe: bool = True
    reproducible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        experiment_name: str,
        policy_id: str,
        dataset_id: str,
        seeds: Sequence[int],
        configuration: Mapping[str, Any],
        experiment_id: str | None = None,
        manifest_path: str | None = None,
        notes: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ExperimentRecord":
        clean_name = experiment_name.strip()
        clean_policy_id = policy_id.strip()
        clean_dataset_id = dataset_id.strip()
        clean_seeds = tuple(int(seed) for seed in seeds)

        if not clean_name:
            raise ExperimentRegistryError(
                "experiment_name must not be empty."
            )
        if not clean_policy_id:
            raise ExperimentRegistryError(
                "policy_id must not be empty."
            )
        if not clean_dataset_id:
            raise ExperimentRegistryError(
                "dataset_id must not be empty."
            )
        if not clean_seeds:
            raise ExperimentRegistryError(
                "At least one seed is required."
            )
        if len(set(clean_seeds)) != len(clean_seeds):
            raise ExperimentRegistryError(
                "Experiment seeds must be unique."
            )

        fingerprint_payload = {
            "experiment_name": clean_name,
            "policy_id": clean_policy_id,
            "dataset_id": clean_dataset_id,
            "seeds": sorted(clean_seeds),
            "configuration": dict(configuration),
        }

        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()

        generated_id = (
            experiment_id.strip()
            if experiment_id
            else (
                f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
                f"_{clean_name}_{fingerprint[:8]}"
            )
        )

        return cls(
            experiment_id=generated_id,
            fingerprint=fingerprint,
            experiment_name=clean_name,
            policy_id=clean_policy_id,
            dataset_id=clean_dataset_id,
            seeds=clean_seeds,
            configuration=dict(configuration),
            metrics={},
            status=ExperimentStatus.CREATED,
            created_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            manifest_path=manifest_path,
            notes=notes.strip(),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["seeds"] = list(self.seeds)
        return payload
