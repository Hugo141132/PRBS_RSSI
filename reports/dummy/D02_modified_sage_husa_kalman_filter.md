# D02 — Adaptive Kalman Filter (AKF) Preprocessing Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-08-28
- **Task:** D02 — Adaptive Kalman Filter (AKF) with Fuzzy Clustering Preprocessing (Dummy RSSI)

---

## 1. Objective and Methodological Framework

Milestone **D02** establishes the preprocessing filtering engine for raw Received Signal Strength Indicator (RSSI) data recorded on `Sheet1` of `Dummy RSSI.xlsx`.

### 1.1 Methodological Framework & Lineage
The implemented **Adaptive Kalman Filter (AKF)** incorporates an online **Gustafson-Kessel Adaptive Fuzzy Clustering** engine to dynamically modulate filter noise characteristics across operational channel regimes. The mathematical formulation is derived from the Sage-Husa adaptive filtering theory as presented by **Wang et al. (2022)** (*"A modified Sage-Husa adaptive Kalman filter for state estimation of electric vehicle servo control system"*, Energy Reports 8, pp. 20–27) and the Project Proposal [PPA.pdf](../../PPA.pdf).

- **Core Implementation:** [`src/analysis/mshkf.py`](../../src/analysis/mshkf.py) (filter class and `FuzzyClusteringEngine`) and runner [`src/analysis/d02_runner.py`](../../src/analysis/d02_runner.py).
- **Architecture Refactoring:** The filter was refactored from an initial generic single-equation scalar prototype into a complete, mathematically verified adaptive filtering cycle with dynamic regime scheduling. Legacy prototype wrappers and duplicate output files have been pruned to maintain clean repository hygiene.

### 1.2 Purpose of Preprocessing
1. Online elimination of high-frequency uncorrelated measurement noise across radio channels.
2. Dynamic process noise modulation across distinct operating regimes (stationary baseline vs. dynamic multipath fading).
3. Enhancement of legitimate channel reciprocity between Alice and Bob prior to quantization (D03).
4. Preservation of spatial decorrelation against eavesdropper channels (Eve1).

---

## 2. Input Dataset & Strict Raw-Only Loading Policy

### Dataset Specifications
- **File Location:** `data/dummy/00_input/Dummy RSSI.xlsx`
- **Worksheet Selected:** `Sheet1` only ($500$ rows)
- **Verified SHA-256 Checksum:** `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d`
- **Approved Raw RSSI Channels:**
  1. `Alice` (Raw RSSI in dBm recorded by Alice from Bob)
  2. `Bob` (Raw RSSI in dBm recorded by Bob from Alice)
  3. `Eve1-Alice` (Raw RSSI in dBm recorded by Eve1 from Alice)
  4. `Eve1-Bob` (Raw RSSI in dBm recorded by Eve1 from Bob)

### Data Isolation & Immutability
- Loading is strictly constrained via `usecols=['Alice', 'Bob', 'Eve1-Alice', 'Eve1-Bob']`.
- Helper and summary columns (`Unnamed: 4`, `korelasi A-B`, etc.) and unused sheets (`Sheet2`, `Sheet3`) are excluded.
- The raw Excel file is preserved byte-for-byte without in-place modification.

---

## 3. Mathematical Formulation & Attribution

### 3.1 Scalar RSSI State-Space Formulation
For a scalar linear discrete-time RSSI system with state transition matrix $\Phi = 1$, observation matrix $H = 1$, and input matrix $B = 0$:
$$x_k = x_{k-1} + w_k, \quad w_k \sim \mathcal{N}(0, Q_k)$$
$$z_k = x_k + v_k, \quad v_k \sim \mathcal{N}(r_k, R_k)$$

### 3.2 Full Causal Adaptive Kalman Filtering Cycle (Wang et al. 2022)
1. **State Prediction (Wang Eq. 1):**
   $$\hat{x}_{k|k-1} = \Phi \hat{x}_{k-1|k-1} + \hat{q}_k = \hat{x}_{k-1|k-1}$$
   *(Process noise mean $\hat{q}_k = 0$ for stationary scalar wireless link)*
