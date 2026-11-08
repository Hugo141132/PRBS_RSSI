"""Unit tests for Stage 8 — Key Generation Rate (KGR) Measurement (PA.pdf Section 3.2.8.b & Eq 3.63).

Verifies:
1. Controlled mock clock injection for deterministic KGR rate computation.
2. Strict single accounting of Alice's final key (256 bits; Bob is not duplicate-counted).
3. Statistical acceptance gating (N_accepted = 256 if NIST passes, 0 if NIST fails or inapplicable).
4. Cache warm-up policy (warm_up_bch_cache pre-compiles Galois Numba routines before timed execution).
5. Timing boundaries and independent per-path measurement.
6. Full pipeline KGR measurement on dummy dataset across quant_2bit and prbs_2bit.
7. Artifact exporters (CSV metrics, config JSON, and companion multi-sheet Excel workbook).
8. CLI integration with --nist and --kgr flags.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl
import pytest

from rssi_skg.cli import main
from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.kgr import (
    RESEARCH_DISCLAIMER_KGR,
    KGRConfig,
    MultiPathKGRResult,
    PathKGRResult,
    export_evaluation_workbook_xlsx,
    export_kgr_config_json,
    export_kgr_metrics_csv,
    measure_multipath_kgr,
    warm_up_bch_cache,
)
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.nist import (
    KeyRandomnessResult,
    MultiPathNISTResult,
    NISTConfig,
    NISTTestResult,
    evaluate_pa_keys_randomness,
)
from rssi_skg.prbs import PRBSConfig, expand_channels_prbs
from rssi_skg.privacy_amplification import PrivacyAmplificationConfig, amplify_privacy_all_paths
from rssi_skg.quantization import QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import ReconciliationConfig, reconcile_all_paths


# ==============================================================================
# 1. Controlled Clock Injection & Rate Calculation
# ==============================================================================


class MockTimer:
    """Mock monotonic timer advancing by fixed increments."""

    def __init__(self, step: float = 0.5) -> None:
        self.time = 0.0
        self.step = step

    def __call__(self) -> float:
        val = self.time
        self.time += self.step
        return val


def test_kgr_controlled_mock_clock() -> None:
    """Verify KGR calculation using controlled mock timer."""
    # Step = 0.5 seconds => Duration T = 0.5 s
    # 256 bits / 0.5 s = 512.0 bps
    mock_timer = MockTimer(step=0.5)
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")

    # Pre-build NIST result where Alice passes
    filtered = filter_rssi_channels(raw, FilterConfig())
    quant = quantize_channels(filtered, QuantizationConfig())
    prbs = expand_channels_prbs(quant, PRBSConfig())
    recon = reconcile_all_paths(quant, prbs, ReconciliationConfig(seed=42))
    pa = amplify_privacy_all_paths(recon)
    nist_res = evaluate_pa_keys_randomness(pa, NISTConfig())

    res = measure_multipath_kgr(
        raw_data=raw,
        nist_result=nist_res,
        config=KGRConfig(pre_warm_bch=False),
        timer=mock_timer,
    )

    for path_name in ["quant_2bit", "prbs_2bit"]:
        path_kgr = res.paths[path_name]
        assert path_kgr.raw_generated_bits == 256
        assert path_kgr.accepted_bits == 256
        assert path_kgr.duration_seconds == pytest.approx(0.5, abs=1e-5)
        assert path_kgr.raw_kgr_bps == pytest.approx(512.0, abs=1e-3)
        assert path_kgr.accepted_kgr_bps == pytest.approx(512.0, abs=1e-3)


# ==============================================================================
# 2. Single Key Accounting & Bob Non-Duplication
# ==============================================================================


def test_kgr_single_alice_accounting() -> None:
    """Verify that only Alice's key is counted (256 bits) and Bob is not duplicate-counted."""
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    filtered = filter_rssi_channels(raw, FilterConfig())
    quant = quantize_channels(filtered, QuantizationConfig())
    prbs = expand_channels_prbs(quant, PRBSConfig())
    recon = reconcile_all_paths(quant, prbs, ReconciliationConfig(seed=42))
    pa = amplify_privacy_all_paths(recon)
    nist_res = evaluate_pa_keys_randomness(pa, NISTConfig())

    res = measure_multipath_kgr(
        raw_data=raw,
        nist_result=nist_res,
        config=KGRConfig(pre_warm_bch=True),
    )

    for path_name in ["quant_2bit", "prbs_2bit"]:
        path_kgr = res.paths[path_name]
        # Must be exactly 256, NEVER 512
        assert path_kgr.raw_generated_bits == 256
        assert path_kgr.accepted_bits == 256
        # Agreement is recorded separately
        assert path_kgr.alice_bob_exact_match is True


