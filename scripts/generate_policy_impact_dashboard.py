from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch


REPO_ROOT = Path(__file__).resolve().parents[1]

SUMMARY_PATH = (
    REPO_ROOT
    / "artifacts"
    / "policy_training"
    / "robust_benchmark"
    / "summary.json"
)

DELTAS_PATH = (
    REPO_ROOT
    / "artifacts"
    / "policy_training"
    / "robust_benchmark"
    / "paired_deltas.csv"
)

OUTPUT_PATH = (
    REPO_ROOT
    / "docs"
    / "assets"
    / "policy_performance_comparison.png"
)


def load_summary() -> dict:
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(
            f"Benchmark summary not found: {SUMMARY_PATH}"
        )

    with SUMMARY_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_paired_deltas() -> list[dict[str, float]]:
    if not DELTAS_PATH.exists():
        raise FileNotFoundError(
            f"Paired benchmark results not found: {DELTAS_PATH}"
        )

    numeric_fields = (
        "value_delta",
        "service_delta",
        "stockout_delta",
        "unmet_demand_delta",
    )

    rows: list[dict[str, float]] = []

    with DELTAS_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        missing_fields = [
            field
            for field in numeric_fields
            if field not in (reader.fieldnames or [])
        ]

        if missing_fields:
            raise ValueError(
                "Missing expected CSV columns: "
                + ", ".join(missing_fields)
            )

        for row in reader:
            rows.append(
                {
                    field: float(row[field])
                    for field in numeric_fields
                }
            )

    if not rows:
        raise ValueError(
            "paired_deltas.csv contains no benchmark rows."
        )

    return rows


def compute_metrics(
    summary: dict,
    rows: list[dict[str, float]],
) -> dict[str, float]:
    paired_summary = summary["paired_summary"]

    metrics = {
        "episodes": len(rows),
        "value_delta": mean(
            row["value_delta"] for row in rows
        ),
        "service_delta": mean(
            row["service_delta"] for row in rows
        ),
        "stockout_delta": mean(
            row["stockout_delta"] for row in rows
        ),
        "unmet_demand_delta": mean(
            row["unmet_demand_delta"] for row in rows
        ),
        "value_win_rate": float(
            paired_summary["value_win_rate"]
        ),
        "service_win_rate": float(
            paired_summary["service_win_rate"]
        ),
    }

    expected_episodes = int(summary["episodes"])

    if metrics["episodes"] != expected_episodes:
        raise ValueError(
            "Benchmark row count does not match summary.json: "
            f"{metrics['episodes']} rows versus "
            f"{expected_episodes} expected."
        )

    return metrics


def add_rounded_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    facecolor: str,
    edgecolor: str,
    linewidth: float = 1.0,
    radius: float = 0.018,
):
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=(
            f"round,pad=0.008,"
            f"rounding_size={radius}"
        ),
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=linewidth,
        transform=ax.transAxes,
        clip_on=False,
    )

    ax.add_patch(patch)
    return patch


def add_metric_icon(
    ax,
    x: float,
    y: float,
    symbol: str,
    accent: str,
    accent_soft: str,
) -> None:
    circle = Circle(
        (x, y),
        radius=0.021,
        facecolor=accent_soft,
        edgecolor=accent,
        linewidth=1.1,
        transform=ax.transAxes,
        clip_on=False,
    )

    ax.add_patch(circle)

    ax.text(
        x,
        y,
        symbol,
        color=accent,
        fontsize=12,
        fontweight="bold",
        ha="center",
        va="center",
        transform=ax.transAxes,
    )


def format_signed_currency(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.0f}"


def format_signed_points(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value) * 100:.2f} pts"


def format_reduction(value: float) -> str:
    if value <= 0:
        return f"-{abs(value):,.0f}"

    return f"+{value:,.0f}"


