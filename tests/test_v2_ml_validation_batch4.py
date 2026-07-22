from __future__ import annotations

import pytest

from simulation.validation.ml_protocol import EpisodeSeedSplit


def test_default_split_has_no_overlap_and_preserves_expected_boundaries():
    split = EpisodeSeedSplit.default()
    split.validate()

    assert split.train == frozenset(range(1, 71))
    assert split.validation == frozenset(range(71, 86))
    assert split.test == frozenset(range(86, 101))
    assert len(split.all_development_seeds) == 100


def test_split_contract_rejects_overlap():
    split = EpisodeSeedSplit(
        train=frozenset({1, 2}),
        validation=frozenset({2, 3}),
        test=frozenset({4}),
    )

    with pytest.raises(ValueError, match="overlap"):
        split.validate()


def test_benchmark_rejects_any_seed_used_for_model_development():
    split = EpisodeSeedSplit.default()

    with pytest.raises(ValueError, match="benchmark seeds overlap"):
        split.validate_benchmark_seeds([100, 101])


def test_benchmark_accepts_strictly_unseen_unique_seeds():
    split = EpisodeSeedSplit.default()

    assert split.validate_benchmark_seeds(range(101, 131)) == tuple(range(101, 131))


def test_benchmark_rejects_duplicate_seeds():
    split = EpisodeSeedSplit.default()

    with pytest.raises(ValueError, match="unique"):
        split.validate_benchmark_seeds([101, 101])


def test_benchmark_rejects_empty_seed_collection():
    split = EpisodeSeedSplit.default()

    with pytest.raises(ValueError, match="cannot be empty"):
        split.validate_benchmark_seeds([])
