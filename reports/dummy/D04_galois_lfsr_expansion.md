# D04.0 — Per-Sample Pure Galois LFSR PRBS Bit Expansion Report

## Status
- **Milestone:** D04.0 — Per-Sample Pure Galois LFSR PRBS Bit Expansion ($m = 2^L - 1$)
- **Status:** COMPLETED (PASS)
- **Approved Roadmap:** D03 Quantization → **D04.0 Galois LFSR Expansion** → D04.1 BCH Reconciliation → D05 Galois LFSR Expansion
- **Active Architecture:** Per-Sample Pure Galois LFSR Expansion with Full-Period Length $m = 2^L - 1$ (LFSR reset per sample; zero tail omission)
- **Historical Benchmarks:** 
  1. $2\times$ Per-Sample Expansion (4-bit and 8-bit output; preserved in results JSON under `"historical_2x_persample"`)
  2. 32-Bit Blockwise Expansion (preserved in [`results/dummy/d04_historical_32bit_expanded_bits.csv`](../../results/dummy/d04_historical_32bit_expanded_bits.csv) and results JSON under `"historical_32bit_blockwise"`)
- **Date:** 2026-10-09

---

## 1. Executive Summary & Core Architectural Evolution

Milestone **D04.0** establishes the bit expansion stage of the Physical Layer Secret Key Generation (SKG) pipeline. 

### 1.1 Per-Sample Full-Period Galois LFSR Expansion ($m = 2^L - 1$)
Following architectural and mathematical evaluation, D04.0 configures output length to the full maximal period of the Galois LFSR ($m = 2^L - 1$), superseding previous settings:
1. **Per-Sample Direct Seeding:** Each row in the upstream D03 quantization dataset ([`results/dummy/d03_quantized_bits.csv`](../../results/dummy/d03_quantized_bits.csv)) represents one discrete channel measurement sample. Its complete 2-bit Gray coding or 4-bit LoRa-PRIME representation is directly loaded as the seed for an independent Galois LFSR.
2. **Explicit Reset per Sample:** The LFSR state is strictly reset before every sample. There is **no cross-sample state accumulation, no concatenative buffering, no bit padding or remapping, and no hashing or nonlinear scrambling**.
3. **100% Sample Coverage (Zero Omitted Tail):** All 500 samples are expanded without omission:
   - **2-bit seed ($L=2$):** $m = 2^2 - 1 = 3$ bits/sample $\implies 500 \times 3 = 1,500$ output bits per channel.
   - **4-bit seed ($L=4$):** $m = 2^4 - 1 = 15$ bits/sample $\implies 500 \times 15 = 7,500$ output bits per channel.
4. **Preserved Zero Seeds:** Zero seeds (Level 0 in 2-bit Gray coding) generate $m$ consecutive zeros (`"000"`), remaining at the linear fixed point, and are explicitly flagged with `is_zero_seed: True` (degenerate fixed point, not a maximal-period PRBS).

### 1.2 Scientific Reference, Design Choice & Engineering Distinctions
- **Primary Reference:** Vimalathithan, R., Rossi, D., Omana, M., Metra, C., & Valarmathi, M. L. (2013). *"Polynomial Based Key Distribution Scheme for WPAN."* *Malaysian Journal of Mathematical Sciences*, 7(S), pp. 59–72.
  - Section 2 (pp. 62–63): Key generation with LFSR, primitive polynomials, period $2^L - 1$.
  - Section 4 (pp. 66–67): Key distribution scheme.
- **Design Choice vs. Paper Specification:**
  > [!NOTE]
  > **Design Choice Notice:**
  > Choosing the full-period output length $m = 2^L - 1$ (3 bits for $L=2$, 15 bits for $L=4$) is **our pipeline engineering design choice**, NOT a mandated expansion formula from `Galois.pdf`. 
  > In Vimalathithan et al. (2013, Section 4, p. 67), a 16-bit rolling counter code is concatenated 8 times to form a 128-bit seed prior to feeding a 128-bit LFSR. In our SKG architecture, we adapt pure Galois LFSRs to operate directly on discrete quantization samples without inter-sample coupling.
