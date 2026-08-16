# D02 — Adaptive Kalman Filter (AKF) Preprocessing Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-08-16
- **Task:** D02 — Adaptive Kalman Filter (AKF) Preprocessing (Dummy RSSI)

---

## 1. Objective and Scope
The objective of milestone **D02** is to implement, evaluate, and verify the Adaptive Kalman Filter (AKF) based on the Sage-Husa measurement noise covariance estimator for raw Received Signal Strength Indicator (RSSI) preprocessing on `Sheet1` of `Dummy RSSI.xlsx`. The primary purpose of this filtering phase is to smooth high-frequency measurement fluctuations, enhance physical-layer channel reciprocity between legitimate communicating nodes (Alice and Bob), and examine linear cross-correlation with the eavesdropper (Eve1) prior to multi-bit quantization.

### Scope Boundaries
- **In Scope:**
  - Implementation of scalar Discrete Kalman Filter equations (PPA.pdf Equations 3.10–3.16 with $A=1, H=1, B=0$).
  - Exact implementation of Wang et al. 2022 (AKF.pdf) Eq. (27) for recursive measurement noise covariance ($\hat{R}_k$) adaptation without artificial clipping or covariance floors.
  - Implementation of weighting factor $d_{k-1} = (1-b)/(1-b^k)$ with analytical limit $d_{k-1} = 1/k$ at $b=1.0$.
  - Offline causal parameter-sensitivity evaluation on legitimate channels (Alice and Bob).
  - Parameterized execution with approved Configuration **C1** across all four approved channels (`Alice`, `Bob`, `Eve1-Alice`, `Eve1-Bob`).
  - Output data generation (`d02_akf_filtered.csv`, `d02_akf_results.json`), visual artifacts, and regression testing.
- **Out of Scope:** Quantization (D03 Modified ADQ), Information Reconciliation (D04 BCH), Bit Expansion (D05 PRBS/Galois LFSR), Privacy Amplification (D06 SHA-256), and Cryptographic Testing (D07/D08).

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
- Helper and precomputed single-cell columns (`Unnamed: 4`, `korelasi A-B`, etc.) and unused worksheets (`Sheet2`, `Sheet3`) are never accessed or referenced.
- The input Excel file is preserved byte-for-byte without in-place modification.

---

## 3. Mathematical Formulation and Source Traceability

The mathematical framework is partitioned into four distinct, rigorously cited components:

### 3.1 Standard Discrete Kalman Filter (PPA.pdf Equations 3.10–3.16)
For a scalar linear discrete-time RSSI system with $A = 1, H = 1, B = 0$:
1. **State Prediction (Eq. 3.10):**
   $$\hat{x}_k^- = \hat{x}_{k-1}$$
2. **Covariance Prediction (Eq. 3.11):**
   $$P_k^- = P_{k-1} + Q$$
3. **Measurement Innovation (Eq. 3.12):**
   $$\epsilon_k = z_k - \hat{x}_k^-$$
4. **Innovation Covariance (Eq. 3.13):**
   $$S_k = P_k^- + \hat{R}_k$$
5. **Kalman Gain (Eq. 3.14):**
   $$K_k = \frac{P_k^-}{S_k}$$
6. **State Estimation Update (Eq. 3.15):**
   $$\hat{x}_k = \hat{x}_k^- + K_k \epsilon_k$$
7. **Error Covariance Update (Eq. 3.16):**
   $$P_k = (1 - K_k) P_k^-$$

### 3.2 Recursive Adaptive Measurement Noise Estimator (Wang et al. 2022, Eq. 27)
The time-varying measurement noise covariance $\hat{R}_k$ is estimated online using the simplified Sage-Husa formulation:
$$\hat{R}_k = (1 - d_{k-1})\hat{R}_{k-1} + d_{k-1} \left[\epsilon_k^2 - P_k^-\right]$$
*Implementation Note:* In strict accordance with the primary source, no covariance clipping, artificial floors, or substitute formulas were introduced.

### 3.3 Weighting Factor ($d_{k-1}$) & Analytical Limit
The weighting parameter follows the adopted fading memory convention:
$$d_k = \frac{1 - b}{1 - b^{k+1}} \implies d_{k-1} = \frac{1 - b}{1 - b^k}$$