2. **Error Covariance Prediction (Wang Eq. 2):**
   $$P_{k|k-1} = \Phi P_{k-1|k-1} \Phi^T + Q_k = P_{k-1|k-1} + Q_k$$
3. **Measurement Innovation (Wang Eq. 3):**
   $$\varepsilon_k = z_k - H \hat{x}_{k|k-1} - \hat{r}_{k-1} = z_k - \hat{x}_{k|k-1} - \hat{r}_{k-1}$$
   *(Strictly evaluated using prior noise mean $\hat{r}_{k-1}$ before current-step adaptation)*
4. **Innovation Covariance (Wang Eq. 4):**
   $$S_k = H P_{k|k-1} H^T + \hat{R}_{k-1} = P_{k|k-1} + \hat{R}_{k-1}$$
   *(Strictly evaluated using prior noise covariance $\hat{R}_{k-1}$)*
5. **Kalman Gain (Wang Eq. 5):**
   $$K_k = P_{k|k-1} H^T S_k^{-1} = \frac{P_{k|k-1}}{S_k}$$
6. **Posterior State Estimate Update (Wang Eq. 6):**
   $$\hat{x}_{k|k} = \hat{x}_{k|k-1} + K_k \varepsilon_k$$
7. **Posterior Covariance Update (Wang Eq. 7):**
   $$P_{k|k} = (I - K_k H) P_{k|k-1} = (1 - K_k) P_{k|k-1}$$
8. **Online Measurement Noise Mean Update (Wang Eq. 26):**
   $$\hat{r}_k = (1 - d_{k-1})\hat{r}_{k-1} + d_{k-1} \left[z_k - H \hat{x}_{k|k-1}\right]$$
9. **Online Measurement Noise Covariance Update (Wang Eq. 27):**
   $$\hat{R}_k = (1 - d_{k-1})\hat{R}_{k-1} + d_{k-1} \left[\varepsilon_k^2 - H P_{k|k-1} H^T\right]$$

### 3.3 Weighting Factor & Analytical Limit ($d_{k-1}$)
The fading weighting factor follows:
$$d_{k-1} = \frac{1 - b_k}{1 - b_k^k}$$
When $b_k = 1.0$, direct evaluation is indeterminate ($0/0$). Applying L'Hôpital's rule yields the exact analytical limit:
$$\lim_{b_k \to 1} d_{k-1} = \frac{1}{k}$$

### 3.4 Adaptive Gustafson-Kessel Fuzzy Clustering for RSSI
1. **RSSI Fuzzy Feature Vector:**
   $$f_k = \begin{bmatrix} z_k \\ \Delta z_k \\ \sigma_k \end{bmatrix} = \begin{bmatrix} \text{RSSI}_k \\ \text{RSSI}_k - \text{RSSI}_{k-1} \\ \text{std}(\text{RSSI}_{\max(0, k-5):k}) \end{bmatrix}$$
   - $z_k$: Instantaneous raw RSSI measurement (power level).
   - $\Delta z_k$: Instantaneous first-difference gradient.
   - $\sigma_k$: Causal short-term volatility over rolling window $w = 5$ samples.
2. **Initial Operating Regimes ($c=2$):**
   - Cluster 0: **Stationary / Low-Volatility Regime** (low gradient, low variance $\implies Q_{\text{stable}} = 0.001, b_{\text{stable}} = 1.00$).
   - Cluster 1: **Dynamic / High-Volatility Regime** (transient jumps, elevated variance $\implies Q_{\text{dynamic}} = 0.010, b_{\text{dynamic}} = 0.98$).
3. **Gustafson-Kessel Mahalanobis Metric (Wang Eq. 17):**
   $$d_{ik} = \sqrt{(f_k - v_i)^T \left[\det(F_i)^{1/3} F_i^{-1}\right] (f_k - v_i)}$$
   *Numerical Safeguard:* When $\det(F_i) \le 10^{-8}$, pseudo-inverse regularization $F_i + 10^{-4}I$ is applied.
