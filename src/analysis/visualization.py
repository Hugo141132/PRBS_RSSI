"""
visualization.py

Visualization module for generating publication-quality plots for Physical Layer
Secret Key Generation (SKG) analysis, including raw channel correlation baselines
and MSHKF adaptive filter and fuzzy clustering diagnostics.
"""

import os
from typing import Any, Dict, List, Optional, Tuple
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_correlation_scatter(
    df: pd.DataFrame,
    pairs: List[Tuple[str, str]],
    correlation_results: Dict[str, Any],
    output_path: str,
    suffix: str = "",
) -> str:
    """
    Generate a 3-panel scatter plot of RSSI channel pairs with Pearson r and n annotations.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, axes = plt.subplots(1, len(pairs), figsize=(15, 4.8), sharey=False)
    if len(pairs) == 1:
        axes = [axes]

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

    for idx, (col_a, col_b) in enumerate(pairs):
        ax = axes[idx]
        pair_key = f"{col_a} vs {col_b}"
        pair_data = correlation_results.get(pair_key, {})
        r_val = pair_data.get("r", pair_data.get("filtered_r", np.nan))
        n_val = pair_data.get("n", len(df))

        col_a_full = col_a + suffix
        col_b_full = col_b + suffix

        # Scatter points
        ax.scatter(
            df[col_a_full],
            df[col_b_full],
            alpha=0.35,
            s=22,
            color=colors[idx % len(colors)],
            edgecolors="none",
        )

        ax.set_title(f"{col_a} vs {col_b}", fontsize=12, fontweight="bold")
        ax.set_xlabel(f"{col_a} RSSI (dBm)", fontsize=10)
        ax.set_ylabel(f"{col_b} RSSI (dBm)", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.margins(x=0.08, y=0.18)

        # Annotation box with r and n
        textstr = f"Pearson $r = {r_val:.4f}$\n$n = {n_val}$"
        props = dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="gray", alpha=0.9)
        ax.text(
            0.05,
            0.95,
            textstr,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            bbox=props,
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_pearson_comparison(
    correlation_results: Dict[str, Any],
    output_path: str,
) -> str:
    """
    Generate a bar chart comparing Pearson r coefficients with fixed [-1.0, 1.0] correlation scale.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    labels = list(correlation_results.keys())
    r_values = [correlation_results[k]["r"] for k in labels]
    n_values = [correlation_results[k]["n"] for k in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    bar_colors = ["#2b5c8f", "#d95f02", "#7570b3"]

    bars = ax.bar(labels, r_values, color=bar_colors, width=0.45, edgecolor="black", linewidth=0.8)

    # Fixed correlation scale with headroom for text annotations
    ax.set_ylim(-1.15, 1.25)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.set_ylabel("Pearson Correlation Coefficient ($r$)", fontsize=11)
    ax.set_title("Pearson Correlation Coefficient Comparison ($n = 500$)", fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    # Annotate bars with numeric r values and n
    for bar, r_val, n_val in zip(bars, r_values, n_values):
        y_pos = bar.get_height()
        offset = 0.05 if y_pos >= 0 else -0.10
        va = "bottom" if y_pos >= 0 else "top"
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            y_pos + offset,
            f"r = {r_val:.4f}\n(n={n_val})",
            ha="center",
            va=va,
            fontsize=10,
            fontweight="bold",
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def generate_d01_figures(
    df: pd.DataFrame,
    correlation_results: Dict[str, Any],
    figures_dir: str,
) -> Dict[str, str]:
    """
    Generate all standard figures for D01 milestone and return their saved paths.
    """
    pairs = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    scatter_path = os.path.join(figures_dir, "d01_rssi_correlation_scatter.png")
    bar_path = os.path.join(figures_dir, "d01_pearson_r_comparison.png")

    saved_scatter = plot_correlation_scatter(df, pairs, correlation_results, scatter_path)
    saved_bar = plot_pearson_comparison(correlation_results, bar_path)

    return {
        "scatter_figure": saved_scatter,
        "comparison_figure": saved_bar,
    }


def plot_mshkf_channel_comparison(
    df: pd.DataFrame,
    channel_name: str,
    output_path: str,
) -> str:
    """
    Plots Raw vs AKF Filtered RSSI for a specific channel.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 5.2))

    # Plot raw
    ax.plot(df.index, df[channel_name], color="gray", alpha=0.5, label="Raw RSSI", marker="o", markersize=3, linestyle="-")

    # Plot filtered
    filtered_col = f"{channel_name}_Filtered"
    ax.plot(df.index, df[filtered_col], color="#d62728", linewidth=2, label="AKF Filtered", marker="x", markersize=3)

    ax.set_title(f"Adaptive Kalman Filter (AKF) Performance: {channel_name}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Sample Index ($k$)", fontsize=12)
    ax.set_ylabel("RSSI (dBm)", fontsize=12)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.margins(y=0.25)
    ax.legend(loc="upper right", fontsize=10, framealpha=0.92, edgecolor="gray")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_d02_correlation_comparison(
    raw_correlations: Dict[str, Any],
    filtered_correlations: Dict[str, Any],
    output_path: str,
) -> str:
    """
    Generate a grouped bar chart comparing Raw vs AKF Filtered Pearson r across all 3 channel pairs.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    labels = list(raw_correlations.keys())
    raw_r = [raw_correlations[k]["r"] for k in labels]
    filt_r = [filtered_correlations[k]["r"] if "r" in filtered_correlations[k] else filtered_correlations[k]["filtered_r"] for k in labels]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 5.5))
    rects1 = ax.bar(x - width / 2, raw_r, width, label="Raw RSSI", color="#7f7f7f", edgecolor="black", linewidth=0.8)
    rects2 = ax.bar(x + width / 2, filt_r, width, label="AKF Filtered", color="#d62728", edgecolor="black", linewidth=0.8)

    ax.set_ylabel("Pearson Correlation Coefficient ($r$)", fontsize=11)
    ax.set_title("Physical-Layer Channel Reciprocity: Raw vs. AKF Filtered ($n=500$)", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax.set_ylim(-1.15, 1.35)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.98), ncol=2, framealpha=0.92, edgecolor="gray")

    # Annotations
    for rect in rects1:
        height = rect.get_height()
        offset = 0.02 if height >= 0 else -0.04
        va = "bottom" if height >= 0 else "top"
        ax.text(rect.get_x() + rect.get_width() / 2.0, height + offset,
                f"{height:.4f}", ha="center", va=va, fontsize=9)
    for rect in rects2:
        height = rect.get_height()
        offset = 0.02 if height >= 0 else -0.04
        va = "bottom" if height >= 0 else "top"
        ax.text(rect.get_x() + rect.get_width() / 2.0, height + offset,
                f"{height:.4f}", ha="center", va=va, fontsize=9, fontweight="bold", color="#d62728")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_all_channels_mshkf(
    df: pd.DataFrame,
    channels: List[str],
    output_path: str,
) -> str:
    """
    Generate a 4-panel time series plot showing Raw vs AKF Filtered for all channels.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(14, 8.5), sharex=True)
    axes_flat = axes.flatten()

    for idx, ch in enumerate(channels):
        ax = axes_flat[idx]
        filt_col = f"{ch}_Filtered"
        ax.plot(df.index, df[ch], color="gray", alpha=0.5, label="Raw", marker="o", markersize=2, linestyle="-")
        ax.plot(df.index, df[filt_col], color="#d62728", linewidth=1.5, label="AKF Filtered", marker="x", markersize=2)
        ax.set_title(f"Channel: {ch}", fontsize=11, fontweight="bold")
        ax.set_ylabel("RSSI (dBm)", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.margins(y=0.25)
        ax.legend(loc="upper right", fontsize=9, framealpha=0.92, edgecolor="gray")

    for ax in axes[1, :]:
        ax.set_xlabel("Sample Index ($k$)", fontsize=10)

    plt.suptitle("Adaptive Kalman Filter (AKF) Preprocessing on Dummy RSSI ($n=500$)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_signal_overlay(
    df: pd.DataFrame,
    pairs: List[Tuple[str, str]],
    output_path: str,
    suffix: str = "",
) -> str:
    """
    Generate a multi-panel time series plot showing overlaid signals for specific channel pairs.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, axes = plt.subplots(len(pairs), 1, figsize=(12, 3.8 * len(pairs)), sharex=True)
    if len(pairs) == 1:
        axes = [axes]

    colors = [("#1f77b4", "#ff7f0e"), ("#1f77b4", "#2ca02c"), ("#ff7f0e", "#d62728")]

    for idx, (col_a, col_b) in enumerate(pairs):
        ax = axes[idx]
        col_a_full = col_a + suffix
        col_b_full = col_b + suffix

        c1, c2 = colors[idx % len(colors)]

        ax.plot(df.index, df[col_a_full], color=c1, linewidth=1.5, label=col_a, alpha=0.8)
        ax.plot(df.index, df[col_b_full], color=c2, linewidth=1.5, label=col_b, alpha=0.8)

        ax.set_title(f"Time-Series Overlay: {col_a} vs {col_b}", fontsize=12, fontweight="bold")
        ax.set_ylabel("RSSI (dBm)", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.margins(y=0.25)
        ax.legend(loc="upper right", fontsize=10, framealpha=0.92, edgecolor="gray")

    axes[-1].set_xlabel("Sample Index ($k$)", fontsize=11)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_fuzzy_diagnostics(
    filter_objects: Dict[str, Any],
    output_path: str,
) -> str:
    """
    Generate diagnostics plot showing:
    1. Fuzzy cluster membership distributions (Alice & Bob).
    2. Effective process noise Q_eff(k) and fading factor d_{k-1}(k).
    3. Estimated online noise covariance R_k and noise mean r_k.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, axes = plt.subplots(3, 2, figsize=(14, 10.5), sharex=True)

    target_channels = ["Alice", "Bob"]
    for col_idx, ch in enumerate(target_channels):
        filt = filter_objects[ch]
        hist = filt.history
        k_arr = [h["k"] for h in hist]
        mu_0 = [h["memberships"][0] for h in hist]
        mu_1 = [h["memberships"][1] for h in hist]
        q_eff = [h["Q_eff"] for h in hist]
        r_mean = [h["r"] for h in hist]
        r_cov = [h["R"] for h in hist]

        # Top panel: Fuzzy Memberships
        ax_mu = axes[0, col_idx]
        ax_mu.plot(k_arr, mu_0, label="Cluster 0 (Stable)", color="#1f77b4", linewidth=1.5)
        ax_mu.plot(k_arr, mu_1, label="Cluster 1 (Dynamic)", color="#ff7f0e", linewidth=1.5, linestyle="--")
        ax_mu.set_title(f"{ch}: Fuzzy Regime Memberships " + r"($\mu_{ik}$)", fontsize=11, fontweight="bold")
        ax_mu.set_ylabel("Membership Degree", fontsize=10)
        ax_mu.set_ylim(-0.05, 1.40)
        ax_mu.grid(True, linestyle="--", alpha=0.5)
        ax_mu.legend(loc="upper right", ncol=2, fontsize=8.5, framealpha=0.92, edgecolor="gray")

        # Middle panel: Effective Process Noise Q_eff(k)
        ax_q = axes[1, col_idx]
        ax_q.plot(k_arr, q_eff, color="#2ca02c", linewidth=1.5, label=r"Effective $Q_k$")
        ax_q.set_title(f"{ch}: Fuzzy Process Noise Modulation ($Q_k$)", fontsize=11, fontweight="bold")
        ax_q.set_ylabel(r"$Q_k$", fontsize=10)
        ax_q.grid(True, linestyle="--", alpha=0.5)
        ax_q.margins(y=0.28)
        ax_q.legend(loc="upper right", fontsize=8.5, framealpha=0.92, edgecolor="gray")

        # Bottom panel: Online Noise Mean & Covariance
        ax_noise = axes[2, col_idx]
        ax_noise.plot(k_arr, r_mean, color="#9467bd", linewidth=1.5, label=r"Noise Mean $\hat{r}_k$ (Eq. 26)")
        ax_noise.plot(k_arr, r_cov, color="#d62728", linewidth=1.5, label=r"Noise Cov $\hat{R}_k$ (Eq. 27)")
        ax_noise.set_title(f"{ch}: Adaptive Online Noise Statistics", fontsize=11, fontweight="bold")
        ax_noise.set_ylabel("Noise Metric", fontsize=10)
        ax_noise.set_xlabel("Sample Index ($k$)", fontsize=10)
        ax_noise.grid(True, linestyle="--", alpha=0.5)
        ax_noise.margins(y=0.28)
        ax_noise.legend(loc="upper right", fontsize=8.5, framealpha=0.92, edgecolor="gray")

    plt.suptitle("Adaptive Kalman Filter (AKF) Online Fuzzy Clustering & Adaptive Statistics Diagnostics ($n=500$)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def generate_d02_figures(
    df: pd.DataFrame,
    channels: List[str],
    raw_correlations: Dict[str, Any],
    filtered_correlations: Dict[str, Any],
    figures_dir: str,
    filter_objects: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Generate all standard figures for D02 milestone using the canonical MSHKF naming convention.
    """
    saved_paths = {}
    for ch in channels:
        out_path = os.path.join(figures_dir, f"d02_mshkf_{ch}_comparison.png")
        saved = plot_mshkf_channel_comparison(df, ch, out_path)
        saved_paths[f"{ch}_comparison"] = saved

    all_channels_path = os.path.join(figures_dir, "d02_mshkf_all_channels_overview.png")
    saved_paths["all_channels_overview"] = plot_all_channels_mshkf(df, channels, all_channels_path)

    corr_comp_path = os.path.join(figures_dir, "d02_mshkf_pearson_comparison.png")
    saved_paths["correlation_comparison"] = plot_d02_correlation_comparison(
        raw_correlations, filtered_correlations, corr_comp_path
    )

    pairs = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    scatter_path = os.path.join(figures_dir, "d02_mshkf_rssi_correlation_scatter.png")
    saved_paths["filtered_scatter"] = plot_correlation_scatter(
        df, pairs, filtered_correlations, scatter_path, suffix="_Filtered"
    )

    overlay_path = os.path.join(figures_dir, "d02_mshkf_signal_overlay_comparison.png")
    saved_paths["filtered_overlay"] = plot_signal_overlay(
        df, pairs, overlay_path, suffix="_Filtered"
    )

    if filter_objects is not None and "Alice" in filter_objects and "Bob" in filter_objects:
        fuzzy_diag_path = os.path.join(figures_dir, "d02_mshkf_fuzzy_diagnostics.png")
        saved_paths["fuzzy_diagnostics"] = plot_fuzzy_diagnostics(filter_objects, fuzzy_diag_path)

    return saved_paths


def plot_d02_2_channel_comparison(
    df: pd.DataFrame,
    channel_name: str,
    output_path: str,
    n_cal: int = 300,
) -> str:
    """
    Plots Raw and D02.2 Calibrated Filtered RSSI with calibration split marker.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 5.2))

    # Plot raw
    ax.plot(df.index, df[channel_name], color="gray", alpha=0.45, label="Raw RSSI", marker="o", markersize=2.5, linestyle="-")

    # Plot D02.2 calibrated
    d02_2_col = f"{channel_name}_Filtered"
    ax.plot(df.index, df[d02_2_col], color="#2ca02c", linewidth=2.0, label="D02.2 Calibrated", marker="x", markersize=3)

    # Vertical line indicating calibration/evaluation boundary
    ax.axvline(x=n_cal, color="#d62728", linestyle=":", linewidth=1.5, label=f"Calibration Split ($k={n_cal}$)")

    ax.set_title(f"D02.2 Calibrated AKF Performance: {channel_name} (Cal: 0–{n_cal}, Eval: {n_cal}–500)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Sample Index ($k$)", fontsize=11)
    ax.set_ylabel("RSSI (dBm)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.margins(y=0.25)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.92, edgecolor="gray")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_d02_2_pearson_comparison(
    raw_correlations: Dict[str, Any],
    d02_2_correlations: Dict[str, Any],
    output_path: str,
    d02_correlations: Optional[Dict[str, Any]] = None,
    title_suffix: str = "($n=500$)",
) -> str:
    """
    Generate a 2-way grouped bar chart comparing Raw vs D02.2 Calibrated Pearson r across channel pairs.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    labels = list(raw_correlations.keys())
    raw_r = [raw_correlations[k]["r"] for k in labels]
    d02_2_r = [d02_2_correlations[k].get("r", d02_2_correlations[k].get("filtered_r", 0.0)) for k in labels]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 5.5))
    rects1 = ax.bar(x - width / 2.0, raw_r, width, label="Raw RSSI", color="#7f7f7f", edgecolor="black", linewidth=0.8)
    rects2 = ax.bar(x + width / 2.0, d02_2_r, width, label="D02.2 Calibrated", color="#2ca02c", edgecolor="black", linewidth=0.8)

    ax.set_ylabel("Pearson Correlation Coefficient ($r$)", fontsize=11)
    ax.set_title(f"Channel Reciprocity Comparison: Raw vs. D02.2 Calibrated {title_suffix}", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax.set_ylim(-1.15, 1.35)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.98), ncol=2, framealpha=0.92, edgecolor="gray")

    # Annotations
    for rects, color, is_bold in [(rects1, "#333333", False), (rects2, "#2ca02c", True)]:
        for rect in rects:
            height = rect.get_height()
            offset = 0.02 if height >= 0 else -0.04
            va = "bottom" if height >= 0 else "top"
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                height + offset,
                f"{height:.4f}",
                ha="center",
                va=va,
                fontsize=8.5,
                fontweight="bold" if is_bold else "normal",
                color=color,
            )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def generate_d02_2_figures(
    df: pd.DataFrame,
    channels: List[str],
    raw_correlations: Dict[str, Any],
    d02_2_correlations: Dict[str, Any],
    figures_dir: str,
    filter_objects: Optional[Dict[str, Any]] = None,
    n_cal: int = 300,
    d02_correlations: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Generate all standard figures for D02.2 milestone using canonical D02.2 naming conventions.
    """
    saved_paths = {}
    for ch in channels:
        out_path = os.path.join(figures_dir, f"d02_2_mshkf_{ch}_comparison.png")
        saved = plot_d02_2_channel_comparison(df, ch, out_path, n_cal=n_cal)
        saved_paths[f"{ch}_comparison"] = saved

    all_channels_path = os.path.join(figures_dir, "d02_2_mshkf_all_channels_overview.png")
    saved_paths["all_channels_overview"] = plot_all_channels_mshkf(df, channels, all_channels_path)

    corr_comp_path = os.path.join(figures_dir, "d02_2_mshkf_pearson_comparison.png")
    saved_paths["correlation_comparison"] = plot_d02_2_pearson_comparison(
        raw_correlations, d02_2_correlations, corr_comp_path
    )

    pairs = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    scatter_path = os.path.join(figures_dir, "d02_2_mshkf_rssi_correlation_scatter.png")
    saved_paths["filtered_scatter"] = plot_correlation_scatter(
        df, pairs, d02_2_correlations, scatter_path, suffix="_Filtered"
    )

    overlay_path = os.path.join(figures_dir, "d02_2_mshkf_signal_overlay_comparison.png")
    saved_paths["filtered_overlay"] = plot_signal_overlay(
        df, pairs, overlay_path, suffix="_Filtered"
    )

    if filter_objects is not None and "Alice" in filter_objects and "Bob" in filter_objects:
        fuzzy_diag_path = os.path.join(figures_dir, "d02_2_mshkf_fuzzy_diagnostics.png")
        saved_paths["fuzzy_diagnostics"] = plot_fuzzy_diagnostics(filter_objects, fuzzy_diag_path)

    return saved_paths


def plot_d02_vs_d02_2_channel_comparison(
    df_raw: pd.DataFrame,
    d02_df: pd.DataFrame,
    d02_2_df: pd.DataFrame,
    channel_name: str,
    output_path: str,
) -> str:
    """
    Plots Full Trace Comparison for a channel: Raw RSSI vs D02 MSHKF vs D02.2 Calibrated.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, ax = plt.subplots(figsize=(13, 5.5))

    # Raw RSSI
    ax.plot(
        df_raw.index,
        df_raw[channel_name],
        color="#8c8c8c",
        alpha=0.40,
        label="Raw RSSI",
        marker="o",
        markersize=2.5,
        linestyle="-",
    )

    # D02 MSHKF Baseline
    d02_col = f"{channel_name}_Filtered"
    ax.plot(
        d02_df.index,
        d02_df[d02_col],
        color="#d62728",
        linewidth=1.8,
        label="D02 MSHKF (Baseline)",
        linestyle="--",
        marker=".",
        markersize=2,
    )

    # D02.2 Calibrated Filtered
    d02_2_col = f"{channel_name}_Filtered"
    ax.plot(
        d02_2_df.index,
        d02_2_df[d02_2_col],
        color="#2ca02c",
        linewidth=2.0,
        label="D02.2 Calibrated",
        linestyle="-",
        marker="x",
        markersize=3,
    )

    ax.set_title(
        f"Full-Trace Filtering Comparison: {channel_name} (Raw vs. D02 Baseline vs. D02.2 Calibrated, $n=500$)",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Sample Index ($k$)", fontsize=11)
    ax.set_ylabel("RSSI (dBm)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.margins(y=0.25)
    ax.legend(loc="upper right", fontsize=9.5, framealpha=0.92, edgecolor="gray", ncol=3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_d02_vs_d02_2_all_channels_overview(
    df_raw: pd.DataFrame,
    d02_df: pd.DataFrame,
    d02_2_df: pd.DataFrame,
    channels: List[str],
    output_path: str,
) -> str:
    """
    Generate a 4-panel full trace comparison plot showing Raw vs D02 vs D02.2 for all channels.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    axes_flat = axes.flatten()

    for idx, ch in enumerate(channels):
        ax = axes_flat[idx]
        filt_col = f"{ch}_Filtered"

        ax.plot(
            df_raw.index,
            df_raw[ch],
            color="#8c8c8c",
            alpha=0.40,
            label="Raw",
            marker="o",
            markersize=2,
            linestyle="-",
        )
        ax.plot(
            d02_df.index,
            d02_df[filt_col],
            color="#d62728",
            linewidth=1.6,
            label="D02 Baseline",
            linestyle="--",
            marker=".",
            markersize=2,
        )
        ax.plot(
            d02_2_df.index,
            d02_2_df[filt_col],
            color="#2ca02c",
            linewidth=1.8,
            label="D02.2 Calibrated",
            linestyle="-",
            marker="x",
            markersize=2,
        )

        ax.set_title(f"Channel: {ch}", fontsize=11, fontweight="bold")
        ax.set_ylabel("RSSI (dBm)", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.margins(y=0.25)
        ax.legend(loc="upper right", fontsize=8.5, framealpha=0.92, edgecolor="gray", ncol=3)

    for ax in axes[1, :]:
        ax.set_xlabel("Sample Index ($k$)", fontsize=10)

    plt.suptitle(
        "Full-Trace Comparison Across All Channels: Raw vs. D02 Baseline vs. D02.2 Calibrated ($n=500$)",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def plot_d02_vs_d02_2_pearson_comparison(
    raw_correlations: Dict[str, Any],
    d02_correlations: Dict[str, Any],
    d02_2_correlations: Dict[str, Any],
    output_path: str,
    title_suffix: str = "($n=500$)",
) -> str:
    """
    Generate a 3-way grouped bar chart comparing Raw vs D02 Baseline vs D02.2 Calibrated Pearson r.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    labels = list(raw_correlations.keys())
    raw_r = [raw_correlations[k]["r"] for k in labels]
    d02_r = [d02_correlations[k].get("r", d02_correlations[k].get("filtered_r", 0.0)) for k in labels]
    d02_2_r = [d02_2_correlations[k].get("r", d02_2_correlations[k].get("filtered_r", 0.0)) for k in labels]

    x = np.arange(len(labels))
    width = 0.26

    fig, ax = plt.subplots(figsize=(10, 5.8))
    rects1 = ax.bar(x - width, raw_r, width, label="Raw RSSI", color="#7f7f7f", edgecolor="black", linewidth=0.8)
    rects2 = ax.bar(x, d02_r, width, label="D02 Baseline", color="#d62728", edgecolor="black", linewidth=0.8)
    rects3 = ax.bar(x + width, d02_2_r, width, label="D02.2 Calibrated", color="#2ca02c", edgecolor="black", linewidth=0.8)

    ax.set_ylabel("Pearson Correlation Coefficient ($r$)", fontsize=11)
    ax.set_title(
        f"Full-Trace Channel Reciprocity: Raw vs. D02 Baseline vs. D02.2 Calibrated {title_suffix}",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax.set_ylim(-1.15, 1.38)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.98), ncol=3, framealpha=0.92, edgecolor="gray")

    # Annotations
    for rects, color, is_bold in [
        (rects1, "#333333", False),
        (rects2, "#d62728", True),
        (rects3, "#2ca02c", True),
    ]:
        for rect in rects:
            height = rect.get_height()
            offset = 0.02 if height >= 0 else -0.04
            va = "bottom" if height >= 0 else "top"
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                height + offset,
                f"{height:.4f}",
                ha="center",
                va=va,
                fontsize=8.0,
                fontweight="bold" if is_bold else "normal",
                color=color,
            )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(output_path)


def generate_d02_vs_d02_2_comparison_figures(
    df_raw: pd.DataFrame,
    d02_df: pd.DataFrame,
    d02_2_df: pd.DataFrame,
    channels: List[str],
    raw_correlations: Dict[str, Any],
    d02_correlations: Dict[str, Any],
    d02_2_correlations: Dict[str, Any],
    figures_dir: str,
) -> Dict[str, str]:
    """
    Generate all full-trace comparison figures between D02 and D02.2.
    """
    os.makedirs(figures_dir, exist_ok=True)
    saved_paths = {}

    for ch in channels:
        out_path = os.path.join(figures_dir, f"d02_vs_d02_2_{ch}_comparison.png")
        saved = plot_d02_vs_d02_2_channel_comparison(df_raw, d02_df, d02_2_df, ch, out_path)
        saved_paths[f"{ch}_comparison"] = saved

    all_channels_path = os.path.join(figures_dir, "d02_vs_d02_2_all_channels_overview.png")
    saved_paths["all_channels_overview"] = plot_d02_vs_d02_2_all_channels_overview(
        df_raw, d02_df, d02_2_df, channels, all_channels_path
    )

    corr_comp_path = os.path.join(figures_dir, "d02_vs_d02_2_pearson_comparison.png")
    saved_paths["correlation_comparison"] = plot_d02_vs_d02_2_pearson_comparison(
        raw_correlations, d02_correlations, d02_2_correlations, corr_comp_path
    )

    return saved_paths
