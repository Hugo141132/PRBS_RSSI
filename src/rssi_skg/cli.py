"""Command Line Interface (CLI) for RSSI correlation and filtering analysis.

Executes Pearson correlation analysis on RSSI datasets according to PA.pdf Eq (3.62),
with optional preprocessing using the Modified Sage–Husa Adaptive Kalman Filter (MSHKF)
according to PA.pdf Section 3.2.2, Equations (3.10)–(3.20).

Calculating pairs:
- Alice–Bob
- Alice–Eve1-Alice
- Bob–Eve1-Bob

Exports:
- Correlation CSV (raw or before/after comparison)
- Optional aligned raw/filtered samples CSV
- Optional filter configuration metadata JSON
- Optional figure plots (PNG 300 dpi and PDF)
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from rssi_skg.correlation import pearson_correlation
from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import (
    plot_combined_correlation_figure,
    plot_filtering_comparison_figure,
    plot_kar_comparison_figure,
)
from rssi_skg.quantization import (
    ChannelQuantizationResult,
    QuantizationConfig,
    export_quantization_metadata_json,
    export_quantization_metrics_csv,
    export_quantized_bitstreams_csv,
    export_quantized_samples_csv,
    export_quantized_segments_csv,
    export_quantized_workbook_xlsx,
    quantize_channels,
)


TARGET_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("Alice", "Bob", "Alice–Bob"),
    ("Alice", "Eve1-Alice", "Alice–Eve1-Alice"),
    ("Bob", "Eve1-Bob", "Bob–Eve1-Bob"),
)


def export_aligned_samples_csv(
    raw_data: dict[str, list[float]],
    filtered_data: dict[str, list[float]],
    output_path: str | Path,
) -> Path:
    """Export aligned raw and filtered RSSI samples to a CSV file.

    Args:
        raw_data: Mapping of raw RSSI sequences.
        filtered_data: Mapping of filtered RSSI sequences.
        output_path: Path to destination CSV.

    Returns:
        Path: Destination path of written CSV.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    columns = ["Alice", "Bob", "Eve1-Alice", "Eve1-Bob"]
    n_samples = len(raw_data[columns[0]])

    header = ["sample_index"]
    for col in columns:
        header.append(f"{col}_raw")
        header.append(f"{col}_filtered")

    with open(out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(n_samples):
            row: list[Any] = [i]
            for col in columns:
                row.append(raw_data[col][i])
                row.append(filtered_data[col][i])
            writer.writerow(row)

    return out_path


def export_filter_metadata_json(
    filter_config: FilterConfig,
    output_path: str | Path,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Export filter configuration and rationale metadata to a JSON file.

    Args:
        filter_config: FilterConfig object.
        output_path: Destination path for JSON.
        extra_metadata: Optional dictionary of additional metadata to include.

    Returns:
        Path: Destination path of written JSON.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = filter_config.to_metadata_dict()
    if extra_metadata:
        meta.update(extra_metadata)

    with open(out_path, mode="w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return out_path


def run_correlation_analysis(
    input_path: str | Path,
    output_path: str | Path | None = None,
    figure_prefix: str | Path | None = None,
    data_kind: str = "dummy",
    enable_filter: bool = False,
    filter_config: FilterConfig | None = None,
    filtered_samples_output: str | Path | None = None,
    filter_config_output: str | Path | None = None,
    enable_quantize: bool = False,
    quantize_config: QuantizationConfig | None = None,
    quantized_samples_output: str | Path | None = None,
    quantized_segments_output: str | Path | None = None,
    quantized_bitstreams_output: str | Path | None = None,
    quantize_config_output: str | Path | None = None,
    quantize_metrics_output: str | Path | None = None,
    quantized_xlsx_output: str | Path | None = None,
    quantize_figure_prefix: str | Path | None = None,
    return_quant_result: bool = False,
) -> tuple[list[dict[str, Any]], tuple[Path, Path] | None] | tuple[list[dict[str, Any]], tuple[Path, Path] | None, ChannelQuantizationResult | None]:
    """Execute correlation analysis on the given workbook, optionally filtering, quantizing, and saving artifacts.

    Args:
        input_path: Path to the Excel workbook.
        output_path: Optional path to save resulting CSV.
        figure_prefix: Optional file prefix to export PNG (300 dpi) and PDF figures.
        data_kind: Data category tag, default 'dummy'.
        enable_filter: If True, execute Modified Sage–Husa Adaptive Kalman Filter stage.
        filter_config: Optional FilterConfig instance (uses defaults if None).
        filtered_samples_output: Optional path to export aligned raw/filtered samples CSV.
        filter_config_output: Optional path to export filter configuration metadata JSON.
        enable_quantize: If True, execute Modified Adaptive Dual-Threshold Quantization stage.
        quantize_config: Optional QuantizationConfig instance (uses defaults if None).
        quantized_samples_output: Optional path to export aligned sample-level quantization CSV.
        quantized_segments_output: Optional path to export segment thresholds/statistics CSV.
        quantized_bitstreams_output: Optional path to export encoded bitstreams CSV.
        quantize_config_output: Optional path to export quantization configuration metadata JSON.
        quantize_metrics_output: Optional path to export KAR and level agreement metrics CSV.
        quantized_xlsx_output: Optional path to export companion Excel workbook (.xlsx) preserving leading zeros.
        quantize_figure_prefix: Optional file prefix to export quantization KAR figures.
        return_quant_result: If True, return (results, figure_paths, quant_result). Default False.

    Returns:
        tuple: (results, figure_paths) by default, or (results, figure_paths, quant_result) if return_quant_result is True.
    """
    in_path = Path(input_path)
    raw_data = load_rssi_workbook(in_path)

    results: list[dict[str, Any]] = []

    # If quantization is requested, filtering is automatically required as a prerequisite
    effective_filter = enable_filter or enable_quantize

    if not effective_filter:
        # Default correlation-only behavior (strictly backward compatible)
        for col1, col2, pair_name in TARGET_PAIRS:
            series1 = raw_data[col1]
            series2 = raw_data[col2]
            count = len(series1)
            rho = pearson_correlation(series1, series2)

            results.append(
                {
                    "pair": pair_name,
                    "sample_count": count,
                    "correlation_coefficient": rho,
                    "data_kind": data_kind,
                }
            )

        if output_path is not None:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, mode="w", newline="", encoding="utf-8") as f:
                fieldnames = ["pair", "sample_count", "correlation_coefficient", "data_kind"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in results:
                    writer.writerow(row)

        fig_paths = None
        if figure_prefix is not None:
            fig_paths = plot_combined_correlation_figure(
                data=raw_data,
                results=results,
                prefix_path=figure_prefix,
            )

        if return_quant_result:
            return results, fig_paths, None
        return results, fig_paths

    # Filtering Stage Enabled (Modified Sage–Husa Adaptive Kalman Filter)
    cfg = filter_config if filter_config is not None else FilterConfig()
    filtered_data = filter_rssi_channels(raw_data, config=cfg)

    for col1, col2, pair_name in TARGET_PAIRS:
        raw_s1 = raw_data[col1]
        raw_s2 = raw_data[col2]
        filt_s1 = filtered_data[col1]
        filt_s2 = filtered_data[col2]
        count = len(raw_s1)

        raw_rho = pearson_correlation(raw_s1, raw_s2)
        filt_rho = pearson_correlation(filt_s1, filt_s2)
        delta = filt_rho - raw_rho

        results.append(
            {
                "pair": pair_name,
                "sample_count": count,
                "correlation_coefficient": filt_rho,
                "raw_correlation": raw_rho,
                "filtered_correlation": filt_rho,
                "correlation_delta": delta,
                "data_kind": data_kind,
            }
        )

    # Export correlation results CSV
    if output_path is not None:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, mode="w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "pair",
                "sample_count",
                "raw_correlation",
                "filtered_correlation",
                "correlation_delta",
                "data_kind",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in results:
                csv_row = {k: row[k] for k in fieldnames}
                writer.writerow(csv_row)

    # Export aligned raw and filtered samples CSV
    if filtered_samples_output is not None:
        export_aligned_samples_csv(
            raw_data=raw_data,
            filtered_data=filtered_data,
            output_path=filtered_samples_output,
        )

    # Export configuration metadata JSON
    if filter_config_output is not None:
        export_filter_metadata_json(
            filter_config=cfg,
            output_path=filter_config_output,
            extra_metadata={
                "data_kind": data_kind,
                "input_file": str(in_path),
                "samples_count": len(raw_data["Alice"]),
            },
        )

    # Export comparison figure
    fig_paths = None
    if figure_prefix is not None:
        fig_paths = plot_filtering_comparison_figure(
            raw_data=raw_data,
            filtered_data=filtered_data,
            results=results,
            prefix_path=figure_prefix,
        )

    # Quantization Stage (Modified Adaptive Dual-Threshold Quantization)
    quant_res: ChannelQuantizationResult | None = None
    if enable_quantize:
        q_cfg = quantize_config if quantize_config is not None else QuantizationConfig()
        quant_res = quantize_channels(channels=filtered_data, config=q_cfg)

        if quantized_samples_output is not None:
            export_quantized_samples_csv(
                filtered_data=filtered_data,
                quant_result=quant_res,
                output_path=quantized_samples_output,
            )

        if quantized_segments_output is not None:
            export_quantized_segments_csv(
                quant_result=quant_res,
                output_path=quantized_segments_output,
            )

        if quantized_bitstreams_output is not None:
            export_quantized_bitstreams_csv(
                quant_result=quant_res,
                output_path=quantized_bitstreams_output,
            )

        if quantize_metrics_output is not None:
            export_quantization_metrics_csv(
                quant_result=quant_res,
                output_path=quantize_metrics_output,
            )

        if quantize_config_output is not None:
            export_quantization_metadata_json(
                quant_result=quant_res,
                output_path=quantize_config_output,
                extra_metadata={
                    "data_kind": data_kind,
                    "input_file": str(in_path),
                },
            )

        if quantized_xlsx_output is not None:
            export_quantized_workbook_xlsx(
                filtered_data=filtered_data,
                quant_result=quant_res,
                output_path=quantized_xlsx_output,
            )

        effective_quant_fig_prefix = quantize_figure_prefix
        if effective_quant_fig_prefix is None and figure_prefix is not None:
            p_str = str(figure_prefix)
            if p_str.endswith("_filtered"):
                effective_quant_fig_prefix = p_str[: -len("_filtered")] + "_quantization"
            else:
                effective_quant_fig_prefix = f"{p_str}_quantization"

        if effective_quant_fig_prefix is not None:
            q_fig_paths = plot_kar_comparison_figure(
                quant_result=quant_res,
                prefix_path=effective_quant_fig_prefix,
            )
            quant_res.figure_paths = q_fig_paths

    if return_quant_result:
        return results, fig_paths, quant_res

    return results, fig_paths



def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Compute Pearson correlation for RSSI datasets with optional Modified Sage–Husa Adaptive Kalman Filter and Modified ADQ quantization."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to input Excel workbook (.xlsx).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to export resulting CSV file (optional).",
    )
    parser.add_argument(
        "--figure-prefix",
        default=None,
        help="Path prefix to export figures in PNG (300 dpi) and PDF (optional).",
    )
    parser.add_argument(
        "--data-kind",
        default="dummy",
        help="Label for data kind (default: dummy).",
    )

    # Filtering Options
    filter_group = parser.add_argument_group("Modified Sage–Husa Adaptive Kalman Filter Options")
    filter_group.add_argument(
        "--filter",
        action="store_true",
        help="Enable Modified Sage–Husa Adaptive Kalman Filter (MSHKF) stage (PA.pdf Section 3.2.2).",
    )
    filter_group.add_argument(
        "--filter-b",
        type=float,
        default=0.99,
        help="Forgetting factor b (default: 0.99, selected within PA.pdf range of 0.95 to 0.999).",
    )
    filter_group.add_argument(
        "--filter-q",
        type=float,
        default=0.1,
        help="Fixed process noise covariance Q in dBm^2 (default: 0.1, software-validation assumption).",
    )
    filter_group.add_argument(
        "--filter-r0",
        type=float,
        default=1.0,
        help="Initial measurement noise covariance R0 in dBm^2 (default: 1.0, software-validation assumption).",
    )
    filter_group.add_argument(
        "--filter-p0",
        type=float,
        default=1.0,
        help="Initial error covariance P0 in dBm^2 (default: 1.0, software-validation assumption).",
    )
    filter_group.add_argument(
        "--filter-d0",
        type=float,
        default=1.0,
        help="Initial adaptive weight D0 (default: 1.0 per PA.pdf Eq 3.10).",
    )
    filter_group.add_argument(
        "--filtered-samples-output",
        default=None,
        help="Path to export aligned raw and filtered samples CSV (optional).",
    )
    filter_group.add_argument(
        "--filter-config-output",
        default=None,
        help="Path to export filter configuration metadata JSON (optional).",
    )

    # Quantization Options
    quant_group = parser.add_argument_group("Modified Adaptive Dual-Threshold Quantization Options")
    quant_group.add_argument(
        "--quantize",
        action="store_true",
        help="Enable Modified Adaptive Dual-Threshold Quantization (MADQ) stage (PA.pdf Section 3.2.3).",
    )
    quant_group.add_argument(
        "--quantize-window",
        type=int,
        default=50,
        help="Segment window size in samples (default: 50, provisional software-validation setting).",
    )
    quant_group.add_argument(
        "--quantize-alpha",
        type=float,
        default=0.5,
        help="Threshold multiplier alpha (default: 0.5, provisional software-validation setting).",
    )
    quant_group.add_argument(
        "--quantized-samples-output",
        default=None,
        help="Path to export aligned sample-level quantization CSV (optional).",
    )
    quant_group.add_argument(
        "--quantized-segments-output",
        default=None,
        help="Path to export segment thresholds and statistics CSV (optional).",
    )
    quant_group.add_argument(
        "--quantized-bitstreams-output",
        default=None,
        help="Path to export encoded bitstreams CSV (optional).",
    )
    quant_group.add_argument(
        "--quantize-config-output",
        default=None,
        help="Path to export quantization configuration metadata JSON (optional).",
    )
    quant_group.add_argument(
        "--quantize-metrics-output",
        default=None,
        help="Path to export KAR and level agreement metrics CSV (optional).",
    )
    quant_group.add_argument(
        "--quantized-xlsx-output",
        default=None,
        help="Path to export companion Excel workbook (.xlsx) preserving leading zeros (optional).",
    )
    quant_group.add_argument(
        "--quantize-figure-prefix",
        default=None,
        help="Path prefix to export quantization KAR figures in PNG (300 dpi) and PDF (optional; defaults to figure-prefix with '_quantization' suffix).",
    )

    args = parser.parse_args(argv)


    print("=" * 70)
    print("RSSI SECRET KEY GENERATION (SKG) - ANALYSIS PIPELINE")
    print(f"[STATUS] Data Kind:         {args.data_kind.upper()}")
    filter_active = args.filter or args.quantize
    filter_desc = "ENABLED (Modified Sage–Husa AKF)" if filter_active else "DISABLED (Raw Correlation Only)"
    if args.quantize and not args.filter:
        filter_desc += " [prerequisite for quantization]"
    print(f"[STATUS] Filtering Mode:    {filter_desc}")
    quant_desc = "ENABLED (Modified ADQ)" if args.quantize else "DISABLED"
    print(f"[STATUS] Quantization Mode: {quant_desc}")
    print("[NOTICE] Software validation only; empirical channel probing is postponed.")
    print("=" * 70)

    filter_cfg: FilterConfig | None = None
    if filter_active:
        try:
            filter_cfg = FilterConfig(
                b=args.filter_b,
                d0=args.filter_d0,
                q=args.filter_q,
                r0=args.filter_r0,
                p0=args.filter_p0,
            )
        except ValueError as cfg_err:
            print(f"\n[ERROR] Invalid filter configuration: {cfg_err}", file=sys.stderr)
            return 1

    quant_cfg: QuantizationConfig | None = None
    if args.quantize:
        try:
            quant_cfg = QuantizationConfig(
                window_size=args.quantize_window,
                alpha=args.quantize_alpha,
            )
        except (ValueError, TypeError) as qcfg_err:
            print(f"\n[ERROR] Invalid quantization configuration: {qcfg_err}", file=sys.stderr)
            return 1

    try:
        ret_val = run_correlation_analysis(
            input_path=args.input,
            output_path=args.output,
            figure_prefix=args.figure_prefix,
            data_kind=args.data_kind,
            enable_filter=args.filter,
            filter_config=filter_cfg,
            filtered_samples_output=args.filtered_samples_output,
            filter_config_output=args.filter_config_output,
            enable_quantize=args.quantize,
            quantize_config=quant_cfg,
            quantized_samples_output=args.quantized_samples_output,
            quantized_segments_output=args.quantized_segments_output,
            quantized_bitstreams_output=args.quantized_bitstreams_output,
            quantize_config_output=args.quantize_config_output,
            quantize_metrics_output=args.quantize_metrics_output,
            quantized_xlsx_output=args.quantized_xlsx_output,
            quantize_figure_prefix=args.quantize_figure_prefix,
            return_quant_result=True,
        )
        results, fig_paths, quant_res = ret_val  # type: ignore[misc]
    except Exception as err:
        print(f"\n[ERROR] Analysis failed: {err}", file=sys.stderr)
        return 1

    if not filter_active:
        print("\nCalculated Pearson Correlation Results (Zero Lag):")
        print("-" * 70)
        print(f"{'Pair':<20} | {'Samples':<8} | {'Pearson (rho)':<18} | {'Data Kind':<10}")
        print("-" * 70)
        for r in results:
            rho_val = float(r["correlation_coefficient"])
            print(
                f"{r['pair']:<20} | {r['sample_count']:<8} | {rho_val:<18.10f} | {r['data_kind']:<10}"
            )
        print("-" * 70)
    else:
        print("\nCalculated Pearson Correlation Results (Before vs After MSHKF Filtering):")
        print("-" * 75)
        print(
            f"{'Pair':<20} | {'Samples':<8} | {'Raw (rho)':<12} | {'Filtered (rho)':<15} | {'Delta':<10}"
        )
        print("-" * 75)
        for r in results:
            raw_rho = float(r["raw_correlation"])
            filt_rho = float(r["filtered_correlation"])
            delta = float(r["correlation_delta"])
            print(
                f"{r['pair']:<20} | {r['sample_count']:<8} | {raw_rho:<+12.6f} | {filt_rho:<+15.6f} | {delta:<+10.6f}"
            )
        print("-" * 75)

    if quant_res is not None:
        print("\nCalculated Quantization & Key Agreement Rate (KAR) Results (PA.pdf Section 3.2.3 & 3.2.8.c):")
        print("-" * 95)
        print(
            f"{'Pair':<20} | {'Samples':<8} | {'Level Agreement':<16} | {'2-bit Gray KAR':<16} | {'4-bit KAR':<14} | {'Bits (2b/4b)':<12}"
        )
        print("-" * 95)
        for pm in quant_res.pair_metrics:
            lvl_agr = f"{float(pm['level_agreement_rate']):.4f}%"
            k2 = f"{float(pm['kar_2bit']):.4f}%"
            k4 = f"{float(pm['kar_4bit']):.4f}%"
            bits = f"{pm['bit_count_2bit']} / {pm['bit_count_4bit']}"
            print(
                f"{pm['pair']:<20} | {pm['sample_count']:<8} | {lvl_agr:<16} | {k2:<16} | {k4:<14} | {bits:<12}"
            )
        print("-" * 95)

        print("\nQuantization Level Distributions per Channel (ddof=0, non-overlapping W=50, alpha=0.5):")
        print("-" * 95)
        print(
            f"{'Channel':<15} | {'Total':<6} | {'Level 0 (x < q-)':<20} | {'Level 1 (q- <= x <= q+)':<25} | {'Level 2 (x > q+)':<20}"
        )
        print("-" * 95)
        for ch, freqs in quant_res.level_frequencies.items():
            c0 = f"{freqs[0]['count']} ({float(freqs[0]['percentage']):5.2f}%)"
            c1 = f"{freqs[1]['count']} ({float(freqs[1]['percentage']):5.2f}%)"
            c2 = f"{freqs[2]['count']} ({float(freqs[2]['percentage']):5.2f}%)"
            print(
                f"{ch:<15} | {quant_res.sample_count:<6} | {c0:<20} | {c1:<25} | {c2:<20}"
            )
        print("-" * 95)

    if args.output:
        print(f"\n[OUTPUT] Correlation CSV exported to:              {args.output}")

    if args.filtered_samples_output:
        print(f"[OUTPUT] Aligned raw/filtered samples CSV:         {args.filtered_samples_output}")

    if args.filter_config_output:
        print(f"[OUTPUT] Filter configuration metadata JSON:       {args.filter_config_output}")

    if args.quantized_samples_output:
        print(f"[OUTPUT] Aligned quantized samples CSV:            {args.quantized_samples_output}")

    if args.quantized_segments_output:
        print(f"[OUTPUT] Quantization segment thresholds CSV:      {args.quantized_segments_output}")

    if args.quantized_bitstreams_output:
        print(f"[OUTPUT] Encoded bitstreams CSV:                   {args.quantized_bitstreams_output}")

    if args.quantize_metrics_output:
        print(f"[OUTPUT] Quantization metrics CSV:                 {args.quantize_metrics_output}")

    if args.quantize_config_output:
        print(f"[OUTPUT] Quantization metadata JSON:               {args.quantize_config_output}")

    if args.quantized_xlsx_output:
        print(f"[OUTPUT] Quantized Excel workbook (.xlsx):         {args.quantized_xlsx_output}")
        print("         (Excel users should open .xlsx rather than .csv to preserve leading zeros in '00' and '01')")

    if fig_paths is not None:
        png_p, pdf_p = fig_paths
        print(f"[OUTPUT] Figure plot (PNG 300 dpi) exported to:    {png_p}")
        print(f"[OUTPUT] Figure plot (PDF) exported to:            {pdf_p}")

    if quant_res is not None and quant_res.figure_paths is not None:
        q_png_p, q_pdf_p = quant_res.figure_paths
        print(f"[OUTPUT] Quantization KAR figure (PNG 300 dpi):    {q_png_p}")
        print(f"[OUTPUT] Quantization KAR figure (PDF):            {q_pdf_p}")

    return 0



if __name__ == "__main__":
    raise SystemExit(main())
