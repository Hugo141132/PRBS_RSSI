# D02.2 — Empirical Parameter Calibration for Adaptive Kalman Filter (AKF) Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-08-28
- **Milestone:** D02.2 — Empirical Parameter Calibration for Adaptive Kalman Filter (AKF) Preprocessing
- **Baseline Preserved:** Milestone D02 remains the fixed baseline; D03 is not executed.

---

## 1. Objective and Methodological Framework

Milestone **D02.2** replaces the heuristic, uniform Configuration C1 initial priors from D02 ($x_0 = z_0 + 2.0\text{ dBm}, P_0 = 1.0, Q = (0.001, 0.010), b = (1.00, 0.98), r_0 = 0.0, R_0 = 1.0$) with **empirically grounded, data-driven parameters** calculated independently for each of the four raw RSSI channels: `Alice`, `Bob`, `Eve1-Alice`, and `Eve1-Bob`.

### 1.1 Temporal Calibration / Evaluation Split
To prevent in-sample overfitting and data leakage during parameter tuning:
- **Calibration Prefix ($N_{\text{cal}} = 300$, $60\%$):** Sample indices $k = 0 \dots 299$.
- **Held-out Evaluation Set ($N_{\text{eval}} = 200$, $40\%$):** Sample indices $k = 300 \dots 499$.
- Parameter calibration is strictly confined to the calibration prefix. The reference state $x_{\text{ref}}$ is constructed solely within $k = 0 \dots 299$ without backward smoothing across the calibration boundary.

### 1.2 Preservation of Non-Target D02 Pipeline
The core state-space model ($\Phi=1, H=1, B=0$), Gustafson-Kessel fuzzy feature definition ($f_k = [z_k, \Delta z_k, \sigma_k]^T$), Mahalanobis metric, membership equations, cluster growth logic, and covariance safeguards are preserved identically to D02. Specifically:
- **Active Clusters & Growth Ceiling:** Initial active clusters $c = 2$, maximum cluster capacity $c_{\text{max}} = 5$.
- **Cluster Covariance Prototypes:**
  $$F_0 = \operatorname{diag}([2.0, 1.0, 0.5]), \quad F_1 = \operatorname{diag}([5.0, 4.0, 1.5])$$
- **Cluster Radii:** $\text{radius}_0 = 3.0, \text{radius}_1 = 4.0$.
- **Fuzzy Hyperparameters:** Fuzzification coefficient $m = 2.0$, learning rate $\eta = 0.05$, window size $w = 5$, minimum cluster support $N_{\text{min\_pts}} = 15$.
- **Initial Cluster Centers:** Consequentially initialized from the newly calibrated channel state prior $x_0$:
  $$v_0 = [x_0, 0.0, 0.3]^T, \quad v_1 = [x_0, 2.0, 1.5]^T$$

---

## 2. Mathematical Formulation & Calibration Derivation

### 2.1 Backward Rauch-Tung-Striebel (RTS) Reference Construction
Using first-pass D02 posterior state estimates $\hat{x}_{k|k}$, covariances $P_{k|k}$, and first-pass process covariances $Q_{\text{ref}}[k] = Q_k^{\text{D02}}$:
$$x_{\text{ref}}[N_{\text{cal}}-1] = \hat{x}[N_{\text{cal}}-1|N_{\text{cal}}-1]$$
$$x_{\text{ref}}[k] = \hat{x}[k|k] + \frac{P[k|k]}{P[k|k] + Q_{\text{ref}}[k]} \left(x_{\text{ref}}[k+1] - \hat{x}[k|k]\right), \quad \text{for } k = N_{\text{cal}}-2 \text{ down to } 0$$
Using $Q_{\text{ref}}[k] = Q_k^{\text{D02}}$ guarantees the reference construction is non-circular.

### 2.2 Independent Parameter Estimation Formulas
1. **Initial State Prior ($x_0$):**
   $$x_0 = \frac{1}{N_{\text{cal}}} \sum_{k=0}^{N_{\text{cal}}-1} x_{\text{ref}}[k]$$
