from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter


class SimulationProfiler:
    def __init__(self):
        self.times = defaultdict(float)

    @contextmanager
    def measure(self, name: str):
        start = perf_counter()
        try:
            yield
        finally:
            self.times[name] += perf_counter() - start

    def report(self, day: int):
        print()
        print("=" * 60)
        print(f"DAY {day:03d} PERFORMANCE PROFILE")
        print("=" * 60)

        total = sum(self.times.values())

        for name, value in sorted(
            self.times.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            pct = (value / total * 100.0) if total else 0.0
            print(f"{name:<35} {value:8.3f}s   ({pct:5.1f}%)")

        print(f"\nTOTAL : {total:.3f}s")
        print("=" * 60)

        self.times.clear()