# ==============================================================================
# 3. Statistical Acceptance Gating
# ==============================================================================


def test_kgr_statistical_rejection_gating() -> None:
    """Verify that if NIST acceptance fails, accepted_bits=0 and accepted_kgr_bps=0.0."""
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")

    # Create dummy NIST result where Alice fails
    failing_test = NISTTestResult(
        test_name="Frequency (Monobit)",
        statistic=10.0,
        p_value=0.0001,
        applicable=True,
        passed=False,
        alpha=0.01,
        details={},
        reason="Failed Monobit threshold",
    )
    passing_test = NISTTestResult(
        test_name="Dummy",
        statistic=1.0,
        p_value=0.5,
        applicable=True,
        passed=True,
        alpha=0.01,
        details={},
        reason=None,
    )

    alice_failing_key = KeyRandomnessResult(
        path_name="quant_2bit",
        channel_name="Alice",
        channel_role="Legitimate transmitter",
        key_length=256,
        key_hex="0" * 64,
        key_bin="0" * 256,
        monobit=failing_test,
        runs=passing_test,
        approximate_entropy=passing_test,
        overall_accepted=False,
    )

    mock_nist_multi = MultiPathNISTResult(
        config=NISTConfig(),
        channel_evaluations={
            "quant_2bit": {"Alice": alice_failing_key},
            "prbs_2bit": {"Alice": alice_failing_key},
        },
    )

    mock_timer = MockTimer(step=0.25)  # 250 ms
    res = measure_multipath_kgr(
        raw_data=raw,
        nist_result=mock_nist_multi,
        config=KGRConfig(pre_warm_bch=False),
        timer=mock_timer,
    )

    path_kgr = res.paths["quant_2bit"]
    assert path_kgr.nist_overall_passed is False
    assert path_kgr.raw_generated_bits == 256
    assert path_kgr.accepted_bits == 0
    assert path_kgr.raw_kgr_bps == pytest.approx(1024.0, abs=1e-3)
    assert path_kgr.accepted_kgr_bps == 0.0


# ==============================================================================
# 4. Cache Warm-Up Policy
# ==============================================================================


def test_warm_up_bch_cache_execution() -> None:
    """Verify that warm_up_bch_cache executes cleanly without errors."""
    warm_up_bch_cache()


# ==============================================================================
# 5. MultiPath KGR Measurement on Dummy Dataset
# ==============================================================================


def test_measure_multipath_kgr_dummy_data() -> None:
    """Verify realistic measurement on actual dummy dataset."""
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    filtered = filter_rssi_channels(raw, FilterConfig())
    quant = quantize_channels(filtered, QuantizationConfig())
    prbs = expand_channels_prbs(quant, PRBSConfig())
    recon = reconcile_all_paths(quant, prbs, ReconciliationConfig(seed=42))
    pa = amplify_privacy_all_paths(recon)
    nist_res = evaluate_pa_keys_randomness(pa, NISTConfig())

    res = measure_multipath_kgr(
        raw_data=raw,
        nist_result=nist_res,
        config=KGRConfig(pre_warm_bch=True),
    )

    assert isinstance(res, MultiPathKGRResult)
    assert "quant_2bit" in res.paths
    assert "prbs_2bit" in res.paths

    for path_name, path_res in res.paths.items():
        assert path_res.raw_generated_bits == 256
        assert path_res.accepted_bits == 256
        assert path_res.nist_overall_passed is True
        assert path_res.alice_bob_exact_match is True
        assert path_res.duration_seconds > 0.0
        assert path_res.raw_kgr_bps > 0.0
        assert path_res.accepted_kgr_bps > 0.0
        assert path_res.bch_cache_policy != ""
        assert "filter" in path_res.timer_start_boundary.lower()
        assert "sha256" in path_res.timer_end_boundary.lower()


