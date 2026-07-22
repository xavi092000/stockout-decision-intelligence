from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from simulation.governance.policy_models import (
    PolicyApproval,
    PolicyGovernanceError,
    PolicyStatus,
    RegisteredPolicy,
)


class PolicyRegistry:
    """
    Local persistent registry for governed decision policies.

    The registry stores policy metadata only. Operational policy
    implementations remain in simulation.decision.
    """

    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        registry_path: str | Path = (
            "simulation/output/governance/"
            "policy_registry.json"
        ),
    ) -> None:
        self.registry_path = Path(registry_path)

    def register(
        self,
        policy: RegisteredPolicy,
    ) -> RegisteredPolicy:
        registry = self._load()

        if policy.policy_id in registry["policies"]:
            raise PolicyGovernanceError(
                f"Policy already registered: {policy.policy_id}"
            )

        registry["policies"][policy.policy_id] = (
            policy.to_dict()
        )
        self._save(registry)
        return policy

    def get(
        self,
        policy_id: str,
    ) -> RegisteredPolicy:
        registry = self._load()
        payload = registry["policies"].get(policy_id)

        if payload is None:
            raise PolicyGovernanceError(
                f"Unknown policy: {policy_id}"
            )

        return self._deserialize(payload)

    def list_policies(
        self,
        *,
        status: PolicyStatus | None = None,
    ) -> list[RegisteredPolicy]:
        registry = self._load()

        policies = [
            self._deserialize(payload)
            for payload in registry["policies"].values()
        ]

        if status is not None:
            policies = [
                policy
                for policy in policies
                if policy.status == status
            ]

        return sorted(
            policies,
            key=lambda item: (
                item.name,
                item.version,
            ),
        )

    def approve(
        self,
        *,
        policy_id: str,
        approved_by: str,
        reason: str,
    ) -> RegisteredPolicy:
        policy = self.get(policy_id)

        if policy.status not in {
            PolicyStatus.CANDIDATE,
            PolicyStatus.CHALLENGER,
        }:
            raise PolicyGovernanceError(
                "Only candidate or challenger policies "
                "may be approved."
            )

        approval = PolicyApproval.create(
            approved_by=approved_by,
            reason=reason,
        )

        approved = replace(
            policy,
            approval=approval,
        )
        self._replace(approved)
        return approved

    def set_status(
        self,
        *,
        policy_id: str,
        status: PolicyStatus,
    ) -> RegisteredPolicy:
        policy = self.get(policy_id)

        if status == PolicyStatus.CHAMPION:
            if policy.approval is None:
                raise PolicyGovernanceError(
                    "A policy must be approved before becoming champion."
                )

            if policy.status not in {
                PolicyStatus.CANDIDATE,
                PolicyStatus.CHALLENGER,
                PolicyStatus.CHAMPION,
            }:
                raise PolicyGovernanceError(
                    "Only an approved candidate or challenger "
                    "may become champion."
                )

            self._retire_existing_champion(
                excluding_policy_id=policy_id
            )

        updated = replace(
            policy,
            status=status,
        )
        self._replace(updated)
        return updated

    def get_champion(self) -> RegisteredPolicy | None:
        champions = self.list_policies(
            status=PolicyStatus.CHAMPION
        )

        if len(champions) > 1:
            raise PolicyGovernanceError(
                "Registry contains multiple champion policies."
            )

        return champions[0] if champions else None

    def _replace(
        self,
        policy: RegisteredPolicy,
    ) -> None:
        registry = self._load()

        if policy.policy_id not in registry["policies"]:
            raise PolicyGovernanceError(
                f"Unknown policy: {policy.policy_id}"
            )

        registry["policies"][policy.policy_id] = (
            policy.to_dict()
        )
        self._save(registry)

    def _retire_existing_champion(
        self,
        *,
        excluding_policy_id: str,
    ) -> None:
        registry = self._load()

        for policy_id, payload in list(
            registry["policies"].items()
        ):
            if policy_id == excluding_policy_id:
                continue

            if payload.get("status") == (
                PolicyStatus.CHAMPION.value
            ):
                payload["status"] = (
                    PolicyStatus.RETIRED.value
                )

        self._save(registry)

    def _load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "schema_version": self.SCHEMA_VERSION,
                "policies": {},
            }

        try:
            payload = json.loads(
                self.registry_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise PolicyGovernanceError(
                f"Unable to read policy registry: {exc}"
            ) from exc

        if payload.get("schema_version") != (
            self.SCHEMA_VERSION
        ):
            raise PolicyGovernanceError(
                "Unsupported policy registry schema."
            )

        policies = payload.get("policies")
        if not isinstance(policies, dict):
            raise PolicyGovernanceError(
                "Registry policies must be an object."
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
            ),
            encoding="utf-8",
        )

        temporary_path.replace(self.registry_path)

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> RegisteredPolicy:
        approval_payload = payload.get("approval")
        approval = (
            PolicyApproval(**approval_payload)
            if approval_payload
            else None
        )

        return RegisteredPolicy(
            policy_id=str(payload["policy_id"]),
            name=str(payload["name"]),
            version=str(payload["version"]),
            policy_type=str(payload["policy_type"]),
            status=PolicyStatus(payload["status"]),
            description=str(payload["description"]),
            configuration=dict(
                payload.get("configuration", {})
            ),
            created_at_utc=str(
                payload["created_at_utc"]
            ),
            experiment_id=payload.get("experiment_id"),
            model_artifact_path=payload.get(
                "model_artifact_path"
            ),
            metrics=dict(payload.get("metrics", {})),
            approval=approval,
        )

