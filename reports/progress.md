# Project Progress Tracker: RSSI PRBS SKG

## Project Overview
Physical Layer Secret Key Generation (SKG) using wireless Received Signal Strength Indicator (RSSI) preprocessing, Adaptive Quantization, BCH Error Correction, Galois LFSR PRBS Expansion, and SHA-256 Privacy Amplification for ESP32/LoRa platforms.

---

## Roadmap & Milestone Status

| Phase | Milestone | Description | Status | Report / Output Deliverable |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy Pipeline** | **D00** | **Dummy RSSI Data Validation** | **COMPLETED** | [`reports/dummy/D00_data_validation.md`](dummy/D00_data_validation.md), [`results/dummy/validation_results.json`](../results/dummy/validation_results.json) |
| **Dummy Pipeline** | **D01** | **Pearson Correlation Baseline** | **COMPLETED** | [`reports/dummy/D01_pearson_correlation.md`](dummy/D01_pearson_correlation.md), [`results/dummy/d01_pearson_correlation.json`](../results/dummy/d01_pearson_correlation.json) |
| **Dummy Pipeline** | **D02** | **Modified Sage-Husa Kalman Filter** | **COMPLETED** | [`reports/dummy/D02_modified_sage_husa_kalman_filter.md`](dummy/D02_modified_sage_husa_kalman_filter.md), [`results/dummy/d02_mshkf_filtered.csv`](../results/dummy/d02_mshkf_filtered.csv) |
| **Dummy Pipeline** | **D02.2** | **Empirical AKF Parameter Calibration** | **COMPLETED** | [`reports/dummy/D02_2_empirical_parameter_calibration.md`](dummy/D02_2_empirical_parameter_calibration.md), [`results/dummy/d02_2_mshkf_filtered.csv`](../results/dummy/d02_2_mshkf_filtered.csv) |
| Dummy Pipeline | **D03** | **Quantization (Single/Double Threshold)** | **NEXT TASK** | Pending |
| Dummy Pipeline | D04 | BCH / Information Reconciliation | PENDING | Pending |
| Dummy Pipeline | D05 | PRBS / Galois LFSR Randomness Enhancement | PENDING | Pending |
| Dummy Pipeline | D06 | SHA-256 Privacy Amplification | PENDING | Pending |
| Dummy Pipeline | D07 | Key Verification / AES Demo | PENDING | Pending |
| Dummy Pipeline | D08 | NIST SP 800-22 Randomness Testing | PENDING | Pending |
| **Raw RSSI Pipeline** | R00–R08 | Real ESP32/LoRa Experimental Validation | Pending | Pending |

---

## Milestone Notes & Summaries

### D00 — Dummy RSSI Data Validation
- **Status:** COMPLETED (PASS)
- **Key Findings:** Verified `Sheet1` raw structure ($500$ rows $\times$ $4$ approved RSSI channels: `Alice`, `Bob`, `Eve1-Alice`, `Eve1-Bob`). Excluded precomputed single-cell helper columns (`Unnamed: 4`, `korelasi A-B`, etc.) and unused sheets (`Sheet2`, `Sheet3`). SHA-256 integrity verified: `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d`.

### D01 — Pearson Correlation Analysis
- **Status:** COMPLETED (PASS)
- **Key Findings:** Baseline reciprocity established on raw data over $n=500$ samples:
  - Legitimate channel (`Alice vs Bob`): $r = 0.6323$
  - Eavesdropper channels: `Alice vs Eve1-Alice` ($r = 0.0171$), `Bob vs Eve1-Bob` ($r = 0.1193$).

### D02 — Adaptive Kalman Filter (AKF) Preprocessing
- **Status:** COMPLETED (PASS)
- **Methodology:** Implemented **Adaptive Kalman Filter (AKF)** equipped with online **Gustafson-Kessel Adaptive Fuzzy Clustering** (based on Wang et al. 2022 / PPA.pdf Sage-Husa formulation), operating on a 3D feature vector $[\text{RSSI}_k, \Delta\text{RSSI}_k, \sigma_k]$.
- **Canonical Files:** Source in [`src/analysis/mshkf.py`](../src/analysis/mshkf.py), runner in [`src/analysis/d02_runner.py`](../src/analysis/d02_runner.py), full documentation in [`reports/dummy/D02_modified_sage_husa_kalman_filter.md`](dummy/D02_modified_sage_husa_kalman_filter.md).
- **Approved Configuration:** Configuration C1 ($x_0 = z_0 + 2.0\text{ dBm}, P_0 = 1.0, Q_{\text{regimes}} = (0.001, 0.010), b_{\text{regimes}} = (1.00, 0.98), r_0 = 0.0, R_0 = 1.0$).
- **Key Results ($n=500$):**
  - Legitimate channel reciprocity increased from $r = 0.6323 \rightarrow 0.8612$ ($\Delta r = +0.2289$).
  - Eavesdropper cross-correlations: `Alice vs Eve1-Alice` ($r = -0.1013$), `Bob vs Eve1-Bob` ($r = 0.0722$).
  - Variance reduction / signal smoothing: Alice ($80.06\%$), Bob ($75.61\%$), Eve1-Alice ($84.85\%$), Eve1-Bob ($92.74\%$).
  - Covariance stability verified: $R_k > 0, P_k > 0, S_k > 0$ across all 500 samples (0 negative instances).
  - Fuzzy Partition Coefficient ($PC$): Alice ($0.9859$), Bob ($0.9880$).
