# D02 — Modified Sage-Husa Adaptive Kalman Filter (MSHAKF) Preprocessing Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-08-28 (Refactored to Pure MSHAKF 2026-10-02)
- **Task:** D02 — Modified Sage-Husa Adaptive Kalman Filter (MSHAKF) Preprocessing (Dummy RSSI)

---

## 1. Objective and Methodological Framework

Milestone **D02** establishes the preprocessing filtering engine for raw Received Signal Strength Indicator (RSSI) data recorded on `Sheet1` of `Dummy RSSI.xlsx`.

### 1.1 Methodological Framework & Lineage
The implemented filter is strictly the **Modified Sage-Husa Adaptive Kalman Filter (MSHAKF)** based on:
- **Reference Paper:** Wang et al. (2022), *"A modified Sage-Husa adaptive Kalman filter for state estimation of electric vehicle servo control system"*, Energy Reports 8, pp. 20–27 ([`AKF.pdf`](../../AKF.pdf)).
- **Project Proposal:** [PPA.pdf](../../PPA.pdf).

> [!IMPORTANT]
> **Methodological Correction:**
> Earlier prototype code included Gustafson-Kessel fuzzy clustering, which in Wang et al. (2022) was applied specifically to multi-operating regime scheduling of a 3-phase PMSM motor servo drive. For physical-layer RSSI channel preprocessing, fuzzy clustering is extraneous and has been completely eliminated. The D02 engine now implements exclusively the pure Modified Sage-Husa Adaptive Kalman Filter equations with causal online noise estimation.

- **Core Implementation:** [`src/analysis/mshkf.py`](../../src/analysis/mshkf.py) (`ModifiedSageHusaKalmanFilter`) and pipeline runner [`src/analysis/d02_runner.py`](../../src/analysis/d02_runner.py).
- **Deliverables:**
  - Filtered RSSI dataset: [`results/dummy/d02_mshkf_filtered.csv`](../../results/dummy/d02_mshkf_filtered.csv)
  - Diagnostic JSON payload: [`results/dummy/d02_mshkf_results.json`](../../results/dummy/d02_mshkf_results.json)
  - Diagnostic figures: `results/dummy/figures/d02/`

### 1.2 Purpose of Preprocessing
1. Online elimination of high-frequency uncorrelated measurement noise across radio channels.
2. Dynamic online adaptation of measurement noise mean ($\hat{r}_k$) and measurement noise covariance ($\hat{R}_k$) without requiring static offline assumptions.
3. Substantial enhancement of legitimate channel reciprocity ($r_{AB}$) between Alice and Bob prior to quantization (D03).
4. Maintenance of spatial decorrelation against eavesdropper channels (Eve1).

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
- Helper and summary columns (`Unnamed: 4`, `korelasi A-B`, etc.) and unused sheets are excluded.
- The raw Excel file is preserved byte-for-byte without in-place modification.

---

## 3. Mathematical Formulation & Attribution

### 3.1 Scalar RSSI State-Space Formulation
For a scalar linear discrete-time RSSI system with state transition matrix $\Phi = 1$, observation matrix $H = 1$, and process noise mean $q = 0$:
$$x_k = x_{k-1} + w_k, \quad w_k \sim \mathcal{N}(0, Q)$$
$$z_k = x_k + v_k, \quad v_k \sim \mathcal{N}(r_k, R_k)$$

### 3.2 Full Causal MSHAKF Recursive Cycle (Wang et al. 2022)
1. **State Prediction (Wang Eq. 1):**
   $$\hat{x}_{k|k-1} = \Phi \hat{x}_{k-1|k-1} + q = \hat{x}_{k-1|k-1}$$
2. **Error Covariance Prediction (Wang Eq. 2):**
   $$P_{k|k-1} = \Phi P_{k-1|k-1} \Phi^T + Q = P_{k-1|k-1} + Q$$
3. **Measurement Innovation (Wang Eq. 3):**
   $$\varepsilon_k = z_k - H \hat{x}_{k|k-1} - \hat{r}_{k-1} = z_k - \hat{x}_{k|k-1} - \hat{r}_{k-1}$$
   *(Evaluated using prior noise mean $\hat{r}_{k-1}$ before current-step adaptation)*
4. **Innovation Covariance (Wang Eq. 4):**
   $$S_k = H P_{k|k-1} H^T + \hat{R}_{k-1} = P_{k|k-1} + \hat{R}_{k-1}$$
   *(Evaluated using prior noise covariance $\hat{R}_{k-1}$)*