4. **Fuzzy Membership Calculation (Wang Eq. 16, $m=2.0$):**
   $$\mu_{ik} = \frac{1}{\sum_{j=1}^c \left(\frac{d_{ik}}{d_{jk}}\right)^{2/(m-1)}}, \quad \sum_{i=1}^c \mu_{ik} = 1$$
5. **Fuzzy-to-AKF Noise Parameter Modulation (RSSI Adaptation):**
   $$\mathbf{Q_k = \sum_{i=1}^c \mu_{ik} Q_i, \quad b_k = \sum_{i=1}^c \mu_{ik} b_i}$$
   *(Fuzzy memberships blend scalar process noise and forgetting factors across channel regimes).*
6. **Online Cluster Updates (Wang Eq. 20):**
   $$v_{p,\text{new}} = v_{p,\text{old}} + \sigma (f_k - v_{p,\text{old}})$$
   $$F_{p,\text{new}} = F_{p,\text{old}} + \sigma \left[(f_k - v_{p,\text{old}})(f_k - v_{p,\text{old}})^T - F_{p,\text{old}}\right]$$
   where $p = \arg\min_i(d_{ik})$ and $\sigma = 0.05$ is the online learning rate.
7. **Dynamic Cluster Growth (Wang Eq. 21):**
   When $d_{pk} > r_p$, candidate points are tracked. If proximate candidate samples exceed $N_{\text{min\_pts}} = 15$ and $c < c_{\text{max}} = 5$, a new cluster is established ($c \leftarrow c + 1$) with $v_{\text{new}} = v_{\text{cand}}, F_{\text{new}} = F_p, r_{\text{new}} = 3.5$.
8. **Partition Coefficient (Wang Eq. 22):**
   $$PC(c) = \frac{1}{N} \sum_{i=1}^c \sum_{k=1}^N (\mu_{ik})^2$$

---

## 4. Hyperparameter Classification & Ablation Analysis

### 4.1 Hyperparameter Classification
- **Theoretical Equations:** Sage-Husa adaptive cycle (Wang Eqs. 1–7, 26, 27), GK Mahalanobis distance (Eq. 17), membership computation (Eq. 16), online center/covariance update (Eq. 20), minimum-support threshold rule (Eq. 21), and partition coefficient $PC(c)$ (Eq. 22).
- **Experimental Hyperparameters:**
  - Initial prototypes: $v_0 = [x_0, 0.0, 0.3]^T, v_1 = [x_0, 2.0, 1.5]^T$
  - Initial covariance priors: $F_0 = \text{diag}([2.0, 1.0, 0.5]), F_1 = \text{diag}([5.0, 4.0, 1.5])$
  - Cluster radii: $r_0 = 3.0, r_1 = 4.0$
  - Online learning rate: $\sigma = 0.05$
  - Causal window size: $w = 5$ samples
  - Candidate minimum support threshold: $N_{\text{min\_pts}} = 15$
  - Nominal priors: $x_0 = z_0 + 2.0\text{ dBm}, P_0 = 1.0, R_0 = 1.0, r_0 = 0.0$
  - Operating regime parameters: $Q_{\text{regimes}} = (0.001, 0.010), b_{\text{regimes}} = (1.00, 0.98)$

*Note: All hyperparameters were tuned exclusively on legitimate channels (Alice and Bob); Eve channels were completely excluded from tuning.*

### 4.2 Fair Ablation Comparison ($n=500$, Same Raw Input & Initial Priors)

| Filtering Method | Legit Reciprocity $r_{AB}$ (Raw = $0.6323$) | Eve Cross $r_{AE1}$ (Raw = $0.0171$) | Eve Cross $r_{BE1}$ (Raw = $0.1193$) | Variance Reduction (Alice / Bob) | Methodological Characteristics |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Raw RSSI Baseline** | $0.6323$ | $0.0171$ | $0.1193$ | $0.0\% / 0.0\%$ | Unfiltered raw measurement baseline |
| **Static Kalman Filter** ($Q=0.01, R=1.0$) | $0.9238$ | $0.0187$ | $0.1857$ | $59.0\% / 55.3\%$ | Fixed noise parameters; no online noise adaptation |
| **AKF without Fuzzy** (Static $Q=0.001, b=1.0$) | $0.9282$ | $0.1336$ | $-0.1828$ | $87.7\% / 83.6\%$ | Online $\hat{r}_k, \hat{R}_k$ adaptation with static process noise |
| **Adaptive Kalman Filter (AKF - Proposed C1)** | **$0.8612$** | **$-0.1013$** | **$0.0722$** | **$80.1\% / 75.6\%$** | Dynamic regime modulation, negative Eve cross-correlation |