- **Ablation Comparison:**
  - Raw RSSI: $r_{AB} = 0.6323, r_{AE1} = 0.0171$
  - Static KF ($Q=0.01, R=1.0$): $r_{AB} = 0.9238, r_{AE1} = 0.0187$
  - AKF without Fuzzy ($Q=0.001$): $r_{AB} = 0.9282, r_{AE1} = 0.1336$
  - Adaptive Kalman Filter (AKF - Proposed C1): $r_{AB} = 0.8612, r_{AE1} = -0.1013$
- **Verification:** 14/14 tests pass (`pytest -v`), Excel SHA-256 unchanged, 500-sample alignment preserved.
- **Deliverables:** [`results/dummy/d02_mshkf_filtered.csv`](../results/dummy/d02_mshkf_filtered.csv), [`results/dummy/d02_mshkf_results.json`](../results/dummy/d02_mshkf_results.json), figures in `results/dummy/figures/d02/`.

### D02.2 — Empirical AKF Parameter Calibration
- **Status:** COMPLETED (PASS)
- **Purpose:** Replaces the heuristic, uniform Configuration C1 initial priors from D02 with data-driven empirical parameter calibration derived independently for each of the four RSSI channels (`Alice`, `Bob`, `Eve1-Alice`, `Eve1-Bob`).
- **Temporal Calibration / Held-out Split:**
  - First 60% ($k = 0 \dots 299$, $N_{\text{cal}} = 300$): Calibration prefix used for RTS reference construction and parameter estimation.
  - Last 40% ($k = 300 \dots 499$, $N_{\text{eval}} = 200$): Held-out evaluation split for unbiased out-of-sample testing.
  - Reference trajectory $x_{\text{ref}}$ constructed strictly inside $k = 0 \dots 299$ using Rauch-Tung-Striebel (RTS) backward recursion anchored at $x_{\text{ref}}[299] = \hat{x}[299|299]$ with non-circular $Q_{\text{ref}}[k] = Q_k^{\text{D02}}$. No backward smoothing across the split boundary.
- **Calibrated Parameters (Independent per channel):**
  - $x_0 = \text{mean}(x_{\text{ref}})$
  - $P_0 = \text{Var}(x_{\text{ref}})$
  - $e_k = z_k - x_{\text{ref}}[k]$, $r_0 = \text{mean}(e_k)$, $R_0 = \text{Var}(e_k - r_0)$
  - $q_k = x_{\text{ref}}[k+1] - x_{\text{ref}}[k]$, $Q_{\text{stable}} = \text{Var}_{k \in S}(q_k)$, $Q_{\text{dynamic}} = \text{Var}_{k \in D}(q_k)$
  - $(b_{\text{stable}}, b_{\text{dynamic}})$ optimized via bounded grid search minimizing RMSE against $x_{\text{ref}}$ over the calibration prefix.
- **Preserved Non-Target Fuzzy Pipeline:**
  - $c = 2$ initial active clusters, $c_{\text{max}} = 5$ cluster growth ceiling.
  - Covariance prototypes: $F_0 = \text{diag}([2.0, 1.0, 0.5]), F_1 = \text{diag}([5.0, 4.0, 1.5])$.
  - Cluster radii: $\text{radius}_0 = 3.0, \text{radius}_1 = 4.0$.
  - Hyperparameters: $m = 2.0, \eta = 0.05, w = 5, N_{\text{min\_pts}} = 15$.
  - Initial centers shifted consistently with calibrated $x_0$: $v_0 = [x_0, 0.0, 0.3]^T, v_1 = [x_0, 2.0, 1.5]^T$.
- **Key Correlation Results:**
  - **Full-Trace ($n=500$):**
    - Legitimate channel (`Alice vs Bob`): Raw $r = 0.6323 \rightarrow$ D02 $r = 0.8612 \rightarrow$ D02.2 $r = \mathbf{0.8824}$ ($\Delta r = +0.2501$ vs Raw, $+0.0212$ vs D02).
    - Eavesdropper channels: `Alice vs Eve1-Alice` ($r = -0.0492$), `Bob vs Eve1-Bob` ($r = 0.1654$).
  - **Primary Held-Out Evaluation ($n=200$, Samples 300–500):**
    - Legitimate channel (`Alice vs Bob`): Raw $r = 0.6802 \rightarrow$ D02 $r = \mathbf{0.8445} \rightarrow$ D02.2 $r = 0.7423$ ($\Delta r = +0.0620$ vs Raw, $-0.1022$ vs D02).
    - Eavesdropper channels: `Alice vs Eve1-Alice` ($r = 0.2407$), `Bob vs Eve1-Bob` ($r = 0.2737$).
- **Methodological Conclusion:**
  - D02.2 improves over Raw on held-out legitimate reciprocity ($0.7423$ vs $0.6802$), but underperforms D02 ($0.8445$).
  - D02.2 is an empirical-calibration comparison rather than an overall performance improvement over D02.
- **Verification:** 24/24 tests pass (`pytest -v`), 500 samples/channel alignment preserved, deterministic reruns verified, Excel SHA-256 unchanged.
- **Deliverables:** [`results/dummy/d02_2_mshkf_filtered.csv`](../results/dummy/d02_2_mshkf_filtered.csv), [`results/dummy/d02_2_mshkf_results.json`](../results/dummy/d02_2_mshkf_results.json), standalone figures in `results/dummy/figures/d02_2/`, comparison figures in `results/dummy/figures/d02_vs_d02_2/`.

---

## Current Project Status
- **Completed Milestones:** D00 (Data Validation), D01 (Pearson Correlation Baseline), D02 (Adaptive Kalman Filter Preprocessing), D02.2 (Empirical AKF Parameter Calibration)
- **Next Active Milestone:** **D03 — Quantization (Single/Double Threshold Quantization)**
