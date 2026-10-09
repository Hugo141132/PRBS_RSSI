# D03 — Modified Adaptive Dual-Threshold Quantization (ADQ) Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-10-02
- **Task:** D03 — Modified Adaptive Dual-Threshold Quantization (ADQ) for RSSI Secret Key Generation

---

## 1. Objective and Methodological Framework

Milestone **D03** implements the channel feature quantization stage of the Physical Layer Secret Key Generation (SKG) pipeline, transforming continuous Kalman-filtered RSSI sequences from Milestone **D02** into discrete cryptographic bit sequences.

### 1.1 Methodological Framework & Lineage
The quantization engine follows strictly the **Modified Adaptive Dual-Threshold Quantization (ADQ)** scheme formulated by **Anisah et al. (2026)** (*"LoRa-PRIME: A Novel Secret Key Generation Framework Based on Periodic Bit Reversal and Modified Adaptive Quantization for Robust Cooperative Jamming LoRa Relay Networks"*, IEEE Open Journal of the Communications Society, Vol. 7, pp. 2664–2683).

- **Core Module:** [`src/analysis/quantization.py`](../../src/analysis/quantization.py)
  - `ModifiedAdaptiveDualThresholdQuantizer`: Implements adaptive dual thresholds $q^+$ and $q^-$ with 3-level symbol mapping and intermediate sample retention.
  - Multi-bit encoding engines: 2-bit Gray coding and 4-bit LoRa-PRIME representation.
  - Metrics: `compute_key_agreement_rate` (KAR, Eq. 7), `compute_bit_error_rate` (BER), and `compute_key_generation_rate` (KGR).
- **Pipeline Runner:** [`src/analysis/d03_runner.py`](../../src/analysis/d03_runner.py)
  - Executes end-to-end quantization on D02 filtered RSSI for all 4 channels (`Alice`, `Bob`, `Eve1-Alice`, `Eve1-Bob`).
  - Evaluates both 2-bit and 4-bit encodings.
  - Performs sensitivity analysis across sensitivity multiplier $\alpha \in [0.1, 1.0]$.
- **Verification Suite:** [`tests/test_d03_quantization.py`](../../tests/test_d03_quantization.py) (12 automated tests covering deterministic behavior, mathematical threshold calculation, encoding tables, sample retention, edge cases, and end-to-end pipeline sanity).

### 1.2 Purpose of Quantization in SKG
1. Map correlated analog channel features ($\text{RSSI}_{\text{Filtered}}$) into discrete symbol alphabets $\{0, 1, 2\}$.
2. Convert discrete symbols into raw initial binary keys ($K_A, K_B$) before downstream Information Reconciliation (D04 / BCH).
3. Maximize legitimate Key Agreement Rate (KAR) between Alice and Bob while maintaining near-chance KAR ($\approx 0.5$) against eavesdropper Eve1.
4. Eliminate sample discarding inherent in conventional dual-threshold quantizers to achieve higher Key Generation Rates (KGR) and avoid information loss.

---

## 2. Input Dataset & Filtering Context

- **Source Input:** Filtered RSSI output from Milestone D02 ([`results/dummy/d02_mshkf_filtered.csv`](../../results/dummy/d02_mshkf_filtered.csv)).
- **Input Channels (Active MSHAKF Configuration C1):**
  - `Alice_Filtered` ($\mu = -77.287\text{ dBm}, \sigma = 0.287\text{ dBm}$)
  - `Bob_Filtered` ($\mu = -76.258\text{ dBm}, \sigma = 0.341\text{ dBm}$)
  - `Eve1-Alice_Filtered` ($\mu = -29.878\text{ dBm}, \sigma = 0.234\text{ dBm}$)
  - `Eve1-Bob_Filtered` ($\mu = -82.435\text{ dBm}, \sigma = 0.463\text{ dBm}$)
- **Sample Length:** Exactly $N = 500$ aligned samples across all 4 channels.

---

## 3. Mathematical Formulation (LoRa-PRIME Section IV-C)

### 3.1 Adaptive Dual-Threshold Calculation (Eq. 4)
For a signal segment $X$ with local mean $\mu_X$ and standard deviation $\sigma_X$, upper threshold $q^+$ and lower threshold $q^-$ are adaptively calculated as:
$$q^+ = \mu_X + \alpha \cdot \sigma_X$$
$$q^- = \mu_X - \alpha \cdot \sigma_X$$
where $\alpha \ge 0$ is a configurable multiplier coefficient controlling threshold sensitivity to channel dynamics.

### 3.2 3-Level Quantization Mapping with Sample Retention (Eq. 5)
Unlike conventional ADQ schemes that drop samples between $q^-$ and $q^+$, Modified ADQ preserves intermediate samples as dedicated Level 1:
$$Q(X_i) = \begin{cases} 
0, & X_i < q^- \\ 
1, & q^- \le X_i \le q^+ \quad \text{(Intermediate samples retained)} \\ 
2, & X_i > q^+ 
\end{cases}$$

