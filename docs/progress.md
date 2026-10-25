# Project Progress & Handoff: RSSI-based Secret Key Generation (SKG)

## 1. Project Purpose & Methodological Reference
This research project develops a physical-layer Secret Key Generation (SKG) pipeline based on Received Signal Strength Indicator (RSSI) measurements.

The project currently implements four sequential pipeline stages:
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

4. **PRBS Expansion Stage (Galois XOR-LFSR)**: Citing LFSR principles in **`PA.pdf`, Section 3.2.4 (pages 28–29)** as background (with characteristic polynomial Equation 3.24 and period Equation 3.26):

```math
f(x) = c_m x^m + c_{m-1} x^{m-1} + \dots + c_1 x + c_0 \qquad (3.24)
```

**Implementation-specific Galois state update**:
```math
S_{k+1} = \left((S_k \ll 1) \wedge (2^m - 1)\right) \oplus \left(c \cdot \text{MSB}(S_k)\right)
```

**Methodological Boundary**: Physical channel probing is **postponed, not replaced**. All current calculations use synthetic indoor dummy data strictly for **software validation** (pipeline integrity, parser correctness, mathematical accuracy), not for empirical claims regarding wireless channel reciprocity or eavesdropping resistance. Parameters such as $W=50$ and $\alpha=0.5$ are provisional software-validation settings, not optimized physical-channel parameters. Deterministic LFSR expansion does not add physical channel entropy.

## 2. Dataset & Semantics
- **File Path**: `data/raw/dummy/Dummy RSSI (data Indoor).xlsx`
- **SHA-256**: `50A3459CB0A09D0A2897A2872E18D977EF6ECE0C7FCB68C0549BDB4CD780A0EE`
- **Observations**: 500 rows. Row-wise pairing is strictly confirmed: row index $i$ corresponds to the exact same observation instance across all channels. Row order and sample alignment are strictly preserved throughout filtering and quantization.
- **Column Definitions**:
  - `Alice`: RSSI received by Alice from Bob's signal transmission.
  - `Bob`: RSSI received by Bob from Alice's signal transmission.
  - `Eve1-Alice`: RSSI overheard by eavesdropper Eve from Alice's transmission.
  - `Eve1-Bob`: RSSI overheard by eavesdropper Eve from Bob's transmission.

## 3. Implemented Modules & Validated Results
- **Workbook Loader (`src/rssi_skg/loader.py`)**: Uses `openpyxl` to read raw workbooks; validates presence of all 4 required headers; enforces numeric cell types; reports exact row and column upon encountering missing/invalid values; supports arbitrary sample sizes $N \ge 2$.
- **Modified Sage–Husa Adaptive Kalman Filter (`src/rssi_skg/filter.py`)**:
  - Implements scalar MSHKF with modeling assumptions $`\Phi = 1.0`$ and $`H = 1.0`$.
  - Adaptive memory parameter $b = 0.99$ is a selected value within the literature range $(0.95, 0.999)$ mentioned in `PA.pdf` Section 3.2.2. Initial weight $D_0 = 1.0$.
  - Parameters $P_0 = 1.0\ \text{dBm}^2, Q = 0.1\ \text{dBm}^2, R_0 = 1.0\ \text{dBm}^2$ are uncalibrated software-validation assumptions.
  - Process noise covariance $Q = 0.1\ \text{dBm}^2$ is held fixed based on `PA.pdf` Section 3.2.2's final modeling assumption (known prior). Consequently, online adaptation is performed on measurement noise covariance $`\hat{R}_k`$ while Equation (3.20) for adaptive $Q$ update is not executed.
  - Online adaptation of $`\hat{R}_k`$ and recursive updates for noise means $`\hat{q}_k`$ and $`\hat{r}_k`$ are retained.
  - Sample indexing policy: auto-initialization from first sample $`x_0 = z_0`$ sets output[0] = $z_0$ and starts recursion at sample $1$ ($k=1$), strictly avoiding double-counting $z_0$.
  - Enforces independent filter instances across Alice, Bob, Eve1-Alice, and Eve1-Bob for strict channel isolation.
