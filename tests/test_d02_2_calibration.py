"""
test_d02_2_calibration.py

Comprehensive test suite for Milestone D02.2: Empirical Parameter Calibration for AKF.

Test Coverage:
1. Mathematical exactness of RTS backward recursion against manual reference values.
2. Independent per-signal parameter estimation (no shared numerical values).
3. Finite and non-negative covariance parameters (P0, R0, Q_stable, Q_dynamic >= 0).
4. Strict ordering constraint enforcement (0 < b_dynamic < b_stable < 1).
5. Elimination of hard-coded D02 C1 priors for replaced parameters.
6. End-to-end D02.2 pipeline execution and schema verification (n=500 aligned samples).
7. Evaluation on held-out test split (last 200 samples).
8. Deterministic reruns producing byte-identical outputs.
9. Excel file byte-for-byte immutability (SHA-256 integrity).
10. D02.2 visualization artifacts existence and non-emptiness.
"""

import json
import os
import sys
import numpy as np
import pandas as pd
import pytest

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.d02_2_calibration import (
    calibrate_channel_parameters,
    compute_rts_reference_state,
)
from src.analysis.d02_2_runner import run_d02_2_pipeline
from src.analysis.d02_runner import APPROVED_C1_PARAMS, APPROVED_RAW_COLUMNS, EXPECTED_SHA256
from src.data_io.loader import compute_file_sha256, load_sheet

DATASET_PATH = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")
OUTPUT_CSV_PATH = os.path.join(project_root, "results", "dummy", "d02_2_mshkf_filtered.csv")
OUTPUT_JSON_PATH = os.path.join(project_root, "results", "dummy", "d02_2_mshkf_results.json")
FIGURES_DIR = os.path.join(project_root, "results", "dummy", "figures", "d02_2")


@pytest.fixture(scope="module")
def d02_2_execution_results():
    """Module-level fixture to run D02.2 pipeline once for downstream tests."""
    return run_d02_2_pipeline(
        input_file=DATASET_PATH,
        sheet_name="Sheet1",
        output_csv_path=OUTPUT_CSV_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        figures_dir=FIGURES_DIR,
    )


def test_rts_backward_recursion_mathematical_exactness():
    """
    Verify step-by-step arithmetic of backward RTS reference smoothing.
    Given:
        N = 3
        x_hat = [10.0, 12.0, 14.0]
        P = [2.0, 3.0, 4.0]
        Q_ref = [1.0, 2.0, 3.0]

    Manual calculations:
    - k=2 (terminal): x_ref[2] = x_hat[2] = 14.0
    - k=1:
        C_1 = P[1] / (P[1] + Q_ref[1]) = 3.0 / (3.0 + 2.0) = 3/5 = 0.6
        x_ref[1] = x_hat[1] + C_1 * (x_ref[2] - x_hat[1]) = 12.0 + 0.6 * (14.0 - 12.0) = 12.0 + 1.2 = 13.2
    - k=0:
        C_0 = P[0] / (P[0] + Q_ref[0]) = 2.0 / (2.0 + 1.0) = 2/3
        x_ref[0] = x_hat[0] + C_0 * (x_ref[1] - x_hat[0]) = 10.0 + (2/3) * (13.2 - 10.0) = 10.0 + (2/3)*3.2 = 10.0 + 2.1333333 = 12.13333333
    """
    x_hat = np.array([10.0, 12.0, 14.0], dtype=np.float64)
    P = np.array([2.0, 3.0, 4.0], dtype=np.float64)
    Q_ref = np.array([1.0, 2.0, 3.0], dtype=np.float64)

    x_ref = compute_rts_reference_state(x_hat, P, Q_ref)

    assert len(x_ref) == 3
    assert np.isclose(x_ref[2], 14.0)
    assert np.isclose(x_ref[1], 13.2)
    assert np.isclose(x_ref[0], 10.0 + (2.0 / 3.0) * 3.2)


def test_independent_per_signal_parameter_sets(d02_2_execution_results):
    """
    Verify all four signals obtain independently calculated, distinct parameter sets.
    """
    params = d02_2_execution_results["calibration_configuration"]["per_signal_calibrated_parameters"]
    assert len(params) == 4

    channels = APPROVED_RAW_COLUMNS
    for i in range(len(channels)):
        for j in range(i + 1, len(channels)):
            ch_a = channels[i]
            ch_b = channels[j]
            p_a = params[ch_a]
            p_b = params[ch_b]

            assert not (
                np.isclose(p_a["x0"], p_b["x0"]) and
                np.isclose(p_a["P0"], p_b["P0"]) and
                np.isclose(p_a["r0"], p_b["r0"]) and
                np.isclose(p_a["R0"], p_b["R0"])
            ), f"Channels {ch_a} and {ch_b} unexpectedly have identical calibrated priors!"


def test_covariance_parameters_finite_and_non_negative(d02_2_execution_results):
    """
    Verify P0, R0, Q_stable, and Q_dynamic are finite and >= 0.0 for every signal.
    """
    params = d02_2_execution_results["calibration_configuration"]["per_signal_calibrated_parameters"]
    for ch in APPROVED_RAW_COLUMNS:
        p = params[ch]
        for key in ["P0", "R0", "Q_stable", "Q_dynamic"]:
            val = p[key]
            assert np.isfinite(val), f"Parameter {key} for {ch} is not finite: {val}"
            assert val >= 0.0, f"Parameter {key} for {ch} is negative: {val}"