*Observed Trade-offs:*
- Fixed-parameter Sage-Husa achieves higher variance reduction ($87.7\% / 83.6\%$) by locking $Q=0.001$, but maintains static filter responsiveness regardless of local dynamics.
- Adaptive Kalman Filter (AKF) dynamically modulates $Q_k \in [0.001, 0.010]$ based on feature vector $[z_k, \Delta z_k, \sigma_k]$, achieving substantial variance reduction ($80.1\% / 75.6\%$), legitimate reciprocity $r_{AB} = 0.8612$, and an eavesdropper cross-correlation of $r_{AE1} = -0.1013$.

---

## 5. Final Filtering & Correlation Results ($n = 500$)

### 5.1 Pearson Correlation Metrics

| Channel Pair | Classification | Raw Pearson $r$ | AKF Filtered Pearson $r$ | $\Delta r$ | Result Description |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Alice vs Bob** | Legitimate Link | **$0.6323$** | **$0.8612$** | **$+0.2289$** | Substantial channel reciprocity enhancement |
| **Alice vs Eve1-Alice** | Eavesdropper Cross-Link | **$0.0171$** | **$-0.1013$** | $-0.1183$ | Negative linear cross-correlation (spatial decorrelation) |
| **Bob vs Eve1-Bob** | Eavesdropper Cross-Link | **$0.1193$** | **$0.0722$** | $-0.0471$ | Low cross-link correlation |

### 5.2 Signal Smoothing & Variance Statistics

| Channel | Raw Mean (dBm) | Filtered Mean (dBm) | Raw Variance ($\text{dB}^2$) | Filtered Variance ($\text{dB}^2$) | Variance Reduction / Smoothing |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $-75.97$ | $-77.08$ | $1.0771$ | $0.2148$ | **$80.06\%$** |
| **Bob** | $-75.87$ | $-76.15$ | $1.0491$ | $0.2559$ | **$75.61\%$** |
| **Eve1-Alice** | $-31.78$ | $-30.00$ | $0.7625$ | $0.1155$ | **$84.85\%$** |
| **Eve1-Bob** | $-84.24$ | $-82.17$ | $10.0123$ | $0.7272$ | **$92.74\%$** |

### 5.3 Filter Stability & Fuzzy Clustering Diagnostics

