"""
test_d01_correlation.py

Verification test suite for Milestone D01 - Pearson Correlation Analysis (Pearson r and n).
"""

import json
import os
import sys
import numpy as np
import pandas as pd

# Ensure project root is on sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.correlation import (
    analyze_channel_correlations,
    compute_pearson_correlation,
    run_d01_dummy_analysis,
)
from src.data_io.loader import load_sheet

DATASET_PATH = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")
RESULTS_JSON_PATH = os.path.join(project_root, "results", "dummy", "d01_pearson_correlation.json")

APPROVED_RAW_COLUMNS = ["Alice", "Bob", "Eve1-Alice", "Eve1-Bob"]
EXCLUDED_COLUMNS = ["Unnamed: 4", "korelasi A-B", "Korelasi A-E1", "Korelasi B-E1"]


def test_raw_columns_only_loaded():
    """Verify that only the 4 approved raw columns are loaded and helper columns are strictly excluded."""
    df = load_sheet(DATASET_PATH, sheet_name="Sheet1", usecols=APPROVED_RAW_COLUMNS)
    assert list(df.columns) == APPROVED_RAW_COLUMNS, f"Loaded columns mismatch: {list(df.columns)}"
    for excluded in EXCLUDED_COLUMNS:
        assert excluded not in df.columns, f"Excluded column '{excluded}' was erroneously loaded!"


def test_independent_pearson_calculation():
    """Independently calculate Pearson r from raw RSSI columns without using helper columns."""
    df = load_sheet(DATASET_PATH, sheet_name="Sheet1", usecols=APPROVED_RAW_COLUMNS)

    # Target pairs
    pairs = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    for col_a, col_b in pairs:
        x = df[col_a].to_numpy(dtype=np.float64)
        y = df[col_b].to_numpy(dtype=np.float64)

        assert len(x) == 500, f"Expected 500 rows for {col_a}, got {len(x)}"
        assert len(y) == 500, f"Expected 500 rows for {col_b}, got {len(y)}"

        # Independent manual calculation of Pearson r directly from raw formula:
        # r = sum((x - x_mean)*(y - y_mean)) / sqrt(sum((x - x_mean)^2) * sum((y - y_mean)^2))
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sqrt(np.sum((x - x_mean) ** 2) * np.sum((y - y_mean) ** 2))
        expected_r = float(numerator / denominator)

        # Function calculation
        res = compute_pearson_correlation(x, y)

        assert res["n"] == 500
        assert -1.0 <= res["r"] <= 1.0
        assert np.isfinite(res["r"])
        assert np.isclose(res["r"], expected_r, rtol=1e-10, atol=1e-10)


def test_json_results_schema_and_values():
    """Verify output JSON results file matches required schema, values, and constraints."""
    run_d01_dummy_analysis(
        input_file=DATASET_PATH,
        sheet_name="Sheet1",
        output_json_path=RESULTS_JSON_PATH,
        expected_n=500,
    )

    assert os.path.exists(RESULTS_JSON_PATH)
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["milestone"] == "D01"
    assert data["expected_n_per_pair"] == 500

    correlations = data["correlation_results"]
    expected_pairs = ["Alice vs Bob", "Alice vs Eve1-Alice", "Bob vs Eve1-Bob"]
    for pair in expected_pairs:
        assert pair in correlations, f"Missing pair {pair} in JSON results"
        p_data = correlations[pair]
        assert p_data["n"] == 500
        assert -1.0 <= p_data["r"] <= 1.0
        assert np.isfinite(p_data["r"])
        assert "p_value" not in p_data, f"p_value should not be in JSON output for {pair}"
        assert "is_valid" not in p_data, f"is_valid should not be in JSON output for {pair}"


def test_dataset_regression_sanity_check():
    """
    Dataset-specific regression sanity check:
    Confirms relative ordering for Sheet1 (legitimate r_AB exceeds Eve cross-links r_AE1, r_BE1).
    """
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    r_ab = data["correlation_results"]["Alice vs Bob"]["r"]
    r_ae = data["correlation_results"]["Alice vs Eve1-Alice"]["r"]
    r_be = data["correlation_results"]["Bob vs Eve1-Bob"]["r"]

    # Verify channel ordering property on this dataset
    assert r_ab > r_ae, f"Expected r_ab ({r_ab}) > r_ae ({r_ae})"
    assert r_ab > r_be, f"Expected r_ab ({r_ab}) > r_be ({r_be})"


def test_figures_generated_and_non_empty():
    """Verify that all D01 visualization figures are generated, exist, and are non-empty."""
    figures_dir = os.path.join(project_root, "results", "dummy", "figures")
    scatter_fig = os.path.join(figures_dir, "d01_rssi_correlation_scatter.png")
    bar_fig = os.path.join(figures_dir, "d01_pearson_r_comparison.png")

    assert os.path.exists(scatter_fig), f"Scatter figure missing: {scatter_fig}"
    assert os.path.exists(bar_fig), f"Comparison figure missing: {bar_fig}"

    assert os.path.getsize(scatter_fig) > 1000, f"Scatter figure file is unexpectedly small: {scatter_fig}"
    assert os.path.getsize(bar_fig) > 1000, f"Comparison figure file is unexpectedly small: {bar_fig}"


if __name__ == "__main__":
    print("Running test suite...")
    test_raw_columns_only_loaded()
    print("[PASS] test_raw_columns_only_loaded")
    test_independent_pearson_calculation()
    print("[PASS] test_independent_pearson_calculation")
    test_json_results_schema_and_values()
    print("[PASS] test_json_results_schema_and_values")
    test_dataset_regression_sanity_check()
    print("[PASS] test_dataset_regression_sanity_check")
    test_figures_generated_and_non_empty()
    print("[PASS] test_figures_generated_and_non_empty")
    print("\nAll D01 verification tests passed successfully!")
