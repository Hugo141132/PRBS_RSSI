"""
d04_runner.py

Runner script for Milestone D04.0: Per-Sample Pure Galois LFSR PRBS Bit Expansion
for the Physical Layer Secret Key Generation (SKG) pipeline.

Scientific References & Lineage:
- Primary Reference: Vimalathithan et al. (2013), Malaysian Journal of Mathematical Sciences 7(S): 59-72.
  Section 2 (pp. 62-63) & Section 4 (pp. 66-67).
  * NOTE ON ADAPTATION FIDELITY: The reference paper repeats rolling code sequences 8 times
    prior to a 128-bit LFSR. In our SKG pipeline, we adapt pure Galois LFSR expansion to operate
    PER-SAMPLE: each D03 quantization sample's 2-bit or 4-bit output directly seeds an independent
    Galois LFSR instance (resetting per sample) without sample concatenation, remapping, hashing,
    scrambling, or nonlinear mixing.
- Upstream Stage: Milestone D03 Modified Adaptive Dual-Threshold Quantization (ADQ)
  (results/dummy/d03_quantized_bits.csv, 500 samples per channel).
- Approved Roadmap:
  D03 quantization -> D04.0 Galois LFSR expansion -> D04.1 BCH reconciliation -> D05 Galois LFSR expansion.

Executes:
1. Loads per-sample quantized bit seeds from D03 (2-bit Gray coding and 4-bit LoRa-PRIME representations).
2. Expands each sample independently with zero cross-sample state leakage (LFSR reset per sample).
   - 2-bit seed -> 4 output bits (2x expansion) via primitive polynomial P(x) = x^2 + x + 1 (period 3).
   - 4-bit seed -> 8 output bits (2x expansion) via primitive polynomial P(x) = x^4 + x + 1 (period 15).
3. Preserves zero seeds and flags all-zero outputs without remapping or substitution.
4. Computes pre- and post-expansion KAR / BER across legitimate (Alice-Bob) and eavesdropper channel pairs.
5. Preserves historical 32-bit blockwise expansion benchmarks separately.
6. Exports results to results/dummy/d04_galois_lfsr_results.json,
   results/dummy/d04_expanded_bits.csv, and publication figures in results/dummy/figures/d04/.
"""

import hashlib
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

from src.analysis.lfsr import (
    DEGREE_2,
    DEGREE_2_TAPS,
    DEGREE_2_TAP_MASK,
    DEGREE_4,
    DEGREE_4_TAPS,
    DEGREE_4_TAP_MASK,
    DEFAULT_DEGREE,
    DEFAULT_POLYNOMIAL_TAPS,
    DEFAULT_TAP_MASK,
    ExpansionResult,
    GaloisLFSR,
    PerSampleExpansionResult,
    SampleExpansionDetail,
    compute_expansion_agreement_metrics,
    compute_per_sample_agreement_metrics,
    create_sample_lfsr,
    expand_bitstream_blocks,
    expand_sample_sequences,
    get_per_sample_symbol_mapping,
)
from src.analysis.visualization import (
    plot_lfsr_ber_vs_length,
    plot_lfsr_block_analysis,
    plot_lfsr_kar_expansion_comparison,
)

CHANNELS = ["Alice", "Bob", "Eve1-Alice", "Eve1-Bob"]
BIT_DEPTHS = ["2bit", "4bit"]
DEFAULT_OUTPUT_LEN_2BIT = 3   # 2-bit seed -> 3 output bits (m = 2^2 - 1 = 3)
DEFAULT_OUTPUT_LEN_4BIT = 15  # 4-bit seed -> 15 output bits (m = 2^4 - 1 = 15)


