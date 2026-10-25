"""Plotting module for RSSI correlation analysis.

Generates a combined figure containing:
1. Top horizontal bar chart of Pearson correlation coefficients with [-1, 1] fixed axis.
2. Bottom 3 scatter panels with coordinate-aggregated bubble markers proportional to observation counts.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

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
