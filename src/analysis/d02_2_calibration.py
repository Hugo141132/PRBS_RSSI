"""
d02_2_calibration.py

Milestone D02.2: Empirical Parameter Calibration Module for Adaptive Kalman Filter (AKF).
Computes independent, data-driven parameters (x0, P0, r0, R0, Q_stable, Q_dynamic, b_stable, b_dynamic)
per RSSI channel using backward Rauch-Tung-Striebel (RTS) reference state reconstruction
over a deterministic temporal calibration prefix (first 60% of samples, k=0..299).
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.analysis.mshkf import FuzzyClusteringEngine, ModifiedSageHusaKalmanFilter


def compute_rts_reference_state(
    x_hat: np.ndarray,
    P: np.ndarray,
    Q_ref: np.ndarray,
) -> np.ndarray:
    """
    Construct backward Rauch-Tung-Striebel (RTS) reference state trajectory.

    Backward recursion:
        x_ref[N-1] = x_hat[N-1|N-1]
        x_ref[k] = x_hat[k|k] + (P[k|k] / (P[k|k] + Q_ref[k])) * (x_ref[k+1] - x_hat[k|k])
        for k = N-2 down to 0.

    Args:
        x_hat: 1D array of posterior state estimates x_hat[k|k].
        P: 1D array of posterior error covariances P[k|k].
        Q_ref: 1D array of first-pass effective process noise covariances Q_k.

    Returns:
        1D array x_ref of smoothed reference states.
    """
    n = len(x_hat)
    if n == 0:
        raise ValueError("Cannot compute reference state for empty trajectory.")
    if len(P) != n or len(Q_ref) != n:
        raise ValueError(f"Array length mismatch: x_hat={n}, P={len(P)}, Q_ref={len(Q_ref)}")

    x_ref = np.zeros(n, dtype=np.float64)
    x_ref[-1] = float(x_hat[-1])

    for k in range(n - 2, -1, -1):
        p_k = float(P[k])
        q_k = float(Q_ref[k])
        denom = p_k + q_k
        smoother_gain = p_k / denom if denom > 0.0 else 0.0
        x_ref[k] = float(x_hat[k]) + smoother_gain * (x_ref[k + 1] - float(x_hat[k]))

    return x_ref


def calibrate_channel_parameters(
    raw_z_cal: np.ndarray,
    d02_history_cal: List[Dict[str, Any]],
    b_s_candidates: Optional[np.ndarray] = None,
    b_d_candidates: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Calibrate all 8 AKF parameters independently for a single RSSI channel
    using only its calibration prefix data.

    Steps:
    1. x0 = mean(x_cal) where x_cal = x_ref (RTS backward smoothed from D02 first pass)
    2. P0 = sample variance of calibration reference samples
    3. e_k = z_k - h(x_k_ref) with h(x) = x (H = 1)
    4. r0 = mean(e_k)
    5. R0 = sample variance of (e_k - r0)
    6. q_k = x_{k+1}_ref - f(x_k_ref) with f(x) = x (Phi = 1)
       Q_stable = cov(q_k for k in S)
       Q_dynamic = cov(q_k for k in D)
       (Verifies N_S >= 2 and N_D >= 2)
    7. Bounded deterministic grid search for (b_stable, b_dynamic) minimizing RMSE vs x_ref,
       enforcing 0 < b_dynamic < b_stable < 1.

    Args:
        raw_z_cal: 1D array of raw RSSI measurements for the calibration prefix.
        d02_history_cal: List of D02 first-pass history dicts for the calibration prefix.
        b_s_candidates: Optional custom candidate array for b_stable.
        b_d_candidates: Optional custom candidate array for b_dynamic.

    Returns:
        Dict containing all calibrated parameters and diagnostic metadata.
    """
    n_cal = len(raw_z_cal)
    if n_cal < 3:
        raise ValueError(f"Calibration prefix too short (n={n_cal}), minimum required: 3")
    if len(d02_history_cal) != n_cal:
        raise ValueError(f"Length mismatch between raw_z_cal ({n_cal}) and d02_history_cal ({len(d02_history_cal)})")

    # Extract D02 first-pass statistics
    x_hat = np.array([h["x"] for h in d02_history_cal], dtype=np.float64)
    p_arr = np.array([h["P"] for h in d02_history_cal], dtype=np.float64)
    q_ref_arr = np.array([h["Q_eff"] for h in d02_history_cal], dtype=np.float64)
    regimes_arr = np.array([h["cluster"] for h in d02_history_cal], dtype=np.int32)

    # Reference state construction over calibration prefix
    x_ref = compute_rts_reference_state(x_hat, p_arr, q_ref_arr)

    # 1. x0 = mean(x_cal)
    x0 = float(np.mean(x_ref))

    # 2. P0 = sample variance of calibration reference samples (ddof=1)
    P0 = float(np.var(x_ref, ddof=1))
    if P0 < 0.0:
        P0 = 0.0

    # 3. Measurement reference residual e_k = z_k - x_k_ref
    e_k = raw_z_cal - x_ref

    # 4. r0 = mean(e_k)
    r0 = float(np.mean(e_k))

    # 5. R0 = sample variance of (e_k - r0) (ddof=1)
    R0 = float(np.var(e_k - r0, ddof=1))
    if R0 < 0.0:
        R0 = 0.0

    # 6. Process noise transitions q_k = x_{k+1}_ref - x_k_ref
    q_k = x_ref[1:] - x_ref[:-1]
    transition_regimes = regimes_arr[:-1]

    s_mask = (transition_regimes == 0)
    d_mask = (transition_regimes == 1)

    n_s = int(np.sum(s_mask))
    n_d = int(np.sum(d_mask))

    # Mathematical blocker check: verify N_s >= 2 and N_d >= 2
    if n_s < 2:
        raise ValueError(f"Mathematical blocker: Stable regime has N_S = {n_s} < 2 samples. Cannot compute sample covariance.")
    if n_d < 2:
        raise ValueError(f"Mathematical blocker: Dynamic regime has N_D = {n_d} < 2 samples. Cannot compute sample covariance.")

    Q_stable = float(np.var(q_k[s_mask], ddof=1))
    Q_dynamic = float(np.var(q_k[d_mask], ddof=1))

    if Q_stable < 0.0:
        Q_stable = 0.0
    if Q_dynamic < 0.0:
        Q_dynamic = 0.0

    # 7. Grid search for b_stable and b_dynamic
    if b_s_candidates is None:
        b_s_candidates = np.array([0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995, 0.999], dtype=np.float64)
    if b_d_candidates is None:
        b_d_candidates = np.array([0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98], dtype=np.float64)

    best_rmse = float("inf")
    best_bs = float(b_s_candidates[-2])
    best_bd = float(b_d_candidates[len(b_d_candidates) // 2])

    for bs in b_s_candidates:
        for bd in b_d_candidates:
            # Enforce strict ordering 0 < b_dynamic < b_stable < 1
            if bd >= bs - 1e-4:
                continue

            test_fuzzy = FuzzyClusteringEngine(
                n_clusters=2,
                m=2.0,
                learning_rate=0.05,
                min_pts_support=15,
                feature_dim=3,
            )
            test_filter = ModifiedSageHusaKalmanFilter(
                x0=x0,
                P0=P0,
                Q_regimes=(Q_stable, Q_dynamic),
                b_regimes=(float(bs), float(bd)),
                r0=r0,
                R0=R0,
                fuzzy_engine=test_fuzzy,
            )
            x_test = np.array([test_filter.step(z) for z in raw_z_cal], dtype=np.float64)
            rmse = float(np.sqrt(np.mean((x_test - x_ref) ** 2)))

            if rmse < best_rmse:
                best_rmse = rmse
                best_bs = float(bs)
                best_bd = float(bd)

    return {
        "x0": x0,
        "P0": P0,
        "r0": r0,
        "R0": R0,
        "Q_stable": Q_stable,
        "Q_dynamic": Q_dynamic,
        "b_stable": best_bs,
        "b_dynamic": best_bd,
        "n_cal": n_cal,
        "n_s_transitions": n_s,
        "n_d_transitions": n_d,
        "tuning_rmse_vs_xref": best_rmse,
        "candidate_grid": {
            "b_stable": b_s_candidates.tolist(),
            "b_dynamic": b_d_candidates.tolist(),
        },
        "x_ref": x_ref,
    }
