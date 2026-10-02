"""
Analysis package for Physical Layer Secret Key Generation pipeline.
"""

from .correlation import (
    analyze_channel_correlations,
    compute_pearson_correlation,
    run_d01_dummy_analysis,
)
from .mshkf import ModifiedSageHusaKalmanFilter
from .quantization import (
    ModifiedAdaptiveDualThresholdQuantizer,
    QuantizationResult,
    compute_bit_error_rate,
    compute_key_agreement_rate,
    compute_key_generation_rate,
)
from .visualization import (
    generate_d01_figures,
    generate_d02_figures,
    plot_correlation_scatter,
    plot_kar_comparison_bar,
    plot_pearson_comparison,
    plot_quantization_levels_distribution,
    plot_quantization_symbol_timeline,
    plot_quantization_thresholds_overlay,
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
    "ModifiedAdaptiveDualThresholdQuantizer",
    "QuantizationResult",

    "compute_key_agreement_rate",
    "compute_bit_error_rate",
    "compute_key_generation_rate",
    "plot_quantization_thresholds_overlay",
    "plot_quantization_symbol_timeline",
    "plot_quantization_levels_distribution",
    "plot_kar_comparison_bar",
]