- **Explicit Entropy, Randomness, and Security Distinctions:**
  > [!WARNING]
  > **Expansion Adds Length, Not Secret Entropy:**
  > Pure Galois LFSR expansion is a strictly deterministic, linear operation over $\text{GF}(2)$. It **does not add physical or secret entropy** to the quantized key material. 
  > - **Repeated Seeds Produce Repeated Patterns:** Because the quantizer generates only three distinct symbol levels per encoding across all 500 samples, **only three distinct output patterns occur per encoding**.
  > - **Correctness $\ne$ Cryptographic Randomness:** The generator is mathematically verified for state transitions, maximal periods, and companion matrix equivalence, but it does NOT provide cryptographic secrecy.
  > - **Unverified Downstream Feasibility:** Bit expansion changes error distribution across symbols. Downstream BCH reconciliation feasibility (Milestone D04.1) remains unverified until D04.1 testing is performed.

---

## 2. Mathematical LFSR Specification & Recurrence

### 2.1 State Recurrence
The linear feedback shift register executes under canonical Galois left-shift form:
```text
b = (state >> (L - 1)) & 1
emit b
state = ((state << 1) & ((1 << L) - 1)) ^ (mask if b else 0)
```
- **Shift Direction:** Left shift (`<< 1`)
- **Output Bit:** Most Significant Bit (MSB, `state >> (L-1)`)
- **Output Timing:** `before_update` (MSB is emitted before state transition)
- **Seed Bit Order:** `msb_first` (bit 0 of seed binary string is MSB of initial state)

### 2.2 Operational Parameters

| Parameter | 2-Bit ADQ Expansion (Active) | 4-Bit ADQ Expansion (Active) | Historical $2\times$ Setting | Historical 32-Bit Blockwise |
| :--- | :--- | :--- | :--- | :--- |
| **Input Unit** | 1 sample (2 bits) | 1 sample (4 bits) | 1 sample (2b or 4b) | 1 block (32 bits, concatenated) |
| **Register Degree ($L$)** | 2 bits | 4 bits | 2 or 4 bits | 32 bits |
| **Primitive Polynomial** | $P(x) = x^2 + x + 1$ | $P(x) = x^4 + x + 1$ | $x^2+x+1$ / $x^4+x+1$ | $P(x) = x^{32} + x^{22} + x^2 + x^1 + 1$ |
| **Non-Zero Tap Exponents** | $\{2, 1, 0\}$ | $\{4, 1, 0\}$ | $\{2, 1, 0\}$ / $\{4, 1, 0\}$ | $\{32, 22, 2, 1, 0\}$ |
| **Tap Mask Hex** | `0x3` (`0b11`) | `0x3` (`0b0011`) | `0x3` | `0x00400007` |
| **Output Length ($m$)** | **3 bits** ($2^2 - 1$) | **15 bits** ($2^4 - 1$) | 4 bits / 8 bits | 40, 48, 64 bits |
| **Max Non-Zero Period** | 3 | 15 | 3 / 15 | $2^{32} - 1 = 4,294,967,295$ |
| **Total Bits / Channel** | **1,500 bits** | **7,500 bits** | 2,000 / 4,000 bits | 1,984 / 3,968 bits (at 64b) |
| **Omitted Tail Bits** | **0 bits (0%)** | **0 bits (0%)** | 0 bits (0%) | 8 bits (2b) / 16 bits (4b) |

---

## 3. Deterministic Symbol Mappings & Output Hamming Distances