def test_b_ordering_constraint(d02_2_execution_results):
    """
    Verify 0 < b_dynamic < b_stable < 1 for every signal.
    """
    params = d02_2_execution_results["calibration_configuration"]["per_signal_calibrated_parameters"]
    for ch in APPROVED_RAW_COLUMNS:
        p = params[ch]
        bs = p["b_stable"]
        bd = p["b_dynamic"]

        assert 0.0 < bd < bs < 1.0, f"Ordering constraint 0 < b_dynamic ({bd}) < b_stable ({bs}) < 1 violated for {ch}"


def test_no_hardcoded_c1_priors_reused(d02_2_execution_results):
    """
    Verify that old hard-coded D02 C1 priors (z0+2, P0=1.0, Q=[0.001,0.010], b=[1.00,0.98], r0=0, R0=1)
    are not silently reused for the replaced parameters.
    """
    params = d02_2_execution_results["calibration_configuration"]["per_signal_calibrated_parameters"]
    for ch in APPROVED_RAW_COLUMNS:
        p = params[ch]
        assert not np.isclose(p["P0"], 1.0), f"Hard-coded P0=1.0 detected for {ch}"
        assert not np.isclose(p["R0"], 1.0), f"Hard-coded R0=1.0 detected for {ch}"
        assert not np.isclose(p["b_stable"], 1.00), f"Hard-coded b_stable=1.00 detected for {ch}"


def test_d02_2_pipeline_outputs_and_schema(d02_2_execution_results):
    """
    Verify D02.2 produces exactly 500 aligned filtered samples per channel and valid schema.
    """
    assert os.path.exists(OUTPUT_CSV_PATH)
    assert os.path.exists(OUTPUT_JSON_PATH)

    df_out = pd.read_csv(OUTPUT_CSV_PATH)
    assert len(df_out) == 500

    for ch in APPROVED_RAW_COLUMNS:
        assert ch in df_out.columns
        filt_col = f"{ch}_Filtered"
        assert filt_col in df_out.columns
        assert len(df_out[filt_col]) == 500
        assert np.isfinite(df_out[filt_col].to_numpy()).all()

    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["milestone"] == "D02.2"
    assert data["calibration_configuration"]["n_cal"] == 300
    assert data["calibration_configuration"]["n_eval"] == 200

    for pair in ["Alice vs Bob", "Alice vs Eve1-Alice", "Bob vs Eve1-Bob"]:
        assert pair in data["correlation_comparison_full_500"]
        assert pair in data["correlation_comparison_held_out_200"]


def test_deterministic_reruns():
    """
    Verify running D02.2 pipeline multiple times produces identical numerical results.
    """
    res1 = run_d02_2_pipeline(input_file=DATASET_PATH, sheet_name="Sheet1")
    df1 = pd.read_csv(OUTPUT_CSV_PATH)

    res2 = run_d02_2_pipeline(input_file=DATASET_PATH, sheet_name="Sheet1")
    df2 = pd.read_csv(OUTPUT_CSV_PATH)

    for ch in APPROVED_RAW_COLUMNS:
        filt_col = f"{ch}_Filtered"
        assert np.allclose(df1[filt_col].to_numpy(), df2[filt_col].to_numpy(), atol=1e-12)

    p1 = res1["calibration_configuration"]["per_signal_calibrated_parameters"]
    p2 = res2["calibration_configuration"]["per_signal_calibrated_parameters"]
    for ch in APPROVED_RAW_COLUMNS:
        for k in ["x0", "P0", "r0", "R0", "Q_stable", "Q_dynamic", "b_stable", "b_dynamic"]:
            assert np.isclose(p1[ch][k], p2[ch][k], atol=1e-12)


def test_excel_sha256_unmodified():
    """
    Verify raw Excel file is untouched.
    """
    actual_sha = compute_file_sha256(DATASET_PATH)
    assert actual_sha == EXPECTED_SHA256


def test_d02_2_figures_exist_and_non_empty(d02_2_execution_results):
    """
    Verify that all D02.2 visualization figures are generated and non-empty.
    """
    expected_figures = [
        "d02_2_mshkf_Alice_comparison.png",
        "d02_2_mshkf_Bob_comparison.png",
        "d02_2_mshkf_Eve1-Alice_comparison.png",
        "d02_2_mshkf_Eve1-Bob_comparison.png",
        "d02_2_mshkf_all_channels_overview.png",
        "d02_2_mshkf_pearson_comparison.png",
        "d02_2_mshkf_rssi_correlation_scatter.png",
        "d02_2_mshkf_signal_overlay_comparison.png",
        "d02_2_mshkf_fuzzy_diagnostics.png",
    ]

    for fig_name in expected_figures:
        fig_path = os.path.join(FIGURES_DIR, fig_name)
        assert os.path.exists(fig_path), f"Figure {fig_name} does not exist!"
        assert os.path.getsize(fig_path) > 1000, f"Figure {fig_name} is empty or corrupted!"


def test_d02_vs_d02_2_comparison_figures_exist_and_non_empty(d02_2_execution_results):
    """
    Verify that all D02 vs D02.2 full-trace comparison figures are generated and non-empty.
    """
    comp_figures_dir = os.path.join(project_root, "results", "dummy", "figures", "d02_vs_d02_2")
    expected_figures = [
        "d02_vs_d02_2_Alice_comparison.png",
        "d02_vs_d02_2_Bob_comparison.png",
        "d02_vs_d02_2_Eve1-Alice_comparison.png",
        "d02_vs_d02_2_Eve1-Bob_comparison.png",
        "d02_vs_d02_2_all_channels_overview.png",
        "d02_vs_d02_2_pearson_comparison.png",
    ]

    for fig_name in expected_figures:
        fig_path = os.path.join(comp_figures_dir, fig_name)
        assert os.path.exists(fig_path), f"Comparison figure {fig_name} does not exist!"
        assert os.path.getsize(fig_path) > 1000, f"Comparison figure {fig_name} is empty or corrupted!"
