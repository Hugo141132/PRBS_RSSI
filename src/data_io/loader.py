"""
loader.py

Reusable functions for inspecting and loading raw RSSI Excel workbooks
without altering the original dataset or applying any in-place modifications.
"""

import hashlib
import os
from typing import Any, Dict, List, Optional, Union
import pandas as pd


def compute_file_sha256(file_path: str) -> str:
    """Compute the SHA-256 hash of a file byte-for-byte."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_workbook_info(file_path: str) -> Dict[str, Union[str, List[str]]]:
    """Retrieve sheet names and basic file info from an Excel workbook."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    excel_file = pd.ExcelFile(file_path)
    return {
        "file_path": file_path,
        "sheet_names": excel_file.sheet_names,
    }


def load_sheet(
    file_path: str,
    sheet_name: Union[str, int] = 0,
    header: Optional[Union[int, List[int]]] = 0,
    usecols: Optional[Union[List[str], List[int], str, Any]] = None,
) -> pd.DataFrame:
    """Load a specific worksheet as a pandas DataFrame without modifying data."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    return pd.read_excel(file_path, sheet_name=sheet_name, header=header, usecols=usecols)


def load_all_sheets(
    file_path: str,
    header: Optional[Union[int, List[int]]] = 0,
    usecols: Optional[Union[List[str], List[int], str, Any]] = None,
) -> Dict[str, pd.DataFrame]:
    """Load all worksheets in an Excel workbook into a dictionary of DataFrames."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    return pd.read_excel(file_path, sheet_name=None, header=header, usecols=usecols)


def classify_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Classify DataFrame columns into RSSI measurements vs precomputed/helper columns.
    
    Returns:
        Dict with keys:
            - 'rssi_measurement_cols': columns containing raw node RSSI measurements
            - 'helper_or_precomputed_cols': precomputed metrics (e.g. correlations) or blank columns
            - 'unknown_cols': any unclassified columns
    """
    rssi_cols = []
    helper_cols = []
    unknown_cols = []

    for col in df.columns:
        col_str = str(col).strip()
        lower_col = col_str.lower()
        if lower_col in ["alice", "bob"] or lower_col.startswith("eve"):
            rssi_cols.append(col_str)
        elif "korelasi" in lower_col or "correlation" in lower_col or "unnamed" in lower_col:
            helper_cols.append(col_str)
        else:
            unknown_cols.append(col_str)

    return {
        "rssi_measurement_cols": rssi_cols,
        "helper_or_precomputed_cols": helper_cols,
        "unknown_cols": unknown_cols,
    }
