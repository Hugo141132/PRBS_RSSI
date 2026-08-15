"""
Analysis package for Physical Layer Secret Key Generation pipeline.
"""

from .correlation import (
    compute_pearson_correlation,
    analyze_channel_correlations,
    run_d01_dummy_analysis,
)
from .visualization import (
    plot_correlation_scatter,
    plot_pearson_comparison,
    generate_d01_figures,
)

__all__ = [
    "compute_pearson_correlation",
    "analyze_channel_correlations",
    "run_d01_dummy_analysis",
    "plot_correlation_scatter",
    "plot_pearson_comparison",
    "generate_d01_figures",
]