5. **Kalman Gain (Wang Eq. 5):**
   $$K_k = P_{k|k-1} H^T S_k^{-1} = \frac{P_{k|k-1}}{S_k}$$
6. **Posterior State Estimate Update (Wang Eq. 6):**
   $$\hat{x}_{k|k} = \hat{x}_{k|k-1} + K_k \varepsilon_k$$
7. **Posterior Error Covariance Update (Wang Eq. 7):**
   $$P_{k|k} = (I - K_k H) P_{k|k-1} = (1 - K_k) P_{k|k-1}$$
8. **Online Measurement Noise Mean Update (Wang Eq. 26):**
   $$\hat{r}_k = (1 - d_{k-1})\hat{r}_{k-1} + d_{k-1} \left[z_k - H \hat{x}_{k|k-1}\right] = (1 - d_{k-1})\hat{r}_{k-1} + d_{k-1}(z_k - \hat{x}_{k|k-1})$$
9. **Online Measurement Noise Covariance Update (Wang Eq. 27):**
   $$\hat{R}_k = (1 - d_{k-1})\hat{R}_{k-1} + d_{k-1} \left[\varepsilon_k^2 - H P_{k|k-1} H^T\right] = (1 - d_{k-1})\hat{R}_{k-1} + d_{k-1}(\varepsilon_k^2 - P_{k|k-1})$$

### 3.3 Weighting Factor & Analytical Limit ($d_{k-1}$)
The fading weighting factor follows exponential forgetting memory:
$$d_{k-1} = \frac{1 - b}{1 - b^k}, \quad 0 < b \le 1$$
When $b = 1.0$, direct evaluation gives $0/0$. Applying L'Hôpital's rule yields the exact analytical limit:
$$\lim_{b \to 1} d_{k-1} = \frac{1}{k}$$
For $b = 0.98$, older measurements gradually decay in weight, allowing the online noise estimator to track non-stationary channel noise variations.

---

## 4. Configuration C1 Specifications

- **State Prior ($x_0$):** Adaptive initialization ($z_0 + 2.0\text{ dBm}$)
- **Error Covariance Prior ($P_0$):** $1.0$
- **Process Noise Covariance ($Q$):** $0.001$
- **Fading Factor ($b$):** $0.98$
- **Measurement Noise Mean Prior ($r_0$):** $0.0$
- **Measurement Noise Covariance Prior ($R_0$):** $1.0$

*Note: Hyperparameters were selected solely on legitimate channels (Alice and Bob); Eve channels were completely excluded from calibration.*

---

## 5. Filtering & Correlation Results ($n = 500$)

### 5.1 Pearson Correlation Metrics

| Channel Pair | Classification | Raw Pearson $r$ | MSHAKF Filtered Pearson $r$ | $\Delta r$ | Result Description |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Alice vs Bob** | Legitimate Reciprocal Link | **$0.6323$** | **$0.9172$** | **$+0.2849$** | Outstanding reciprocity enhancement (+45.0% increase) |
| **Alice vs Eve1-Alice** | Eavesdropper Cross-Link | **$0.0171$** | **$0.1496$** | $+0.1326$ | Low correlation preserved |
| **Bob vs Eve1-Bob** | Eavesdropper Cross-Link | **$0.1193$** | **$-0.0961$** | $-0.2154$ | Decorrelation achieved (negative cross-correlation) |

### 5.2 Signal Smoothing & Variance Reduction

| Channel | Raw Mean (dBm) | Filtered Mean (dBm) | Raw Variance ($\text{dB}^2$) | Filtered Variance ($\text{dB}^2$) | Variance Reduction / Smoothing |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $-75.97$ | $-77.29$ | $1.0771$ | $0.0825$ | **$92.34\%$** |
| **Bob** | $-75.87$ | $-76.26$ | $1.0491$ | $0.1165$ | **$88.89\%$** |
| **Eve1-Alice** | $-31.78$ | $-29.88$ | $0.7625$ | $0.0546$ | **$92.83\%$** |
| **Eve1-Bob** | $-84.24$ | $-82.44$ | $10.0123$ | $0.2146$ | **$97.86\%$** |

### 5.3 Filter Stability Diagnostics

