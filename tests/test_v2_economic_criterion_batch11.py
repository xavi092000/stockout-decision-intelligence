from simulation.benchmark_final_economic_criterion import confidence_interval_95
from simulation.economic_constrained_policy import (
    EconomicConstrainedConfig,
    EconomicConstrainedPolicy,
)


def test_default_policy_configuration_is_cost_aware():
    config = EconomicConstrainedConfig()
    assert config.target_days_of_cover == 21.0
    assert config.expedite_trigger_days == 7.0
    assert config.expedite_trigger_days < config.target_days_of_cover


def test_invalid_expedite_threshold_is_rejected():
    try:
        EconomicConstrainedConfig(
            target_days_of_cover=10,
            expedite_trigger_days=11,
        )
    except ValueError as exc:
        assert "cannot exceed" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_policy_can_be_constructed():
    assert isinstance(EconomicConstrainedPolicy(), EconomicConstrainedPolicy)


def test_confidence_interval_for_constant_values_is_exact():
    assert confidence_interval_95([2.0, 2.0, 2.0]) == (2.0, 2.0)


def test_confidence_interval_rejects_empty_input():
    try:
        confidence_interval_95([])
    except ValueError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