### 3.3 Multi-Bit Binary Encoding Schemes
Each quantized level is encoded into a multi-bit binary representation:
1. **2-Bit Gray Coding Representation:**
   $$\text{Level } 0 \mapsto \text{'00'}, \quad \text{Level } 1 \mapsto \text{'01'}, \quad \text{Level } 2 \mapsto \text{'11'}$$
   Adjacent level transitions differ by only 1 bit, minimizing bit mismatch from minor signal deviations.
2. **4-Bit LoRa-PRIME Representation:**
   $$\text{Level } 0 \mapsto \text{'1010'}, \quad \text{Level } 1 \mapsto \text{'1011'}, \quad \text{Level } 2 \mapsto \text{'1001'}$$
   Maps 3 levels into 4-bit cryptographic blocks, increasing Key Generation Rate (KGR) while maintaining structured bit separation.

### 3.4 Key Agreement Rate (KAR, Eq. 7) & Metrics
The initial Key Agreement Rate between Alice and Bob prior to reconciliation is defined as:
$$\text{KAR} = \frac{1}{n} \sum_{i=1}^n \mathbb{I}\left(K_A[i] == K_B[i]\right)$$
$$\text{BER} = 1.0 - \text{KAR}$$
$$\text{KGR}_{\text{bps}} = \frac{n_{\text{bits}}}{T_{\text{duration}}}, \quad \text{KGR}_{\text{sample}} = \frac{n_{\text{bits}}}{N_{\text{samples}}}$$

---

## 4. Experimental Results & Performance Analysis

### 4.1 Quantization Thresholds and Sample Distribution ($\alpha = 0.5$, $N=500$)

| Channel | Mean $\mu$ (dBm) | Std Dev $\sigma$ (dBm) | Lower $q^-$ (dBm) | Upper $q^+$ (dBm) | Level 0 ($< q^-$) | Level 1 (Interm.) | Level 2 ($> q^+$) | Retained Samples | Discarded Samples |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Alice** | -77.287 | 0.287 | -77.431 | -77.143 | 133 (26.6%) | 205 (41.0%) | 162 (32.4%) | **500 (100%)** | **0 (0%)** |
| **Bob** | -76.258 | 0.341 | -76.429 | -76.088 | 179 (35.8%) | 147 (29.4%) | 174 (34.8%) | **500 (100%)** | **0 (0%)** |
| **Eve1-Alice**| -29.878 | 0.234 | -29.995 | -29.761 | 189 (37.8%) | 131 (26.2%) | 180 (36.0%) | **500 (100%)** | **0 (0%)** |
| **Eve1-Bob** | -82.435 | 0.463 | -82.667 | -82.203 | 171 (34.2%) | 162 (32.4%) | 167 (33.4%) | **500 (100%)** | **0 (0%)** |

*Sample Retention:* Modified ADQ retains **$100\%$ ($500/500$)** of samples across all channels, avoiding data discarding.

### 4.2 Key Agreement Rate (KAR) Across Channel Pairs ($\alpha = 0.5$)

| Channel Pair | Link Type | 2-bit Modified ADQ KAR | 4-bit Modified ADQ KAR | Matching Bits (2b / 4b) | Mismatches (2b / 4b) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Alice vs Bob** | **Legitimate Reciprocal** | **0.8840** | **0.9420** | **884 / 1,884** | **116 / 116** |
| **Alice vs Eve1-Alice** | Eavesdropper | **0.5880** | **0.7940** | **588 / 1,588** | **412 / 412** |
| **Bob vs Eve1-Bob** | Eavesdropper | **0.5470** | **0.7735** | **547 / 1,547** | **453 / 453** |

> [!NOTE]
> **Historical Note on Prior Report Metrics (0.8430 / 0.9215):**
> An earlier version of this report documented Alice–Bob $\text{KAR} = 0.8430$ ($843/1000$ bits) for 2-bit and $0.9215$ ($1843/2000$ bits) for 4-bit, both with $157$ mismatches. That earlier baseline was computed against preliminary D02 filtering ($r \approx 0.86$) prior to commit `9043f14`. When commit `9043f14` upgraded D02 to pure MSHAKF Configuration C1 ($b=0.98, Q=0.001$, raising channel reciprocity to $r = 0.9172$), re-quantizing produced the current active metrics ($\text{KAR} = 0.8840$ / $0.9420$, $116$ mismatches) recorded above.

#### Descriptive Dataset-Specific Channel Comparison
- **Legitimate Reciprocity:** Under the active MSHAKF C1 filtered inputs, Alice and Bob achieve high initial agreement ($\text{KAR} = 88.40\%$ in 2-bit, $94.20\%$ in 4-bit, with exactly 116 bit mismatches).
- **Descriptive Comparison with Eavesdropper:** In this experimental dataset, the legitimate pair exhibits substantially higher agreement than the measured eavesdropper links (Alice vs Eve1-Alice: $58.80\%$ in 2-bit, $79.40\%$ in 4-bit; Bob vs Eve1-Bob: $54.70\%$ in 2-bit, $77.35\%$ in 4-bit). While this comparison demonstrates that the eavesdropper experiences significantly degraded bit agreement in this specific geometry, it is a descriptive observation on the collected traces rather than a formal proof of spatial decorrelation or universal physical-layer secrecy across arbitrary eavesdropper locations.

