"""Unit and integration tests for BCH information reconciliation and SHA-256 candidate-key derivation.

Governing Specification:
    PA.pdf Section 3.2.5, Equations (3.27)–(3.36), pages 29–33.
    PA.pdf Section 3.2.6, Equation (3.37), page 33 (Privacy Amplification).
    PA.pdf Section 3.2.8.c, Equation (3.64), page 35 (Key Agreement Rate).
"""

from __future__ import annotations

import csv
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import openpyxl
import pytest

from rssi_skg.cli import main, run_correlation_analysis
from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import plot_reconciliation_figure, plot_shared_bch_figure
from rssi_skg.prbs import MultiChannelPRBSResult, PRBSConfig, expand_channels_prbs
from rssi_skg.quantization import ChannelQuantizationResult, QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import (
    DEFAULT_BCH_CODE,
    GLOBAL_BCH_CODE,
    INTERLEAVING_STATUS,
    BlockReconciliationDetail,
    PairReconciliationResult,
    ReconciliationConfig,
    export_reconciliation_blocks_csv,
    export_reconciliation_config_json,
    export_reconciliation_metrics_csv,
    export_reconciliation_workbook_xlsx,
    generate_helper_data,
    get_bch_code,
    reconcile_all_paths,
    reconstruct_receiver_bitstream,
)


# ==============================================================================
# 1. BCH Code Cache and Mathematical Properties
# ==============================================================================


def test_bch_code_cache_and_properties() -> None:
    """Verify supported BCH code parameters, caching, and invalid configurations."""
    # Test global default
    bch_default = get_bch_code(*DEFAULT_BCH_CODE)
    assert bch_default.n == 1023
    assert bch_default.k == 46
    assert bch_default.t == 200
    assert bch_default.d == 401

    # Test small valid candidate
    bch15 = get_bch_code(15, 7, 2)
    assert bch15.n == 15
    assert bch15.k == 7
    assert bch15.t == 2
    assert bch15.d == 5

    bch31 = get_bch_code(31, 1, 15)
    assert bch31.n == 31
    assert bch31.k == 1
    assert bch31.t == 15
    assert bch31.d == 31

    # Check cache identity
    assert get_bch_code(1023, 46, 200) is bch_default
    assert get_bch_code(15, 7, 2) is bch15

    # Inconsistent configurations raise actionable ValueError
    with pytest.raises(ValueError, match="inconsistent with Galois code"):
        get_bch_code(1023, 50, 200)

    with pytest.raises(ValueError, match="inconsistent with Galois code|does not exist"):
        get_bch_code(31, 20, 5)


# ==============================================================================
# 2. Privacy Amplification Removed from BCH Scope
# ==============================================================================


def test_privacy_amplification_not_in_reconciliation_scope() -> None:
    """Verify that candidate-key generation and SHA-256 privacy amplification are absent from BCH scope."""
    import rssi_skg.reconciliation as recon_mod
    import dataclasses

    # Functions must not exist
    assert not hasattr(recon_mod, "serialize_bitstream")
    assert not hasattr(recon_mod, "generate_candidate_key")
    assert not hasattr(recon_mod, "export_reconciliation_keys_json")

    # Result dataclass fields must not exist
    pair_fields = {f.name for f in dataclasses.fields(recon_mod.PairReconciliationResult)}
    assert "source_key_sha256" not in pair_fields
    assert "receiver_candidate_key_sha256" not in pair_fields
    assert "key_match" not in pair_fields

    master_fields = {f.name for f in dataclasses.fields(recon_mod.MultiPathReconciliationResult)}
    assert "candidate_keys" not in master_fields


# ==============================================================================
# 3. Error-Free Recovery
# ==============================================================================


