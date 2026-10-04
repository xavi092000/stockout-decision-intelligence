import pytest

from simulation.learning.counterfactual_dataset_v25 import CaptureTracker
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES


def test_periodic_capture_respects_spacing():
    t = CaptureTracker(period=3, cap_per_stratum=3)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=1)
    assert not t.should_capture("S1", "SKU1", "HEALTHY", day=2)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=4)


def test_cap_per_stratum():
    t = CaptureTracker(period=1, cap_per_stratum=2)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=1)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=2)
    assert not t.should_capture("S1", "SKU1", "HEALTHY", day=3)


def test_strata_capped_independently():
    t = CaptureTracker(period=1, cap_per_stratum=1)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=1)
    assert t.should_capture("S1", "SKU1", "EMERGENCY", day=2)
    assert not t.should_capture("S1", "SKU1", "HEALTHY", day=3)
    assert not t.should_capture("S1", "SKU1", "EMERGENCY", day=4)


def test_targets_tracked_independently():
    t = CaptureTracker(period=5, cap_per_stratum=1)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=1)
    assert t.should_capture("S2", "SKU1", "HEALTHY", day=1)
    assert not t.should_capture("S1", "SKU1", "HEALTHY", day=2)


def test_healthy_states_are_capturable():
    # regression guard: V24 never captured HEALTHY; V25 must allow it
    t = CaptureTracker(period=1, cap_per_stratum=1)
    assert t.should_capture("S1", "SKU1", "HEALTHY", day=1)


def test_model_features_contract_unchanged():
    assert len(MODEL_FEATURES) == 14
    assert "action_quantity" in MODEL_FEATURES