2. **Initial Estimation Error Covariance ($P_0$):**
   $$P_0 = \frac{1}{N_{\text{cal}}-1} \sum_{k=0}^{N_{\text{cal}}-1} (x_{\text{ref}}[k] - x_0)^2$$
3. **Measurement Reference Residuals ($e_k$):**
   $$e_k = z_k - x_{\text{ref}}[k], \quad k = 0, \dots, N_{\text{cal}}-1$$
4. **Initial Measurement Noise Mean Prior ($r_0$):**
   $$r_0 = \frac{1}{N_{\text{cal}}} \sum_{k=0}^{N_{\text{cal}}-1} e_k$$
5. **Initial Measurement Noise Covariance Prior ($R_0$):**
   $$R_0 = \frac{1}{N_{\text{cal}}-1} \sum_{k=0}^{N_{\text{cal}}-1} (e_k - r_0)^2$$
6. **Regime-Separated Process Noise Covariances ($Q_{\text{stable}}, Q_{\text{dynamic}}$):**
   $$q_k = x_{\text{ref}}[k+1] - x_{\text{ref}}[k], \quad k = 0, \dots, N_{\text{cal}}-2$$
   $$Q_{\text{stable}} = \frac{1}{N_S - 1} \sum_{k \in S} (q_k - \bar{q}_S)^2, \quad Q_{\text{dynamic}} = \frac{1}{N_D - 1} \sum_{k \in D} (q_k - \bar{q}_D)^2$$
   where $S = \{k \mid \text{cluster}_k = 0\}$ and $D = \{k \mid \text{cluster}_k = 1\}$ from the D02 fuzzy regime history.
7. **Forgetting Factors ($b_{\text{stable}}, b_{\text{dynamic}}$):**
   Determined via deterministic grid search over $b_{\text{stable}} \in [0.90, 0.999]$ and $b_{\text{dynamic}} \in [0.70, 0.98]$ subject to $0 < b_{\text{dynamic}} < b_{\text{stable}} < 1$, minimizing the root-mean-square error against the calibration reference:
   $$\text{RMSE}(b_{\text{stable}}, b_{\text{dynamic}}) = \sqrt{\frac{1}{N_{\text{cal}}} \sum_{k=0}^{N_{\text{cal}}-1} (\hat{x}_{k|k} - x_{\text{ref}}[k])^2}$$

---

## 3. Calibrated Per-Signal Parameter Table

All four channels were calibrated completely independently on the calibration prefix ($N_{\text{cal}} = 300$):

| Parameter | Notation | Alice | Bob | Eve1-Alice | Eve1-Bob |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Initial State Mean** | $x_0$ (dBm) | $-77.1372$ | $-76.1474$ | $-29.9309$ | $-82.3838$ |
| **Initial Error Variance** | $P_0$ | $0.0583$ | $0.1130$ | $0.0363$ | $0.3148$ |
| **Measurement Noise Mean** | $r_0$ (dBm) | $+1.0939$ | $+0.1908$ | $-1.8691$ | $-1.5429$ |
| **Measurement Noise Var** | $R_0$ | $0.8219$ | $0.6798$ | $0.7839$ | $8.7203$ |
| **Stable Process Noise** | $Q_{\text{stable}}$ | $0.000134$ | $0.000232$ | $0.000041$ | $0.000130$ |
| **Dynamic Process Noise** | $Q_{\text{dynamic}}$ | $0.000650$ | $0.001237$ | $0.000505$ | $0.000610$ |
| **Stable Forgetting Factor** | $b_{\text{stable}}$ | $0.92$ | $0.90$ | $0.99$ | $0.90$ |
| **Dynamic Forgetting Factor**| $b_{\text{dynamic}}$ | $0.90$ | $0.88$ | $0.98$ | $0.70$ |
| **Calibration Transitions ($N_S / N_D$)** | $N_S, N_D$ | $272 / 27$ | $254 / 45$ | $257 / 42$ | $198 / 101$ |
| **Tuning RMSE vs $x_{\text{ref}}$** | RMSE (dBm) | $0.1468$ | $0.2113$ | $0.1477$ | $0.5084$ |

