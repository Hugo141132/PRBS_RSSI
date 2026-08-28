"""
d02_2_runner.py

Runner script for Milestone D02.2: Empirical Parameter Calibration for Adaptive Kalman Filter (AKF)
with Gustafson-Kessel Fuzzy Clustering on Dummy RSSI.

Workflow:
1. Load strictly approved raw channels from Dummy RSSI.xlsx (Sheet1, 500 samples).
2. Execute D02 baseline pass to obtain first-pass posterior states and process noise.
3. Perform empirical parameter calibration over the calibration prefix (first 60%, samples 0:300).
4. Run D02.2 AKF filtering over all 500 samples with fixed per-signal calibrated parameters.
5. Compute both full-trace (n=500) and held-out evaluation (n=200, samples 300:500) metrics.
6. Generate publication-quality figures and structured JSON/CSV deliverables.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.correlation import compute_pearson_correlation
from src.analysis.d02_2_calibration import calibrate_channel_parameters
from src.analysis.d02_runner import APPROVED_C1_PARAMS, APPROVED_RAW_COLUMNS, EXPECTED_SHA256
from src.analysis.mshkf import FuzzyClusteringEngine, ModifiedSageHusaKalmanFilter
from src.analysis.visualization import (
    generate_d02_2_figures,
    generate_d02_vs_d02_2_comparison_figures,
)
from src.data_io.loader import compute_file_sha256, load_sheet

N_CAL_SPLIT = 300  # First 60% (indices 0:300)
N_TOTAL = 500      # Total sample count


def run_d02_first_pass(
    df_raw: pd.DataFrame,
) -> Tuple[Dict[str, ModifiedSageHusaKalmanFilter], pd.DataFrame]:
    """
    Execute the canonical D02 baseline pass on all 4 raw channels.
    """
    d02_filters = {}
    d02_df = df_raw.copy()

    for ch in APPROVED_RAW_COLUMNS:
        raw_vals = df_raw[ch].to_numpy(dtype=np.float64)
        x0_val = float(raw_vals[0]) + 2.0
        fuzzy_engine = FuzzyClusteringEngine(
            n_clusters=2,
            m=2.0,
            learning_rate=0.05,
            min_pts_support=15,
            feature_dim=3,
        )
        mshkf = ModifiedSageHusaKalmanFilter(
            x0=x0_val,
            P0=1.0,
            Q_regimes=(0.001, 0.010),
            b_regimes=(1.00, 0.98),
            r0=0.0,
            R0=1.0,
            fuzzy_engine=fuzzy_engine,
        )
        filt_vals = np.array([mshkf.step(z) for z in raw_vals], dtype=np.float64)
        d02_filters[ch] = mshkf
        d02_df[f"{ch}_Filtered"] = filt_vals

    return d02_filters, d02_df


def run_d02_2_pipeline(
    input_file: str,
    sheet_name: str = "Sheet1",
    output_csv_path: Optional[str] = None,
    output_json_path: Optional[str] = None,
    figures_dir: Optional[str] = None,
    comparison_figures_dir: Optional[str] = None,
    n_cal: int = N_CAL_SPLIT,
) -> Dict[str, Any]:
    """
    Execute the complete D02.2 Empirical Parameter Calibration and Filtering Pipeline.
    """
    if output_csv_path is None:
        output_csv_path = os.path.join(project_root, "results", "dummy", "d02_2_mshkf_filtered.csv")
    if output_json_path is None:
        output_json_path = os.path.join(project_root, "results", "dummy", "d02_2_mshkf_results.json")
    if figures_dir is None:
        figures_dir = os.path.join(project_root, "results", "dummy", "figures", "d02_2")
    if comparison_figures_dir is None:
        comparison_figures_dir = os.path.join(project_root, "results", "dummy", "figures", "d02_vs_d02_2")

    # 1. Verify input dataset integrity
    actual_sha256 = compute_file_sha256(input_file)
    if actual_sha256 != EXPECTED_SHA256:
        raise ValueError(f"Input file SHA-256 mismatch! Expected {EXPECTED_SHA256}, got {actual_sha256}")

    # 2. Load strictly approved raw channels
    df_raw = load_sheet(input_file, sheet_name=sheet_name, usecols=APPROVED_RAW_COLUMNS)
    n_samples = len(df_raw)
    if n_samples != N_TOTAL:
        raise ValueError(f"Expected {N_TOTAL} samples, got {n_samples}")

    # 3. Execute D02 baseline pass
    d02_filters, d02_df = run_d02_first_pass(df_raw)

    # 4. Perform per-signal calibration on calibration prefix (0:n_cal)
    calibration_results = {}
    calibrated_params_summary = {}

    for ch in APPROVED_RAW_COLUMNS:
        raw_cal = df_raw[ch].to_numpy(dtype=np.float64)[:n_cal]
        d02_hist_cal = d02_filters[ch].history[:n_cal]

        cal_res = calibrate_channel_parameters(raw_cal, d02_hist_cal)
        calibration_results[ch] = cal_res

        calibrated_params_summary[ch] = {
            "x0": cal_res["x0"],
            "P0": cal_res["P0"],
            "r0": cal_res["r0"],
            "R0": cal_res["R0"],
            "Q_stable": cal_res["Q_stable"],
            "Q_dynamic": cal_res["Q_dynamic"],
            "b_stable": cal_res["b_stable"],
            "b_dynamic": cal_res["b_dynamic"],
            "tuning_rmse_vs_xref": cal_res["tuning_rmse_vs_xref"],
            "n_s_transitions": cal_res["n_s_transitions"],
            "n_d_transitions": cal_res["n_d_transitions"],
        }

    # 5. Execute D02.2 AKF filtering over all 500 samples with calibrated parameters
    out_df = df_raw.copy()
    for ch in APPROVED_RAW_COLUMNS:
        out_df[f"{ch}_D02_Filtered"] = d02_df[f"{ch}_Filtered"]

    d02_2_filters = {}
    channel_stats_full = {}
    channel_stats_eval = {}
    diagnostics = {}
    fuzzy_diagnostics = {}

    for ch in APPROVED_RAW_COLUMNS:
        raw_vals = df_raw[ch].to_numpy(dtype=np.float64)
        p = calibration_results[ch]

        fuzzy_engine = FuzzyClusteringEngine(
            n_clusters=2,
            m=2.0,
            learning_rate=0.05,
            min_pts_support=15,
            feature_dim=3,
        )

        mshkf_d02_2 = ModifiedSageHusaKalmanFilter(
            x0=p["x0"],
            P0=p["P0"],
            Q_regimes=(p["Q_stable"], p["Q_dynamic"]),
            b_regimes=(p["b_stable"], p["b_dynamic"]),
            r0=p["r0"],
            R0=p["R0"],
            fuzzy_engine=fuzzy_engine,
        )

        filt_vals = np.array([mshkf_d02_2.step(z) for z in raw_vals], dtype=np.float64)
        filt_col = f"{ch}_Filtered"
        out_df[filt_col] = filt_vals
        d02_2_filters[ch] = mshkf_d02_2

        # Verification per channel
        if len(filt_vals) != n_samples:
            raise ValueError(f"Channel {ch} filtered output length mismatch!")
        if np.isnan(filt_vals).any() or np.isinf(filt_vals).any():
            raise ValueError(f"Channel {ch} contains NaN or Inf values!")

        history = mshkf_d02_2.history
        min_R = min(h["R"] for h in history)
        max_R = max(h["R"] for h in history)
        final_R = history[-1]["R"]
        min_S = min(h["S_k"] for h in history)
        min_P = min(h["P"] for h in history)
        neg_R_count = sum(1 for h in history if h["R"] < 0)

        # Finite and non-negative covariance validation
        if neg_R_count > 0 or min_R < 0 or min_S <= 0 or min_P <= 0:
            raise ValueError(f"Covariance validation failed for Channel {ch}: min_R={min_R}, min_S={min_S}, min_P={min_P}")

        # Full-trace variance statistics
        raw_var_full = float(np.var(raw_vals))
        filt_var_full = float(np.var(filt_vals))
        var_red_full = float((raw_var_full - filt_var_full) / raw_var_full * 100.0) if raw_var_full > 0 else 0.0

        channel_stats_full[ch] = {
            "raw_mean": float(np.mean(raw_vals)),
            "raw_variance": raw_var_full,
            "filtered_mean": float(np.mean(filt_vals)),
            "filtered_variance": filt_var_full,
            "variance_reduction_percent": var_red_full,
        }

        # Held-out evaluation set variance statistics (indices 300:500)
        raw_eval = raw_vals[n_cal:]
        filt_eval = filt_vals[n_cal:]
        raw_var_eval = float(np.var(raw_eval))
        filt_var_eval = float(np.var(filt_eval))
        var_red_eval = float((raw_var_eval - filt_var_eval) / raw_var_eval * 100.0) if raw_var_eval > 0 else 0.0

        channel_stats_eval[ch] = {
            "raw_mean": float(np.mean(raw_eval)),
            "raw_variance": raw_var_eval,
            "filtered_mean": float(np.mean(filt_eval)),
            "filtered_variance": filt_var_eval,
            "variance_reduction_percent": var_red_eval,
        }

        diagnostics[ch] = {
            "min_R": float(min_R),
            "max_R": float(max_R),
            "final_R": float(final_R),
            "min_S": float(min_S),
            "min_P": float(min_P),
            "negative_R_count": neg_R_count,
            "final_noise_mean_r": float(history[-1]["r"]),
        }

        cluster_counts = {0: 0, 1: 0}
        for h in history:
            cluster_counts[h["cluster"]] += 1

        partition_coef = fuzzy_engine.compute_partition_coefficient()
        fuzzy_diagnostics[ch] = {
            "cluster_0_samples": cluster_counts[0],
            "cluster_1_samples": cluster_counts[1],
            "final_cluster_centers": fuzzy_engine.v.tolist(),
            "final_cluster_radii": fuzzy_engine.r_radius.tolist(),
            "partition_coefficient_PC": float(partition_coef),
        }

    # 6. Compute Pearson Correlations (Full 500 and Held-out 200)
    pairs: List[Tuple[str, str]] = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    correlations_full = {}
    correlations_eval = {}

    for col_a, col_b in pairs:
        pair_key = f"{col_a} vs {col_b}"

        # Full 500
        raw_res_full = compute_pearson_correlation(df_raw[col_a].to_numpy(), df_raw[col_b].to_numpy())
        d02_res_full = compute_pearson_correlation(d02_df[f"{col_a}_Filtered"].to_numpy(), d02_df[f"{col_b}_Filtered"].to_numpy())
        d02_2_res_full = compute_pearson_correlation(out_df[f"{col_a}_Filtered"].to_numpy(), out_df[f"{col_b}_Filtered"].to_numpy())

        correlations_full[pair_key] = {
            "raw_r": raw_res_full["r"],
            "d02_r": d02_res_full["r"],
            "d02_2_r": d02_2_res_full["r"],
            "delta_r_vs_raw": d02_2_res_full["r"] - raw_res_full["r"],
            "delta_r_vs_d02": d02_2_res_full["r"] - d02_res_full["r"],
            "n": raw_res_full["n"],
        }

        # Held-out 200 (indices 300:500)
        raw_res_eval = compute_pearson_correlation(df_raw[col_a].to_numpy()[n_cal:], df_raw[col_b].to_numpy()[n_cal:])
        d02_res_eval = compute_pearson_correlation(d02_df[f"{col_a}_Filtered"].to_numpy()[n_cal:], d02_df[f"{col_b}_Filtered"].to_numpy()[n_cal:])
        d02_2_res_eval = compute_pearson_correlation(out_df[f"{col_a}_Filtered"].to_numpy()[n_cal:], out_df[f"{col_b}_Filtered"].to_numpy()[n_cal:])

        correlations_eval[pair_key] = {
            "raw_r": raw_res_eval["r"],
            "d02_r": d02_res_eval["r"],
            "d02_2_r": d02_2_res_eval["r"],
            "delta_r_vs_raw": d02_2_res_eval["r"] - raw_res_eval["r"],
            "delta_r_vs_d02": d02_2_res_eval["r"] - d02_res_eval["r"],
            "n": raw_res_eval["n"],
        }

    # 7. Generate Figures
    raw_corr_dict = {p: {"r": correlations_full[p]["raw_r"], "n": 500} for p in correlations_full}
    d02_corr_dict = {p: {"r": correlations_full[p]["d02_r"], "n": 500} for p in correlations_full}
    d02_2_corr_dict = {p: {"r": correlations_full[p]["d02_2_r"], "n": 500} for p in correlations_full}

    figure_paths = generate_d02_2_figures(
        out_df,
        APPROVED_RAW_COLUMNS,
        raw_corr_dict,
        d02_2_corr_dict,
        figures_dir,
        filter_objects=d02_2_filters,
        n_cal=n_cal,
        d02_correlations=d02_corr_dict,
    )

    comparison_figure_paths = generate_d02_vs_d02_2_comparison_figures(
        df_raw,
        d02_df,
        out_df,
        APPROVED_RAW_COLUMNS,
        raw_corr_dict,
        d02_corr_dict,
        d02_2_corr_dict,
        comparison_figures_dir,
    )

    # 8. Structure JSON payload
    results_payload = {
        "milestone": "D02.2",
        "algorithm": "Adaptive Kalman Filter (AKF) with Empirical Per-Signal Parameter Calibration",
        "description": "Milestone D02.2 empirical per-signal calibration over temporal prefix (k=0..299, 60%) and held-out evaluation (k=300..499, 40%).",
        "input_dataset": {
            "path": input_file,
            "sheet_name": sheet_name,
            "sha256": actual_sha256,
            "sample_count": n_samples,
        },
        "calibration_configuration": {
            "n_cal": n_cal,
            "n_eval": n_samples - n_cal,
            "split_ratio": "60% Calibration / 40% Held-out Evaluation",
            "reference_construction": "Backward RTS smoother over calibration prefix only (x_ref[N_cal-1] = x_hat[N_cal-1|N_cal-1])",
            "per_signal_calibrated_parameters": calibrated_params_summary,
        },
        "correlation_comparison_full_500": correlations_full,
        "correlation_comparison_held_out_200": correlations_eval,
        "channel_statistics_full_500": channel_stats_full,
        "channel_statistics_held_out_200": channel_stats_eval,
        "filter_diagnostics": diagnostics,
        "fuzzy_clustering_diagnostics": fuzzy_diagnostics,
        "generated_artifacts": {
            "filtered_csv": os.path.abspath(output_csv_path),
            "results_json": os.path.abspath(output_json_path),
            "figures": {k: os.path.abspath(v) for k, v in figure_paths.items()},
            "comparison_figures": {k: os.path.abspath(v) for k, v in comparison_figure_paths.items()},
        },
    }

    # 9. Save CSV (only raw and D02.2 filtered columns to match D02 format)
    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)

    # Prepare export dataframe containing raw and filtered columns
    export_df = pd.DataFrame()
    for ch in APPROVED_RAW_COLUMNS:
        export_df[ch] = df_raw[ch]
    for ch in APPROVED_RAW_COLUMNS:
        export_df[f"{ch}_Filtered"] = out_df[f"{ch}_Filtered"]

    export_df.to_csv(output_csv_path, index=False)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=4)

    return results_payload


if __name__ == "__main__":
    dataset_path = os.path.join(project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx")
    res = run_d02_2_pipeline(dataset_path)
    print("D02.2 Pipeline Execution Complete.")
    print("Calibrated Parameters:")
    print(json.dumps(res["calibration_configuration"]["per_signal_calibrated_parameters"], indent=2))
    print("\nFull 500 Correlations:")
    print(json.dumps(res["correlation_comparison_full_500"], indent=2))
    print("\nHeld-out 200 Correlations:")
    print(json.dumps(res["correlation_comparison_held_out_200"], indent=2))
