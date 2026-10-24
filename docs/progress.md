# Project Progress & Handoff: RSSI-based Secret Key Generation (SKG)

## 1. Project Purpose & Methodological Reference
This research project develops a physical-layer Secret Key Generation (SKG) pipeline based on Received Signal Strength Indicator (RSSI) measurements. The current milestone implements zero-lag Pearson correlation analysis as defined in **`PA.pdf`, Equation (3.62), page 34**:

$$\rho_{X, Y} = \frac{\sum_{i=1}^{n} (X_i - \bar{X})(Y_i - \bar{Y})}{\sqrt{\sum_{i=1}^{n} (X_i - \bar{X})^2} \sqrt{\sum_{i=1}^{n} (Y_i - \bar{Y})^2}}$$

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

## 3. Implemented Modules & Correlation Results
- **Workbook Loader (`src/rssi_skg/loader.py`)**: Uses `openpyxl` to read raw workbooks; validates presence of all 4 required headers; enforces numeric cell types; reports exact row and column upon encountering missing/invalid values; supports arbitrary sample sizes $N \ge 2$.
- **Correlation Calculation (`src/rssi_skg/correlation.py`)**: Computes centered zero-lag Pearson correlation $\rho$ in `float64` precision; validates equal lengths; rejects $N < 2$, NaN, and Inf; raises explicit `ValueError` on constant sequences (zero variance).
- **Plotting & Visualization (`src/rssi_skg/plotting.py`)**: Aggregates identical $(x, y)$ coordinate pairs into frequency counts; generates a unified 2-row figure:
  - Top row: Horizontal bar chart spanning fixed range $[-1.0, +1.0]$, zero reference line, and 4-decimal place coefficient annotations.
  - Bottom row: Three scatter panels (`Alice vs Bob`, `Alice vs Eve1-Alice`, `Bob vs Eve1-Bob`) with marker area proportional to count, readable count legends, generic "RSSI" axis titles, and explicit disclaimer stating results support software validation only.
  - Exports: 300 dpi PNG and vector PDF using Matplotlib `Agg` backend.
- **CLI Interface (`src/rssi_skg/cli.py`)**: Accessible via `python -m rssi_skg` or console script `rssi-skg`. Supports `-i/--input`, `-o/--output`, `--figure-prefix`, and `--data-kind`.
- **Validated Correlation Results ($N=500$, `data_kind=dummy`)**:
  - `Alice–Bob`: $\rho = +0.6322625214$ (display label: `+0.6323`)
  - `Alice–Eve1-Alice`: $\rho = +0.0170595821$ (display label: `+0.0171`)
  - `Bob–Eve1-Bob`: $\rho = +0.1193098371$ (display label: `+0.1193`)
  - Saved outputs: `outputs/dummy_rssi_correlation.csv`, `.png`, and `.pdf`.

## 4. Key Source & Test File Responsibilities
- `src/rssi_skg/correlation.py`: Pure mathematical Pearson implementation and input sanity checking.
- `src/rssi_skg/loader.py`: Excel workbook ingestion, column validation, and row pairing.
- `src/rssi_skg/plotting.py`: Discrete coordinate aggregation and Matplotlib combined figure rendering.
- `src/rssi_skg/cli.py`: Command-line parsing, output directory preparation, CSV export, and figure export dispatch.
- `tests/test_correlation.py`: 8 tests (perfect positive/negative, zero correlation, zero variance, invalid dimensions, NaN/Inf, SciPy reference parity).
- `tests/test_loader.py`: 6 tests (missing columns, non-numeric values, empty cells, row ordering preservation, arbitrary $N$).
- `tests/test_plotting.py`: 5 tests (duplicate point aggregation math, dimension checks, figure generation, headless export, CSV-only execution).

## 5. Verification Records
*(Recorded from prior execution steps; no re-execution performed solely for this document)*:
- **Clean Environment**: Project installed in isolated local `.venv` via `pip install -e ".[dev]"`.
- **Test Suite**: All 19 tests passed successfully (`pytest -v`).
- **CLI Execution**: Executed against the dummy workbook; verified 500-sample count, full float precision in CSV, and simultaneous PNG/PDF generation.
- **Visual Inspection**: Inspected `outputs/dummy_rssi_correlation.png` using IDE file viewer; confirmed readable title/disclaimer spacing, non-overlapping labels, correct $[-1, +1]$ bar bounds, bubble marker scaling, and legible count legends.

## 6. Windows PowerShell Reproduction Commands
> The primary execution guide with output locations is maintained in [README.md](../README.md#petunjuk-penyiapan-lingkungan--eksekusi).

```powershell
# 1. Install dependencies in editable mode
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. Run automated test suite (19 tests)
.\.venv\Scripts\python.exe -m pytest -v

# 3. Run correlation analysis (CSV only)
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv"

# 4. Run correlation analysis (CSV + combined PNG/PDF figure)
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"
```

## 7. Current Git State
- **Active Branch**: `main`.
- **Commit Status**: All current changes are **uncommitted** in the working tree.
- **Unrelated Modification**: `data/dummy/00_input/Dummy RSSI (data Indoor).xlsx` is recorded as deleted (`D`) in Git status from prior user actions and must be left untouched.

## 8. Remaining Limitations & Proposed Next Steps
- **Limitations**: Analysis operates on synthetic indoor dummy data for software verification; cannot establish empirical secrecy; channel probing hardware is deferred.
- **Proposed Future Steps**:
  1. *Proposal*: Implement Kalman Filtering / MSHKF pre-processing stage to reduce measurement noise.
  2. *Proposal*: Implement Adaptive Dual-Threshold Quantization (ADTQ) stage for binary key extraction.
  3. *Proposal*: Implement Information Reconciliation (Galois LFSR expansion / Privacy Amplification).
  4. *Proposal*: Transition to physical channel probing with real wireless hardware when available.

## 9. Files to Share
- **Progress & Context**: `docs/progress.md`, `README.md`, `docs/methodology.md`.
- **Visual & Numeric Outputs**: `outputs/dummy_rssi_correlation.png`, `outputs/dummy_rssi_correlation.csv`.
- **Source Code & Tests**: `pyproject.toml`, `src/rssi_skg/`, and `tests/`.

## 10. Working Preferences
- Agent explanations delivered in Indonesian with technical terms retained in English.
- Prompts written in English; relevant MCP tools (especially filesystem) used first; prompts kept concise.
- User retains sole authority for `git add`, `git commit`, and `git push` on `main`; agent never creates branches or commits.
- Inspect `.gitignore` before changes; modify only when strictly necessary.
