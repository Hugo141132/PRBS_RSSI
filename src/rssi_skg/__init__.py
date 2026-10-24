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
]