def compute_file_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file for cryptographic provenance verification."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_d03_samples(csv_path: str) -> Tuple[Dict[str, Dict[str, List[str]]], List[int]]:
    """
    Load D03 quantized sample seeds per channel and depth from CSV.

    Preserves leading zeros by stripping any Excel text wrapper formulas (="...").

    Returns:
        samples: {depth: {channel: [500 seed strings]}}
        sample_ids: [0, 1, ..., 499]
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"D03 quantized bits CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    sample_ids = df["Sample_ID"].tolist() if "Sample_ID" in df.columns else list(range(len(df)))

    samples: Dict[str, Dict[str, List[str]]] = {depth: {} for depth in BIT_DEPTHS}

    for depth in BIT_DEPTHS:
        for ch in CHANNELS:
            col = f"{ch}_{depth}"
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' not found in {csv_path}.")
            clean_series = (
                df[col]
                .astype(str)
                .str.replace("=", "", regex=False)
                .str.replace('"', "", regex=False)
                .str.strip()
            )
            samples[depth][ch] = clean_series.tolist()

    return samples, sample_ids


def run_historical_32bit_expansion(
    samples: Dict[str, Dict[str, List[str]]],
    output_lengths: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Execute historical 32-bit blockwise expansion for benchmarking.
    """
    if output_lengths is None:
        output_lengths = [40, 48, 64]

    degree = DEFAULT_DEGREE
    bitstreams: Dict[str, Dict[str, str]] = {
        depth: {ch: "".join(samples[depth][ch]) for ch in CHANNELS}
        for depth in BIT_DEPTHS
    }

    pairs: List[Tuple[str, str]] = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    hist_experiments: Dict[str, Any] = {}
    channel_objects: Dict[str, Dict[str, Dict[int, ExpansionResult]]] = {
        d: {ch: {} for ch in CHANNELS} for d in BIT_DEPTHS
    }

    for depth in BIT_DEPTHS:
        hist_experiments[depth] = {}
        for out_len in output_lengths:
            exp_key = f"length_{out_len}"
            hist_experiments[depth][exp_key] = {
                "output_length_per_block": out_len,
                "expansion_ratio": round(out_len / degree, 4),
                "pairs": {},
            }
            for ch in CHANNELS:
                stream = bitstreams[depth][ch]
                ch_lfsr = GaloisLFSR(
                    degree=degree,
                    polynomial_taps=DEFAULT_POLYNOMIAL_TAPS,
                    shift_direction="left",
                    output_bit="msb",
                    output_timing="before_update",
                    seed_bit_order="msb_first",
                )
                res = expand_bitstream_blocks(
                    bitstream=stream,
                    seed_length=degree,
                    output_length=out_len,
                    lfsr=ch_lfsr,
                    partial_handling="exclude",
                )
                channel_objects[depth][ch][out_len] = res

            for node_a, node_b in pairs:
                pair_name = f"{node_a} vs {node_b}"
                exp_a = channel_objects[depth][node_a][out_len]
                exp_b = channel_objects[depth][node_b][out_len]
                pair_metrics = compute_expansion_agreement_metrics(
                    exp_a=exp_a,
                    exp_b=exp_b,
                    label_a=node_a,
                    label_b=node_b,
                )
                hist_experiments[depth][exp_key]["pairs"][pair_name] = pair_metrics

    return {
        "description": "Historical 32-bit blockwise expansion results (31 blocks for 2-bit, 62 blocks for 4-bit, truncated tails).",
        "lfsr_configuration": {
            "register_width": 32,
            "primitive_polynomial": "x^32 + x^22 + x^2 + x^1 + 1",
            "tap_mask_hex": hex(DEFAULT_TAP_MASK),
            "tested_output_lengths": output_lengths,
        },
        "experiments": hist_experiments,
    }


