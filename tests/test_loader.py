"""Tests for workbook data loader and validation."""

from pathlib import Path
import openpyxl
import pytest
from scipy import stats

from rssi_skg.correlation import pearson_correlation
from rssi_skg.loader import DEFAULT_REQUIRED_COLUMNS, load_rssi_workbook


def _create_workbook(
    tmp_path: Path,
    filename: str,
    headers: list[str],
    rows: list[list[object]],
) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    file_path = tmp_path / filename
    wb.save(file_path)
    wb.close()
    return file_path


def test_missing_columns_raises_error(tmp_path: Path) -> None:
    # Only provides Alice, Bob, Eve1-Alice; missing Eve1-Bob
    file_path = _create_workbook(
        tmp_path,
        "missing_col.xlsx",
        headers=["Alice", "Bob", "Eve1-Alice"],
        rows=[[-50, -51, -70], [-52, -53, -71]],
    )

    with pytest.raises(ValueError, match="Missing required column.*Eve1-Bob"):
        load_rssi_workbook(file_path)


def test_invalid_non_numeric_value_identifies_row_and_column(tmp_path: Path) -> None:
    # Header is row 1, data starts at row 2. Row with invalid text is row 3.
    file_path = _create_workbook(
        tmp_path,
        "invalid_text.xlsx",
        headers=list(DEFAULT_REQUIRED_COLUMNS),
        rows=[
            [-50, -51, -70, -75],
            [-52, "INVALID_RSSI", -71, -74],
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        load_rssi_workbook(file_path)
    err_msg = str(exc_info.value)
    assert "Bob" in err_msg
    assert "row 3" in err_msg
    assert "INVALID_RSSI" in err_msg


def test_missing_blank_cell_identifies_row_and_column(tmp_path: Path) -> None:
    file_path = _create_workbook(
        tmp_path,
        "missing_cell.xlsx",
        headers=list(DEFAULT_REQUIRED_COLUMNS),
        rows=[
            [-50, -51, -70, -75],
            [-52, -53, None, -74],
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        load_rssi_workbook(file_path)
    err_msg = str(exc_info.value)
    assert "Eve1-Alice" in err_msg
    assert "row 3" in err_msg


def test_preservation_of_row_pairing(tmp_path: Path) -> None:
    # Verify exact row ordering is preserved across all columns without reordering
    expected_rows = [
        [-40.0, -41.0, -60.0, -61.0],
        [-50.0, -51.0, -70.0, -71.0],
        [-30.0, -31.0, -50.0, -51.0],
        [-45.0, -46.0, -65.0, -66.0],
    ]
    file_path = _create_workbook(
        tmp_path,
        "pairing_test.xlsx",
        headers=list(DEFAULT_REQUIRED_COLUMNS),
        rows=expected_rows,
    )

    data = load_rssi_workbook(file_path)
    for col_idx, col_name in enumerate(DEFAULT_REQUIRED_COLUMNS):
        actual_vals = data[col_name]
        expected_vals = [row[col_idx] for row in expected_rows]
        assert actual_vals == expected_vals


def test_arbitrary_observation_count_not_hardcoded_to_500(tmp_path: Path) -> None:
    # 5 observations (not 500) must load successfully without errors
    rows = [[float(i), float(i * 2), float(-i), float(-i * 2)] for i in range(5)]
    file_path = _create_workbook(
        tmp_path,
        "arbitrary_n.xlsx",
        headers=list(DEFAULT_REQUIRED_COLUMNS),
        rows=rows,
    )

    data = load_rssi_workbook(file_path)
    assert len(data["Alice"]) == 5


def test_dummy_dataset_integrity_and_correlation_verification() -> None:
    dummy_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    assert dummy_path.is_file(), f"Dummy dataset not found at {dummy_path}"

    data = load_rssi_workbook(dummy_path)

    # 1. Verify 500 samples across all columns
    for col in DEFAULT_REQUIRED_COLUMNS:
        assert len(data[col]) == 500, f"Expected 500 samples for {col}, got {len(data[col])}"

    # 2. Check calculations match scipy independent reference
    pairs = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]
    for col1, col2 in pairs:
        rho = pearson_correlation(data[col1], data[col2])
        ref_rho = stats.pearsonr(data[col1], data[col2]).statistic
        assert pytest.approx(ref_rho, rel=1e-12) == rho