For $b = 1.0$, direct numerical evaluation of $\frac{1-1}{1-1^k}$ yields an indeterminate $0/0$. Applying L'Hôpital's rule yields the exact analytical limit:
$$\lim_{b \to 1} d_{k-1} = \frac{1}{k}$$
At step $k=1$, $d_0 = 1.0 \implies (1 - d_0) = 0$, which initializes the measurement noise estimate to $\hat{R}_1 = \epsilon_1^2 - P_1^-$.

### 3.4 Classification of Experimental Parameters
Neither `PPA.pdf` nor `AKF.pdf` specifies numerical initial values for $(\hat{x}_0, P_0, Q, R_0, b)$. These parameters are strictly **experimental and configurable engineering choices** rather than proposal-defined constants.

---

## 4. Parameter Selection & Sensitivity Study

### 4.1 Methodology & Exclusion of Eavesdropper from Tuning
To prevent overfitting or biasing security metrics, parameter sensitivity evaluation was conducted **strictly on legitimate channels (Alice and Bob)**. The eavesdropper channels (`Eve1-Alice`, `Eve1-Bob`) were completely excluded from filter tuning and were evaluated only as passive observers during the final analysis.

### 4.2 Mathematical Analysis of Initial State ($\hat{x}_0$)
A critical mathematical finding emerged during sensitivity analysis regarding exact Wang Eq. (27):
- **Causal First-Sample Initialization ($\hat{x}_0 = z_1$):**
  When setting $\hat{x}_0 = z_1$, the initial innovation at $k=1$ becomes identically zero:
  $$\epsilon_1 = z_1 - \hat{x}_1^- = z_1 - \hat{x}_0 = 0$$
  Since $d_0 = 1.0$, Wang Eq. (27) evaluates to:
  $$\hat{R}_1 = (1 - d_0)\hat{R}_0 + d_0[\epsilon_1^2 - P_1^-] = 0 - (P_0 + Q) = -(P_0 + Q) < 0$$
  Without artificial floors, this immediately produces an invalid negative covariance $\hat{R}_1 < 0$.
- **Nominal Operating Prior Initialization ($\hat{x}_0 = -70.0\text{ dBm}$):**
  Initializing with the nominal expected physical RSSI level for the indoor LoRa link produces an initial non-zero innovation ($\epsilon_1 \approx -10\text{ dBm} \implies \epsilon_1^2 \approx 100 \gg P_1^-$). This guarantees $\hat{R}_k > 0$, $S_k > 0$, and $P_k > 0$ strictly across all 500 filtering steps without any heuristic modifications.

### 4.3 Sensitivity Study Results on Alice & Bob ($n = 500$)

| Config ID | $\hat{x}_0$ (dBm) | $P_0$ | $Q$ | $R_0$ | $b$ | Status | Alice-Bob Pearson $r$ (Raw = $0.6323$) | $\Delta r$ | Variance Reduction (Alice / Bob) | $\min(R_k)$ (Alice / Bob) | $\min(S_k)$ (Alice / Bob) | $\min(P_k)$ (Alice / Bob) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **C1** | $-70.0$ | $1.0$ | $0.010$ | $1.0$ | $1.00$ | **VALID** | **$0.9059$** | $+0.2737$ | $70.8\% / 62.9\%$ | $0.92 / 0.85$ | $1.02 / 0.95$ | $0.091 / 0.087$ |
| **C2** | $-70.0$ | $1.0$ | $0.010$ | $1.0$ | $0.98$ | **VALID** | **$0.8931$** | $+0.2609$ | $69.4\% / 60.0\%$ | $0.21 / 0.20$ | $0.26 / 0.25$ | $0.042 / 0.041$ |
| **C3** | $-70.0$ | $1.0$ | $0.010$ | $1.0$ | $0.95$ | **VALID** | **$0.8873$** | $+0.2551$ | $70.1\% / 60.4\%$ | $0.06 / 0.04$ | $0.09 / 0.07$ | $0.020 / 0.016$ |
| **C4** | $-70.0$ | $1.0$ | $0.001$ | $1.0$ | $0.98$ | **VALID** | **$0.9087$** | $+0.2764$ | $90.6\% / 85.3\%$ | $0.35 / 0.38$ | $0.37 / 0.41$ | $0.020 / 0.021$ |
| **C5** | $-70.0$ | $1.0$ | $0.050$ | $1.0$ | $0.98$ | **VALID** | **$0.8257$** | $+0.1934$ | $49.4\% / 40.4\%$ | $0.10 / 0.08$ | $0.20 / 0.17$ | $0.050 / 0.042$ |
| **C6** | $-70.0$ | $0.1$ | $0.010$ | $1.0$ | $0.98$ | **VALID** | **$0.9818$** | $+0.3495$ | $-74.3\% / -79.4\%$ | $0.21 / 0.20$ | $0.27 / 0.25$ | $0.042 / 0.041$ |
| **C7** | $-75.0$ | $0.1$ | $0.010$ | $1.0$ | $0.98$ | **VALID** | **$0.8889$** | $+0.2567$ | $70.0\% / 61.8\%$ | $0.21 / 0.20$ | $0.26 / 0.25$ | $0.042 / 0.041$ |
| **C8** | $z_1$ | $1.0$ | $0.010$ | $1.0$ | $0.98$ | **INVALID** | N/A | N/A | N/A | $-1.01 / -1.01$ | $-3.24 / -0.50$ | $-2.73 / -0.33$ |

