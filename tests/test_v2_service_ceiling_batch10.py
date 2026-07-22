from simulation.service_ceiling_policy import ServiceCeilingConfig, ServiceCeilingPolicy


def test_default_service_ceiling_configuration_is_aggressive():
    config = ServiceCeilingConfig()
    assert config.target_days_of_cover == 45.0
    assert config.always_expedite is True


def test_invalid_days_of_cover_is_rejected():
    try:
        ServiceCeilingConfig(target_days_of_cover=0)
    except ValueError as exc:
        assert "target_days_of_cover" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_policy_can_be_constructed():
    assert isinstance(ServiceCeilingPolicy(), ServiceCeilingPolicy)
