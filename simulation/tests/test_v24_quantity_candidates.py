import math

import pytest

from simulation.action import ActionType
from simulation.learning.counterfactual_dataset_v24 import (
    ORDER_FRACTIONS,
    TRANSFER_FRACTIONS,
    build_v24_candidates,
    fraction_quantities,
    runtime_gap,
    validate_seed_split,
)
from simulation.learning.leakage_guard_v2 import MODEL_FEATURES


def test_gap_fraction_quantities_exact():
    assert fraction_quantities(100, ORDER_FRACTIONS) == [25, 50, 75, 100]


def test_duplicate_quantities_after_rounding_are_deduplicated():
    assert fraction_quantities(2, ORDER_FRACTIONS) == [1, 2]


def test_quantities_below_one_are_pruned():
    assert fraction_quantities(0, ORDER_FRACTIONS) == []
    assert fraction_quantities(1, ORDER_FRACTIONS) == [1]


def test_no_negative_or_zero_quantities():
    for gap in range(0, 50):
        for q in fraction_quantities(gap, ORDER_FRACTIONS):
            assert q >= 1


def test_orders_receive_multiple_quantities_when_gap_sufficient():
    cands = build_v24_candidates("S1", "SKU1", gap=100, donor_surpluses=[])
    for at in (ActionType.ORDER_NORMAL, ActionType.ORDER_EXPEDITE):
        qs = [c.quantity for c in cands if c.action_type == at]
        assert len(qs) >= 3
        assert qs == sorted(qs)


def test_transfer_respects_donor_surplus():
    cands = build_v24_candidates("S1", "SKU1", gap=100,
                                 donor_surpluses=[("S2", 10)])
    transfers = [c for c in cands if c.action_type == ActionType.TRANSFER_STOCK]
    assert transfers
    for t in transfers:
        assert t.quantity <= 10
        assert t.source_store_id == "S2"


def test_do_nothing_is_quantity_zero():
    cands = build_v24_candidates("S1", "SKU1", gap=100,
                                 donor_surpluses=[("S2", 50)])
    dn = [c for c in cands if c.action_type == ActionType.DO_NOTHING]
    assert len(dn) == 1
    assert dn[0].quantity == 0


def test_zero_gap_yields_only_do_nothing():
    cands = build_v24_candidates("S1", "SKU1", gap=0,
                                 donor_surpluses=[("S2", 50)])
    assert {c.action_type for c in cands} == {ActionType.DO_NOTHING}


def test_candidate_actions_are_deduplicated():
    cands = build_v24_candidates("S1", "SKU1", gap=3, donor_surpluses=[])
    keys = [(c.action_type, c.quantity, c.source_store_id) for c in cands]
    assert len(keys) == len(set(keys))


def test_runtime_gap_matches_policy_formula():
    assert runtime_gap(10.0, 5, 100, 20) == max(0, math.ceil(10.0 * 14.0 + 5 - 100 - 20))
    assert runtime_gap(1.0, 0, 999, 0) == 0


def test_model_features_contract_unchanged():
    expected = (
        "store_id", "sku_id", "current_stock", "pending_units",
        "forecast_daily_demand", "forecast_next_3d", "lead_time_days",
        "safety_stock", "temperature_c", "weather_condition", "simulation_day",
        "action_type", "action_quantity", "source_store_id",
    )
    assert MODEL_FEATURES == expected


def test_seed_split_validation():
    validate_seed_split([2000, 2001], [4000, 4001])
    with pytest.raises(ValueError):
        validate_seed_split([2000, 2001], [2001, 4000])
