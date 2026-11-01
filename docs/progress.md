# Project Progress & Handoff: RSSI-based Secret Key Generation (SKG)

## 1. Project Purpose & Methodological Reference
This research project develops a physical-layer Secret Key Generation (SKG) pipeline based on Received Signal Strength Indicator (RSSI) measurements.

The project currently implements five sequential pipeline stages:
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
*(Note: Privacy Amplification per Section 3.2.6 is a future stage requiring a separate request and is NOT part of this implementation.)*

**Methodological Boundary**: Physical channel probing is **postponed, not replaced**. All current calculations use synthetic indoor dummy data strictly for **software validation** (pipeline integrity, parser correctness, mathematical accuracy), not for empirical claims regarding wireless channel reciprocity or eavesdropping resistance. Deterministic LFSR expansion does not add physical channel entropy. Public helper data leaks information up to $(n - k)$ bits per block.

## 2. Dataset & Semantics
- **File Path**: `data/raw/dummy/Dummy RSSI (data Indoor).xlsx`
- **SHA-256**: `50A3459CB0A09D0A2897A2872E18D977EF6ECE0C7FCB68C0549BDB4CD780A0EE`
- **Observations**: 500 rows. Row-wise pairing is strictly confirmed: row index $i$ corresponds to the exact same observation instance across all channels. Row order and sample alignment are strictly preserved throughout filtering, quantization, PRBS, and reconciliation.
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
  - Full sample coverage: processes all samples, including any shorter final segment.
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
  - Produces 1,500 bits/channel (2-bit seed) and 7,500 bits/channel (4-bit seed) across 500 samples.
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
  - **Direct Bitstream Equality & Privacy Amplification Status**:
    - Direct unpadded bitstream equality: $\text{exact\_recovery} = (A == \hat{A}_{\text{unpadded}})$.
    - Privacy Amplification (`PA.pdf` Section 3.2.6) is removed from this task's scope and deferred to a future request.
  - **Reconciliation Scope & 4-bit Removal**:
    - Reconciliation and subsequent candidate-key generation support **ONLY** 2-bit paths:
      1. `quant_2bit`: 2-bit Gray quantization output ($L = 1000$ bits).
      2. `prbs_2bit`: PRBS-expanded output from 2-bit seeds ($L = 1500$ bits).
    - Obsolete paths `quant_4bit` and `prbs_4bit` have been removed from reconciliation configuration, processing, metrics, candidate-key outputs, export sheets/rows, and plot panels. Obsolete options (`code_quant_4bit`, `code_prbs_4bit`) are explicitly rejected with `ValueError`.
    - **Upstream Preservation**: Upstream 4-bit quantization and 4-bit PRBS generation, exports, plots, and unit tests are strictly preserved and remain fully functional.
  - **Shared BCH Parameter Investigation & Public Information Leakage Audit**:
    - Evaluated primitive lengths $n \in \{31, 63, 127, 255, 511, 1023\}$ across both supported paths (`quant_2bit` and `prbs_2bit`) on the actual dummy dataset:
      * Without interleaving:
        - $n=31$: max error = 21 (max valid $t$ for $k>1$ is 7 $\implies$ FAIL).
        - $n=63$: max error = 32 (max valid $t$ for $k>1$ is 15 $\implies$ FAIL).
        - $n=127$: max error = 49 (max valid $t$ for $k>1$ is 31 $\implies$ FAIL).
        - $n=255$: max error = 90 (max valid $t$ for $k>1$ is 60 $\implies$ FAIL).
        - $n=511$: max error = 164 (max valid $t$ for $k>1$ is 126 $\implies$ FAIL).
        - $n=1023$: `quant_2bit` max error = 196, `prbs_2bit` max error = 192 (global max = 196). Valid candidate: $\text{BCH}(1023, 46, d_{\text{designed}}=401, t=200)$.
      * With deterministic public interleaving (seed 2026):
        - $n=31$: max error = 12 (max $t=7 \implies$ FAIL).
        - $n=63$: max error = 21 (max $t=15 \implies$ FAIL).
        - $n=127$: max error = 36 (max $t=31 \implies$ FAIL).
        - $n=255$: max error = 67 (max $t=60 \implies$ FAIL).
        - $n=511$: max error = 127 (max $t=126 \implies$ FAIL by 1 bit).
        - $n=1023$: `quant_2bit` max error = 196, `prbs_2bit` max error = 179 (global max = 196). Valid candidate: $\text{BCH}(1023, 46, t=200)$.
    - **Public Information Leakage Audit (Padding & Linear Constraints)**:
      * For $\text{BCH}(1023, 46, t=200)$ on `prbs_2bit` ($L=1500, M=2$ blocks, $N_{pad}=546$ zero-padding bits):
        - With Interleaving (seed 2026): Padding is dispersed (Block 0 has 276 padding bits, Block 1 has 270 padding bits).
          The exact $\text{GF}(2)$ rank of the submatrix formed by public padding columns $G[:, J]$ is **46 out of 46 (full rank)** in both blocks!
          Because $h_J = u G[:, J] \oplus A_J$ and $A_J = 0$, $u$ is determined via direct matrix inversion over $\text{GF}(2)$, completely recovering Alice's message, codeword, and source bitstream ($K_E = K_A$, key leaked).
        - Without Interleaving: Block 1 has 546 padding bits, also yielding $\text{rank}_{\text{GF}(2)}(G[:, J]) = 46$ (full rank, completely leaked).
    - **Integration Decision**:
      * Because the shared candidate $\text{BCH}(1023, 46, t=200)$ fails the secrecy/leakage criterion, it is not adopted as production default.
      * In accordance with the decision rule, **calibrated 2-bit defaults are preserved**:
        - `quant_2bit`: $\text{BCH}(31, 1, 15)$
        - `prbs_2bit`: $\text{BCH}(127, 1, 63)$
  - **Historical Calibrated Diagnostic Exploration ($N=500$ samples, `data_kind=dummy`)**:
    - `quant_2bit` (1,000b): Diagnostic BCH(31, 1, 15), 33 blocks, max block error = 14 $\le 15$.
      * Alice–Bob: Pre-KAR 80.40% $\to$ Post-KAR 100.00%, Exact=True, 33/33 success, helper overhead 1.02x (1023b).
      * Alice–Eve1-Alice: Pre-KAR 58.20% $\to$ Post-KAR 75.20%, 25/33 success, 8 miscorrected, Exact=False.
      * Bob–Eve1-Bob: Pre-KAR 55.40% $\to$ Post-KAR 69.00%, 23/33 success, 10 miscorrected, Exact=False.
    - `prbs_2bit` (1,500b): Diagnostic BCH(127, 1, 63), 12 blocks, max block error = 49 $\le 63$.
      * Alice–Bob: Pre-KAR 76.27% $\to$ Post-KAR 100.00%, Exact=True, 12/12 success, helper overhead 1.02x (1524b).
      * Alice–Eve1-Alice: Pre-KAR 56.53% $\to$ Post-KAR 66.13%, 8/12 success, 4 miscorrected, Exact=False.
      * Bob–Eve1-Bob: Pre-KAR 56.27% $\to$ Post-KAR 74.60%, 9/12 success, 3 miscorrected, Exact=False.
  - **Generated Output Artifacts in `outputs/`**:
    - `dummy_rssi_reconcile_metrics.csv` (6 rows: 2 paths $\times$ 3 pairs)
    - `dummy_rssi_reconcile_blocks.csv`
    - `dummy_rssi_reconcile_config.json`
    - `dummy_rssi_bch_metrics.csv`
    - `dummy_rssi_bch_blocks.csv`
    - `dummy_rssi_bch_config.json`
    - `dummy_rssi_bch.xlsx` (companion multi-sheet Excel workbook with Text `@` formatting and >32k cell chunking)
    - `dummy_rssi_bch_reconciliation.png` & `.pdf` (2×2 300-dpi / vector PDF reconciliation figure)