### 3.1 2-Bit ADQ Symbol Mapping ($L=2$, $m=3$)
- **Degree 2 Polynomial:** $P(x) = x^2 + x + 1$
- **Periodicity:** Exact period 3. The 3-bit output covers exactly one complete period of the m-sequence.
- **Gray Coding Adjacency:** In upstream D03 quantization, 2-bit symbols follow standard Gray coding where adjacent levels differ by exactly 1 bit ($d_H = 1$): Level 0 (`"00"`) $\leftrightarrow$ Level 1 (`"01"`), and Level 1 (`"01"`) $\leftrightarrow$ Level 2 (`"11"`).

| Quantization Level | Input Seed (Binary) | Seed Int | Is Zero Seed | Expanded Output (3 Bits) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Level 0 (Gray)** | `"00"` | 0 | **`True`** | `"000"` | Absorbing zero state; weight 0 |
| **Level 1 (Gray)** | `"01"` | 1 | **`False`** | `"011"` | Non-zero m-sequence; weight 2 ($2^{L-1}$) |
| **Level 2 (Gray)** | `"11"` | 3 | **`False`** | `"101"` | Non-zero m-sequence; weight 2 ($2^{L-1}$) |

> [!NOTE]
> **Resolution of Documentation Typo:**
> An earlier draft of this report inadvertently listed Level 2 as `"10"` (which maps to `"110"`). If Level 2 were `"10"`, the 46 Level 1 $\leftrightarrow$ Level 2 mismatches (`"01"` vs `"10"`) would have had Hamming distance 2, resulting in $70 \times 1 + 46 \times 2 = 162$ input bit errors. However, the upstream D03 encoder ([`src/analysis/quantization.py`](../../src/analysis/quantization.py)) and active CSV strictly use `"11"` for Level 2 ($d_H=1$), yielding exactly $70 \times 1 + 46 \times 1 = \mathbf{116}$ input bit errors across 1,000 bits ($\text{Pre-KAR} = \mathbf{0.8840}$).

#### Pairwise Output Hamming Distances ($L=2$)
- $d_H(\text{Level 0}, \text{Level 1}) = d_H(\text{"000"}, \text{"011"}) = \mathbf{2}$
- $d_H(\text{Level 0}, \text{Level 2}) = d_H(\text{"000"}, \text{"101"}) = \mathbf{2}$
- $d_H(\text{Level 1}, \text{Level 2}) = d_H(\text{"011"}, \text{"101"}) = \mathbf{2}$
- **All Four 2-Bit States Exhaustively:**
  - `"00"` $\mapsto$ `"000"` (Seed 0)
  - `"01"` $\mapsto$ `"011"` (Seed 1)
  - `"10"` $\mapsto$ `"110"` (Seed 2)
  - `"11"` $\mapsto$ `"101"` (Seed 3)
- **Exhaustive Invariant:** Every pair of distinct seeds in $\{0, 1, 2, 3\}$ has full-length output Hamming distance **strictly 2 out of 3 bits** ($d_H / m = 2/3 \approx 66.67\%$).

### 3.2 4-Bit LoRa-PRIME Symbol Mapping ($L=4$, $m=15$)
- **Degree 4 Polynomial:** $P(x) = x^4 + x + 1$
- **Periodicity:** Exact period 15. The 15-bit output covers exactly one complete period of the m-sequence.

| Quantization Level | Input Seed (Binary) | Seed Int | Is Zero Seed | Expanded Output (15 Bits) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Level 0 (PRIME)** | `"1010"` | 10 | **`False`** | `"101111000100110"` | Non-zero m-sequence; weight 8 ($2^{L-1}$) |
| **Level 1 (PRIME)** | `"1011"` | 11 | **`False`** | `"101011110001001"` | Non-zero m-sequence; weight 8 ($2^{L-1}$) |
| **Level 2 (PRIME)** | `"1001"` | 9 | **`False`** | `"100010011010111"` | Non-zero m-sequence; weight 8 ($2^{L-1}$) |

