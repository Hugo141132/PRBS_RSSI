"""Plotting module for RSSI correlation analysis.

Generates a combined figure containing:
1. Top horizontal bar chart of Pearson correlation coefficients with [-1, 1] fixed axis.
2. Bottom 3 scatter panels with coordinate-aggregated bubble markers proportional to observation counts.
"""

from __future__ import annotations

from collections import Counter
import csv
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

# Ensure headless execution backend
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np

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


def plot_filtering_comparison_figure(
    raw_data: Mapping[str, Sequence[float]],
    filtered_data: Mapping[str, Sequence[float]],
    results: Sequence[Mapping[str, Any]],
    prefix_path: str | Path,
) -> tuple[Path, Path]:
    """Create and save comparison figure between raw and filtered RSSI data.

    Layout:
    - Top Left (2 cols): Grouped horizontal bar chart of Pearson correlation coefficients (Raw vs Filtered).
    - Top Right (1 col): Time-series trajectory snippet (first 80 samples) of Alice & Bob raw vs filtered.
    - Bottom (3 cols): 3 scatter panels of filtered data with bubble markers for discrete coordinates.

    Args:
        raw_data: Mapping of raw RSSI observations.
        filtered_data: Mapping of filtered RSSI observations.
        results: Sequence of result records with raw_correlation, filtered_correlation, correlation_delta.
        prefix_path: File path prefix for saving .png and .pdf figures.

    Returns:
        tuple[Path, Path]: (png_path, pdf_path) of the saved files.
    """
    prefix = Path(prefix_path)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    png_path = prefix.with_name(f"{prefix.name}.png")
    pdf_path = prefix.with_name(f"{prefix.name}.pdf")

    # Map pair to results
    res_map: dict[str, Mapping[str, Any]] = {}
    for r in results:
        res_map[str(r["pair"])] = r

    fig = plt.figure(figsize=(16, 11), layout="constrained")
    gs = gridspec.GridSpec(2, 3, figure=fig, height_ratios=[1.1, 1.9])

    fig.suptitle(
        "Dummy RSSI Filtering & Correlation Comparison (Modified Sage–Husa AKF)\n"
        "[Software validation using dummy data. Channel probing remains postponed; results do not support real-channel security conclusions]",
        fontsize=13,
        fontweight="bold",
    )

    # ==========================================
    # Top Left Panel: Grouped Horizontal Bar Chart
    # ==========================================
    ax_bar = fig.add_subplot(gs[0, :2])

    bar_pairs = [
        ("Alice–Bob", "Alice–Bob"),
        ("Alice–Eve1-Alice", "Alice–Eve1-Alice"),
        ("Bob–Eve1-Bob", "Bob–Eve1-Bob"),
    ]

    labels = [p[0] for p in bar_pairs][::-1]
    keys = [p[1] for p in bar_pairs][::-1]

    raw_rhos = [float(res_map[k]["raw_correlation"]) for k in keys]
    filt_rhos = [float(res_map[k]["filtered_correlation"]) for k in keys]
    deltas = [float(res_map[k].get("correlation_delta", filt_rhos[i] - raw_rhos[i])) for i, k in enumerate(keys)]

    y_indices = list(range(len(labels)))
    bar_height = 0.32

    y_raw = [y - bar_height / 2.0 for y in y_indices]
    y_filt = [y + bar_height / 2.0 for y in y_indices]

    ax_bar.barh(
        y_raw,
        raw_rhos,
        height=bar_height,
        color="#7f7f7f",
        edgecolor="black",
        alpha=0.75,
        label="Raw RSSI (Zero Lag)",
    )

    filt_colors = ["#d95f02" if "Eve" in lbl else "#1b9e77" for lbl in labels]
    ax_bar.barh(
        y_filt,
        filt_rhos,
        height=bar_height,
        color=filt_colors,
        edgecolor="black",
        alpha=0.9,
        label="Filtered RSSI (MSHKF)",
    )

    ax_bar.set_yticks(y_indices)
    ax_bar.set_yticklabels(labels, fontsize=11, fontweight="bold")
    ax_bar.set_xlim(-1.0, 1.0)
    ax_bar.axvline(0.0, color="black", linestyle="--", linewidth=1.2, alpha=0.75)
    ax_bar.grid(True, axis="x", linestyle=":", alpha=0.6)
    ax_bar.set_xlabel("Pearson Correlation Coefficient ($\\rho$)", fontsize=11)
    ax_bar.set_title("Pearson Correlation Comparison (Raw vs Filtered)", fontsize=12, pad=6)
    ax_bar.legend(loc="upper left", fontsize=9.5, framealpha=0.9)

    # Annotate bars
    for idx in range(len(labels)):
        r_raw = raw_rhos[idx]
        r_filt = filt_rhos[idx]
        delta = deltas[idx]
        yr = y_raw[idx]
        yf = y_filt[idx]

        # Raw label
        txt_raw = f"  {r_raw:+.4f}" if r_raw >= 0 else f"{r_raw:+.4f}  "
        ha_r = "left" if r_raw >= 0 else "right"
        ax_bar.text(r_raw, yr, txt_raw, va="center", ha=ha_r, fontsize=9, color="#333333")

        # Filtered label
        txt_filt = f"  {r_filt:+.4f} ($\\Delta$: {delta:+.4f})" if r_filt >= 0 else f"{r_filt:+.4f} ($\\Delta$: {delta:+.4f})  "
        ha_f = "left" if r_filt >= 0 else "right"
        ax_bar.text(r_filt, yf, txt_filt, va="center", ha=ha_f, fontsize=9.5, fontweight="bold")

    # ==========================================
    # Top Right Panel: Time-series Trajectory Snippet
    # ==========================================
    ax_ts = fig.add_subplot(gs[0, 2])
    n_plot = min(80, len(raw_data["Alice"]))
    t_idx = list(range(n_plot))

    ax_ts.plot(t_idx, raw_data["Alice"][:n_plot], label="Alice (Raw)", color="#a6cee3", linestyle="--", alpha=0.7, linewidth=1.2)
    ax_ts.plot(t_idx, filtered_data["Alice"][:n_plot], label="Alice (MSHKF)", color="#1f78b4", linewidth=1.8)
    ax_ts.plot(t_idx, raw_data["Bob"][:n_plot], label="Bob (Raw)", color="#b2df8a", linestyle="--", alpha=0.7, linewidth=1.2)
    ax_ts.plot(t_idx, filtered_data["Bob"][:n_plot], label="Bob (MSHKF)", color="#33a02c", linewidth=1.8)

    ax_ts.set_title(f"Smoothing Trajectory (Samples 0–{n_plot-1})", fontsize=11, pad=6)
    ax_ts.set_xlabel("Sample Index", fontsize=10)
    ax_ts.set_ylabel("RSSI (dBm)", fontsize=10)
    ax_ts.grid(True, linestyle=":", alpha=0.5)
    ax_ts.legend(loc="lower right", fontsize=8, framealpha=0.85)

    # ==========================================
    # Bottom Panels: 3 Filtered Scatter Plots
    # ==========================================
    base_marker_area = 5.0
    for col_idx, (c1, c2, title) in enumerate(SCATTER_PAIRS):
        ax_scatter = fig.add_subplot(gs[1, col_idx])

        x_series = filtered_data[c1]
        y_series = filtered_data[c2]
        total_samples = len(x_series)

        # Round to 1 decimal for bubble aggregation of continuous filtered states
        x_rounded = [round(v, 1) for v in x_series]
        y_rounded = [round(v, 1) for v in y_series]

        ux, uy, counts = aggregate_coordinate_counts(x_rounded, y_rounded)
        areas = [base_marker_area * c for c in counts]

        pair_key = f"{c1}–{c2}"
        res_pair = res_map.get(pair_key, {})
        r_filt = float(res_pair.get("filtered_correlation", 0.0))
        r_raw = float(res_pair.get("raw_correlation", 0.0))
        d_val = float(res_pair.get("correlation_delta", r_filt - r_raw))

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
            f"{title} (Filtered)\n$\\rho_{{filt}} = {r_filt:+.4f}$ (Raw: ${r_raw:+.4f}$, $\\Delta$: ${d_val:+.4f}$)",
            fontsize=11,
            fontweight="bold",
            pad=8,
        )
        ax_scatter.set_xlabel(f"{c1} Filtered RSSI (dBm)", fontsize=10)
        ax_scatter.set_ylabel(f"{c2} Filtered RSSI (dBm)", fontsize=10)
        ax_scatter.grid(True, linestyle=":", alpha=0.5)

        max_c = max(counts) if counts else 1
        if max_c <= 10:
            legend_counts = [1, 5, 10]
        elif max_c <= 40:
            legend_counts = [1, 10, 25]
        else:
            legend_counts = [1, 15, 30, 50]

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
            title="Density (0.1 dBm bins)",
            loc="upper left",
            fontsize=8,
            title_fontsize=8.5,
            framealpha=0.85,
        )

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    return png_path, pdf_path


