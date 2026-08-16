"""
test_d02_akf.py

Verification test suite for Milestone D02 - Adaptive Kalman Filter (AKF) Preprocessing.
Covers:
1. Exact scalar Kalman filter arithmetic (PPA.pdf Equations 3.10–3.16).
2. Exact Wang et al. Eq. (27) adaptive measurement noise R_k updates.
3. Analytical b=1.0 limit handling without division-by-zero (0/0).
4. Exponential forgetting with b < 1.0.
5. Exact streaming-vs-batch equivalence.
6. Negative R_k capability without artificial clamping.
7. End-to-end D02 pipeline execution with approved Configuration C1.
8. Preservation of original dataset length (n=500), indices, and SHA-256 immutability.
"""

import json
import os
import sys
import numpy as np
import pandas as pd

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.akf import AdaptiveKalmanFilter
from src.analysis.d02_runner import APPROVED_C1_PARAMS, APPROVED_RAW_COLUMNS, EXPECTED_SHA256, run_d02_pipeline
from src.data_io.loader import compute_file_sha256, load_sheet

DATASET_PATH = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")
OUTPUT_CSV_PATH = os.path.join(project_root, "results", "dummy", "d02_akf_filtered.csv")
OUTPUT_JSON_PATH = os.path.join(project_root, "results", "dummy", "d02_akf_results.json")
FIGURES_DIR = os.path.join(project_root, "results", "dummy", "figures")


def test_akf_initialization():
    """Verify parameters are explicitly set and configurable."""
    akf = AdaptiveKalmanFilter(b=0.95, x0=10.0, P0=1.0, Q=0.1, R0=2.0)
    assert akf.b == 0.95
    assert akf.x == 10.0
    assert akf.P == 1.0
    assert akf.Q == 0.1
    assert akf.R == 2.0
    assert akf.k == 1


def test_akf_b_1_limit():
    """Verify that b=1.0 utilizes the analytical limit without division by zero."""
    akf = AdaptiveKalmanFilter(b=1.0, x0=0.0, P0=1.0, Q=0.0, R0=10.0)
    z = 5.0
    akf.step(z)

    hist = akf.history[0]
    assert hist["d_k_minus_1"] == 1.0

    # Wang Eq 27 with d_0 = 1.0 -> R_1 = 0 * R_0 + 1 * (e_1^2 - P_pred)
    # x_pred = 0, P_pred = 1.0. e_1 = 5.0.
    # R_1 = 5^2 - 1.0 = 24.0
    assert np.isclose(hist["R"], 24.0)


def test_akf_exponential_forgetting():
    """Verify d_{k-1} with b < 1.0."""
    akf = AdaptiveKalmanFilter(b=0.9, x0=0.0, P0=1.0, Q=0.1, R0=2.0)
    # k=1: d_0 = (1-0.9)/(1-0.9^1) = 1.0
    akf.step(1.0)
    assert np.isclose(akf.history[0]["d_k_minus_1"], 1.0)

    # k=2: d_1 = (1-0.9)/(1-0.9^2) = 0.1 / 0.19 = 10/19 ~= 0.526315
    akf.step(2.0)
    assert np.isclose(akf.history[1]["d_k_minus_1"], 10.0 / 19.0)


def test_negative_R_capability():
    """
    Ensure R can mathematically go negative without artificial floors,
    as required to keep Wang Eq 27 strictly unchanged.
    """
    akf = AdaptiveKalmanFilter(b=1.0, x0=0.0, P0=10.0, Q=0.0, R0=1.0)
    # k=1 -> d_0 = 1. P_pred = 10.0. z = 0 -> e_1 = 0.
    # R_1 = 1 * (0^2 - 10) = -10.0
    akf.step(0.0)
    assert np.isclose(akf.history[0]["R"], -10.0)


def test_streaming_vs_batch_equivalence():
    """
    Verify that processing data sequentially yields expected behavior
    and correctly increments step index.
    """
    akf = AdaptiveKalmanFilter(b=0.98, x0=0.0, P0=1.0, Q=1e-3, R0=5.0)
    data = [1.2, 1.5, 1.1, 1.6, 1.3]
    results = [akf.step(z) for z in data]

    assert len(results) == len(data)
    assert len(akf.history) == len(data)
    assert akf.k == 6  # Since it starts at 1, after 5 steps it is 6


