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
    plot_prbs_kar_comparison_figure,
    plot_privacy_amplification_figure,
    plot_reconciliation_figure,
    plot_shared_bch_figure,
)
from rssi_skg.privacy_amplification import (
    MultiPathPrivacyAmplificationResult,
    PA_PATHS,
    PrivacyAmplificationConfig,
    SEGMENT_SIZE_BITS,
    amplify_privacy_all_paths,
    export_pa_config_json,
    export_pa_keys_csv,
    export_pa_metrics_csv,
    export_pa_workbook_xlsx,
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
from rssi_skg.prbs import (
    MultiChannelPRBSResult,
    PRBSConfig,
    expand_channels_prbs,
    export_prbs_bitstreams_csv,
    export_prbs_config_json,
    export_prbs_metrics_csv,
    export_prbs_samples_csv,
    export_prbs_workbook_xlsx,
)
from rssi_skg.reconciliation import (
    DEFAULT_BCH_CODE,
    DEFAULT_BCH_CODE_2BIT,
    DEFAULT_BCH_CODE_4BIT,
    GLOBAL_BCH_CODE,
    INTERLEAVING_STATUS,
    MultiPathReconciliationResult,
    ReconciliationConfig,
    export_reconciliation_blocks_csv,
    export_reconciliation_config_json,
    export_reconciliation_metrics_csv,
    export_reconciliation_workbook_xlsx,
    reconcile_all_paths,
)
from rssi_skg.nist import (
    KeyRandomnessResult,
    MultiPathNISTResult,
    NISTConfig,
    NISTTestResult,
    evaluate_pa_keys_randomness,
    export_nist_config_json,
    export_nist_metrics_csv,
)
from rssi_skg.kgr import (
    BCH_CACHE_POLICY_DESC,
    KGRConfig,
    MultiPathKGRResult,
    PathKGRResult,
    RESEARCH_DISCLAIMER_KGR,
    TIMER_END_BOUNDARY,
    TIMER_START_BOUNDARY,
    export_evaluation_workbook_xlsx,
    export_kgr_config_json,
    export_kgr_metrics_csv,
    measure_multipath_kgr,
)




class ObsoleteReconciliationFlagAction(argparse.Action):
    """Action that rejects obsolete reconciliation CLI flags with actionable migration instructions."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        flag = option_string or "This flag"
        if flag == "--reconcile-keys-output":
            parser.error(
                f"'{flag}' is obsolete. Post-reconciliation SHA-256 privacy amplification (candidate-key "
                "derivation) has been removed from BCH reconciliation scope. Privacy amplification is a separate "
                "future stage requiring a separate request. Please run '--reconcile' without candidate-key options."
            )
        parser.error(
            f"'{flag}' is obsolete. Configured BCH codes are used automatically "
            f"(2-bit: BCH{DEFAULT_BCH_CODE_2BIT}, 4-bit: BCH{DEFAULT_BCH_CODE_4BIT}, interleaving OFF). "
            "Please use '--reconcile' without mode or shared flags."
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
    enable_prbs: bool = False,
    prbs_config: PRBSConfig | None = None,
    prbs_samples_output: str | Path | None = None,
    prbs_bitstreams_output: str | Path | None = None,
    prbs_metrics_output: str | Path | None = None,
    prbs_config_output: str | Path | None = None,
    prbs_xlsx_output: str | Path | None = None,
    prbs_figure_prefix: str | Path | None = None,
    return_prbs_result: bool = False,
    enable_reconcile: bool = False,
    reconcile_config: ReconciliationConfig | None = None,
    reconcile_metrics_output: str | Path | None = None,
    reconcile_blocks_output: str | Path | None = None,
    reconcile_config_output: str | Path | None = None,
    reconciled_xlsx_output: str | Path | None = None,
    reconcile_figure_prefix: str | Path | None = None,
    return_reconcile_result: bool = False,
    enable_pa: bool = False,
    pa_config: PrivacyAmplificationConfig | None = None,
    pa_metrics_output: str | Path | None = None,
    pa_keys_output: str | Path | None = None,
    reconcile_keys_output: str | Path | None = None,
    pa_config_output: str | Path | None = None,
    pa_xlsx_output: str | Path | None = None,
    pa_figure_prefix: str | Path | None = None,
    return_pa_result: bool = False,
    enable_nist: bool = False,
    nist_config: NISTConfig | None = None,
    nist_metrics_output: str | Path | None = None,
    nist_config_output: str | Path | None = None,
    return_nist_result: bool = False,
    enable_kgr: bool = False,
    kgr_config: KGRConfig | None = None,
    kgr_metrics_output: str | Path | None = None,
    kgr_config_output: str | Path | None = None,
    evaluation_xlsx_output: str | Path | None = None,
    return_kgr_result: bool = False,
) -> Any:
    """Execute correlation analysis on the given workbook, optionally filtering, quantizing, expanding via PRBS, reconciling, and saving artifacts.

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
        enable_prbs: If True, execute per-sample PRBS bit expansion stage (PA.pdf Section 3.2.4).
        prbs_config: Optional PRBSConfig instance (uses defaults if None).
        prbs_samples_output: Optional path to export per-sample PRBS expansion CSV.
        prbs_bitstreams_output: Optional path to export concatenated PRBS bitstreams CSV.
        prbs_metrics_output: Optional path to export before/after PRBS KAR comparison metrics CSV.
        prbs_config_output: Optional path to export PRBS configuration metadata JSON.
        prbs_xlsx_output: Optional path to export companion PRBS Excel workbook (.xlsx).
        prbs_figure_prefix: Optional file prefix to export PRBS KAR comparison figures.
        return_prbs_result: If True, return (results, figure_paths, quant_result, prbs_result). Default False.
        enable_reconcile: If True, execute BCH information reconciliation and SHA-256 key extraction.
        reconcile_config: Optional ReconciliationConfig instance (uses calibrated defaults if None).
        reconcile_metrics_output: Optional path to export reconciliation metrics CSV.
        reconcile_blocks_output: Optional path to export per-block reconciliation details CSV.
        reconcile_config_output: Optional path to export reconciliation configuration metadata JSON.
        reconciled_xlsx_output: Optional path to export companion reconciliation Excel workbook (.xlsx).
        reconcile_figure_prefix: Optional file prefix to export reconciliation comparison figures.
        return_reconcile_result: If True, return (results, figure_paths, quant_result, prbs_result, reconcile_result). Default False.

    Returns:
        tuple: (results, figure_paths) by default,
               (results, figure_paths, quant_result) if return_quant_result is True,
               (results, figure_paths, quant_result, prbs_result) if return_prbs_result is True,
               (results, figure_paths, quant_result, prbs_result, reconcile_result) if return_reconcile_result is True.
    """
    in_path = Path(input_path)
    raw_data = load_rssi_workbook(in_path)

    results: list[dict[str, Any]] = []

    # Automatic prerequisite chaining: KGR requires NIST, NIST requires PA, PA requires Reconcile, Reconcile requires PRBS, PRBS requires Quantization, Quantization requires Filtering
    effective_kgr = enable_kgr
    effective_nist = enable_nist or effective_kgr
    effective_pa = enable_pa or effective_nist
    effective_reconcile = enable_reconcile or effective_pa
    effective_prbs = enable_prbs or effective_reconcile
    effective_quantize = enable_quantize or effective_prbs
    effective_filter = enable_filter or effective_quantize

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

        if return_kgr_result:
            return results, fig_paths, None, None, None, None, None, None
        if return_nist_result:
            return results, fig_paths, None, None, None, None, None
        if return_pa_result:
            return results, fig_paths, None, None, None, None
        if return_reconcile_result:
            return results, fig_paths, None, None, None
        if return_prbs_result:
            return results, fig_paths, None, None
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
    if effective_quantize:
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

    # PRBS Bit Expansion Stage (Galois XOR-LFSR per PA.pdf Section 3.2.4)
    prbs_res: MultiChannelPRBSResult | None = None
    if effective_prbs and quant_res is not None:
        p_cfg = prbs_config if prbs_config is not None else PRBSConfig()
        prbs_res = expand_channels_prbs(quant_result=quant_res, config=p_cfg)

        if prbs_samples_output is not None:
            export_prbs_samples_csv(
                prbs_result=prbs_res,
                output_path=prbs_samples_output,
            )

        if prbs_bitstreams_output is not None:
            export_prbs_bitstreams_csv(
                prbs_result=prbs_res,
                output_path=prbs_bitstreams_output,
            )

        if prbs_metrics_output is not None:
            export_prbs_metrics_csv(
                prbs_result=prbs_res,
                output_path=prbs_metrics_output,
            )

        if prbs_config_output is not None:
            export_prbs_config_json(
                prbs_result=prbs_res,
                output_path=prbs_config_output,
                extra_metadata={
                    "data_kind": data_kind,
                    "input_file": str(in_path),
                },
            )

        if prbs_xlsx_output is not None:
            export_prbs_workbook_xlsx(
                prbs_result=prbs_res,
                output_path=prbs_xlsx_output,
            )

        effective_prbs_fig_prefix = prbs_figure_prefix
        if effective_prbs_fig_prefix is None and figure_prefix is not None:
            p_str = str(figure_prefix)
            if p_str.endswith("_filtered"):
                effective_prbs_fig_prefix = p_str[: -len("_filtered")] + "_prbs_kar"
            else:
                effective_prbs_fig_prefix = f"{p_str}_prbs_kar"

        if effective_prbs_fig_prefix is not None:
            p_fig_paths = plot_prbs_kar_comparison_figure(
                prbs_metrics=prbs_res,
                prefix_path=effective_prbs_fig_prefix,
            )
            prbs_res.figure_paths = p_fig_paths

    # Information Reconciliation & SHA-256 Privacy Amplification (PA.pdf Sections 3.2.5–3.2.6)
    reconcile_res: MultiPathReconciliationResult | None = None
    if effective_reconcile and quant_res is not None and prbs_res is not None:
        r_cfg = reconcile_config if reconcile_config is not None else ReconciliationConfig()
        reconcile_res = reconcile_all_paths(
            quant_result=quant_res,
            prbs_result=prbs_res,
            config=r_cfg,
        )

        if reconcile_metrics_output is not None:
            export_reconciliation_metrics_csv(
                reconcile_result=reconcile_res,
                output_path=reconcile_metrics_output,
            )

        if reconcile_blocks_output is not None:
            export_reconciliation_blocks_csv(
                reconcile_result=reconcile_res,
                output_path=reconcile_blocks_output,
            )

        if reconcile_config_output is not None:
            export_reconciliation_config_json(
                reconcile_result=reconcile_res,
                output_path=reconcile_config_output,
                extra_metadata={
                    "data_kind": data_kind,
                    "input_file": str(in_path),
                },
            )



        if reconciled_xlsx_output is not None:
            export_reconciliation_workbook_xlsx(
                reconcile_result=reconcile_res,
                output_path=reconciled_xlsx_output,
            )

        effective_rec_fig_prefix = reconcile_figure_prefix
        if effective_rec_fig_prefix is None and figure_prefix is not None:
            p_str = str(figure_prefix)
            sub_suffix = "_reconciliation"
            if p_str.endswith("_filtered"):
                effective_rec_fig_prefix = p_str[: -len("_filtered")] + sub_suffix
            else:
                effective_rec_fig_prefix = f"{p_str}{sub_suffix}"

        if effective_rec_fig_prefix is not None:
            rec_fig_paths = plot_reconciliation_figure(
                reconcile_result=reconcile_res,
                prefix_path=effective_rec_fig_prefix,
            )
            reconcile_res.figure_paths = rec_fig_paths

    # Privacy Amplification Stage (PA.pdf Section 3.2.6, Equations 3.37–3.53)
    pa_res: MultiPathPrivacyAmplificationResult | None = None
    if effective_pa and reconcile_res is not None:
        pa_cfg = pa_config if pa_config is not None else PrivacyAmplificationConfig()
        pa_res = amplify_privacy_all_paths(
            reconcile_result=reconcile_res,
            config=pa_cfg,
        )

        if pa_metrics_output is not None:
            export_pa_metrics_csv(
                pa_result=pa_res,
                output_path=pa_metrics_output,
            )

        effective_keys_out = pa_keys_output if pa_keys_output is not None else reconcile_keys_output
        if effective_keys_out is not None:
            export_pa_keys_csv(
                pa_result=pa_res,
                output_path=effective_keys_out,
            )

        if pa_config_output is not None:
            export_pa_config_json(
                pa_result=pa_res,
                output_path=pa_config_output,
                extra_metadata={
                    "data_kind": data_kind,
                    "input_file": str(in_path),
                },
            )

        if pa_xlsx_output is not None:
            export_pa_workbook_xlsx(
                pa_result=pa_res,
                output_path=pa_xlsx_output,
            )

        effective_pa_fig_prefix = pa_figure_prefix
        if effective_pa_fig_prefix is None and figure_prefix is not None:
            p_str = str(figure_prefix)
            sub_suffix = "_pa_comparison"
            if p_str.endswith("_filtered"):
                effective_pa_fig_prefix = p_str[: -len("_filtered")] + sub_suffix
            else:
                effective_pa_fig_prefix = f"{p_str}{sub_suffix}"

        if effective_pa_fig_prefix is not None:
            pa_fig_paths = plot_privacy_amplification_figure(
                pa_result=pa_res,
                prefix_path=effective_pa_fig_prefix,
            )
            pa_res.figure_paths = pa_fig_paths

    # NIST SP 800-22 Randomness Testing (PA.pdf Section 3.2.8.d & Eqs 3.65–3.73)
    nist_res: MultiPathNISTResult | None = None
    if effective_nist and pa_res is not None:
        n_cfg = nist_config if nist_config is not None else NISTConfig()
        nist_res = evaluate_pa_keys_randomness(pa_res, config=n_cfg)

        if nist_metrics_output is not None:
            export_nist_metrics_csv(
                nist_result=nist_res,
                output_path=nist_metrics_output,
            )

        if nist_config_output is not None:
            export_nist_config_json(
                nist_result=nist_res,
                output_path=nist_config_output,
                extra_metadata={
                    "data_kind": data_kind,
                    "input_file": str(in_path),
                },
            )

    # Key Generation Rate (KGR) Measurement (PA.pdf Section 3.2.8.b & Eq 3.63)
    kgr_res: MultiPathKGRResult | None = None
    if effective_kgr:
        k_cfg = kgr_config if kgr_config is not None else KGRConfig()
        kgr_res = measure_multipath_kgr(
            raw_data=raw_data,
            nist_result=nist_res,
            filter_config=filter_config,
            quant_config=quantize_config,
            prbs_config=prbs_config,
            recon_config=reconcile_config,
            pa_config=pa_config,
            nist_config=nist_config,
            config=k_cfg,
        )

        if kgr_metrics_output is not None:
            export_kgr_metrics_csv(
                kgr_result=kgr_res,
                output_path=kgr_metrics_output,
            )

        if kgr_config_output is not None:
            export_kgr_config_json(
                kgr_result=kgr_res,
                output_path=kgr_config_output,
                extra_metadata={
                    "data_kind": data_kind,
                    "input_file": str(in_path),
                },
            )

    # Companion Multi-Sheet Evaluation Workbook (.xlsx)
    if evaluation_xlsx_output is not None and nist_res is not None and kgr_res is not None:
        export_evaluation_workbook_xlsx(
            nist_result=nist_res,
            kgr_result=kgr_res,
            output_path=evaluation_xlsx_output,
        )

    if return_kgr_result:
        return results, fig_paths, quant_res, prbs_res, reconcile_res, pa_res, nist_res, kgr_res

    if return_nist_result:
        return results, fig_paths, quant_res, prbs_res, reconcile_res, pa_res, nist_res

    if return_pa_result:
        return results, fig_paths, quant_res, prbs_res, reconcile_res, pa_res

    if return_reconcile_result:
        return results, fig_paths, quant_res, prbs_res, reconcile_res

    if return_prbs_result:
        return results, fig_paths, quant_res, prbs_res

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

    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    is_pa_or_recon_requested = any(
        arg in effective_argv for arg in ("--privacy-amplify", "--pa", "--reconcile")
    )

    parser = argparse.ArgumentParser(
        description="Compute Pearson correlation for RSSI datasets with optional Modified Sage–Husa Adaptive Kalman Filter, Modified ADQ quantization, PRBS expansion, BCH reconciliation, and Privacy Amplification."
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

    # PRBS Expansion Options
    prbs_group = parser.add_argument_group("Per-Sample PRBS Bit Expansion Options (PA.pdf Section 3.2.4)")
    prbs_group.add_argument(
        "--prbs",
        action="store_true",
        help="Enable per-sample PRBS bit expansion stage (PA.pdf Section 3.2.4, Equations 3.24-3.26).",
    )
    prbs_group.add_argument(
        "--prbs-samples-output",
        default=None,
        help="Path to export per-sample PRBS expansion CSV (optional).",
    )
    prbs_group.add_argument(
        "--prbs-bitstreams-output",
        default=None,
        help="Path to export concatenated PRBS bitstreams CSV (optional).",
    )
    prbs_group.add_argument(
        "--prbs-metrics-output",
        default=None,
        help="Path to export before/after PRBS KAR comparison metrics CSV (optional).",
    )
    prbs_group.add_argument(
        "--prbs-config-output",
        default=None,
        help="Path to export PRBS configuration metadata JSON (optional).",
    )
    prbs_group.add_argument(
        "--prbs-xlsx-output",
        default=None,
        help="Path to export companion PRBS Excel workbook (.xlsx) preserving leading zeros and long bitstrings (optional).",
    )
    prbs_group.add_argument(
        "--prbs-figure-prefix",
        default=None,
        help="Path prefix to export PRBS KAR comparison figures in PNG (300 dpi) and PDF (optional; defaults to figure-prefix with '_prbs_kar' suffix).",
    )

    # Reconciliation Options
    reconcile_group = parser.add_argument_group("BCH Information Reconciliation (PA.pdf Section 3.2.5)")
    reconcile_group.add_argument(
        "--reconcile",
        action="store_true",
        help="Enable BCH Information Reconciliation (PA.pdf Section 3.2.5).",
    )
    reconcile_group.add_argument(
        "--reconcile-seed",
        type=int,
        default=42,
        help="Random seed for Alice's independent k-bit random message generation (default: 42).",
    )
    reconcile_group.add_argument(
        "--reconcile-metrics-output",
        default=None,
        help="Path to export reconciliation summary metrics CSV (optional).",
    )
    reconcile_group.add_argument(
        "--reconcile-blocks-output",
        default=None,
        help="Path to export per-block reconciliation details CSV (optional).",
    )
    reconcile_group.add_argument(
        "--reconcile-config-output",
        default=None,
        help="Path to export reconciliation configuration metadata JSON (optional).",
    )
    if is_pa_or_recon_requested:
        reconcile_group.add_argument(
            "--reconcile-keys-output",
            default=None,
            help="Path to export candidate keys CSV/JSON (alias for --pa-keys-output).",
        )
    else:
        reconcile_group.add_argument(
            "--reconcile-keys-output",
            nargs="?",
            action=ObsoleteReconciliationFlagAction,
            help=argparse.SUPPRESS,
        )
    reconcile_group.add_argument(
        "--reconciled-xlsx-output",
        default=None,
        help="Path to export companion reconciliation Excel workbook (.xlsx) preserving leading zeros (optional).",
    )
    reconcile_group.add_argument(
        "--reconcile-figure-prefix",
        default=None,
        help="Path prefix to export reconciliation comparison figures in PNG (300 dpi) and PDF (optional; defaults to figure-prefix with '_reconciliation' or '_shared_bch' suffix).",
    )
    reconcile_group.add_argument(
        "--reconcile-shared",
        nargs=0,
        action=ObsoleteReconciliationFlagAction,
        help=argparse.SUPPRESS,
    )
    reconcile_group.add_argument(
        "--reconcile-mode",
        nargs="?",
        action=ObsoleteReconciliationFlagAction,
        help=argparse.SUPPRESS,
    )

    # Privacy Amplification Options (PA.pdf Section 3.2.6)
    pa_group = parser.add_argument_group("Privacy Amplification (PA.pdf Section 3.2.6)")
    pa_group.add_argument(
        "--privacy-amplify",
        "--pa",
        action="store_true",
        help="Enable bit-level SHA-256 Privacy Amplification stage (PA.pdf Section 3.2.6).",
    )
    pa_group.add_argument(
        "--pa-metrics-output",
        default=None,
        help="Path to export privacy amplification summary metrics CSV (optional).",
    )
    pa_group.add_argument(
        "--pa-keys-output",
        default=None,
        help="Path to export 256-bit channel secret keys CSV (optional).",
    )
    pa_group.add_argument(
        "--pa-config-output",
        default=None,
        help="Path to export privacy amplification configuration metadata JSON (optional).",
    )
    pa_group.add_argument(
        "--pa-xlsx-output",
        default=None,
        help="Path to export companion privacy amplification Excel workbook (.xlsx) preserving leading zeros (optional).",
    )
    pa_group.add_argument(
        "--pa-figure-prefix",
        default=None,
        help="Path prefix to export privacy amplification comparison figures in PNG (300 dpi) and PDF (optional; defaults to figure-prefix with '_pa_comparison' suffix).",
    )

    # NIST SP 800-22 Randomness Evaluation Options (PA.pdf Section 3.2.8.d)
    nist_group = parser.add_argument_group("NIST Randomness Evaluation (PA.pdf Section 3.2.8.d)")
    nist_group.add_argument(
        "--nist",
        action="store_true",
        help="Enable NIST SP 800-22 Rev. 1a statistical randomness evaluation (Frequency, Runs, Approximate Entropy).",
    )
    nist_group.add_argument(
        "--nist-alpha",
        type=float,
        default=0.01,
        help="Significance level alpha for NIST tests (default: 0.01).",
    )
    nist_group.add_argument(
        "--nist-m",
        type=int,
        default=2,
        help="Block length m for Approximate Entropy test (default: 2, satisfies m < floor(log2(n))-5).",
    )
    nist_group.add_argument(
        "--nist-metrics-output",
        default=None,
        help="Path to export NIST randomness metrics CSV (optional).",
    )
    nist_group.add_argument(
        "--nist-config-output",
        default=None,
        help="Path to export NIST configuration metadata JSON (optional).",
    )

    # Key Generation Rate (KGR) Options (PA.pdf Section 3.2.8.b)
    kgr_group = parser.add_argument_group("Key Generation Rate (KGR, PA.pdf Section 3.2.8.b)")
    kgr_group.add_argument(
        "--kgr",
        action="store_true",
        help="Enable Key Generation Rate (KGR) measurement and evaluation per PA.pdf Eq (3.63).",
    )
    kgr_group.add_argument(
        "--kgr-metrics-output",
        default=None,
        help="Path to export KGR metrics CSV (optional).",
    )
    kgr_group.add_argument(
        "--kgr-config-output",
        default=None,
        help="Path to export KGR configuration metadata JSON (optional).",
    )
    kgr_group.add_argument(
        "--evaluation-xlsx-output",
        default=None,
        help="Path to export companion NIST & KGR evaluation Excel workbook (.xlsx) (optional).",
    )

    args = parser.parse_args(argv)

    kgr_active = args.kgr
    nist_active = args.nist or kgr_active
    pa_active = args.privacy_amplify or nist_active
    recon_active = args.reconcile or pa_active
    prbs_active = args.prbs or recon_active
    quant_active = args.quantize or prbs_active
    filter_active = args.filter or quant_active

    print("=" * 70)
    print("RSSI SECRET KEY GENERATION (SKG) - ANALYSIS PIPELINE")
    print(f"[STATUS] Data Kind:         {args.data_kind.upper()}")
    filter_desc = "ENABLED (Modified Sage–Husa AKF)" if filter_active else "DISABLED (Raw Correlation Only)"
    if kgr_active and not args.filter:
        filter_desc += " [prerequisite for KGR]"
    elif nist_active and not args.filter:
        filter_desc += " [prerequisite for NIST evaluation]"
    elif pa_active and not args.filter:
        filter_desc += " [prerequisite for privacy amplification]"
    elif recon_active and not args.filter:
        filter_desc += " [prerequisite for reconciliation]"
    elif prbs_active and not args.filter:
        filter_desc += " [prerequisite for PRBS]"
    elif args.quantize and not args.filter:
        filter_desc += " [prerequisite for quantization]"
    print(f"[STATUS] Filtering Mode:    {filter_desc}")

    quant_desc = "ENABLED (Modified ADQ)" if quant_active else "DISABLED"
    if kgr_active and not args.quantize:
        quant_desc += " [prerequisite for KGR]"
    elif nist_active and not args.quantize:
        quant_desc += " [prerequisite for NIST evaluation]"
    elif pa_active and not args.quantize:
        quant_desc += " [prerequisite for privacy amplification]"
    elif recon_active and not args.quantize:
        quant_desc += " [prerequisite for reconciliation]"
    elif prbs_active and not args.quantize:
        quant_desc += " [prerequisite for PRBS]"
    print(f"[STATUS] Quantization Mode: {quant_desc}")

    prbs_desc = "ENABLED (Galois XOR-LFSR, per-sample reset)" if prbs_active else "DISABLED"
    if kgr_active and not args.prbs:
        prbs_desc += " [prerequisite for KGR]"
    elif nist_active and not args.prbs:
        prbs_desc += " [prerequisite for NIST evaluation]"
    elif pa_active and not args.prbs:
        prbs_desc += " [prerequisite for privacy amplification]"
    elif recon_active and not args.prbs:
        prbs_desc += " [prerequisite for reconciliation]"
    print(f"[STATUS] PRBS Expansion:    {prbs_desc}")

    if recon_active:
        n2, k2, t2 = DEFAULT_BCH_CODE_2BIT
        n4, k4, t4 = DEFAULT_BCH_CODE_4BIT
        recon_desc = f"ENABLED (2-bit: BCH({n2},{k2},{t2}), 4-bit: BCH({n4},{k4},{t4}), Interleaving OFF)"
        if kgr_active and not args.reconcile:
            recon_desc += " [prerequisite for KGR]"
        elif nist_active and not args.reconcile:
            recon_desc += " [prerequisite for NIST evaluation]"
        elif pa_active and not args.reconcile:
            recon_desc += " [prerequisite for privacy amplification]"
    else:
        recon_desc = "DISABLED"
    print(f"[STATUS] Reconciliation:    {recon_desc}")

    pa_desc = (
        f"ENABLED (Bit-Level SHA-256 with {SEGMENT_SIZE_BITS}-bit Segmentation, 4 Paths, PA.pdf Section 3.2.6)"
        if pa_active
        else "DISABLED"
    )
    if kgr_active and not args.privacy_amplify:
        pa_desc += " [prerequisite for KGR]"
    elif nist_active and not args.privacy_amplify:
        pa_desc += " [prerequisite for NIST evaluation]"
    print(f"[STATUS] Privacy Amplification: {pa_desc}")

    nist_desc = (
        f"ENABLED (NIST SP 800-22 Rev. 1a: Monobit, Runs, ApEn m={args.nist_m}, alpha={args.nist_alpha})"
        if nist_active
        else "DISABLED"
    )
    if kgr_active and not args.nist:
        nist_desc += " [prerequisite for KGR]"
    print(f"[STATUS] NIST Randomness:   {nist_desc}")

    kgr_desc = "ENABLED (PA.pdf Section 3.2.8.b, Eq 3.63: KGR = N_bit / T bps)" if kgr_active else "DISABLED"
    print(f"[STATUS] Key Generation Rate: {kgr_desc}")
    if pa_active or nist_active or kgr_active:
        print("[NOTICE] Downstream evaluation (PA, NIST SP 800-22, KGR) is PAUSED for the 8-bit PRBS / 4-path revision")
        print("         pending 4-path key derivation architecture; running strictly under historical 2-bit configuration.")
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
    if quant_active:
        try:
            quant_cfg = QuantizationConfig(
                window_size=args.quantize_window,
                alpha=args.quantize_alpha,
            )
        except (ValueError, TypeError) as qcfg_err:
            print(f"\n[ERROR] Invalid quantization configuration: {qcfg_err}", file=sys.stderr)
            return 1

    prbs_cfg: PRBSConfig | None = None
    if prbs_active:
        prbs_cfg = PRBSConfig()

    reconcile_cfg: ReconciliationConfig | None = None
    if recon_active:
        reconcile_cfg = ReconciliationConfig(seed=args.reconcile_seed)

    effective_reconcile_keys = getattr(args, "reconcile_keys_output", None)
    effective_pa_keys = args.pa_keys_output if args.pa_keys_output is not None else effective_reconcile_keys

    nist_cfg = NISTConfig(
        alpha=args.nist_alpha,
        approximate_entropy_m=args.nist_m,
    ) if nist_active else None

    kgr_cfg = KGRConfig() if kgr_active else None

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
            enable_prbs=args.prbs,
            prbs_config=prbs_cfg,
            prbs_samples_output=args.prbs_samples_output,
            prbs_bitstreams_output=args.prbs_bitstreams_output,
            prbs_metrics_output=args.prbs_metrics_output,
            prbs_config_output=args.prbs_config_output,
            prbs_xlsx_output=args.prbs_xlsx_output,
            prbs_figure_prefix=args.prbs_figure_prefix,
            return_prbs_result=True,
            enable_reconcile=recon_active,
            reconcile_config=reconcile_cfg,
            reconcile_metrics_output=args.reconcile_metrics_output,
            reconcile_blocks_output=args.reconcile_blocks_output,
            reconcile_config_output=args.reconcile_config_output,
            reconciled_xlsx_output=args.reconciled_xlsx_output,
            reconcile_figure_prefix=args.reconcile_figure_prefix,
            return_reconcile_result=True,
            enable_pa=pa_active,
            pa_metrics_output=args.pa_metrics_output,
            pa_keys_output=effective_pa_keys,
            reconcile_keys_output=effective_reconcile_keys,
            pa_config_output=args.pa_config_output,
            pa_xlsx_output=args.pa_xlsx_output,
            pa_figure_prefix=args.pa_figure_prefix,
            return_pa_result=True,
            enable_nist=nist_active,
            nist_config=nist_cfg,
            nist_metrics_output=args.nist_metrics_output,
            nist_config_output=args.nist_config_output,
            return_nist_result=nist_active,
            enable_kgr=kgr_active,
            kgr_config=kgr_cfg,
            kgr_metrics_output=args.kgr_metrics_output,
            kgr_config_output=args.kgr_config_output,
            evaluation_xlsx_output=args.evaluation_xlsx_output,
            return_kgr_result=kgr_active,
        )
        if kgr_active:
            results, fig_paths, quant_res, prbs_res, reconcile_res, pa_res, nist_res, kgr_res = ret_val  # type: ignore[misc]
        elif nist_active:
            results, fig_paths, quant_res, prbs_res, reconcile_res, pa_res, nist_res = ret_val  # type: ignore[misc]
            kgr_res = None
        else:
            results, fig_paths, quant_res, prbs_res, reconcile_res, pa_res = ret_val  # type: ignore[misc]
            nist_res = None
            kgr_res = None
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

    if prbs_res is not None:
        print("\nCalculated PRBS Expansion & Key Agreement Rate (KAR) Results (PA.pdf Section 3.2.4 & 3.2.8.c):")
        print("-" * 125)
        print(
            f"{'Pair':<20} | {'Samples':<8} | {'2-bit Pre-KAR':<14} | {'2-bit Post-KAR':<15} | {'2b Delta':<10} | {'4-bit Pre-KAR':<14} | {'4-bit Post-KAR':<15} | {'4b Delta':<10} | {'Bits (2b/4b)':<12}"
        )
        print("-" * 125)
        for pm in prbs_res.pair_metrics:
            k2_pre = f"{float(pm['pre_prbs_kar_2bit']):.4f}%"
            k2_post = f"{float(pm['post_prbs_kar_2bit']):.4f}%"
            d2 = f"{float(pm['kar_delta_2bit']):+.4f}%"
            k4_pre = f"{float(pm['pre_prbs_kar_4bit']):.4f}%"
            k4_post = f"{float(pm['post_prbs_kar_4bit']):.4f}%"
            d4 = f"{float(pm['kar_delta_4bit']):+.4f}%"
            bits = f"{pm['post_prbs_bits_2bit']} / {pm['post_prbs_bits_4bit']}"
            print(
                f"{pm['pair']:<20} | {pm['sample_count']:<8} | {k2_pre:<14} | {k2_post:<15} | {d2:<10} | {k4_pre:<14} | {k4_post:<15} | {d4:<10} | {bits:<12}"
            )
        print("-" * 125)

        print("\nZero-Seed and Lockup Statistics per Channel (Galois XOR-LFSR, zero-seed -> 000 with period 1):")
        print("-" * 95)
        print(
            f"{'Channel':<15} | {'Total':<6} | {'2-bit Zero Seeds':<22} | {'4-bit Zero Seeds':<22} | {'Lockup Behavior':<25}"
        )
        print("-" * 95)
        for ch, ch_res in prbs_res.channels.items():
            z2 = f"{ch_res.zero_seed_count_2bit} ({ch_res.zero_seed_percentage_2bit:5.2f}%)"
            z4 = f"{ch_res.zero_seed_count_4bit} ({ch_res.zero_seed_percentage_4bit:5.2f}%)"
            lockup_desc = "Locked at 0 (actual period 1)" if ch_res.zero_seed_count_2bit > 0 else "None (all nonzero)"
            print(
                f"{ch:<15} | {ch_res.sample_count:<6} | {z2:<22} | {z4:<22} | {lockup_desc:<25}"
            )
        print("-" * 95)

    if reconcile_res is not None:
        print("\nCalculated BCH Reconciliation (PA.pdf Section 3.2.5):")
        print("-" * 128)
        print(
            f"{'Path':<12} | {'Pair':<20} | {'BCH (n,k,t,d)':<22} | {'Interleave':<10} | {'Pre-KAR':<10} | {'Post-KAR':<10} | {'Exact Recovery':<16} | {'Blocks (S/F/M)':<16}"
        )
        print("-" * 128)
        for m in reconcile_res.metrics:
            d_part = f",d={m.designed_d}" if m.designed_d else ""
            code_str = f"BCH({m.n},{m.k},{m.t}{d_part})"
            pre_k = f"{m.pre_kar:.2f}%"
            post_k = f"{m.post_kar:.2f}%"
            exact_s = "TRUE" if m.exact_recovery else "FALSE"
            blk_s = f"{m.successful_blocks}/{m.detected_failures}/{m.miscorrected_blocks}"
            print(
                f"{m.path:<12} | {m.pair:<20} | {code_str:<22} | {m.interleaving:<10} | {pre_k:<10} | {post_k:<10} | {exact_s:<16} | {blk_s:<16}"
            )
        print("-" * 128)

    if pa_res is not None:
        print("\nCalculated Privacy Amplification (SHA-256) Results (PA.pdf Section 3.2.6 & Eq 3.64):")
        print("-" * 140)
        print(
            f"{'Path':<12} | {'Pair':<20} | {'Pre-PA KAR':<12} | {'Post-PA Mean KAR':<18} | {'Delta':<10} | {'Exact Matches':<15} | {'Match Rate':<12} | {'All Match':<12} | {'Chunks':<8}"
        )
        print("-" * 140)
        for m in pa_res.metrics:
            pre_k = f"{m.pre_pa_kar:.2f}%"
            post_k = f"{m.post_pa_kar:.2f}%"
            d_k = f"{m.kar_delta:+.2f} pp"
            matches_s = f"{m.exact_match_count}/{m.num_chunks}"
            rate_s = f"{m.exact_match_rate_percent:.1f}%"
            all_m = "TRUE (MATCH)" if m.exact_key_match else "FALSE"
            print(
                f"{m.path_name:<12} | {m.pair_name:<20} | {pre_k:<12} | {post_k:<18} | {d_k:<10} | {matches_s:<15} | {rate_s:<12} | {all_m:<12} | {m.num_chunks:<8}"
            )
        print("-" * 140)
        print("\nDerived 256-bit Channel Secret Keys (First Chunk Hex Digests & Total Chunks):")
        print("-" * 120)
        print(
            f"{'Path':<12} | {'Channel':<15} | {'Role':<32} | {'Chunks':<8} | {'First Key Hex (64-char)':<64}"
        )
        print("-" * 120)
        for p_name, chs in pa_res.channel_keys.items():
            for ch_name, k_info in chs.items():
                print(
                    f"{p_name:<12} | {ch_name:<15} | {k_info.channel_role:<32} | {k_info.num_chunks:<8} | {k_info.key_hex}"
                )
        print("-" * 120)

    if nist_res is not None:
        print("\nCalculated NIST SP 800-22 Randomness Test Results (PA.pdf Section 3.2.8.d & Eqs 3.65–3.73):")
        print("-" * 125)
        print(
            f"{'Path':<12} | {'Channel':<15} | {'Monobit (s/P)':<20} | {'Runs (Vn/P)':<20} | {'ApEn m=2 (chi2/P)':<22} | {'Overall':<10}"
        )
        print("-" * 125)
        for res in nist_res.all_results:
            mono_p = "P" if res.monobit.passed else "F"
            runs_p = "P" if res.runs.passed else "F"
            apen_p = "P" if res.approximate_entropy.passed else "F"
            mono_s = f"{res.monobit.statistic:.2f} (p={res.monobit.p_value:.4f}) {mono_p}"
            runs_s = f"{res.runs.statistic:.0f} (p={res.runs.p_value:.4f}) {runs_p}"
            apen_s = f"{res.approximate_entropy.statistic:.2f} (p={res.approximate_entropy.p_value:.4f}) {apen_p}"
            ov_s = "ACCEPTED" if res.overall_accepted else "REJECTED"
            print(
                f"{res.path_name:<12} | {res.channel_name:<15} | {mono_s:<20} | {runs_s:<20} | {apen_s:<22} | {ov_s:<10}"
            )
        print("-" * 125)

    if kgr_res is not None:
        print("\nCalculated Key Generation Rate (KGR) Results (PA.pdf Section 3.2.8.b & Eq 3.63):")
        print("-" * 125)
        print(
            f"{'Path':<12} | {'N_raw (b)':<10} | {'NIST Pass':<10} | {'N_bit (b)':<10} | {'Time (ms)':<12} | {'Accepted KGR':<18} | {'Raw KGR':<16} | {'Alice–Bob Match':<20}"
        )
        print("-" * 125)
        for km in kgr_res.metrics:
            p_pass = "YES" if km.nist_overall_passed else "NO"
            t_ms = f"{km.duration_ms:.2f} ms"
            acc_kgr = f"{km.accepted_kgr_bps:.2f} bps"
            raw_kgr = f"{km.raw_kgr_bps:.2f} bps"
            agr_str = "MATCH (100.00%)" if km.alice_bob_exact_match else f"MISMATCH ({km.alice_bob_kar:.2f}%)"
            print(
                f"{km.path_name:<12} | {km.raw_generated_bits:<10} | {p_pass:<10} | {km.accepted_bits:<10} | {t_ms:<12} | {acc_kgr:<18} | {raw_kgr:<16} | {agr_str:<20}"
            )
        print("-" * 125)
        print(f"[TIMING] Timer Scope:   {TIMER_START_BOUNDARY} -> {TIMER_END_BOUNDARY}")
        print(f"[TIMING] Cache Policy:  {BCH_CACHE_POLICY_DESC}")
        print(f"[LABEL]  Validation:    {RESEARCH_DISCLAIMER_KGR}")

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

    if args.prbs_samples_output:
        print(f"[OUTPUT] PRBS sample-level expansion CSV:         {args.prbs_samples_output}")

    if args.prbs_bitstreams_output:
        print(f"[OUTPUT] PRBS concatenated bitstreams CSV:         {args.prbs_bitstreams_output}")

    if args.prbs_metrics_output:
        print(f"[OUTPUT] PRBS before/after KAR metrics CSV:        {args.prbs_metrics_output}")

    if args.prbs_config_output:
        print(f"[OUTPUT] PRBS configuration metadata JSON:        {args.prbs_config_output}")

    if args.prbs_xlsx_output:
        print(f"[OUTPUT] PRBS companion Excel workbook (.xlsx):    {args.prbs_xlsx_output}")
        print("         (Excel users should open .xlsx rather than .csv to preserve leading zeros in '000', '00', and split bitstreams beyond 32,767 limit)")

    if args.reconcile_metrics_output:
        print(f"[OUTPUT] Reconciliation summary metrics CSV:       {args.reconcile_metrics_output}")

    if args.reconcile_blocks_output:
        print(f"[OUTPUT] Per-block reconciliation details CSV:     {args.reconcile_blocks_output}")

    if args.reconcile_config_output:
        print(f"[OUTPUT] Reconciliation metadata JSON:             {args.reconcile_config_output}")

    if args.reconciled_xlsx_output:
        print(f"[OUTPUT] Reconciliation Excel workbook (.xlsx):    {args.reconciled_xlsx_output}")
        print("         (Excel users should open .xlsx rather than .csv to preserve leading zeros in bitstreams)")

    if args.pa_metrics_output:
        print(f"[OUTPUT] Privacy amplification metrics CSV:        {args.pa_metrics_output}")

    if effective_pa_keys:
        print(f"[OUTPUT] Channel secret keys CSV:                  {effective_pa_keys}")

    if args.pa_config_output:
        print(f"[OUTPUT] Privacy amplification config JSON:        {args.pa_config_output}")

    if args.pa_xlsx_output:
        print(f"[OUTPUT] Privacy amplification Excel workbook:     {args.pa_xlsx_output}")
        print("         (Excel users should open .xlsx rather than .csv to preserve leading zeros in bit/hex keys)")

    if args.nist_metrics_output:
        print(f"[OUTPUT] NIST SP 800-22 metrics CSV:               {args.nist_metrics_output}")

    if args.nist_config_output:
        print(f"[OUTPUT] NIST SP 800-22 config metadata JSON:      {args.nist_config_output}")

    if args.kgr_metrics_output:
        print(f"[OUTPUT] Key Generation Rate (KGR) metrics CSV:    {args.kgr_metrics_output}")

    if args.kgr_config_output:
        print(f"[OUTPUT] KGR configuration metadata JSON:          {args.kgr_config_output}")

    if args.evaluation_xlsx_output:
        print(f"[OUTPUT] Evaluation companion Excel (.xlsx):       {args.evaluation_xlsx_output}")
        print("         (Excel users should open .xlsx rather than .csv to preserve leading zeros in bit/hex keys)")

    if fig_paths is not None:
        png_p, pdf_p = fig_paths
        print(f"[OUTPUT] Figure plot (PNG 300 dpi) exported to:    {png_p}")
        print(f"[OUTPUT] Figure plot (PDF) exported to:            {pdf_p}")

    if quant_res is not None and quant_res.figure_paths is not None:
        q_png_p, q_pdf_p = quant_res.figure_paths
        print(f"[OUTPUT] Quantization KAR figure (PNG 300 dpi):    {q_png_p}")
        print(f"[OUTPUT] Quantization KAR figure (PDF):            {q_pdf_p}")

    if prbs_res is not None and prbs_res.figure_paths is not None:
        p_png_p, p_pdf_p = prbs_res.figure_paths
        print(f"[OUTPUT] PRBS KAR figure (PNG 300 dpi):            {p_png_p}")
        print(f"[OUTPUT] PRBS KAR figure (PDF vector):             {p_pdf_p}")

    if reconcile_res is not None and reconcile_res.figure_paths is not None:
        r_png_p, r_pdf_p = reconcile_res.figure_paths
        print(f"[OUTPUT] Reconciliation figure (PNG 300 dpi):      {r_png_p}")
        print(f"[OUTPUT] Reconciliation figure (PDF vector):       {r_pdf_p}")

    if pa_res is not None and pa_res.figure_paths is not None:
        pa_png_p, pa_pdf_p = pa_res.figure_paths
        print(f"[OUTPUT] PA comparison figure (PNG 300 dpi):       {pa_png_p}")
        print(f"[OUTPUT] PA comparison figure (PDF vector):        {pa_pdf_p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
