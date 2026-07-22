from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PolicyGovernanceError(RuntimeError):
    """Raised when a governed policy violates registry rules."""


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    CHALLENGER = "CHALLENGER"
    CHAMPION = "CHAMPION"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class PolicyApproval:
    approved_by: str
    approved_at_utc: str
    reason: str

    @classmethod
    def create(
        cls,
        *,
        approved_by: str,
        reason: str,
    ) -> "PolicyApproval":
        if not approved_by.strip():
            raise PolicyGovernanceError(
                "approved_by must not be empty."
            )
        if not reason.strip():
            raise PolicyGovernanceError(
                "approval reason must not be empty."
            )

        return cls(
            approved_by=approved_by.strip(),
            approved_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            reason=reason.strip(),
        )


@dataclass(frozen=True)
class RegisteredPolicy:
    policy_id: str
    name: str
    version: str
    policy_type: str
    status: PolicyStatus
    description: str
    configuration: dict[str, Any]
    created_at_utc: str
    experiment_id: str | None = None
    model_artifact_path: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    approval: PolicyApproval | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str,
        version: str,
        policy_type: str,
        description: str,
        configuration: dict[str, Any],
        status: PolicyStatus = PolicyStatus.DRAFT,
        experiment_id: str | None = None,
        model_artifact_path: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> "RegisteredPolicy":
        clean_name = name.strip()
        clean_version = version.strip()
        clean_type = policy_type.strip()

        if not clean_name:
            raise PolicyGovernanceError(
                "Policy name must not be empty."
            )
        if not clean_version:
            raise PolicyGovernanceError(
                "Policy version must not be empty."
            )
        if not clean_type:
            raise PolicyGovernanceError(
                "Policy type must not be empty."
            )

        policy_id = f"{clean_name}:{clean_version}"

        return cls(
            policy_id=policy_id,
            name=clean_name,
            version=clean_version,
            policy_type=clean_type,
            status=status,
            description=description.strip(),
            configuration=dict(configuration),
            created_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            experiment_id=experiment_id,
            model_artifact_path=model_artifact_path,
            metrics=dict(metrics or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