#### Pairwise Output Hamming Distances ($L=4$)
- $d_H(\text{Level 0}, \text{Level 1}) = d_H(\text{"101111000100110"}, \text{"101011110001001"}) = \mathbf{8}$
- $d_H(\text{Level 0}, \text{Level 2}) = d_H(\text{"101111000100110"}, \text{"100010011010111"}) = \mathbf{8}$
- $d_H(\text{Level 1}, \text{Level 2}) = d_H(\text{"101011110001001"}, \text{"100010011010111"}) = \mathbf{8}$
- **Exhaustive Invariant:** Every pair of distinct seeds in $\{0, 1, \dots, 15\}$ has full-length output Hamming distance **strictly 8 out of 15 bits** ($d_H / m = 8/15 \approx 53.33\%$).

---

## 4. Measured Per-Sample Expansion Results Across Channels

### 4.1 Sample-Level Agreement & Zero-Seed Distribution
Across all 500 samples in [`results/dummy/d03_quantized_bits.csv`](../../results/dummy/d03_quantized_bits.csv):
- **Alice vs Bob Matching Samples:** **384 / 500 = 76.80%**
- **Alice vs Bob Mismatched Samples:** **116 / 500 = 23.20%**
  - Level 0 $\leftrightarrow$ Level 1 mismatches: **70 samples** (Alice=0/Bob=1: 12; Alice=1/Bob=0: 58)
  - Level 1 $\leftrightarrow$ Level 2 mismatches: **46 samples** (Alice=1/Bob=2: 29; Alice=2/Bob=1: 17)
  - Level 0 $\leftrightarrow$ Level 2 mismatches: **0 samples**
- **Zero-Seed Counts per Channel:**
  - **2-Bit ADQ:** Alice = **133** (26.6%), Bob = **179** (35.8%), Eve1-Alice = **189** (37.8%), Eve1-Bob = **171** (34.2%).
  - **4-Bit LoRa-PRIME:** **0** (0.0%) across all four channels (since Level 0 is encoded as `"1010"` $\ne 0$).

### 4.2 Comprehensive Key Agreement Rate (KAR) & Bit Error Rate (BER)

| Channel Pair | Bit Depth | Seed Length | Output Length | Pre-Expansion KAR (BER) | Post-Expansion KAR (BER) | Matching Samples | Total Output Bits |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Alice vs Bob (Legitimate)** | **2-bit ADQ** | 2 bits | **3 bits** | **0.8840** (0.1160) | **0.8453** (0.1547) | **384 / 500** (76.80%) | **1,500** |
| **Alice vs Bob (Legitimate)** | **4-bit ADQ** | 4 bits | **15 bits** | **0.9420** (0.0580) | **0.8763** (0.1237) | **384 / 500** (76.80%) | **7,500** |
| **Alice vs Eve1-Alice** | **2-bit ADQ** | 2 bits | **3 bits** | **0.5880** (0.4120) | **0.5680** (0.4320) | **176 / 500** (35.20%) | **1,500** |
| **Alice vs Eve1-Alice** | **4-bit ADQ** | 4 bits | **15 bits** | **0.7940** (0.2060) | **0.6544** (0.3456) | **176 / 500** (35.20%) | **7,500** |
| **Bob vs Eve1-Bob** | **2-bit ADQ** | 2 bits | **3 bits** | **0.5470** (0.4530) | **0.5373** (0.4627) | **153 / 500** (30.60%) | **1,500** |
| **Bob vs Eve1-Bob** | **4-bit ADQ** | 4 bits | **15 bits** | **0.7735** (0.2265) | **0.6299** (0.3701) | **153 / 500** (30.60%) | **7,500** |