def run_d04_pipeline(
    input_bits_csv: Optional[str] = None,
    output_json_path: Optional[str] = None,
    output_expanded_csv: Optional[str] = None,
    historical_csv_path: Optional[str] = None,
    figures_dir: Optional[str] = None,
    output_length_2bit: int = DEFAULT_OUTPUT_LEN_2BIT,
    output_length_4bit: int = DEFAULT_OUTPUT_LEN_4BIT,
) -> Dict[str, Any]:
    """
    Execute full Milestone D04.0 Per-Sample Pure Galois LFSR expansion pipeline.

    Args:
        input_bits_csv: Path to D03 quantized bits CSV.
        output_json_path: Path for results JSON.
        output_expanded_csv: Path for active per-sample expanded bit sequences CSV.
        historical_csv_path: Optional path for historical 32-bit blockwise CSV.
        figures_dir: Directory to save generated publication figures.
        output_length_2bit: Output length for 2-bit seeds (default: 4 bits).
        output_length_4bit: Output length for 4-bit seeds (default: 8 bits).

    Returns:
        Structured results payload dictionary.
    """
    if input_bits_csv is None:
        input_bits_csv = os.path.join(project_root, "results", "dummy", "d03_quantized_bits.csv")
    if output_json_path is None:
        output_json_path = os.path.join(project_root, "results", "dummy", "d04_galois_lfsr_results.json")
    if output_expanded_csv is None:
        output_expanded_csv = os.path.join(project_root, "results", "dummy", "d04_expanded_bits.csv")
    if historical_csv_path is None:
        historical_csv_path = os.path.join(project_root, "results", "dummy", "d04_historical_32bit_expanded_bits.csv")
    if figures_dir is None:
        figures_dir = os.path.join(project_root, "results", "dummy", "figures", "d04")

    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_expanded_csv)), exist_ok=True)

    # 1. Provenance Hash & Load D03 samples
    input_sha256 = compute_file_sha256(input_bits_csv)
    samples, sample_ids = load_d03_samples(input_bits_csv)
    num_samples = len(sample_ids)

    # 2. Active Per-Sample LFSR Expansion
    # 2-bit: Degree 2, P(x) = x^2 + x + 1, taps (2, 1, 0), tap mask 0x3, period 3
    # 4-bit: Degree 4, P(x) = x^4 + x + 1, taps (4, 1, 0), tap mask 0x3, period 15
    per_sample_results: Dict[str, Dict[str, PerSampleExpansionResult]] = {
        "2bit": {},
        "4bit": {},
    }

    for ch in CHANNELS:
        per_sample_results["2bit"][ch] = expand_sample_sequences(
            seed_strings=samples["2bit"][ch],
            seed_length=2,
            output_length=output_length_2bit,
            channel=ch,
            bit_depth="2bit",
        )
        per_sample_results["4bit"][ch] = expand_sample_sequences(
            seed_strings=samples["4bit"][ch],
            seed_length=4,
            output_length=output_length_4bit,
            channel=ch,
            bit_depth="4bit",
        )

    # 3. Deterministic Symbol Mappings & Hamming Distances
    mapping_2bit = get_per_sample_symbol_mapping("2bit", output_length_2bit)
    mapping_4bit = get_per_sample_symbol_mapping("4bit", output_length_4bit)

    # 4. Pair Agreement Metrics
    pairs: List[Tuple[str, str]] = [
        ("Alice", "Bob"),
        ("Alice", "Eve1-Alice"),
        ("Bob", "Eve1-Bob"),
    ]

    pair_metrics_record: Dict[str, Dict[str, Any]] = {
        "2bit": {},
        "4bit": {},
    }

    for depth in BIT_DEPTHS:
        for node_a, node_b in pairs:
            pair_name = f"{node_a} vs {node_b}"
            res_a = per_sample_results[depth][node_a]
            res_b = per_sample_results[depth][node_b]
            metrics = compute_per_sample_agreement_metrics(
                res_a=res_a,
                res_b=res_b,
                label_a=node_a,
                label_b=node_b,
            )
            # Add backwards-compatibility aliases for legacy visualization & testing
            metrics["seed_block_match_pct"] = metrics["sample_match_pct"]
            metrics["post_expansion_all_blocks"] = metrics["post_expansion"]
            pair_metrics_record[depth][pair_name] = metrics

    # 5. Export Active Per-Sample Expanded CSV
    csv_rows: List[Dict[str, Any]] = []
    for idx in range(num_samples):
        row: Dict[str, Any] = {"Sample_ID": sample_ids[idx]}
        for depth in BIT_DEPTHS:
            for ch in CHANNELS:
                s_detail = per_sample_results[depth][ch].samples[idx]
                row[f"{ch}_{depth}_Seed"] = f'="{s_detail.seed_string}"'
                row[f"{ch}_{depth}_IsZero"] = s_detail.is_zero_seed
                row[f"{ch}_{depth}_Expanded"] = f'="{s_detail.expanded_string}"'
        csv_rows.append(row)

    df_expanded = pd.DataFrame(csv_rows)
    try:
        df_expanded.to_csv(output_expanded_csv, index=False)
    except PermissionError:
        print(f"[WARNING] Could not overwrite '{output_expanded_csv}' (file in use).")

    # 6. Historical 32-bit Blockwise Expansion (Preserved Separately)
    historical_benchmark = run_historical_32bit_expansion(samples)
    
    # Save historical 32-bit CSV
    hist_rows: List[Dict[str, Any]] = []
    bitstreams_hist = {
        d: {ch: "".join(samples[d][ch]) for ch in CHANNELS} for d in BIT_DEPTHS
    }
    hist_exp_objs = {
        d: {
            ch: expand_bitstream_blocks(
                bitstreams_hist[d][ch], seed_length=32, output_length=64, partial_handling="exclude"
            )
            for ch in CHANNELS
        }
        for d in BIT_DEPTHS
    }
    max_hist_blocks = max(
        hist_exp_objs["2bit"]["Alice"].num_full_blocks,
        hist_exp_objs["4bit"]["Alice"].num_full_blocks,
    )
    for b_idx in range(max_hist_blocks):
        h_row: Dict[str, Any] = {"Block_Index": b_idx}
        for depth in BIT_DEPTHS:
            for ch in CHANNELS:
                obj = hist_exp_objs[depth][ch]
                if b_idx < obj.num_full_blocks:
                    b_det = obj.blocks[b_idx]
                    h_row[f"{ch}_{depth}_Seed"] = f'="{b_det.seed_string}"'
                    h_row[f"{ch}_{depth}_IsZeroSeed"] = b_det.is_zero_seed
                    h_row[f"{ch}_{depth}_Exp_64b"] = f'="{b_det.expanded_string}"'
                else:
                    h_row[f"{ch}_{depth}_Seed"] = ""
                    h_row[f"{ch}_{depth}_IsZeroSeed"] = None
                    h_row[f"{ch}_{depth}_Exp_64b"] = ""
        hist_rows.append(h_row)
    try:
        pd.DataFrame(hist_rows).to_csv(historical_csv_path, index=False)
    except Exception:
        pass

    # 6b. Historical 2x Per-Sample Expansion (Preserved Separately)
    hist_2x_experiments = {"2bit": {}, "4bit": {}}
    res_2b_4b = {ch: expand_sample_sequences(samples["2bit"][ch], seed_length=2, output_length=4, channel=ch, bit_depth="2bit") for ch in CHANNELS}
    res_4b_8b = {ch: expand_sample_sequences(samples["4bit"][ch], seed_length=4, output_length=8, channel=ch, bit_depth="4bit") for ch in CHANNELS}
    for na, nb in pairs:
        hist_2x_experiments["2bit"][f"{na} vs {nb}"] = compute_per_sample_agreement_metrics(res_2b_4b[na], res_2b_4b[nb], na, nb)
        hist_2x_experiments["4bit"][f"{na} vs {nb}"] = compute_per_sample_agreement_metrics(res_4b_8b[na], res_4b_8b[nb], na, nb)
    historical_2x_benchmark = {
        "description": "Historical 2x per-sample expansion benchmark (2-bit seed -> 4 bits, 4-bit seed -> 8 bits).",
        "experiments": hist_2x_experiments,
    }

    # 7. Channel summary dictionary
    channel_expansions_summary: Dict[str, Any] = {}
    for depth in BIT_DEPTHS:
        channel_expansions_summary[depth] = {}
        for ch in CHANNELS:
            res_obj = per_sample_results[depth][ch]
            channel_expansions_summary[depth][ch] = {
                "channel": ch,
                "bit_depth": depth,
                "seed_length": res_obj.seed_length,
                "output_length": res_obj.output_length,
                "expansion_ratio": res_obj.expansion_ratio,
                "total_samples": res_obj.total_samples,
                "total_output_bits": res_obj.total_output_bits,
                "zero_seed_count": res_obj.zero_seed_count,
                "zero_seed_pct": res_obj.zero_seed_pct,
            }

    # 8. Assemble Master JSON Payload
    results_payload: Dict[str, Any] = {
        "milestone": "D04.0",
        "algorithm": "Per-Sample Pure Galois LFSR PRBS Bit Expansion (m = 2^L - 1)",
        "architecture": "per_sample_pure_galois_lfsr",
        "output_length_formula": "m = 2^L - 1",
        "scientific_fidelity_and_adaptation_note": (
            "In Vimalathithan et al. (2013), the 16->128 expansion repeats the rolling code sequence 8 times "
            "prior to feeding a 128-bit LFSR. In our SKG pipeline Milestone D04.0, bit expansion is executed "
            "purely PER-SAMPLE with full maximal-period sequence length m = 2^L - 1 (3 bits for L=2, 15 bits for L=4): "
            "each D03 quantization sample (2-bit or 4-bit) serves directly as an LFSR seed with an explicit reset "
            "before each sample. There is NO cross-sample concatenation, no padding, no seed remapping, no hashing, "
            "and no scrambling. Repeated seeds yield identical deterministic outputs. The full-period sequence length "
            "is our design choice, not a mandated expansion formula from Galois.pdf. Expansion adds length, not secret "
            "entropy. We claim neither cryptographic randomness nor guaranteed downstream BCH success."
        ),
        "active_configuration": {
            "mode": "per_sample_expansion",
            "output_length_formula": "m = 2^L - 1",
            "reset_behavior": "reset_before_each_sample",
            "sample_concatenation": False,
            "hash_or_scramble_applied": False,
            "bch_implemented": False,
            "2bit": {
                "seed_length": 2,
                "output_length": output_length_2bit,
                "expansion_ratio": round(output_length_2bit / 2, 4),
                "register_width": DEGREE_2,
                "primitive_polynomial": "x^2 + x + 1",
                "polynomial_taps": list(DEGREE_2_TAPS),
                "tap_mask_hex": hex(DEGREE_2_TAP_MASK),
                "maximum_period": (1 << DEGREE_2) - 1,
                "shift_direction": "left",
                "output_bit": "msb",
                "output_timing": "before_update",
                "seed_bit_order": "msb_first",
                "symbol_mapping": mapping_2bit["symbols"],
                "pairwise_output_hamming_distances": mapping_2bit["pairwise_hamming_distances"],
            },
            "4bit": {
                "seed_length": 4,
                "output_length": output_length_4bit,
                "expansion_ratio": round(output_length_4bit / 4, 4),
                "register_width": DEGREE_4,
                "primitive_polynomial": "x^4 + x + 1",
                "polynomial_taps": list(DEGREE_4_TAPS),
                "tap_mask_hex": hex(DEGREE_4_TAP_MASK),
                "maximum_period": (1 << DEGREE_4) - 1,
                "shift_direction": "left",
                "output_bit": "msb",
                "output_timing": "before_update",
                "seed_bit_order": "msb_first",
                "symbol_mapping": mapping_4bit["symbols"],
                "pairwise_output_hamming_distances": mapping_4bit["pairwise_hamming_distances"],
            },
        },
        "input_provenance": {
            "source_file": os.path.abspath(input_bits_csv),
            "sha256": input_sha256,
            "total_samples_per_channel": num_samples,
            "input_bit_counts": {
                "2bit": {ch: num_samples * 2 for ch in CHANNELS},
                "4bit": {ch: num_samples * 4 for ch in CHANNELS},
            },
            "output_bit_counts": {
                "2bit": {ch: num_samples * output_length_2bit for ch in CHANNELS},
                "4bit": {ch: num_samples * output_length_4bit for ch in CHANNELS},
            },
            "zero_seed_counts": {
                "2bit": {ch: per_sample_results["2bit"][ch].zero_seed_count for ch in CHANNELS},
                "4bit": {ch: per_sample_results["4bit"][ch].zero_seed_count for ch in CHANNELS},
            },
            "omitted_tail_bits": {
                "2bit": 0,
                "4bit": 0,
            },
        },
        "channel_expansions": channel_expansions_summary,
        "experiments": {
            "2bit": {
                "seed_length": 2,
                "output_length": output_length_2bit,
                "expansion_ratio": round(output_length_2bit / 2, 4),
                "pairs": pair_metrics_record["2bit"],
            },
            "4bit": {
                "seed_length": 4,
                "output_length": output_length_4bit,
                "expansion_ratio": round(output_length_4bit / 4, 4),
                "pairs": pair_metrics_record["4bit"],
            },
        },
        "historical_32bit_blockwise": historical_benchmark,
        "historical_2x_persample": historical_2x_benchmark,
        "generated_artifacts": {
            "results_json": os.path.abspath(output_json_path),
            "expanded_bits_csv": os.path.abspath(output_expanded_csv),
            "historical_32bit_csv": os.path.abspath(historical_csv_path),
            "figures": {},
        },
    }

    # 9. Generate Publication Figures
    fig_paths: Dict[str, str] = {}
    fig_paths["kar_expansion_comparison"] = plot_lfsr_kar_expansion_comparison(
        d04_results=results_payload,
        output_path=os.path.join(figures_dir, "d04_kar_expansion_comparison.png"),
    )
    fig_paths["ber_vs_length"] = plot_lfsr_ber_vs_length(
        d04_results=results_payload,
        output_path=os.path.join(figures_dir, "d04_ber_vs_length.png"),
    )
    fig_paths["block_seed_analysis"] = plot_lfsr_block_analysis(
        d04_results=results_payload,
        output_path=os.path.join(figures_dir, "d04_block_seed_analysis.png"),
    )
    results_payload["generated_artifacts"]["figures"] = {
        k: os.path.abspath(v) for k, v in fig_paths.items()
    }

    # 10. Write Results JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=4)

    return results_payload


if __name__ == "__main__":
    print("Executing Milestone D04.0: Per-Sample Pure Galois LFSR PRBS Bit Expansion...")
    res = run_d04_pipeline()
    print("D04.0 Pipeline Execution Completed Successfully!")
    print(f"Results JSON: {res['generated_artifacts']['results_json']}")
    print(f"Expanded Bits CSV: {res['generated_artifacts']['expanded_bits_csv']}")

    for depth in BIT_DEPTHS:
        print(f"\n================ Input: {depth.upper()} ADQ Per-Sample ================")
        exp_data = res["experiments"][depth]["pairs"]["Alice vs Bob"]
        pre_kar = exp_data["pre_expansion"]["kar"]
        post_kar = exp_data["post_expansion"]["kar"]
        post_ber = exp_data["post_expansion"]["ber"]
        ratio = exp_data["expansion_ratio"]
        print(
            f"  {depth.upper()} (Seed {exp_data['seed_length']}b -> Output {exp_data['output_length']}b, {ratio:.1f}x): "
            f"Pre-KAR = {pre_kar:.4f} -> Post-KAR = {post_kar:.4f} (BER = {post_ber:.4f})"
        )