*Verification:* For every signal, $P_0, R_0, Q_{\text{stable}}, Q_{\text{dynamic}} > 0$, $N_S \ge 2$, $N_D \ge 2$, and $0 < b_{\text{dynamic}} < b_{\text{stable}} < 1$.

*Grid Boundary Status ($b_{\text{stable}} \in [0.90, 0.999]$, $b_{\text{dynamic}} \in [0.70, 0.98]$):*
- **Alice:** $b_S = 0.92$ (Interior), $b_D = 0.90$ (Interior).
- **Bob:** $b_S = 0.90$ (Lower boundary hit at $0.90$), $b_D = 0.88$ (Interior).
- **Eve1-Alice:** $b_S = 0.99$ (Interior), $b_D = 0.98$ (Upper boundary hit at $0.98$).
- **Eve1-Bob:** $b_S = 0.90$ (Lower boundary hit at $0.90$), $b_D = 0.70$ (Lower boundary hit at $0.70$).

---

## 4. Pearson Correlation Analysis: Raw vs. D02 vs. D02.2

### 4.1 Full Dataset Evaluation ($n = 500$)

| Channel Pair | Raw RSSI ($r_{\text{raw}}$) | D02 Baseline ($r_{\text{D02}}$) | D02.2 Calibrated ($r_{\text{D02.2}}$) | $\Delta r$ (vs. Raw) | $\Delta r$ (vs. D02) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice vs. Bob (Legitimate)** | **$0.6323$** | **$0.8612$** | **$0.8824$** | **$+0.2501$** | **$+0.0212$** |
| **Alice vs. Eve1-Alice (Eavesdropper)** | $0.0171$ | $-0.1013$ | $-0.0492$ | $-0.0663$ | $+0.0520$ |
| **Bob vs. Eve1-Bob (Eavesdropper)** | $0.1193$ | $0.0722$ | $0.1654$ | $+0.0461$ | $+0.0931$ |

### 4.2 Primary Out-of-Sample Evaluation: Held-out Test Split ($n = 200$, Samples 300–500)

| Channel Pair | Raw RSSI ($r_{\text{raw}}$) | D02 Baseline ($r_{\text{D02}}$) | D02.2 Calibrated ($r_{\text{D02.2}}$) | $\Delta r$ (vs. Raw) | $\Delta r$ (vs. D02) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice vs. Bob (Legitimate)** | **$0.6802$** | **$0.8445$** | **$0.7423$** | **$+0.0620$** | **$-0.1022$** |
| **Alice vs. Eve1-Alice (Eavesdropper)** | $0.0365$ | $-0.0059$ | $0.2407$ | $+0.2043$ | $+0.2466$ |
| **Bob vs. Eve1-Bob (Eavesdropper)** | $0.3628$ | $0.3149$ | $0.2737$ | $-0.0891$ | $-0.0413$ |

---

## 5. Variance and Signal Smoothing Statistics

### 5.1 Full-Trace Statistics ($n=500$)

| Channel | Raw Mean (dBm) | Raw Var | Filtered Mean (dBm) | Filtered Var | Variance Reduction |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $-75.970$ | $1.0771$ | $-77.105$ | $0.0156$ | **$98.55\%$** |
| **Bob** | $-75.870$ | $1.0491$ | $-76.101$ | $0.0396$ | **$96.23\%$** |
| **Eve1-Alice** | $-31.782$ | $0.7625$ | $-29.990$ | $0.0306$ | **$95.98\%$** |
| **Eve1-Bob** | $-84.236$ | $10.0123$ | $-82.054$ | $0.0468$ | **$99.53\%$** |

### 5.2 Held-out Evaluation Statistics ($n=200$, Samples 300–500)

