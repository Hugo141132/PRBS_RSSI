# D01 — Pearson Correlation Analysis Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-08-15
- **Task:** D01 — Pearson Correlation Analysis (Dummy RSSI)

---

## 1. Objective and Scope
The objective of milestone **D01** is to compute the Pearson cross-correlation coefficient ($r$) and valid paired sample count ($n$) across legitimate and eavesdropper channels on `Sheet1` of `Dummy RSSI.xlsx`. This analysis establishes baseline physical-layer channel reciprocity between legitimate communicating nodes (Alice and Bob) and spatial decorrelation with respect to the eavesdropper (Eve1) prior to any digital filtering or quantization.

### Scope Boundaries
- **In Scope:** Pairwise Pearson correlation calculation ($r$) and sample verification ($n = 500$) across three specified channel pairs (`Alice vs Bob`, `Alice vs Eve1-Alice`, `Bob vs Eve1-Bob`), reproducible visualization generation, and automated mathematical verification.
- **Out of Scope:** Filtering (D02 Adaptive Kalman Filter), Quantization (D03 Modified ADQ), Information Reconciliation (D04 BCH), Bit Expansion (D05 PRBS/Galois LFSR), Privacy Amplification (D06 SHA-256), and Cryptographic Testing (D07/D08).

---

## 2. Input Dataset & Strict Raw-Only Data Rule

### Dataset Specifications
- **File Location:** `data/dummy/00_input/Dummy RSSI.xlsx`
- **Worksheet Selected:** `Sheet1` only ($500$ rows)
- **Approved Raw RSSI Channels:**
  1. `Alice` (Integer RSSI in dBm recorded by Alice from Bob)
  2. `Bob` (Integer RSSI in dBm recorded by Bob from Alice)
  3. `Eve1-Alice` (Integer RSSI in dBm recorded by Eve1 from Alice)
  4. `Eve1-Bob` (Integer RSSI in dBm recorded by Eve1 from Bob)

### Excluded Columns and Sheets
- **Helper & Precomputed Columns Excluded:**
  - `Unnamed: 4` (Empty separator column)
  - `korelasi A-B`, `Korelasi A-E1`, `Korelasi B-E1` (Single-cell precomputed correlation values)
- **Unused Worksheets:** `Sheet2` and `Sheet3` exist in the original workbook but are strictly out of scope and never accessed.
- **Column-Restricted Loading:** All dataset ingestion strictly enforces `usecols=['Alice', 'Bob', 'Eve1-Alice', 'Eve1-Bob']` via `src.data_io.loader.load_sheet()`. Excluded columns and non-measurement data are never read into memory during the D01 analysis pipeline.

---

## 3. Mathematical Formulation and Calculation Method

### Pearson Correlation Coefficient Formula
For two paired random variables $X$ and $Y$ with $n$ discrete observations $(x_1, y_1), (x_2, y_2), \dots, (x_n, y_n)$:

$$r = \frac{\sum_{i=1}^{n} (x_i - \bar{x})(y_i - \bar{y})}{\sqrt{\sum_{i=1}^{n} (x_i - \bar{x})^2} \cdot \sqrt{\sum_{i=1}^{n} (y_i - \bar{y})^2}} = \frac{\operatorname{Cov}(X, Y)}{\sigma_X \sigma_Y}$$

Where:
- $\bar{x} = \frac{1}{n} \sum_{i=1}^n x_i$ and $\bar{y} = \frac{1}{n} \sum_{i=1}^n y_i$ are the sample means.
- $\sigma_X = \sqrt{\frac{1}{n-1} \sum_{i=1}^n (x_i - \bar{x})^2}$ and $\sigma_Y = \sqrt{\frac{1}{n-1} \sum_{i=1}^n (y_i - \bar{y})^2}$ are the sample standard deviations.

### Computation Implementation
- Primary calculation uses `scipy.stats.pearsonr(x, y)` to extract statistic $r$.
- Pairwise valid filtering ensures only finite, non-null numerical pairs are processed.
- Precomputed workbook correlation cells are completely ignored and never used as inputs or expected targets.

---

## 4. Correlation Results Summary

