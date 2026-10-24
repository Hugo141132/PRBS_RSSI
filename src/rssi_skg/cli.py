"""Command Line Interface (CLI) for RSSI correlation analysis.

Executes Pearson correlation analysis on RSSI datasets according to PA.pdf Eq (3.62),
calculating pairs:
- Alice–Bob
- Alice–Eve1-Alice
- Bob–Eve1-Bob

Exports results to CSV with schema:
pair,sample_count,correlation_coefficient,data_kind
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from typing import Sequence

from rssi_skg.correlation import pearson_correlation
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import plot_combined_correlation_figure

TARGET_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("Alice", "Bob", "Alice–Bob"),
    ("Alice", "Eve1-Alice", "Alice–Eve1-Alice"),
    ("Bob", "Eve1-Bob", "Bob–Eve1-Bob"),
)


def run_correlation_analysis(
    input_path: str | Path,
    output_path: str | Path | None = None,
    figure_prefix: str | Path | None = None,
    data_kind: str = "dummy",
) -> tuple[list[dict[str, str | int | float]], tuple[Path, Path] | None]:
    """Execute correlation analysis on the given workbook, optionally saving to CSV and figure.

    Args:
        input_path: Path to the Excel workbook.
        output_path: Optional path to save resulting CSV.
        figure_prefix: Optional file prefix to export PNG (300 dpi) and PDF figures.
        data_kind: Data category tag, default 'dummy'.

    Returns:
        tuple: (results, figure_paths) where figure_paths is (png_path, pdf_path) or None.
    """
    in_path = Path(input_path)
    data = load_rssi_workbook(in_path)

    results: list[dict[str, str | int | float]] = []

    for col1, col2, pair_name in TARGET_PAIRS:
        series1 = data[col1]
        series2 = data[col2]
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
            data=data,
            results=results,
            prefix_path=figure_prefix,
        )

    return results, fig_paths


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Compute Pearson correlation for RSSI datasets (PA.pdf Eq 3.62)."
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
        help="Path prefix to export combined correlation figure in PNG (300 dpi) and PDF (optional).",
    )
    parser.add_argument(
        "--data-kind",
        default="dummy",
        help="Label for data kind (default: dummy).",
    )

    args = parser.parse_args(argv)

    print("=" * 65)
    print("RSSI SECRET KEY GENERATION (SKG) - CORRELATION ANALYSIS")
    print(f"[STATUS] Data Kind: {args.data_kind.upper()}")
    print("[NOTICE] Software validation only; empirical channel probing is postponed.")
    print("=" * 65)

    try:
        results, fig_paths = run_correlation_analysis(
            input_path=args.input,
            output_path=args.output,
            figure_prefix=args.figure_prefix,
            data_kind=args.data_kind,
        )
    except Exception as err:
        print(f"\n[ERROR] Analysis failed: {err}", file=sys.stderr)
        return 1

    print("\nCalculated Pearson Correlation Results (Zero Lag):")
    print("-" * 65)
    print(f"{'Pair':<20} | {'Samples':<8} | {'Pearson (rho)':<18} | {'Data Kind':<10}")
    print("-" * 65)
    for r in results:
        rho_val = float(r["correlation_coefficient"])
        print(
            f"{r['pair']:<20} | {r['sample_count']:<8} | {rho_val:<18.10f} | {r['data_kind']:<10}"
        )
    print("-" * 65)

    if args.output:
        print(f"\n[OUTPUT] CSV results successfully exported to: {args.output}")

    if fig_paths is not None:
        png_p, pdf_p = fig_paths
        print(f"[OUTPUT] Combined figure (PNG 300 dpi) exported to: {png_p}")
        print(f"[OUTPUT] Combined figure (PDF) exported to:         {pdf_p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
