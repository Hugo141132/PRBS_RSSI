"""RSSI-based Secret Key Generation (SKG) package.

Scaffolding for RSSI correlation and secret key extraction research.
"""

__version__ = "0.1.0"

from rssi_skg.correlation import pearson_correlation
from rssi_skg.filter import FilterConfig, ModifiedSageHusaFilter, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import (
    aggregate_coordinate_counts,
    plot_combined_correlation_figure,
    plot_filtering_comparison_figure,
    plot_kar_comparison_figure,
)
from rssi_skg.quantization import (
    CODE_4BIT_MAP,
    EXCEL_MAX_CELL_CHARS,
    GRAY_2BIT_MAP,
    ChannelQuantizationResult,
    QuantizationConfig,
    SegmentThresholds,
    calculate_kar,
    calculate_level_agreement,
    calculate_level_frequencies,
    encode_levels_to_bits,
    export_quantized_workbook_xlsx,
    quantize_channels,
    quantize_series,
)

__all__ = [
    "pearson_correlation",
    "FilterConfig",
    "ModifiedSageHusaFilter",
    "filter_rssi_channels",
    "load_rssi_workbook",
    "aggregate_coordinate_counts",
    "plot_combined_correlation_figure",
    "plot_filtering_comparison_figure",
    "plot_kar_comparison_figure",
    "QuantizationConfig",
    "SegmentThresholds",
    "ChannelQuantizationResult",
    "GRAY_2BIT_MAP",
    "CODE_4BIT_MAP",
    "EXCEL_MAX_CELL_CHARS",
    "quantize_series",
    "quantize_channels",
    "encode_levels_to_bits",
    "calculate_kar",
    "calculate_level_agreement",
    "calculate_level_frequencies",
    "export_quantized_workbook_xlsx",
]