def test_error_free_recovery() -> None:
    """Verify error-free reconciliation when Bob's bitstream matches Alice's bitstream."""
    n, k, t = 15, 7, 2
    rng = np.random.default_rng(12345)

    source_bits = "101100101011110010101101010101010101010111000"  # 45 bits (3 blocks)
    orig_len = len(source_bits)
    num_blocks = (orig_len + n - 1) // n

    # Generate helper data: returns (helper_blocks, original_length, padding_count)
    helper_blocks, orig_l, pad_cnt = generate_helper_data(source_bits, n=n, k=k, t=t, rng=rng)
    assert len(helper_blocks) == num_blocks
    assert orig_l == orig_len
    assert pad_cnt == (num_blocks * n - orig_len)

    # Bob has identical bitstream
    recovered_unpadded, corrections_list = reconstruct_receiver_bitstream(
        receiver_bits=source_bits,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        t=t,
        original_length=orig_l,
        padding_count=pad_cnt,
    )
    recovered_str = "".join(str(b) for b in recovered_unpadded)

    assert recovered_str == source_bits
    assert len(corrections_list) == num_blocks
    for num_corr in corrections_list:
        assert num_corr == 0


# ==============================================================================
# 4. Controlled Error Correction Up to t
# ==============================================================================


def test_controlled_error_correction_up_to_t() -> None:
    """Verify that injected bit errors up to t are completely corrected."""
    n, k, t = 15, 7, 2
    bch = get_bch_code(n, k, t)
    rng = np.random.default_rng(42)

    # 1 block of 15 bits
    source_block = "".join(str(b) for b in rng.integers(0, 2, size=n))
    helper_blocks, orig_l, pad_cnt = generate_helper_data(source_block, n=n, k=k, t=t, rng=rng)

    # Inject exactly t errors at random positions
    err_pos = rng.choice(n, size=t, replace=False)
    rx_block_list = list(source_block)
    for pos in err_pos:
        rx_block_list[pos] = "1" if rx_block_list[pos] == "0" else "0"
    rx_block = "".join(rx_block_list)

    recovered_unpadded, corrections_list = reconstruct_receiver_bitstream(
        receiver_bits=rx_block,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        t=t,
        original_length=orig_l,
        padding_count=pad_cnt,
    )
    recovered_str = "".join(str(b) for b in recovered_unpadded)

    assert recovered_str == source_block
    assert len(corrections_list) == 1
    assert corrections_list[0] == t


# ==============================================================================
# 5. Beyond-t Error Handling (Detected Failure & Miscorrection)
# ==============================================================================


def test_beyond_t_error_handling() -> None:
    """Verify that errors exceeding error-correction capability t trigger detected failure or miscorrection."""
    n, k, t = 15, 7, 2
    bch = get_bch_code(n, k, t)
    rng = np.random.default_rng(999)

    source_block = "".join(str(b) for b in rng.integers(0, 2, size=n))
    helper_blocks, orig_l, pad_cnt = generate_helper_data(source_block, n=n, k=k, t=t, rng=rng)

    # Invert 5 bits (exceeds t=2)
    err_pos = rng.choice(n, size=5, replace=False)
    rx_block_list = list(source_block)
    for pos in err_pos:
        rx_block_list[pos] = "1" if rx_block_list[pos] == "0" else "0"
    rx_block = "".join(rx_block_list)

    recovered_unpadded, corrections_list = reconstruct_receiver_bitstream(
        receiver_bits=rx_block,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        t=t,
        original_length=orig_l,
        padding_count=pad_cnt,
    )
    recovered_str = "".join(str(b) for b in recovered_unpadded)
    num_corr = corrections_list[0]

    # In binary block codes, beyond-t error either gives num_corrected == -1 or miscorrects
    if num_corr == -1:
        # Detected failure: receiver block retained
        assert recovered_str == rx_block
    else:
        # Miscorrected: num_corrected >= 0 but does not equal true source block
        assert recovered_str != source_block


# ==============================================================================
# 6. Padding Addition, Removal & Payload Metric Isolation
# ==============================================================================


def test_padding_addition_and_removal() -> None:
    """Verify zero-padding addition, exact stripping post-recovery, and metric isolation."""
    n, k, t = 15, 7, 2
    rng = np.random.default_rng(100)

    # Original length = 25 bits (requires 2 blocks: 15 + 15 = 30 bits, 5 padding bits)
    orig_bits = "".join(str(b) for b in rng.integers(0, 2, size=25))
    orig_len = len(orig_bits)

    helper_blocks, orig_l, pad_cnt = generate_helper_data(orig_bits, n=n, k=k, t=t, rng=rng)
    assert orig_l == 25
    assert pad_cnt == 5
    assert len(helper_blocks) == 2

    # Receiver with identical bits
    recovered_unpadded, _ = reconstruct_receiver_bitstream(
        receiver_bits=orig_bits,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        t=t,
        original_length=orig_l,
        padding_count=pad_cnt,
    )
    recovered_str = "".join(str(b) for b in recovered_unpadded)

    assert len(recovered_str) == 25
    assert recovered_str == orig_bits




