from __future__ import annotations

import json
from pathlib import Path

from simulation.domain.factory import WorldFactory
from simulation.domain.models import WorldState


class WorldRepositoryError(RuntimeError):
    """Raised when a world state cannot be loaded or persisted."""


class JsonWorldRepository:
    def load(self, path: str | Path) -> WorldState:
        source = Path(path)
        if not source.is_file():
            raise WorldRepositoryError(
                f"World-state file not found: {source}"
            )
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorldRepositoryError(
                f"Invalid world-state JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise WorldRepositoryError(
                "World-state root must be a JSON object."
            )
        return WorldFactory.world(payload)

    def save(
        self,
        world: WorldState,
        path: str | Path,
    ) -> Path:
        world.validate()
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                world.to_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return destination
