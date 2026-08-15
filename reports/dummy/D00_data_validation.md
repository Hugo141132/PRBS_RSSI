# D00 — Dummy RSSI Data Validation Report

## Status
- **Status:** COMPLETED (PASS)
- **Date:** 2026-08-15
- **Task:** D00 — Dummy RSSI Data Validation

## Objective
The objective of D00 is to establish the minimum directory structure, preserve the original dataset `Dummy RSSI.xlsx` byte-for-byte, implement reusable loading and validation modules in Python, and perform rigorous data quality validation strictly on `Sheet1` without applying any cleaning, interpolation, Pearson correlation, or modification to the underlying data.

## Input
- **Dataset File:** `data/dummy/00_input/Dummy RSSI.xlsx`
- **SHA-256 Checksum (Before & After):** `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d`
- **Methodological Reference:** `PPA.pdf`
- **Workbook Sheets Present:** `Sheet1`, `Sheet2`, `Sheet3`
- **Dataset Selected for Pipeline:** **`Sheet1` only** (Sheets `Sheet2` and `Sheet3` are explicitly marked out of scope and intentionally unused).

---

## Dataset Structure (Sheet1)

- **Selected Worksheet:** `Sheet1`
- **Shape:** 500 rows × 8 columns
- **Column Classification:**
  - **RSSI Measurement Channels (Integer RSSI in dBm):**
    - `Alice` (int64): RSSI values recorded by Alice from Bob.
    - `Bob` (int64): RSSI values recorded by Bob from Alice.
    - `Eve1-Alice` (int64): RSSI values recorded by Eve1 from Alice.
    - `Eve1-Bob` (int64): RSSI values recorded by Eve1 from Bob.
  - **Excluded Helper & Precomputed Columns:**
    - `Unnamed: 4` (float64): Blank separator column (500 null entries).
    - `korelasi A-B` (float64): Precomputed correlation summary (value `0.632263` at index 0, 499 null entries).
    - `Korelasi A-E1` (float64): Precomputed correlation summary (value `0.017060` at index 0, 499 null entries).
    - `Korelasi B-E1` (float64): Precomputed correlation summary (value `0.119310` at index 0, 499 null entries).

---

## Validation Results

### RSSI Channel Quality Metrics
| Column | Data Type | Sample Count | Missing | Non-Numeric | Min (dBm) | Max (dBm) | Mean (dBm) | Std Dev (dBm) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Alice** | `int64` | 500 | 0 | 0 | -81.0 | -73.0 | -75.9700 | 1.0389 |
| **Bob** | `int64` | 500 | 0 | 0 | -81.0 | -73.0 | -75.8700 | 1.0253 |
| **Eve1-Alice** | `int64` | 500 | 0 | 0 | -34.0 | -30.0 | -31.7820 | 0.8741 |
| **Eve1-Bob** | `int64` | 500 | 0 | 0 | -97.0 | -78.0 | -84.2360 | 3.1674 |

- **Duplicate Rows (across 4 RSSI channels):** 262 duplicate row patterns exist due to discrete integer quantization of RSSI values across 500 samples.

### Node and Channel Identification
- **Legitimate Nodes:** `Alice` and `Bob` (synchronized reciprocal link).
- **Eavesdropper Channels:** `Eve1-Alice` and `Eve1-Bob` (synchronized eavesdropping link).

---

## Files Created / Modified
- `.gitignore`: Standard Python repository exclusion rules.
- `requirements.txt`: Specified Python dependencies (`pandas`, `openpyxl`).
- `data/dummy/00_input/Dummy RSSI.xlsx`: Organized input dataset, byte-for-byte preserved.
- `src/data_io/__init__.py`: Package initialization.
- `src/data_io/loader.py`: Reusable data loader and column classification functions.
- `src/data_io/validator.py`: Comprehensive dataset validation script focusing on `Sheet1`.
- `results/dummy/validation_results.json`: Machine-readable JSON output of all validation metrics.
- `reports/dummy/D00_data_validation.md`: This comprehensive validation report.
- `reports/progress.md`: Project milestone tracker.

---

## Commands Used
- `python src/data_io/validator.py` (Validation execution and JSON generation)

---

## Verification Performed
- Computed SHA-256 before and after file organization: both matched `abbe9973cbd95d0d9a248e12c6fb04eaf736bbc515d7f83764e33cd303270e4d`.
- Verified non-existence of null values or non-numeric entries in the 4 primary RSSI channels.
- Verified machine-readable JSON schema generation in `results/dummy/validation_results.json`.

---

## Problems or Ambiguities & Exclusions
1. **Precalculated Summary Columns:** `Sheet1` columns `korelasi A-B`, `Korelasi A-E1`, and `Korelasi B-E1` contain pre-existing single-row correlation numbers and 499 NaNs; these are excluded from the measurement pipeline.
2. **Empty Separator Column:** `Sheet1` column `Unnamed: 4` contains 500 NaNs and is excluded.
3. **Unused Sheets:** `Sheet2` and `Sheet3` exist in the workbook but are marked out of scope and intentionally unused.

---

## Methodological Decisions
- Only `Sheet1` is used as the dataset for the dummy RSSI pipeline.
- Column classification explicitly isolates measurement channels (`Alice`, `Bob`, `Eve1-Alice`, `Eve1-Bob`) from helper/summary columns.
- The raw dataset `Dummy RSSI.xlsx` is preserved byte-for-byte without automatic cleaning or modification.

---

## Conclusion
The dummy dataset `Dummy RSSI.xlsx` (`Sheet1`) has been successfully organized and validated. Reusable data loading and validation modules are established in `src/data_io/`. Data integrity is verified with byte-for-byte hash preservation.

## Recommended Next Task
- **D01 — Pearson Correlation Analysis** on `Alice`, `Bob`, `Eve1-Alice`, and `Eve1-Bob` channels from `Sheet1`.