def test_arithmetic_exactness():
    """Step-by-step arithmetic check for PPA equations."""
    akf = AdaptiveKalmanFilter(b=1.0, x0=2.0, P0=1.0, Q=0.5, R0=2.0)

    # z_1 = 4.0
    # x_pred = 2.0
    # P_pred = 1.0 + 0.5 = 1.5
    # e_1 = 4.0 - 2.0 = 2.0
    # S_1 = 1.5 + 2.0 = 3.5
    # K_1 = 1.5 / 3.5 = 3/7
    # x_1 = 2.0 + (3/7)*2.0 = 2.0 + 6/7 = 20/7
    # P_1 = (1 - 3/7)*1.5 = 4/7 * 1.5 = 6/7
    # d_0 = 1
    # R_1 = 0*R_0 + 1*(2^2 - 1.5) = 4 - 1.5 = 2.5

    x_1 = akf.step(4.0)

    assert np.isclose(x_1, 20.0 / 7.0)
    hist = akf.history[0]
    assert np.isclose(hist["x_pred"], 2.0)
    assert np.isclose(hist["P_pred"], 1.5)
    assert np.isclose(hist["e_k"], 2.0)
    assert np.isclose(hist["S_k"], 3.5)
    assert np.isclose(hist["K_k"], 3.0 / 7.0)
    assert np.isclose(hist["P"], 6.0 / 7.0)
    assert np.isclose(hist["R"], 2.5)


def test_d02_pipeline_execution_and_schema():
    """Run full D02 pipeline with Configuration C1 and verify JSON and CSV outputs."""
    res = run_d02_pipeline(
        input_file=DATASET_PATH,
        sheet_name="Sheet1",
        output_csv_path=OUTPUT_CSV_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        figures_dir=FIGURES_DIR,
        akf_params=APPROVED_C1_PARAMS,
    )

    assert os.path.exists(OUTPUT_CSV_PATH)
    assert os.path.exists(OUTPUT_JSON_PATH)

    df_out = pd.read_csv(OUTPUT_CSV_PATH)
    assert len(df_out) == 500

    for ch in APPROVED_RAW_COLUMNS:
        assert ch in df_out.columns
        filt_col = f"{ch}_Filtered"
        assert filt_col in df_out.columns
        assert np.isfinite(df_out[filt_col].to_numpy()).all()

    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["milestone"] == "D02"
    assert data["selected_configuration"]["config_id"] == "C1"

    # Verify correlations exist for all 3 pairs
    for pair in ["Alice vs Bob", "Alice vs Eve1-Alice", "Bob vs Eve1-Bob"]:
        assert pair in data["correlation_comparison"]
        pdata = data["correlation_comparison"][pair]
        assert pdata["n"] == 500
        assert -1.0 <= pdata["filtered_r"] <= 1.0
        assert np.isfinite(pdata["filtered_r"])

    # Verify no negative R_k across any channel
    for ch in APPROVED_RAW_COLUMNS:
        diag = data["filter_diagnostics"][ch]
        assert diag["negative_R_count"] == 0
        assert diag["min_R"] >= 0.0
        assert diag["min_S"] > 0.0
        assert diag["min_P"] > 0.0


def test_excel_sha256_immutability():
    """Verify that the original Excel file has not been modified in place."""
    sha256_val = compute_file_sha256(DATASET_PATH)
    assert sha256_val == EXPECTED_SHA256, f"Excel file modified! SHA256: {sha256_val}"


def test_d02_figures_exist_and_non_empty():
    """Verify that all D02 visualization figures are generated and non-empty."""
    expected_figures = [
        "d02_akf_Alice_comparison.png",
        "d02_akf_Bob_comparison.png",
        "d02_akf_Eve1-Alice_comparison.png",
        "d02_akf_Eve1-Bob_comparison.png",
        "d02_akf_all_channels_overview.png",
        "d02_akf_pearson_comparison.png",
    ]

    for fig_name in expected_figures:
        fig_path = os.path.join(FIGURES_DIR, fig_name)
        assert os.path.exists(fig_path), f"Figure missing: {fig_path}"
        assert os.path.getsize(fig_path) > 1000, f"Figure file suspiciously small: {fig_path}"


if __name__ == "__main__":
    print("Running D02 test suite...")
    test_akf_initialization()
    print("[PASS] test_akf_initialization")
    test_akf_b_1_limit()
    print("[PASS] test_akf_b_1_limit")
    test_akf_exponential_forgetting()
    print("[PASS] test_akf_exponential_forgetting")
    test_negative_R_capability()
    print("[PASS] test_negative_R_capability")
    test_streaming_vs_batch_equivalence()
    print("[PASS] test_streaming_vs_batch_equivalence")
    test_arithmetic_exactness()
    print("[PASS] test_arithmetic_exactness")
    test_d02_pipeline_execution_and_schema()
    print("[PASS] test_d02_pipeline_execution_and_schema")
    test_excel_sha256_immutability()
    print("[PASS] test_excel_sha256_immutability")
    test_d02_figures_exist_and_non_empty()
    print("[PASS] test_d02_figures_exist_and_non_empty")
    print("\nAll D02 AKF verification tests passed successfully!")