All computations were executed directly on the raw RSSI measurements over $n = 500$ paired observations per channel pair.

| Channel Pair | Channel Classification | Pearson $r$ | Sample Count ($n$) | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **Alice vs Bob** | Legitimate Reciprocal Link | **0.632263** | **500** | PASS |
| **Alice vs Eve1-Alice** | Eavesdropper Cross-Link | **0.017060** | **500** | PASS |
| **Bob vs Eve1-Bob** | Eavesdropper Cross-Link | **0.119310** | **500** | PASS |

---

## 5. Independent Raw-Formula Verification

To ensure absolute mathematical integrity and eliminate reliance on third-party black-box routines or workbook artifacts:
1. An independent manual calculation of Pearson $r$ was implemented directly from the fundamental algebraic covariance/variance formula using NumPy array primitives.
2. In automated testing (`tests/test_d01_correlation.py`), the manual formula results were compared against `scipy.stats.pearsonr` outputs.
3. The comparison verified exact numerical agreement ($|r_{\text{manual}} - r_{\text{scipy}}| < 10^{-10}$) across all three channel pairs with exact sample size $n = 500$.

---

## 6. Physical Layer Security & Correlation Interpretation

1. **Legitimate Channel Reciprocity (Alice vs Bob):**
   - The Pearson correlation coefficient $r \approx 0.6323$ demonstrates a moderate positive correlation between the reciprocal RSSI measurements of Alice and Bob.
   - This legitimate-channel correlation is substantially higher than the correlations observed on either eavesdropper channel, establishing a baseline level of channel reciprocity between Alice and Bob before filtering or quantization.

2. **Eavesdropper Channels & Expected Spatial Decorrelation (Eve1 Links):**
   - The cross-correlations between legitimate nodes and the eavesdropper remain low in magnitude:
     - **Alice vs Eve1-Alice:** $r \approx 0.0171$, indicating negligible linear association.
     - **Bob vs Eve1-Bob:** $r \approx 0.1193$, indicating a weak linear correlation.
   - These low correlation magnitudes are consistent with the expected spatial-decorrelation behavior of wireless multipath fading.

3. **Methodological Note on Thresholds:**
   - In accordance with rigorous scientific reporting, no arbitrary pass/fail correlation thresholds (e.g. $r > 0.6$) are imposed as absolute security claims. The physical layer security evaluation is based on the relative contrast between legitimate reciprocity ($r \approx 0.6323$) and eavesdropper decorrelation ($r \le 0.1193$).

---

## 7. Correlation Visualizations

The following figures were generated strictly from the raw measurement channels using the column-restricted loading pipeline:

1. **Three-Panel Raw RSSI Scatter Plots:**
   - Visualizes pairwise raw integer RSSI distributions without artificial jitter or modification. Point transparency ($\alpha = 0.35$) illustrates point density resulting from discrete integer quantization. Labeled axes in `RSSI (dBm)` with annotated $r$ and $n$.
   - Figure File: [`results/dummy/figures/d01/d01_rssi_correlation_scatter.png`](../../results/dummy/figures/d01/d01_rssi_correlation_scatter.png)

2. **Pearson $r$ Magnitude Comparison Bar Chart:**
   - Displays comparative correlation coefficients across the three pairs on a fixed $[-1.0, 1.0]$ correlation scale with zero-reference baseline and value annotations.
   - Figure File: [`results/dummy/figures/d01/d01_pearson_r_comparison.png`](../../results/dummy/figures/d01/d01_pearson_r_comparison.png)

---

## 8. Deliverables & Files Created / Modified

