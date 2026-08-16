"""
akf.py

Implementation of the Adaptive Kalman Filter (AKF) based on the Sage-Husa
estimator for RSSI filtering.

Mathematical Source Specifications:
1. Core Kalman Filter: PPA.pdf Equations 3.10 - 3.16.
   - Evaluated as a scalar system: A = 1, H = 1, B = 0.
2. Adaptive Measurement Noise (R_k): Wang et al. 2022 (AKF.pdf), Eq. 27.
3. Weighting Factor (d_{k-1}): 
   Adopted experimental weighting convention: d_{k-1} = (1-b)/(1-b^k).
   This is an experimental/tuning choice and not explicitly derived from PPA.pdf or Wang.
   For b=1.0, it uses the analytical limit d_{k-1} = 1/k.

Note on Initialization:
Parameters b, x0, P0, Q, and R0 are experimental/configurable choices.
"""

from typing import Dict, Any, List

class AdaptiveKalmanFilter:
    def __init__(self, b: float, x0: float, P0: float, Q: float, R0: float):
        """
        Initializes the Adaptive Kalman Filter with explicitly
        configurable experimental parameters.

        Args:
            b: Forgetting factor (0 < b <= 1.0).
            x0: Initial state estimate.
            P0: Initial state error covariance.
            Q: Process noise covariance (static).
            R0: Initial measurement noise covariance.
        """
        self.b = float(b)
        self.x = float(x0)
        self.P = float(P0)
        self.Q = float(Q)
        self.R = float(R0)
        self.k = 1  # Step counter (k >= 1)

        # Diagnostics history
        self.history: List[Dict[str, float]] = []

    def step(self, z: float) -> float:
        """
        Processes a single RSSI measurement and updates the state.
        
        Args:
            z: The raw RSSI measurement at step k.
            
        Returns:
            The filtered state estimate x_k.
        """
        # Calculate weighting factor d_{k-1}
        # If b = 1.0, we use the analytical limit to prevent DivisionByZero (0/0)
        if abs(self.b - 1.0) < 1e-12:
            d_k_minus_1 = 1.0 / self.k
        else:
            d_k_minus_1 = (1.0 - self.b) / (1.0 - self.b**self.k)

        # 1. State Prediction (Eq 3.10: x_pred = A*x, A=1)
        x_pred = self.x

        # 2. Covariance Prediction (Eq 3.11: P_pred = A*P*A^T + Q, A=1)
        P_pred = self.P + self.Q

        # 3. Innovation (Eq 3.12: e_k = z - H*x_pred, H=1)
        e_k = z - x_pred

        # 4. Innovation Covariance (Eq 3.13: S_k = H*P_pred*H^T + R, H=1)
        S_k = P_pred + self.R

        # 5. Kalman Gain (Eq 3.14: K_k = P_pred*H^T * S_k^-1, H=1)
        # Prevent division by zero mathematically if S_k is exactly 0
        K_k = P_pred / S_k if S_k != 0 else 0.0

        # 6. State Update (Eq 3.15: x = x_pred + K_k * e_k)
        self.x = x_pred + K_k * e_k

        # 7. Covariance Update (Eq 3.16: P = (I - K_k*H)*P_pred, H=1)
        self.P = (1.0 - K_k) * P_pred

        # 8. Adaptive Measurement Noise Update (Wang Eq. 27 exactly)
        # R_k = (1 - d_{k-1}) * R_{k-1} + d_{k-1} * [e_k^2 - H * P_pred * H^T]
        # H=1
        self.R = (1.0 - d_k_minus_1) * self.R + d_k_minus_1 * (e_k**2 - P_pred)

        # Record diagnostics for later visualization
        self.history.append({
            'k': self.k,
            'z': z,
            'x_pred': x_pred,
            'P_pred': P_pred,
            'e_k': e_k,
            'S_k': S_k,
            'K_k': K_k,
            'x': self.x,
            'P': self.P,
            'R': self.R,
            'd_k_minus_1': d_k_minus_1
        })

        self.k += 1
        return self.x