def plot_kar_comparison_figure(
    quant_result: Any,
    prefix_path: str | Path,
) -> tuple[Path, Path]:
    """Create and save Key Agreement Rate (KAR) comparison figure in PNG (300 dpi) and PDF formats.

    Layout:
    - Top Left Panel: Grouped bar chart comparing 2-bit Gray KAR and 4-bit KAR
      across evaluation pairs with a fixed 0–100% axis and exact readable value labels.
    - Top Right Panel: Bar chart of Sample-Level Agreement Rate (Q(A) == Q(B))
      with a fixed 0–100% axis.
    - Bottom Left Panel: Table summarizing exact numerical metrics (Level Agreement,
      2-bit KAR, 4-bit KAR, equal mismatch counts, total bits).
    - Bottom Right Panel: Explanatory text box detailing the mathematical origin of
      the 4-bit KAR increase (fixed prefix '10', equal Hamming distances, exact
      linear relation KAR_4bit = 50% + KAR_2bit / 2).

    Args:
        quant_result: ChannelQuantizationResult instance with metrics and configurations.
        prefix_path: Path prefix for saving .png and .pdf figures.

    Returns:
        tuple[Path, Path]: (png_path, pdf_path) of the saved files.
    """
    prefix = Path(prefix_path)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    png_path = prefix.with_name(f"{prefix.name}.png")
    pdf_path = prefix.with_name(f"{prefix.name}.pdf")

    pair_metrics = quant_result.pair_metrics

    fig = plt.figure(figsize=(15, 10), layout="constrained")
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1.2, 0.9], width_ratios=[1.2, 0.8])

    fig.suptitle(
        "Dummy RSSI Quantization & Key Agreement Rate (KAR) Analysis (Modified ADQ)",
        fontsize=13,
        fontweight="bold",
    )

    # -------------------------------------------------------------
    # 1. Top Left Panel: Grouped Bar Chart (2-bit Gray vs 4-bit KAR)
    # -------------------------------------------------------------
    ax_kar = fig.add_subplot(gs[0, 0])

    display_labels = []
    kar_2b_vals = []
    kar_4b_vals = []
    lvl_agr_vals = []
    mismatch_counts = []
    bit_counts_2b = []
    bit_counts_4b = []

    for pm in pair_metrics:
        p_name = pm["pair"]
        if "Eve" in p_name:
            display_labels.append(f"{p_name}\n(Eavesdropper)")
        else:
            display_labels.append(f"{p_name}\n(Legitimate)")

        k2 = float(pm["kar_2bit"])
        k4 = float(pm["kar_4bit"])
        la = float(pm["level_agreement_rate"])
        b2_cnt = int(pm["bit_count_2bit"])
        b4_cnt = int(pm["bit_count_4bit"])

        kar_2b_vals.append(k2)
        kar_4b_vals.append(k4)
        lvl_agr_vals.append(la)
        bit_counts_2b.append(b2_cnt)
        bit_counts_4b.append(b4_cnt)

        # Compute mismatches
        ch_a = pm.get("channel_a")
        ch_b = pm.get("channel_b")
        if ch_a and ch_b and hasattr(quant_result, "bitstreams_2bit"):
            bs_a = quant_result.bitstreams_2bit.get(ch_a, "")
            bs_b = quant_result.bitstreams_2bit.get(ch_b, "")
            if bs_a and bs_b and len(bs_a) == len(bs_b):
                mismatches = sum(1 for a, b in zip(bs_a, bs_b) if a != b)
            else:
                mismatches = round((100.0 - k2) / 100.0 * b2_cnt)
        else:
            mismatches = round((100.0 - k2) / 100.0 * b2_cnt)
        mismatch_counts.append(mismatches)

    n_pairs = len(display_labels)
    x = [float(i) for i in range(n_pairs)]
    bar_w = 0.35

    x_2b = [xi - bar_w / 2.0 for xi in x]
    x_4b = [xi + bar_w / 2.0 for xi in x]

    rects1 = ax_kar.bar(
        x_2b,
        kar_2b_vals,
        width=bar_w,
        color="#2b5c8f",
        edgecolor="black",
        alpha=0.9,
        label="2-bit Gray KAR (PA.pdf Eq 3.64)",
    )
    rects2 = ax_kar.bar(
        x_4b,
        kar_4b_vals,
        width=bar_w,
        color="#7570b3",
        edgecolor="black",
        alpha=0.9,
        label="4-bit KAR (PA.pdf Section 3.2.3)",
    )

    # Annotate bar values
    for rect in rects1:
        h = rect.get_height()
        ax_kar.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
    for rect in rects2:
        h = rect.get_height()
        ax_kar.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax_kar.set_ylim(0, 105)
    ax_kar.set_ylabel("Key Agreement Rate (%)", fontsize=11, fontweight="bold")
    ax_kar.set_title(
        "Key Agreement Rate Comparison (2-bit Gray vs 4-bit)",
        fontsize=11.5,
        fontweight="bold",
        pad=8,
    )
    ax_kar.set_xticks(x)
    ax_kar.set_xticklabels(display_labels, fontsize=10)
    ax_kar.grid(True, axis="y", linestyle=":", alpha=0.6)
    ax_kar.legend(loc="lower right", fontsize=9.5, framealpha=0.95)

    # -------------------------------------------------------------
    # 2. Top Right Panel: Sample-Level Agreement Rate
    # -------------------------------------------------------------
    ax_lvl = fig.add_subplot(gs[0, 1])

    lvl_colors = ["#1b9e77" if "Legitimate" in lbl else "#d95f02" for lbl in display_labels]
    rects_lvl = ax_lvl.bar(
        x,
        lvl_agr_vals,
        width=0.48,
        color=lvl_colors,
        edgecolor="black",
        alpha=0.88,
        label="Sample-Level Agreement",
    )

    for rect in rects_lvl:
        h = rect.get_height()
        ax_lvl.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax_lvl.set_ylim(0, 105)
    ax_lvl.set_ylabel("Agreement Rate (%)", fontsize=11, fontweight="bold")
    ax_lvl.set_title("Quantization Level Agreement (Q(A) == Q(B))", fontsize=12, fontweight="bold", pad=8)
    ax_lvl.set_xticks(x)
    ax_lvl.set_xticklabels(display_labels, fontsize=10)
    ax_lvl.grid(True, axis="y", linestyle=":", alpha=0.6)

    # -------------------------------------------------------------
    # 3. Bottom Left Panel: Metrics Summary Table
    # -------------------------------------------------------------
    ax_tbl = fig.add_subplot(gs[1, 0])
    ax_tbl.axis("off")

    table_data = []
    for i in range(n_pairs):
        p_name = pair_metrics[i]["pair"]
        table_data.append([
            p_name,
            f"{lvl_agr_vals[i]:.2f}%",
            f"{kar_2b_vals[i]:.2f}%",
            f"{kar_4b_vals[i]:.2f}%",
            f"{mismatch_counts[i]}",
            f"{bit_counts_2b[i]:,} / {bit_counts_4b[i]:,}",
        ])

    col_labels = ["Pair", "Level Agreement", "2-bit Gray KAR", "4-bit KAR", "Bit Mismatches", "Bits (2b / 4b)"]
    tbl = ax_tbl.table(
        cellText=table_data,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 1.9)

    for (r_idx, c_idx), cell in tbl.get_celld().items():
        if r_idx == 0:
            cell.set_facecolor("#2b5c8f")
            cell.set_text_props(color="white", weight="bold")
        else:
            cell.set_facecolor("#f8f9fa" if r_idx % 2 == 1 else "white")

    ax_tbl.set_title("Quantitative Metric Summary Across Evaluated Pairs", fontsize=11, fontweight="bold", pad=12)

    # -------------------------------------------------------------
    # 4. Bottom Right Panel: Explanatory Annotation Box
    # -------------------------------------------------------------
    ax_note = fig.add_subplot(gs[1, 1])
    ax_note.axis("off")

    explanation_text = (
        "Mathematical Origin of 4-bit KAR Gain:\n\n"
        "1. Fixed-Prefix Effect:\n"
        "   4-bit encoding {0: '1010', 1: '1011', 2: '1001'} shares the\n"
        "   fixed prefix '10' across all symbols, guaranteeing a\n"
        "   structural minimum agreement of 50%.\n\n"
        "2. Identical Hamming Distances:\n"
        "   Pairwise distances between symbols are identical across encodings:\n"
        "   d_H(0, 1) = 1, d_H(1, 2) = 1, d_H(0, 2) = 2 in both 2-bit & 4-bit.\n"
        "   Hence: N_mismatch,4bit ≡ N_mismatch,2bit for any sequence.\n\n"
        "3. Exact Linear Relation:\n"
        "   KAR_4bit = 50% + KAR_2bit / 2\n"
        "   Doubling total bits mechanically halves the disagreement rate.\n\n"
        "4. Security Conclusion:\n"
        "   Higher 4-bit KAR reflects encoding structure, NOT enhanced\n"
        "   channel agreement or additional secret key entropy."
    )

    ax_note.text(
        0.02,
        0.5,
        explanation_text,
        fontsize=9.2,
        va="center",
        ha="left",
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.7", facecolor="#f4f6f9", edgecolor="#b0bec5", linewidth=1.2),
    )

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    return png_path, pdf_path


