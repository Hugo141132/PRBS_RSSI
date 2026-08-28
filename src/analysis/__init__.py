"""
Analysis package for Physical Layer Secret Key Generation pipeline.
"""

from .correlation import (
    analyze_channel_correlations,
    compute_pearson_correlation,
    run_d01_dummy_analysis,
)
from .mshkf import FuzzyClusteringEngine, ModifiedSageHusaKalmanFilter
from .visualization import (
    generate_d01_figures,
    generate_d02_figures,
    plot_correlation_scatter,
    plot_pearson_comparison,
)

__all__ = [
    "compute_pearson_correlation",
    "analyze_channel_correlations",
    "run_d01_dummy_analysis",
    "plot_correlation_scatter",
    "plot_pearson_comparison",
    "generate_d01_figures",
    "generate_d02_figures",
    "ModifiedSageHusaKalmanFilter",
    "FuzzyClusteringEngine",
]