- **Correlation Calculation (`src/rssi_skg/correlation.py`)**: Computes centered zero-lag Pearson correlation $`\rho`$ in `float64` precision; validates equal lengths; rejects $N < 2$, NaN, and Inf; raises explicit `ValueError` on constant sequences (zero variance).
- **Modified Adaptive Dual-Threshold Quantization (`src/rssi_skg/quantization.py`)**:
  - Segment-based adaptive threshold calculation: non-overlapping segments with configurable default window size $W = 50$, multiplier $\alpha = 0.5$, and population standard deviation ($\text{ddof} = 0$).
  - Full sample coverage: processes all samples, including any shorter final segment.
  - Sample retention: all samples are retained; no sample in the intermediate zone is discarded. Constant segments ($\sigma = 0$) unconditionally produce level 1.
  - Channel isolation: each channel's mean, standard deviation, and thresholds are calculated independently with zero cross-channel contamination.
  - Dual binary encodings generated simultaneously in every run:
    - **2-bit Gray code**: $`0 \rightarrow 00`$, $`1 \rightarrow 01`$, $`2 \rightarrow 11`$ (implementation choice to minimize bit errors for adjacent state transitions).
    - **4-bit code**: $`0 \rightarrow 1010`$, $`1 \rightarrow 1011`$, $`2 \rightarrow 1001`$ (per `PA.pdf` Section 3.2.3, page 28).
  - Bitstreams preserve temporal sample order.
  - Evaluation: Bit-level Key Agreement Rate (KAR) per `PA.pdf` Equation (3.64), sample-level agreement rate, and per-channel level frequencies.
  - **Companion XLSX Export (`export_quantized_workbook_xlsx`)**:
    - Creates a 4-sheet multi-tab workbook (`Quantized Samples`, `Bitstreams`, `Agreement Metrics`, `Segment Thresholds`) using existing `openpyxl`.
    - Stores bit encodings (`"00"`, `"01"`, `"11"`, `"1010"`, etc.) explicitly as string cells (`cell.data_type = 's'`) with Text format (`cell.number_format = '@'`), overcoming Microsoft Excel's automatic number conversion that drops leading zeros from CSVs.
    - Explicitly handles Excel's single-cell limit of 32,767 characters by splitting long bitstreams across sequential parts (`part`, `total_parts`) with zero silent data truncation.
  - **KAR Comparison Visualization (`plot_kar_comparison_figure`)**:
    - Generates 4-panel 300-dpi PNG and vector PDF (`_quantization.png` / `_quantization.pdf`).
    - Top-Left: Grouped bar chart comparing 2-bit Gray KAR and 4-bit KAR across Alice–Bob, Alice–Eve1-Alice, and Bob–Eve1-Bob with fixed 0–100% axis, explicit value labels, and annotation noting the fixed-prefix relation ($`\text{KAR}_{\text{4bit}} = 50\% + \text{KAR}_{\text{2bit}} / 2`$).
    - Top-Right: Companion sample-level agreement rate panel clearly separated from bitstream KAR.
    - Bottom-Left: Formatted metrics summary table.
    - Bottom-Right: Monospace mathematical explanation box explaining why 4-bit KAR is elevated due to fixed `'10'` prefix structure (structural minimum agreement of 50%, with exact relation $`\text{KAR}_{\text{4bit}} = 50\% + \text{KAR}_{\text{2bit}} / 2`$) rather than genuine physical reciprocity or added entropy.
- **CLI Interface (`src/rssi_skg/cli.py`)**:
  - Default behavior: raw correlation only (backward compatible).
  - Optional `--filter`: executes MSHKF, exports aligned raw/filtered samples CSV, metadata JSON, and comparison plots.
  - Optional `--quantize`: executes MADQ on MSHKF-filtered RSSI, exports aligned sample-level quantization CSV, segment thresholds CSV, bitstreams CSV, quantization metrics CSV, configuration metadata JSON, companion XLSX workbook (`--quantized-xlsx-output`), and quantization comparison plots (`--quantize-figure-prefix`).