STANDARD_PRBS_EVALUATION_PAIRS: tuple[str, ...] = (
    "Alice–Bob",
    "Alice–Eve1-Alice",
    "Bob–Eve1-Bob",
)


def _normalize_pair_name(pair_str: str) -> str:
    """Normalize pair label string to canonical en-dash representation."""
    cleaned = pair_str.strip()
    cleaned = cleaned.replace(" vs ", "–").replace(" - ", "–").replace("-", "–")
    if "Alice" in cleaned and "Bob" in cleaned and "Eve" not in cleaned:
        return "Alice–Bob"
    if "Alice" in cleaned and "Eve1" in cleaned:
        return "Alice–Eve1-Alice"
    if "Bob" in cleaned and "Eve1" in cleaned:
        return "Bob–Eve1-Bob"
    return cleaned


def plot_prbs_kar_comparison_figure(
    prbs_metrics: Sequence[Mapping[str, Any]] | Any | str | Path,
    prefix_path: str | Path,
    title_prefix: str = "Dummy RSSI",
) -> tuple[Path, Path]:
    """Create and save reproducible 2x2 figure comparing before/after PRBS Key Agreement Rates (KAR).

    Layout:
    - Top-Left: Grouped bars comparing pre- vs post-PRBS KAR for 2-bit Gray path (0-100% axis).
    - Top-Right: Grouped bars comparing pre- vs post-PRBS KAR for 4-bit path (0-100% axis).
    - Bottom-Left: Sample-level agreement rate Q(A) == Q(B) across channel pairs (0-100% axis).
    - Bottom-Right: Compact summary table with before/after KAR and signed differences in percentage points (pp),
      accompanied by scientific constraints notes.

    Evaluation Pairs are strictly ordered:
    1. Alice–Bob (Legitimate)
    2. Alice–Eve1-Alice (Eavesdropper)
    3. Bob–Eve1-Bob (Eavesdropper)

    Args:
        prbs_metrics: Sequence of metric dicts, MultiChannelPRBSResult instance, or path to CSV metrics.
        prefix_path: Path prefix for output files (.png and .pdf).
        title_prefix: Prefix string for figure title (default: "Dummy RSSI").

    Returns:
        tuple[Path, Path]: (png_path, pdf_path) of the saved 300 dpi PNG and vector PDF files.

    Raises:
        ValueError: If prbs_metrics is invalid, missing required evaluation pairs, contains non-finite
                    values, or percentage rates are outside [0.0, 100.0].
    """
    prefix = Path(prefix_path)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    png_path = prefix.with_name(f"{prefix.name}.png")
    pdf_path = prefix.with_name(f"{prefix.name}.pdf")

    # 1. Ingest input metrics
    raw_records: list[dict[str, Any]] = []
    if isinstance(prbs_metrics, (str, Path)):
        csv_p = Path(prbs_metrics)
        if not csv_p.exists():
            raise ValueError(f"PRBS metrics CSV file does not exist: {csv_p}")
        with open(csv_p, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            raw_records = [dict(row) for row in reader]
    elif hasattr(prbs_metrics, "pair_metrics"):
        raw_records = [dict(pm) for pm in getattr(prbs_metrics, "pair_metrics")]
    elif isinstance(prbs_metrics, Sequence):
        raw_records = [dict(item) for item in prbs_metrics]
    else:
        raise ValueError(
            f"Unsupported prbs_metrics type: {type(prbs_metrics)}. Expected CSV path, MultiChannelPRBSResult, or list of dicts."
        )

    if not raw_records:
        raise ValueError("PRBS metrics record list is empty.")

    # 2. Build normalized lookup keyed by canonical pair name
    pair_lookup: dict[str, dict[str, Any]] = {}
    for row in raw_records:
        pair_val = str(row.get("pair", row.get("pair_label", "")))
        canonical = _normalize_pair_name(pair_val)
        pair_lookup[canonical] = row

    # 3. Validate required pairs coverage
    for required_pair in STANDARD_PRBS_EVALUATION_PAIRS:
        if required_pair not in pair_lookup:
            raise ValueError(
                f"Missing required evaluation pair '{required_pair}' in PRBS metrics. Available pairs: {list(pair_lookup.keys())}"
            )

    # 4. Extract and validate metrics for each required pair
    display_pairs = list(STANDARD_PRBS_EVALUATION_PAIRS)
    display_labels = [
        "Alice–Bob\n(Legitimate)",
        "Alice–Eve1-Alice\n(Eavesdropper)",
        "Bob–Eve1-Bob\n(Eavesdropper)",
    ]

    level_agreements: list[float] = []
    kar_2b_before: list[float] = []
    kar_2b_after: list[float] = []
    kar_2b_delta: list[float] = []
    kar_4b_before: list[float] = []
    kar_4b_after: list[float] = []
    kar_4b_delta: list[float] = []

    sample_counts: list[int] = []
    bit_counts_2b_pre: list[int] = []
    bit_counts_2b_post: list[int] = []
    bit_counts_4b_pre: list[int] = []
    bit_counts_4b_post: list[int] = []

    def _extract_float(row: dict[str, Any], *keys: str, name: str) -> float:
        for k in keys:
            if k in row and row[k] is not None and str(row[k]).strip() != "":
                try:
                    val = float(row[k])
                    if not math.isfinite(val):
                        raise ValueError(f"Metric '{name}' for pair '{row.get('pair')}' is non-finite: {val}")
                    if val < 0.0 or val > 100.0:
                        raise ValueError(f"Percentage metric '{name}' for pair '{row.get('pair')}' out of range [0.0, 100.0]: {val}")
                    return val
                except ValueError as e:
                    if "out of range" in str(e) or "non-finite" in str(e):
                        raise
                    raise ValueError(f"Cannot parse metric '{name}' as float: {row[k]!r}") from e
        raise ValueError(f"Missing required metric field for '{name}'. Checked keys: {keys} in {row}")

    def _extract_int(row: dict[str, Any], *keys: str, default: int) -> int:
        for k in keys:
            if k in row and row[k] is not None and str(row[k]).strip() != "":
                try:
                    return int(row[k])
                except (ValueError, TypeError):
                    pass
        return default

    for p_name in display_pairs:
        row = pair_lookup[p_name]
        lvl_agr = _extract_float(row, "level_agreement_rate", "level_agreement", name="level_agreement_rate")
        k2_pre = _extract_float(row, "kar_2bit_before", "pre_prbs_kar_2bit", name="kar_2bit_before")
        k2_post = _extract_float(row, "kar_2bit_after", "post_prbs_kar_2bit", name="kar_2bit_after")
        k4_pre = _extract_float(row, "kar_4bit_before", "pre_prbs_kar_4bit", name="kar_4bit_before")
        k4_post = _extract_float(row, "kar_4bit_after", "post_prbs_kar_4bit", name="kar_4bit_after")

        # Full precision delta in percentage points (pp)
        d2 = k2_post - k2_pre
        d4 = k4_post - k4_pre

        s_cnt = _extract_int(row, "sample_count", default=500)
        b2_pre = _extract_int(row, "bit_count_2bit_before", "pre_prbs_bits_2bit", default=1000)
        b2_post = _extract_int(row, "bit_count_2bit_after", "post_prbs_bits_2bit", default=1500)
        b4_pre = _extract_int(row, "bit_count_4bit_before", "pre_prbs_bits_4bit", default=2000)
        b4_post = _extract_int(row, "bit_count_4bit_after", "post_prbs_bits_4bit", default=7500)

        level_agreements.append(lvl_agr)
        kar_2b_before.append(k2_pre)
        kar_2b_after.append(k2_post)
        kar_2b_delta.append(d2)
        kar_4b_before.append(k4_pre)
        kar_4b_after.append(k4_post)
        kar_4b_delta.append(d4)

        sample_counts.append(s_cnt)
        bit_counts_2b_pre.append(b2_pre)
        bit_counts_2b_post.append(b2_post)
        bit_counts_4b_pre.append(b4_pre)
        bit_counts_4b_post.append(b4_post)

    # 5. Build 2x2 Figure
    fig = plt.figure(figsize=(16, 12), layout="constrained")
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1.15, 1.0])

    fig.suptitle(
        f"{title_prefix} Key Agreement Rate (KAR) Analysis: Per-Sample PRBS Expansion\n"
        "Galois XOR-LFSR Evaluation (PA.pdf Section 3.2.4, Equations 3.24–3.26)",
        fontsize=14,
        fontweight="bold",
    )

    n_pairs = len(display_labels)
    x = [float(i) for i in range(n_pairs)]
    bar_w = 0.35
    x_pre = [xi - bar_w / 2.0 for xi in x]
    x_post = [xi + bar_w / 2.0 for xi in x]

    # Accessible palette: Navy for Pre-PRBS, Deep Orange for Post-PRBS
    c_pre = "#2b5c8f"
    c_post = "#e66101"

    # -------------------------------------------------------------
    # Panel 1: Top-Left: Grouped Bars 2-bit Gray Path
    # -------------------------------------------------------------
    ax_2b = fig.add_subplot(gs[0, 0])
    rects_2b_pre = ax_2b.bar(
        x_pre,
        kar_2b_before,
        width=bar_w,
        color=c_pre,
        edgecolor="black",
        linewidth=0.8,
        label="Pre-PRBS (Quantization Baseline, 2b Gray)",
    )
    rects_2b_post = ax_2b.bar(
        x_post,
        kar_2b_after,
        width=bar_w,
        color=c_post,
        edgecolor="black",
        linewidth=0.8,
        label="Post-PRBS (Galois XOR-LFSR, 3b/sample)",
    )

    ax_2b.set_ylim(0, 100)
    ax_2b.set_ylabel("Key Agreement Rate (%)", fontsize=11, fontweight="bold")
    ax_2b.set_title(
        "(a) 2-bit Gray Path: Pre- vs Post-PRBS Key Agreement Rate\n"
        f"Samples: N={sample_counts[0]} | Bit Counts: {bit_counts_2b_pre[0]:,}b (Pre) → {bit_counts_2b_post[0]:,}b (Post)",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax_2b.set_xticks(x)
    ax_2b.set_xticklabels(display_labels, fontsize=10)
    ax_2b.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax_2b.legend(loc="upper right", framealpha=0.95, fontsize=9.0)

    for i, rect in enumerate(rects_2b_pre):
        h = rect.get_height()
        ax_2b.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9.2,
            fontweight="bold",
            color=c_pre,
        )
    for i, rect in enumerate(rects_2b_post):
        h = rect.get_height()
        ax_2b.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9.2,
            fontweight="bold",
            color=c_post,
        )
        d_val = kar_2b_delta[i]
        d_color = "#b2182b" if d_val < 0 else "#2166ac"
        max_h = max(kar_2b_before[i], kar_2b_after[i])
        ax_2b.annotate(
            f"Δ = {d_val:+.2f} pp",
            xy=(x[i], max_h),
            xytext=(0, 16),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.8,
            fontweight="bold",
            color=d_color,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=d_color, alpha=0.95, linewidth=0.8),
        )

    # -------------------------------------------------------------
    # Panel 2: Top-Right: Grouped Bars 4-bit Path
    # -------------------------------------------------------------
    ax_4b = fig.add_subplot(gs[0, 1])
    rects_4b_pre = ax_4b.bar(
        x_pre,
        kar_4b_before,
        width=bar_w,
        color=c_pre,
        edgecolor="black",
        linewidth=0.8,
        label="Pre-PRBS (Quantization Baseline, 4b Code)",
    )
    rects_4b_post = ax_4b.bar(
        x_post,
        kar_4b_after,
        width=bar_w,
        color=c_post,
        edgecolor="black",
        linewidth=0.8,
        label="Post-PRBS (Galois XOR-LFSR, 15b/sample)",
    )

    ax_4b.set_ylim(0, 100)
    ax_4b.set_ylabel("Key Agreement Rate (%)", fontsize=11, fontweight="bold")
    ax_4b.set_title(
        "(b) 4-bit Path: Pre- vs Post-PRBS Key Agreement Rate\n"
        f"Samples: N={sample_counts[0]} | Bit Counts: {bit_counts_4b_pre[0]:,}b (Pre) → {bit_counts_4b_post[0]:,}b (Post)",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax_4b.set_xticks(x)
    ax_4b.set_xticklabels(display_labels, fontsize=10)
    ax_4b.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax_4b.legend(loc="upper right", framealpha=0.95, fontsize=9.0)

    for i, rect in enumerate(rects_4b_pre):
        h = rect.get_height()
        if h > 85.0:
            ax_4b.annotate(
                f"{h:.2f}%",
                xy=(rect.get_x() + rect.get_width() / 2.0, h - 2.0),
                ha="center",
                va="top",
                fontsize=9.2,
                fontweight="bold",
                color="white",
            )
        else:
            ax_4b.annotate(
                f"{h:.2f}%",
                xy=(rect.get_x() + rect.get_width() / 2.0, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9.2,
                fontweight="bold",
                color=c_pre,
            )
    for i, rect in enumerate(rects_4b_post):
        h = rect.get_height()
        ax_4b.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9.2,
            fontweight="bold",
            color=c_post,
        )
        d_val = kar_4b_delta[i]
        d_color = "#b2182b" if d_val < 0 else "#2166ac"
        if i == 0:
            ax_4b.annotate(
                f"Δ = {d_val:+.2f} pp",
                xy=(x[i], 94.0),
                ha="center",
                va="center",
                fontsize=8.8,
                fontweight="bold",
                color=d_color,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=d_color, alpha=0.95, linewidth=0.8),
            )
        elif i == 1:
            ax_4b.annotate(
                f"Δ = {d_val:+.2f} pp",
                xy=(x[i], 85.5),
                ha="center",
                va="center",
                fontsize=8.8,
                fontweight="bold",
                color=d_color,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=d_color, alpha=0.95, linewidth=0.8),
            )
        else:
            ax_4b.annotate(
                f"Δ = {d_val:+.2f} pp",
                xy=(x_post[i], 74.5),
                ha="center",
                va="center",
                fontsize=8.8,
                fontweight="bold",
                color=d_color,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=d_color, alpha=0.95, linewidth=0.8),
            )

    # -------------------------------------------------------------
    # Panel 3: Bottom-Left: Sample-Level Agreement Rate Q(A) == Q(B)
    # -------------------------------------------------------------
    ax_lvl = fig.add_subplot(gs[1, 0])
    lvl_colors = ["#1b9e77", "#7570b3", "#7570b3"]
    rects_lvl = ax_lvl.bar(
        x,
        level_agreements,
        width=0.45,
        color=lvl_colors,
        edgecolor="black",
        linewidth=0.8,
    )
    ax_lvl.set_ylim(0, 100)
    ax_lvl.set_ylabel("Agreement Rate (%)", fontsize=11, fontweight="bold")
    ax_lvl.set_title(
        "(c) Quantization-Level Agreement\n"
        f"Sample-Level Agreement: Q(Channel A) == Q(Channel B) (N={sample_counts[0]} samples)",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax_lvl.set_xticks(x)
    ax_lvl.set_xticklabels(display_labels, fontsize=10)
    ax_lvl.grid(True, linestyle="--", alpha=0.4, axis="y")

    for rect in rects_lvl:
        h = rect.get_height()
        ax_lvl.annotate(
            f"{h:.2f}%",
            xy=(rect.get_x() + rect.get_width() / 2.0, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax_lvl.text(
        0.5,
        0.86,
        "Percentage of paired samples assigned the same quantization level before encoding.\n"
        "This metric is distinct from bit-level KAR.",
        transform=ax_lvl.transAxes,
        ha="center",
        va="center",
        fontsize=9.2,
        style="italic",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#eef5f2", edgecolor="#80cbc4", linewidth=1.0),
    )

    # -------------------------------------------------------------
    # Panel 4: Bottom-Right: Inner GridSpec with Summary Table & Notes
    # -------------------------------------------------------------
    sub_gs = gs[1, 1].subgridspec(2, 1, height_ratios=[0.85, 1.15], hspace=0.08)

    # Top Sub-panel: Compact Table
    ax_tbl = fig.add_subplot(sub_gs[0])
    ax_tbl.axis("off")

    table_data = []
    for i, p_canonical in enumerate(display_pairs):
        table_data.append([
            p_canonical,
            f"{level_agreements[i]:.2f}%",
            f"{kar_2b_before[i]:.2f}%",
            f"{kar_2b_after[i]:.2f}%",
            f"{kar_2b_delta[i]:+.2f} pp",
            f"{kar_4b_before[i]:.2f}%",
            f"{kar_4b_after[i]:.2f}%",
            f"{kar_4b_delta[i]:+.2f} pp",
        ])

    col_labels = [
        "Channel Pair",
        "Level Agr.",
        "2b Pre",
        "2b Post",
        "Δ 2b",
        "4b Pre",
        "4b Post",
        "Δ 4b",
    ]
    col_widths = [0.26, 0.11, 0.10, 0.10, 0.11, 0.10, 0.10, 0.12]

    tbl = ax_tbl.table(
        cellText=table_data,
        colLabels=col_labels,
        colWidths=col_widths,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.2)
    tbl.scale(1.0, 1.6)

    for (r_idx, c_idx), cell in tbl.get_celld().items():
        if r_idx == 0:
            cell.set_facecolor("#2b5c8f")
            cell.set_text_props(color="white", weight="bold")
        else:
            cell.set_facecolor("#f8f9fa" if r_idx % 2 == 1 else "white")
            if c_idx in (4, 7):
                cell.set_text_props(weight="bold")

    ax_tbl.set_title(
        "(d) Quantitative Summary: Before vs After PRBS Expansion (Signed Differences in pp)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )

    # Bottom Sub-panel: Notes Box
    ax_notes = fig.add_subplot(sub_gs[1])
    ax_notes.axis("off")

    notes_text = (
        "Methodological Notes & Scientific Constraints:\n"
        "• Dummy data: software validation only; empirical channel probing is postponed.\n"
        "• Deterministic PRBS expansion does not add source entropy:\n"
        "  Generated bits derive deterministically from the 3 quantization codewords.\n"
        "  Expansion increases bitstream volume, not underlying physical randomness.\n"
        "• Zero-seed '00' behavior:\n"
        "  Seed '00' remains unmodified and generates '000' with actual period 1.\n"
        "  Zero state is preserved (never remapped, discarded, or reseeded).\n"
        "• Security interpretation:\n"
        "  Post-expansion KAR depends on quantization-level matches and pairwise Hamming\n"
        "  distances between expanded codewords. Lower eavesdropper KAR does not establish\n"
        "  cryptographic security."
    )

    ax_notes.text(
        0.01,
        0.95,
        notes_text,
        fontsize=8.8,
        va="top",
        ha="left",
        family="sans-serif",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#f4f6f9", edgecolor="#b0bec5", linewidth=1.1),
    )

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path


def plot_reconciliation_figure(
    reconcile_result: Any,
    prefix_path: str | Path,
) -> tuple[Path, Path]:
    """Generate clear 2x2 figure evaluating BCH reconciliation and candidate-key extraction.

    Panels:
        (a) quant_2bit: Pre-BCH vs Post-BCH KAR across Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob.
        (b) prbs_2bit: Pre-BCH vs Post-BCH KAR across Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob.
        (c) Exact Block Recovery Rates for both paths across all evaluation pairs.
        (d) Compact Quantitative Summary (failures, miscorrections, exact recovery) & Security Notice.

    All titles, annotations, and parameters are read dynamically from global configuration and actual results.

    Args:
        reconcile_result: MultiPathReconciliationResult instance.
        prefix_path: Base filepath prefix.

    Returns:
        tuple[Path, Path]: (png_path, pdf_path) of saved 300-dpi PNG and vector PDF figures.
    """
    prefix = Path(prefix_path)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if str(prefix).endswith(".png") or str(prefix).endswith(".pdf"):
        base_stem = prefix.stem
    else:
        base_stem = prefix.name
    # Append suffix if bare stem without suffix
    if not base_stem.endswith("_reconciliation") and not base_stem.endswith("_shared_bch"):
        base_stem = f"{base_stem}_reconciliation"
    png_path = prefix.with_name(f"{base_stem}.png")
    pdf_path = prefix.with_name(f"{base_stem}.pdf")

    # Read actual dynamic parameters from global configuration and results
    cfg = reconcile_result.config
    n_val = cfg.n
    k_val = cfg.k
    t_val = cfg.t
    d_val = cfg.designed_distance
    interleave_val = cfg.interleaving

    q_res = reconcile_result.path_results["quant_2bit"]
    p_res = reconcile_result.path_results["prbs_2bit"]
    q_ab = q_res["Alice–Bob"]
    p_ab = p_res["Alice–Bob"]

    q_blocks = q_ab.num_blocks
    q_pad = q_ab.padding_count
    blk_str_q = f"{q_blocks} Block" if q_blocks == 1 else f"{q_blocks} Blocks"

    p_blocks = p_ab.num_blocks
    p_pad = p_ab.padding_count
    blk_str_p = f"{p_blocks} Block" if p_blocks == 1 else f"{p_blocks} Blocks"

    fig = plt.figure(figsize=(15.5, 12.0))
    gs = fig.add_gridspec(2, 2, hspace=0.36, wspace=0.26, left=0.06, right=0.96, top=0.88, bottom=0.06)

    fig.suptitle(
        f"BCH({n_val}, {k_val}, {t_val}) Information Reconciliation & KAR Comparison\n"
        f"[Interleaving {interleave_val} | Designed d={d_val} | Configured t={t_val} | Codeword Helper Data H = A ⊕ C | Synthetic Software Validation]",
        fontsize=13,
        fontweight="bold",
        y=0.965,
    )

    pair_names = ["Alice–Bob", "Alice–Eve1-Alice", "Bob–Eve1-Bob"]
    pair_labels = [
        "Alice–Bob\n(Legitimate)",
        "Alice–Eve1-Alice\n(Eavesdropper)",
        "Bob–Eve1-Bob\n(Eavesdropper)",
    ]

    # Consistent color palette
    c_pre = "#4575b4"       # Steel blue for pre-reconciliation KAR
    c_legit = "#1b7837"     # Forest green for legitimate post-KAR / success
    c_eve1 = "#d73027"      # Crimson red for Eve1-Alice
    c_eve2 = "#e66101"      # Amber orange for Eve1-Bob
    c_bar_post = [c_legit, c_eve1, c_eve2]

    # =========================================================================
    # Panel (a): quant_2bit: Pre-BCH vs Post-BCH KAR across all 3 pairs
    # =========================================================================
    ax_a = fig.add_subplot(gs[0, 0])
    x = np.arange(len(pair_names))
    b_width = 0.35

    q_pre = [q_res[p].pre_reconcile_kar for p in pair_names]
    q_post = [q_res[p].post_reconcile_kar for p in pair_names]
    q_deltas = [post - pre for pre, post in zip(q_pre, q_post)]

    r_q_pre = ax_a.bar(x - b_width / 2.0, q_pre, width=b_width, color=c_pre, edgecolor="black", linewidth=0.8, label="Pre-BCH KAR")
    r_q_post = ax_a.bar(x + b_width / 2.0, q_post, width=b_width, color=c_bar_post, edgecolor="black", linewidth=0.8, label="Post-BCH KAR")

    ax_a.set_ylim(0, 118)
    ax_a.set_ylabel("Key Agreement Rate (%)", fontsize=10.5, fontweight="bold")
    ax_a.set_title(
        f"(a) quant_2bit: Pre-BCH vs Post-BCH KAR\n(n={n_val}, k={k_val}, d={d_val}, t={t_val} | Interleaving {interleave_val} | {blk_str_q}, {q_pad} Pad Bits Excluded)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )
    ax_a.set_xticks(x)
    ax_a.set_xticklabels(pair_labels, fontsize=9.2)
    ax_a.grid(True, linestyle="--", alpha=0.4, axis="y")

    # Custom legend for panel a
    leg_handles_a = [
        plt.Rectangle((0, 0), 1, 1, facecolor=c_pre, edgecolor="black", linewidth=0.8),
        plt.Rectangle((0, 0), 1, 1, facecolor=c_legit, edgecolor="black", linewidth=0.8),
        plt.Rectangle((0, 0), 1, 1, facecolor=c_eve1, edgecolor="black", linewidth=0.8),
        plt.Rectangle((0, 0), 1, 1, facecolor=c_eve2, edgecolor="black", linewidth=0.8),
    ]
    leg_labels_a = ["Pre-BCH KAR", "Post-BCH (Alice–Bob)", "Post-BCH (Eve1-Alice)", "Post-BCH (Eve1-Bob)"]
    ax_a.legend(leg_handles_a, leg_labels_a, loc="upper right", framealpha=0.92, fontsize=8.2)

    for i, rect in enumerate(r_q_pre):
        h = rect.get_height()
        ax_a.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=c_pre)
    for i, rect in enumerate(r_q_post):
        h = rect.get_height()
        col = c_bar_post[i]
        ax_a.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=col)
        d_val_i = q_deltas[i]
        d_txt = f"Δ={d_val_i:+.1f}pp"
        badge_y = h + 9.5 if h < 95 else 111.0
        ax_a.annotate(d_txt, xy=(rect.get_x() + rect.get_width() / 2.0, badge_y), ha="center", va="center", fontsize=8.0, fontweight="bold", color=col, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=col, alpha=0.92, linewidth=0.7))

    # =========================================================================
    # Panel (b): prbs_2bit: Pre-BCH vs Post-BCH KAR across all 3 pairs
    # =========================================================================
    ax_b = fig.add_subplot(gs[0, 1])

    p_pre = [p_res[p].pre_reconcile_kar for p in pair_names]
    p_post = [p_res[p].post_reconcile_kar for p in pair_names]
    p_deltas = [post - pre for pre, post in zip(p_pre, p_post)]

    r_p_pre = ax_b.bar(x - b_width / 2.0, p_pre, width=b_width, color=c_pre, edgecolor="black", linewidth=0.8, label="Pre-BCH KAR")
    r_p_post = ax_b.bar(x + b_width / 2.0, p_post, width=b_width, color=c_bar_post, edgecolor="black", linewidth=0.8, label="Post-BCH KAR")

    ax_b.set_ylim(0, 118)
    ax_b.set_ylabel("Key Agreement Rate (%)", fontsize=10.5, fontweight="bold")
    ax_b.set_title(
        f"(b) prbs_2bit: Pre-BCH vs Post-BCH KAR\n(n={n_val}, k={k_val}, d={d_val}, t={t_val} | Interleaving {interleave_val} | {blk_str_p}, {p_pad} Pad Bits Excluded)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )
    ax_b.set_xticks(x)
    ax_b.set_xticklabels(pair_labels, fontsize=9.2)
    ax_b.grid(True, linestyle="--", alpha=0.4, axis="y")

    ax_b.legend(leg_handles_a, leg_labels_a, loc="upper right", framealpha=0.92, fontsize=8.2)

    for i, rect in enumerate(r_p_pre):
        h = rect.get_height()
        ax_b.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=c_pre)
    for i, rect in enumerate(r_p_post):
        h = rect.get_height()
        col = c_bar_post[i]
        ax_b.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=col)
        d_val_i = p_deltas[i]
        d_txt = f"Δ={d_val_i:+.1f}pp"
        badge_y = h + 9.5 if h < 95 else 111.0
        ax_b.annotate(d_txt, xy=(rect.get_x() + rect.get_width() / 2.0, badge_y), ha="center", va="center", fontsize=8.0, fontweight="bold", color=col, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=col, alpha=0.92, linewidth=0.7))

    # =========================================================================
    # Panel (c): Exact Block Recovery Rates for Both Paths
    # =========================================================================
    ax_c = fig.add_subplot(gs[1, 0])
    x_paths = np.arange(2)
    path_names = ["quant_2bit", "prbs_2bit"]
    path_labels_c = [f"quant_2bit\n({blk_str_q})", f"prbs_2bit\n({blk_str_p})"]
    w3 = 0.24

    ab_succ_pct = [reconcile_result.path_results[p]["Alice–Bob"].block_success_rate for p in path_names]
    ea_succ_pct = [reconcile_result.path_results[p]["Alice–Eve1-Alice"].block_success_rate for p in path_names]
    eb_succ_pct = [reconcile_result.path_results[p]["Bob–Eve1-Bob"].block_success_rate for p in path_names]

    r_c_ab = ax_c.bar(x_paths - w3, ab_succ_pct, width=w3, color=c_legit, edgecolor="black", linewidth=0.8, label="Alice–Bob (Legitimate)")
    r_c_ea = ax_c.bar(x_paths, ea_succ_pct, width=w3, color=c_eve1, edgecolor="black", linewidth=0.8, label="Alice–Eve1-Alice (Eve)")
    r_c_eb = ax_c.bar(x_paths + w3, eb_succ_pct, width=w3, color=c_eve2, edgecolor="black", linewidth=0.8, label="Bob–Eve1-Bob (Eve)")

    ax_c.set_ylim(0, 115)
    ax_c.set_ylabel("Block Recovery Rate (%)", fontsize=10.5, fontweight="bold")
    ax_c.set_title(
        f"(c) Exact Block Recovery Rates for Both Paths\n(Decoder Success Rate per Block | Error Capability t={t_val})",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )
    ax_c.set_xticks(x_paths)
    ax_c.set_xticklabels(path_labels_c, fontsize=9.5)
    ax_c.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax_c.legend(loc="upper right", framealpha=0.92, fontsize=8.5)

    for i in range(2):
        p = path_names[i]
        res_ab = reconcile_result.path_results[p]["Alice–Bob"]
        ax_c.annotate(
            f"{ab_succ_pct[i]:.1f}%\n({res_ab.success_blocks}/{res_ab.num_blocks})",
            xy=(x_paths[i] - w3, ab_succ_pct[i] + 2),
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color=c_legit,
        )
        res_ea = reconcile_result.path_results[p]["Alice–Eve1-Alice"]
        ax_c.annotate(
            f"{ea_succ_pct[i]:.1f}%\n({res_ea.success_blocks}/{res_ea.num_blocks})",
            xy=(x_paths[i], ea_succ_pct[i] + 2),
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color=c_eve1,
        )
        res_eb = reconcile_result.path_results[p]["Bob–Eve1-Bob"]
        ax_c.annotate(
            f"{eb_succ_pct[i]:.1f}%\n({res_eb.success_blocks}/{res_eb.num_blocks})",
            xy=(x_paths[i] + w3, eb_succ_pct[i] + 2),
            ha="center",
            va="bottom",
            fontsize=8.0,
            fontweight="bold",
            color=c_eve2,
        )

    # =========================================================================
    # Panel (d): Compact Summary Table + Notes
    # =========================================================================
    sub_gs_d = gs[1, 1].subgridspec(2, 1, height_ratios=[0.45, 0.55], hspace=0.18)

    ax_d_tbl = fig.add_subplot(sub_gs_d[0])
    ax_d_tbl.axis("off")

    table_data = [
        ["Path", "Pair", "Pre-KAR", "Post-KAR", "Δ(pp)", "Fail", "Mis", "Exact Recovery"],
    ]
    for p in path_names:
        for pair in pair_names:
            r = reconcile_result.path_results[p][pair]
            p_short = "quant_2b" if p == "quant_2bit" else "prbs_2b"
            pair_short = pair.replace("–", "-").replace("Alice", "A").replace("Bob", "B").replace("Eve1", "E1")
            d_pp = r.post_reconcile_kar - r.pre_reconcile_kar
            table_data.append([
                p_short,
                pair_short,
                f"{r.pre_reconcile_kar:.1f}%",
                f"{r.post_reconcile_kar:.1f}%",
                f"{d_pp:+.1f}",
                f"{r.detected_failure_blocks}",
                f"{r.miscorrected_blocks}",
                "EXACT" if r.exact_recovery else "FAIL",
            ])

    col_widths = [0.12, 0.16, 0.12, 0.12, 0.10, 0.09, 0.09, 0.20]
    tbl_d = ax_d_tbl.table(
        cellText=table_data,
        cellLoc="center",
        loc="center",
        colWidths=col_widths,
    )
    tbl_d.auto_set_font_size(False)
    tbl_d.set_fontsize(8.0)
    tbl_d.scale(1.0, 1.20)

    for (row_i, col_i), cell in tbl_d.get_celld().items():
        if row_i == 0:
            cell.set_facecolor("#1F497D")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            if row_i % 2 == 1:
                cell.set_facecolor("#f7f9fb")
            if col_i == 7:
                txt = cell.get_text().get_text()
                if txt == "EXACT":
                    cell.set_text_props(color=c_legit, fontweight="bold")
                else:
                    cell.set_text_props(color=c_eve1, fontweight="bold")

    ax_d_tbl.set_title("(d) Quantitative Summary: Failures, Miscorrections & Exact Recovery", fontsize=10.2, fontweight="bold", pad=4)

    # Sub-panel 2: Security & Methodological Notes Box
    ax_d_notes = fig.add_subplot(sub_gs_d[1])
    ax_d_notes.axis("off")

    notes_text = (
        "Methodological Notes & Scientific Constraints:\n"
        f"• Global BCH Parameters: n={n_val}, k={k_val}, designed distance d={d_val}, configured t={t_val}, Interleaving: {interleave_val}.\n"
        "• Failed-Block Convention: Unchanged raw receiver bits are retained as fallback (never discarded or zeroed);\n"
        "  when decoder failure occurs, unpadded bitstream recovery is incomplete (exact_recovery = False).\n"
        "• Ordinary Eve Decoding vs Algebraic Attack: Standard Eve decoding fails (0% block recovery), but this\n"
        "  DOES NOT establish secrecy. Without interleaving, known padding reveals the final PRBS block;\n"
        "  the reported full-stream attack additionally uses per-sample PRBS parity constraints (joint GF(2) full rank 92/92),\n"
        "  allowing an algebraic attacker to recover Alice's full bitstream with 100% accuracy without channel observation.\n"
        "• Disclaimer: Dummy-data comparison; global configuration has reported public-information leakage.\n"
        "  KAR does not establish secrecy."
    )

    ax_d_notes.text(
        0.00,
        0.98,
        notes_text,
        fontsize=7.8,
        va="top",
        ha="left",
        family="sans-serif",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff9e6", edgecolor="#d4b106", linewidth=1.1),
    )

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path


