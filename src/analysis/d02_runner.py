"""
d02_runner.py

Runner script for Milestone D02: Adaptive Kalman Filter (AKF) Preprocessing.
Executes the approved Configuration C1 on all 4 raw RSSI measurement channels.

Configuration C1 (Experimentally Selected for Dummy RSSI):
- x0 = Adaptive (Uses first measurement of each stream for N=1 causal initialization)
- P0 = 1.0 (Baseline initial state estimation error covariance)
- Q  = 0.01 (Static process noise covariance for stationary channel)
- R0 = 1.0 (Initial measurement noise covariance prior)
- b  = 1.0 (Analytical limit d_{k-1} = 1/k, exact arithmetic Sage-Husa mean)
"""

import json
import os
import sys
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.akf import AdaptiveKalmanFilter
from src.analysis.correlation import compute_pearson_correlation
from src.analysis.visualization import generate_d02_figures
from src.data_io.loader import compute_file_sha256, load_sheet

APPROVED_RAW_COLUMNS = ["Alice", "Bob", "Eve1-Alice", "Eve1-Bob"]
EXPECTED_SHA256 = "abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d"

# Approved experimental configuration C1
APPROVED_C1_PARAMS = {
    "x0": "Adaptive",
    "P0": 1.0,
    "Q": 0.01,
    "R0": 1.0,
    "b": 1.0,
}