- **`requirements.txt`**: Added `scipy>=1.10.0` and `matplotlib>=3.7.0`.
- **`src/data_io/loader.py`**: Enhanced `load_sheet()` and `load_all_sheets()` with backward-compatible `usecols` parameter for column-restricted loading.
- **`src/analysis/__init__.py`**: Analysis package initializer exposing correlation and visualization modules.
- **`src/analysis/correlation.py`**: Reusable Pearson correlation module enforcing `usecols` raw-only column loading and automated pipeline execution.
- **`src/analysis/visualization.py`**: Reusable visualization module generating multi-panel scatter plots and fixed-scale comparison charts.
- **`results/dummy/d01_pearson_correlation.json`**: Machine-readable JSON output storing channel pair metadata, Pearson $r$, sample count $n$, and figure paths.
- **`results/dummy/figures/d01/d01_rssi_correlation_scatter.png`**: 3-panel scatter visualization of channel pairs with $r$ and $n$ annotations.
- **`results/dummy/figures/d01/d01_pearson_r_comparison.png`**: Bar chart comparing Pearson $r$ across channel pairs on fixed $[-1.0, 1.0]$ scale.
- **`tests/test_d01_correlation.py`**: Automated verification suite covering raw-only column isolation, independent formula checks, schema validation, relative magnitude regression checks, and figure verification.
- **`reports/dummy/D01_pearson_correlation.md`**: This comprehensive D01 milestone report.
- **`reports/progress.md`**: Milestone progress tracker updated to COMPLETED.

---

## 9. Verification Commands & Results

| Verification Step | Command / Test | Status | Result Summary |
| :--- | :--- | :--- | :--- |
| **D01 Analysis Execution** | `python src/analysis/correlation.py` | **PASS** | Generated `d01_pearson_correlation.json` and figures |
| **D01 Automated Test Suite** | `python tests/test_d01_correlation.py` | **PASS** | 5/5 automated unit/integration tests passed |
| **Raw Column Isolation** | `test_raw_columns_only_loaded` | **PASS** | Only 4 approved columns loaded; helper columns excluded |
| **Independent Formula Match** | `test_independent_pearson_calculation` | **PASS** | Manual formula matches SciPy ($|r_{\text{diff}}| < 10^{-10}$) |
| **JSON Schema & Values** | `test_json_results_schema_and_values` | **PASS** | Clean schema, finite $r$, $n=500$, no extraneous fields |
| **Regression Sanity Check** | `test_dataset_regression_sanity_check` | **PASS** | Relative ordering verified ($r_{AB} > r_{AE1}, r_{BE1}$) |
| **Figure Verification** | `test_figures_generated_and_non_empty` | **PASS** | Both PNG figure files exist and are non-empty |
| **D00 Regression Check** | `python src/data_io/validator.py` | **PASS** | D00 dataset structure and integrity intact |
| **Scope Boundary Check** | Codebase Inspection | **PASS** | No downstream milestone functionality implemented |

---

## 10. Methodological Decisions, Assumptions & Exclusions

1. **Strict Raw-Only Column Loading:** Excel access enforces `usecols=['Alice', 'Bob', 'Eve1-Alice', 'Eve1-Bob']`. Helper columns (`Unnamed: 4`, `korelasi A-B`, `Korelasi A-E1`, `Korelasi B-E1`) and unused sheets (`Sheet2`, `Sheet3`) are never accessed or referenced.
2. **Data Immutability:** The input Excel dataset `Dummy RSSI.xlsx` is treated as strictly read-only and preserved byte-for-byte.
3. **Reusability:** Functions in `src/analysis/correlation.py` and `src/analysis/visualization.py` accept generic Pandas DataFrames, Series, and NumPy arrays, allowing direct reuse for the subsequent raw ESP32/LoRa RSSI experimental pipeline.
4. **Scope Isolation:** No Kalman filtering, quantization, PRBS expansion, BCH reconciliation, SHA-256 privacy amplification, or NIST randomness testing was implemented in D01.

---

## 11. Conclusion & Recommended Next Task

Milestone **D01 — Pearson Correlation Analysis** has been successfully executed, mathematically verified, documented, and visualized. Baseline legitimate channel reciprocity ($r \approx 0.6323$) is substantially higher than both eavesdropper cross-correlations ($r \le 0.1193$), confirming the suitability of the dataset for subsequent SKG preprocessing.

- **Completed Milestone:** **D01 — Pearson Correlation Analysis**
- **Recommended Next Task:** **D02 — Adaptive Kalman Filter (AKF)** with Adaptive Fuzzy Clustering for RSSI noise reduction and reciprocity enhancement.
