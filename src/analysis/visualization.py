"""
visualization.py

Reusable module for plotting physical-layer RSSI correlation figures and comparison charts.
"""

import os
from typing import Any, Dict, List, Tuple
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
) -> str:
    """
    Generate a 3-panel scatter plot of raw RSSI channel pairs with Pearson r and n annotations.

    Args:
        df: DataFrame containing the raw RSSI measurements.
        pairs: List of (channel_1, channel_2) tuples.
        correlation_results: Dict containing correlation metrics ('r', 'n') per pair.
        output_path: Destination file path for the figure.

    Returns:
        Absolute path to the generated figure.
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
        r_val = pair_data.get("r", np.nan)
        n_val = pair_data.get("n", len(df))

        # Raw scatter points without jitter; alpha indicates density of quantized integer points
        ax.scatter(
            df[col_a],
            df[col_b],
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

    Args:
        correlation_results: Dict containing correlation metrics per pair.
        output_path: Destination file path for the figure.

    Returns:
        Absolute path to the generated figure.
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
