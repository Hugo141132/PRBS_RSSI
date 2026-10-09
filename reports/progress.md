# Project Progress Tracker: RSSI PRBS SKG

## Project Overview
Physical Layer Secret Key Generation (SKG) using wireless Received Signal Strength Indicator (RSSI) preprocessing, Adaptive Quantization, Galois LFSR PRBS Expansion, BCH Error Correction, and SHA-256 Privacy Amplification for ESP32/LoRa platforms.

---

## Roadmap & Milestone Status

| Phase | Milestone | Description | Status | Report / Output Deliverable |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy Pipeline** | **D00** | **Dummy RSSI Data Validation** | **COMPLETED** | [`reports/dummy/D00_data_validation.md`](dummy/D00_data_validation.md), [`results/dummy/validation_results.json`](../results/dummy/validation_results.json) |
| **Dummy Pipeline** | **D01** | **Pearson Correlation Baseline** | **COMPLETED** | [`reports/dummy/D01_pearson_correlation.md`](dummy/D01_pearson_correlation.md), [`results/dummy/d01_pearson_correlation.json`](../results/dummy/d01_pearson_correlation.json) |
| **Dummy Pipeline** | **D02** | **Modified Sage-Husa Kalman Filter** | **COMPLETED** | [`reports/dummy/D02_modified_sage_husa_kalman_filter.md`](dummy/D02_modified_sage_husa_kalman_filter.md), [`results/dummy/d02_mshkf_filtered.csv`](../results/dummy/d02_mshkf_filtered.csv) |
| **Dummy Pipeline** | **D03** | **Modified Adaptive Dual-Threshold Quantization (ADQ)** | **COMPLETED** | [`reports/dummy/D03_modified_adaptive_dual_threshold_quantization.md`](dummy/D03_modified_adaptive_dual_threshold_quantization.md), [`results/dummy/d03_quantized_bits.csv`](../results/dummy/d03_quantized_bits.csv) |
| **Dummy Pipeline** | **D04.0**| **Pure Galois LFSR PRBS Bit Expansion** | **COMPLETED** | [`reports/dummy/D04_galois_lfsr_expansion.md`](dummy/D04_galois_lfsr_expansion.md), [`results/dummy/d04_expanded_bits.csv`](../results/dummy/d04_expanded_bits.csv) |
| Dummy Pipeline | **D04.1**| **BCH / Information Reconciliation** | **NEXT TASK** | Pending |
| Dummy Pipeline | D05 | Galois LFSR Expansion (Post-Reconciliation) | PENDING | Pending |
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

### D02 — Modified Sage-Husa Adaptive Kalman Filter (MSHAKF) Preprocessing
- **Status:** COMPLETED (PASS)
- **Methodology:** Implemented pure **Modified Sage-Husa Adaptive Kalman Filter (MSHAKF)** based strictly on Wang et al. (2022) / `AKF.pdf` (Eqs. 1–7, 26, 27). Completely eliminated extraneous Gustafson-Kessel fuzzy clustering.
- **Canonical Files:** Source in [`src/analysis/mshkf.py`](../src/analysis/mshkf.py), runner in [`src/analysis/d02_runner.py`](../src/analysis/d02_runner.py), full documentation in [`reports/dummy/D02_modified_sage_husa_kalman_filter.md`](dummy/D02_modified_sage_husa_kalman_filter.md).
- **Approved Configuration:** Configuration C1 ($x_0 = z_0 + 2.0\text{ dBm}, P_0 = 1.0, Q = 0.001, b = 0.98, r_0 = 0.0, R_0 = 1.0$).
- **Key Results ($n=500$):**
  - Legitimate channel reciprocity increased from $r = 0.6323 \rightarrow 0.9172$ ($\Delta r = +0.2849$, $+45.0\%$ increase).
  - Eavesdropper cross-correlations: `Alice vs Eve1-Alice` ($r = 0.1496$), `Bob vs Eve1-Bob` ($r = -0.0961$).
  - Variance reduction / signal smoothing: Alice ($92.34\%$), Bob ($88.89\%$), Eve1-Alice ($92.83\%$), Eve1-Bob ($97.86\%$).
  - Covariance stability verified: $R_k > 0, P_k > 0, S_k > 0$ across all 500 samples (0 negative instances).
- **Verification:** All 25 tests pass (`pytest`), Excel SHA-256 unchanged, 500-sample alignment preserved.
- **Deliverables:** [`results/dummy/d02_mshkf_filtered.csv`](../results/dummy/d02_mshkf_filtered.csv), [`results/dummy/d02_mshkf_results.json`](../results/dummy/d02_mshkf_results.json), figures in `results/dummy/figures/d02/`.

