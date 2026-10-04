from __future__ import annotations

"""Generate V25 proof charts from existing benchmark artifacts only.

Reads:
- artifacts/model_based_v25/final_60d/seed_*.json + aggregate.json
- artifacts/model_based_v25/final_365d/seed_*.json + aggregate.json
- artifacts/model_based_v24/counterfactual_dataset.json
- artifacts/model_based_v25/counterfactual_dataset.json

Writes PNG charts to docs/assets/. No values are hardcoded; every number
comes from the artifact files.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
V25 = ROOT / "artifacts" / "model_based_v25"
OUT = ROOT / "docs" / "assets"


def load_seed_deltas(split_dir):
    seeds, deltas = [], []
    for p in sorted(split_dir.glob("seed_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        seeds.append(str(d["seed"]))
        deltas.append(d["delta"])
    return seeds, deltas


def chart_seed_deltas(split_dir, title, out_name):
    seeds, deltas = load_seed_deltas(split_dir)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = ["#2e7d32" if d >= 0 else "#c62828" for d in deltas]
    ax.bar(seeds, deltas, color=colors)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_title(title)
    ax.set_xlabel("Held-out seed")
    ax.set_ylabel("Business value delta vs baseline (USD)")
    ax.yaxis.set_major_formatter(lambda x, _: f"${x:,.0f}")
    for i, d in enumerate(deltas):
        ax.text(i, d, f"+${d:,.0f}" if d >= 0 else f"-${abs(d):,.0f}",
                ha="center", va="bottom" if d >= 0 else "top", fontsize=8)
    ax.set_ylim(min(0, min(deltas) * 1.15), max(deltas) * 1.2)
    fig.tight_layout()
    fig.savefig(OUT / out_name, dpi=150)
    plt.close(fig)


def chart_decision_distribution(split_dir, out_name):
    totals = {"DO_NOTHING": 0, "ORDER_NORMAL": 0, "ORDER_EXPEDITE": 0,
              "TRANSFER_STOCK": 0}
    n = 0
    for p in sorted(split_dir.glob("seed_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))["v25"]
        n += 1
        for k in totals:
            totals[k] += d[k]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    labels = list(totals)
    values = [totals[k] for k in labels]
    ax.bar(labels, values, color=["#607d8b", "#1976d2", "#ef6c00", "#7b1fa2"])
    ax.set_title(f"V25 decision distribution — {n} held-out seeds x 60 days")
    ax.set_xlabel("Action type")
    ax.set_ylabel("Decision count")
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, max(values) * 1.12)
    fig.tight_layout()
    fig.savefig(OUT / out_name, dpi=150)
    plt.close(fig)


def _state_stats(ds_path):
    rows = json.loads(ds_path.read_text(encoding="utf-8"))["rows"]
    states = {}
    for r in rows:
        if r["split"] != "train":
            continue
        f = r["features"]
        key = (r["episode_seed"], f["store_id"], f["sku_id"], f["simulation_day"])
        if key not in states:
            cov = (f["current_stock"] + f["pending_units"]) / max(
                f["forecast_daily_demand"], 1e-9)
            states[key] = (cov, f["pending_units"])
    n = len(states)
    healthy = sum(1 for c, _ in states.values() if c >= 14.0) / n * 100
    pending = sum(1 for _, p in states.values() if p > 0) / n * 100
    cov14 = sum(1 for c, _ in states.values() if c > 14.0) / n * 100
    return healthy, pending, cov14


def chart_dataset_coverage(out_name):
    v24 = _state_stats(ROOT / "artifacts" / "model_based_v24"
                       / "counterfactual_dataset.json")
    v25 = _state_stats(V25 / "counterfactual_dataset.json")
    metrics = ["HEALTHY states (%)", "pending_units > 0 (%)",
               "coverage > 14 days (%)"]
    x = np.arange(len(metrics))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4.5))
    b1 = ax.bar(x - width / 2, v24, width, label="V24 train states",
                color="#c62828")
    b2 = ax.bar(x + width / 2, v25, width, label="V25 train states",
                color="#2e7d32")
    ax.bar_label(b1, fmt="%.1f")
    ax.bar_label(b2, fmt="%.1f")
    ax.set_title("Training state coverage — V24 vs V25")
    ax.set_ylabel("Share of unique train states (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 100)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / out_name, dpi=150)
    plt.close(fig)


def chart_mean_delta_ci(out_name):
    a60 = json.loads((V25 / "final_60d" / "aggregate.json").read_text(encoding="utf-8"))
    a365 = json.loads((V25 / "final_365d" / "aggregate.json").read_text(encoding="utf-8"))
    labels = ["60 days x 10 seeds", "365 days x 10 seeds"]
    means = [a60["mean_delta"], a365["mean_delta"]]
    lows = [a60["ci95"][0], a365["ci95"][0]]
    highs = [a60["ci95"][1], a365["ci95"][1]]
    err = [[m - l for m, l in zip(means, lows)],
           [h - m for h, m in zip(highs, means)]]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.errorbar(labels, means, yerr=err, fmt="o", capsize=8, markersize=8,
                color="#1976d2", linewidth=2)
    ax.axhline(0, color="black", linewidth=1)
    for i, (m, l, h) in enumerate(zip(means, lows, highs)):
        ax.text(i, h, f"mean +${m:,.0f}\nCI95 [+${l:,.0f}, +${h:,.0f}]",
                ha="center", va="bottom", fontsize=9)
    ax.set_title("V25 mean business value delta vs baseline (95% CI)")
    ax.set_ylabel("Mean delta (USD)")
    ax.set_ylim(min(0, min(lows) * 1.2 - 1000), max(highs) * 1.3)
    fig.tight_layout()
    fig.savefig(OUT / out_name, dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    chart_seed_deltas(V25 / "final_60d",
                      "V25 vs baseline — business value delta per seed (60 days)",
                      "v25_60d_seed_deltas.png")
    chart_seed_deltas(V25 / "final_365d",
                      "V25 vs baseline — business value delta per seed (365 days)",
                      "v25_365d_seed_deltas.png")
    chart_decision_distribution(V25 / "final_60d", "v25_decision_distribution.png")
    chart_dataset_coverage("v25_dataset_coverage.png")
    chart_mean_delta_ci("v25_mean_delta_ci.png")
    for p in sorted(OUT.glob("v25_*.png")):
        print(f"created {p}")


if __name__ == "__main__":
    main()