- **Validated Results on Dummy Dataset ($N=500$, `data_kind=dummy`)**:
  - **Correlation Results**:
    - `Alice–Bob`: Raw $`\rho = +0.632263`$, Filtered $`\rho = +0.842244`$ ($`\Delta\rho = +0.209981`$)
    - `Alice–Eve1-Alice`: Raw $`\rho = +0.017060`$, Filtered $`\rho = -0.013725`$ ($`\Delta\rho = -0.030784`$)
    - `Bob–Eve1-Bob`: Raw $`\rho = +0.119310`$, Filtered $`\rho = +0.015151`$ ($`\Delta\rho = -0.104159`$)
  - **Quantization & Agreement Results ($W=50, \alpha=0.5, \text{ddof}=0$)**:
    - Segments: exactly 10 segments (50 samples each).
    - Bitstream Lengths: exactly 1,000 bits per channel (2-bit Gray) and 2,000 bits per channel (4-bit).
    - `Alice–Bob`: Level Agreement = 64.4000% (322/500), 2-bit Gray KAR = 80.4000% (804/1000), 4-bit KAR = 90.2000% (1804/2000).
    - `Alice–Eve1-Alice`: Level Agreement = 34.8000% (174/500), 2-bit Gray KAR = 58.2000% (582/1000), 4-bit KAR = 79.1000% (1582/2000).
    - `Bob–Eve1-Bob`: Level Agreement = 34.4000% (172/500), 2-bit Gray KAR = 55.4000% (554/1000), 4-bit KAR = 77.7000% (1554/2000).
  - **Channel Level Distributions**:
    - `Alice`: Level 0 = 127 (25.40%), Level 1 = 219 (43.80%), Level 2 = 154 (30.80%)
    - `Bob`: Level 0 = 169 (33.80%), Level 1 = 161 (32.20%), Level 2 = 170 (34.00%)
    - `Eve1-Alice`: Level 0 = 147 (29.40%), Level 1 = 193 (38.60%), Level 2 = 160 (32.00%)
    - `Eve1-Bob`: Level 0 = 164 (32.80%), Level 1 = 147 (29.40%), Level 2 = 189 (37.80%)
  - **Critical Encoding Analysis**:
    In the 4-bit representation (`1010`, `1011`, `1001`), the first two bits (`10`) are identical across all levels. Consequently, 50% of the bits match unconditionally, elevating eavesdropper KAR to ~77–79% even when level agreement is only ~34%. Reporting level agreement alongside bit-level KAR keeps encoding effects fully visible. Encoded bit length must not be equated with physical entropy or cryptographic security.
  - **PRBS Expansion Stage (Galois XOR-LFSR, `src/rssi_skg/prbs.py`)**:
    - **Galois Recurrence**: Left-shift LFSR with MSB emitted at each step; if MSB=1, next state is XORed with the feedback mask.
    - **Primitive Polynomials & Register Sizes**:
      * Degree 2 ($m=2$): $`f(x) = x^2 + x + 1`$, Galois mask `0b11` (3), produces exactly 3 bits/sample (1,500 bits/channel for 500 samples), maximal period 3 for non-zero seeds.
      * Degree 4 ($m=4$): $`f(x) = x^4 + x + 1`$, Galois mask `0b0011` (3), produces exactly 15 bits/sample (7,500 bits/channel for 500 samples), maximal period 15 for non-zero seeds.
    - **Per-Sample Deterministic Resets**: LFSR is initialized with each sample's exact codeword seed, stepped $`2^m-1`$ times, and outputs are concatenated in temporal sample order. Both encoding paths and all 4 channels are processed with strict isolation.
    - **Explicit Zero-Seed Handling (Deliberate Exception to `PA.pdf` Section 3.2.4)**: Seed `"00"` strictly produces `"000"`, locks up at state 0 with `actual_period = 1`, and `is_zero_state = True`. Samples are never discarded and seeds are never remapped.
    - **Pre- vs. Post-PRBS Key Agreement Rate (KAR) ($N=500$, `data_kind=dummy`)**:
      * `Alice–Bob`:
        - 2-bit Gray KAR: Pre = `80.4000%` $\to$ Post = `76.2667%` (1144/1500 matches, $`\Delta = -4.1333\text{ pp}`$)
        - 4-bit KAR: Pre = `90.2000%` $\to$ Post = `81.0133%` (6076/7500 matches, $`\Delta = -9.1867\text{ pp}`$)
      * `Alice–Eve1-Alice`:
        - 2-bit Gray KAR: Pre = `58.2000%` $\to$ Post = `56.5333%` (848/1500 matches, $`\Delta = -1.6667\text{ pp}`$)
        - 4-bit KAR: Pre = `79.1000%` $\to$ Post = `65.2267%` (4892/7500 matches, $`\Delta = -13.8733\text{ pp}`$)
      * `Bob–Eve1-Bob`:
        - 2-bit Gray KAR: Pre = `55.4000%` $\to$ Post = `56.2667%` (844/1500 matches, $`\Delta = +0.8667\text{ pp}`$)
        - 4-bit KAR: Pre = `77.7000%` $\to$ Post = `65.0133%` (4876/7500 matches, $`\Delta = -12.6867\text{ pp}`$)
    - **Zero-Seed Statistics**:
      * 2-bit Gray Path: Alice = 127 (25.40%), Bob = 169 (33.80%), Eve1-Alice = 147 (29.40%), Eve1-Bob = 164 (32.80%).
      * 4-bit Path: 0 (0.00%) across all channels.
    - **Scientific Entropy & Security Warning**: Deterministic LFSR expansion does not add physical channel entropy. Repeated encodings produce identical expanded output blocks. Post-PRBS KAR decreases because deterministic bit dispersion across 15 states breaks the artificial 50% match bias of the static `'10'` prefix in 4-bit MADQ codewords.
    - **PRBS KAR Comparison Visualization (`plot_prbs_kar_comparison_figure`)**:
      * Implemented in `src/rssi_skg/plotting.py` with reproducible CLI option `--prbs-figure-prefix`.
      * Automatically generates 4-panel 2×2 300-dpi PNG and vector PDF (`_prbs_kar.png` / `_prbs_kar.pdf`).
      * Panel (a) Top-Left: Grouped bar chart comparing pre- vs. post-PRBS KAR for the 2-bit Gray path (1,000b $\to$ 1,500b) with fixed 0–100% axis, explicit percentage labels, and delta percentage point (`pp`) annotations.
      * Panel (b) Top-Right: Grouped bar chart comparing pre- vs. post-PRBS KAR for the 4-bit path (2,000b $\to$ 7,500b) with fixed 0–100% axis, explicit percentage labels, and delta percentage point (`pp`) annotations.
      * Panel (c) Bottom-Left: Sample-level agreement rate chart across the three channel pairs (Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob), clearly distinguished from bit-level KAR.
      * Panel (d) Bottom-Right: Compact metrics summary table reporting level agreement, pre- and post-PRBS KAR, and signed differences in percentage points (pp), alongside a concise methodological notes box reiterating that dummy data is for software validation only, deterministic PRBS expansion does not add source entropy, seed `00` remains unchanged with actual period 1, and lower eavesdropper KAR does not prove security.
  - **Generated Output Artifacts in `outputs/`**:
    - `dummy_rssi_filtered_correlation.csv`
    - `dummy_rssi_filtered_samples.csv`
    - `dummy_rssi_filter_config.json`
    - `dummy_rssi_quantized_samples.csv` (clean machine-readable CSV)
    - `dummy_rssi_quantized_segments.csv`
    - `dummy_rssi_quantized_bitstreams.csv`
    - `dummy_rssi_quantize_metrics.csv`
    - `dummy_rssi_quantize_config.json`
    - `dummy_rssi_quantized.xlsx` (multi-sheet companion Excel workbook)
    - `dummy_rssi_filtered.png` & `.pdf`
    - `dummy_rssi_quantization.png` & `.pdf` (KAR comparison visualization)
    - `dummy_rssi_correlation.csv`, `.png` & `.pdf` (legacy raw run)
    - `dummy_rssi_prbs_samples.csv` (sample-level expansion table with zero-state tracking)
    - `dummy_rssi_prbs_bitstreams.csv` (concatenated PRBS bitstreams)
    - `dummy_rssi_prbs_metrics.csv` (before/after KAR comparison metrics)
    - `dummy_rssi_prbs_config.json` (PRBS metadata and zero-seed counts)
    - `dummy_rssi_prbs.xlsx` (companion multi-sheet Excel workbook with >32k cell chunking)
    - `dummy_rssi_prbs_kar.png` & `.pdf` (2×2 PRBS KAR visualization comparison figure)

