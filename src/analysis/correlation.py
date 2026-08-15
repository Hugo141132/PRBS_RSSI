"""
correlation.py

Reusable module for Pearson correlation analysis across reciprocal and eavesdropper
RSSI channels using scipy.stats.pearsonr.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

# Ensure project root is in sys.path when executed directly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data_io.loader import load_sheet
from src.analysis.visualization import generate_d01_figures


def compute_pearson_correlation(
    x: Union[np.ndarray, pd.Series, List[Union[int, float]]],
    y: Union[np.ndarray, pd.Series, List[Union[int, float]]],
) -> Dict[str, Union[float, int]]:
    """
    Compute Pearson correlation coefficient r and valid paired sample count n.

    Args:
        x: First numeric array or Series.
        y: Second numeric array or Series.

    Returns:
        Dict containing:
            - 'r': Pearson correlation coefficient (float)
            - 'n': Number of valid paired observations (int)
    """
    # Convert to pandas Series for pairwise valid filtering
    s_x = pd.to_numeric(pd.Series(x), errors="coerce")
    s_y = pd.to_numeric(pd.Series(y), errors="coerce")

    # Filter strictly finite and non-null paired observations
    valid_mask = s_x.notna() & s_y.notna() & np.isfinite(s_x) & np.isfinite(s_y)
    clean_x = s_x[valid_mask].to_numpy(dtype=np.float64)
    clean_y = s_y[valid_mask].to_numpy(dtype=np.float64)

    n_samples = len(clean_x)

    if n_samples < 2:
        raise ValueError(f"Insufficient paired observations for correlation: n={n_samples} (minimum required: 2)")

    # Check for zero variance
    std_x = np.std(clean_x, ddof=1)
    std_y = np.std(clean_y, ddof=1)

    if std_x == 0.0 or std_y == 0.0:
        raise ValueError(
            f"Zero variance detected in input data: std(x)={std_x}, std(y)={std_y}. "
            "Pearson correlation is undefined."
        )

    res = pearsonr(clean_x, clean_y)
    r_val = float(res.statistic)

    return {
        "r": r_val,
        "n": n_samples,
    }


def analyze_channel_correlations(
    df: pd.DataFrame,
    pairs: List[Tuple[str, str]],
    expected_n: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute pairwise Pearson correlations for specified column pairs in a DataFrame.

    Args:
        df: DataFrame containing the channel data.
        pairs: List of tuples (col_a, col_b) defining the pairs to analyze.
        expected_n: Expected number of valid paired observations. Raises ValueError if n != expected_n.

    Returns:
        Dict mapping pair names (e.g. 'Alice vs Bob') to their correlation metrics (channel_1, channel_2, r, n).
    """
    results: Dict[str, Any] = {}

    for col_a, col_b in pairs:
        pair_key = f"{col_a} vs {col_b}"
        if col_a not in df.columns:
            raise KeyError(f"Column '{col_a}' not found in DataFrame columns: {list(df.columns)}")
        if col_b not in df.columns:
            raise KeyError(f"Column '{col_b}' not found in DataFrame columns: {list(df.columns)}")

        metrics = compute_pearson_correlation(df[col_a], df[col_b])

        if expected_n is not None and metrics["n"] != expected_n:
            raise ValueError(
                f"Sample count mismatch for pair '{pair_key}': got n={metrics['n']}, expected n={expected_n}"
            )

        results[pair_key] = {
            "channel_1": col_a,
            "channel_2": col_b,
            "r": metrics["r"],
            "n": metrics["n"],
        }

    return results


def run_d01_dummy_analysis(
    input_file: Optional[str] = None,
    sheet_name: str = "Sheet1",
    output_json_path: Optional[str] = None,
    figures_dir: Optional[str] = None,
    expected_n: int = 500,
) -> Dict[str, Any]:
    """
    Execute milestone D01 Pearson correlation analysis on the dummy RSSI dataset.

    Evaluates:
        - Alice vs Bob (Legitimate reciprocal channel)
        - Alice vs Eve1-Alice (Eavesdropper channel)
        - Bob vs Eve1-Bob (Eavesdropper channel)

    Restricts reading strictly to the four approved raw RSSI channels on Sheet1.
    Generates publication-quality figures without modifying raw data.
    """
    if input_file is None:
        input_file = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")

    if output_json_path is None:
        output_json_path = os.path.join(project_root, "results", "dummy", "d01_pearson_correlation.json")

    if figures_dir is None:
        figures_dir = os.path.join(project_root, "results", "dummy", "figures")

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input dataset not found: {input_file}")

    # Target raw RSSI measurement channels only
    target_channels = ["Alice", "Bob", "Eve1-Alice", "Eve1-Bob"]

    # Load Sheet1 with column restriction (usecols)
    # Excluded helper/precomputed columns are never read into memory
    df = load_sheet(input_file, sheet_name=sheet_name, usecols=target_channels)

    # Enforce strictly that only the approved raw columns are present
    if set(df.columns) != set(target_channels):
        raise ValueError(
            f"Unexpected columns loaded! Expected strictly {target_channels}, got {list(df.columns)}"
        )

    # Define the 3 required evaluation pairs
    target_pairs = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    # Compute correlations
    pair_results = analyze_channel_correlations(df, target_pairs, expected_n=expected_n)

    # Generate reproducible figures using the raw columns only
    saved_figures = generate_d01_figures(df, pair_results, figures_dir)

    summary_payload = {
        "milestone": "D01",
        "description": "Dummy RSSI Pearson Correlation Analysis",
        "dataset": {
            "file_path": os.path.relpath(input_file, project_root).replace("\\", "/"),
            "sheet_name": sheet_name,
        },
        "target_channels": target_channels,
        "expected_n_per_pair": expected_n,
        "correlation_results": pair_results,
        "figures": {
            k: os.path.relpath(v, project_root).replace("\\", "/")
            for k, v in saved_figures.items()
        },
    }

    # Ensure output directory exists and write JSON
    out_dir = os.path.dirname(output_json_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    return summary_payload


if __name__ == "__main__":
    import pprint
    print("=" * 60)
    print("Executing D01 Pearson Correlation Analysis on Sheet1...")
    print("=" * 60)
    res = run_d01_dummy_analysis()
    pprint.pprint(res)
    print("\nD01 Analysis completed successfully.")
