
from __future__ import annotations

# Apply the pending-operation cache optimization safely.
#
# Run from the project root:
#     python apply_pending_cache_optimization.py

from datetime import datetime
from pathlib import Path
import py_compile
import shutil
import sys


ROOT = Path.cwd()
SIMULATION = ROOT / "simulation"

ENGINE = SIMULATION / "engine.py"
POLICY = SIMULATION / "decision_policy.py"
DATASET = SIMULATION / "dataset_builder.py"

TARGETS = (ENGINE, POLICY, DATASET)


def replace_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one match, found {count}."
        )

    return text.replace(old, new, 1)


def patch_policy(text: str) -> str:
    if "_pending_inbound_by_key" in text:
        print("decision_policy.py: cache already present.")
        return text

    old = '''    @staticmethod
    def _pending_inbound_quantity(
        state: SimulationState,
        store_id: str,
        sku_id: str,
    ) -> int:
        return sum(
            operation.quantity
            for operation in state.pending_operations
            if (
                operation.is_pending
                and operation.destination_store_id == store_id
                and operation.sku_id == sku_id
            )
        )
'''

    new = '''    @staticmethod
    def _pending_inbound_quantity(
        state: SimulationState,
        store_id: str,
        sku_id: str,
    ) -> int:
        cached = getattr(
            state,
            "_pending_inbound_by_key",
            None,
        )

        if cached is not None:
            return cached.get(
                (store_id, sku_id),
                0,
            )

        return sum(
            operation.quantity
            for operation in state.pending_operations
            if (
                operation.is_pending
                and operation.destination_store_id == store_id
                and operation.sku_id == sku_id
            )
        )
'''

    return replace_once(
        text,
        old,
        new,
        "decision policy pending lookup",
    )


def patch_dataset(text: str) -> str:
    if "_pending_by_type" in text:
        print("dataset_builder.py: cache already present.")
        return text

    old = '''    @staticmethod
    def _pending_units(
        *,
        state: SimulationState,
        store_id: str,
        sku_id: str,
        operation_type: PendingOperationType,
    ) -> int:
        operations = getattr(
            state,
            "pending_operations",
            (),
        )

        return sum(
            operation.quantity
            for operation in operations
            if (
                operation.status
                == PendingOperationStatus.PENDING
                and operation.operation_type
                == operation_type
                and operation.destination_store_id
                == store_id
                and operation.sku_id == sku_id
            )
        )
'''

    new = '''    @staticmethod
    def _pending_units(
        *,
        state: SimulationState,
        store_id: str,
        sku_id: str,
        operation_type: PendingOperationType,
    ) -> int:
        cached = getattr(
            state,
            "_pending_by_type",
            None,
        )

        if cached is not None:
            return cached.get(
                (
                    store_id,
                    sku_id,
                    operation_type,
                ),
                0,
            )

        operations = getattr(
            state,
            "pending_operations",
            (),
        )

        return sum(
            operation.quantity
            for operation in operations
            if (
                operation.status
                == PendingOperationStatus.PENDING
                and operation.operation_type
                == operation_type
                and operation.destination_store_id
                == store_id
                and operation.sku_id == sku_id
            )
        )
'''

    return replace_once(
        text,
        old,
        new,
        "dataset pending lookup",
    )