### D03 — Modified Adaptive Dual-Threshold Quantization (ADQ)
- **Status:** COMPLETED (PASS)
- **Methodology:** Implemented **Modified Adaptive Dual-Threshold Quantization (ADQ)** following LoRa-PRIME (*IEEE OJ-COMS 2026, Section IV-C*). Adaptively computes dual thresholds $q^+ = \mu + \alpha\sigma$ and $q^- = \mu - \alpha\sigma$, discretizing filtered RSSI into 3 distinct symbols ($\{0, 1, 2\}$) while preserving intermediate samples ($q^- \le X \le q^+$) as Level 1 to achieve $100\%$ sample retention ($0\%$ discarded).
- **Direct Multi-Bit Mapping:**
  - 2-bit Gray Code: Level $0 \mapsto \text{'00'}$, Level $1 \mapsto \text{'01'}$, Level $2 \mapsto \text{'11'}$.
  - 4-bit LoRa-PRIME Code: Level $0 \mapsto \text{'1010'}$, Level $1 \mapsto \text{'1011'}$, Level $2 \mapsto \text{'1001'}$.
  - Both 2-bit and 4-bit bitstreams are direct mappings from the same underlying symbol sequence (not converted or padded from each other).
- **Excel Text Formatting:** Exported CSV bit sequence columns formatted explicitly with Excel text formulas (`="00"`, `="01"`, `="1010"`) to prevent integer truncation and preserve leading zeros in Microsoft Excel.
- **Key Results ($\alpha = 0.5$, $n=500$ samples):**
  - **Sample Retention:** $500/500$ ($100.0\%$) across all channels; $0$ discarded samples.
  - **Legitimate Channel (`Alice vs Bob`):**
    - 2-bit Modified ADQ: $\text{KAR} = \mathbf{0.8840}$ ($884/1000$ bits full stream, $116$ mismatches), $\text{BER} = 0.1160$. (Note: initial D03 report Table 4.2 documented $\text{KAR} = 0.8430$ / $157$ mismatches from earlier pre-C1 D02 iterations before commit `9043f14` raised filtered reciprocity to $r = 0.9172$).
    - 4-bit Modified ADQ: $\text{KAR} = \mathbf{0.9420}$ ($1884/2000$ bits full stream, $116$ mismatches), $\text{BER} = 0.0580$. (Initial D03 report noted $0.9215$ / $157$ mismatches).
  - **Descriptive Eavesdropper Comparison:**
    - `Alice vs Eve1-Alice`: 2-bit $\text{KAR} = 0.5880$, 4-bit $\text{KAR} = 0.7940$.
    - `Bob vs Eve1-Bob`: 2-bit $\text{KAR} = 0.5470$, 4-bit $\text{KAR} = 0.7735$.
    - In this dataset, legitimate agreement substantially exceeds measured eavesdropper links (descriptive trace comparison rather than universal security proof).
  - **Key Generation Rate (KGR):** 2.0 bits/sample ($1000$ bits) for 2-bit; 4.0 bits/sample ($2000$ bits) for 4-bit.
- **Verification:** 12/12 D03 tests pass; 25 baseline tests pass. 0 SkyGlow / baseline quantizer references.
- **Deliverables:** [`results/dummy/d03_quantized_bits.csv`](../results/dummy/d03_quantized_bits.csv), [`results/dummy/d03_quantization_results.json`](../results/dummy/d03_quantization_results.json), figures in `results/dummy/figures/d03/`, full report in [`reports/dummy/D03_modified_adaptive_dual_threshold_quantization.md`](dummy/D03_modified_adaptive_dual_threshold_quantization.md).

### D04.0 — Per-Sample Pure Galois LFSR PRBS Bit Expansion
- **Status:** COMPLETED (PASS)
- **Active Architecture (Per-Sample Pure Galois LFSR):**
  - *Methodology:* Each row in [`results/dummy/d03_quantized_bits.csv`](../results/dummy/d03_quantized_bits.csv) (500 samples per channel) directly seeds an independent Galois LFSR. The LFSR state is strictly reset before every sample. Excludes sample concatenation, padding, remapping, hashing, scrambling, and BCH/D05.
  - *Polynomial & Expansion Specifications ($m = 2^L - 1$ Full Period):*
    - 2-bit seed $\rightarrow$ 3 output bits ($1.5\times$): Degree 2, $P(x) = x^2 + x + 1$ (taps $\{2, 1, 0\}$, mask `0b11`, period 3).
    - 4-bit seed $\rightarrow$ 15 output bits ($3.75\times$): Degree 4, $P(x) = x^4 + x + 1$ (taps $\{4, 1, 0\}$, mask `0b0011`, period 15).
    - Both use left shift (`<< 1`), MSB output before register update, and `msb_first` seed bit order.
  - *Coverage & Tail:* **100% sample coverage with 0 omitted tail bits** ($500 \times 3 = 1,500$ bits for 2-bit; $500 \times 15 = 7,500$ bits for 4-bit).
  - *Symbol Mappings & Pairwise Hamming Distances:*
    - 2-bit: Level 0 (`"00"`) $\mapsto$ `"000"` (zero seed), Level 1 (`"01"`) $\mapsto$ `"011"`, Level 2 (`"11"`) $\mapsto$ `"101"`. Invariant: $d_H(0, 1) = d_H(0, 2) = d_H(1, 2) = \mathbf{2}$.
    - 4-bit: Level 0 (`"1010"`) $\mapsto$ `"101111000100110"`, Level 1 (`"1011"`) $\mapsto$ `"101011110001001"`, Level 2 (`"1001"`) $\mapsto$ `"100010011010111"`. Invariant: $d_H(0, 1) = d_H(0, 2) = d_H(1, 2) = \mathbf{8}$.