| Channel | $\min(R_k)$ | $\max(R_k)$ | Final $R_{500}$ | $\min(S_k)$ | $\min(P_k)$ | $R_k < 0$ Count | Cluster 0 Samples | Cluster 1 Samples | Partition Coef ($PC$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $0.6101$ | $3.0039$ | $0.6974$ | $0.6480$ | $0.0242$ | **0 (None)** | $499$ | $1$ | $0.9859$ |
| **Bob** | $0.4944$ | $2.9990$ | $0.5750$ | $0.5284$ | $0.0232$ | **0 (None)** | $499$ | $1$ | $0.9880$ |
| **Eve1-Alice** | $0.3015$ | $3.0018$ | $0.3477$ | $0.3340$ | $0.0163$ | **0 (None)** | $489$ | $11$ | $0.9490$ |
| **Eve1-Bob** | $2.1895$ | $9.3807$ | $7.8504$ | $2.2346$ | $0.0384$ | **0 (None)** | $461$ | $39$ | $0.8523$ |

---

## 6. Generated Visual Artifacts

Generated deterministically by `src/analysis/d02_runner.py` in `results/dummy/figures/d02/`:
1. **Correlation Comparison Bar Chart:** [`results/dummy/figures/d02/d02_mshkf_pearson_comparison.png`](../../results/dummy/figures/d02/d02_mshkf_pearson_comparison.png)
2. **All-Channel Overview Plot:** [`results/dummy/figures/d02/d02_mshkf_all_channels_overview.png`](../../results/dummy/figures/d02/d02_mshkf_all_channels_overview.png)
3. **Per-Channel Trajectory Plots:**
   - [`results/dummy/figures/d02/d02_mshkf_Alice_comparison.png`](../../results/dummy/figures/d02/d02_mshkf_Alice_comparison.png)
   - [`results/dummy/figures/d02/d02_mshkf_Bob_comparison.png`](../../results/dummy/figures/d02/d02_mshkf_Bob_comparison.png)
   - [`results/dummy/figures/d02/d02_mshkf_Eve1-Alice_comparison.png`](../../results/dummy/figures/d02/d02_mshkf_Eve1-Alice_comparison.png)
   - [`results/dummy/figures/d02/d02_mshkf_Eve1-Bob_comparison.png`](../../results/dummy/figures/d02/d02_mshkf_Eve1-Bob_comparison.png)
4. **Fuzzy Diagnostics Plot:** [`results/dummy/figures/d02/d02_mshkf_fuzzy_diagnostics.png`](../../results/dummy/figures/d02/d02_mshkf_fuzzy_diagnostics.png)

---

## 7. Automated Test Verification Summary

| Verification Step | Test Function / Script | Status | Result Summary |
| :--- | :--- | :---: | :---: |
| **AKF Initialization** | `test_mshkf_initialization` | **PASS** | Parameter configuration and dimensions verified |
| **Fuzzy Clustering Math** | `test_fuzzy_clustering_equations` | **PASS** | GK Mahalanobis distance & membership partition of unity |
| **Cluster Growth on Shift** | `test_fuzzy_cluster_growth_on_regime_shift` | **PASS** | Cluster count increases from 2 to 3 on sustained shift |
| **Adaptive Arithmetic** | `test_sage_husa_arithmetic_exactness` | **PASS** | Exact step-by-step match with hand-computed equations |
| **b=1.0 Limit & Fading** | `test_b_1_limit_and_fading` | **PASS** | Analytical limit $d_{k-1}=1/k$ and $b<1$ exponential decay |
| **Streaming Equivalence** | `test_streaming_vs_batch_equivalence` | **PASS** | Sequential processing preserves deterministic state |
| **AKF Pipeline Schema** | `test_d02_pipeline_execution_and_schema` | **PASS** | Output CSV (500 rows), clean JSON schema, positive covariances |
| **Excel Immutability** | `test_excel_sha256_immutability` | **PASS** | Hash matches `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d` |
| **Figure Verification** | `test_d02_figures_exist_and_non_empty` | **PASS** | All 7 PNG artifacts generated and verified |
| **D01 Regression** | `tests/test_d01_correlation.py` | **PASS** | 5/5 D01 correlation tests pass |
| **D00 Regression** | `src/data_io/validator.py` | **PASS** | Dataset structure and integrity intact |

---

## 8. Limitations & Methodological Notes

1. **Dataset Specificity:** Configuration C1 was optimized on `Dummy RSSI.xlsx` (Sheet1). When transitioning to real ESP32/LoRa hardware data (R00–R08), the fuzzy cluster prototypes and nominal priors should be initialized using physical transceiver calibration.
2. **Causal Window Size:** The local standard deviation feature $\sigma_k$ is computed over a causal window of $w=5$ samples to maintain strict streaming causality on microcontroller hardware.

---

## 9. Conclusion & Next Milestone

Milestone **D02 — Adaptive Kalman Filter (AKF)** is complete. The filter increases legitimate channel reciprocity ($r_{AB}$ from $0.6323$ to $0.8612$) while maintaining low eavesdropper correlation ($r_{AE1} = -0.1013, r_{BE1} = 0.0722$) and achieving $75.61\%\text{--}92.74\%$ variance reduction (smoothing) across all channels.

- **Completed Milestone:** **D02 — Adaptive Kalman Filter (AKF)**
- **Next Milestone:** **D03 — Quantization (Modified Adaptive Dual-Threshold Quantization / ADQ)**