def run_d02_pipeline(
    input_file: str,
    sheet_name: str = "Sheet1",
    output_csv_path: str = None,
    output_json_path: str = None,
    figures_dir: str = None,
    akf_params: Dict[str, float] = None,
) -> Dict[str, Any]:
    """
    Execute the complete D02 AKF filtering, correlation analysis, and figure generation.
    """
    if akf_params is None:
        akf_params = APPROVED_C1_PARAMS

    if output_csv_path is None:
        output_csv_path = os.path.join(project_root, "results", "dummy", "d02_akf_filtered.csv")
    if output_json_path is None:
        output_json_path = os.path.join(project_root, "results", "dummy", "d02_akf_results.json")
    if figures_dir is None:
        figures_dir = os.path.join(project_root, "results", "dummy", "figures")

    # 1. Verify input dataset integrity
    actual_sha256 = compute_file_sha256(input_file)
    if actual_sha256 != EXPECTED_SHA256:
        raise ValueError(f"Input file SHA-256 mismatch! Expected {EXPECTED_SHA256}, got {actual_sha256}")

    # 2. Load strictly approved raw channels
    df_raw = load_sheet(input_file, sheet_name=sheet_name, usecols=APPROVED_RAW_COLUMNS)
    n_samples = len(df_raw)
    if n_samples != 500:
        raise ValueError(f"Expected 500 samples, got {n_samples}")

    out_df = df_raw.copy()
    diagnostics = {}
    channel_stats = {}

    # 3. Apply AKF independently to each approved channel
    for ch in APPROVED_RAW_COLUMNS:
        raw_vals = df_raw[ch].to_numpy(dtype=np.float64)
        
        # Adaptive initialization: first measurement + 2.0 dBm offset
        x0_val = float(raw_vals[0]) + 2.0 if akf_params.get("x0") == "Adaptive" else float(akf_params.get("x0", -70.0))

        akf = AdaptiveKalmanFilter(
            b=akf_params["b"],
            x0=x0_val,
            P0=akf_params["P0"],
            Q=akf_params["Q"],
            R0=akf_params["R0"],
        )

        filt_vals = np.array([akf.step(z) for z in raw_vals], dtype=np.float64)

        filt_col = f"{ch}_Filtered"
        out_df[filt_col] = filt_vals

        # Verification per channel
        if len(filt_vals) != n_samples:
            raise ValueError(f"Channel {ch} filtered output length mismatch!")
        if np.isnan(filt_vals).any() or np.isinf(filt_vals).any():
            raise ValueError(f"Channel {ch} contains NaN or Inf values!")

        history = akf.history
        min_R = min(h["R"] for h in history)
        max_R = max(h["R"] for h in history)
        final_R = history[-1]["R"]
        min_S = min(h["S_k"] for h in history)
        min_P = min(h["P"] for h in history)
        neg_R_count = sum(1 for h in history if h["R"] < 0)

        if neg_R_count > 0 or min_R <= 0 or min_S <= 0 or min_P <= 0:
            raise ValueError(f"Strict covariance validation failed for Channel {ch}: min_R={min_R}, min_S={min_S}, min_P={min_P}")

        raw_var = float(np.var(raw_vals))
        filt_var = float(np.var(filt_vals))
        var_reduction_pct = float((raw_var - filt_var) / raw_var * 100.0)

        channel_stats[ch] = {
            "raw_mean": float(np.mean(raw_vals)),
            "raw_variance": raw_var,
            "filtered_mean": float(np.mean(filt_vals)),
            "filtered_variance": filt_var,
            "variance_reduction_percent": var_reduction_pct,
        }

        diagnostics[ch] = {
            "min_R": float(min_R),
            "max_R": float(max_R),
            "final_R": float(final_R),
            "min_S": float(min_S),
            "min_P": float(min_P),
            "negative_R_count": neg_R_count,
        }

    # 4. Compute correlations for standard pairs (Raw vs Filtered)
    pairs: List[Tuple[str, str]] = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    raw_correlations = {}
    filtered_correlations = {}

    for col_a, col_b in pairs:
        pair_key = f"{col_a} vs {col_b}"
        raw_res = compute_pearson_correlation(df_raw[col_a].to_numpy(), df_raw[col_b].to_numpy())
        filt_res = compute_pearson_correlation(out_df[f"{col_a}_Filtered"].to_numpy(), out_df[f"{col_b}_Filtered"].to_numpy())

        raw_correlations[pair_key] = raw_res
        filtered_correlations[pair_key] = filt_res

    # 5. Generate Figures
    figure_paths = generate_d02_figures(
        out_df,
        APPROVED_RAW_COLUMNS,
        raw_correlations,
        filtered_correlations,
        figures_dir,
    )

    # 6. Construct structured JSON payload
    results_payload = {
        "milestone": "D02",
        "description": "Adaptive Kalman Filter (AKF) Preprocessing on Dummy RSSI",
        "input_dataset": {
            "path": input_file,
            "sheet_name": sheet_name,
            "sha256": actual_sha256,
            "sample_count": n_samples,
        },
        "selected_configuration": {
            "config_id": "C1",
            "parameters": akf_params,
            "classification": "Experimentally selected from Alice/Bob sensitivity study",
            "weighting_factor_convention": "d_{k-1} = 1/k (analytical b=1.0 limit)",
        },
        "correlation_comparison": {
            pair: {
                "raw_r": raw_correlations[pair]["r"],
                "filtered_r": filtered_correlations[pair]["r"],
                "delta_r": filtered_correlations[pair]["r"] - raw_correlations[pair]["r"],
                "n": raw_correlations[pair]["n"],
            }
            for pair in raw_correlations
        },
        "channel_statistics": channel_stats,
        "filter_diagnostics": diagnostics,
        "generated_artifacts": {
            "filtered_csv": os.path.abspath(output_csv_path),
            "results_json": os.path.abspath(output_json_path),
            "figures": {k: os.path.abspath(v) for k, v in figure_paths.items()},
        },
    }

    # 7. Write results to disk
    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)

    out_df.to_csv(output_csv_path, index=False)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=4)

    return results_payload


if __name__ == "__main__":
    dataset_path = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")
    print(f"Running D02 pipeline on {dataset_path}...")
    res = run_d02_pipeline(dataset_path)
    print("\nD02 AKF Run Completed Successfully!")
    print(f"Filtered CSV: {res['generated_artifacts']['filtered_csv']}")
    print(f"Results JSON: {res['generated_artifacts']['results_json']}")
    print("\nCorrelation Results:")
    for pair, cdata in res["correlation_comparison"].items():
        print(f"  {pair}: raw r = {cdata['raw_r']:.4f} -> filtered r = {cdata['filtered_r']:.4f} (delta = {cdata['delta_r']:+.4f})")
