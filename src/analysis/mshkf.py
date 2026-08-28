"""
mshkf.py

Adaptive Kalman Filter (AKF) for RSSI Preprocessing
with online adaptive Gustafson-Kessel fuzzy clustering based on:
Wang et al. (2022), "A modified Sage-Husa adaptive Kalman filter for state
estimation of electric vehicle servo control system", Energy Reports 8, 20-27.

Theoretical Foundations vs. RSSI Adaptations:
1. Core Adaptive Kalman Filter Recursive Cycle (Wang et al. Eqs. 1-7, 26, 27):
   - Scalar state-space model: x_k = x_{k-1} + w_k (Phi=1), z_k = x_k + v_k (H=1)
   - State prediction (Eq. 1):       x_pred = x_{k-1} (process noise mean q=0 for stationary channel)
   - Covariance prediction (Eq. 2):  P_pred = P_{k-1} + Q_k
   - Innovation (Eq. 3):             eps_k  = z_k - x_pred - r_{k-1}  (uses prior noise mean r_{k-1})
   - Innovation covariance (Eq. 4):  S_k    = P_pred + R_{k-1}        (uses prior noise covariance R_{k-1})
   - Kalman gain (Eq. 5):            K_k    = P_pred / S_k
   - Posterior state update (Eq. 6): x_k    = x_pred + K_k * eps_k
   - Posterior covariance (Eq. 7):   P_k    = (1 - K_k) * P_pred
   - Online noise mean (Eq. 26):     r_k    = (1 - d_{k-1}) * r_{k-1} + d_{k-1} * (z_k - x_pred)
   - Online noise covariance (Eq. 27):R_k   = (1 - d_{k-1}) * R_{k-1} + d_{k-1} * (eps_k^2 - P_pred)
   - Fading factor:                  d_{k-1}= (1 - b_k) / (1 - b_k^k), with analytical limit d_{k-1} = 1/k at b_k=1.0.

2. Online Gustafson-Kessel Fuzzy Clustering (Wang et al. Section 2.2, Eqs. 16-22):
   - Feature Vector: f_k = [z_k, Delta z_k, sigma_k]^T (3D RSSI feature space)
   - Mahalanobis distance (Eq. 17): d_{ik} = sqrt((f_k - v_i)^T * [det(F_i)^(1/d) * F_i^(-1)] * (f_k - v_i))
   - Membership degree (Eq. 16):    mu_{ik} = 1 / sum_{j=1}^c (d_{ik} / d_{jk})^(2/(m-1))
   - Nearest cluster (Eq. 18):       p = argmin_i d_{ik}
   - Cluster update (Eq. 20):        v_p <- v_p + sigma * (f_k - v_p), F_p <- F_p + sigma * (zeta*zeta^T - F_p)
   - Cluster growth (Eq. 21):        Candidate cluster tracked when d_{pk} > r_p; promoted to active cluster
                                     once sample support exceeds minimum threshold N_min.
   - Partition coefficient (Eq. 22): PC(c) = 1/N * sum_{i=1}^c sum_{k=1}^N mu_{ik}^2

3. Project-Specific Fuzzy-to-AKF Coupling (RSSI Heuristic Adaptation):
   - In Wang et al., fuzzy clustering scheduled multi-dimensional PMSM motor sub-models.
   - In this scalar RSSI pipeline, fuzzy memberships dynamically blend the regime-specific
     process noise Q_k and fading memory b_k:
     Q_k = sum_{i=1}^c mu_{ik} * Q_i
     b_k = sum_{i=1}^c mu_{ik} * b_i

Hyperparameter Classification:
- Theoretical: Eqs. (1-7), (16-22), (26), (27) from Wang et al. (2022).
- Experimental Hyperparameters: Initial cluster prototypes v_0/v_1, covariance priors F_0/F_1,
  initial radius r_0=3.0, learning rate sigma=0.05, causal window w=5, support threshold N_min=15,
  process noise regimes (Q_stable=0.001, Q_dynamic=0.010), and initial offset x0 = z0 + 2.0 dBm.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class FuzzyClusteringEngine:
    """
    Online Adaptive Gustafson-Kessel Fuzzy Clustering Engine adapted for RSSI features.
    Maintains cluster centers, adaptive covariance matrices, membership distributions,
    and supports dynamic cluster generation under minimum sample support.
    """

    def __init__(
        self,
        n_clusters: int = 2,
        m: float = 2.0,
        learning_rate: float = 0.05,
        min_pts_support: int = 15,
        max_clusters: int = 5,
        feature_dim: int = 3,
    ):
        """
        Args:
            n_clusters: Initial number of active operating regime clusters (default: 2 -> Stable, Dynamic).
            m: Fuzziness weighting exponent (default: 2.0).
            learning_rate: Online cluster update learning rate sigma (Wang Eq. 20, default: 0.05).
            min_pts_support: Minimum consecutive/proximate data points required before retaining
                             a new cluster (Wang Eq. 21, default: 15).
            max_clusters: Safety upper bound on active clusters to prevent unbounded memory growth.
            feature_dim: Dimension of the RSSI feature vector [z_k, Delta z_k, sigma_k] (default: 3).
        """
        self.c = int(n_clusters)
        self.m = float(m)
        self.sigma = float(learning_rate)
        self.min_pts_support = int(min_pts_support)
        self.max_clusters = int(max_clusters)
        self.dim = int(feature_dim)

        self.v = np.zeros((self.c, self.dim), dtype=np.float64)
        self.F = np.zeros((self.c, self.dim, self.dim), dtype=np.float64)
        self.r_radius = np.zeros(self.c, dtype=np.float64)
        self.is_initialized = False

        # Candidate cluster state for Wang Eq. 21
        self.candidate_center: Optional[np.ndarray] = None
        self.candidate_count: int = 0

        # Diagnostics history
        self.history: List[Dict[str, Any]] = []

    def init_clusters(self, z_first: float, x0_prior: float) -> None:
        """
        Initialize cluster prototypes causally based on prior knowledge and link level.
        - Cluster 0: Stationary/Stable regime (low gradient, low variance).
        - Cluster 1: Dynamic/Fading regime (elevated gradient, higher variance).
        """
        # Cluster 0: Steady-state / Low Dynamics [x0, 0.0 dBm/step, 0.3 dBm std]
        self.v[0] = np.array([x0_prior, 0.0, 0.3], dtype=np.float64)
        self.F[0] = np.diag([2.0, 1.0, 0.5]).astype(np.float64)
        self.r_radius[0] = 3.0

        # Cluster 1: Transient / High Dynamics [x0, 2.0 dBm/step, 1.5 dBm std]
        self.v[1] = np.array([x0_prior, 2.0, 1.5], dtype=np.float64)
        self.F[1] = np.diag([5.0, 4.0, 1.5]).astype(np.float64)
        self.r_radius[1] = 4.0

        self.is_initialized = True

    def extract_features(self, z_buffer: List[float]) -> np.ndarray:
        """
        Construct causal 3D RSSI feature vector f_k = [z_k, Delta z_k, sigma_k]^T.
        - z_k: Current raw RSSI measurement.
        - Delta z_k: First-difference gradient (z_k - z_{k-1}).
        - sigma_k: Causal short-term standard deviation over window w=5.
        """
        z_k = float(z_buffer[-1])
        delta_z = float(z_k - z_buffer[-2]) if len(z_buffer) >= 2 else 0.0
        w = min(len(z_buffer), 5)
        local_std = float(np.std(z_buffer[-w:], ddof=0)) if w > 1 else 0.5
        return np.array([z_k, delta_z, local_std], dtype=np.float64)

    def compute_mahalanobis_distances(self, f_k: np.ndarray) -> np.ndarray:
        """
        Compute Gustafson-Kessel Mahalanobis distance d_{ik} to all clusters (Wang Eq. 17):
        d_{ik} = sqrt((f_k - v_i)^T * [(det(F_i))^(1/d) * F_i^(-1)] * (f_k - v_i))
        """
        d_vec = np.zeros(self.c, dtype=np.float64)
        for i in range(self.c):
            diff = f_k - self.v[i]
            det_F = float(np.linalg.det(self.F[i]))
            # Documented numerical regularization for ill-conditioned cluster covariances:
            if det_F <= 1e-8 or np.isnan(det_F):
                F_inv = np.linalg.pinv(self.F[i] + 1e-4 * np.eye(self.dim))
                scale = 1.0
            else:
                scale = det_F ** (1.0 / self.dim)
                F_inv = np.linalg.inv(self.F[i])

            A_i = scale * F_inv
            dist_sq = float(diff.T @ A_i @ diff)
            d_vec[i] = np.sqrt(max(dist_sq, 1e-12))
        return d_vec

    def compute_memberships(self, d_vec: np.ndarray) -> np.ndarray:
        """
        Compute fuzzy membership degrees mu_{ik} for all active clusters (Wang Eq. 16):
        mu_{ik} = 1 / sum_{j=1}^c (d_{ik} / d_{jk})^(2 / (m - 1))
        """
        exp = 2.0 / (self.m - 1.0)
        memberships = np.zeros(self.c, dtype=np.float64)
        zero_idx = np.where(d_vec < 1e-6)[0]

        if len(zero_idx) > 0:
            memberships[zero_idx[0]] = 1.0
        else:
            for i in range(self.c):
                ratios = (d_vec[i] / d_vec) ** exp
                memberships[i] = 1.0 / float(np.sum(ratios))

        # Enforce exact partition of unity: sum(mu) = 1
        total_mu = np.sum(memberships)
        if total_mu > 0:
            memberships /= total_mu
        else:
            memberships.fill(1.0 / self.c)

        return memberships

    def step(self, z_buffer: List[float], x0_prior: float) -> Tuple[np.ndarray, np.ndarray, int]:
        """
        Process a single observation buffer causally and update clustering parameters.

        Returns:
            f_k: Feature vector [z_k, Delta z_k, sigma_k].
            memberships: Array of cluster memberships [mu_0, ..., mu_{c-1}].
            p: Nearest cluster index.
        """
        f_k = self.extract_features(z_buffer)

        if not self.is_initialized:
            self.init_clusters(z_buffer[0], x0_prior)

        d_vec = self.compute_mahalanobis_distances(f_k)
        memberships = self.compute_memberships(d_vec)
        p = int(np.argmin(d_vec))

        # Online Cluster Center and Covariance Adaptation (Wang Eq. 20)
        if d_vec[p] <= self.r_radius[p]:
            zeta = f_k - self.v[p]
            self.v[p] += self.sigma * zeta
            cov_delta = np.outer(zeta, zeta) - self.F[p]
            self.F[p] += self.sigma * cov_delta
            self.r_radius[p] = max(self.r_radius[p], float(d_vec[p]))
        else:
            # Candidate New Cluster Handling with Minimum-Support Rule (Wang Eq. 21)
            if self.candidate_center is None:
                self.candidate_center = f_k.copy()
                self.candidate_count = 1
            else:
                dist_to_cand = float(np.linalg.norm(f_k - self.candidate_center))
                if dist_to_cand < 2.5:
                    self.candidate_count += 1
                    # Retain and establish new cluster if support threshold is achieved (Wang Eq. 21)
                    if self.candidate_count >= self.min_pts_support and self.c < self.max_clusters:
                        new_v = self.candidate_center.copy()
                        new_F = self.F[p].copy()
                        new_r = 3.5

                        self.v = np.vstack([self.v, new_v.reshape(1, self.dim)])
                        self.F = np.concatenate([self.F, new_F.reshape(1, self.dim, self.dim)], axis=0)
                        self.r_radius = np.append(self.r_radius, new_r)
                        self.c += 1

                        self.candidate_center = None
                        self.candidate_count = 0
                else:
                    self.candidate_center = f_k.copy()
                    self.candidate_count = 1

        self.history.append({
            "f_k": f_k.copy(),
            "d_vec": d_vec.copy(),
            "memberships": memberships.copy(),
            "nearest_cluster": p,
            "cluster_centers": self.v.copy(),
            "cluster_radius": self.r_radius.copy(),
            "active_cluster_count": self.c,
        })

        return f_k, memberships, p

    def compute_partition_coefficient(self) -> float:
        """
        Compute overall partition coefficient PC(c) (Wang Eq. 22):
        PC(c) = 1/N * sum_{i=1}^c sum_{k=1}^N (mu_{ik})^2
        """
        if not self.history:
            return 0.0
        n_samples = len(self.history)
        total_sq = sum(float(np.sum(h["memberships"] ** 2)) for h in self.history)
        return total_sq / float(n_samples)


class ModifiedSageHusaKalmanFilter:
    """
    Adaptive Kalman Filter (AKF) for scalar RSSI tracking based on Sage-Husa formulation (Wang et al. 2022).
    Integrates online Gustafson-Kessel fuzzy clustering to adapt process noise and fading memory.
    """

    def __init__(
        self,
        x0: float,
        P0: float = 1.0,
        Q_regimes: Tuple[float, float] = (0.001, 0.010),
        b_regimes: Tuple[float, float] = (1.00, 0.98),
        r0: float = 0.0,
        R0: float = 1.0,
        fuzzy_engine: Optional[FuzzyClusteringEngine] = None,
    ):
        """
        Args:
            x0: Initial state estimate prior.
            P0: Initial error covariance prior.
            Q_regimes: Tuple of (Q_stable, Q_dynamic) process noise covariances.
            b_regimes: Tuple of (b_stable, b_dynamic) forgetting factors.
            r0: Initial measurement noise mean prior (Wang Eq. 26).
            R0: Initial measurement noise covariance prior (Wang Eq. 27).
            fuzzy_engine: Optional pre-configured FuzzyClusteringEngine instance.
        """
        self.x = float(x0)
        self.P = float(P0)
        self.Q_regimes = tuple(float(q) for q in Q_regimes)
        self.b_regimes = tuple(float(b) for b in b_regimes)
        self.r = float(r0)
        self.R = float(R0)
        self.k = 1  # 1-indexed step counter

        self.fuzzy = fuzzy_engine if fuzzy_engine is not None else FuzzyClusteringEngine(n_clusters=2)
        self.z_buffer: List[float] = []
        self.history: List[Dict[str, Any]] = []

    def step(self, z: float) -> float:
        """
        Execute one causal step of the complete MSHKF cycle on incoming raw RSSI measurement z.

        Returns:
            The posterior filtered RSSI state estimate x_k.
        """
        z_val = float(z)
        self.z_buffer.append(z_val)

        # 0. Fuzzy Clustering Step: extract features & evaluate membership
        f_k, mu, cluster_idx = self.fuzzy.step(self.z_buffer, self.x)

        # Handle dynamically sized cluster memberships (c >= 2)
        c_curr = len(mu)
        if len(self.Q_regimes) >= c_curr:
            q_weights = np.array(self.Q_regimes[:c_curr], dtype=np.float64)
        else:
            q_weights = np.array(list(self.Q_regimes) + [self.Q_regimes[-1]] * (c_curr - len(self.Q_regimes)), dtype=np.float64)

        if len(self.b_regimes) >= c_curr:
            b_weights = np.array(self.b_regimes[:c_curr], dtype=np.float64)
        else:
            b_weights = np.array(list(self.b_regimes) + [self.b_regimes[-1]] * (c_curr - len(self.b_regimes)), dtype=np.float64)

        # Fuzzy parameter blending across operating regimes (Project Heuristic Adaptation)
        Q_k = float(np.dot(mu, q_weights))
        b_k = float(np.dot(mu, b_weights))

        # Fading factor d_{k-1} with exact analytical limit at b_k=1.0
        if abs(b_k - 1.0) < 1e-12:
            d_k_minus_1 = 1.0 / self.k
        else:
            d_k_minus_1 = (1.0 - b_k) / (1.0 - b_k**self.k)

        # 1. State Prediction (Wang Eq. 1: Phi=1, q=0 for stationary channel)
        x_pred = self.x

        # 2. Covariance Prediction (Wang Eq. 2: Phi=1, Q_k dynamic)
        P_pred = self.P + Q_k

        # 3. Measurement Innovation using prior noise mean r_{k-1} (Wang Eq. 3)
        eps_k = z_val - x_pred - self.r

        # 4. Innovation Covariance using prior noise covariance R_{k-1} (Wang Eq. 4)
        S_k = P_pred + self.R

        # 5. Kalman Gain (Wang Eq. 5)
        K_k = P_pred / S_k if S_k != 0 else 0.0

        # 6. Posterior State Update (Wang Eq. 6)
        self.x = x_pred + K_k * eps_k

        # 7. Posterior Covariance Update (Wang Eq. 7)
        self.P = (1.0 - K_k) * P_pred

        # 8. Online Measurement Noise Mean Update (Wang Eq. 26)
        self.r = (1.0 - d_k_minus_1) * self.r + d_k_minus_1 * (z_val - x_pred)

        # 9. Online Measurement Noise Covariance Update (Wang Eq. 27)
        self.R = (1.0 - d_k_minus_1) * self.R + d_k_minus_1 * (eps_k**2 - P_pred)

        # Record complete diagnostics
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
            "Q_eff": Q_k,
            "b_eff": b_k,
            "d_k_minus_1": d_k_minus_1,
            "cluster": cluster_idx,
            "memberships": mu.copy(),
            "f_k": f_k.copy(),
        })

        self.k += 1
        return self.x