# ==============================================================================
# 7. Receiver & Eve Channel Isolation
# ==============================================================================


def test_receiver_isolation_and_no_source_leak() -> None:
    """Verify that receiver decoding functions only accept receiver bits, helper data, and BCH configuration."""
    n, k, t = 15, 7, 2
    rng = np.random.default_rng(777)

    alice_bits = "101100101011110"  # 15 bits
    helper_blocks, orig_l, pad_cnt = generate_helper_data(alice_bits, n=n, k=k, t=t, rng=rng)

    # Receiver B only sees helper_blocks and B's own bits
    bob_bits = alice_bits  # error-free for test
    bob_recovered, _ = reconstruct_receiver_bitstream(
        receiver_bits=bob_bits,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        t=t,
        original_length=orig_l,
        padding_count=pad_cnt,
    )
    assert "".join(str(b) for b in bob_recovered) == alice_bits

    # Eve sees public helper data and Eve's independent channel bits
    eve_bits = "000000000000000"  # uncorrelated Eve
    eve_recovered, _ = reconstruct_receiver_bitstream(
        receiver_bits=eve_bits,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        t=t,
        original_length=orig_l,
        padding_count=pad_cnt,
    )
    # Eve should NOT recover Alice's bits
    assert "".join(str(b) for b in eve_recovered) != alice_bits


# ==============================================================================
# 8. Full End-to-End Pipeline Evaluation on Dummy Dataset (Global BCH 1023, 46, 200)
# ==============================================================================


@pytest.fixture(scope="module")
def pipeline_results() -> tuple[dict[str, list[float]], ChannelQuantizationResult, MultiChannelPRBSResult]:
    """Execute stages 1-3 on the dummy dataset to produce inputs for reconciliation tests."""
    data_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    raw_data = load_rssi_workbook(data_path)
    filt_data = filter_rssi_channels(raw_data, config=FilterConfig())
    quant_res = quantize_channels(filt_data, config=QuantizationConfig(window_size=50, alpha=0.5))
    prbs_res = expand_channels_prbs(quant_res, config=PRBSConfig())
    return filt_data, quant_res, prbs_res


def test_reconcile_supported_paths(pipeline_results: tuple) -> None:
    """Verify BCH reconciliation across supported 2-bit paths and rejection of obsolete options."""
    _, quant_res, prbs_res = pipeline_results

    rec_cfg = ReconciliationConfig(seed=42)
    rec_result = reconcile_all_paths(
        quant_result=quant_res,
        prbs_result=prbs_res,
        config=rec_cfg,
    )

    # 2 supported paths * 3 evaluated pairs (Alice-Bob, Alice-Eve1A, Bob-Eve1B) = 6 metrics
    assert len(rec_result.metrics) == 6

    metrics_by_key = {(m.path, m.pair): m for m in rec_result.metrics}

    # Path 1: quant_2bit (Global BCH 1023, 46, 200)
    ab_q2 = metrics_by_key[("quant_2bit", "Alice–Bob")]
    assert ab_q2.pre_kar == pytest.approx(80.40, abs=0.01)
    assert ab_q2.post_kar == 100.00
    assert ab_q2.exact_recovery is True
    assert ab_q2.successful_blocks == 1
    assert ab_q2.detected_failures == 0
    assert ab_q2.miscorrected_blocks == 0

    # Eve on quant_2bit must fail
    ae_q2 = metrics_by_key[("quant_2bit", "Alice–Eve1-Alice")]
    assert ae_q2.exact_recovery is False

    # Path 2: prbs_2bit (Global BCH 1023, 46, 200)
    ab_p2 = metrics_by_key[("prbs_2bit", "Alice–Bob")]
    assert ab_p2.pre_kar == pytest.approx(76.27, abs=0.01)
    assert ab_p2.post_kar == 100.00
    assert ab_p2.exact_recovery is True
    assert ab_p2.successful_blocks == 2
    assert ab_p2.detected_failures == 0
    assert ab_p2.miscorrected_blocks == 0

    ae_p2 = metrics_by_key[("prbs_2bit", "Alice–Eve1-Alice")]
    assert ae_p2.exact_recovery is False

    # Explicit rejection of obsolete reconciliation options
    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(code_quant_2bit=(31, 1, 15))  # type: ignore

    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(code_prbs_2bit=(127, 1, 63))  # type: ignore

    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(mode="shared_1023")  # type: ignore

    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(code_quant_4bit=(63, 10, 13))  # type: ignore

    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(code_prbs_4bit=(127, 1, 63))  # type: ignore

    with pytest.raises(ValueError, match="Obsolete reconciliation path"):
        rec_cfg.get_code_for_path("quant_4bit")

    with pytest.raises(ValueError, match="Obsolete reconciliation path"):
        rec_cfg.get_code_for_path("prbs_4bit")