### 4.3 Sensitivity Analysis across Multiplier $\alpha$ (Alice vs Bob)

| $\alpha$ | 2-bit KAR | 4-bit KAR | Generated Bits (2b / 4b) | Retained Samples | Discarded Samples |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 0.1 | 0.8490 | 0.9245 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 0.2 | 0.8620 | 0.9310 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 0.3 | 0.8660 | 0.9330 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 0.4 | 0.8710 | 0.9355 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| **0.5 (Default)** | **0.8840** | **0.9420** | **1000 / 2000** | **500 (100%)** | **0 (0%)** |
| 0.6 | 0.9210 | 0.9605 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 0.7 | 0.9310 | 0.9655 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 0.8 | 0.9250 | 0.9625 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 0.9 | 0.9230 | 0.9615 | 1000 / 2000 | 500 (100%) | 0 (0%) |
| 1.0 | 0.9150 | 0.9575 | 1000 / 2000 | 500 (100%) | 0 (0%) |

---

## 5. Artifacts and Deliverables

1. **Python Modules:**
   - [`src/analysis/quantization.py`](../../src/analysis/quantization.py): Core quantizer class and metric functions.
   - [`src/analysis/d03_runner.py`](../../src/analysis/d03_runner.py): Pipeline execution runner.
   - [`src/analysis/visualization.py`](../../src/analysis/visualization.py): Threshold overlays, level distribution, symbol timeline, and KAR comparison charts.
   - [`src/analysis/__init__.py`](../../src/analysis/__init__.py): Package-level exports.
2. **Data & Results Artifacts:**
   - [`results/dummy/d03_quantized_bits.csv`](../../results/dummy/d03_quantized_bits.csv): Aligned quantization symbols and bit streams (2-bit and 4-bit) for all 500 samples across all 4 channels, formatted with Excel text formulas (`="00"`, `="01"`, `="1010"`) to guarantee *leading zeros* are preserved in Microsoft Excel.
   - [`results/dummy/d03_quantization_results.json`](../../results/dummy/d03_quantization_results.json): Complete machine-readable experimental metadata, threshold statistics, KAR/BER metrics, alpha sweeps, and KGR values.
3. **Publication-Ready Figures:**
   - `results/dummy/figures/d03/d03_adq_thresholds_overlay.png`: 4-panel time series showing filtered RSSI with adaptive threshold overlays and shaded Level 1 regions.
   - `results/dummy/figures/d03/d03_adq_symbol_timeline.png`: 4-panel timeline displaying discrete quantization symbols over the 500-sample index.
   - `results/dummy/figures/d03/d03_adq_levels_distribution.png`: Bar chart of Level 0, Level 1, and Level 2 sample distributions per channel.
   - `results/dummy/figures/d03/d03_kar_comparison.png`: Comparison of KAR across legitimate vs eavesdropper pairs for 2-bit and 4-bit Modified ADQ.


---

## 6. Verification and Regression Testing

- Automated test suite executed via `pytest`:
  - `tests/test_d01_correlation.py`: 5 passed.
  - `tests/test_d02_mshkf.py`: 9 passed.
  - `tests/test_d03_quantization.py`: 12 passed.
  - **Overall status:** **26 passed in 16.97s** (100% pass rate).
- Key test verifications:
  - Exact formula correctness of $q^+ = \mu + \alpha\sigma$ and $q^- = \mu - \alpha\sigma$.
  - 100% deterministic output on repeated executions.
  - Correct 2-bit Gray coding and 4-bit LoRa-PRIME bit mapping.
  - 100% sample retention across adaptive thresholds.
  - Robust handling of edge cases (constant signals, low variance, short/empty sequences).
  - Physical layer security property confirmed ($\text{KAR}_{AB} > \text{KAR}_{AE1}$).

---

## 7. Limitations and Next Milestone

### 7.1 Limitations
- **Raw Quantization Residual Bit Discrepancies:** While Modified ADQ achieves high initial KAR ($84.30\%$ for 2-bit, $92.15\%$ for 4-bit), there remain residual bit mismatches between Alice and Bob ($\approx 7.8\% - 15.7\%$ BER) due to channel non-reciprocity and noise.
- **Raw Key Entropy:** Direct quantized bit sequences derived from fading RSSI contain local temporal correlation (runs of identical symbols), necessitating error reconciliation and subsequent bit randomization.

### 7.2 Next Milestone: D04 — Information Reconciliation (BCH)
The subsequent pipeline stage will implement **Bose–Chaudhuri–Hocquenghem (BCH)** error correction coding (specifically $\text{BCH}(63, 30, t=6)$ as evaluated in LoRa-PRIME) to:
1. Divide quantized bit streams into non-overlapping blocks.
2. Generate syndrome vectors on Alice's side and transmit them to Bob over a public channel.
3. Correct up to $t=6$ bit errors per 63-bit block on Bob's side to achieve full bit agreement ($\text{KAR} = 100\%$).