## 4. Key Source & Test File Responsibilities
- `src/rssi_skg/reconciliation.py`: Codeword helper data engine, BCH code caching (`get_bch_code`), `ReconciliationConfig`, `serialize_bitstream`, `generate_candidate_key`, `generate_helper_data`, `reconstruct_receiver_bitstream`, `evaluate_reconciliation_pair`, `reconcile_all_paths`, artifact CSV/JSON exporters, and `export_reconciliation_workbook_xlsx`.
- `src/rssi_skg/prbs.py`: Galois XOR-LFSR engine (`GaloisLFSR`), primitive polynomial definitions, `PRBSConfig`, `expand_seed`, `expand_channel_prbs`, `expand_channels_prbs`, artifact CSV/JSON exporters, and `export_prbs_workbook_xlsx`.
- `src/rssi_skg/quantization.py`: Modified ADQ engine, `QuantizationConfig`, `SegmentThresholds`, `ChannelQuantizationResult`, `quantize_series`, `quantize_channels`, `encode_levels_to_bits`, `calculate_kar`, `calculate_level_agreement`, `calculate_level_frequencies`, CSV/JSON export functions, and `export_quantized_workbook_xlsx`.
- `src/rssi_skg/filter.py`: Scalar MSHKF engine, `FilterConfig`, `ModifiedSageHusaFilter`, `filter_rssi_channels`.
- `src/rssi_skg/correlation.py`: Pure mathematical Pearson implementation and input sanity checking.
- `src/rssi_skg/loader.py`: Excel workbook ingestion, column validation, and row pairing.
- `src/rssi_skg/plotting.py`: Bubble aggregation, raw figure rendering, filtered comparison figure, quantization KAR figure (`plot_kar_comparison_figure`), 2×2 PRBS KAR figure (`plot_prbs_kar_comparison_figure`), and 2-panel reconciliation figure (`plot_reconciliation_figure`).
- `src/rssi_skg/cli.py`: Command-line parsing, optional filtering, quantization, PRBS, and reconciliation dispatch with prerequisite chaining, companion XLSX export dispatch, figure prefix routing, and stdout user guidance.
- `tests/test_reconciliation.py`: 10 tests (BCH code validation & caching, packed bit serialization & SHA-256, error-free recovery, controlled error injection up to $t$, beyond-$t$ handling, padding removal & payload metric isolation, receiver isolation, 2-path supported pipeline evaluation on dummy data with obsolete 4-bit rejection, artifact exporters with XLSX chunking, CLI integration).
- `tests/test_prbs.py`: 15 tests (primitive polynomials, zero-state lockup, known-answer sequences, Equation 3.25 recurrence, boundary resets, input validation, channel isolation, exports, cell chunking, CLI).
- `tests/test_quantization.py`: 16 tests (threshold calculation, boundary conditions, both encodings, sample sequence preservation, constant segments, partial segments, channel isolation, KAR formula, level agreement, invalid configs, invalid inputs, dummy dataset, CLI export, XLSX companion, cell limit chunking, plotting).
- `tests/test_filter.py`: 11 tests (intermediate step validation against independent 2-step example, channel isolation, sample indexing, constant-input behavior, numerical safeguards, invalid configs, non-finite inputs, dummy dataset, CLI integration).
- `tests/test_correlation.py`: 8 tests (perfect positive/negative, zero correlation, zero variance, invalid dimensions, NaN/Inf, SciPy reference parity).
- `tests/test_loader.py`: 6 tests (missing columns, non-numeric values, empty cells, row ordering preservation, arbitrary $N$).
- `tests/test_plotting.py`: 11 tests (duplicate point aggregation math, dimension checks, figure generation, headless export, CSV-only execution, comparison figure generation, PRBS KAR records input, PRBS KAR CSV input with self-contained tmp_path fixture, PRBS input validation, CLI PRBS figure export, CLI PRBS auto-derivation).
- `tests/test_reconciliation.py`: 15 tests (BCH code cache & properties validation, privacy amplification removal verification, error-free recovery, controlled error-correction up to t, beyond-t error handling, zero-padding addition & stripping, receiver/Eve channel isolation, 2-path reconciliation with obsolete option rejection, identical path parameter verification, second small valid BCH configuration test, dynamic CSV/JSON/XLSX companion exporters, CLI full pipeline, obsolete CLI options rejection, global BCH code properties & metadata, global BCH 2-path recovery & 2x2 figure export).

