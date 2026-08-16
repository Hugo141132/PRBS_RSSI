# Project Progress Tracker: RSSI PRBS SKG

## Project Overview
RSSI-based Physical Layer Secret Key Generation using PRBS/Galois LFSR on ESP32/LoRa.

---

## Roadmap & Milestone Status

| Phase | Milestone | Description | Status | Report / Output |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy Pipeline** | **D00** | **Dummy RSSI Data Validation** | **COMPLETED** | [`reports/dummy/D00_data_validation.md`](dummy/D00_data_validation.md), [`results/dummy/validation_results.json`](../results/dummy/validation_results.json) |
| **Dummy Pipeline** | **D01** | **Pearson Correlation Analysis** | **COMPLETED** | [`reports/dummy/D01_pearson_correlation.md`](dummy/D01_pearson_correlation.md), [`results/dummy/d01_pearson_correlation.json`](../results/dummy/d01_pearson_correlation.json) |
| **Dummy Pipeline** | **D02** | **Adaptive Kalman Filter (AKF)** | **COMPLETED** | [`reports/dummy/D02_adaptive_kalman_filter.md`](dummy/D02_adaptive_kalman_filter.md), [`results/dummy/d02_akf_filtered.csv`](../results/dummy/d02_akf_filtered.csv) |
| Dummy Pipeline | **D03** | Quantization (Single/Double Threshold) | **NEXT TASK** | Pending |
| Dummy Pipeline | D04 | Information Reconciliation (BCH / Slepian-Wolf) | Pending | Pending |
| Dummy Pipeline | D05 | Randomness Enhancement (PRBS / Galois LFSR) | Pending | Pending |
| Dummy Pipeline | D06 | Privacy Amplification (SHA-256) | Pending | Pending |
| Dummy Pipeline | D07 | Key Verification & AES Encryption Demo | Pending | Pending |
| Dummy Pipeline | D08 | NIST SP 800-22 Randomness Testing | Pending | Pending |
| **Raw RSSI Pipeline** | R00–R08 | Real ESP32/LoRa Experimental Validation | Pending | Pending |

---

## Milestone Notes & Summary

### D00 — Dummy RSSI Data Validation
- **Status:** COMPLETED
- **Key Findings:** Verified `Sheet1` raw structure ($500$ rows $\times$ $4$ approved RSSI channels: `Alice`, `Bob`, `Eve1-Alice`, `Eve1-Bob`). Excluded precomputed helper columns (`Unnamed: 4`, `korelasi A-B`, etc.) and unused sheets (`Sheet2`, `Sheet3`). SHA-256 integrity verified: `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d`.

### D01 — Pearson Correlation Analysis
- **Status:** COMPLETED
- **Key Findings:** Baseline reciprocity established on raw data over $n=500$ samples:
  - Legitimate channel (`Alice vs Bob`): $r = 0.6323$
  - Eavesdropper channels: `Alice vs Eve1-Alice` ($r = 0.0171$), `Bob vs Eve1-Bob` ($r = 0.1193$).

### D02 — Adaptive Kalman Filter (AKF) Preprocessing
- **Status:** COMPLETED
- **Selected Configuration:** Configuration C1 ($\hat{x}_0 = -70.0\text{ dBm}, P_0 = 1.0, Q = 0.01, R_0 = 1.0, b = 1.00$ with analytical limit $d_{k-1} = 1/k$).
- **Key Findings:**
  - Legitimate channel reciprocity increased from $r = 0.6323 \rightarrow 0.9059$ ($\Delta r = +0.2737$).
  - Eavesdropper cross-correlations remained low: `Alice vs Eve1-Alice` ($r = 0.1100$), `Bob vs Eve1-Bob` ($r = 0.1048$).
  - Signal variance reduction / smoothing: Alice ($70.82\%$), Bob ($62.87\%$).
  - Zero negative covariances ($R_k < 0$) across all channels; output length ($500$) and Excel hash preserved.
  - Report & Data: [`reports/dummy/D02_adaptive_kalman_filter.md`](dummy/D02_adaptive_kalman_filter.md), [`results/dummy/d02_akf_filtered.csv`](../results/dummy/d02_akf_filtered.csv), [`results/dummy/d02_akf_results.json`](../results/dummy/d02_akf_results.json).

---

## Current Status
- **Completed:** D00 (Data Validation), D01 (Pearson Correlation), D02 (Adaptive Kalman Filter)
- **Next Milestone:** D03 — Quantization (Modified Adaptive Dual-Threshold Quantization / ADQ)