# ==============================================================================
# 6. KGR Artifact Exporters (CSV, JSON, multi-sheet XLSX)
# ==============================================================================


def test_kgr_exporters(tmp_path: Path) -> None:
    """Verify CSV, JSON, and XLSX export functions for KGR metrics."""
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    filtered = filter_rssi_channels(raw, FilterConfig())
    quant = quantize_channels(filtered, QuantizationConfig())
    prbs = expand_channels_prbs(quant, PRBSConfig())
    recon = reconcile_all_paths(quant, prbs, ReconciliationConfig(seed=42))
    pa = amplify_privacy_all_paths(recon)
    nist_res = evaluate_pa_keys_randomness(pa, NISTConfig())
    kgr_res = measure_multipath_kgr(raw_data=raw, nist_result=nist_res)

    csv_out = tmp_path / "kgr_metrics.csv"
    json_out = tmp_path / "kgr_config.json"
    xlsx_out = tmp_path / "evaluation_summary.xlsx"

    export_kgr_metrics_csv(kgr_res, csv_out)
    export_kgr_config_json(kgr_res, json_out, extra_metadata={"run": "test"})
    export_evaluation_workbook_xlsx(nist_res, kgr_res, xlsx_out)

    assert csv_out.exists()
    assert json_out.exists()
    assert xlsx_out.exists()

    # Check CSV
    with open(csv_out, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    paths = [r["path"] for r in rows]
    assert "quant_2bit" in paths
    assert "prbs_2bit" in paths

    # Check JSON
    with open(json_out, "r", encoding="utf-8") as f:
        kgr_json = json.load(f)
    assert kgr_json["scientific_disclaimer"] == RESEARCH_DISCLAIMER_KGR
    assert "summary" in kgr_json
    summary_paths = [item["path"] for item in kgr_json["summary"]]
    assert "quant_2bit" in summary_paths
    assert "prbs_2bit" in summary_paths

    # Check XLSX workbook and sheets
    wb = openpyxl.load_workbook(xlsx_out)
    sheet_names = wb.sheetnames
    assert "KGR Metrics" in sheet_names
    assert "NIST Randomness" in sheet_names
    assert "Config & Disclaimers" in sheet_names

    # Check that text format is preserved
    ws_nist = wb["NIST Randomness"]
    assert ws_nist.cell(row=2, column=5).number_format == "@"


# ==============================================================================
# 7. CLI Integration Test
# ==============================================================================


def test_cli_nist_and_kgr_execution(tmp_path: Path) -> None:
    """Verify end-to-end CLI command with --nist and --kgr flags."""
    nist_csv = tmp_path / "nist_metrics.csv"
    nist_json = tmp_path / "nist_config.json"
    kgr_csv = tmp_path / "kgr_metrics.csv"
    kgr_json = tmp_path / "kgr_config.json"
    eval_xlsx = tmp_path / "evaluation.xlsx"

    argv = [
        "-i",
        "data/raw/dummy/Dummy RSSI (data Indoor).xlsx",
        "--filter",
        "--quantize",
        "--prbs",
        "--reconcile",
        "--pa",
        "--nist",
        "--kgr",
        "--nist-metrics-output",
        str(nist_csv),
        "--nist-config-output",
        str(nist_json),
        "--kgr-metrics-output",
        str(kgr_csv),
        "--kgr-config-output",
        str(kgr_json),
        "--evaluation-xlsx-output",
        str(eval_xlsx),
    ]

    ret = main(argv)
    assert ret == 0

    assert nist_csv.exists()
    assert nist_json.exists()
    assert kgr_csv.exists()
    assert kgr_json.exists()
    assert eval_xlsx.exists()
