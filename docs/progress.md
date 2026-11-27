# Project Progress & Handoff: RSSI-based Secret Key Generation (SKG)

## Current BCH reconciliation release

The standard reconciliation command is:

```bash
python -m rssi_skg -i "data/raw/dummy/Data 1.xlsx" --reconcile
```

All four paths use BCH(2047, 166, 348), designed distance 697, interleaving off. Bob retains blocks with a nonnegative decoder correction count. Both Eve comparisons use exactly those indices, including a receiver's fallback bits when its own decoding fails. Pre/post KAR and exact recovery use retained payload bits after padding removal. A detected failure at Bob discards the block for all pairs. A silent miscorrection remains in the evaluation. With no retained bits, KAR is undefined and exact recovery is false. Block outcomes and helper overhead still cover all attempted blocks.

| Path | Retained / attempted blocks | Retained / original bits | Alice–Bob KAR | Alice–Eve1-Alice KAR | Bob–Eve1-Bob KAR |
|---|---:|---:|---:|---:|---:|
| quant_2bit | 1/1 | 982/982 | 100% | 49.80% | 62.73% |
| quant_4bit | 1/1 | 1964/1964 | 100% | 74.90% | 81.36% |
| prbs_2bit | 2/2 | 3928/3928 | 100% | 52.85% | 62.12% |
| prbs_4bit | 2/2 | 3928/3928 | 100% | 69.78% | 76.63% |

These results are for `data/raw/dummy/Data 1.xlsx`. The ordinary decoder metrics do not establish secrecy. The historical public-helper findings in the handoff concern earlier parameter sets.

Privacy amplification hashes each retained segment at its actual length, using a maximum of 131 bits. The `Data 1.xlsx` workbook yields 8, 15, 30 and 30 digests on the four paths, with final segments of 65, 130, 129 and 129 bits respectively. Both Eve streams have zero exact matches on this workbook.

## 1. Project Purpose & Methodological Reference
This research project develops a physical-layer Secret Key Generation (SKG) pipeline based on Received Signal Strength Indicator (RSSI) measurements.

The project currently implements eight sequential pipeline stages:
1. **RSSI Filtering Stage**: Modified Sage–Husa Adaptive Kalman Filter (MSHKF) based on **`PA.pdf`, Section 3.2.2, Equations (3.10)–(3.20), pages 26–27**.
2. **Zero-Lag Pearson Correlation Analysis**: As defined in **`PA.pdf`, Equation (3.62), page 34**:

```math
\rho_{u,v} =
\frac{
\sum_{n=1}^{N}
\left(X_u(n)-\mu_u\right)
\left(X_v(n)-\mu_v\right)
}{
\sqrt{\sum_{n=1}^{N}\left(X_u(n)-\mu_u\right)^2}
\sqrt{\sum_{n=1}^{N}\left(X_v(n)-\mu_v\right)^2}
}
```

3. **Modified Adaptive Dual-Threshold Quantization (MADQ)**: As defined in **`PA.pdf`, Section 3.2.3, Equations (3.21)–(3.23), pages 27–28**, with performance evaluation via Key Agreement Rate (KAR) in **`PA.pdf`, Section 3.2.8.c, Equation (3.64), page 35**:

```math
q_i^+ = \mu_X + \alpha \sigma_X \qquad (3.21)
```

```math
q_i^- = \mu_X - \alpha \sigma_X \qquad (3.22)
```

```math
Q(X_i) = \begin{cases}
0, & X_i < q_i^- \\
1, & q_i^- \le X_i \le q_i^+ \\
2, & X_i > q_i^+
\end{cases} \qquad (3.23)
```

```math
\text{KAR} = \left(1 - \frac{N_{\text{mismatch}}}{N_{\text{total}}}\right) \times 100\% = \frac{N_{\text{total}} - N_{\text{mismatch}}}{N_{\text{total}}} \times 100\% \qquad (3.64)
```

4. **PRBS Expansion Stage (Galois XOR-LFSR)**: Citing LFSR principles in **`PA.pdf`, Section 3.2.4 (pages 28–29)** as background (with characteristic polynomial Equation 3.24, output recurrence Equation 3.25, and period Equation 3.26):

```math
f(x) = c_m x^m + c_{m-1} x^{m-1} + \dots + c_1 x + c_0 \qquad (3.24)
```

**Output Recurrence (Equation 3.25)**:
```math
S_{i+m} = \left(\sum_{j=0}^{m-1} C_j S_{i+j}\right) \bmod 2 \qquad (3.25)
```

5. **BCH Codeword-based Information Reconciliation**: As defined in **`PA.pdf`, Section 3.2.5, Equations (3.32)–(3.36), pages 29–30**:

```math
H = A \oplus C \qquad (3.32)
```
```math
C' = H \oplus B = (A \oplus C) \oplus B = C \oplus (A \oplus B) = C \oplus e \qquad (3.33)
```
```math
\hat{C} = \text{BCH\_Decode}(C') \qquad (3.34)
```
```math
\hat{A} = H \oplus \hat{C} \qquad (3.35)
```
When decoding is successful and without miscorrection, $\hat{C} = C$ and $\hat{A} = A$. Reconciliation success is defined by direct unpadded bitstream equality:
```math
\text{exact\_recovery} = (A == \hat{A}_{\text{unpadded}})
```

6. **Privacy Amplification (Bit-Level SHA-256)**: As defined in **`PA.pdf`, Section 3.2.6, Equations (3.37)–(3.53), pages 30–33** and **FIPS PUB 180-4**:
```math
M' = M \parallel 1 \parallel 0^p \parallel [L]_{64}, \qquad p = (448 - 1 - L) \bmod 512
```
```math
K = \text{SHA256}(M') \in \{0, 1\}^{256}
```
Final Secret Key Agreement Rate (KAR) is evaluated strictly per **`PA.pdf` Section 3.2.8.c, Equation (3.64)**:
```math
\text{KAR} = \frac{256 - N_{\text{mismatch}}}{256} \times 100\%
```
```math
\text{exact\_key\_match} = (K_{\text{source}} == K_{\text{receiver}})
```

7. **Statistical Randomness Testing (NIST SP 800-22 Rev. 1a)**: Governed by **`PA.pdf`, Section 3.2.8.d, Equations (3.65)–(3.73), pages 35–37** and cross-checked against official **NIST SP 800-22 Rev. 1a**:
- **Frequency (Monobit) Test (Equations 3.65–3.66, NIST Sec 2.1)**:
  $$S_n = \sum_{i=1}^n (2\varepsilon_i - 1), \qquad s_{\text{obs}} = \frac{|S_n|}{\sqrt{n}}, \qquad P\text{-value} = \text{erfc}\left(\frac{s_{\text{obs}}}{\sqrt{2}}\right)$$
- **Runs Test (Equations 3.67–3.69, NIST Sec 2.3)**:
  $$\pi = \frac{1}{n}\sum_{i=1}^n \varepsilon_i, \qquad \tau = \frac{2}{\sqrt{n}}$$
  *Prerequisite Check*: If $|\pi - 0.5| \ge \tau$, the sequence is heavily unbalanced; test is marked not applicable, $P\text{-value} = 0.0$, and the explicit reason is recorded. If satisfied:
  $$V_n(\text{obs}) = 1 + \sum_{k=1}^{n-1} (\varepsilon_k \ne \varepsilon_{k+1}), \qquad P\text{-value} = \text{erfc}\left(\frac{|V_n(\text{obs}) - 2n\pi(1-\pi)|}{2\sqrt{2n}\pi(1-\pi)}\right)$$