| Channel | Raw Mean (dBm) | Raw Var | Filtered Mean (dBm) | Filtered Var | Variance Reduction |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alice** | $-75.860$ | $1.1904$ | $-77.080$ | $0.0099$ | **$99.17\%$** |
| **Bob** | $-75.740$ | $1.1724$ | $-76.108$ | $0.0161$ | **$98.63\%$** |
| **Eve1-Alice** | $-31.755$ | $0.5950$ | $-30.033$ | $0.0571$ | **$90.41\%$** |
| **Eve1-Bob** | $-84.700$ | $9.6000$ | $-81.948$ | $0.0360$ | **$99.62\%$** |

---

## 6. Filter Stability and Convergence Diagnostics

Across all 500 samples for all four channels:
- **Strict Covariance Positivity:** $R_k > 0, P_k > 0, S_k > 0$ maintained throughout (zero negative instances).
- **Online Noise Adaptation:**
  - Alice: $\min(R) = 0.0526, \max(R) = 15.5966, R_{\text{final}} = 0.6979, r_{\text{final}} = +1.4151\text{ dBm}$
  - Bob: $\min(R) = 0.0183, \max(R) = 9.1484, R_{\text{final}} = 1.0293, r_{\text{final}} = +0.4418\text{ dBm}$
  - Eve1-Alice: $\min(R) = 0.3570, \max(R) = 2.3677, R_{\text{final}} = 0.4414, r_{\text{final}} = -1.7343\text{ dBm}$
  - Eve1-Bob: $\min(R) = 0.0027, \max(R) = 41.5012, R_{\text{final}} = 12.4604, r_{\text{final}} = -5.3011\text{ dBm}$
- **Fuzzy Partition Coefficient ($PC$):**
  - Alice: $PC = 0.7630$ (Cluster 0: 431 samples, Cluster 1: 69 samples)
  - Bob: $PC = 0.7686$ (Cluster 0: 404 samples, Cluster 1: 96 samples)

---

## 7. Comparative Assessment: Does D02.2 Improve or Worsen D02?

### 7.1 Key Empirical Findings
1. **Mathematical Grounding:** Eliminates heuristic C1 priors ($z_0+2, P_0=1.0, Q=(0.001, 0.010), b=(1.00, 0.98)$). Parameters are derived from first-principles RTS reference residuals and regime-specific process covariances.
2. **Channel Independence:** Reflects distinct physical transceiver characteristics (e.g. Eve1-Bob's high measurement noise variance $R_0 = 8.7203$ vs Alice's $0.8219$).
3. **Full-Trace Reciprocity:** On the full 500-sample dataset, D02.2 improves legitimate Alice–Bob correlation from Raw $0.6323$ and D02 $0.8612$ to **$0.8824$** ($\Delta r = +0.0212$ over D02, $+0.2501$ over Raw).

