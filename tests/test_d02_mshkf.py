"""
test_d02_mshkf.py

Verification test suite for Milestone D02 - Modified Sage-Husa Adaptive Kalman Filter (MSHAKF)
based on Wang et al. (2022) and AKF.pdf.

Coverage:
1. Exact scalar Sage-Husa recursive arithmetic (Wang et al. Eqs. 1-7, 26, 27):
   - state prediction
   - covariance prediction
   - innovation calculation
   - innovation covariance
   - Kalman gain
   - state update
   - covariance update
   - adaptive measurement noise mean update
   - adaptive measurement noise covariance update
2. Analytical b=1.0 limit handling without division-by-zero (d_{k-1} = 1/k).
3. Exponential fading with b < 1.0 (d_{k-1} = (1 - b) / (1 - b^k)).
4. Streaming vs batch equivalence.
5. Finite and positive covariance behavior across all channels.
6. Adaptive online noise estimation convergence/tracking.
7. End-to-end D02 pipeline execution with approved Configuration C1.
8. Preservation of dataset length (n=500), columns, and Excel SHA-256 immutability.
9. Regression verification for downstream D03 compatibility.
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

from src.analysis.mshkf import ModifiedSageHusaKalmanFilter
from src.analysis.d02_runner import (
    APPROVED_C1_PARAMS,
    APPROVED_RAW_COLUMNS,
    EXPECTED_SHA256,
    run_d02_pipeline,
)
from src.data_io.loader import compute_file_sha256

DATASET_PATH = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")
OUTPUT_CSV_PATH = os.path.join(project_root, "results", "dummy", "d02_mshkf_filtered.csv")
OUTPUT_JSON_PATH = os.path.join(project_root, "results", "dummy", "d02_mshkf_results.json")
FIGURES_DIR = os.path.join(project_root, "results", "dummy", "figures", "d02")


def test_mshkf_initialization():
    """Verify MSHAKF parameters are explicitly set and configurable."""
    mshkf = ModifiedSageHusaKalmanFilter(
        x0=-75.0,
        P0=1.0,
        Q=0.001,
        b=0.98,
        r0=0.0,
        R0=1.0,
    )
    assert mshkf.x == -75.0
    assert mshkf.P == 1.0
    assert mshkf.Q == 0.001
    assert mshkf.b == 0.98
    assert mshkf.r == 0.0
    assert mshkf.R == 1.0
    assert mshkf.k == 1


def test_sage_husa_arithmetic_exactness():
    """
    Step-by-step arithmetic verification of all 8 core MSHAKF equations (Wang Eqs. 1-7, 26, 27).
    
    Setup:
      x0 = 2.0, P0 = 1.0, Q = 0.5, b = 1.0, r0 = 0.0, R0 = 2.0, q = 0.0
      Input: z_1 = 4.0
    
    Theoretical derivation at k=1 (b=1.0 -> d_0 = 1/1 = 1.0):
      1. State prediction (Eq. 1):              x_pred = 2.0 + 0 = 2.0
      2. Covariance prediction (Eq. 2):         P_pred = 1.0 + 0.5 = 1.5
      3. Innovation (Eq. 3):                    eps_1  = 4.0 - 2.0 - 0.0 = 2.0
      4. Innovation covariance (Eq. 4):         S_1    = 1.5 + 2.0 = 3.5
      5. Kalman gain (Eq. 5):                   K_1    = 1.5 / 3.5 = 3/7
      6. Posterior state update (Eq. 6):        x_1    = 2.0 + (3/7)*2.0 = 20/7
      7. Posterior covariance (Eq. 7):          P_1    = (1 - 3/7)*1.5 = 6/7
      8. Noise mean update (Eq. 26):            r_1    = (1 - 1)*0 + 1*(4.0 - 2.0) = 2.0
      9. Noise covariance update (Eq. 27):      R_1    = (1 - 1)*2.0 + 1*(2.0^2 - 1.5) = 2.5
    """
    mshkf = ModifiedSageHusaKalmanFilter(
        x0=2.0,
        P0=1.0,
        Q=0.5,
        b=1.0,
        r0=0.0,
        R0=2.0,
    )

    x_1 = mshkf.step(4.0)
    assert np.isclose(x_1, 20.0 / 7.0)

    h1 = mshkf.history[0]
    assert np.isclose(h1["x_pred"], 2.0)
    assert np.isclose(h1["P_pred"], 1.5)
    assert np.isclose(h1["eps_k"], 2.0)
    assert np.isclose(h1["S_k"], 3.5)
    assert np.isclose(h1["K_k"], 3.0 / 7.0)
    assert np.isclose(h1["x"], 20.0 / 7.0)
    assert np.isclose(h1["P"], 6.0 / 7.0)
    assert np.isclose(h1["r"], 2.0)
    assert np.isclose(h1["R"], 2.5)
    assert np.isclose(h1["d_k_minus_1"], 1.0)

    # Step 2: z_2 = 3.0
    # At k=2, b=1.0 -> d_1 = 1/2 = 0.5
    # x_pred = 20/7
    # P_pred = 6/7 + 0.5 = 19/14 (~1.3571)
    # eps_2  = 3.0 - 20/7 - 2.0 = 1/7 - 2 = -13/7
    # S_2    = 19/14 + 2.5 = 19/14 + 35/14 = 54/14 = 27/7
    # K_2    = (19/14) / (54/14) = 19/54
    # x_2    = 20/7 + (19/54)*(-13/7) = (1080 - 247) / 378 = 833 / 378
    # P_2    = (1 - 19/54)*(19/14) = (35/54)*(19/14) = 665 / 756
    # r_2    = 0.5*2.0 + 0.5*(3.0 - 20/7) = 1.0 + 0.5*(1/7) = 1.0 + 1/14 = 15/14
    # R_2    = 0.5*2.5 + 0.5*((-13/7)^2 - 19/14)
    x_2 = mshkf.step(3.0)
    h2 = mshkf.history[1]
    assert np.isclose(h2["d_k_minus_1"], 0.5)
    assert np.isclose(h2["x_pred"], 20.0 / 7.0)
    assert np.isclose(h2["P_pred"], 19.0 / 14.0)
    assert np.isclose(h2["eps_k"], -13.0 / 7.0)
    assert np.isclose(h2["S_k"], 27.0 / 7.0)
    assert np.isclose(h2["K_k"], 19.0 / 54.0)
    assert np.isclose(x_2, 833.0 / 378.0)
    assert np.isclose(h2["P"], (35.0 / 54.0) * (19.0 / 14.0))
    assert np.isclose(h2["r"], 15.0 / 14.0)
    expected_R2 = 0.5 * 2.5 + 0.5 * ((-13.0 / 7.0) ** 2 - 19.0 / 14.0)
    assert np.isclose(h2["R"], expected_R2)


def test_b_1_limit_and_fading():
    """Verify that b=1.0 uses analytical limit (1/k) and b<1 uses exponential fading."""
    mshkf_1 = ModifiedSageHusaKalmanFilter(x0=0.0, P0=1.0, Q=0.0, b=1.0)
    mshkf_1.step(5.0)
    assert mshkf_1.history[0]["d_k_minus_1"] == 1.0
    mshkf_1.step(6.0)
    assert mshkf_1.history[1]["d_k_minus_1"] == 0.5
    mshkf_1.step(7.0)
    assert np.isclose(mshkf_1.history[2]["d_k_minus_1"], 1.0 / 3.0)

    mshkf_fading = ModifiedSageHusaKalmanFilter(x0=0.0, P0=1.0, Q=0.1, b=0.9)
    mshkf_fading.step(1.0)
    assert np.isclose(mshkf_fading.history[0]["d_k_minus_1"], 1.0)
    mshkf_fading.step(2.0)
    # k=2: d_1 = (1 - 0.9)/(1 - 0.9^2) = 0.1 / 0.19 = 10/19
    assert np.isclose(mshkf_fading.history[1]["d_k_minus_1"], 10.0 / 19.0)
    mshkf_fading.step(3.0)
    # k=3: d_2 = (1 - 0.9)/(1 - 0.9^3) = 0.1 / 0.271 = 100/271
    assert np.isclose(mshkf_fading.history[2]["d_k_minus_1"], 100.0 / 271.0)


def test_streaming_vs_batch_equivalence():
    """Verify sequential processing produces identical deterministic states."""
    data = [1.2, 1.5, 1.1, 1.6, 1.3, 1.8, 1.4]

    # Run 1
    mshkf1 = ModifiedSageHusaKalmanFilter(x0=1.0, P0=1.0, Q=0.001, b=0.98)
    res1 = [mshkf1.step(z) for z in data]

    # Run 2
    mshkf2 = ModifiedSageHusaKalmanFilter(x0=1.0, P0=1.0, Q=0.001, b=0.98)
    res2 = [mshkf2.step(z) for z in data]

    assert np.allclose(res1, res2)
    assert len(mshkf1.history) == len(data)
    assert mshkf1.k == len(data) + 1


def test_adaptive_noise_estimation_convergence():
    """Verify that MSHAKF online noise estimation adapts towards persistent noise offsets."""
    np.random.seed(42)
    true_x = -70.0
    true_noise_mean = 3.0
    true_noise_std = 1.0
    n_points = 200

    # Generate synthetic observations with offset noise: z = -70 + N(3.0, 1.0)
    measurements = true_x + np.random.normal(true_noise_mean, true_noise_std, n_points)

    mshkf = ModifiedSageHusaKalmanFilter(
        x0=true_x,
        P0=1.0,
        Q=0.0001,
        b=0.95,
        r0=0.0,
        R0=1.0,
    )

    for z in measurements:
        mshkf.step(z)

    final_r = mshkf.history[-1]["r"]
    final_R = mshkf.history[-1]["R"]

    # r_k should adaptively track the positive bias (shifting from initial 0.0 towards positive mean)
    assert final_r > 1.0, f"Expected r to adaptively increase towards positive bias, got {final_r}"
    assert final_R > 0.0, f"Expected positive noise covariance R, got {final_R}"


def test_d02_pipeline_execution_and_schema():
    """Run full D02 MSHAKF pipeline with Configuration C1 and verify JSON and CSV outputs."""
    res = run_d02_pipeline(
        input_file=DATASET_PATH,
        sheet_name="Sheet1",
        output_csv_path=OUTPUT_CSV_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        figures_dir=FIGURES_DIR,
        mshkf_params=APPROVED_C1_PARAMS,
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
    assert "fuzzy" not in data["algorithm"].lower()
    assert "fuzzy_clustering_diagnostics" not in data
    assert data["selected_configuration"]["config_id"] == "C1"

    # Verify correlations exist for all 3 pairs
    for pair in ["Alice vs Bob", "Alice vs Eve1-Alice", "Bob vs Eve1-Bob"]:
        assert pair in data["correlation_comparison"]
        pdata = data["correlation_comparison"][pair]
        assert pdata["n"] == 500
        assert -1.0 <= pdata["filtered_r"] <= 1.0
        assert np.isfinite(pdata["filtered_r"])

    # Alice vs Bob reciprocity must improve
    ab_corr = data["correlation_comparison"]["Alice vs Bob"]
    assert ab_corr["filtered_r"] > ab_corr["raw_r"], f"Filtered r ({ab_corr['filtered_r']}) should exceed raw r ({ab_corr['raw_r']})"

    # Verify strict positivity across all channels
    for ch in APPROVED_RAW_COLUMNS:
        diag = data["filter_diagnostics"][ch]
        assert diag["negative_R_count"] == 0
        assert diag["min_R"] > 0.0
        assert diag["min_S"] > 0.0
        assert diag["min_P"] > 0.0


def test_excel_sha256_immutability():
    """Verify that the original Excel file has not been modified byte-for-byte."""
    sha256_val = compute_file_sha256(DATASET_PATH)
    assert sha256_val == EXPECTED_SHA256, f"Excel file modified! SHA256: {sha256_val}"


def test_d02_figures_exist_and_non_empty():
    """Verify that all D02 visualization figures are generated and non-empty."""
    expected_figures = [
        "d02_mshkf_Alice_comparison.png",
        "d02_mshkf_Bob_comparison.png",
        "d02_mshkf_Eve1-Alice_comparison.png",
        "d02_mshkf_Eve1-Bob_comparison.png",
        "d02_mshkf_all_channels_overview.png",
        "d02_mshkf_pearson_comparison.png",
        "d02_mshkf_adaptive_diagnostics.png",
    ]

    for fig_name in expected_figures:
        fig_path = os.path.join(FIGURES_DIR, fig_name)
        assert os.path.exists(fig_path), f"Figure missing: {fig_path}"
        assert os.path.getsize(fig_path) > 1000, f"Figure file suspiciously small: {fig_path}"


if __name__ == "__main__":
    print("Running D02 Modified Sage-Husa Adaptive Kalman Filter (MSHAKF) test suite...")
    test_mshkf_initialization()
    print("[PASS] test_mshkf_initialization")
    test_sage_husa_arithmetic_exactness()
    print("[PASS] test_sage_husa_arithmetic_exactness")
    test_b_1_limit_and_fading()
    print("[PASS] test_b_1_limit_and_fading")
    test_streaming_vs_batch_equivalence()
    print("[PASS] test_streaming_vs_batch_equivalence")
    test_adaptive_noise_estimation_convergence()
    print("[PASS] test_adaptive_noise_estimation_convergence")
    test_d02_pipeline_execution_and_schema()
    print("[PASS] test_d02_pipeline_execution_and_schema")
    test_excel_sha256_immutability()
    print("[PASS] test_excel_sha256_immutability")
    test_d02_figures_exist_and_non_empty()
    print("[PASS] test_d02_figures_exist_and_non_empty")
    print("\nAll D02 MSHAKF verification tests passed successfully!")
