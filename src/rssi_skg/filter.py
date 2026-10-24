"""Modified Sage–Husa Adaptive Kalman Filter (MSHKF) module for RSSI filtering.

Governing Specification:
    PA.pdf Section 3.2.2, Equations (3.10)–(3.20), pages 26–27.

RSSI Modeling Assumptions:
    - Scalar System Model: State X_k represents the true underlying RSSI (in dBm).
      State transition matrix Phi = 1.0 (assuming slowly-varying / static RSSI channel):
          X_k = Phi * X_{k-1} + q_{k-1} + w_{k-1} = X_{k-1} + q_{k-1} + w_{k-1}
      where w_{k-1} ~ N(0, Q) is zero-mean disturbance with fixed variance Q,
      and q_{k-1} is the adaptive process noise mean.
    - Scalar Measurement Model: Observation Z_k is the raw received RSSI (in dBm).
      Measurement matrix H = 1.0 (direct scalar observation):
          Z_k = H * X_k + r_k + v_k = X_k + r_k + v_k
      where v_k ~ N(0, R_k) is zero-mean measurement noise with adaptive variance R_k,
      and r_k is the adaptive measurement noise mean.
    - Adaptation Mode:
      As stated in the final paragraph of PA.pdf Section 3.2.2 (page 27):
      Because the updates of process noise covariance Q_k and measurement noise
      covariance R_k are both driven by the innovation sequence e_k, PA.pdf establishes
      the modeling assumption that process noise covariance Q_k is known (fixed),
      enabling measurement noise covariance R_k to be accurately estimated online.
      Based on this assumption, Q_k is not adaptively estimated alongside R_k, and
      Equation (3.20) for adaptive Q update is consequently not executed in this mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FilterConfig:
    """Configuration parameters for the Modified Sage–Husa Adaptive Kalman Filter.

    Attributes:
        b: Forgetting factor for adaptive noise estimation, selected within the
           PA.pdf Section 3.2.2 range of (0.95, 0.999). Default: 0.99 (dimensionless).
        d0: Initial adaptive weighting coefficient D_0.
            Default: 1.0 (dimensionless, per Eq 3.10).
        q: Fixed process noise covariance Q (software-validation assumption).
           Default: 0.1 (dBm^2, uncalibrated nominal prior).
        r0: Initial measurement noise covariance R_0 (software-validation assumption).
            Default: 1.0 (dBm^2, uncalibrated initial estimate).
        p0: Initial state estimation error covariance P_0 (software-validation assumption).
            Default: 1.0 (dBm^2, uncalibrated initial uncertainty).
        q0: Initial process noise mean q_0 (software-validation assumption).
            Default: 0.0 (dBm, nominal zero initial process drift).
        r0_mean: Initial measurement noise mean r_0 (software-validation assumption).
                 Default: 0.0 (dBm, nominal zero initial measurement bias).
        phi: State transition scalar Phi.
             Default: 1.0 (dimensionless, static RSSI modeling assumption).
        h: Measurement observation scalar H.
           Default: 1.0 (dimensionless, direct RSSI observation assumption).
        x0: Optional explicit initial state prior (in dBm).
            If None (recommended default), x0 is auto-initialized to the first
            observation z[0] of the series without double-counting (updates begin at z[1]).
        r_min: Numerical safeguard floor for measurement noise variance R_k.
               Default: 1e-8 (dBm^2).
        p_min: Numerical safeguard floor for error covariance P_k.
               Default: 0.0 (dBm^2).
    """

    b: float = 0.99
    d0: float = 1.0
    q: float = 0.1
    r0: float = 1.0
    p0: float = 1.0
    q0: float = 0.0
    r0_mean: float = 0.0
    phi: float = 1.0
    h: float = 1.0
    x0: float | None = None
    r_min: float = 1e-8
    p_min: float = 0.0

    def __post_init__(self) -> None:
        """Validate filter configuration bounds."""
        if not (0.0 < self.b < 1.0):
            raise ValueError(f"Forgetting factor b must be in (0, 1), got {self.b}.")
        if self.d0 <= 0.0 or not math.isfinite(self.d0):
            raise ValueError(f"Initial weight d0 must be positive and finite, got {self.d0}.")
        if self.q <= 0.0 or not math.isfinite(self.q):
            raise ValueError(f"Process noise covariance q must be positive and finite, got {self.q}.")
        if self.r0 <= 0.0 or not math.isfinite(self.r0):
            raise ValueError(f"Initial measurement noise covariance r0 must be positive and finite, got {self.r0}.")
        if self.p0 < 0.0 or not math.isfinite(self.p0):
            raise ValueError(f"Initial error covariance p0 must be non-negative and finite, got {self.p0}.")
        if not math.isfinite(self.q0):
            raise ValueError(f"Initial process noise mean q0 must be finite, got {self.q0}.")
        if not math.isfinite(self.r0_mean):
            raise ValueError(f"Initial measurement noise mean r0_mean must be finite, got {self.r0_mean}.")
        if self.phi == 0.0 or not math.isfinite(self.phi):
            raise ValueError(f"Phi must be non-zero and finite, got {self.phi}.")
        if self.h == 0.0 or not math.isfinite(self.h):
            raise ValueError(f"H must be non-zero and finite, got {self.h}.")
        if self.x0 is not None and not math.isfinite(self.x0):
            raise ValueError(f"Explicit x0 must be finite, got {self.x0}.")
        if self.r_min <= 0.0 or not math.isfinite(self.r_min):
            raise ValueError(f"r_min must be positive and finite, got {self.r_min}.")
        if self.p_min < 0.0 or not math.isfinite(self.p_min):
            raise ValueError(f"p_min must be non-negative and finite, got {self.p_min}.")

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert configuration to comprehensive metadata documentation dictionary."""
        return {
            "specification": "PA.pdf Section 3.2.2, Equations (3.10)–(3.20)",
            "algorithm": "Modified Sage–Husa Adaptive Kalman Filter (Scalar MSHKF)",
            "adaptation_mode": "Fixed Q, Adaptive R, Adaptive q and r noise means",
            "modeling_assumptions": {
                "phi": {
                    "value": self.phi,
                    "units": "dimensionless",
                    "rationale": "State transition scalar for static/slowly-varying RSSI channels (Phi = 1.0).",
                },
                "h": {
                    "value": self.h,
                    "units": "dimensionless",
                    "rationale": "Measurement observation scalar for direct RSSI observation (H = 1.0).",
                },
                "omission_of_adaptive_q_update": (
                    "Following the stated assumption in PA.pdf Section 3.2.2 (page 27), because both process noise "
                    "covariance Q and measurement noise covariance R updates are driven by the innovation sequence, "
                    "process noise covariance Q is assumed known (fixed software-validation prior of 0.1 dBm^2) "
                    "so that measurement noise covariance R can be accurately estimated online without executing Equation (3.20)."
                ),
                "sample_indexing_policy": (
                    "When x0 is auto-initialized from the first observation (x0 = z[0]), the recursive update begins at "
                    "observation index 1 (k=1) using measurement z[1]. Output index 0 retains x0 = z[0]. This strictly avoids "
                    "double-counting z[0] as both the initial state and an innovation measurement. If an explicit x0 prior "
                    "is provided, recursive updates begin at observation index 0 (k=1) with z[0] as measurement Z_1."
                ),
            },
            "parameters": {
                "x0": {
                    "value": "auto (z[0])" if self.x0 is None else self.x0,
                    "units": "dBm",
                    "category": "Implementation Assumption",
                    "rationale": "Initial state estimate. Initializing to z[0] sets the baseline directly from the first sample without transient settling bias.",
                },
                "P0": {
                    "value": self.p0,
                    "units": "dBm^2",
                    "category": "Software-Validation Assumption",
                    "rationale": "Uncalibrated initial error covariance representing initial state uncertainty for software validation.",
                },
                "q0": {
                    "value": self.q0,
                    "units": "dBm",
                    "category": "Software-Validation Assumption",
                    "rationale": "Uncalibrated initial process noise mean, assuming zero initial drift.",
                },
                "r0": {
                    "value": self.r0_mean,
                    "units": "dBm",
                    "category": "Software-Validation Assumption",
                    "rationale": "Uncalibrated initial measurement noise mean, assuming zero initial measurement error.",
                },
                "Q": {
                    "value": self.q,
                    "units": "dBm^2",
                    "category": "Software-Validation Assumption",
                    "rationale": "Uncalibrated fixed process noise covariance assumed known per PA.pdf Section 3.2.2.",
                },
                "R0": {
                    "value": self.r0,
                    "units": "dBm^2",
                    "category": "Software-Validation Assumption",
                    "rationale": "Uncalibrated initial measurement noise covariance prior for online adaptation.",
                },
                "b": {
                    "value": self.b,
                    "units": "dimensionless",
                    "category": "Selected Value within Literature Range",
                    "rationale": "Forgetting factor selected within PA.pdf Section 3.2.2 range of (0.95, 0.999). Controls adaptive memory window ~100 samples.",
                },
                "D0": {
                    "value": self.d0,
                    "units": "dimensionless",
                    "category": "Explicit Specification",
                    "rationale": "Initial adaptive weighting factor according to PA.pdf Eq (3.10).",
                },
            },
            "numerical_safeguards": {
                "r_min": self.r_min,
                "p_min": self.p_min,
                "input_validation": "Strict validation rejecting NaN, +Inf, -Inf, and non-numeric entries.",
                "covariance_constraints": "Guards against non-positive innovation denominator, negative variances, and non-finite results (raises FloatingPointError).",
            },
        }


