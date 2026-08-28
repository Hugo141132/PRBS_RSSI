"""
Analysis package for Physical Layer Secret Key Generation pipeline.
"""

from .correlation import (
    analyze_channel_correlations,
    compute_pearson_correlation,
    run_d01_dummy_analysis,
)
from .d02_2_calibration import (
    calibrate_channel_parameters,
    compute_rts_reference_state,
)
from .d02_2_runner import run_d02_2_pipeline
from .mshkf import FuzzyClusteringEngine, ModifiedSageHusaKalmanFilter
from .visualization import (
    generate_d01_figures,
    generate_d02_figures,
    generate_d02_2_figures,
    generate_d02_vs_d02_2_comparison_figures,
    plot_correlation_scatter,
    plot_d02_vs_d02_2_all_channels_overview,
    plot_d02_vs_d02_2_channel_comparison,
    plot_d02_vs_d02_2_pearson_comparison,
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
    "generate_d02_2_figures",
    "generate_d02_vs_d02_2_comparison_figures",
    "plot_d02_vs_d02_2_channel_comparison",
    "plot_d02_vs_d02_2_all_channels_overview",
    "plot_d02_vs_d02_2_pearson_comparison",
    "ModifiedSageHusaKalmanFilter",
    "FuzzyClusteringEngine",
    "compute_rts_reference_state",
    "calibrate_channel_parameters",
    "run_d02_2_pipeline",
]
