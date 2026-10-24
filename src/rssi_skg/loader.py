"""Workbook data loader module for RSSI datasets.

Loads and validates tabular RSSI data from Excel workbooks with strict integrity checks:
- Verifies existence of required columns.
- Preserves exact row-wise observation pairing and order.
- Rejects missing, blank, non-numeric, or non-finite values with explicit row/column errors.
- Never silently drops, sorts, interpolates, or fabricates samples.
- Does not hardcode sample count constraints (requires at least 2 observations).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import openpyxl

DEFAULT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "Alice",
    "Bob",
    "Eve1-Alice",
    "Eve1-Bob",
)


def load_rssi_workbook(
    file_path: str | Path,
    required_columns: Sequence[str] = DEFAULT_REQUIRED_COLUMNS,
) -> dict[str, list[float]]:
    """Load and validate RSSI observations from an Excel workbook (.xlsx).

    Args:
        file_path: Path to the .xlsx workbook.
        required_columns: Sequence of column names that must exist in the header.

    Returns:
        dict[str, list[float]]: Dictionary mapping column names to lists of float64 RSSI values,
            preserving exact row order.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If required columns are missing, data rows are fewer than 2,
            or any cell in the required columns contains missing, non-numeric,
            or non-finite values.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Workbook file not found at: {path}")

    wb = openpyxl.load_workbook(filename=path, data_only=True, read_only=True)
    try:
        sheet = wb.active
        if sheet is None:
            raise ValueError(f"Workbook at {path} contains no active worksheet.")

        row_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(row_iter)
        except StopIteration as err:
            raise ValueError(f"Workbook at {path} is empty (no header row).") from err

        if not header_row:
            raise ValueError(f"Workbook at {path} has an empty header row.")

        # Map column names (stripped of leading/trailing whitespace if string) to column index
        col_indices: dict[str, int] = {}
        available_columns: list[str] = []
        for idx, col_val in enumerate(header_row):
            if col_val is not None:
                col_name = str(col_val).strip()
                col_indices[col_name] = idx
                available_columns.append(col_name)

        # Check required columns
        missing_columns = [col for col in required_columns if col not in col_indices]
        if missing_columns:
            raise ValueError(
                f"Missing required column(s) in workbook: {missing_columns}. "
                f"Available columns: {available_columns}."
            )

        # Prepare containers preserving column order
        data: dict[str, list[float]] = {col: [] for col in required_columns}

        row_num = 1  # Header is row 1
        for row_vals in row_iter:
            row_num += 1

            # Check if this row is completely empty across all workbook cells
            if all(v is None for v in row_vals):
                continue

            for col_name in required_columns:
                col_idx = col_indices[col_name]
                if col_idx >= len(row_vals):
                    val = None
                else:
                    val = row_vals[col_idx]

                if val is None or (isinstance(val, str) and not val.strip()):
                    raise ValueError(
                        f"Missing value encountered in column '{col_name}' at row {row_num}."
                    )

                try:
                    f_val = float(val)
                except (TypeError, ValueError) as err:
                    raise ValueError(
                        f"Invalid non-numeric value {val!r} encountered in column '{col_name}' at row {row_num}."
                    ) from err

                if not math.isfinite(f_val):
                    raise ValueError(
                        f"Non-finite value ({f_val}) encountered in column '{col_name}' at row {row_num}."
                    )

                data[col_name].append(f_val)

        # Validate minimum observations
        sample_counts = {col: len(vals) for col, vals in data.items()}
        first_count = next(iter(sample_counts.values())) if sample_counts else 0

        if first_count < 2:
            raise ValueError(
                f"At least two paired observations are required, found {first_count} data rows."
            )

        # Sanity check: ensure all loaded columns have equal lengths
        for col, count in sample_counts.items():
            if count != first_count:
                raise ValueError(
                    f"Inconsistent sample count across columns: '{col}' has {count} rows, expected {first_count}."
                )

        return data
    finally:
        wb.close()
