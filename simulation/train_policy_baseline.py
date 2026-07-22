from __future__ import annotations

"""
Train the first leakage-safe imitation-policy models.

The split is performed by complete episode seeds:
- train: seeds 1..70
- validation: seeds 71..85
- test: seeds 86..100

No random row-level train/test split is used.

Default mode samples a fixed number of rows from every episode so the
first experiment remains fast and memory-safe. Increase --rows-per-episode
later after the pipeline is validated.

Usage:
    python -m simulation.train_policy_baseline

Faster smoke test:
    python -m simulation.train_policy_baseline --rows-per-episode 2000

Larger experiment:
    python -m simulation.train_policy_baseline --rows-per-episode 10000
"""

from argparse import ArgumentParser
from collections import Counter
from csv import DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
import json
import re
import sys

try:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier
except ImportError as exc:
    raise SystemExit(
        "Missing ML dependencies. Install them with:\n"
        "python -m pip install pandas numpy scikit-learn joblib"
    ) from exc


DATASET_DIR = Path(
    "data/training/parallel_multi_episode_corrected"
)

OUTPUT_DIR = Path("artifacts/policy_training")

TRAIN_SEEDS = set(range(1, 71))
VALIDATION_SEEDS = set(range(71, 86))
TEST_SEEDS = set(range(86, 101))

from simulation.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    EXPECTED_ACTIONS,
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_VERSION,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
)


@dataclass(frozen=True)
class ModelMetrics:
    model_name: str
    split: str
    rows: int
    accuracy: float
    balanced_accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_f1: float
    runtime_seconds: float


def parse_args():
    parser = ArgumentParser(
        description=(
            "Train Decision Tree and Random Forest baselines "
            "using complete-seed dataset splits."
        )
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATASET_DIR,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
    )
    parser.add_argument(
        "--rows-per-episode",
        type=int,
        default=5000,
        help=(
            "Maximum rows sampled from each episode. "
            "Use 0 to load every row."
        ),
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--skip-random-forest",
        action="store_true",
        help="Train only the Decision Tree baseline.",
    )

    return parser.parse_args()


def discover_episode_files(
    data_dir: Path,
) -> dict[int, Path]:
    if not data_dir.exists():
        raise FileNotFoundError(
            f"Dataset directory not found: {data_dir.resolve()}"
        )

    files_by_seed: dict[int, Path] = {}

    for path in sorted(data_dir.glob("*.csv")):
        if path.name == "episode_summary.csv":
            continue

        match = re.search(r"_seed_(\d+)_", path.name)

        if match is None:
            continue

        seed = int(match.group(1))

        if seed in files_by_seed:
            raise RuntimeError(
                f"Duplicate dataset file for seed {seed}."
            )

        files_by_seed[seed] = path

    expected_seeds = (
        TRAIN_SEEDS
        | VALIDATION_SEEDS
        | TEST_SEEDS
    )
    missing = sorted(expected_seeds - set(files_by_seed))

    if missing:
        raise RuntimeError(
            "Missing episode files for seeds: "
            + ", ".join(map(str, missing))
        )

    return files_by_seed


def read_episode(
    *,
    path: Path,
    rows_per_episode: int,
    random_state: int,
) -> pd.DataFrame:
    usecols = [
        *FEATURE_COLUMNS,
        TARGET_COLUMN,
        "episode_seed",
    ]

    frame = pd.read_csv(
        path,
        usecols=usecols,
    )

    if rows_per_episode > 0 and len(frame) > rows_per_episode:
        frame = frame.sample(
            n=rows_per_episode,
            random_state=random_state,
        )

    return frame