def test_paths_use_identical_parameters() -> None:
    """Verify that quant_2bit and prbs_2bit obtain the exact same BCH code parameters."""
    cfg = ReconciliationConfig()
    code_q = cfg.get_code_for_path("quant_2bit")
    code_p = cfg.get_code_for_path("prbs_2bit")
    assert code_q == code_p == DEFAULT_BCH_CODE == (1023, 46, 200)


def test_second_small_valid_bch_configuration() -> None:
    """Verify that editing ReconciliationConfig with a second valid BCH configuration works cleanly."""
    valid_small = (15, 7, 2)
    cfg = ReconciliationConfig(code=valid_small)
    assert cfg.code == valid_small
    assert cfg.get_code_for_path("quant_2bit") == valid_small
    assert cfg.get_code_for_path("prbs_2bit") == valid_small

    bch = get_bch_code(*cfg.code)
    assert bch.n == 15
    assert bch.k == 7
    assert bch.t == 2
    assert bch.d == 5


# ==============================================================================
# 9. Exporters & Excel Companion Formatting
# ==============================================================================


def test_reconciliation_exporters(tmp_path: Path, pipeline_results: tuple) -> None:
    """Verify that CSV, JSON, and XLSX companion files export valid data with dynamic parameters."""
    _, quant_res, prbs_res = pipeline_results

    rec_result = reconcile_all_paths(
        quant_result=quant_res,
        prbs_result=prbs_res,
        config=ReconciliationConfig(seed=42),
    )

    # 1. Summary metrics CSV (2 paths * 3 pairs = 6 rows)
    csv_metrics_path = tmp_path / "metrics.csv"
    export_reconciliation_metrics_csv(rec_result, csv_metrics_path)
    assert csv_metrics_path.exists()
    with open(csv_metrics_path, mode="r", encoding="utf-8") as f:
        reader_dict = csv.DictReader(f)
        fieldnames = reader_dict.fieldnames or []
        assert "exact_recovery" in fieldnames
        assert "key_match" not in fieldnames
        assert "source_key_sha256" not in fieldnames
        reader = list(reader_dict)
        assert len(reader) == 6
        for row in reader:
            assert row["n"] == "1023"
            assert row["k"] == "46"
            assert row["t"] == "200"
            assert row["designed_d"] == "401"
            assert row["interleaving"] == "OFF"

    # 2. Block details CSV
    csv_blocks_path = tmp_path / "blocks.csv"
    export_reconciliation_blocks_csv(rec_result, csv_blocks_path)
    assert csv_blocks_path.exists()
    with open(csv_blocks_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) > 0

    # 3. Config JSON
    json_config_path = tmp_path / "config.json"
    export_reconciliation_config_json(rec_result, json_config_path)
    assert json_config_path.exists()
    with open(json_config_path, mode="r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["algorithm"] == "Codeword-Based BCH Information Reconciliation"
        assert "quant_2bit" in data["parameters"]["paths"]
        assert "prbs_2bit" in data["parameters"]["paths"]
        assert data["parameters"]["paths"]["quant_2bit"]["n"] == 1023
        assert data["parameters"]["paths"]["quant_2bit"]["designed_d"] == 401
        assert "quant_4bit" not in data["parameters"]["paths"]
        assert "prbs_4bit" not in data["parameters"]["paths"]

    # 4. Excel Workbook (.xlsx)
    xlsx_path = tmp_path / "reconciliation.xlsx"
    export_reconciliation_workbook_xlsx(rec_result, xlsx_path)
    assert xlsx_path.exists()
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    assert "Reconciliation Metrics" in wb.sheetnames
    assert "Block Details" in wb.sheetnames
    assert "Recovered Bitstreams" in wb.sheetnames
    assert "Candidate Keys" not in wb.sheetnames

    # Verify Sheet 1 has Exact Recovery and not Key Match
    ws_m = wb["Reconciliation Metrics"]
    header_vals = [cell.value for cell in ws_m[1]]
    assert "Exact Recovery" in header_vals
    assert "Key Match" not in header_vals

    # Verify text format '@' is set for bitstrings in Recovered Bitstreams
    ws_streams = wb["Recovered Bitstreams"]
    for row in ws_streams.iter_rows(min_row=2, max_row=5, min_col=7, max_col=7):
        for cell in row:
            if cell.value is not None:
                assert cell.number_format == "@"


# ==============================================================================
# 10. CLI Full Integration Test & Obsolete Flags Rejection
# ==============================================================================


def test_cli_reconciliation_full(tmp_path: Path) -> None:
    """Verify that CLI executes with --reconcile flag and produces all specified artifacts."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    metrics_csv = tmp_path / "recon_metrics.csv"
    blocks_csv = tmp_path / "recon_blocks.csv"
    config_json = tmp_path / "recon_config.json"
    xlsx_out = tmp_path / "recon_workbook.xlsx"
    fig_prefix = tmp_path / "fig_recon"

    cmd = [
        "-i",
        input_file,
        "--reconcile",
        "--reconcile-metrics-output",
        str(metrics_csv),
        "--reconcile-blocks-output",
        str(blocks_csv),
        "--reconcile-config-output",
        str(config_json),
        "--reconciled-xlsx-output",
        str(xlsx_out),
        "--reconcile-figure-prefix",
        str(fig_prefix),
    ]

    ret = main(cmd)
    assert ret == 0

    assert metrics_csv.exists()
    assert blocks_csv.exists()
    assert config_json.exists()
    assert xlsx_out.exists()
    assert Path(f"{fig_prefix}_reconciliation.png").exists()
    assert Path(f"{fig_prefix}_reconciliation.pdf").exists()


def test_obsolete_cli_options_rejected(capsys: pytest.CaptureFixture) -> None:
    """Verify that obsolete --reconcile-shared and --reconcile-mode flags raise an actionable error."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"

    with pytest.raises(SystemExit) as exc_info1:
        main(["-i", input_file, "--reconcile-shared"])
    assert exc_info1.value.code == 2
    captured1 = capsys.readouterr()
    assert "'--reconcile-shared' is obsolete" in captured1.err

    with pytest.raises(SystemExit) as exc_info2:
        main(["-i", input_file, "--reconcile-mode", "shared_1023"])
    assert exc_info2.value.code == 2
    captured2 = capsys.readouterr()
    assert "'--reconcile-mode' is obsolete" in captured2.err

    with pytest.raises(SystemExit) as exc_info3:
        main(["-i", input_file, "--reconcile-keys-output", "out_keys.json"])
    assert exc_info3.value.code == 2
    captured3 = capsys.readouterr()
    assert "'--reconcile-keys-output' is obsolete" in captured3.err


# ==============================================================================
# 11. Global BCH(1023, 46, 200) Verification Tests
# ==============================================================================


def test_global_bch_code_properties_and_config() -> None:
    """Verify global BCH(1023, 46, 200) code properties and ReconciliationConfig guarantees."""
    bch = get_bch_code(*DEFAULT_BCH_CODE)
    assert bch.n == 1023
    assert bch.k == 46
    assert bch.d == 401
    assert bch.t == 200

    cfg = ReconciliationConfig(seed=42)
    assert cfg.code == (1023, 46, 200)
    assert cfg.get_code_for_path("quant_2bit") == (1023, 46, 200)
    assert cfg.get_code_for_path("prbs_2bit") == (1023, 46, 200)
    assert cfg.interleaving == "OFF"

    meta = cfg.to_metadata_dict()
    assert meta["parameters"]["n"] == 1023
    assert meta["parameters"]["k"] == 46
    assert meta["parameters"]["t"] == 200
    assert meta["parameters"]["designed_d"] == 401
    assert meta["parameters"]["interleaving"] == "OFF"
    assert meta["parameters"]["paths"]["quant_2bit"]["designed_d"] == 401
    assert meta["parameters"]["paths"]["prbs_2bit"]["designed_d"] == 401
    assert meta["parameters"]["paths"]["quant_2bit"]["interleaving"] == "OFF"
    assert meta["parameters"]["paths"]["prbs_2bit"]["interleaving"] == "OFF"


def test_global_bch_reconciliation_exact_recovery_and_exports(tmp_path: Path) -> None:
    """Verify exact Alice-Bob recovery, failure detection, exports, and 2x2 figure under global configuration."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(input_file)
    filtered = filter_rssi_channels(raw_data, FilterConfig())
    quant_res = quantize_channels(filtered, QuantizationConfig())
    prbs_res = expand_channels_prbs(quant_res, PRBSConfig())

    cfg = ReconciliationConfig(seed=42)
    reconcile_res = reconcile_all_paths(quant_res, prbs_res, config=cfg)

    # 1. Verify quant_2bit ground truth
    q_ab = reconcile_res.path_results["quant_2bit"]["Alice–Bob"]
    assert q_ab.n == 1023
    assert q_ab.k == 46
    assert q_ab.t == 200
    assert q_ab.designed_d == 401
    assert q_ab.interleaving == "OFF"
    assert q_ab.exact_recovery is True
    assert q_ab.pre_reconcile_kar == pytest.approx(80.40, abs=0.01)
    assert q_ab.post_reconcile_kar == pytest.approx(100.00, abs=0.01)
    assert q_ab.success_blocks == 1
    assert q_ab.detected_failure_blocks == 0
    assert q_ab.miscorrected_blocks == 0

    q_ea = reconcile_res.path_results["quant_2bit"]["Alice–Eve1-Alice"]
    assert q_ea.exact_recovery is False
    assert q_ea.success_blocks == 0
    assert q_ea.detected_failure_blocks == 1

    # 2. Verify prbs_2bit ground truth
    p_ab = reconcile_res.path_results["prbs_2bit"]["Alice–Bob"]
    assert p_ab.n == 1023
    assert p_ab.k == 46
    assert p_ab.t == 200
    assert p_ab.designed_d == 401
    assert p_ab.interleaving == "OFF"
    assert p_ab.exact_recovery is True
    assert p_ab.pre_reconcile_kar == pytest.approx(76.2667, abs=0.01)
    assert p_ab.post_reconcile_kar == pytest.approx(100.00, abs=0.01)
    assert p_ab.success_blocks == 2
    assert p_ab.detected_failure_blocks == 0
    assert p_ab.miscorrected_blocks == 0

    p_ea = reconcile_res.path_results["prbs_2bit"]["Alice–Eve1-Alice"]
    assert p_ea.exact_recovery is False
    assert p_ea.success_blocks == 1
    assert p_ea.detected_failure_blocks == 1

    # 3. Test Exports & Figures
    csv_metrics = tmp_path / "recon_metrics.csv"
    csv_blocks = tmp_path / "recon_blocks.csv"
    json_config = tmp_path / "recon_config.json"
    xlsx_wb = tmp_path / "recon_workbook.xlsx"
    fig_prefix = tmp_path / "recon_figure"

    export_reconciliation_metrics_csv(reconcile_res, csv_metrics)
    export_reconciliation_blocks_csv(reconcile_res, csv_blocks)
    export_reconciliation_config_json(reconcile_res, json_config)
    export_reconciliation_workbook_xlsx(reconcile_res, xlsx_wb)
    png_p, pdf_p = plot_reconciliation_figure(reconcile_res, fig_prefix)

    assert csv_metrics.exists()
    assert csv_blocks.exists()
    assert json_config.exists()
    assert xlsx_wb.exists()
    assert png_p.exists() and png_p.stat().st_size > 10000
    assert pdf_p.exists() and pdf_p.stat().st_size > 10000

    # Check that CSV contains designed_d and interleaving columns
    with open(csv_metrics, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 6
        for r in rows:
            assert r["n"] == "1023"
            assert r["k"] == "46"
            assert r["t"] == "200"
            assert r["designed_d"] == "401"
            assert r["interleaving"] == "OFF"
