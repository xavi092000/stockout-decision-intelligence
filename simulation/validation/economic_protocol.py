from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EconomicAcceptanceCriteria:
    """Formal decision rule for claiming economic superiority.

    A candidate policy must improve value with statistical support while
    preserving an operational service floor. This avoids declaring a policy
    superior merely because it cuts inventory at the expense of customers.
    """

    minimum_episodes: int = 30
    minimum_service_level: float = 0.95
    maximum_mean_service_degradation: float = 0.0
    minimum_value_win_rate: float = 0.60
    minimum_joint_win_rate: float = 0.50
    require_positive_value_ci: bool = True

    def __post_init__(self) -> None:
        if self.minimum_episodes <= 1:
            raise ValueError("minimum_episodes must be greater than one.")
        for name, value in (
            ("minimum_service_level", self.minimum_service_level),
            ("minimum_value_win_rate", self.minimum_value_win_rate),
            ("minimum_joint_win_rate", self.minimum_joint_win_rate),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")


@dataclass(frozen=True)
class EconomicValidationResult:
    accepted: bool
    checks: dict[str, bool]
    reasons: tuple[str, ...]


def evaluate_economic_superiority(
    *,
    episode_count: int,
    candidate_average_service_level: float,
    mean_value_delta: float,
    value_ci95_low: float,
    mean_service_delta: float,
    value_win_rate: float,
    joint_value_service_win_rate: float,
    criteria: EconomicAcceptanceCriteria | None = None,
) -> EconomicValidationResult:
    criteria = criteria or EconomicAcceptanceCriteria()

    checks = {
        "enough_episodes": episode_count >= criteria.minimum_episodes,
        "service_floor": (
            candidate_average_service_level
            >= criteria.minimum_service_level
        ),
        "positive_mean_value": mean_value_delta > 0.0,
        "service_not_degraded": (
            mean_service_delta
            >= -criteria.maximum_mean_service_degradation
        ),
        "value_win_rate": (
            value_win_rate >= criteria.minimum_value_win_rate
        ),
        "joint_win_rate": (
            joint_value_service_win_rate
            >= criteria.minimum_joint_win_rate
        ),
        "positive_value_ci": (
            value_ci95_low > 0.0
            if criteria.require_positive_value_ci
            else True
        ),
    }

    reasons = tuple(
        name for name, passed in checks.items() if not passed
    )
    return EconomicValidationResult(
        accepted=all(checks.values()),
        checks=checks,
        reasons=reasons,
    )