| Channel | $\min(R_k)$ | $\max(R_k)$ | Final $R_{500}$ | $\min(S_k)$ | $\min(P_k)$ | $R_k < 0$ Count | Final Noise Mean $\hat{r}_{500}$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $0.3082$ | $4.4973$ | $0.5206$ | $0.3278$ | $0.0184$ | **0 (None)** | $+1.4319$ |
| **Bob** | $0.3269$ | $3.6444$ | $0.5752$ | $0.3475$ | $0.0191$ | **0 (None)** | $+0.4771$ |
| **Eve1-Alice** | $0.2397$ | $2.9990$ | $0.4124$ | $0.2571$ | $0.0162$ | **0 (None)** | $-1.9916$ |
| **Eve1-Bob** | $1.8501$ | $19.8494$ | $5.1434$ | $1.9517$ | $0.0560$ | **0 (None)** | $-2.5878$ |

*All covariances remained strictly positive ($P_k > 0, S_k > 0, R_k > 0$) with zero filter divergence or numeric instability.*

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
4. **Adaptive Statistics Diagnostics Plot:** [`results/dummy/figures/d02/d02_mshkf_adaptive_diagnostics.png`](../../results/dummy/figures/d02/d02_mshkf_adaptive_diagnostics.png)
5. **Correlation Scatter Plot:** [`results/dummy/figures/d02/d02_mshkf_rssi_correlation_scatter.png`](../../results/dummy/figures/d02/d02_mshkf_rssi_correlation_scatter.png)
6. **Signal Overlay Comparison:** [`results/dummy/figures/d02/d02_mshkf_signal_overlay_comparison.png`](../../results/dummy/figures/d02/d02_mshkf_signal_overlay_comparison.png)

---

## 7. Automated Test Verification Summary

| Verification Step | Test Function / Script | Status | Result Summary |
| :--- | :--- | :---: | :--- |
| **MSHAKF Initialization** | `test_mshkf_initialization` | **PASS** | Parameter configuration and dimensions verified |
| **8 MSHAKF Equations** | `test_sage_husa_arithmetic_exactness` | **PASS** | Exact hand-computed match across all equations (Eqs. 1–7, 26, 27) |
| **b=1.0 Limit & Fading** | `test_b_1_limit_and_fading` | **PASS** | Analytical limit $d_{k-1}=1/k$ and exponential decay $d_{k-1} = (1-b)/(1-b^k)$ |
| **Streaming Equivalence** | `test_streaming_vs_batch_equivalence` | **PASS** | Causal sequential processing preserves deterministic state |
| **Adaptive Noise Tracking** | `test_adaptive_noise_estimation_convergence` | **PASS** | Online estimation tracks noise bias and maintains positive covariance |
| **MSHAKF Pipeline Schema** | `test_d02_pipeline_execution_and_schema` | **PASS** | Output CSV (500 rows), clean JSON schema, positive covariances |
| **Excel Immutability** | `test_excel_sha256_immutability` | **PASS** | Hash matches `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d` |
| **Figure Verification** | `test_d02_figures_exist_and_non_empty` | **PASS** | All generated PNG artifacts verified and non-empty |
| **D01 Regression** | `tests/test_d01_correlation.py` | **PASS** | 5/5 D01 correlation tests pass |
| **D03 Regression** | `tests/test_d03_quantization.py` | **PASS** | 12/12 D03 quantization tests pass with new D02 output |

---

## 8. Conclusion

Milestone **D02 — Modified Sage-Husa Adaptive Kalman Filter (MSHAKF)** is verified and complete.
By eliminating Gustafson-Kessel fuzzy clustering and adhering strictly to the Modified Sage-Husa equations, the D02 pipeline achieves:
- **Legitimate Reciprocity ($r_{AB}$):** Increases from raw $0.6323$ to **$0.9172$** ($\Delta r = +0.2849$).
- **Variance Smoothing:** $88.89\%\text{--}92.34\%$ variance reduction on legitimate links ($97.86\%$ on Eve1-Bob).
- **Eavesdropper Decorrelation:** Eve cross-correlations stay low ($r_{AE1} = 0.1496$, $r_{BE1} = -0.0961$).
- **Downstream Key Agreement:** Serves as the high-fidelity input to D03 Modified Adaptive Dual-Threshold Quantization, achieving $88.4\%$ (2-bit) and $94.2\%$ (4-bit) key agreement between Alice and Bob.