def load_split(
    *,
    split_name: str,
    seeds: set[int],
    files_by_seed: dict[int, Path],
    rows_per_episode: int,
    random_state: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for index, seed in enumerate(
        sorted(seeds),
        start=1,
    ):
        frame = read_episode(
            path=files_by_seed[seed],
            rows_per_episode=rows_per_episode,
            random_state=random_state + seed,
        )
        frames.append(frame)

        if (
            index == 1
            or index % 10 == 0
            or index == len(seeds)
        ):
            print(
                f"Loaded {split_name}: "
                f"{index:02d}/{len(seeds):02d} episodes",
                flush=True,
            )

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    observed_seeds = set(
        combined["episode_seed"].astype(int).unique()
    )

    if observed_seeds != seeds:
        raise RuntimeError(
            f"{split_name} seed boundary mismatch."
        )

    return combined


def validate_no_seed_overlap(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> None:
    train_seeds = set(train["episode_seed"].astype(int))
    validation_seeds = set(
        validation["episode_seed"].astype(int)
    )
    test_seeds = set(test["episode_seed"].astype(int))

    if train_seeds & validation_seeds:
        raise RuntimeError(
            "Leakage: train and validation seeds overlap."
        )

    if train_seeds & test_seeds:
        raise RuntimeError(
            "Leakage: train and test seeds overlap."
        )

    if validation_seeds & test_seeds:
        raise RuntimeError(
            "Leakage: validation and test seeds overlap."
        )


def build_preprocessor() -> ColumnTransformer:
    try:
        encoder = OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=True,
        )
    except TypeError:
        # Compatibility with older scikit-learn versions.
        encoder = OneHotEncoder(
            handle_unknown="ignore",
            sparse=True,
        )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                encoder,
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def evaluate_model(
    *,
    model_name: str,
    split_name: str,
    pipeline: Pipeline,
    frame: pd.DataFrame,
) -> tuple[
    ModelMetrics,
    dict,
    list[list[int]],
]:
    x = frame[FEATURE_COLUMNS]
    y_true = frame[TARGET_COLUMN]

    started = perf_counter()
    y_pred = pipeline.predict(x)
    runtime = perf_counter() - started

    metrics = ModelMetrics(
        model_name=model_name,
        split=split_name,
        rows=len(frame),
        accuracy=accuracy_score(
            y_true,
            y_pred,
        ),
        balanced_accuracy=balanced_accuracy_score(
            y_true,
            y_pred,
        ),
        macro_precision=precision_score(
            y_true,
            y_pred,
            average="macro",
            zero_division=0,
        ),
        macro_recall=recall_score(
            y_true,
            y_pred,
            average="macro",
            zero_division=0,
        ),
        macro_f1=f1_score(
            y_true,
            y_pred,
            average="macro",
            zero_division=0,
        ),
        weighted_f1=f1_score(
            y_true,
            y_pred,
            average="weighted",
            zero_division=0,
        ),
        runtime_seconds=runtime,
    )

    report = classification_report(
        y_true,
        y_pred,
        labels=EXPECTED_ACTIONS,
        output_dict=True,
        zero_division=0,
    )

    matrix = confusion_matrix(
        y_true,
        y_pred,
        labels=EXPECTED_ACTIONS,
    ).tolist()

    return metrics, report, matrix


def train_one_model(
    *,
    model_name: str,
    estimator,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    output_dir: Path,
) -> list[ModelMetrics]:
    pipeline = Pipeline(
        steps=[
            (
                "preprocessor",
                build_preprocessor(),
            ),
            (
                "model",
                estimator,
            ),
        ]
    )

    x_train = train[FEATURE_COLUMNS]
    y_train = train[TARGET_COLUMN]

    print()
    print(f"Training {model_name}...")
    started = perf_counter()
    pipeline.fit(x_train, y_train)
    training_runtime = perf_counter() - started
    print(
        f"{model_name} training completed in "
        f"{training_runtime:.2f}s"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_path = output_dir / (
        f"{model_name.lower().replace(' ', '_')}.joblib"
    )
    joblib.dump(
        pipeline,
        model_path,
    )

    metrics_rows: list[ModelMetrics] = []

    for split_name, frame in (
        ("validation", validation),
        ("test", test),
    ):
        metrics, report, matrix = evaluate_model(
            model_name=model_name,
            split_name=split_name,
            pipeline=pipeline,
            frame=frame,
        )

        metrics_rows.append(metrics)

        report_path = output_dir / (
            f"{model_name.lower().replace(' ', '_')}"
            f"_{split_name}_classification_report.json"
        )
        report_path.write_text(
            json.dumps(
                report,
                indent=2,
            ),
            encoding="utf-8",
        )

        matrix_path = output_dir / (
            f"{model_name.lower().replace(' ', '_')}"
            f"_{split_name}_confusion_matrix.json"
        )
        matrix_path.write_text(
            json.dumps(
                {
                    "labels": EXPECTED_ACTIONS,
                    "matrix": matrix,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print(f"{model_name} — {split_name.upper()}")
        print("-" * 45)
        print(f"Rows              : {metrics.rows:,}")
        print(f"Accuracy          : {metrics.accuracy:.4f}")
        print(
            f"Balanced Accuracy : "
            f"{metrics.balanced_accuracy:.4f}"
        )
        print(
            f"Macro Precision   : "
            f"{metrics.macro_precision:.4f}"
        )
        print(
            f"Macro Recall      : "
            f"{metrics.macro_recall:.4f}"
        )
        print(f"Macro F1          : {metrics.macro_f1:.4f}")
        print(
            f"Weighted F1       : "
            f"{metrics.weighted_f1:.4f}"
        )

    return metrics_rows


def print_split_summary(
    name: str,
    frame: pd.DataFrame,
) -> None:
    counts = Counter(frame[TARGET_COLUMN])

    print()
    print(name.upper())
    print("-" * len(name))
    print(f"Rows  : {len(frame):,}")
    print(
        "Seeds : "
        + ", ".join(
            map(
                str,
                sorted(
                    frame["episode_seed"]
                    .astype(int)
                    .unique()
                ),
            )
        )
    )

    for action in EXPECTED_ACTIONS:
        count = counts[action]
        percentage = count / len(frame)

        print(
            f"{action:<20}: "
            f"{count:>9,} ({percentage:>6.2%})"
        )


def write_metrics(
    output_dir: Path,
    metrics_rows: list[ModelMetrics],
) -> Path:
    path = output_dir / "model_metrics.csv"

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = DictWriter(
            file,
            fieldnames=list(
                ModelMetrics.__dataclass_fields__.keys()
            ),
        )
        writer.writeheader()

        for row in metrics_rows:
            writer.writerow(asdict(row))

    return path


def main() -> None:
    args = parse_args()

    if args.rows_per_episode < 0:
        raise ValueError(
            "--rows-per-episode cannot be negative."
        )

    files_by_seed = discover_episode_files(
        args.data_dir
    )

    print("LEAKAGE-SAFE POLICY TRAINING")
    print("============================")
    print(f"Dataset directory : {args.data_dir.resolve()}")
    print(
        "Split strategy    : complete episode seeds "
        "(70 train / 15 validation / 15 test)"
    )
    print(
        f"Rows per episode  : "
        f"{args.rows_per_episode or 'ALL'}"
    )

    train = load_split(
        split_name="train",
        seeds=TRAIN_SEEDS,
        files_by_seed=files_by_seed,
        rows_per_episode=args.rows_per_episode,
        random_state=args.random_state,
    )

    validation = load_split(
        split_name="validation",
        seeds=VALIDATION_SEEDS,
        files_by_seed=files_by_seed,
        rows_per_episode=args.rows_per_episode,
        random_state=args.random_state,
    )

    test = load_split(
        split_name="test",
        seeds=TEST_SEEDS,
        files_by_seed=files_by_seed,
        rows_per_episode=args.rows_per_episode,
        random_state=args.random_state,
    )

    validate_no_seed_overlap(
        train,
        validation,
        test,
    )

    print_split_summary("train", train)
    print_split_summary("validation", validation)
    print_split_summary("test", test)

    metrics_rows: list[ModelMetrics] = []

    metrics_rows.extend(
        train_one_model(
            model_name="Decision Tree",
            estimator=DecisionTreeClassifier(
                max_depth=18,
                min_samples_leaf=20,
                class_weight="balanced",
                random_state=args.random_state,
            ),
            train=train,
            validation=validation,
            test=test,
            output_dir=args.output_dir,
        )
    )

    if not args.skip_random_forest:
        metrics_rows.extend(
            train_one_model(
                model_name="Random Forest",
                estimator=RandomForestClassifier(
                    n_estimators=120,
                    max_depth=22,
                    min_samples_leaf=10,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                    random_state=args.random_state,
                    verbose=1,
                ),
                train=train,
                validation=validation,
                test=test,
                output_dir=args.output_dir,
            )
        )

    metrics_path = write_metrics(
        args.output_dir,
        metrics_rows,
    )

    metadata = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "training_pipeline_version": "2.0.0",
        "feature_columns": list(FEATURE_COLUMNS),
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "expected_actions": list(EXPECTED_ACTIONS),
        "target_column": TARGET_COLUMN,
        "random_state": args.random_state,
        "train_seeds": sorted(TRAIN_SEEDS),
        "validation_seeds": sorted(
            VALIDATION_SEEDS
        ),
        "test_seeds": sorted(TEST_SEEDS),
        "rows_per_episode": args.rows_per_episode,
    }

    metadata_path = (
        args.output_dir
        / "training_metadata.json"
    )
    metadata_path.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("TRAINING COMPLETE")
    print("=================")
    print(f"Metrics  : {metrics_path}")
    print(f"Metadata : {metadata_path}")
    print(f"Models   : {args.output_dir.resolve()}")
    print()
    print(
        "The next step is to wrap the selected model inside "
        "MLDecisionPolicy and benchmark it in unseen simulations."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        sys.exit(1)
