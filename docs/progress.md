# Project Progress & Handoff: RSSI-based Secret Key Generation (SKG)

## 1. Project Purpose & Methodological Reference
This research project develops a physical-layer Secret Key Generation (SKG) pipeline based on Received Signal Strength Indicator (RSSI) measurements.

The project currently implements two key sequential stages:
1. **RSSI Filtering Stage**: Modified Sage–Husa Adaptive Kalman Filter (MSHKF) based on **`PA.pdf`, Section 3.2.2, Equations (3.10)–(3.20), pages 26–27**.
2. **Zero-Lag Pearson Correlation Analysis**: As defined in **`PA.pdf`, Equation (3.62), page 34**:

$$
\rho_{u,v} =
\frac{
\sum_{n=1}^{N}
\left(X_u(n)-\mu_u\right)
\left(X_v(n)-\mu_v\right)
}{
\sqrt{\sum_{n=1}^{N}\left(X_u(n)-\mu_u\right)^2}
\sqrt{\sum_{n=1}^{N}\left(X_v(n)-\mu_v\right)^2}
}
$$

Where:
- $X_u(n)$: RSSI sample value of channel $u$ at observation index $n$.
- $X_v(n)$: RSSI sample value of channel $v$ at observation index $n$.
- $\mu_u$: Sample mean of RSSI channel $u$ over $N$ observations ($\mu_u = \frac{1}{N}\sum_{n=1}^N X_u(n)$).
- $\mu_v$: Sample mean of RSSI channel $v$ over $N$ observations ($\mu_v = \frac{1}{N}\sum_{n=1}^N X_v(n)$).
- $N$: Total number of observation pairs ($N = 500$ in validation dummy dataset).
*(Note: The $u, v$ notation is mathematically equivalent to the previous $X, Y$ notation).*

**Methodological Boundary**: Physical channel probing is **postponed, not replaced**. All current calculations use synthetic indoor dummy data strictly for **software validation** (pipeline integrity, parser correctness, mathematical accuracy), not for empirical claims regarding wireless channel reciprocity or eavesdropping resistance.

## 2. Dataset & Semantics
- **File Path**: `data/raw/dummy/Dummy RSSI (data Indoor).xlsx`
- **SHA-256**: `50A3459CB0A09D0A2897A2872E18D977EF6ECE0C7FCB68C0549BDB4CD780A0EE`
- **Observations**: 500 rows. Row-wise pairing is strictly confirmed: row index $i$ corresponds to the exact same observation instance across all channels. Row order is preserved without sorting.
- **Column Definitions**:
  - `Alice`: RSSI received by Alice from Bob's signal transmission.
  - `Bob`: RSSI received by Bob from Alice's signal transmission.
  - `Eve1-Alice`: RSSI overheard by eavesdropper Eve from Alice's transmission.
  - `Eve1-Bob`: RSSI overheard by eavesdropper Eve from Bob's transmission.

## 3. Implemented Modules & Filter/Correlation Results
- **Workbook Loader (`src/rssi_skg/loader.py`)**: Uses `openpyxl` to read raw workbooks; validates presence of all 4 required headers; enforces numeric cell types; reports exact row and column upon encountering missing/invalid values; supports arbitrary sample sizes $N \ge 2$.
- **Modified Sage–Husa Adaptive Kalman Filter (`src/rssi_skg/filter.py`)**:
  - Implements scalar MSHKF with modeling assumptions $\Phi = 1.0$ and $H = 1.0$.
  - Adaptive memory parameter $b = 0.99$ is a selected value within the literature range $(0.95, 0.999)$ mentioned in `PA.pdf` Section 3.2.2, not an explicitly prescribed single value. Initial weight $D_0 = 1.0$.
  - Parameters $P_0 = 1.0\ \text{dBm}^2, Q = 0.1\ \text{dBm}^2, R_0 = 1.0\ \text{dBm}^2$ are uncalibrated software-validation assumptions, not measured channel or transceiver properties.
  - Process noise covariance $Q = 0.1\ \text{dBm}^2$ is held fixed based on `PA.pdf` Section 3.2.2's final modeling assumption (process noise covariance assumed known). Consequently, online adaptation is performed on measurement noise covariance $\hat{R}_k$ while Equation (3.20) for adaptive $Q$ update is not executed.
  - Adaptive measurement noise covariance $\hat{R}_k$ and recursive updates for noise means $\hat{q}_k$ and $\hat{r}_k$ are retained.
  - Preserves exact update sequence, using the updated $\hat{r}_k$ in calculating innovation $e_k$.
  - Sample indexing policy: auto-initialization from first sample $x_0 = z_0$ sets output[0] = $z_0$ and starts recursion at sample $1$ ($k=1$), strictly avoiding double-counting $z_0$.
  - Enforces independent filter instances across Alice, Bob, Eve1-Alice, and Eve1-Bob for strict channel isolation.
