"""
Step 7 - Figures for the results.

Inputs : results/optimized_timetable.csv
         results/budget_tradeoff.csv
         results/match_day_extra_demand.csv
Outputs: results/figures/load_ratio_heatmap.png
         results/figures/budget_tradeoff.png
         results/figures/match_day_extra_demand.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
# Diverging scale around "exactly at capacity": blue = spare room, red = over capacity.
DIVERGING = LinearSegmentedColormap.from_list("load", ["#184f95", "#86b6ef", "#f0efec", "#ec835a", "#a82020"])

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_SECONDARY,
    "ytick.labelcolor": INK_SECONDARY,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def load_ratio_heatmap():
    t = pd.read_csv(RESULTS / "optimized_timetable.csv")
    plan_col = next(c for c in t.columns if c.startswith("plan_load_ratio_budget_"))
    budget = plan_col.rsplit("_", 1)[1]
    panels = [
        ("baseline_load_ratio", "Today's timetable"),
        ("rescheduled_load_ratio", "Rescheduled, no extra trips"),
        (plan_col, f"Rescheduled + {budget} extra trips"),
    ]
    lines = sorted(t["line"].unique())
    hours = sorted(t["hour"].unique())
    norm = TwoSlopeNorm(vmin=0.2, vcenter=1.0, vmax=2.1)

    fig, axes = plt.subplots(len(panels), 1, figsize=(11, 9.6), sharex=True)
    for ax, (col, title) in zip(axes, panels):
        grid = t.pivot(index="line", columns="hour", values=col).reindex(index=lines, columns=hours)
        image = ax.imshow(grid.to_numpy(), cmap=DIVERGING, norm=norm, aspect="auto")
        for i in range(len(lines)):
            for j in range(len(hours)):
                value = grid.iat[i, j]
                if np.isnan(value):
                    continue
                dark = value >= 1.6 or value <= 0.45
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7.5,
                        color="#ffffff" if dark else INK)
        # 2px surface gaps between cells
        ax.set_xticks(np.arange(-0.5, len(hours)), minor=True)
        ax.set_yticks(np.arange(-0.5, len(lines)), minor=True)
        ax.grid(which="minor", color=SURFACE, linewidth=2)
        ax.tick_params(which="both", length=0)
        ax.set_yticks(range(len(lines)), lines)
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=6)
        for spine in ax.spines.values():
            spine.set_visible(False)
    axes[-1].set_xticks(range(len(hours)), [f"{h:02d}" for h in hours])
    axes[-1].set_xlabel("Hour of day")
    bar = fig.colorbar(image, ax=axes, shrink=0.5, pad=0.02, ticks=[0.5, 1.0, 1.5, 2.0])
    bar.set_label("Load ratio (demand / capacity). 1.00 = exactly full")
    bar.outline.set_visible(False)
    fig.suptitle("Load ratio by line and hour, average day", x=0.07, ha="left", fontsize=13, fontweight="bold")
    fig.savefig(FIGURES / "load_ratio_heatmap.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def budget_tradeoff():
    t = pd.read_csv(RESULTS / "budget_tradeoff.csv")
    series = [
        ("budget", "Extra trips only", ORANGE),
        ("combined", "Extra trips + rescheduling", BLUE),
    ]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for key, label, color in series:
        part = t[t["scenario"] == key]
        x, y = part["extra_trip_budget"].to_numpy(), part["passengers_over_capacity"].to_numpy() / 1000
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=label)
        ax.annotate(f"{y[0]:.0f}k", (x[0], y[0]), textcoords="offset points", xytext=(8, 2),
                    fontsize=9, color=INK_SECONDARY)
    ax.set_xlabel("Extra trips per day across the network")
    ax.set_ylabel("Passengers over capacity per day (thousands)")
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=-3)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("What extra trips buy, with and without rescheduling", loc="left", fontsize=12, fontweight="bold")
    fig.savefig(FIGURES / "budget_tradeoff.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def match_day_extra_demand():
    d = pd.read_csv(RESULTS / "match_day_extra_demand.csv", encoding="utf-8-sig")
    total = d.groupby(["team", "hour_offset"])["extra_demand"].sum().reset_index()
    series = [("beşiktaş", "Beşiktaş", BLUE), ("fenerbahçe", "Fenerbahçe", ORANGE), ("galatasaray", "Galatasaray", AQUA)]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for key, label, color in series:
        part = total[total["team"] == key].sort_values("hour_offset")
        x, y = part["hour_offset"].to_numpy(), part["extra_demand"].to_numpy() / 1000
        ax.plot(x, y, color=color, linewidth=2, label=label)
    ax.axvline(0, color=AXIS, linewidth=1)
    ax.text(0.2, 0.5, "kick-off", fontsize=9, color=MUTED, va="bottom")
    ax.set_xlabel("Hours from kick-off")
    ax.set_ylabel("Extra station entries per hour (thousands)")
    ax.set_ylim(bottom=0)
    ax.set_xticks(range(-12, 13, 2))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Extra rail demand around football matches, all lines", loc="left", fontsize=12, fontweight="bold")
    fig.savefig(FIGURES / "match_day_extra_demand.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    load_ratio_heatmap()
    budget_tradeoff()
    match_day_extra_demand()
    print(f"Saved 3 figures -> {FIGURES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