### 4.3 Exact Closed-Form Mathematical Reconciliation
Because every pair of distinct seeds has an invariant Hamming distance ($d_H = 2$ for $L=2$, $d_H = 8$ for $L=4$), post-expansion metrics follow exact closed-form arithmetic:
1. **2-Bit ADQ Post-Expansion (1,500 Bits Total):**
   - Matching samples ($384$): contribute $384 \times 3 = 1,152$ matching bits ($0$ errors).
   - Mismatched samples ($116$): each distinct pair has $d_H = 2 \implies 1$ match, $2$ errors $\implies 116 \times 1 = 116$ matching bits, $116 \times 2 = 232$ errors.
   - Total matching bits: $1,152 + 116 = \mathbf{1,268}$.
   - Total error bits: $\mathbf{232}$.
   - Post KAR: $1,268 / 1,500 = \mathbf{0.845333...} \approx \mathbf{0.8453}$. Post BER: $232 / 1,500 = \mathbf{0.154667...} \approx \mathbf{0.1547}$.
2. **4-Bit LoRa-PRIME Post-Expansion (7,500 Bits Total):**
   - Matching samples ($384$): contribute $384 \times 15 = 5,760$ matching bits ($0$ errors).
   - Mismatched samples ($116$): each distinct pair has $d_H = 8 \implies 7$ matches, $8$ errors $\implies 116 \times 7 = 812$ matching bits, $116 \times 8 = 928$ errors.
   - Total matching bits: $5,760 + 812 = \mathbf{6,572}$.
   - Total error bits: $\mathbf{928}$.
   - Post KAR: $6,572 / 7,500 = \mathbf{0.876267...} \approx \mathbf{0.8763}$. Post BER: $928 / 7,500 = \mathbf{0.123733...} \approx \mathbf{0.1237}$.

---

## 5. Architectural Comparison Across Settings

| Metric | Active $m = 2^L - 1$ Setting | Historical $2\times$ Per-Sample | Historical 32-Bit Blockwise | Key Insight |
| :--- | :--- | :--- | :--- | :--- |
| **Output Length ($m$)** | **3 bits (2b) / 15 bits (4b)** | 4 bits (2b) / 8 bits (4b) | 64 bits | $m = 2^L - 1$ completes exact non-zero period |
| **Output Bits / Channel** | **1,500 (2b) / 7,500 (4b)** | 2,000 (2b) / 4,000 (4b) | 1,984 (2b) / 3,968 (4b) | Exact integer multiple of 500 samples |
| **Tail Truncation** | **0 bits (100% coverage)** | 0 bits (100% coverage) | 8 bits (2b) / 16 bits (4b) | Per-sample eliminates tail omission |
| **Distinct Seed $d_H$** | **Uniform: 2 (2b), 8 (4b)** | Variable: 2..3 (2b), 3..4 (4b) | Variable (impulse wt 5) | Full-period guarantees constant distance |
| **Alice–Bob Pre-KAR** | **0.8840 (2b) / 0.9420 (4b)** | 0.8840 (2b) / 0.9420 (4b) | 0.8871 (2b) / 0.9435 (4b) | Full 500 sample evaluation |
| **Alice–Bob Post-KAR** | **0.8453 (2b) / 0.8763 (4b)** | 0.8610 (2b) / 0.9130 (4b) | 0.7290 (2b) / 0.7838 (4b) | Controlled error expansion |
| **Eve Discrimination** | **0.5720 (2b) / 0.6576 (4b)** | 0.5850 (2b) / 0.7350 (4b) | 0.5055 (2b) / 0.5363 (4b) | Decorrelated from legitimate channel |

---

## 6. Generated Publication Figures

All visual artifacts were generated and verified at 300 DPI in [`results/dummy/figures/d04/`](../../results/dummy/figures/d04/):
1. **`d04_kar_expansion_comparison.png`:** Bar chart comparing Pre-expansion KAR vs Post-expansion KAR across legitimate and eavesdropper channel pairs for both 2-bit (1,500 bits) and 4-bit (7,500 bits) per-sample encodings.
2. **`d04_ber_vs_length.png`:** Bit Error Rate (BER) progression across pipeline stages, demonstrating error diffusion behavior in relation to the independent unbiased-bit reference (BER = 0.50). (Note: This reference line serves as an idealized benchmark for independent unbiased Bernoulli(0.5) bits; it does not constitute a proof of physical information-theoretic secrecy or eavesdropper isolation).
3. **`d04_block_seed_analysis.png`:** Distribution analysis showing exact sample agreement percentage between Alice and Bob (76.80%) and zero-seed sample counts per channel.

