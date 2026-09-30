from simulation.learning.leakage_guard_v2 import MODEL_FEATURES, model_row, validate_model_features

def test_v2_feature_contract_contains_no_future_outcomes():
    validate_model_features(MODEL_FEATURES)
    joined=" ".join(MODEL_FEATURES).lower()
    for token in ("future_seed","business_value","fill_rate","unmet","stockout","ending_stock"):
        assert token not in joined

def test_v2_rejects_unapproved_feature():
    try:
        validate_model_features((*MODEL_FEATURES, "future_seed"))
    except ValueError:
        pass
    else:
        raise AssertionError("future_seed must be rejected")

def test_model_row_is_allow_list_only():
    source={k:0 for k in MODEL_FEATURES}
    source.update({"store_id":"S","sku_id":"K","weather_condition":"clear",
                   "action_type":"DO_NOTHING","source_store_id":"",
                   "future_seed":999,"network_business_value":123.0})
    row=model_row(source)
    assert set(row)==set(MODEL_FEATURES)
    assert "future_seed" not in row
    assert "network_business_value" not in row