# Backward compatibility alias
plot_shared_bch_figure = plot_reconciliation_figure


def plot_privacy_amplification_figure(
    pa_result: Any,
    prefix_path: str | Path,
) -> tuple[Path, Path]:
    """Generate 2x2 figure evaluating Privacy Amplification (Pre-PA vs Post-PA KAR).

    Panels:
        (a) quant_2bit: Pre-PA vs Post-PA KAR across Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob.
        (b) prbs_2bit: Pre-PA vs Post-PA KAR across Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob.
        (c) Final 256-bit Key Agreement & Exact Match Status across both paths.
        (d) Quantitative Summary Table & Scientific Disclaimer Box.

    Args:
        pa_result: MultiPathPrivacyAmplificationResult instance.
        prefix_path: Filepath prefix for saving PNG (300 dpi) and PDF figures.

    Returns:
        tuple[Path, Path]: (png_path, pdf_path) of saved figures.
    """
    prefix = Path(prefix_path)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if str(prefix).endswith(".png") or str(prefix).endswith(".pdf"):
        base_stem = prefix.stem
    else:
        base_stem = prefix.name

    if not base_stem.endswith("_pa_comparison") and not base_stem.endswith("_privacy_amplification"):
        base_stem = f"{base_stem}_pa_comparison"

    png_path = prefix.with_name(f"{base_stem}.png")
    pdf_path = prefix.with_name(f"{base_stem}.pdf")

    pair_names = ["Alice–Bob", "Alice–Eve1-Alice", "Bob–Eve1-Bob"]
    pair_labels = [
        "Alice–Bob\n(Legitimate)",
        "Alice–Eve1-Alice\n(Eavesdropper)",
        "Bob–Eve1-Bob\n(Eavesdropper)",
    ]

    # Color palette matching pipeline aesthetic
    c_pre = "#4575b4"       # Steel blue for pre-PA KAR
    c_legit = "#1b7837"     # Forest green for legitimate post-PA KAR / exact match
    c_eve1 = "#d73027"      # Crimson red for Eve1-Alice
    c_eve2 = "#e66101"      # Amber orange for Eve1-Bob
    c_bar_post = [c_legit, c_eve1, c_eve2]

    q_res = pa_result.pair_results["quant_2bit"]
    p_res = pa_result.pair_results["prbs_2bit"]

    fig = plt.figure(figsize=(15.5, 12.0))
    gs = fig.add_gridspec(2, 2, hspace=0.36, wspace=0.26, left=0.06, right=0.96, top=0.88, bottom=0.06)

    fig.suptitle(
        "Privacy Amplification (SHA-256) Key Agreement Rate (KAR) Comparison\n"
        "[PA.pdf Section 3.2.6 (Eqs. 3.37–3.53) & Eq. 3.64 | 256-bit Final Keys | Software Validation on Synthetic Data]",
        fontsize=13,
        fontweight="bold",
        y=0.965,
    )

    x = np.arange(len(pair_names))
    b_width = 0.35

    # =========================================================================
    # Panel (a): quant_2bit: Pre-PA vs Post-PA KAR
    # =========================================================================
    ax_a = fig.add_subplot(gs[0, 0])
    q_pre = [q_res[p].pre_pa_kar for p in pair_names]
    q_post = [q_res[p].post_pa_kar for p in pair_names]
    q_deltas = [q_res[p].kar_delta for p in pair_names]

    r_q_pre = ax_a.bar(x - b_width / 2.0, q_pre, width=b_width, color=c_pre, edgecolor="black", linewidth=0.8, label="Pre-PA KAR (Reconciled)")
    r_q_post = ax_a.bar(x + b_width / 2.0, q_post, width=b_width, color=c_bar_post, edgecolor="black", linewidth=0.8, label="Post-PA KAR (256-bit Key)")

    ax_a.set_ylim(0, 118)
    ax_a.set_ylabel("Key Agreement Rate (%)", fontsize=10.5, fontweight="bold")
    ax_a.set_title(
        "(a) quant_2bit Path: Pre-PA vs Post-PA KAR\n(Input: 1,000 bits | Output: 256-bit SHA-256 Key)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )
    ax_a.set_xticks(x)
    ax_a.set_xticklabels(pair_labels, fontsize=9.2)
    ax_a.grid(True, linestyle="--", alpha=0.4, axis="y")

    leg_handles_a = [
        plt.Rectangle((0, 0), 1, 1, facecolor=c_pre, edgecolor="black", linewidth=0.8),
        plt.Rectangle((0, 0), 1, 1, facecolor=c_legit, edgecolor="black", linewidth=0.8),
        plt.Rectangle((0, 0), 1, 1, facecolor=c_eve1, edgecolor="black", linewidth=0.8),
        plt.Rectangle((0, 0), 1, 1, facecolor=c_eve2, edgecolor="black", linewidth=0.8),
    ]
    leg_labels_a = ["Pre-PA KAR", "Post-PA (Alice–Bob)", "Post-PA (Eve1-Alice)", "Post-PA (Eve1-Bob)"]
    ax_a.legend(leg_handles_a, leg_labels_a, loc="upper right", framealpha=0.92, fontsize=8.2)

    for i, rect in enumerate(r_q_pre):
        h = rect.get_height()
        ax_a.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=c_pre)
    for i, rect in enumerate(r_q_post):
        h = rect.get_height()
        col = c_bar_post[i]
        ax_a.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=col)
        d_val_i = q_deltas[i]
        d_txt = f"Δ={d_val_i:+.1f}pp"
        badge_y = h + 9.5 if h < 95 else 111.0
        ax_a.annotate(d_txt, xy=(rect.get_x() + rect.get_width() / 2.0, badge_y), ha="center", va="center", fontsize=8.0, fontweight="bold", color=col, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=col, alpha=0.92, linewidth=0.7))

    # =========================================================================
    # Panel (b): prbs_2bit: Pre-PA vs Post-PA KAR
    # =========================================================================
    ax_b = fig.add_subplot(gs[0, 1])
    p_pre = [p_res[p].pre_pa_kar for p in pair_names]
    p_post = [p_res[p].post_pa_kar for p in pair_names]
    p_deltas = [p_res[p].kar_delta for p in pair_names]

    r_p_pre = ax_b.bar(x - b_width / 2.0, p_pre, width=b_width, color=c_pre, edgecolor="black", linewidth=0.8, label="Pre-PA KAR (Reconciled)")
    r_p_post = ax_b.bar(x + b_width / 2.0, p_post, width=b_width, color=c_bar_post, edgecolor="black", linewidth=0.8, label="Post-PA KAR (256-bit Key)")

    ax_b.set_ylim(0, 118)
    ax_b.set_ylabel("Key Agreement Rate (%)", fontsize=10.5, fontweight="bold")
    ax_b.set_title(
        "(b) prbs_2bit Path: Pre-PA vs Post-PA KAR\n(Input: 1,500 bits | Output: 256-bit SHA-256 Key)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )
    ax_b.set_xticks(x)
    ax_b.set_xticklabels(pair_labels, fontsize=9.2)
    ax_b.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax_b.legend(leg_handles_a, leg_labels_a, loc="upper right", framealpha=0.92, fontsize=8.2)

    for i, rect in enumerate(r_p_pre):
        h = rect.get_height()
        ax_b.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=c_pre)
    for i, rect in enumerate(r_p_post):
        h = rect.get_height()
        col = c_bar_post[i]
        ax_b.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=col)
        d_val_i = p_deltas[i]
        d_txt = f"Δ={d_val_i:+.1f}pp"
        badge_y = h + 9.5 if h < 95 else 111.0
        ax_b.annotate(d_txt, xy=(rect.get_x() + rect.get_width() / 2.0, badge_y), ha="center", va="center", fontsize=8.0, fontweight="bold", color=col, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=col, alpha=0.92, linewidth=0.7))

    # =========================================================================
    # Panel (c): Key Agreement Rate & Exact Match Comparison Across Both Paths
    # =========================================================================
    ax_c = fig.add_subplot(gs[1, 0])
    group_labels = ["Alice–Bob\n(Legitimate)", "Alice–Eve1-Alice\n(Eavesdropper)", "Bob–Eve1-Bob\n(Eavesdropper)"]
    x_c = np.arange(len(group_labels))
    w_c = 0.35

    q_kar_vals = [q_res[p].post_pa_kar for p in pair_names]
    p_kar_vals = [p_res[p].post_pa_kar for p in pair_names]

    bars_q = ax_c.bar(x_c - w_c / 2.0, q_kar_vals, width=w_c, color="#2b83ba", edgecolor="black", linewidth=0.8, label="quant_2bit (256-bit Key)")
    bars_p = ax_c.bar(x_c + w_c / 2.0, p_kar_vals, width=w_c, color="#abdda4", edgecolor="black", linewidth=0.8, label="prbs_2bit (256-bit Key)")

    ax_c.axhline(50.0, color="#d73027", linestyle=":", linewidth=1.2, label="50% Ideal Avalanche Level (Random Guessing)")
    ax_c.set_ylim(0, 118)
    ax_c.set_ylabel("Final Key Agreement Rate (%)", fontsize=10.5, fontweight="bold")
    ax_c.set_title(
        "(c) Final Secret Key KAR & Avalanche Isolation\n(Legitimate: 100% Match | Eavesdropper: Residual Errors Induce ~50% KAR)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )
    ax_c.set_xticks(x_c)
    ax_c.set_xticklabels(group_labels, fontsize=9.2)
    ax_c.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax_c.legend(loc="upper right", framealpha=0.92, fontsize=8.2)

    for i, rect in enumerate(bars_q):
        h = rect.get_height()
        pair_key = pair_names[i]
        match_str = "MATCH" if q_res[pair_key].exact_key_match else "MISMATCH"
        ax_c.annotate(f"{h:.1f}%\n[{match_str}]", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.8, fontweight="bold", color="#1c5579")

    for i, rect in enumerate(bars_p):
        h = rect.get_height()
        pair_key = pair_names[i]
        match_str = "MATCH" if p_res[pair_key].exact_key_match else "MISMATCH"
        ax_c.annotate(f"{h:.1f}%\n[{match_str}]", xy=(rect.get_x() + rect.get_width() / 2.0, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.8, fontweight="bold", color="#27681c")

    # =========================================================================
    # Panel (d): Quantitative Summary Table & Scientific Disclaimer Box
    # =========================================================================
    sub_gs_d = gs[1, 1].subgridspec(2, 1, height_ratios=[1.3, 1.0], hspace=0.28)

    # Sub-panel 1: Summary Table
    ax_d_tbl = fig.add_subplot(sub_gs_d[0])
    ax_d_tbl.axis("off")

    table_data = [
        ["Path", "Pair", "Pre-KAR", "Post-KAR", "Δ(pp)", "Key Match"],
    ]
    for p_name in ["quant_2bit", "prbs_2bit"]:
        for pair in pair_names:
            r = pa_result.pair_results[p_name][pair]
            p_short = "quant_2b" if p_name == "quant_2bit" else "prbs_2b"
            pair_short = pair.replace("–", "-").replace("Alice", "A").replace("Bob", "B").replace("Eve1", "E1")
            table_data.append([
                p_short,
                pair_short,
                f"{r.pre_pa_kar:.2f}%",
                f"{r.post_pa_kar:.2f}%",
                f"{r.kar_delta:+.2f}",
                "EXACT MATCH" if r.exact_key_match else "NO MATCH",
            ])

    col_widths = [0.16, 0.20, 0.16, 0.16, 0.14, 0.18]
    tbl_d = ax_d_tbl.table(
        cellText=table_data,
        cellLoc="center",
        loc="center",
        colWidths=col_widths,
    )
    tbl_d.auto_set_font_size(False)
    tbl_d.set_fontsize(8.2)
    tbl_d.scale(1.0, 1.25)

    for (row_i, col_i), cell in tbl_d.get_celld().items():
        if row_i == 0:
            cell.set_facecolor("#1F497D")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            if row_i % 2 == 1:
                cell.set_facecolor("#f7f9fb")
            if col_i == 5:
                txt = cell.get_text().get_text()
                if txt == "EXACT MATCH":
                    cell.set_text_props(color=c_legit, fontweight="bold")
                else:
                    cell.set_text_props(color=c_eve1, fontweight="bold")

    ax_d_tbl.set_title("(d) Quantitative Summary: Pre-PA vs Post-PA KAR (PA.pdf Eq. 3.64)", fontsize=10.2, fontweight="bold", pad=4)

    # Sub-panel 2: Scientific Disclaimer Box
    ax_d_notes = fig.add_subplot(sub_gs_d[1])
    ax_d_notes.axis("off")

    notes_text = (
        "Methodological Notes & Scientific Disclaimer:\n"
        "• SHA-256 Bit-Level Privacy Amplification (PA.pdf Section 3.2.6, Eqs. 3.37–3.53):\n"
        "  Bit-level padding M' = M || 1 || 0^p || [L]_64 directly accommodates arbitrary bit lengths\n"
        "  (L=1000 for quant_2bit, L=1500 for prbs_2bit) yielding 256-bit final keys.\n"
        "• Avalanche Effect & Channel Isolation: For Alice–Bob, error-free reconciled bitstreams\n"
        "  yield identical keys (100% Post-PA KAR). For Eve pairs, residual errors trigger the\n"
        "  cryptographic avalanche effect, driving key agreement to ~50% (random-guess equivalence).\n"
        "• Scientific Secrecy Disclaimer: Synthetic software validation only; 256-bit SHA-256 output\n"
        "  does NOT imply 256 bits of physical entropy when upstream PRBS expansion is deterministic\n"
        "  and public BCH helper data leaks parity relations. Physical channel probing is postponed."
    )

    ax_d_notes.text(
        0.00,
        0.98,
        notes_text,
        fontsize=7.8,
        va="top",
        ha="left",
        family="sans-serif",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff9e6", edgecolor="#d4b106", linewidth=1.1),
    )

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path