## 4. Key Source & Test File Responsibilities
- `src/rssi_skg/prbs.py`: Galois XOR-LFSR engine (`GaloisLFSR`), primitive polynomial definitions, `PRBSConfig`, `expand_seed`, `expand_channel_prbs`, `expand_channels_prbs`, artifact CSV/JSON exporters, and `export_prbs_workbook_xlsx` (with Text format cell preservation and `EXCEL_MAX_CELL_CHARS` chunking).
- `src/rssi_skg/quantization.py`: Modified ADQ engine, `QuantizationConfig`, `SegmentThresholds`, `ChannelQuantizationResult`, `quantize_series`, `quantize_channels`, `encode_levels_to_bits`, `calculate_kar`, `calculate_level_agreement`, `calculate_level_frequencies`, CSV/JSON export functions, and `export_quantized_workbook_xlsx`.
- `src/rssi_skg/filter.py`: Scalar MSHKF engine, `FilterConfig`, `ModifiedSageHusaFilter`, `filter_rssi_channels`.
- `src/rssi_skg/correlation.py`: Pure mathematical Pearson implementation and input sanity checking.
- `src/rssi_skg/loader.py`: Excel workbook ingestion, column validation, and row pairing.
- `src/rssi_skg/plotting.py`: Bubble aggregation, raw figure rendering, filtered comparison figure rendering, quantization KAR figure (`plot_kar_comparison_figure`), and 2×2 PRBS KAR comparison figure (`plot_prbs_kar_comparison_figure`).
- `src/rssi_skg/cli.py`: Command-line parsing, optional filtering, quantization, and PRBS dispatch with prerequisite chaining, companion XLSX export dispatch, figure prefix routing (`--prbs-figure-prefix`), and stdout user guidance.
- `tests/test_prbs.py`: 12 tests (primitive polynomial verification, zero-state lockup, known-answer sequences, requested length vs. period distinction, input validation, deterministic resets, channel isolation & ordering, multi-channel expansion & KAR, artifact exports, Excel cell chunking, CLI pipeline integration).
- `tests/test_quantization.py`: 16 tests (threshold calculation, boundary conditions, both encodings, sample sequence preservation, constant segments, partial segments, channel isolation, KAR formula, level agreement, invalid configs, invalid inputs, dummy dataset verification, CLI artifact export, XLSX companion export with leading zeros, XLSX 32,767 cell limit chunking, and KAR comparison plotting integration).
- `tests/test_filter.py`: 11 tests (intermediate step validation against independent 2-step example, channel isolation, sample indexing, constant-input behavior, numerical safeguards, invalid configs, non-finite inputs, dummy dataset, CLI integration).
- `tests/test_correlation.py`: 8 tests (perfect positive/negative, zero correlation, zero variance, invalid dimensions, NaN/Inf, SciPy reference parity).
- `tests/test_loader.py`: 6 tests (missing columns, non-numeric values, empty cells, row ordering preservation, arbitrary $N$).
- `tests/test_plotting.py`: 11 tests (duplicate point aggregation math, dimension checks, figure generation, headless export, CSV-only execution, comparison figure generation, PRBS KAR records input, PRBS KAR CSV input, PRBS input validation, CLI PRBS figure export, CLI PRBS auto-derivation).

