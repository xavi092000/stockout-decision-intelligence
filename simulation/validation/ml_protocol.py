from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EpisodeSeedSplit:
    """Leakage-safe split contract based on complete simulation episodes."""

    train: frozenset[int]
    validation: frozenset[int]
    test: frozenset[int]

    @classmethod
    def default(cls) -> "EpisodeSeedSplit":
        return cls(
            train=frozenset(range(1, 71)),
            validation=frozenset(range(71, 86)),
            test=frozenset(range(86, 101)),
        )

    def validate(self) -> None:
        groups = {
            "train": self.train,
            "validation": self.validation,
            "test": self.test,
        }

        for name, seeds in groups.items():
            if not seeds:
                raise ValueError(f"{name} seed split cannot be empty.")
            if any(seed < 0 for seed in seeds):
                raise ValueError(f"{name} seed split cannot contain negative seeds.")

        names = tuple(groups)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                overlap = groups[left_name] & groups[right_name]
                if overlap:
                    raise ValueError(
                        f"Leakage: {left_name} and {right_name} seed splits overlap: "
                        + ", ".join(map(str, sorted(overlap)))
                    )

    @property
    def all_development_seeds(self) -> frozenset[int]:
        return self.train | self.validation | self.test

    def validate_benchmark_seeds(self, seeds: Iterable[int]) -> tuple[int, ...]:
        normalized = tuple(int(seed) for seed in seeds)

        if not normalized:
            raise ValueError("Benchmark seed collection cannot be empty.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Benchmark seeds must be unique.")
        if any(seed < 0 for seed in normalized):
            raise ValueError("Benchmark seeds cannot be negative.")

        overlap = self.all_development_seeds & set(normalized)
        if overlap:
            raise ValueError(
                "Leakage: benchmark seeds overlap model-development seeds: "
                + ", ".join(map(str, sorted(overlap)))
            )

        return normalized


DEFAULT_EPISODE_SPLIT = EpisodeSeedSplit.default()
DEFAULT_EPISODE_SPLIT.validate()
