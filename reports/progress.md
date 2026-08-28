# Project Progress Tracker: RSSI PRBS SKG

## Project Overview
Physical Layer Secret Key Generation (SKG) using wireless Received Signal Strength Indicator (RSSI) preprocessing, Adaptive Quantization, BCH Error Correction, Galois LFSR PRBS Expansion, and SHA-256 Privacy Amplification for ESP32/LoRa platforms.

---

## Roadmap & Milestone Status

| Phase | Milestone | Description | Status | Report / Output Deliverable |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy Pipeline** | **D00** | **Dummy RSSI Data Validation** | **COMPLETED** | [`reports/dummy/D00_data_validation.md`](dummy/D00_data_validation.md), [`results/dummy/validation_results.json`](../results/dummy/validation_results.json) |
| **Dummy Pipeline** | **D01** | **Pearson Correlation Analysis** | **COMPLETED** | [`reports/dummy/D01_pearson_correlation.md`](dummy/D01_pearson_correlation.md), [`results/dummy/d01_pearson_correlation.json`](../results/dummy/d01_pearson_correlation.json) |
| **Dummy Pipeline** | **D02** | **Adaptive Kalman Filter (AKF)** | **COMPLETED** | [`reports/dummy/D02_modified_sage_husa_kalman_filter.md`](dummy/D02_modified_sage_husa_kalman_filter.md), [`results/dummy/d02_mshkf_filtered.csv`](../results/dummy/d02_mshkf_filtered.csv) |
| Dummy Pipeline | **D03** | Quantization (Single/Double Threshold) | **NEXT TASK** | Pending |
| Dummy Pipeline | D04 | Information Reconciliation (BCH / Slepian-Wolf) | Pending | Pending |
| Dummy Pipeline | D05 | Randomness Enhancement (PRBS / Galois LFSR) | Pending | Pending |
| Dummy Pipeline | D06 | Privacy Amplification (SHA-256) | Pending | Pending |
| Dummy Pipeline | D07 | Key Verification & AES Encryption Demo | Pending | Pending |
| Dummy Pipeline | D08 | NIST SP 800-22 Randomness Testing | Pending | Pending |
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
- **Deliverables:** [`results/dummy/d02_mshkf_filtered.csv`](../results/dummy/d02_mshkf_filtered.csv), [`results/dummy/d02_mshkf_results.json`](../results/dummy/d02_mshkf_results.json), figures in `results/dummy/figures/`.

---

## Current Project Status
- **Completed Milestones:** D00 (Data Validation), D01 (Pearson Correlation Baseline), D02 (Adaptive Kalman Filter Preprocessing)
- **Next Active Milestone:** **D03 — Quantization (Modified Adaptive Dual-Threshold Quantization / ADQ)**