- **Approximate Entropy Test (Equations 3.70–3.73, NIST Sec 2.12)**:
  $$C_i^{(k)} = \frac{\#i^{(k)}}{n}, \qquad \phi(k) = \sum_{i=0}^{2^k - 1} C_i^{(k)} \ln C_i^{(k)} \qquad (\text{with convention } 0 \ln 0 = 0)$$
  $$\text{ApEn}(m) = \phi(m) - \phi(m+1), \qquad \chi^2 = \max(0.0, 2n[\ln 2 - \text{ApEn}(m)])$$
  $$P\text{-value} = Q\left(2^{m-1}, \frac{\chi^2}{2}\right) = \text{gammaincc}\left(2^{m-1}, \frac{\chi^2}{2}\right)$$
  Constraint recommendation per NIST Sec 2.12.7: $m < \lfloor \log_2 n \rfloor - 5$. For 256-bit keys ($n=256$), $\lfloor \log_2 256 \rfloor - 5 = 3$, so default $m=2$ strictly satisfies $m < 3$.
- **Significance Level & Acceptance**: $\alpha = 0.01$. A key is accepted if and only if all three tests are applicable and pass ($P\text{-value} \ge \alpha$).

8. **Key Generation Rate (KGR) Measurement**: Governed by **`PA.pdf`, Section 3.2.8.b, Equation (3.63), page 35**:
```math
\text{KGR} = \frac{N_{\text{bit}}}{T} \qquad (\text{bps}) \qquad (3.63)
```
- **Bit Counting Policy**: Evaluated per path. Alice's generated keys are counted once ($N_{\text{bit}} = 256$ bits per chunk passing all three NIST tests, $0$ bits if rejected). Bob's matching key is not duplicate-counted. Alice–Bob agreement is reported separately.
- **Timing Policy**: Elapsed software duration $T$ is measured using a monotonic high-resolution timer (`time.perf_counter()`) starting immediately before scalar MSHKF filtering and ending immediately after SHA-256 privacy amplification on that path (PRBS expansion is included on both PRBS paths). Dataset loading, plotting, exports, and NIST testing are strictly excluded.
- **Cache Warm-Up Policy**: A standardized pre-warm step constructs the BCH code and runs a dummy decode prior to timing, eliminating multi-second Numba JIT compilation timing-order bias between paths.

**Methodological Boundary**: Physical channel probing is **postponed, not replaced**. All current calculations use synthetic dummy data strictly for **software validation** (pipeline integrity, parser correctness, mathematical accuracy), not for empirical claims regarding wireless channel reciprocity or eavesdropping resistance. Deterministic LFSR expansion does not add physical channel entropy. Public helper data leaks information up to $(n - k)$ bits per block.

## 2. Dataset & Semantics
- **File Path**: `data/raw/dummy/Data 1.xlsx` (legacy `Dummy RSSI (data Indoor).xlsx` with 500 observations is also retained in `data/raw/dummy/`).
- **SHA-256**: `49CDDCDD6F45875C58334EB750F3008481415EFE59F8A3E7385BF992842A096F`
- **Observations**: 491 rows. Row-wise pairing is strictly confirmed: row index $i$ corresponds to the exact same observation instance across all channels. Row order and sample alignment are strictly preserved throughout filtering, quantization, PRBS, and reconciliation.
- **Column Definitions**:
  - `Alice`: RSSI received by Alice from Bob's signal transmission.
  - `Bob`: RSSI received by Bob from Alice's signal transmission.
  - `Eve1-Alice`: RSSI overheard by eavesdropper Eve from Alice's transmission.
  - `Eve1-Bob`: RSSI overheard by eavesdropper Eve from Bob's transmission.

## 3. Implemented Modules & Validated Results
- **Workbook Loader (`src/rssi_skg/loader.py`)**: Uses `openpyxl` to read raw workbooks; validates presence of all 4 required headers; enforces numeric cell types; reports exact row and column upon encountering missing/invalid values; supports arbitrary sample sizes $N \ge 2$.
- **Modified Sage–Husa Adaptive Kalman Filter (`src/rssi_skg/filter.py`)**:
  - Implements scalar MSHKF with modeling assumptions $\Phi = 1.0$ and $H = 1.0$.
  - Adaptive memory parameter $b = 0.99$ is a selected value within the literature range $(0.95, 0.999)$ mentioned in `PA.pdf` Section 3.2.2. Initial weight $D_0 = 1.0$.
  - Parameters $P_0 = 1.0\ \text{dBm}^2, Q = 0.1\ \text{dBm}^2, R_0 = 1.0\ \text{dBm}^2$ are uncalibrated software-validation assumptions.
  - Process noise covariance $Q = 0.1\ \text{dBm}^2$ is held fixed based on `PA.pdf` Section 3.2.2's final modeling assumption (known prior). Consequently, online adaptation is performed on measurement noise covariance $\hat{R}_k$ while Equation (3.20) for adaptive $Q$ update is not executed.
  - Online adaptation of $\hat{R}_k$ and recursive updates for noise means $\hat{q}_k$ and $\hat{r}_k$ are retained.
  - Sample indexing policy: auto-initialization from first sample $x_0 = z_0$ sets output[0] = $z_0$ and starts recursion at sample $1$ ($k=1$), strictly avoiding double-counting $z_0$.
  - Enforces independent filter instances across Alice, Bob, Eve1-Alice, and Eve1-Bob for strict channel isolation.
- **Correlation Calculation (`src/rssi_skg/correlation.py`)**: Computes centered zero-lag Pearson correlation $\rho$ in `float64` precision; validates equal lengths; rejects $N < 2$, NaN, and Inf; raises explicit `ValueError` on constant sequences (zero variance).
- **Modified Adaptive Dual-Threshold Quantization (`src/rssi_skg/quantization.py`)**:
  - Segment-based adaptive threshold calculation: non-overlapping segments with configurable default window size $W = 50$, multiplier $\alpha = 0.5$, and population standard deviation ($\text{ddof} = 0$).
  - Full sample coverage: processes all samples, including any shorter final segment (10 segments for $N=491$: 9 of 50 samples, 1 of 41 samples).
  - Sample retention: all samples are retained; no sample in the intermediate zone is discarded. Constant segments ($\sigma = 0$) unconditionally produce level 1.
  - Channel isolation: each channel's mean, standard deviation, and thresholds are calculated independently with zero cross-channel contamination.
  - Dual binary encodings generated simultaneously in every run:
    - **2-bit Gray code**: $0 \rightarrow 00$, $1 \rightarrow 01$, $2 \rightarrow 11$ (implementation choice to minimize bit errors for adjacent state transitions).
    - **4-bit code**: $0 \rightarrow 1010$, $1 \rightarrow 1011$, $2 \rightarrow 1001$ (per `PA.pdf` Section 3.2.3, page 28).
  - Bitstreams preserve temporal sample order.
  - Evaluation: Bit-level Key Agreement Rate (KAR) per `PA.pdf` Equation (3.64), sample-level agreement rate, and per-channel level frequencies.
  - Companion XLSX Export (`export_quantized_workbook_xlsx`) with Text format (`@`) and >32k cell limit chunking.
  - Visualization (`plot_kar_comparison_figure`): 4-panel 300-dpi PNG and vector PDF.
- **PRBS Expansion Stage (Galois XOR-LFSR, `src/rssi_skg/prbs.py`)**:
  - Left-shift Galois LFSR with primitive polynomials $f(x) = x^2 + x + 1$ ($m=2$) and $f(x) = x^4 + x + 1$ ($m=4$).
  - Produces 3,928 bits/channel for either seed width (8 clocks per sample) across 491 samples.
  - Output recurrence strictly satisfied per `PA.pdf` Equation (3.25) within each sample block.
  - Explicit zero-seed handling: seed `00` locked up at state 0 with actual period 1.
  - Companion multi-sheet XLSX export and 2×2 PRBS KAR comparison figure (`plot_prbs_kar_comparison_figure`).
- **BCH Codeword Helper Data Reconciliation (`src/rssi_skg/reconciliation.py`)**:
  - **Codeword Helper Data Scheme (`PA.pdf` Equations 3.32–3.36)**:
    - Source generates independent random $k$-bit message per block: $M \leftarrow \text{GF}(2)^k$.
    - Encodes $M$ to BCH codeword: $C = \text{BCH\_Encode}(M) \in \text{GF}(2)^n$.
    - Publishes helper data: $H = A \oplus C$.
    - Receiver computes $C' = H \oplus B = C \oplus (A \oplus B) = C \oplus e$.
    - Receiver decodes: $\hat{C} = \text{BCH\_Decode}(C')$. If error weight $w(e) \le t$, $\hat{C} = C$.
    - Receiver reconstructs: $\hat{A} = H \oplus \hat{C}$. If $\hat{C} = C$, then $\hat{A} = A$.
  - **Zero-Padding & Padding Removal**:
    - Final block zero-padded to $n$ bits with explicit tracking of original length $L$ and padding count $P$.
    - Padding stripped immediately after reconstruction: $\hat{A} \leftarrow \hat{A}[:L]$.
    - Excluded from all KAR metrics and payload recovery verification.
  - **Receiver Isolation**:
    - Receiver decoder accesses only its own bits $B$, public helper data $H$, and BCH parameters $(n, k, t)$.
    - Source bitstream $A$ is strictly excluded from decoder operations.
    - Evaluation categories: `success` ($num\_corr \ge 0, \hat{A} == A$), `detected_failure` ($num\_corr == -1$), and `miscorrected` ($num\_corr \ge 0, \hat{A} \ne A$). Source equality verified only in the offline evaluator.
  - Evaluate payload agreement on Bob’s retained block indices. For each pair, validate exact recovery on the retained bits after removing padding.
- **Privacy amplification** uses SHA-256 on successive segments of up to 131 bits. The last segment uses its actual bit length. Each channel produces 8, 15, 30 and 30 digests on the four paths respectively (83 per channel, 332 total).

  - **NIST SP 800-22 Randomness Testing (`src/rssi_skg/nist.py`)**:
    - Implements three core statistical tests per `PA.pdf` Section 3.2.8.d and NIST SP 800-22 Rev. 1a:
      1. Frequency (Monobit) Test (Equations 3.65–3.66, NIST Sec 2.1).
      2. Runs Test (Equations 3.67–3.69, NIST Sec 2.3) with explicit prerequisite check $|\pi - 0.5| < 2/\sqrt{n}$. Prerequisite failure explicitly yields $P\text{-value} = 0.0$, `applicable=False`, and documented reason.
      3. Approximate Entropy Test (Equations 3.70–3.73, NIST Sec 2.12) with default $m=2$ and constraint $m < \lfloor \log_2 n \rfloor - 5$.
    - Significance level $\alpha = 0.01$. Overall acceptance requires all three tests to be applicable and passed.
    - Reference test vectors from NIST SP 800-22 Rev. 1a Sections 2.1.8, 2.3.8, and 2.12.8 verified with exact numerical match to 6 decimal places.
    - Exporters: `export_nist_metrics_csv` (wide format per key) and `export_nist_config_json`.

  - **Key Generation Rate (KGR) Measurement (`src/rssi_skg/kgr.py`)**:
    - Implements KGR per `PA.pdf` Section 3.2.8.b, Equation (3.63): $\text{KGR} = N_{\text{bit}} / T$ (bps).
    - Bit counting policy: Alice's 256-bit key is counted once ($N_{\text{bit}} = 256$ per accepted chunk, $0$ if rejected). Bob's key is not duplicate-counted. Alice–Bob exact key agreement is reported separately.
    - High-resolution timing: Independent per-path measurement using monotonic timer `time.perf_counter()` spanning immediately before MSHKF filtering through SHA-256 compression (PRBS expansion included on `prbs_2bit` and `prbs_4bit`). Excludes workbook loading, plotting, exports, and NIST testing.
    - Cold-start & cache policy: `warm_up_bch_cache()` pre-compiles Galois Numba JIT kernels and tables before timing, eliminating initial compilation order bias between paths.
    - Exporters: `export_kgr_metrics_csv`, `export_kgr_config_json`, and companion multi-sheet Excel workbook `export_evaluation_workbook_xlsx` with `@` (Text) format for key cells.

## 4. Key Source & Test File Responsibilities
- `src/rssi_skg/nist.py`: NIST SP 800-22 statistical test suite (`monobit_test`, `runs_test`, `approximate_entropy_test`), key validator (`evaluate_key_randomness`, `evaluate_pa_keys_randomness`), and artifact exporters (`export_nist_metrics_csv`, `export_nist_config_json`).
- `src/rssi_skg/kgr.py`: High-resolution software KGR measurement (`measure_multipath_kgr`, `execute_timed_path_pipeline`), cache pre-warming (`warm_up_bch_cache`), injectable mock clock support, and companion Excel exporter (`export_evaluation_workbook_xlsx`).
- `src/rssi_skg/privacy_amplification.py`: Bit-level SHA-256 Privacy Amplification engine per FIPS 180-4 (`PA.pdf` Section 3.2.6), bit-level padding (`pad_bitstream`), 64-round compression (`sha256_bitstream`), `PrivacyAmplificationConfig`, `ChannelPrivacyAmplificationResult`, `PairPrivacyAmplificationResult`, `MultiPathPrivacyAmplificationResult`, `amplify_privacy_all_paths`, artifact exporters (`export_pa_metrics_csv`, `export_pa_keys_csv`, `export_pa_config_json`, `export_pa_workbook_xlsx`), and `verify_against_hashlib`.
- `src/rssi_skg/reconciliation.py`: Codeword helper data engine, BCH code caching (`get_bch_code`), `ReconciliationConfig`, `serialize_bitstream`, `generate_candidate_key`, `generate_helper_data`, `reconstruct_receiver_bitstream`, `evaluate_reconciliation_pair`, `reconcile_all_paths`, artifact CSV/JSON exporters, and `export_reconciliation_workbook_xlsx`.
- `src/rssi_skg/prbs.py`: Galois XOR-LFSR engine (`GaloisLFSR`), primitive polynomial definitions, `PRBSConfig`, `expand_seed`, `expand_channel_prbs`, `expand_channels_prbs`, artifact CSV/JSON exporters, and `export_prbs_workbook_xlsx`.
- `src/rssi_skg/quantization.py`: Modified ADQ engine, `QuantizationConfig`, `SegmentThresholds`, `ChannelQuantizationResult`, `quantize_series`, `quantize_channels`, `encode_levels_to_bits`, `calculate_kar`, `calculate_level_agreement`, `calculate_level_frequencies`, CSV/JSON export functions, and `export_quantized_workbook_xlsx`.
- `src/rssi_skg/filter.py`: Scalar MSHKF engine, `FilterConfig`, `ModifiedSageHusaFilter`, `filter_rssi_channels`.
- `src/rssi_skg/correlation.py`: Pure mathematical Pearson implementation and input sanity checking.
- `src/rssi_skg/loader.py`: Excel workbook ingestion, column validation, and row pairing.
- `src/rssi_skg/plotting.py`: Bubble aggregation, raw figure rendering, filtered comparison figure, quantization KAR figure (`plot_kar_comparison_figure`), 2×2 PRBS KAR figure (`plot_prbs_kar_comparison_figure`), four-path reconciliation figure (`plot_reconciliation_figure`), and 2×2 Privacy Amplification comparison figure (`plot_privacy_amplification_figure`).
- `src/rssi_skg/cli.py`: Unified CLI parsing with prerequisite chaining, `--nist` and `--kgr` evaluation options, companion XLSX export dispatch, figure prefix routing, and stdout user guidance.

## 5. Verification records

The following tables come from the CLI run on the 491-sample `data/raw/dummy/Data 1.xlsx` workbook using `BCH(2047, 166, 348)` and 131-bit segmented SHA-256 Privacy Amplification.

### BCH reconciliation

| Path | Pair | Pre-BCH KAR | Post-BCH KAR | Δ (pp) | Blocks (success / detected failure / miscorrection) | Block success | Exact retained payload |
| --- | --- | --- | --- | --- | --- | --- | --- |
| quant_2bit | Alice–Bob | 87.88% | 100.00% | +12.12 | 1 / 0 / 0 | 100.00% | True |
| quant_2bit | Alice–Eve1-Alice | 49.80% | 49.80% | +0.00 | 0 / 1 / 0 | 0.00% | False |
| quant_2bit | Bob–Eve1-Bob | 62.73% | 62.73% | +0.00 | 0 / 1 / 0 | 0.00% | False |
| quant_4bit | Alice–Bob | 93.94% | 100.00% | +6.06 | 1 / 0 / 0 | 100.00% | True |
| quant_4bit | Alice–Eve1-Alice | 74.90% | 74.90% | +0.00 | 0 / 1 / 0 | 0.00% | False |
| quant_4bit | Bob–Eve1-Bob | 81.36% | 81.36% | +0.00 | 0 / 1 / 0 | 0.00% | False |
| prbs_2bit | Alice–Bob | 83.43% | 100.00% | +16.57 | 2 / 0 / 0 | 100.00% | True |
| prbs_2bit | Alice–Eve1-Alice | 52.85% | 52.85% | +0.00 | 0 / 2 / 0 | 0.00% | False |
| prbs_2bit | Bob–Eve1-Bob | 62.12% | 62.12% | +0.00 | 0 / 2 / 0 | 0.00% | False |
| prbs_4bit | Alice–Bob | 91.01% | 100.00% | +8.99 | 2 / 0 / 0 | 100.00% | True |
| prbs_4bit | Alice–Eve1-Alice | 69.78% | 69.78% | +0.00 | 0 / 2 / 0 | 0.00% | False |
| prbs_4bit | Bob–Eve1-Bob | 76.63% | 76.63% | +0.00 | 0 / 2 / 0 | 0.00% | False |

### Privacy amplification

| Path | Evaluation Pair | Reference / Source | Receiver | Chunks | Pre-PA KAR | Post-PA Mean KAR | Δ (pp) | Exact Matches | Match Rate | All Match |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quant_2bit | Alice–Bob | Alice | Bob | 8 | 100.00% | 100.00% | +0.00 | 8 / 8 | 100.00% | TRUE |
| quant_2bit | Alice–Eve1-Alice | Alice | Eve1-Alice | 8 | 49.80% | 51.03% | +1.23 | 0 / 8 | 0.00% | FALSE |
| quant_2bit | Bob–Eve1-Bob | Bob | Eve1-Bob | 8 | 62.73% | 49.32% | -13.41 | 0 / 8 | 0.00% | FALSE |
| quant_4bit | Alice–Bob | Alice | Bob | 15 | 100.00% | 100.00% | +0.00 | 15 / 15 | 100.00% | TRUE |
| quant_4bit | Alice–Eve1-Alice | Alice | Eve1-Alice | 15 | 74.90% | 50.03% | -24.87 | 0 / 15 | 0.00% | FALSE |
| quant_4bit | Bob–Eve1-Bob | Bob | Eve1-Bob | 15 | 81.36% | 49.69% | -31.68 | 0 / 15 | 0.00% | FALSE |
| prbs_2bit | Alice–Bob | Alice | Bob | 30 | 100.00% | 100.00% | +0.00 | 30 / 30 | 100.00% | TRUE |
| prbs_2bit | Alice–Eve1-Alice | Alice | Eve1-Alice | 30 | 52.85% | 50.64% | -2.21 | 0 / 30 | 0.00% | FALSE |
| prbs_2bit | Bob–Eve1-Bob | Bob | Eve1-Bob | 30 | 62.12% | 50.44% | -11.68 | 0 / 30 | 0.00% | FALSE |
| prbs_4bit | Alice–Bob | Alice | Bob | 30 | 100.00% | 100.00% | +0.00 | 30 / 30 | 100.00% | TRUE |
| prbs_4bit | Alice–Eve1-Alice | Alice | Eve1-Alice | 30 | 69.78% | 50.38% | -19.40 | 0 / 30 | 0.00% | FALSE |
| prbs_4bit | Bob–Eve1-Bob | Bob | Eve1-Bob | 30 | 76.63% | 51.58% | -25.05 | 0 / 30 | 0.00% | FALSE |

### NIST randomness tests

Each of the four channels contributes 83 digest observations (332 total). Significance level 0.01, ApEn block length 2, digest length 256 bits. All three tests must apply and pass for acceptance.

| Path | Channel | Chunks evaluated | Applicable chunks | Monobit pass | Runs pass | ApEn pass | Accepted chunks | Acceptance rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quant_2bit | Alice | 8 | 8 | 8 / 8 | 8 / 8 | 8 / 8 | 8 / 8 | 100.00% |
| quant_2bit | Bob | 8 | 8 | 8 / 8 | 8 / 8 | 8 / 8 | 8 / 8 | 100.00% |
| quant_2bit | Eve1-Alice | 8 | 8 | 8 / 8 | 8 / 8 | 8 / 8 | 8 / 8 | 100.00% |
| quant_2bit | Eve1-Bob | 8 | 8 | 8 / 8 | 8 / 8 | 8 / 8 | 8 / 8 | 100.00% |
| quant_4bit | Alice | 15 | 15 | 15 / 15 | 15 / 15 | 15 / 15 | 15 / 15 | 100.00% |
| quant_4bit | Bob | 15 | 15 | 15 / 15 | 15 / 15 | 15 / 15 | 15 / 15 | 100.00% |
| quant_4bit | Eve1-Alice | 15 | 15 | 14 / 15 | 15 / 15 | 15 / 15 | 14 / 15 | 93.33% |
| quant_4bit | Eve1-Bob | 15 | 15 | 15 / 15 | 15 / 15 | 15 / 15 | 15 / 15 | 100.00% |
| prbs_2bit | Alice | 30 | 30 | 28 / 30 | 30 / 30 | 30 / 30 | 28 / 30 | 93.33% |
| prbs_2bit | Bob | 30 | 30 | 28 / 30 | 30 / 30 | 30 / 30 | 28 / 30 | 93.33% |
| prbs_2bit | Eve1-Alice | 30 | 30 | 29 / 30 | 30 / 30 | 30 / 30 | 29 / 30 | 96.67% |
| prbs_2bit | Eve1-Bob | 30 | 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 100.00% |
| prbs_4bit | Alice | 30 | 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 100.00% |
| prbs_4bit | Bob | 30 | 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 100.00% |
| prbs_4bit | Eve1-Alice | 30 | 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 100.00% |
| prbs_4bit | Eve1-Bob | 30 | 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 100.00% |

### KGR

Recorded in one CLI run. Durations and rates vary by host and run.

| Path | Total chunks | Accepted chunks (Alice) | Raw bits | Accepted bits | Duration (ms) | Raw KGR (bps) | Accepted KGR (bps) | Alice–Bob matches | Alice–Bob KAR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quant_2bit | 8 | 8 | 2048 | 2048 | 35.492 | 57702.49 | 57702.49 | 8 / 8 | 100.00% |
| quant_4bit | 15 | 15 | 3840 | 3840 | 40.988 | 93686.41 | 93686.41 | 15 / 15 | 100.00% |
| prbs_2bit | 30 | 28 | 7680 | 7168 | 112.242 | 68423.58 | 63862.01 | 30 / 30 | 100.00% |
| prbs_4bit | 30 | 30 | 7680 | 7680 | 99.281 | 77355.96 | 77355.96 | 30 / 30 | 100.00% |

## 6. Windows PowerShell Reproduction Commands
> The primary execution guide with output locations is maintained in [README.md](../README.md#petunjuk-penyiapan-lingkungan--eksekusi).

```powershell
# 1. Run automated test suite
.\.venv\Scripts\python.exe -m pytest -v

# 2. Run default correlation analysis (raw only)
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Data 1.xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"

# 3. Run filtering and correlation pipeline (MSHKF + Raw vs Filtered export)
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Data 1.xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --figure-prefix "outputs/dummy_rssi_filtered"

# 4. Run full pipeline with Modified ADQ Quantization stage, companion XLSX, and KAR comparison charts
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Data 1.xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --quantize-window 50 `
  --quantize-alpha 0.5 `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --quantized-samples-output "outputs/dummy_rssi_quantized_samples.csv" `
  --quantized-segments-output "outputs/dummy_rssi_quantized_segments.csv" `
  --quantized-bitstreams-output "outputs/dummy_rssi_quantized_bitstreams.csv" `
  --quantize-metrics-output "outputs/dummy_rssi_quantize_metrics.csv" `
  --quantize-config-output "outputs/dummy_rssi_quantize_config.json" `
  --quantized-xlsx-output "outputs/dummy_rssi_quantized.xlsx" `
  --figure-prefix "outputs/dummy_rssi_filtered"

# 5. Run full pipeline with PRBS bit expansion stage, companion multi-sheet XLSX, and 2x2 PRBS KAR visualization
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Data 1.xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --prbs-samples-output "outputs/dummy_rssi_prbs_samples.csv" `
  --prbs-bitstreams-output "outputs/dummy_rssi_prbs_bitstreams.csv" `
  --prbs-metrics-output "outputs/dummy_rssi_prbs_metrics.csv" `
  --prbs-config-output "outputs/dummy_rssi_prbs_config.json" `
  --prbs-xlsx-output "outputs/dummy_rssi_prbs.xlsx" `
  --prbs-figure-prefix "outputs/dummy_rssi_prbs_kar"

# 6. Run full pipeline through global BCH reconciliation
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Data 1.xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --reconcile-metrics-output "outputs/dummy_rssi_bch_metrics.csv" `
  --reconcile-blocks-output "outputs/dummy_rssi_bch_blocks.csv" `
  --reconcile-config-output "outputs/dummy_rssi_bch_config.json" `
  --reconciled-xlsx-output "outputs/dummy_rssi_bch.xlsx" `
  --reconcile-figure-prefix "outputs/dummy_rssi_bch_reconciliation"

# 7. Run full pipeline through Privacy Amplification (SHA-256 256-bit key generation)
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Data 1.xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --privacy-amplify `
  --pa-metrics-output "outputs/dummy_rssi_pa_metrics.csv" `
  --pa-keys-output "outputs/dummy_rssi_pa_keys.csv" `
  --pa-config-output "outputs/dummy_rssi_pa_config.json" `
  --pa-xlsx-output "outputs/dummy_rssi_pa.xlsx" `
  --pa-figure-prefix "outputs/dummy_rssi_pa_comparison"

# 8. Run full pipeline through NIST SP 800-22 randomness testing & Key Generation Rate (KGR) measurement
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Data 1.xlsx" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --pa `
  --nist `
  --kgr `
  --nist-metrics-output "outputs/dummy_rssi_nist_metrics.csv" `
  --nist-config-output "outputs/dummy_rssi_nist_config.json" `
  --kgr-metrics-output "outputs/dummy_rssi_kgr_metrics.csv" `
  --kgr-config-output "outputs/dummy_rssi_kgr_config.json" `
  --evaluation-xlsx-output "outputs/dummy_rssi_evaluation.xlsx"
```

## 7. Current Git State & Verification
- **Active Branch**: `main`.
- **Working Tree Policy**: All modified and untracked files remain strictly unstaged in the working tree awaiting user review. No commits or pushes have been performed.
- **Gitignore Status**: Inspected `.gitignore`. The existing rule `outputs/*` (with `!outputs/.gitkeep`) already covers all generated artifacts, candidate keys, and visualizations. No `.gitignore` modification was required.

## 8. Remaining Limitations & Proposed Next Steps
- **Limitations & Scientific Notice**:
  - Operates on synthetic indoor dummy data for software verification; cannot establish empirical secrecy.
  - Channel probing hardware is deferred to a subsequent physical testing phase.
  - Parameters $W=50$ and $\alpha=0.5$ are provisional software-validation settings, not optimized physical-channel parameters.
  - PRBS bit expansion is deterministic and does not add physical channel entropy.
  - Helper data reveals parity relations and leaks information; SHA-256 output length (256 bits) does not establish 256 bits of min-entropy.
  - **NIST Randomness & KGR Scope**:
    - The three NIST tests (Monobit, Runs, Approximate Entropy) validate basic statistical randomness properties of the 256-bit hash digests on dummy data. Passing these tests does NOT claim a full NIST SP 800-22 suite pass, physical entropy, or cryptographic unpredictability.
    - Repeated software timing runs do NOT constitute independent randomness samples. Duplicate matching keys from Bob are never concatenated or double-counted to inflate bit counts.
    - KGR measures pure software processing throughput ($N_{\text{accepted\_bits}} / T$) on a local machine with a pre-warmed JIT cache, NOT an empirical channel probing rate or over-the-air throughput.
- **Pipeline Roadmap**:
  1. *Completed*: Implemented Modified Sage–Husa Adaptive Kalman Filter (MSHKF) stage.
  2. *Completed*: Implemented Modified Adaptive Dual-Threshold Quantization (MADQ) stage (`PA.pdf` Section 3.2.3, Equations 3.21–3.23) and KAR evaluation (Equation 3.64).
  3. *Completed*: Implemented Bit Expansion with Galois XOR-LFSR PRBS generator (`PA.pdf` Section 3.2.4 as background) and before/after KAR evaluation.
  4. *Completed*: Implemented BCH Codeword-based Information Reconciliation (`PA.pdf` Section 3.2.5, Equations 3.32–3.36).
  5. Implemented shared BCH(2047, 166, 348), 131-bit segmented SHA-256, per-digest NIST testing and per-path KGR reporting on all four paths.
  6. Physical-channel measurements remain future work.

### Earlier public-helper experiments

Prior experiments used different BCH codes, PRBS expansion lengths or padding patterns. The earlier four-bit BCH(255, 9, 62) experiment reported unique recovery from public information on its tested data. An earlier BCH(1023, 46, 200) experiment reported leakage from known padding. Neither result is a measurement of public-helper recovery for the current configuration.
