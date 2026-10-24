"""Plotting module for RSSI correlation analysis.

Generates a combined figure containing:
1. Top horizontal bar chart of Pearson correlation coefficients with [-1, 1] fixed axis.
2. Bottom 3 scatter panels with coordinate-aggregated bubble markers proportional to observation counts.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Sequence

import matplotlib

# Ensure headless execution backend
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

SCATTER_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("Alice", "Bob", "Alice vs Bob"),
    ("Alice", "Eve1-Alice", "Alice vs Eve1-Alice"),
    ("Bob", "Eve1-Bob", "Bob vs Eve1-Bob"),
)


def aggregate_coordinate_counts(
    x: Sequence[float | int],
    y: Sequence[float | int],
) -> tuple[list[float], list[float], list[int]]:
    """Aggregate identical (x, y) coordinates and compute observation counts.

    Args:
        x: Sequence of x-coordinates.
        y: Sequence of y-coordinates.

    Returns:
        tuple[list[float], list[float], list[int]]:
            (unique_x, unique_y, counts) where each count is the number of times
            (unique_x[i], unique_y[i]) appeared in the original paired observations.
    """
    if len(x) != len(y):
        raise ValueError(
            f"Series x and y must have identical length: len(x)={len(x)}, len(y)={len(y)}."
        )

    pts = list(zip(x, y))
    counts_map = Counter(pts)

    unique_x: list[float] = []
    unique_y: list[float] = []
    counts: list[int] = []

    for (ux, uy), c in counts_map.items():
        unique_x.append(float(ux))
        unique_y.append(float(uy))
        counts.append(c)

    return unique_x, unique_y, counts


def plot_combined_correlation_figure(
    data: dict[str, list[float]],
    results: list[dict[str, str | int | float]],
    prefix_path: str | Path,
) -> tuple[Path, Path]:
    """Create and save the combined correlation figure in PNG (300 dpi) and PDF formats.

    Layout:
    - Top: Horizontal correlation bar chart across the width (-1.0 to +1.0 fixed axis).
    - Bottom: 3 scatter panels (Alice vs Bob, Alice vs Eve1-Alice, Bob vs Eve1-Bob)
      with area proportional to duplicate observation count.

    Args:
        data: Dictionary of loaded RSSI observations (Alice, Bob, Eve1-Alice, Eve1-Bob).
        results: Correlation results containing pair, sample_count, correlation_coefficient, data_kind.
        prefix_path: File path prefix for saving .png and .pdf figures.

    Returns:
        tuple[Path, Path]: (png_path, pdf_path) of the saved files.
    """
    prefix = Path(prefix_path)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    png_path = prefix.with_name(f"{prefix.name}.png")
    pdf_path = prefix.with_name(f"{prefix.name}.pdf")

    # Map pair name to correlation and sample count
    corr_lookup: dict[str, tuple[float, int]] = {}
    for r in results:
        pair_str = str(r["pair"])
        corr_lookup[pair_str] = (float(r["correlation_coefficient"]), int(r["sample_count"]))

    # Setup figure with 2 rows: row 0 for bar chart, row 1 for 3 scatter plots
    fig = plt.figure(figsize=(15, 11), layout="constrained")
    gs = gridspec.GridSpec(2, 3, figure=fig, height_ratios=[1.0, 2.2])

    fig.suptitle(
        "Dummy RSSI correlation analysis\n"
        "[Software validation using dummy data. Channel probing remains postponed; results do not support real-channel security conclusions]",
        fontsize=13,
        fontweight="bold",
    )

    # ==========================================
    # Top Panel: Horizontal Bar Chart
    # ==========================================
    ax_bar = fig.add_subplot(gs[0, :])

    bar_pairs = [
        ("Alice–Bob", "Alice–Bob"),
        ("Alice–Eve1-Alice", "Alice–Eve1-Alice"),
        ("Bob–Eve1-Bob", "Bob–Eve1-Bob"),
    ]

    labels: list[str] = []
    rhos: list[float] = []
    sample_sizes: list[int] = []

    for display_name, key in bar_pairs:
        rho_val, n_val = corr_lookup.get(key, (0.0, 0))
        labels.append(display_name)
        rhos.append(rho_val)
        sample_sizes.append(n_val)

    # Invert order for top-to-bottom bar presentation
    y_positions = list(range(len(labels)))[::-1]
    labels_rev = labels[::-1]
    rhos_rev = rhos[::-1]
    sample_sizes_rev = sample_sizes[::-1]

    # Use distinct, accessible colors: primary blue for legit, amber/orange for eavesdroppers
    colors = []
    for lbl in labels_rev:
        if "Eve" in lbl:
            colors.append("#d95f02")
        else:
            colors.append("#1b9e77")

    bars = ax_bar.barh(y_positions, rhos_rev, color=colors, height=0.55, edgecolor="black", alpha=0.85)

    ax_bar.set_yticks(y_positions)
    ax_bar.set_yticklabels(labels_rev, fontsize=11, fontweight="bold")
    ax_bar.set_xlim(-1.0, 1.0)
    ax_bar.axvline(0.0, color="black", linestyle="--", linewidth=1.2, alpha=0.75)
    ax_bar.grid(True, axis="x", linestyle=":", alpha=0.6)
    ax_bar.set_xlabel("Pearson Correlation Coefficient ($\\rho$)", fontsize=11)
    ax_bar.set_title("Pearson Correlation at Zero Lag (PA.pdf Eq 3.62)", fontsize=12, pad=8)

    # Add 4-decimal place coefficient labels and sample count
    for idx, (bar, rho, n) in enumerate(zip(bars, rhos_rev, sample_sizes_rev)):
        y_pos = bar.get_y() + bar.get_height() / 2.0
        label_text = f"  {rho:+.4f} (N={n})"
        if rho >= 0:
            ax_bar.text(rho, y_pos, label_text, va="center", ha="left", fontsize=10, fontweight="bold")
        else:
            ax_bar.text(rho, y_pos, f"{rho:+.4f} (N={n})  ", va="center", ha="right", fontsize=10, fontweight="bold")

    # ==========================================
    # Bottom Panels: 3 Scatter Plots
    # ==========================================
    base_marker_area = 5.0  # Area multiplier for count = 1

    for col_idx, (c1, c2, title) in enumerate(SCATTER_PAIRS):
        ax_scatter = fig.add_subplot(gs[1, col_idx])

        x_series = data[c1]
        y_series = data[c2]
        total_samples = len(x_series)

        ux, uy, counts = aggregate_coordinate_counts(x_series, y_series)
        areas = [base_marker_area * c for c in counts]

        # Find correlation for this pair
        pair_key = f"{c1}–{c2}"
        rho_val, _ = corr_lookup.get(pair_key, (0.0, total_samples))

        scatter_color = "#d95f02" if "Eve" in title else "#1b9e77"
        ax_scatter.scatter(
            ux,
            uy,
            s=areas,
            color=scatter_color,
            alpha=0.6,
            edgecolors="black",
            linewidths=0.7,
        )

        ax_scatter.set_title(
            f"{title}\n$\\rho = {rho_val:+.4f}$ (N={total_samples})",
            fontsize=12,
            fontweight="bold",
            pad=10,
        )
        ax_scatter.set_xlabel(f"{c1} RSSI", fontsize=11)
        ax_scatter.set_ylabel(f"{c2} RSSI", fontsize=11)
        ax_scatter.grid(True, linestyle=":", alpha=0.5)

        # Build clean count legend
        max_c = max(counts) if counts else 1
        if max_c <= 10:
            legend_counts = [1, 5, 10]
        elif max_c <= 50:
            legend_counts = [1, 10, 25, 50]
        elif max_c <= 120:
            legend_counts = [1, 20, 50, 100]
        else:
            legend_counts = [1, 25, 75, 150]

        legend_handles = []
        legend_labels = []
        for lc in legend_counts:
            if lc <= max_c * 1.2:
                handle = ax_scatter.scatter(
                    [],
                    [],
                    s=base_marker_area * lc,
                    color="#666666",
                    alpha=0.6,
                    edgecolors="black",
                    linewidths=0.7,
                )
                legend_handles.append(handle)
                legend_labels.append(f"{lc} obs")

        ax_scatter.legend(
            legend_handles,
            legend_labels,
            title="Duplicates / Area",
            loc="upper left",
            fontsize=8.5,
            title_fontsize=9,
            framealpha=0.85,
        )

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    return png_path, pdf_path
