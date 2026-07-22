from simulation.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    EXPECTED_ACTIONS,
    FEATURE_COLUMNS,
    IDENTIFIER_FEATURES,
    NUMERIC_FEATURES,
    PRE_DECISION_FEATURE_COLUMNS,
    validate_contract,
)


def test_feature_contract_is_unique_and_ordered() -> None:
    validate_contract()

    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))
    assert FEATURE_COLUMNS == (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)
    assert len(EXPECTED_ACTIONS) == len(set(EXPECTED_ACTIONS))


def test_dataset_and_model_contracts_cover_same_inputs() -> None:
    dataset_inputs = set(PRE_DECISION_FEATURE_COLUMNS) | set(
        IDENTIFIER_FEATURES
    )
    assert dataset_inputs == set(FEATURE_COLUMNS)