### 7.2 Primary Out-of-Sample Evaluation (Held-Out Test Split, Samples 300–500)
1. **Held-out Generalization:** On the primary held-out evaluation set ($k = 300 \dots 499$), D02.2 improves legitimate Alice–Bob correlation over Raw ($r = 0.7423$ vs Raw $0.6802$), but **underperforms D02** ($r = 0.8445$). This occurs because D02.2 estimates smaller process noise covariances ($Q \approx 10^{-4}$ vs D02's uniform $10^{-3}$), which imposes heavier smoothing (variance reduction $>98\%$) and tracks the rapid fluctuations in the second half of the trace more sluggishly.
2. **Eavesdropper Isolation:** On the held-out split, while Bob vs Eve1-Bob correlation decreases ($r = 0.2737$ vs Raw $0.3628$ and D02 $0.3149$), Alice vs Eve1-Alice correlation increases to $0.2407$ (worse than D02's $-0.0059$).

### 7.3 Methodological Conclusion
- **D02.2 improves full-trace Alice–Bob correlation;**
- **On the primary held-out evaluation, D02.2 improves over Raw but underperforms D02;**
- **Alice–Eve held-out correlation is worse than D02;**
- **Therefore, D02.2 is an empirical-calibration comparison, not an overall performance improvement over D02.**

---

## 8. Artifacts and Generated Deliverables

- **Filtered Data:** [`results/dummy/d02_2_mshkf_filtered.csv`](../../results/dummy/d02_2_mshkf_filtered.csv) (500 aligned rows $\times$ 8 columns)
- **Structured Results:** [`results/dummy/d02_2_mshkf_results.json`](../../results/dummy/d02_2_mshkf_results.json)
- **Standalone D02.2 Figures (`results/dummy/figures/d02_2/`):**
  - Full channel comparison plots: `results/dummy/figures/d02_2/d02_2_mshkf_Alice_comparison.png`, `d02_2_mshkf_Bob_comparison.png`, `d02_2_mshkf_Eve1-Alice_comparison.png`, `d02_2_mshkf_Eve1-Bob_comparison.png`
  - All channels overview: `results/dummy/figures/d02_2/d02_2_mshkf_all_channels_overview.png`
  - Pearson comparison (Raw vs D02.2): `results/dummy/figures/d02_2/d02_2_mshkf_pearson_comparison.png`
  - Scatter & Overlay diagnostics: `results/dummy/figures/d02_2/d02_2_mshkf_rssi_correlation_scatter.png`, `d02_2_mshkf_signal_overlay_comparison.png`, `d02_2_mshkf_fuzzy_diagnostics.png`
- **Full-Trace Comparison Figures (Raw vs D02 vs D02.2 in `results/dummy/figures/d02_vs_d02_2/`):**
  - 3-Way Pearson comparison: `results/dummy/figures/d02_vs_d02_2/d02_vs_d02_2_pearson_comparison.png`
  - 4-Channel all-in-one trajectory overview: `results/dummy/figures/d02_vs_d02_2/d02_vs_d02_2_all_channels_overview.png`
  - Per-channel 3-way trajectory comparisons: `results/dummy/figures/d02_vs_d02_2/d02_vs_d02_2_Alice_comparison.png`, `d02_vs_d02_2_Bob_comparison.png`, `d02_vs_d02_2_Eve1-Alice_comparison.png`, `d02_vs_d02_2_Eve1-Bob_comparison.png`

---

## 9. Automated Test Suite & Verification Results

The entire project test suite was executed to verify D02.2 compliance, numerical precision, and non-regression of D00/D01/D02 baselines:

```powershell
.venv\Scripts\pytest tests/ -v
```

### Test Suite Execution Summary (24/24 Passed)
- **`tests/test_d01_correlation.py` (5 tests):**
  - `test_raw_columns_only_loaded` — PASSED
  - `test_independent_pearson_calculation` — PASSED
  - `test_json_results_schema_and_values` — PASSED
  - `test_dataset_regression_sanity_check` — PASSED
  - `test_figures_generated_and_non_empty` — PASSED
- **`tests/test_d02_mshkf.py` (9 tests):**
  - `test_mshkf_initialization` — PASSED
  - `test_fuzzy_clustering_equations` — PASSED
  - `test_fuzzy_cluster_growth_on_regime_shift` — PASSED
  - `test_sage_husa_arithmetic_exactness` — PASSED
  - `test_b_1_limit_and_fading` — PASSED
  - `test_streaming_vs_batch_equivalence` — PASSED
  - `test_d02_pipeline_execution_and_schema` — PASSED
  - `test_excel_sha256_immutability` — PASSED
  - `test_d02_figures_exist_and_non_empty` — PASSED
- **`tests/test_d02_2_calibration.py` (10 tests):**
  - `test_rts_backward_recursion_mathematical_exactness` — PASSED
  - `test_independent_per_signal_parameter_sets` — PASSED
  - `test_covariance_parameters_finite_and_non_negative` — PASSED
  - `test_b_ordering_constraint` — PASSED
  - `test_no_hardcoded_c1_priors_reused` — PASSED
  - `test_d02_2_pipeline_outputs_and_schema` — PASSED
  - `test_deterministic_reruns` — PASSED
  - `test_excel_sha256_unmodified` — PASSED
  - `test_d02_2_figures_exist_and_non_empty` — PASSED
  - `test_d02_vs_d02_2_comparison_figures_exist_and_non_empty` — PASSED

**Integrity Verification:**
- Raw input Excel SHA-256 hash: `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d` (100% byte-for-byte unmodified).
