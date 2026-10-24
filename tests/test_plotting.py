"""Tests for correlation plotting and figure generation."""

from pathlib import Path
import pytest

from rssi_skg.cli import run_correlation_analysis
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import aggregate_coordinate_counts, plot_combined_correlation_figure


def test_aggregate_coordinate_counts() -> None:
    x = [1.0, 2.0, 1.0, 1.0, 2.0]
    y = [10.0, 20.0, 10.0, 10.0, 25.0]

    ux, uy, counts = aggregate_coordinate_counts(x, y)

    # 3 unique coordinate pairs: (1.0, 10.0), (2.0, 20.0), (2.0, 25.0)
    assert len(ux) == 3
    assert len(uy) == 3
    assert len(counts) == 3
    assert sum(counts) == len(x)

    # Find count for (1.0, 10.0)
    idx_1_10 = [(i, c) for i, (px, py, c) in enumerate(zip(ux, uy, counts)) if px == 1.0 and py == 10.0]
    assert len(idx_1_10) == 1
    assert idx_1_10[0][1] == 3

    # Find count for (2.0, 20.0)
    idx_2_20 = [(i, c) for i, (px, py, c) in enumerate(zip(ux, uy, counts)) if px == 2.0 and py == 20.0]
    assert len(idx_2_20) == 1
    assert idx_2_20[0][1] == 1


def test_aggregate_coordinate_counts_length_mismatch() -> None:
    with pytest.raises(ValueError, match="must have identical length"):
        aggregate_coordinate_counts([1.0, 2.0], [10.0])


def test_figure_creation(tmp_path: Path) -> None:
    dummy_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    assert dummy_path.is_file()

    data = load_rssi_workbook(dummy_path)
    results = [
        {"pair": "Alice–Bob", "sample_count": 500, "correlation_coefficient": 0.63226, "data_kind": "dummy"},
        {"pair": "Alice–Eve1-Alice", "sample_count": 500, "correlation_coefficient": 0.01706, "data_kind": "dummy"},
        {"pair": "Bob–Eve1-Bob", "sample_count": 500, "correlation_coefficient": 0.11931, "data_kind": "dummy"},
    ]

    prefix = tmp_path / "test_fig"
    png_p, pdf_p = plot_combined_correlation_figure(data, results, prefix)

    assert png_p.is_file()
    assert pdf_p.is_file()
    assert png_p.stat().st_size > 1000
    assert pdf_p.stat().st_size > 1000
    assert png_p.suffix == ".png"
    assert pdf_p.suffix == ".pdf"


def test_cli_figure_export_with_temporary_paths(tmp_path: Path) -> None:
    dummy_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    csv_out = tmp_path / "out.csv"
    fig_prefix = tmp_path / "corr_plot"

    results, fig_paths = run_correlation_analysis(
        input_path=dummy_path,
        output_path=csv_out,
        figure_prefix=fig_prefix,
    )

    assert len(results) == 3
    assert fig_paths is not None
    png_path, pdf_path = fig_paths
    assert csv_out.is_file()
    assert png_path.is_file()
    assert pdf_path.is_file()
    assert png_path.name == "corr_plot.png"
    assert pdf_path.name == "corr_plot.pdf"


def test_cli_csv_only_without_figure_prefix(tmp_path: Path) -> None:
    dummy_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    csv_out = tmp_path / "out_only.csv"

    results, fig_paths = run_correlation_analysis(
        input_path=dummy_path,
        output_path=csv_out,
        figure_prefix=None,
    )

    assert len(results) == 3
    assert fig_paths is None
    assert csv_out.is_file()


def test_plot_filtering_comparison_figure(tmp_path: Path) -> None:
    from rssi_skg.plotting import plot_filtering_comparison_figure

    raw_data = {
        "Alice": [-80.0, -80.0, -79.0, -76.0],
        "Bob": [-79.0, -80.0, -79.0, -76.0],
        "Eve1-Alice": [-31.0, -33.0, -32.0, -33.0],
        "Eve1-Bob": [-83.0, -81.0, -78.0, -83.0],
    }
    filtered_data = {
        "Alice": [-80.0, -80.0, -79.6, -79.2],
        "Bob": [-79.0, -79.3, -79.1, -78.8],
        "Eve1-Alice": [-31.0, -31.5, -31.5, -31.8],
        "Eve1-Bob": [-83.0, -82.4, -81.7, -81.7],
    }
    results = [
        {"pair": "Alice–Bob", "raw_correlation": 0.63, "filtered_correlation": 0.84, "correlation_delta": 0.21},
        {"pair": "Alice–Eve1-Alice", "raw_correlation": 0.01, "filtered_correlation": -0.01, "correlation_delta": -0.02},
        {"pair": "Bob–Eve1-Bob", "raw_correlation": 0.11, "filtered_correlation": 0.01, "correlation_delta": -0.10},
    ]

    prefix = tmp_path / "test_comparison_fig"
    png_p, pdf_p = plot_filtering_comparison_figure(raw_data, filtered_data, results, prefix)

    assert png_p.is_file()
    assert pdf_p.is_file()
    assert png_p.stat().st_size > 1000
    assert pdf_p.stat().st_size > 1000