## 5. Verification Records
- **Clean Environment**: Project installed in isolated local `.venv` via `pip install -e ".[dev]"`.
- **Test Suite**: 67 automated tests pass (`pytest -v` exited 0 with 67/67 passing in ~48s).
- **CLI Execution**: Executed raw-only, filtering-only, quantization, and full PRBS pipelines against the dummy workbook; verified 500-sample count, 10 segments, 1,000 bits (2-bit Gray), 2,000 bits (4-bit), 1,500 PRBS bits (2-bit), 7,500 PRBS bits (4-bit), CSV float precision, JSON metadata, XLSX companion workbooks with text cells, and 300-dpi/PDF KAR visualization figures (`dummy_rssi_prbs_kar.png` / `.pdf`).

## 6. Windows PowerShell Reproduction Commands
> The primary execution guide with output locations is maintained in [README.md](../README.md#petunjuk-penyiapan-lingkungan--eksekusi).

```powershell
# 1. Run automated test suite (67 tests)
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
```

## 7. Current Git State & Verification
- **Active Branch**: `main`.
- **Working Tree Policy**: All modified and untracked files remain strictly unstaged in the working tree awaiting user review. No commits or pushes have been performed.
- **Gitignore Status**: Inspected `.gitignore`. The existing rule `outputs/*` (with `!outputs/.gitkeep`) already covers all generated quantization and PRBS artifacts. No `.gitignore` modification was required.

## 8. Remaining Limitations & Proposed Next Steps
- **Limitations**:
  - Operates on synthetic indoor dummy data for software verification; cannot establish empirical secrecy.
  - Channel probing hardware is deferred to a subsequent physical testing phase.
  - Parameters $W=50$ and $\alpha=0.5$ are provisional software-validation settings, not optimized physical-channel parameters.
  - PRBS bit expansion is deterministic and does not add physical channel entropy.
- **Pipeline Roadmap**:
  1. *Completed*: Implemented Modified Sage–Husa Adaptive Kalman Filter (MSHKF) stage.
  2. *Completed*: Implemented Modified Adaptive Dual-Threshold Quantization (MADQ) stage (`PA.pdf` Section 3.2.3, Equations 3.21–3.23) and KAR evaluation (Equation 3.64).
  3. *Completed*: Implemented Bit Expansion with Galois XOR-LFSR PRBS generator (`PA.pdf` Section 3.2.4 as background) and before/after KAR evaluation.
  4. *Proposal*: Implement Information Reconciliation (Syndrome Reconciliation with BCH Codes).
  5. *Proposal*: Implement Privacy Amplification (SHA-256 compression).
  6. *Proposal*: Transition to physical channel probing with real wireless hardware when available.
