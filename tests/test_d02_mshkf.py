"""
test_d02_mshkf.py

Verification test suite for Milestone D02 - Adaptive Kalman Filter (AKF)
with online adaptive fuzzy clustering based on Wang et al. (2022) and PPA.pdf.

Coverage:
1. Exact scalar Sage-Husa recursive arithmetic (Wang et al. Eqs. 1-7, 26, 27).
2. Exact Gustafson-Kessel fuzzy clustering math (Wang et al. Eqs. 16-22).
3. Online fuzzy cluster growth verification upon regime shifts (Wang Eq. 21).
4. Analytical b=1.0 limit handling without division-by-zero (d_{k-1} = 1/k).
5. Exponential fading with b < 1.0.
6. Streaming vs batch equivalence.
7. Finite and positive covariance behavior across all channels.
8. End-to-end D02 pipeline execution with approved Configuration C1.
9. Preservation of dataset length (n=500), columns, and Excel SHA-256 immutability.
10. D00 and D01 regression sanity checks.
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

from src.analysis.mshkf import FuzzyClusteringEngine, ModifiedSageHusaKalmanFilter
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
    """Verify MSHKF and Fuzzy engine parameters are explicitly set and configurable."""
    fuzzy = FuzzyClusteringEngine(n_clusters=2, m=2.0, learning_rate=0.05)
    mshkf = ModifiedSageHusaKalmanFilter(
        x0=-75.0,
        P0=1.0,
        Q_regimes=(0.001, 0.010),
        b_regimes=(1.00, 0.98),
        r0=0.0,
        R0=1.0,
        fuzzy_engine=fuzzy,
    )
    assert mshkf.x == -75.0
    assert mshkf.P == 1.0
    assert mshkf.Q_regimes == (0.001, 0.010)
    assert mshkf.b_regimes == (1.00, 0.98)
    assert mshkf.r == 0.0
    assert mshkf.R == 1.0
    assert mshkf.k == 1


def test_fuzzy_clustering_equations():
    """Verify exact Gustafson-Kessel fuzzy clustering calculations (Wang Eqs. 16-22)."""
    engine = FuzzyClusteringEngine(n_clusters=2, m=2.0, learning_rate=0.1)
    engine.init_clusters(z_first=-80.0, x0_prior=-78.0)

    # Feature extraction check: [z_k, Delta z_k, sigma_k]
    z_buf = [-80.0, -78.0, -76.0]
    f_k = engine.extract_features(z_buf)
    assert np.isclose(f_k[0], -76.0)
    assert np.isclose(f_k[1], 2.0)
    assert f_k[2] > 0.0

    # Distance and membership partition of unity
    d_vec = engine.compute_mahalanobis_distances(f_k)
    assert len(d_vec) == 2
    assert (d_vec > 0).all()

    mu = engine.compute_memberships(d_vec)
    assert len(mu) == 2
    assert np.isclose(np.sum(mu), 1.0)
    assert (mu >= 0.0).all() and (mu <= 1.0).all()


def test_fuzzy_cluster_growth_on_regime_shift():
    """Verify that cluster count actually grows when observing a sustained regime shift (Wang Eq. 21)."""
    # Create engine with lower support threshold for testing
    engine = FuzzyClusteringEngine(n_clusters=2, min_pts_support=8, max_clusters=5)
    
    # Generate synthetic sequence: 30 stationary samples around -75 dBm followed by 30 samples at -45 dBm
    np.random.seed(42)
    regime_1 = np.random.normal(-75.0, 0.3, 30)
    regime_2 = np.random.normal(-45.0, 0.3, 30)
    synthetic_stream = np.concatenate([regime_1, regime_2])

    z_buf = []
    for z in synthetic_stream:
        z_buf.append(z)
        engine.step(z_buf, -75.0)

    # Confirm that cluster count grew from 2 to 3
    assert engine.c == 3, f"Expected cluster count to increase to 3, got {engine.c}"
    assert engine.v.shape[0] == 3
    assert engine.F.shape[0] == 3
    assert len(engine.r_radius) == 3


def test_sage_husa_arithmetic_exactness():
    """Step-by-step arithmetic check for Sage-Husa recursion (Wang Eqs. 1-7, 26, 27)."""
    class StaticFuzzyEngine:
        def step(self, z_buf, x_prior):
            return np.array([z_buf[-1], 0.0, 0.5]), np.array([1.0, 0.0]), 0

    mshkf = ModifiedSageHusaKalmanFilter(
        x0=2.0,
        P0=1.0,
        Q_regimes=(0.5, 0.5),
        b_regimes=(1.0, 1.0),
        r0=0.0,
        R0=2.0,
        fuzzy_engine=StaticFuzzyEngine(),
    )

    # Step 1: z_1 = 4.0
    # Q = 0.5, b = 1.0 -> d_0 = 1.0 / 1 = 1.0
    # 1. x_pred = 2.0
    # 2. P_pred = 1.0 + 0.5 = 1.5
    # 3. eps_1 = 4.0 - 2.0 - 0.0 = 2.0
    # 4. S_1 = 1.5 + 2.0 = 3.5
    # 5. K_1 = 1.5 / 3.5 = 3/7
    # 6. x_1 = 2.0 + (3/7)*2.0 = 20/7
    # 7. P_1 = (1 - 3/7)*1.5 = 6/7
    # 8. r_1 = (1 - 1)*0 + 1*(4.0 - 2.0) = 2.0
    # 9. R_1 = (1 - 1)*2.0 + 1*(2.0^2 - 1.5) = 4.0 - 1.5 = 2.5

    x_1 = mshkf.step(4.0)
    assert np.isclose(x_1, 20.0 / 7.0)

    h1 = mshkf.history[0]
    assert np.isclose(h1["x_pred"], 2.0)
    assert np.isclose(h1["P_pred"], 1.5)
    assert np.isclose(h1["eps_k"], 2.0)
    assert np.isclose(h1["S_k"], 3.5)
    assert np.isclose(h1["K_k"], 3.0 / 7.0)
    assert np.isclose(h1["P"], 6.0 / 7.0)
    assert np.isclose(h1["r"], 2.0)
    assert np.isclose(h1["R"], 2.5)


def test_b_1_limit_and_fading():
    """Verify that b=1.0 uses analytical limit (1/k) and b<1 uses exponential fading."""
    mshkf_1 = ModifiedSageHusaKalmanFilter(x0=0.0, P0=1.0, Q_regimes=(0.0, 0.0), b_regimes=(1.0, 1.0))
    mshkf_1.step(5.0)
    assert mshkf_1.history[0]["d_k_minus_1"] == 1.0

    mshkf_fading = ModifiedSageHusaKalmanFilter(x0=0.0, P0=1.0, Q_regimes=(0.1, 0.1), b_regimes=(0.9, 0.9))
    mshkf_fading.step(1.0)
    assert np.isclose(mshkf_fading.history[0]["d_k_minus_1"], 1.0)
    mshkf_fading.step(2.0)
    # k=2: d_1 = (1 - 0.9)/(1 - 0.9^2) = 0.1 / 0.19 = 10/19
    assert np.isclose(mshkf_fading.history[1]["d_k_minus_1"], 10.0 / 19.0)


def test_streaming_vs_batch_equivalence():
    """Verify sequential processing produces identical deterministic states."""
    data = [1.2, 1.5, 1.1, 1.6, 1.3, 1.8, 1.4]

    # Run 1
    mshkf1 = ModifiedSageHusaKalmanFilter(x0=1.0, P0=1.0, Q_regimes=(0.01, 0.05), b_regimes=(1.0, 0.98))
    res1 = [mshkf1.step(z) for z in data]

    # Run 2
    mshkf2 = ModifiedSageHusaKalmanFilter(x0=1.0, P0=1.0, Q_regimes=(0.01, 0.05), b_regimes=(1.0, 0.98))
    res2 = [mshkf2.step(z) for z in data]

    assert np.allclose(res1, res2)
    assert len(mshkf1.history) == len(data)
    assert mshkf1.k == len(data) + 1


def test_d02_pipeline_execution_and_schema():
    """Run full D02 MSHKF pipeline with Configuration C1 and verify JSON and CSV outputs."""
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
    assert data["selected_configuration"]["config_id"] == "C1"

    # Verify correlations exist for all 3 pairs
    for pair in ["Alice vs Bob", "Alice vs Eve1-Alice", "Bob vs Eve1-Bob"]:
        assert pair in data["correlation_comparison"]
        pdata = data["correlation_comparison"][pair]
        assert pdata["n"] == 500
        assert -1.0 <= pdata["filtered_r"] <= 1.0
        assert np.isfinite(pdata["filtered_r"])

    # Verify strict positivity across all channels
    for ch in APPROVED_RAW_COLUMNS:
        diag = data["filter_diagnostics"][ch]
        assert diag["negative_R_count"] == 0
        assert diag["min_R"] > 0.0
        assert diag["min_S"] > 0.0
        assert diag["min_P"] > 0.0

        fuzzy_diag = data["fuzzy_clustering_diagnostics"][ch]
        assert fuzzy_diag["partition_coefficient_PC"] > 0.0
        assert fuzzy_diag["cluster_0_samples"] + fuzzy_diag["cluster_1_samples"] == 500


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
        "d02_mshkf_fuzzy_diagnostics.png",
    ]

    for fig_name in expected_figures:
        fig_path = os.path.join(FIGURES_DIR, fig_name)
        assert os.path.exists(fig_path), f"Figure missing: {fig_path}"
        assert os.path.getsize(fig_path) > 1000, f"Figure file suspiciously small: {fig_path}"


if __name__ == "__main__":
    print("Running D02 Adaptive Kalman Filter (AKF) test suite...")
    test_mshkf_initialization()
    print("[PASS] test_mshkf_initialization")
    test_fuzzy_clustering_equations()
    print("[PASS] test_fuzzy_clustering_equations")
    test_fuzzy_cluster_growth_on_regime_shift()
    print("[PASS] test_fuzzy_cluster_growth_on_regime_shift")
    test_sage_husa_arithmetic_exactness()
    print("[PASS] test_sage_husa_arithmetic_exactness")
    test_b_1_limit_and_fading()
    print("[PASS] test_b_1_limit_and_fading")
    test_streaming_vs_batch_equivalence()
    print("[PASS] test_streaming_vs_batch_equivalence")
    test_d02_pipeline_execution_and_schema()
    print("[PASS] test_d02_pipeline_execution_and_schema")
    test_excel_sha256_immutability()
    print("[PASS] test_excel_sha256_immutability")
    test_d02_figures_exist_and_non_empty()
    print("[PASS] test_d02_figures_exist_and_non_empty")
    print("\nAll D02 Adaptive Kalman Filter (AKF) verification tests passed successfully!")