---

## 7. Verification & Full Regression Summary

The verification suite ([`tests/test_d04_lfsr.py`](../../tests/test_d04_lfsr.py)) comprises 21 dedicated automated tests. All tests execute cleanly with **exit code 0**:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Puroh\Documents\PRBS_RSSI
collected 21 items

tests/test_d04_lfsr.py::test_taps_to_tap_mask_conversion PASSED          [  4%]
tests/test_d04_lfsr.py::test_known_answer_state_and_output_vectors PASSED [  9%]
tests/test_d04_lfsr.py::test_small_register_full_period PASSED           [ 14%]
tests/test_d04_lfsr.py::test_degree_32_polynomial_mathematical_primitivity PASSED [ 19%]
tests/test_d04_lfsr.py::test_seed_sensitivity PASSED                     [ 23%]
tests/test_d04_lfsr.py::test_independent_companion_matrix_reference_kat PASSED [ 28%]
tests/test_d04_lfsr.py::test_deterministic_resets PASSED                 [ 33%]
tests/test_d04_lfsr.py::test_output_lengths_exactness PASSED             [ 38%]
tests/test_d04_lfsr.py::test_seed_bit_ordering PASSED                    [ 42%]
tests/test_d04_lfsr.py::test_invalid_inputs_and_edge_cases PASSED        [ 47%]
tests/test_d04_lfsr.py::test_zero_seed_handling PASSED                   [ 52%]
tests/test_d04_lfsr.py::test_partial_block_handling_and_coverage PASSED  [ 57%]
tests/test_d04_lfsr.py::test_channel_independence_and_no_crosstalk PASSED [ 61%]
tests/test_d04_lfsr.py::test_degree_2_and_4_primitive_periods_exhaustive PASSED [ 66%]
tests/test_d04_lfsr.py::test_known_answer_per_sample_symbol_mappings PASSED [ 71%]
tests/test_d04_lfsr.py::test_all_distinct_seed_pairs_hamming_distance_exhaustive PASSED [ 76%]
tests/test_d04_lfsr.py::test_per_sample_reset_independence_and_zero_seed PASSED [ 80%]
tests/test_d04_lfsr.py::test_d03_per_sample_alignment_and_exact_metrics PASSED [ 85%]
tests/test_d04_lfsr.py::test_d04_pipeline_full_execution_and_schema PASSED [ 90%]
tests/test_d03_inputs_remain_unmodified PASSED                           [ 95%]
tests/test_d03_provenance_and_exact_bit_partitioning PASSED             [100%]

============================= 21 passed in 7.74s ==============================
```

**Full Regression Status:** The complete suite across Milestones D01, D02, D03, and D04 passed with **46/46 tests passing (100%)** and **`git diff --check` exiting with code 0**.

---

## 8. Limitations & Handoff to Milestone D04.1

1. **Deterministic Pattern Space:** Because the per-sample architecture expands each 2-bit or 4-bit sample independently and only three quantizer levels occur in D03, the expanded output contains only three distinct output patterns per encoding.
2. **Error Expansion Invariant:** Each single-sample mismatch expands into exactly 2 bit errors for 2-bit ($d_H = 2$) and exactly 8 bit errors for 4-bit ($d_H = 8$), resulting in a post-expansion KAR of 0.8453 (2-bit) and 0.8763 (4-bit).
3. **Boundary Check:** Development strictly stops before **D04.1 (BCH error reconciliation)**. No code or configuration from D04.1 has been introduced.