def build_dashboard(metrics: dict[str, float]) -> None:
    background = "#07111F"
    panel = "#0D1B2A"
    panel_border = "#203247"
    text_primary = "#F4F7FB"
    text_secondary = "#9FB0C3"
    accent = "#2ED3A7"
    accent_soft = "#102E2A"

    fig = plt.figure(
        figsize=(16, 9),
        dpi=160,
        facecolor=background,
    )

    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Header
    ax.text(
        0.065,
        0.925,
        "BUSINESS IMPACT OF THE ML DECISION POLICY",
        color=text_primary,
        fontsize=25,
        fontweight="bold",
        ha="left",
        va="center",
        transform=ax.transAxes,
    )

    ax.text(
        0.065,
        0.881,
        (
            "Average operational impact compared with "
            "the rule-based decision baseline."
        ),
        color=text_secondary,
        fontsize=12.5,
        ha="left",
        va="center",
        transform=ax.transAxes,
    )

    add_rounded_box(
        ax,
        0.775,
        0.875,
        0.16,
        0.06,
        accent_soft,
        accent,
        linewidth=1.2,
        radius=0.025,
    )

    ax.text(
        0.855,
        0.905,
        f"{int(metrics['episodes'])} UNSEEN SIMULATIONS",
        color=accent,
        fontsize=10.5,
        fontweight="bold",
        ha="center",
        va="center",
        transform=ax.transAxes,
    )

    # Main KPI cards
    card_width = 0.425
    card_height = 0.195

    cards = [
        {
            "x": 0.055,
            "y": 0.590,
            "symbol": "$",
            "label": "NET BUSINESS VALUE",
            "value": format_signed_currency(
                metrics["value_delta"]
            ),
            "description": "Average gain per simulation",
        },
        {
            "x": 0.52,
            "y": 0.590,
            "symbol": "↑",
            "label": "SERVICE LEVEL",
            "value": format_signed_points(
                metrics["service_delta"]
            ),
            "description": "Average service improvement",
        },
        {
            "x": 0.055,
            "y": 0.365,
            "symbol": "↓",
            "label": "STOCKOUT EVENTS",
            "value": format_reduction(
                metrics["stockout_delta"]
            ),
            "description": "Average stockouts avoided",
        },
        {
            "x": 0.52,
            "y": 0.365,
            "symbol": "↓",
            "label": "UNMET DEMAND",
            "value": format_reduction(
                metrics["unmet_demand_delta"]
            ),
            "description": "Average unmet demand avoided",
        },
    ]

    for card in cards:
        add_rounded_box(
            ax,
            card["x"],
            card["y"],
            card_width,
            card_height,
            panel,
            panel_border,
            linewidth=1.2,
            radius=0.022,
        )

        add_metric_icon(
            ax,
            card["x"] + 0.039,
            card["y"] + 0.145,
            card["symbol"],
            accent,
            accent_soft,
        )

        ax.text(
            card["x"] + 0.074,
            card["y"] + 0.145,
            card["label"],
            color=text_primary,
            fontsize=11.5,
            fontweight="bold",
            ha="left",
            va="center",
            transform=ax.transAxes,
        )

        ax.text(
            card["x"] + 0.03,
            card["y"] + 0.088,
            card["value"],
            color=accent,
            fontsize=29,
            fontweight="bold",
            ha="left",
            va="center",
            transform=ax.transAxes,
        )

        ax.text(
            card["x"] + 0.03,
            card["y"] + 0.034,
            card["description"],
            color=text_secondary,
            fontsize=10.3,
            ha="left",
            va="center",
            transform=ax.transAxes,
        )

    # Executive conclusion
    add_rounded_box(
        ax,
        0.055,
        0.265,
        0.89,
        0.062,
        accent_soft,
        accent,
        linewidth=1.0,
        radius=0.018,
    )

    ax.text(
        0.5,
        0.296,
        (
            "The ML policy increased business value and service quality "
            "while reducing stockouts and unmet demand."
        ),
        color=text_primary,
        fontsize=11.5,
        fontweight="bold",
        ha="center",
        va="center",
        transform=ax.transAxes,
    )

    # Validation cards
    validation_card_y = 0.105
    validation_card_height = 0.105
    validation_card_width = 0.275

    validation_cards = [
        (
            0.055,
            f"{metrics['value_win_rate'] * 100:.1f}%",
            "BUSINESS VALUE WINS",
        ),
        (
            0.3625,
            f"{metrics['service_win_rate'] * 100:.1f}%",
            "SERVICE LEVEL WINS",
        ),
        (
            0.67,
            str(int(metrics["episodes"])),
            "PAIRED EVALUATIONS",
        ),
    ]

    for x, value, label in validation_cards:
        add_rounded_box(
            ax,
            x,
            validation_card_y,
            validation_card_width,
            validation_card_height,
            panel,
            panel_border,
            linewidth=1.1,
            radius=0.02,
        )

        ax.text(
            x + 0.025,
            validation_card_y + 0.066,
            value,
            color=text_primary,
            fontsize=21,
            fontweight="bold",
            ha="left",
            va="center",
            transform=ax.transAxes,
        )

        ax.text(
            x + 0.025,
            validation_card_y + 0.027,
            label,
            color=text_secondary,
            fontsize=9.5,
            fontweight="bold",
            ha="left",
            va="center",
            transform=ax.transAxes,
        )

    ax.text(
        0.945,
        0.044,
        "Source: robust paired benchmark artifacts",
        color="#6F8195",
        fontsize=8.5,
        ha="right",
        va="center",
        transform=ax.transAxes,
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.savefig(
        OUTPUT_PATH,
        dpi=160,
        facecolor=background,
        bbox_inches="tight",
        pad_inches=0.15,
    )

    plt.close(fig)


def main() -> None:
    summary = load_summary()
    rows = load_paired_deltas()
    metrics = compute_metrics(summary, rows)

    build_dashboard(metrics)

    print("Dashboard generated successfully.")
    print(f"Output: {OUTPUT_PATH}")
    print()
    print("Metrics used:")
    print(
        "  Net business value: "
        f"{format_signed_currency(metrics['value_delta'])}"
    )
    print(
        "  Service level: "
        f"{format_signed_points(metrics['service_delta'])}"
    )
    print(
        "  Stockout events: "
        f"{format_reduction(metrics['stockout_delta'])}"
    )
    print(
        "  Unmet demand: "
        f"{format_reduction(metrics['unmet_demand_delta'])}"
    )
    print(
        "  Business value wins: "
        f"{metrics['value_win_rate'] * 100:.1f}%"
    )
    print(
        "  Service level wins: "
        f"{metrics['service_win_rate'] * 100:.1f}%"
    )
    print(
        f"  Simulations: {int(metrics['episodes'])}"
    )


if __name__ == "__main__":
    main()