## 5. Verification Records
- **Clean Environment**: Project installed in isolated local `.venv` via `pip install -e ".[dev]"`.
- **Test Suite & Independence**: 85 automated tests pass (`pytest -v` exited 0 with 85/85 passing in ~60s).
  - *Test Independence Audit*: Identified that `test_plot_prbs_kar_comparison_figure_from_csv` previously relied on pre-existing `outputs/dummy_rssi_prbs_metrics.csv`. Fixed by generating isolated synthetic CSV data within pytest's `tmp_path`. Verified by executing the full 85-test suite with `outputs/` completely unavailable (`outputs_backup`); all 85 tests passed cleanly with zero cross-test or disk dependencies.
  - *Decoding Rigor*: Distinction between detected failures and miscorrections is mathematically enforced. The decoder operates solely on syndromes and does not have access to the true channel error count; channel errors exceeding $t$ produce either detected failure or miscorrection.
- **CLI Execution**: Executed raw-only, filtering-only, quantization, PRBS, and global BCH reconciliation pipelines against the dummy workbook; verified 500-sample count, 10 segments, 1,000 bits (2-bit Gray), 2,000 bits (4-bit), 1,500 PRBS bits (2-bit), 7,500 PRBS bits (4-bit), global BCH(1023, 46, 200) reconciliation without interleaving across both supported 2-bit paths (`quant_2bit` and `prbs_2bit`), direct bitstream equality verification, CSV/JSON metadata, companion XLSX workbooks with text `@` cells, and 300-dpi/PDF 2×2 visualization figures.