@dataclass
class FilterStepRecord:
    """Snapshot of intermediate calculation variables at filter step k."""

    k: int
    z: float
    d_k: float
    x_pred: float
    p_pred: float
    r_k: float
    e_k: float
    r_cov_k: float
    k_gain: float
    x_est: float
    p_est: float
    q_k: float


class ModifiedSageHusaFilter:
    """Scalar Modified Sage–Husa Adaptive Kalman Filter (MSHKF).

    Implements PA.pdf Section 3.2.2, Equations (3.10)–(3.19).
    """

    def __init__(self, config: FilterConfig | None = None) -> None:
        """Initialize filter with configuration.

        Args:
            config: FilterConfig instance or None for default parameters.
        """
        self.config = config if config is not None else FilterConfig()
        self._is_initialized = False

        # State variables
        self.k: int = 0
        self.x_est: float = 0.0
        self.p_est: float = self.config.p0
        self.q_est: float = self.config.q0
        self.r_est: float = self.config.r0_mean
        self.r_cov: float = self.config.r0
        self.d_val: float = self.config.d0

    def initialize_state(self, initial_x: float) -> None:
        """Initialize filter state at k=0.

        Args:
            initial_x: Initial state estimate x_0 (in dBm).
        """
        if not math.isfinite(initial_x):
            raise ValueError(f"initial_x must be finite, got {initial_x}.")

        self.k = 0
        self.x_est = float(initial_x)
        self.p_est = float(self.config.p0)
        self.q_est = float(self.config.q0)
        self.r_est = float(self.config.r0_mean)
        self.r_cov = float(self.config.r0)
        self.d_val = float(self.config.d0)
        self._is_initialized = True

    def step(self, z: float) -> tuple[float, FilterStepRecord]:
        """Execute one recursive filtering step given observation Z_k.

        Governing Equations:
            (3.10) D_k = D_{k-1} / (D_{k-1} + b)
            (3.11) X_pred = Phi * X_{k-1} + q_{k-1}
            (3.12) P_pred = Phi * P_{k-1} * Phi^T + Q
            (3.13) r_k = (1 - D_k) * r_{k-1} + D_k * (Z_k - H * X_pred)
            (3.14) e_k = Z_k - H * X_pred - r_k
            (3.15) R_k = (1 - D_k) * R_{k-1} + D_k * e_k^2
            (3.16) K_k = P_pred * H^T / (H * P_pred * H^T + R_k)
            (3.17) X_k = X_pred + K_k * e_k
            (3.18) P_k = (1 - K_k * H) * P_pred
            (3.19) q_k = (1 - D_k) * q_{k-1} + D_k * (X_k - Phi * X_{k-1})

        Args:
            z: Observed measurement Z_k.

        Returns:
            tuple[float, FilterStepRecord]: Updated state estimate X_k and detailed record.

        Raises:
            RuntimeError: If filter state has not been initialized.
            ValueError: If observation z is non-finite.
            FloatingPointError: If numerical breakdown or non-finite covariance occurs.
        """
        if not self._is_initialized:
            raise RuntimeError("Filter state has not been initialized. Call initialize_state() first.")

        if not math.isfinite(z):
            raise ValueError(f"Measurement z at step {self.k + 1} must be finite, got {z}.")

        self.k += 1
        cfg = self.config

        # 1. Adaptive weight update (Eq 3.10)
        denom_d = self.d_val + cfg.b
        if denom_d <= 0.0 or not math.isfinite(denom_d):
            raise FloatingPointError(f"Numerical error in D_k denominator at step {self.k}: {denom_d}.")
        d_k = self.d_val / denom_d
        one_minus_d = 1.0 - d_k

        # 2. State prediction (Eq 3.11, with Phi=1)
        x_pred = cfg.phi * self.x_est + self.q_est
        if not math.isfinite(x_pred):
            raise FloatingPointError(f"Predicted state non-finite at step {self.k}: {x_pred}.")

        # 3. Covariance prediction (Eq 3.12, with Phi=1 and fixed Q)
        p_pred = (cfg.phi ** 2) * self.p_est + cfg.q
        if not math.isfinite(p_pred) or p_pred < 0.0:
            raise FloatingPointError(f"Predicted covariance non-finite or negative at step {self.k}: {p_pred}.")

        # 4. Measurement noise mean update (Eq 3.13, with H=1)
        meas_residual = z - cfg.h * x_pred
        r_k = one_minus_d * self.r_est + d_k * meas_residual
        if not math.isfinite(r_k):
            raise FloatingPointError(f"Measurement noise mean r_k non-finite at step {self.k}: {r_k}.")

        # 5. Innovation calculation using updated r_k (Eq 3.14, with H=1)
        e_k = z - cfg.h * x_pred - r_k
        if not math.isfinite(e_k):
            raise FloatingPointError(f"Innovation e_k non-finite at step {self.k}: {e_k}.")

        # 6. Measurement noise covariance update (Eq 3.15, modified form omitting -H P H^T)
        r_cov_k = one_minus_d * self.r_cov + d_k * (e_k ** 2)
        if not math.isfinite(r_cov_k) or r_cov_k < 0.0:
            raise FloatingPointError(
                f"Measurement noise covariance R_k became non-finite or negative at step {self.k}: {r_cov_k}."
            )
        if r_cov_k < cfg.r_min:
            r_cov_k = cfg.r_min

        # 7. Kalman gain calculation (Eq 3.16, with H=1)
        denom_k = (cfg.h ** 2) * p_pred + r_cov_k
        if denom_k <= 0.0 or not math.isfinite(denom_k):
            raise FloatingPointError(
                f"Numerical singularity in Kalman gain denominator at step {self.k}: {denom_k}."
            )
        k_gain = (p_pred * cfg.h) / denom_k
        if not math.isfinite(k_gain):
            raise FloatingPointError(f"Kalman gain non-finite at step {self.k}: {k_gain}.")

        # 8. State estimate update (Eq 3.17)
        x_k = x_pred + k_gain * e_k
        if not math.isfinite(x_k):
            raise FloatingPointError(f"State estimate X_k non-finite at step {self.k}: {x_k}.")

        # 9. Error covariance update (Eq 3.18, with H=1)
        p_k = (1.0 - k_gain * cfg.h) * p_pred
        if not math.isfinite(p_k) or p_k < -1e-9:
            raise FloatingPointError(
                f"Error covariance P_k became non-finite or significantly negative at step {self.k}: {p_k}."
            )
        if p_k < cfg.p_min:
            p_k = cfg.p_min

        # 10. Process noise mean update (Eq 3.19, with Phi=1)
        q_k = one_minus_d * self.q_est + d_k * (x_k - cfg.phi * self.x_est)
        if not math.isfinite(q_k):
            raise FloatingPointError(f"Process noise mean q_k non-finite at step {self.k}: {q_k}.")

        record = FilterStepRecord(
            k=self.k,
            z=z,
            d_k=d_k,
            x_pred=x_pred,
            p_pred=p_pred,
            r_k=r_k,
            e_k=e_k,
            r_cov_k=r_cov_k,
            k_gain=k_gain,
            x_est=x_k,
            p_est=p_k,
            q_k=q_k,
        )

        # Update persistent state for next iteration
        self.d_val = d_k
        self.x_est = x_k
        self.p_est = p_k
        self.q_est = q_k
        self.r_est = r_k
        self.r_cov = r_cov_k

        return x_k, record

    def filter_series(
        self,
        series: Sequence[float | int],
        initial_x: float | None = None,
    ) -> list[float]:
        """Filter an entire sequence of scalar RSSI measurements.

        Sample Indexing Policy (avoiding double-counting):
        - If initial_x (or config.x0) is None:
          The initial state x_0 is initialized to the first observation z[0].
          Output[0] = z[0].
          The recursive update loop (Equations 3.10-3.19) executes for observations
          z[1], z[2], ..., z[N-1] at steps k = 1, 2, ..., N-1.
          Observation z[0] is used solely as the initial state estimate at time 0,
          and is never fed as an innovation measurement into the filter equations.
          Every sample is used exactly once; no double-counting occurs.
        - If an explicit initial_x is provided:
          The initial state x_0 is set to the provided prior.
          The recursive update loop executes for ALL observations z[0], z[1], ..., z[N-1]
          at steps k = 1, 2, ..., N. Output[i] = X_{i+1}.
          Measurement z[0] is processed as measurement Z_1, avoiding double-counting.

        Args:
            series: Sequence of numeric RSSI observations.
            initial_x: Optional override for initial state prior x_0.

        Returns:
            list[float]: Filtered RSSI series of identical length N, in float64 precision.

        Raises:
            ValueError: If series has fewer than 2 samples or contains non-numeric / non-finite values.
        """
        n = len(series)
        if n < 2:
            raise ValueError(f"Series must contain at least 2 samples, got {n}.")

        # Convert to float64 and validate finite numeric values
        float_series: list[float] = []
        for idx, val in enumerate(series):
            try:
                f_val = float(val)
            except (TypeError, ValueError) as err:
                raise ValueError(
                    f"Invalid non-numeric value {val!r} at index {idx} (sample {idx + 1})."
                ) from err

            if not math.isfinite(f_val):
                raise ValueError(
                    f"Non-finite value ({f_val}) at index {idx} (sample {idx + 1})."
                )
            float_series.append(f_val)

        init_val = initial_x if initial_x is not None else self.config.x0

        filtered: list[float] = [0.0] * n

        if init_val is None:
            # Policy A: Auto-initialize from first sample; update begins at sample 1
            first_obs = float_series[0]
            self.initialize_state(first_obs)
            filtered[0] = first_obs

            for i in range(1, n):
                x_filt, _ = self.step(float_series[i])
                filtered[i] = x_filt
        else:
            # Policy B: Explicit prior provided; update begins at sample 0
            self.initialize_state(init_val)
            for i in range(n):
                x_filt, _ = self.step(float_series[i])
                filtered[i] = x_filt

        return filtered