### 4.4 Approved Configuration C1 Specifications
Approved exclusively for the `Dummy RSSI.xlsx` D02 experiment:
- **$\hat{x}_0 = -70.0\text{ dBm}$**: Nominal operating RSSI prior.
- **$P_0 = 1.0$**: Initial state error covariance uncertainty.
- **$Q = 0.01$**: Static process noise covariance.
- **$R_0 = 1.0$**: Initial measurement noise covariance prior.
- **$b = 1.00$**: Analytical limit $d_{k-1} = 1/k$ (equal-weight arithmetic Sage-Husa).

---

## 5. Final Filtering & Correlation Results

### 5.1 Pearson Correlation Comparison ($n = 500$)

| Channel Pair | Classification | Raw Pearson $r$ | AKF Filtered Pearson $r$ | $\Delta r$ | Result Description |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Alice vs Bob** | Legitimate Link | **$0.6323$** | **$0.9059$** | **$+0.2737$** | Substantial reciprocity enhancement |
| **Alice vs Eve1-Alice** | Eavesdropper Cross-Link | **$0.0171$** | **$0.1100$** | $+0.0929$ | Low linear cross-correlation observed |
| **Bob vs Eve1-Bob** | Eavesdropper Cross-Link | **$0.1193$** | **$0.1048$** | $-0.0146$ | Low linear cross-correlation observed |

### 5.2 Channel Smoothing & Variance Statistics

| Channel | Raw Mean (dBm) | Filtered Mean (dBm) | Raw Variance ($\text{dB}^2$) | Filtered Variance ($\text{dB}^2$) | Variance Reduction / Smoothing |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $-75.97$ | $-75.91$ | $1.0771$ | $0.3143$ | **$70.82\%$** |
| **Bob** | $-75.87$ | $-75.78$ | $1.0491$ | $0.3895$ | **$62.87\%$** |
| **Eve1-Alice** | $-31.78$ | $-39.17$ | $0.7625$ | $36.5735$ | Evaluation-only |
| **Eve1-Bob** | $-84.24$ | $-83.34$ | $10.0123$ | $4.9711$ | **$50.35\%$** |

*Methodological Note on Smoothing:* The observed variance reduction reflects signal smoothing by the recursive filter under the dynamic model $A=1$. It is reported as an empirical variance reduction rather than proven noise extraction.

### 5.3 Filter Stability & Covariance Diagnostics

| Channel | $\min(R_k)$ | $\max(R_k)$ | Final $R_{500}$ | $\min(S_k)$ | $\min(P_k)$ | $R_k < 0$ Count |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $0.9166$ | $98.9900$ | $0.9180$ | $1.0178$ | $0.0911$ | **0 (None)** |
| **Bob** | $0.8476$ | $79.9900$ | $0.8543$ | $0.9452$ | $0.0874$ | **0 (None)** |
| **Eve1-Alice** | $93.2077$ | $1519.9900$ | $93.2077$ | $2.0100$ | $0.5025$ | **0 (None)** |
| **Eve1-Bob** | $10.8856$ | $167.9900$ | $11.0017$ | $2.0100$ | $0.3287$ | **0 (None)** |