### Two-Path Global BCH Reconciliation Results (BCH(1023, 46, 200), Interleaving OFF)
- **Global Parameters**: $n = 1023, k = 46, d = 401, t = 200$ (derived $d = 2t + 1$), Interleaving `OFF`. Single configuration source for both paths and all receivers.
- **`quant_2bit` (1 block, 23 pad bits excluded)**:
  - Alice–Bob: Pre-KAR 80.40% $\to$ Post-KAR 100.00% ($\Delta = +19.60\text{ pp}$), Exact: TRUE, Blocks (S/F/M): 1/0/0.
  - Alice–Eve1-Alice: Pre-KAR 58.20% $\to$ Post-KAR 58.20% ($\Delta = +0.00\text{ pp}$), Exact: FALSE, Blocks (S/F/M): 0/1/0.
  - Bob–Eve1-Bob: Pre-KAR 55.40% $\to$ Post-KAR 55.40% ($\Delta = +0.00\text{ pp}$), Exact: FALSE, Blocks (S/F/M): 0/1/0.
- **`prbs_2bit` (2 blocks, 546 pad bits excluded)**:
  - Alice–Bob: Pre-KAR 76.27% $\to$ Post-KAR 100.00% ($\Delta = +23.73\text{ pp}$), Exact: TRUE, Blocks (S/F/M): 2/0/0.
  - Alice–Eve1-Alice: Pre-KAR 56.53% $\to$ Post-KAR 68.93% ($\Delta = +12.40\text{ pp}$), Exact: FALSE, Blocks (S/F/M): 1/1/0.
  - Bob–Eve1-Bob: Pre-KAR 56.27% $\to$ Post-KAR 56.27% ($\Delta = +0.00\text{ pp}$), Exact: FALSE, Blocks (S/F/M): 0/2/0.

## 6. Windows PowerShell Reproduction Commands
> The primary execution guide with output locations is maintained in [README.md](../README.md#petunjuk-penyiapan-lingkungan--eksekusi).

```powershell
# 1. Run automated test suite (85 tests)
.\.venv\Scripts\python.exe -m pytest -v

# 2. Run default correlation analysis (raw only)
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"

# 3. Run filtering and correlation pipeline (MSHKF + Raw vs Filtered export)
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --figure-prefix "outputs/dummy_rssi_filtered"

# 4. Run full pipeline with Modified ADQ Quantization stage, companion XLSX, and KAR comparison charts
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
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
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
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

# 6. Run full pipeline through global BCH reconciliation and candidate key generation
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --reconcile-metrics-output "outputs/dummy_rssi_reconcile_metrics.csv" `
  --reconcile-blocks-output "outputs/dummy_rssi_reconcile_blocks.csv" `
  --reconcile-config-output "outputs/dummy_rssi_reconcile_config.json" `
  --reconcile-keys-output "outputs/dummy_rssi_reconcile_keys.json" `
  --reconciled-xlsx-output "outputs/dummy_rssi_reconciled.xlsx" `
  --reconcile-figure-prefix "outputs/dummy_rssi_reconciliation"
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
  - **Global BCH Secrecy Limitation**: While global $\text{BCH}(1023, 46, 200)$ successfully reconciles both paths to 100% KAR for Alice–Bob, without interleaving known padding reveals the final PRBS block ({pad} = 546$ on Block 1); the reported full-stream attack additionally uses per-sample PRBS parity constraints to achieve joint $\text{GF}(2)$ full rank 92/92 across both blocks, allowing Eve to solve Alice's private message algebraically from helper data alone. Standard Eve decoder failure does not establish secrecy.
  - **Mandatory Disclaimer**: *Dummy-data comparison; shared configuration has reported public-information leakage. KAR does not establish secrecy.* This shared configuration mode is strictly for algorithmic benchmarking and comparative analysis; it is **NOT** claimed to be cryptographically secure.
- **Pipeline Roadmap**:
  1. *Completed*: Implemented Modified Sage–Husa Adaptive Kalman Filter (MSHKF) stage.
  2. *Completed*: Implemented Modified Adaptive Dual-Threshold Quantization (MADQ) stage (`PA.pdf` Section 3.2.3, Equations 3.21–3.23) and KAR evaluation (Equation 3.64).
  3. *Completed*: Implemented Bit Expansion with Galois XOR-LFSR PRBS generator (`PA.pdf` Section 3.2.4 as background) and before/after KAR evaluation.
  4. *Completed*: Implemented BCH Codeword-based Information Reconciliation (`PA.pdf` Section 3.2.5, Equations 3.32–3.36). Privacy Amplification (`PA.pdf` Section 3.2.6) is postponed to a future request.
  5. *Completed*: Unified global BCH configuration architecture (`DEFAULT_BCH_CODE = (1023, 46, 200)` with derived $d=401$, Interleaving OFF), eliminated legacy mode branching, rejected obsolete flags with migration messages, and validated 85 automated tests.
  6. *Proposal*: Implement physical channel probing with real wireless hardware and evaluate empirical entropy.
