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

    # Fixed correlation scale from -1.0 to +1.0
    ax.set_ylim(-1.0, 1.0)
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

    fig, ax = plt.subplots(figsize=(12, 5))

    # Plot raw
    ax.plot(df.index, df[channel_name], color="gray", alpha=0.5, label="Raw RSSI", marker="o", markersize=3, linestyle="-")

    # Plot filtered
    filtered_col = f"{channel_name}_Filtered"
    ax.plot(df.index, df[filtered_col], color="#d62728", linewidth=2, label="AKF Filtered", marker="x", markersize=3)

    ax.set_title(f"Adaptive Kalman Filter (AKF) Performance: {channel_name}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Sample Index ($k$)", fontsize=12)
    ax.set_ylabel("RSSI (dBm)", fontsize=12)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(loc="upper right")

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

    fig, ax = plt.subplots(figsize=(9, 5.2))
    rects1 = ax.bar(x - width / 2, raw_r, width, label="Raw RSSI", color="#7f7f7f", edgecolor="black", linewidth=0.8)
    rects2 = ax.bar(x + width / 2, filt_r, width, label="AKF Filtered", color="#d62728", edgecolor="black", linewidth=0.8)

    ax.set_ylabel("Pearson Correlation Coefficient ($r$)", fontsize=11)
    ax.set_title("Physical-Layer Channel Reciprocity: Raw vs. AKF Filtered ($n=500$)", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax.set_ylim(-1.1, 1.1)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper left")

    # Annotations
    for rect in rects1:
        height = rect.get_height()
        offset = 0.02 if height >= 0 else -0.02
        va = "bottom" if height >= 0 else "top"
        ax.text(rect.get_x() + rect.get_width() / 2.0, height + offset,
                f"{height:.4f}", ha="center", va=va, fontsize=9)
    for rect in rects2:
        height = rect.get_height()
        offset = 0.02 if height >= 0 else -0.02
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

    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True)
    axes_flat = axes.flatten()

    for idx, ch in enumerate(channels):
        ax = axes_flat[idx]
        filt_col = f"{ch}_Filtered"
        ax.plot(df.index, df[ch], color="gray", alpha=0.5, label="Raw", marker="o", markersize=2, linestyle="-")
        ax.plot(df.index, df[filt_col], color="#d62728", linewidth=1.5, label="AKF Filtered", marker="x", markersize=2)
        ax.set_title(f"Channel: {ch}", fontsize=11, fontweight="bold")
        ax.set_ylabel("RSSI (dBm)", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend(loc="upper right", fontsize=9)

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

    fig, axes = plt.subplots(len(pairs), 1, figsize=(12, 3.5 * len(pairs)), sharex=True)
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
        ax.legend(loc="upper right", fontsize=10)

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

    fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=True)

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
        ax_mu.set_ylim(-0.05, 1.05)
        ax_mu.grid(True, linestyle="--", alpha=0.5)
        ax_mu.legend(loc="upper right", fontsize=9)

        # Middle panel: Effective Process Noise Q_eff(k)
        ax_q = axes[1, col_idx]
        ax_q.plot(k_arr, q_eff, color="#2ca02c", linewidth=1.5, label="Effective $Q_k$")
        ax_q.set_title(f"{ch}: Fuzzy Process Noise Modulation ($Q_k$)", fontsize=11, fontweight="bold")
        ax_q.set_ylabel("$Q_k$", fontsize=10)
        ax_q.grid(True, linestyle="--", alpha=0.5)
        ax_q.legend(loc="upper right", fontsize=9)

        # Bottom panel: Online Noise Mean & Covariance
        ax_noise = axes[2, col_idx]
        ax_noise.plot(k_arr, r_mean, color="#9467bd", linewidth=1.5, label=r"Noise Mean $\hat{r}_k$ (Eq. 26)")
        ax_noise.plot(k_arr, r_cov, color="#d62728", linewidth=1.5, label=r"Noise Cov $\hat{R}_k$ (Eq. 27)")
        ax_noise.set_title(f"{ch}: Adaptive Online Noise Statistics", fontsize=11, fontweight="bold")
        ax_noise.set_ylabel("Noise Metric", fontsize=10)
        ax_noise.set_xlabel("Sample Index ($k$)", fontsize=10)
        ax_noise.grid(True, linestyle="--", alpha=0.5)
        ax_noise.legend(loc="upper right", fontsize=9)

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
