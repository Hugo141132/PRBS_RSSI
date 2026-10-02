"""
mshkf.py

Modified Sage-Husa Adaptive Kalman Filter (MSHAKF) for RSSI Preprocessing
based on:
Wang et al. (2022), "A modified Sage-Husa adaptive Kalman filter for state
estimation of electric vehicle servo control system", Energy Reports 8, 20-27.

Theoretical Foundations (Wang et al. Eqs. 1-7, 26, 27):
1. Scalar State-Space Model for RSSI Channel:
   - State equation:       x_k = Phi * x_{k-1} + w_k,  Phi = 1, w_k ~ N(q, Q)
   - Observation equation: z_k = H * x_k + v_k,        H = 1,   v_k ~ N(r_k, R_k)
   - For stationary physical channel, process noise mean q = 0.

2. Recursive Adaptive Kalman Filtering Cycle:
   - State prediction (Eq. 1):              x_pred = x_{k-1} + q
   - Covariance prediction (Eq. 2):         P_pred = P_{k-1} + Q
   - Innovation (Eq. 3):                    eps_k  = z_k - x_pred - r_{k-1}  (prior noise mean r_{k-1})
   - Innovation covariance (Eq. 4):         S_k    = P_pred + R_{k-1}        (prior noise covariance R_{k-1})
   - Kalman gain (Eq. 5):                   K_k    = P_pred / S_k
   - Posterior state update (Eq. 6):        x_k    = x_pred + K_k * eps_k
   - Posterior covariance update (Eq. 7):   P_k    = (1 - K_k) * P_pred

3. Adaptive Online Measurement Noise Estimation:
   - Fading factor (Wang et al.):           d_{k-1}= (1 - b) / (1 - b^k),
                                            with analytical limit d_{k-1} = 1/k when b = 1.0.
   - Adaptive noise mean update (Eq. 26):   r_k    = (1 - d_{k-1}) * r_{k-1} + d_{k-1} * (z_k - x_pred)
   - Adaptive noise cov update (Eq. 27):    R_k    = (1 - d_{k-1}) * R_{k-1} + d_{k-1} * (eps_k^2 - P_pred)
"""

from typing import Any, Dict, List, Optional
import numpy as np


class ModifiedSageHusaKalmanFilter:
    """
    Modified Sage-Husa Adaptive Kalman Filter (MSHAKF) for scalar RSSI tracking based on Wang et al. (2022).

    Provides recursive online estimation of the time-varying measurement noise mean (r_k)
    and measurement noise covariance (R_k) using exponential fading memory.
    """

    def __init__(
        self,
        x0: float,
        P0: float = 1.0,
        Q: float = 0.001,
        b: float = 0.98,
        r0: float = 0.0,
        R0: float = 1.0,
        q: float = 0.0,
    ) -> None:
        """
        Initialize the Modified Sage-Husa Adaptive Kalman Filter.

        Args:
            x0: Initial state estimate prior (dBm).
            P0: Initial error covariance prior (default: 1.0).
            Q: Process noise covariance prior (default: 0.001).
            b: Fading / forgetting factor in range (0, 1] (default: 0.98).
            r0: Initial measurement noise mean prior (Wang Eq. 26, default: 0.0).
            R0: Initial measurement noise covariance prior (Wang Eq. 27, default: 1.0).
            q: Process noise mean prior (default: 0.0 for stationary channel).
        """
        self.x = float(x0)
        self.P = float(P0)
        self.Q = float(Q)
        self.b = float(b)
        self.r = float(r0)
        self.R = float(R0)
        self.q = float(q)
        self.k = 1  # 1-indexed discrete time step counter

        self.history: List[Dict[str, Any]] = []

    def compute_fading_factor(self, k: int) -> float:
        """
        Compute weighting factor d_{k-1} = (1 - b) / (1 - b^k).
        Applies L'Hopital analytical limit d_{k-1} = 1/k when b = 1.0.
        """
        if abs(self.b - 1.0) < 1e-12:
            return 1.0 / float(k)
        return float((1.0 - self.b) / (1.0 - (self.b ** k)))

    def step(self, z: float) -> float:
        """
        Execute one causal step of the complete MSHAKF recursion on incoming raw RSSI measurement z.

        Equations:
            1. State Prediction:              x_pred = x_{k-1} + q
            2. Covariance Prediction:         P_pred = P_{k-1} + Q
            3. Innovation:                    eps_k  = z_k - x_pred - r_{k-1}
            4. Innovation Covariance:         S_k    = P_pred + R_{k-1}
            5. Kalman Gain:                   K_k    = P_pred / S_k
            6. State Update:                  x_k    = x_pred + K_k * eps_k
            7. Covariance Update:             P_k    = (1 - K_k) * P_pred
            8. Adaptive Noise Mean Update:    r_k    = (1 - d_{k-1}) * r_{k-1} + d_{k-1} * (z_k - x_pred)
            9. Adaptive Noise Cov Update:     R_k    = (1 - d_{k-1}) * R_{k-1} + d_{k-1} * (eps_k^2 - P_pred)

        Args:
            z: Instantaneous raw RSSI measurement.

        Returns:
            The posterior filtered RSSI state estimate x_k.
        """
        z_val = float(z)

        # Fading factor d_{k-1}
        d_k_minus_1 = self.compute_fading_factor(self.k)

        # 1. State Prediction (Wang Eq. 1: Phi=1)
        x_pred = self.x + self.q

        # 2. Error Covariance Prediction (Wang Eq. 2: Phi=1)
        P_pred = self.P + self.Q

        # 3. Measurement Innovation using prior noise mean r_{k-1} (Wang Eq. 3)
        eps_k = z_val - x_pred - self.r

        # 4. Innovation Covariance using prior noise covariance R_{k-1} (Wang Eq. 4)
        S_k = P_pred + self.R

        # 5. Kalman Gain (Wang Eq. 5)
        K_k = P_pred / S_k if S_k != 0.0 else 0.0

        # 6. Posterior State Update (Wang Eq. 6)
        self.x = x_pred + K_k * eps_k

        # 7. Posterior Error Covariance Update (Wang Eq. 7)
        self.P = (1.0 - K_k) * P_pred

        # 8. Online Measurement Noise Mean Update (Wang Eq. 26)
        self.r = (1.0 - d_k_minus_1) * self.r + d_k_minus_1 * (z_val - x_pred)

        # 9. Online Measurement Noise Covariance Update (Wang Eq. 27)
        self.R = (1.0 - d_k_minus_1) * self.R + d_k_minus_1 * (eps_k**2 - P_pred)

        # Record diagnostics
        self.history.append({
            "k": self.k,
            "z": z_val,
            "x_pred": x_pred,
            "P_pred": P_pred,
            "eps_k": eps_k,
            "S_k": S_k,
            "K_k": K_k,
            "x": self.x,
            "P": self.P,
            "r": self.r,
            "R": self.R,
            "Q": self.Q,
            "b": self.b,
            "d_k_minus_1": d_k_minus_1,
        })

        self.k += 1
        return self.x