def patch_engine(text: str) -> str:
    if "def _build_pending_indexes(" not in text:
        anchor = '''    def _prepare_daily_decisions(
'''
        helper = '''    @staticmethod
    def _build_pending_indexes(
        state: SimulationState,
    ) -> tuple[
        dict[tuple[str, str], int],
        dict[
            tuple[
                str,
                str,
                PendingOperationType,
            ],
            int,
        ],
    ]:
        pending_inbound_by_key: dict[
            tuple[str, str],
            int,
        ] = {}

        pending_by_type: dict[
            tuple[
                str,
                str,
                PendingOperationType,
            ],
            int,
        ] = {}

        for operation in state.pending_operations:
            if not operation.is_pending:
                continue

            store_sku_key = (
                operation.destination_store_id,
                operation.sku_id,
            )

            pending_inbound_by_key[store_sku_key] = (
                pending_inbound_by_key.get(
                    store_sku_key,
                    0,
                )
                + operation.quantity
            )

            type_key = (
                operation.destination_store_id,
                operation.sku_id,
                operation.operation_type,
            )

            pending_by_type[type_key] = (
                pending_by_type.get(type_key, 0)
                + operation.quantity
            )

        return (
            pending_inbound_by_key,
            pending_by_type,
        )

'''
        text = replace_once(
            text,
            anchor,
            helper + anchor,
            "engine helper insertion",
        )

    if "state._pending_inbound_by_key" not in text:
        old = '''        transition_actions: list[InventoryAction] = []
        realized_demands: list[RealizedDemand] = []
        decisions: list[DecisionResult] = []

        reserved_transfer_out: dict[tuple[str, str], int] = {}
'''
        new = '''        transition_actions: list[InventoryAction] = []
        realized_demands: list[RealizedDemand] = []
        decisions: list[DecisionResult] = []

        (
            pending_inbound_by_key,
            pending_by_type,
        ) = self._build_pending_indexes(state)

        state._pending_inbound_by_key = (
            pending_inbound_by_key
        )
        state._pending_by_type = pending_by_type

        reserved_transfer_out: dict[tuple[str, str], int] = {}
'''
        text = replace_once(
            text,
            old,
            new,
            "engine daily cache initialization",
        )

    if "Keep the daily O(1) indexes synchronized" not in text:
        old = '''        state.add_pending_operation(operation)
'''
        new = '''        state.add_pending_operation(operation)

        # Keep the daily O(1) indexes synchronized so later
        # decisions on the same day observe newly created orders.
        pending_inbound_by_key = getattr(
            state,
            "_pending_inbound_by_key",
            None,
        )

        if pending_inbound_by_key is not None:
            store_sku_key = (
                operation.destination_store_id,
                operation.sku_id,
            )
            pending_inbound_by_key[store_sku_key] = (
                pending_inbound_by_key.get(
                    store_sku_key,
                    0,
                )
                + operation.quantity
            )

        pending_by_type = getattr(
            state,
            "_pending_by_type",
            None,
        )

        if pending_by_type is not None:
            type_key = (
                operation.destination_store_id,
                operation.sku_id,
                operation.operation_type,
            )
            pending_by_type[type_key] = (
                pending_by_type.get(type_key, 0)
                + operation.quantity
            )
'''
        text = replace_once(
            text,
            old,
            new,
            "engine cache synchronization",
        )

    return text


def main() -> None:
    missing = [
        str(path)
        for path in TARGETS
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required files:\n- "
            + "\n- ".join(missing)
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups: dict[Path, Path] = {}

    try:
        for path in TARGETS:
            backup = path.with_name(
                f"{path.name}.backup_{timestamp}"
            )
            shutil.copy2(path, backup)
            backups[path] = backup

        ENGINE.write_text(
            patch_engine(
                ENGINE.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
        POLICY.write_text(
            patch_policy(
                POLICY.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
        DATASET.write_text(
            patch_dataset(
                DATASET.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )

        for path in TARGETS:
            py_compile.compile(
                str(path),
                doraise=True,
            )

    except Exception:
        print()
        print("Patch failed. Restoring backups...")

        for original, backup in backups.items():
            if backup.exists():
                shutil.copy2(backup, original)

        raise

    print()
    print("PENDING CACHE OPTIMIZATION APPLIED")
    print("==================================")
    print("Compilation: PASSED")
    print()
    print("Next commands:")
    print("python -m simulation.profile_episode --seed 1")
    print("python -m simulation.engine")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        sys.exit(1)