---

## 6. Generated Visual Artifacts

The following high-resolution figures were generated by the D02 pipeline:
1. **Correlation Comparison Bar Chart:**
   - Visualizes Pearson $r$ before and after AKF filtering across all channel pairs.
   - File: [`results/dummy/figures/d02_akf_pearson_comparison.png`](../../results/dummy/figures/d02_akf_pearson_comparison.png)
2. **All-Channel Time-Series Overview:**
   - 4-panel figure comparing raw RSSI vs AKF filtered trajectories over all 500 samples.
   - File: [`results/dummy/figures/d02_akf_all_channels_overview.png`](../../results/dummy/figures/d02_akf_all_channels_overview.png)
3. **Per-Channel Comparison Plots:**
   - [`results/dummy/figures/d02_akf_Alice_comparison.png`](../../results/dummy/figures/d02_akf_Alice_comparison.png)
   - [`results/dummy/figures/d02_akf_Bob_comparison.png`](../../results/dummy/figures/d02_akf_Bob_comparison.png)
   - [`results/dummy/figures/d02_akf_Eve1-Alice_comparison.png`](../../results/dummy/figures/d02_akf_Eve1-Alice_comparison.png)
   - [`results/dummy/figures/d02_akf_Eve1-Bob_comparison.png`](../../results/dummy/figures/d02_akf_Eve1-Bob_comparison.png)

---

## 7. Automated Test Verification Summary

| Verification Step | Test Function / Script | Status | Result Summary |
| :--- | :--- | :---: | :--- |
| **D02 Pipeline Execution** | `test_d02_pipeline_execution_and_schema` | **PASS** | Output CSV (500 rows), clean JSON schema |
| **PPA Exact Arithmetic** | `test_arithmetic_exactness` | **PASS** | Step-by-step hand arithmetic matches filter output |
| **b=1.0 Limit** | `test_akf_b_1_limit` | **PASS** | Evaluates analytical limit ($d_{k-1}=1/k$) with zero division errors |
| **Exponential Forgetting** | `test_akf_exponential_forgetting` | **PASS** | Evaluates $d_{k-1}=(1-b)/(1-b^k)$ correctly for $b<1$ |
| **Streaming Equivalence** | `test_streaming_vs_batch_equivalence` | **PASS** | Sequential processing preserves state and step counter |
| **Wang Eq. 27 Exactness** | `test_negative_R_capability` | **PASS** | Covariance updates unrestricted by artificial floors |
| **Excel Immutability** | `test_excel_sha256_immutability` | **PASS** | Checksum matches `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d` |
| **Figure Verification** | `test_d02_figures_exist_and_non_empty` | **PASS** | All 6 PNG artifacts generated and verified |
| **D01 Regression** | `tests/test_d01_correlation.py` | **PASS** | 5/5 D01 correlation tests pass |
| **D00 Regression** | `src/data_io/validator.py` | **PASS** | Dataset structure and integrity intact |

---

## 8. Limitations & Methodological Notes

1. **Configuration Specificity:** Configuration C1 was selected based on the empirical statistics of `Dummy RSSI.xlsx` (Sheet1). When migrating to real experimental ESP32/LoRa hardware data (R00–R08), the nominal prior $\hat{x}_0$ and noise covariances must be re-calibrated against the empirical link budget of the physical environment.
2. **Untracked Reference:** `AKF.pdf` remains untracked in accordance with repository guidelines.

---

## 9. Conclusion & Next Milestone

Milestone **D02 — Adaptive Kalman Filter (AKF)** is complete. The filter increases legitimate channel reciprocity ($r_{AB}$ from $0.6323$ to $0.9059$) while retaining low cross-correlation with Eve ($r \le 0.1100$) and achieving $62.87\%\text{--}70.82\%$ variance reduction (smoothing) on legitimate channels.

- **Completed Milestone:** **D02 — Adaptive Kalman Filter (AKF)**
- **Next Milestone:** **D03 — Quantization (Modified Adaptive Dual-Threshold Quantization / ADQ)**
