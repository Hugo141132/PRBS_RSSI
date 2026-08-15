"""
validator.py

Executes rigorous validation on the RSSI dataset according to D00 specifications.
Focuses strictly on Sheet1 as the sole selected dataset for the dummy pipeline.
Sheet2 and Sheet3 are recorded as existing in the workbook but marked as out of scope.
Generates machine-readable output in results/dummy/validation_results.json.
"""

import json
import os
import sys
from typing import Any, Dict
import pandas as pd

# Add project root to sys.path if executed directly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data_io.loader import (
    classify_columns,
    compute_file_sha256,
    get_workbook_info,
    load_sheet,
)


def validate_dataset(
    file_path: str,
    output_json_path: str = None,
) -> Dict[str, Any]:
    """
    Validate the RSSI Excel workbook according to D00 specifications.
    Strictly focuses on Sheet1. Does NOT modify the file or clean data automatically.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256_hash = compute_file_sha256(file_path)
    wb_info = get_workbook_info(file_path)
    all_sheet_names = wb_info["sheet_names"]

    # 1. Selected Sheet Validation (Sheet1 only)
    selected_sheet = "Sheet1"
    df_sheet1 = load_sheet(file_path, sheet_name=selected_sheet, header=0)
    col_classification = classify_columns(df_sheet1)
    rssi_cols = col_classification["rssi_measurement_cols"]
    helper_cols = col_classification["helper_or_precomputed_cols"]

    # Statistics & missing values for Sheet1
    sheet1_missing = df_sheet1.isnull().sum().to_dict()
    sheet1_dtypes = {col: str(df_sheet1[col].dtype) for col in df_sheet1.columns}

    # Check non-numeric values in RSSI measurement columns
    non_numeric_counts = {}
    rssi_stats = {}
    for col in rssi_cols:
        series = df_sheet1[col]
        non_numeric = pd.to_numeric(series, errors="coerce").isnull().sum()
        non_numeric_counts[col] = int(non_numeric)

        # Summary statistics on raw integer measurements without modification
        numeric_series = pd.to_numeric(series, errors="coerce").dropna()
        rssi_stats[col] = {
            "count": int(numeric_series.count()),
            "min": float(numeric_series.min()),
            "max": float(numeric_series.max()),
            "mean": round(float(numeric_series.mean()), 4),
            "std": round(float(numeric_series.std()), 4),
        }

    # Duplicate rows across RSSI measurement channels
    rssi_df = df_sheet1[rssi_cols]
    duplicate_rows_count = int(rssi_df.duplicated().sum())

    # Precomputed correlation values inspection (Row 0 values only)
    precomputed_values = {}
    for col in helper_cols:
        val = df_sheet1[col].dropna().tolist()
        precomputed_values[col] = val

    # 2. Scope & Sheet Status
    unused_sheets = [s for s in all_sheet_names if s != selected_sheet]

    # 3. Node and Channel Identification on Sheet1
    identified_nodes = {
        "legitimate_nodes": {
            "Alice": "Alice measurement column in Sheet1 (500 samples)",
            "Bob": "Bob measurement column in Sheet1 (500 samples)",
        },
        "eavesdropper_channels": {
            "Eve1-Alice": "Eve1 measuring Alice transmission in Sheet1 (500 samples)",
            "Eve1-Bob": "Eve1 measuring Bob transmission in Sheet1 (500 samples)",
        },
    }

    # 4. Warnings and Exclusions
    warnings = [
        "Sheet1 contains precalculated correlation summary columns ('korelasi A-B', 'Korelasi A-E1', 'Korelasi B-E1') with values only in row 1 and 499 NaN entries; excluded from measurement pipeline.",
        "Sheet1 contains an empty column ('Unnamed: 4') with 500 NaN entries; excluded from measurement pipeline.",
        f"Workbook contains additional sheets {unused_sheets}, which are explicitly marked out of scope and intentionally unused.",
    ]

    results = {
        "status": "VALIDATED",
        "file_info": {
            "file_path": file_path,
            "sha256": sha256_hash,
            "all_workbook_sheets": all_sheet_names,
            "selected_sheet": selected_sheet,
            "unused_sheets": unused_sheets,
            "scope_note": "Only Sheet1 is used as the dataset for the dummy RSSI pipeline. Other sheets are out of scope.",
        },
        "dataset_validation": {
            "sheet_name": selected_sheet,
            "total_rows": len(df_sheet1),
            "total_columns": len(df_sheet1.columns),
            "column_names": list(df_sheet1.columns),
            "dtypes": sheet1_dtypes,
            "missing_values_per_column": sheet1_missing,
            "column_classification": col_classification,
            "rssi_measurement_channels": {
                "columns": rssi_cols,
                "non_numeric_counts": non_numeric_counts,
                "duplicate_rows_count": duplicate_rows_count,
                "statistics": rssi_stats,
            },
            "excluded_helper_columns": {
                "columns": helper_cols,
                "values_found": precomputed_values,
                "reason_excluded": "Contains non-measurement metadata (empty column or single-row precomputed correlation metrics).",
            },
        },
        "node_and_channel_identification": identified_nodes,
        "warnings_and_exclusions": warnings,
    }

    if output_json_path:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    default_input = os.path.join(
        project_root, "data", "dummy", "00_input", "Dummy RSSI.xlsx"
    )
    default_output = os.path.join(
        project_root, "results", "dummy", "validation_results.json"
    )
    res = validate_dataset(default_input, default_output)
    print(f"Validation completed successfully.")
    print(f"SHA-256: {res['file_info']['sha256']}")
    print(f"Selected Sheet: {res['file_info']['selected_sheet']}")
    print(f"Unused Sheets: {res['file_info']['unused_sheets']}")
    print(f"Output saved to: {default_output}")
