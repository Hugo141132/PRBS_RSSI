"""
d03_runner.py

Runner script for Milestone D03: Modified Adaptive Dual-Threshold Quantization (ADQ)
for the Physical Layer Secret Key Generation (SKG) pipeline.

Executes:
1. Loads the D02 Adaptive Kalman Filter filtered RSSI dataset.
2. Applies Modified Adaptive Dual-Threshold Quantization (ADQ) across all 4 channels:
   - Evaluates both 2-bit (Gray coding) and 4-bit configurations.
   - Evaluates parameter sensitivity across alpha multiplier values (0.1 to 1.0).
   - Preserves intermediate samples as Level 1 without sample dropping.
3. Computes Key Agreement Rate (KAR) and Bit Error Rate (BER) across channel pairs:
   - Alice vs Bob (legitimate reciprocal link)
   - Alice vs Eve1-Alice (eavesdropper link)
   - Bob vs Eve1-Bob (eavesdropper link)
4. Saves results to results/dummy/d03_quantization_results.json,
   generated bits to results/dummy/d03_quantized_bits.csv,
   and publication-ready visualization figures.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.quantization import (
    ModifiedAdaptiveDualThresholdQuantizer,
    compute_bit_error_rate,
    compute_key_agreement_rate,
    compute_key_generation_rate,
)
from src.analysis.visualization import (
    plot_kar_comparison_bar,
    plot_quantization_levels_distribution,
    plot_quantization_symbol_timeline,
    plot_quantization_thresholds_overlay,
)


APPROVED_RAW_COLUMNS = ["Alice", "Bob", "Eve1-Alice", "Eve1-Bob"]
FILTERED_COLUMNS = [f"{col}_Filtered" for col in APPROVED_RAW_COLUMNS]


def run_d03_pipeline(
    input_csv_path: Optional[str] = None,
    output_json_path: Optional[str] = None,
    output_bits_csv_path: Optional[str] = None,
    figures_dir: Optional[str] = None,
    alpha: float = 0.5,
    segment_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute full D03 Modified ADQ quantization pipeline on D02 filtered RSSI.

    Args:
        input_csv_path: Path to D02 filtered CSV. Defaults to results/dummy/d02_mshkf_filtered.csv.
        output_json_path: Path for output JSON report.
        output_bits_csv_path: Path for output quantized bits CSV.
        figures_dir: Directory to save generated figures.
        alpha: Multiplier coefficient for adaptive thresholds (default: 0.5).
        segment_size: Window size for segmented threshold adaptation (default: None, global).

    Returns:
        Structured results payload dictionary.
    """
    if input_csv_path is None:
        input_csv_path = os.path.join(project_root, "results", "dummy", "d02_mshkf_filtered.csv")
    if output_json_path is None:
        output_json_path = os.path.join(project_root, "results", "dummy", "d03_quantization_results.json")
    if output_bits_csv_path is None:
        output_bits_csv_path = os.path.join(project_root, "results", "dummy", "d03_quantized_bits.csv")
    if figures_dir is None:
        figures_dir = os.path.join(project_root, "results", "dummy", "figures", "d03")

    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"D02 filtered CSV not found at: {input_csv_path}. Please run D02 pipeline first.")

    df_filtered = pd.read_csv(input_csv_path)
    n_samples = len(df_filtered)

    # Verify required columns exist
    for col in FILTERED_COLUMNS:
        if col not in df_filtered.columns:
            raise ValueError(f"Required filtered column {col} missing from input CSV: {input_csv_path}")

    # Initialize Modified ADQ quantizers
    adq_2bit = ModifiedAdaptiveDualThresholdQuantizer(alpha=alpha, bit_depth=2, segment_size=segment_size)
    adq_4bit = ModifiedAdaptiveDualThresholdQuantizer(alpha=alpha, bit_depth=4, segment_size=segment_size)

    # 1. Run quantization across all 4 channels
    channel_results_2bit: Dict[str, Any] = {}
    channel_results_4bit: Dict[str, Any] = {}

    bits_df_data: Dict[str, List[Union[int, str]]] = {}

    for ch in APPROVED_RAW_COLUMNS:
        filt_col = f"{ch}_Filtered"
        data = df_filtered[filt_col].to_numpy(dtype=np.float64)

        res_2b = adq_2bit.quantize(data)
        res_4b = adq_4bit.quantize(data)

        channel_results_2bit[ch] = res_2b.to_dict()
        channel_results_4bit[ch] = res_4b.to_dict()

        bits_df_data[f"{ch}_Symbol"] = res_2b.symbols
        bits_df_data[f"{ch}_2bit"] = [adq_2bit.encoding_table[s] for s in res_2b.symbols]
        bits_df_data[f"{ch}_4bit"] = [adq_4bit.encoding_table[s] for s in res_4b.symbols]

    # 2. Compute Channel Pair Agreements (Alice vs Bob, Alice vs Eve1-Alice, Bob vs Eve1-Bob)
    pairs: List[Tuple[str, str]] = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    pair_metrics_2bit: Dict[str, Dict[str, float]] = {}
    pair_metrics_4bit: Dict[str, Dict[str, float]] = {}

    for col_a, col_b in pairs:
        pair_key = f"{col_a} vs {col_b}"

        # 2-bit Modified ADQ
        k_a_2b = channel_results_2bit[col_a]["bits"]
        k_b_2b = channel_results_2bit[col_b]["bits"]
        kar_2b = compute_key_agreement_rate(k_a_2b, k_b_2b)
        ber_2b = compute_bit_error_rate(k_a_2b, k_b_2b)
        pair_metrics_2bit[pair_key] = {
            "kar": kar_2b,
            "ber": ber_2b,
            "bit_length": len(k_a_2b),
            "matching_bits": int(round(kar_2b * len(k_a_2b))),
            "mismatch_bits": int(round(ber_2b * len(k_a_2b))),
        }

        # 4-bit Modified ADQ
        k_a_4b = channel_results_4bit[col_a]["bits"]
        k_b_4b = channel_results_4bit[col_b]["bits"]
        kar_4b = compute_key_agreement_rate(k_a_4b, k_b_4b)
        ber_4b = compute_bit_error_rate(k_a_4b, k_b_4b)
        pair_metrics_4bit[pair_key] = {
            "kar": kar_4b,
            "ber": ber_4b,
            "bit_length": len(k_a_4b),
            "matching_bits": int(round(kar_4b * len(k_a_4b))),
            "mismatch_bits": int(round(ber_4b * len(k_a_4b))),
        }

    # 3. Alpha sensitivity sweep (Alice vs Bob)
    alpha_sweep_results: List[Dict[str, Any]] = []
    for test_alpha in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        q2 = ModifiedAdaptiveDualThresholdQuantizer(alpha=test_alpha, bit_depth=2, segment_size=segment_size)
        q4 = ModifiedAdaptiveDualThresholdQuantizer(alpha=test_alpha, bit_depth=4, segment_size=segment_size)

        res_a_2 = q2.quantize(df_filtered["Alice_Filtered"].to_numpy())
        res_b_2 = q2.quantize(df_filtered["Bob_Filtered"].to_numpy())
        res_a_4 = q4.quantize(df_filtered["Alice_Filtered"].to_numpy())
        res_b_4 = q4.quantize(df_filtered["Bob_Filtered"].to_numpy())

        kar2 = compute_key_agreement_rate(res_a_2.bits, res_b_2.bits)
        kar4 = compute_key_agreement_rate(res_a_4.bits, res_b_4.bits)

        alpha_sweep_results.append({
            "alpha": test_alpha,
            "kar_2bit": kar2,
            "kar_4bit": kar4,
            "bit_length_2bit": len(res_a_2.bits),
            "bit_length_4bit": len(res_a_4.bits),
            "retained_samples_alice": res_a_2.retained_samples,
            "discarded_samples_alice": res_a_2.discarded_samples,
        })

    # 4. Key Generation Rate (KGR) statistics
    kgr_stats = {
        "modified_adq_2bit": compute_key_generation_rate(
            bit_length=channel_results_2bit["Alice"]["bit_length"],
            num_samples=n_samples,
        ),
        "modified_adq_4bit": compute_key_generation_rate(
            bit_length=channel_results_4bit["Alice"]["bit_length"],
            num_samples=n_samples,
        ),
    }

    # 5. Build output files and figures
    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_bits_csv_path)), exist_ok=True)
    os.makedirs(os.path.abspath(figures_dir), exist_ok=True)

    bits_df = pd.DataFrame(bits_df_data)
    # Ensure all bit sequence columns are exported as Excel-compatible text formulas
    # so Excel forces cell format to Text rather than General (preventing integer conversion & stripping leading zeros)
    excel_bits_df = bits_df.copy()
    for ch in APPROVED_RAW_COLUMNS:
        excel_bits_df[f"{ch}_2bit"] = excel_bits_df[f"{ch}_2bit"].apply(lambda x: f'="{x}"')
        excel_bits_df[f"{ch}_4bit"] = excel_bits_df[f"{ch}_4bit"].apply(lambda x: f'="{x}"')

    try:
        excel_bits_df.to_csv(output_bits_csv_path, index=False)
    except PermissionError:
        print(f"[WARNING] Could not overwrite '{output_bits_csv_path}' because it is open in another program (e.g. Microsoft Excel).")


    # Generate figures
    fig_paths = {}
    fig_paths["thresholds_overlay"] = plot_quantization_thresholds_overlay(
        df_filtered=df_filtered,
        channels=APPROVED_RAW_COLUMNS,
        threshold_info={ch: channel_results_2bit[ch]["thresholds"] for ch in APPROVED_RAW_COLUMNS},
        output_path=os.path.join(figures_dir, "d03_adq_thresholds_overlay.png"),
    )
    fig_paths["levels_distribution"] = plot_quantization_levels_distribution(
        channel_results=channel_results_2bit,
        channels=APPROVED_RAW_COLUMNS,
        output_path=os.path.join(figures_dir, "d03_adq_levels_distribution.png"),
    )
    fig_paths["symbol_timeline"] = plot_quantization_symbol_timeline(
        df_bits=bits_df,
        channels=APPROVED_RAW_COLUMNS,
        output_path=os.path.join(figures_dir, "d03_adq_symbol_timeline.png"),
    )
    fig_paths["kar_comparison"] = plot_kar_comparison_bar(
        adq_2bit=pair_metrics_2bit,
        adq_4bit=pair_metrics_4bit,
        output_path=os.path.join(figures_dir, "d03_kar_comparison.png"),
    )


    results_payload = {
        "milestone": "D03",
        "algorithm": "Modified Adaptive Dual-Threshold Quantization (ADQ)",
        "reference": "LoRa-PRIME (IEEE OJ-COMS 2026, Section IV-C)",
        "configuration": {
            "alpha": alpha,
            "segment_size": segment_size,
            "input_file": os.path.abspath(input_csv_path),
            "sample_count": n_samples,
            "preserves_intermediate_samples": True,
        },
        "channel_quantization_results": {
            "modified_adq_2bit": channel_results_2bit,
            "modified_adq_4bit": channel_results_4bit,
        },
        "pair_agreement_metrics": {
            "modified_adq_2bit": pair_metrics_2bit,
            "modified_adq_4bit": pair_metrics_4bit,
        },
        "alpha_sensitivity_sweep": alpha_sweep_results,
        "kgr_statistics": kgr_stats,
        "generated_artifacts": {
            "results_json": os.path.abspath(output_json_path),
            "quantized_bits_csv": os.path.abspath(output_bits_csv_path),
            "figures": {k: os.path.abspath(v) for k, v in fig_paths.items()},
        },
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=4)

    return results_payload


if __name__ == "__main__":
    print("Executing Milestone D03: Modified Adaptive Dual-Threshold Quantization...")
    res = run_d03_pipeline()
    print("D03 Execution Completed Successfully!")
    print(f"Results JSON: {res['generated_artifacts']['results_json']}")
    print(f"Bits CSV: {res['generated_artifacts']['quantized_bits_csv']}")
    print("\nLegitimate Key Agreement Rate (Alice vs Bob):")
    print(f"  2-bit Modified ADQ: KAR = {res['pair_agreement_metrics']['modified_adq_2bit']['Alice vs Bob']['kar']:.4f}")
    print(f"  4-bit Modified ADQ: KAR = {res['pair_agreement_metrics']['modified_adq_4bit']['Alice vs Bob']['kar']:.4f}")
    print("\nEavesdropper Key Agreement Rate (Alice vs Eve1-Alice):")
    print(f"  2-bit Modified ADQ: KAR = {res['pair_agreement_metrics']['modified_adq_2bit']['Alice vs Eve1-Alice']['kar']:.4f}")
    print(f"  4-bit Modified ADQ: KAR = {res['pair_agreement_metrics']['modified_adq_4bit']['Alice vs Eve1-Alice']['kar']:.4f}")