def filter_rssi_channels(
    data: Mapping[str, Sequence[float | int]],
    config: FilterConfig | None = None,
) -> dict[str, list[float]]:
    """Filter multiple RSSI channels independently using separate filter states.

    Enforces strict channel isolation:
    Each channel is filtered with its own instance of ModifiedSageHusaFilter,
    ensuring that calculations on one channel (e.g. Alice) cannot affect or leak
    state into any other channel (e.g. Bob or Eve1-Alice).

    Args:
        data: Mapping from channel name to raw RSSI sequence.
        config: FilterConfig instance or None for default configuration.

    Returns:
        dict[str, list[float]]: Dictionary mapping each channel to its filtered series,
            preserving exact row alignment and sample count.

    Raises:
        ValueError: If data is empty or if any channel has unequal lengths or invalid data.
    """
    if not data:
        raise ValueError("Data dictionary cannot be empty.")

    cfg = config if config is not None else FilterConfig()
    filtered_data: dict[str, list[float]] = {}

    expected_len: int | None = None

    for col_name, raw_series in data.items():
        if expected_len is None:
            expected_len = len(raw_series)
        elif len(raw_series) != expected_len:
            raise ValueError(
                f"Channel '{col_name}' has length {len(raw_series)}, expected {expected_len}."
            )

        # Independent filter instance per channel enforces channel isolation
        channel_filter = ModifiedSageHusaFilter(config=cfg)
        filtered_data[col_name] = channel_filter.filter_series(raw_series)

    return filtered_data