- **Correlation Calculation (`src/rssi_skg/correlation.py`)**: Computes centered zero-lag Pearson correlation $\rho$ in `float64` precision; validates equal lengths; rejects $N < 2$, NaN, and Inf; raises explicit `ValueError` on constant sequences (zero variance).
- **Plotting & Visualization (`src/rssi_skg/plotting.py`)**:
  - `plot_combined_correlation_figure`: Top horizontal bar chart + bottom 3 bubble scatter panels for raw correlation.
  - `plot_filtering_comparison_figure`: Top-left grouped horizontal bar chart (Raw vs Filtered $\rho$) + top-right time-series trajectory smoothing snippet (samples 0–79) + bottom 3 bubble scatter panels for filtered data.
  - Exports: 300 dpi PNG and vector PDF using Matplotlib `Agg` backend.
- **CLI Interface (`src/rssi_skg/cli.py`)**:
  - Default behavior: raw correlation only (backward compatible).
  - Optional `--filter`: executes MSHKF, exports aligned raw/filtered samples CSV, metadata JSON, and comparison plots.
- **Validated Results on Dummy Dataset ($N=500$, `data_kind=dummy`)**:
  - `Alice–Bob`: Raw $\rho = +0.632263$, Filtered $\rho = +0.842244$ ($\Delta\rho = +0.209981$)
  - `Alice–Eve1-Alice`: Raw $\rho = +0.017060$, Filtered $\rho = -0.013725$ ($\Delta\rho = -0.030784$)
  - `Bob–Eve1-Bob`: Raw $\rho = +0.119310$, Filtered $\rho = +0.015151$ ($\Delta\rho = -0.104159$)
  - Generated output files in `outputs/`:
    - `dummy_rssi_filtered_correlation.csv`
    - `dummy_rssi_filtered_samples.csv`
    - `dummy_rssi_filter_config.json`
    - `dummy_rssi_filtered.png` & `.pdf`
    - `dummy_rssi_correlation.csv`, `.png` & `.pdf` (legacy raw run)

## 4. Key Source & Test File Responsibilities
- `src/rssi_skg/filter.py`: Scalar MSHKF engine, `FilterConfig`, `ModifiedSageHusaFilter`, `filter_rssi_channels`.
- `src/rssi_skg/correlation.py`: Pure mathematical Pearson implementation and input sanity checking.
- `src/rssi_skg/loader.py`: Excel workbook ingestion, column validation, and row pairing.
- `src/rssi_skg/plotting.py`: Bubble aggregation, raw figure rendering, and filtered comparison figure rendering.
- `src/rssi_skg/cli.py`: Command-line parsing, optional filtering dispatch, CSV/JSON/figure export.
- `tests/test_filter.py`: 11 tests (intermediate step validation against independent 2-step example, channel isolation, sample indexing, constant-input behavior, numerical safeguards, invalid configs, non-finite inputs, dummy dataset, CLI integration).
- `tests/test_correlation.py`: 8 tests (perfect positive/negative, zero correlation, zero variance, invalid dimensions, NaN/Inf, SciPy reference parity).
- `tests/test_loader.py`: 6 tests (missing columns, non-numeric values, empty cells, row ordering preservation, arbitrary $N$).
- `tests/test_plotting.py`: 6 tests (duplicate point aggregation math, dimension checks, figure generation, headless export, CSV-only execution, comparison figure generation).

## 5. Verification Records
- **Clean Environment**: Project installed in isolated local `.venv` via `pip install -e ".[dev]"`.
- **Test Suite**: Recorded full pass of all 31 automated tests (`pytest -v` exited 0). Reused without re-running for documentation-only edits.
- **CLI Execution**: Executed both default (unfiltered) and filtered analysis pipelines against the dummy workbook; verified 500-sample count, float64 precision in CSV, metadata JSON, and simultaneous PNG/PDF generation.
- **Visual Inspection**: Inspected both `outputs/dummy_rssi_filtered.png` and `outputs/dummy_rssi_filtered.pdf`; confirmed grouped bar chart labels, time-series smoothing plot, density bubble scatter panels, zero text clipping, and software-validation disclaimer.

## 6. Windows PowerShell Reproduction Commands
> The primary execution guide with output locations is maintained in [README.md](../README.md#petunjuk-penyiapan-lingkungan--eksekusi).

```powershell
# 1. Run automated test suite (31 tests)
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
```

## 7. Current Git State & Verification
- **Active Branch**: `main`.
- **Working Tree Policy**: All modified and untracked files remain strictly unstaged in the working tree awaiting user review. No commits or pushes have been performed.

## 8. Remaining Limitations & Proposed Next Steps
- **Limitations**: Analysis operates on synthetic indoor dummy data for software verification; cannot establish empirical secrecy; channel probing hardware is deferred.
- **Proposed Future Steps**:
  1. *Completed*: Implemented Modified Sage–Husa Adaptive Kalman Filter (MSHKF) stage.
  2. *Proposal*: Implement Modified Adaptive Dual-Threshold Quantization (MADQ) stage (`PA.pdf` Section 3.2.3, Equations 3.21–3.23).
  3. *Proposal*: Implement Bit Expansion with Galois LFSR PRBS generator (`PA.pdf` Section 3.2.4).
  4. *Proposal*: Implement Information Reconciliation (Syndrome Reconciliation with BCH Codes).
  5. *Proposal*: Implement Privacy Amplification (SHA-256 compression).
  6. *Proposal*: Transition to physical channel probing with real wireless hardware when available.