- **Key Measured Results (Active Per-Sample Full-Period Expansion, 500 Samples):**
  - **Sample-Level Agreement:** Alice vs Bob exact sample match is **$384 / 500$ ($76.80\%$)**. Mismatches: $116 / 500$ ($23.20\%$) consisting of 70 Level 0 $\leftrightarrow$ 1 and 46 Level 1 $\leftrightarrow$ 2.
  - **Zero Seeds:**
    - 2-bit: Alice = 133 ($26.6\%$), Bob = 179 ($35.8\%$), Eve1-Alice = 189 ($37.8\%$), Eve1-Bob = 171 ($34.2\%$). Preserved and flagged; outputs `"000"`.
    - 4-bit: Exactly **0 zero seeds** across all channels.
  - **Legitimate Channel (`Alice vs Bob`):**
    - 2-bit ADQ (2b $\rightarrow$ 3b, 1,500 bits): Pre-expansion $\text{KAR} = \mathbf{0.8840}$ ($\text{BER} = 0.1160$) $\longrightarrow$ Post-expansion $\text{KAR} = \mathbf{0.8453}$ ($\text{BER} = 0.1547$). (Exact closed form: $1,268$ matching bits, $232$ errors).
    - 4-bit ADQ (4b $\rightarrow$ 15b, 7,500 bits): Pre-expansion $\text{KAR} = \mathbf{0.9420}$ ($\text{BER} = 0.0580$) $\longrightarrow$ Post-expansion $\text{KAR} = \mathbf{0.8763}$ ($\text{BER} = 0.1237$). (Exact closed form: $6,572$ matching bits, $928$ errors).
  - **Eavesdropper Links:**
    - `Alice vs Eve1-Alice`: 2-bit Post $\text{KAR} = 0.5680$ ($\text{BER} = 0.4320$); 4-bit Post $\text{KAR} = 0.6544$ ($\text{BER} = 0.3456$).
    - `Bob vs Eve1-Bob`: 2-bit Post $\text{KAR} = 0.5373$ ($\text{BER} = 0.4627$); 4-bit Post $\text{KAR} = 0.6299$ ($\text{BER} = 0.3701$).
- **Historical Benchmarks:**
  - $2\times$ per-sample expansion (4b & 8b outputs) preserved in results JSON under `"historical_2x_persample"`.
  - 32-bit blockwise expansion preserved in [`results/dummy/d04_historical_32bit_expanded_bits.csv`](../results/dummy/d04_historical_32bit_expanded_bits.csv) and results JSON under `"historical_32bit_blockwise"`.
- **Technical & Scientific Distinctions:**
  - Choosing $m = 2^L - 1$ is a pipeline engineering design choice, not a mandated formula from Galois.pdf.
  - Repeated seeds produce repeated patterns; bit expansion increases stream length, not secret physical entropy.
  - Correctness of algebraic LFSR transitions is distinct from cryptographic randomness, secrecy, and unverified downstream BCH reconciliation feasibility.
- **Verification:** 21/21 D04 tests pass; 46/46 full regression suite pass (`pytest -v`). Upstream D03 CSV SHA-256 hash verified unmodified.
- **Deliverables:** Source in [`src/analysis/lfsr.py`](../src/analysis/lfsr.py), runner in [`src/analysis/d04_runner.py`](../src/analysis/d04_runner.py), [`results/dummy/d04_galois_lfsr_results.json`](../results/dummy/d04_galois_lfsr_results.json), [`results/dummy/d04_expanded_bits.csv`](../results/dummy/d04_expanded_bits.csv), [`results/dummy/d04_historical_32bit_expanded_bits.csv`](../results/dummy/d04_historical_32bit_expanded_bits.csv), figures in `results/dummy/figures/d04/`, full report in [`reports/dummy/D04_galois_lfsr_expansion.md`](dummy/D04_galois_lfsr_expansion.md).

---

## Current Project Status
- **Completed Milestones:** D00 (Data Validation), D01 (Pearson Correlation Baseline), D02 (Adaptive Kalman Filter Preprocessing), D03 (Modified Adaptive Dual-Threshold Quantization), D04.0 (Pure Galois LFSR PRBS Bit Expansion)
- **Next Active Milestone:** **D04.1 — BCH / Information Reconciliation**
