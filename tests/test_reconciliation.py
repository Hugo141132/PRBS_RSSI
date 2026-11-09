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
import galois

from rssi_skg.cli import main, run_correlation_analysis
from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import plot_reconciliation_figure, plot_shared_bch_figure
from rssi_skg.prbs import MultiChannelPRBSResult, PRBSConfig, expand_channels_prbs
from rssi_skg.quantization import CODE_4BIT_MAP, ChannelQuantizationResult, QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import (
    DEFAULT_BCH_CODE,
    DEFAULT_BCH_CODE_2BIT,
    DEFAULT_BCH_CODE_4BIT,
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
    # Test 2-bit default: BCH(511, 1, 198)
    bch_2bit = get_bch_code(*DEFAULT_BCH_CODE_2BIT)
    assert bch_2bit.n == 511
    assert bch_2bit.k == 1
    assert bch_2bit.t == 198
    assert bch_2bit.d == 397

    # Test 4-bit default: BCH(255, 9, 62)
    bch_4bit = get_bch_code(*DEFAULT_BCH_CODE_4BIT)
    assert bch_4bit.n == 255
    assert bch_4bit.k == 9
    assert bch_4bit.t == 62
    assert bch_4bit.d == 125

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
    assert get_bch_code(511, 1, 198) is bch_2bit
    assert get_bch_code(255, 9, 62) is bch_4bit
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
    """Verify BCH reconciliation across all 4 supported paths and rejection of obsolete options."""
    _, quant_res, prbs_res = pipeline_results

    rec_cfg = ReconciliationConfig(seed=42)
    rec_result = reconcile_all_paths(
        quant_result=quant_res,
        prbs_result=prbs_res,
        config=rec_cfg,
    )

    # 4 supported paths * 3 evaluated pairs = 12 metrics
    assert len(rec_result.metrics) == 12

    metrics_by_key = {(m.path, m.pair): m for m in rec_result.metrics}

    # Path 1: quant_2bit (Shared BCH 511, 1, 198)
    ab_q2 = metrics_by_key[("quant_2bit", "Alice–Bob")]
    assert ab_q2.pre_kar == pytest.approx(80.40, abs=0.01)
    assert ab_q2.post_kar == 100.00
    assert ab_q2.exact_recovery is True
    assert ab_q2.successful_blocks == 2
    assert ab_q2.detected_failures == 0
    assert ab_q2.miscorrected_blocks == 0

    # Path 2: quant_4bit (BCH 255, 9, 62)
    ab_q4 = metrics_by_key[("quant_4bit", "Alice–Bob")]
    assert ab_q4.pre_kar == pytest.approx(90.20, abs=0.01)
    assert ab_q4.post_kar == 100.00
    assert ab_q4.exact_recovery is True
    assert ab_q4.successful_blocks == 8
    assert ab_q4.detected_failures == 0
    assert ab_q4.miscorrected_blocks == 0

    # Path 3: prbs_2bit (BCH 511, 1, 198)
    ab_p2 = metrics_by_key[("prbs_2bit", "Alice–Bob")]
    assert ab_p2.pre_kar == pytest.approx(75.85, abs=0.01)
    assert ab_p2.post_kar == 100.00
    assert ab_p2.exact_recovery is True
    assert ab_p2.successful_blocks == 8
    assert ab_p2.detected_failures == 0
    assert ab_p2.miscorrected_blocks == 0

    # Path 4: prbs_4bit (BCH 255, 9, 62)
    ab_p4 = metrics_by_key[("prbs_4bit", "Alice–Bob")]
    assert ab_p4.pre_kar == pytest.approx(86.20, abs=0.01)
    assert ab_p4.post_kar == 100.00
    assert ab_p4.exact_recovery is True
    assert ab_p4.successful_blocks == 16
    assert ab_p4.detected_failures == 0
    assert ab_p4.miscorrected_blocks == 0

    # Explicit rejection of obsolete reconciliation options
    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(code_quant_2bit=(31, 1, 15))  # type: ignore

    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(code_prbs_2bit=(127, 1, 63))  # type: ignore

    with pytest.raises(ValueError, match="is obsolete and has been removed"):
        ReconciliationConfig(mode="shared_1023")  # type: ignore

    with pytest.raises(ValueError, match="Unknown path name"):
        rec_cfg.get_code_for_path("invalid_path")


def test_paths_use_identical_parameters() -> None:
    """Verify that 2-bit paths use BCH(511,1,198) and 4-bit paths route to shared BCH(255,9,62)."""
    cfg = ReconciliationConfig()
    code_q2 = cfg.get_code_for_path("quant_2bit")
    code_q4 = cfg.get_code_for_path("quant_4bit")
    code_p2 = cfg.get_code_for_path("prbs_2bit")
    code_p4 = cfg.get_code_for_path("prbs_4bit")
    assert code_q2 == code_p2 == DEFAULT_BCH_CODE_2BIT == (511, 1, 198)
    assert code_q4 == code_p4 == DEFAULT_BCH_CODE_4BIT == (255, 9, 62)

    # Independent configuration per path family
    custom_cfg = ReconciliationConfig(code_2bit=(31, 1, 15), code_4bit=(255, 9, 62))
    assert custom_cfg.code_2bit == (31, 1, 15)
    assert custom_cfg.code_4bit == (255, 9, 62)
    assert custom_cfg.get_code_for_path("quant_2bit") == (31, 1, 15)
    assert custom_cfg.get_code_for_path("prbs_2bit") == (31, 1, 15)
    assert custom_cfg.get_code_for_path("quant_4bit") == (255, 9, 62)
    assert custom_cfg.get_code_for_path("prbs_4bit") == (255, 9, 62)


def test_second_small_valid_bch_configuration() -> None:
    """Verify that editing ReconciliationConfig with a global valid BCH configuration works cleanly."""
    valid_small = (15, 7, 2)
    cfg = ReconciliationConfig(code=valid_small)
    assert cfg.code == valid_small
    assert cfg.get_code_for_path("quant_2bit") == valid_small
    assert cfg.get_code_for_path("quant_4bit") == valid_small
    assert cfg.get_code_for_path("prbs_2bit") == valid_small
    assert cfg.get_code_for_path("prbs_4bit") == valid_small

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

    # 1. Summary metrics CSV (4 paths * 3 pairs = 12 rows)
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
        assert len(reader) == 12
        for row in reader:
            if row["path"] in ("quant_2bit", "prbs_2bit"):
                assert row["n"] == "511"
                assert row["k"] == "1"
                assert row["t"] == "198"
                assert row["designed_d"] == "397"
            else:
                assert row["n"] == "255"
                assert row["k"] == "9"
                assert row["t"] == "62"
                assert row["designed_d"] == "125"
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
        assert "quant_4bit" in data["parameters"]["paths"]
        assert "prbs_2bit" in data["parameters"]["paths"]
        assert "prbs_4bit" in data["parameters"]["paths"]
        assert data["parameters"]["paths"]["quant_2bit"]["n"] == 511
        assert data["parameters"]["paths"]["quant_2bit"]["designed_d"] == 397
        assert data["parameters"]["paths"]["quant_4bit"]["n"] == 255
        assert data["parameters"]["paths"]["quant_4bit"]["designed_d"] == 125

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
# 11. Global BCH Verification Tests: 2-bit BCH(511,1,198) & 4-bit BCH(255,9,62)
# ==============================================================================


def test_global_bch_code_properties_and_config() -> None:
    """Verify default BCH code properties and ReconciliationConfig guarantees."""
    bch_2bit = get_bch_code(*DEFAULT_BCH_CODE_2BIT)
    assert bch_2bit.n == 511
    assert bch_2bit.k == 1
    assert bch_2bit.d == 397
    assert bch_2bit.t == 198

    bch_4bit = get_bch_code(*DEFAULT_BCH_CODE_4BIT)
    assert bch_4bit.n == 255
    assert bch_4bit.k == 9
    assert bch_4bit.d == 125
    assert bch_4bit.t == 62

    cfg = ReconciliationConfig(seed=42)
    assert cfg.get_code_for_path("quant_2bit") == (511, 1, 198)
    assert cfg.get_code_for_path("quant_4bit") == (255, 9, 62)
    assert cfg.get_code_for_path("prbs_2bit") == (511, 1, 198)
    assert cfg.get_code_for_path("prbs_4bit") == (255, 9, 62)
    assert cfg.interleaving == "OFF"

    meta = cfg.to_metadata_dict()
    assert meta["parameters"]["paths"]["quant_2bit"]["designed_d"] == 397
    assert meta["parameters"]["paths"]["quant_4bit"]["designed_d"] == 125
    assert meta["parameters"]["paths"]["prbs_2bit"]["designed_d"] == 397
    assert meta["parameters"]["paths"]["prbs_4bit"]["designed_d"] == 125
    assert meta["parameters"]["paths"]["quant_2bit"]["interleaving"] == "OFF"
    assert meta["parameters"]["paths"]["quant_4bit"]["interleaving"] == "OFF"
    assert meta["parameters"]["paths"]["prbs_2bit"]["interleaving"] == "OFF"
    assert meta["parameters"]["paths"]["prbs_4bit"]["interleaving"] == "OFF"


def test_global_bch_reconciliation_exact_recovery_and_exports(tmp_path: Path) -> None:
    """Verify exact Alice-Bob recovery, failure detection, exports, and figure under configured BCH."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(input_file)
    filtered = filter_rssi_channels(raw_data, FilterConfig())
    quant_res = quantize_channels(filtered, QuantizationConfig())
    prbs_res = expand_channels_prbs(quant_res, PRBSConfig())

    cfg = ReconciliationConfig(seed=42)
    reconcile_res = reconcile_all_paths(quant_res, prbs_res, config=cfg)

    # 1. Verify quant_2bit ground truth (BCH(511,1,198))
    q_ab = reconcile_res.path_results["quant_2bit"]["Alice–Bob"]
    assert q_ab.n == 511
    assert q_ab.k == 1
    assert q_ab.t == 198
    assert q_ab.designed_d == 397
    assert q_ab.interleaving == "OFF"
    assert q_ab.exact_recovery is True
    assert q_ab.pre_reconcile_kar == pytest.approx(80.40, abs=0.01)
    assert q_ab.post_reconcile_kar == pytest.approx(100.00, abs=0.01)
    assert q_ab.success_blocks == 2
    assert q_ab.detected_failure_blocks == 0
    assert q_ab.miscorrected_blocks == 0

    # 2. Verify quant_4bit ground truth (BCH(255,9,62))
    q4_ab = reconcile_res.path_results["quant_4bit"]["Alice–Bob"]
    assert q4_ab.n == 255
    assert q4_ab.k == 9
    assert q4_ab.t == 62
    assert q4_ab.designed_d == 125
    assert q4_ab.exact_recovery is True
    assert q4_ab.post_reconcile_kar == pytest.approx(100.00, abs=0.01)
    assert q4_ab.success_blocks == 8
    assert q4_ab.detected_failure_blocks == 0
    assert q4_ab.miscorrected_blocks == 0

    # Eve fails exact recovery on quant_4bit
    q4_ea = reconcile_res.path_results["quant_4bit"]["Alice–Eve1-Alice"]
    assert q4_ea.exact_recovery is False
    assert q4_ea.detected_failure_blocks == 3
    q4_eb = reconcile_res.path_results["quant_4bit"]["Bob–Eve1-Bob"]
    assert q4_eb.exact_recovery is False
    assert q4_eb.detected_failure_blocks == 3
    assert q4_eb.success_blocks == 5

    # 3. Verify prbs_2bit ground truth (BCH(511,1,198))
    p_ab = reconcile_res.path_results["prbs_2bit"]["Alice–Bob"]
    assert p_ab.n == 511
    assert p_ab.k == 1
    assert p_ab.t == 198
    assert p_ab.designed_d == 397
    assert p_ab.interleaving == "OFF"
    assert p_ab.exact_recovery is True
    assert p_ab.pre_reconcile_kar == pytest.approx(75.85, abs=0.01)
    assert p_ab.post_reconcile_kar == pytest.approx(100.00, abs=0.01)
    assert p_ab.success_blocks == 8
    assert p_ab.detected_failure_blocks == 0
    assert p_ab.miscorrected_blocks == 0

    # 4. Verify prbs_4bit ground truth (BCH(255,9,62))
    p4_ab = reconcile_res.path_results["prbs_4bit"]["Alice–Bob"]
    assert p4_ab.n == 255
    assert p4_ab.k == 9
    assert p4_ab.t == 62
    assert p4_ab.designed_d == 125
    assert p4_ab.exact_recovery is True
    assert p4_ab.post_reconcile_kar == pytest.approx(100.00, abs=0.01)
    assert p4_ab.success_blocks == 16
    assert p4_ab.detected_failure_blocks == 0
    assert p4_ab.miscorrected_blocks == 0

    # Eve fails exact recovery on prbs_4bit
    p4_ea = reconcile_res.path_results["prbs_4bit"]["Alice–Eve1-Alice"]
    assert p4_ea.exact_recovery is False
    assert p4_ea.detected_failure_blocks == 9
    p4_eb = reconcile_res.path_results["prbs_4bit"]["Bob–Eve1-Bob"]
    assert p4_eb.exact_recovery is False
    assert p4_eb.detected_failure_blocks == 9
    assert p4_eb.success_blocks == 7

    # 5. Test Exports & Figures
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

    # Check that CSV contains designed_d and interleaving columns (12 rows for 4 paths * 3 pairs)
    with open(csv_metrics, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 12
        for r in rows:
            if r["path"] in ("quant_2bit", "prbs_2bit"):
                assert r["n"] == "511"
                assert r["k"] == "1"
                assert r["t"] == "198"
                assert r["designed_d"] == "397"
            else:
                assert r["n"] == "255"
                assert r["k"] == "9"
                assert r["t"] == "62"
                assert r["designed_d"] == "125"
            assert r["interleaving"] == "OFF"


def test_eavesdropper_threat_model_helper_data_reuse_and_isolation(pipeline_results: tuple) -> None:
    """Regression test proving:
    1. Source-specific helper data:
       - Alice generates helper data used for Alice–Bob (legitimate) and Alice–Eve1-Alice (passive observer).
       - Bob generates independent helper data used for Bob–Eve1-Bob (passive observer).
    2. Receiver isolation:
       - Bob reconstructs against Alice's helper data and Alice's source bits.
       - Eve1-Alice reconstructs against Alice's helper data and Alice's source bits.
       - Eve1-Bob reconstructs against Bob's separate helper data and Bob's source bits.
    3. Passive receiver isolation: Eve only accesses her own observation bits and the respective source helper data.
    4. Evaluated pairs match established measurements: Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob.
    """
    _, quant_res, prbs_res = pipeline_results
    rec_cfg = ReconciliationConfig(seed=42)
    rec_res = reconcile_all_paths(quant_res, prbs_res, config=rec_cfg)

    for path_name in ["quant_2bit", "quant_4bit", "prbs_2bit", "prbs_4bit"]:
        p_res = rec_res.path_results[path_name]

        # Exact 3 pairs evaluated: Alice–Bob, Alice–Eve1-Alice, Bob–Eve1-Bob
        assert set(p_res.keys()) == {"Alice–Bob", "Alice–Eve1-Alice", "Bob–Eve1-Bob"}
        assert "Alice–Eve1-Bob" not in p_res

        res_ab = p_res["Alice–Bob"]
        res_ea = p_res["Alice–Eve1-Alice"]
        res_eb = p_res["Bob–Eve1-Bob"]

        # Source-specific helper data & reference bits
        assert res_ab.source_name == "Alice"
        assert res_ea.source_name == "Alice"
        assert res_eb.source_name == "Bob"

        assert res_ab.source_unpadded == res_ea.source_unpadded
        assert res_ab.receiver_name == "Bob"
        assert res_ea.receiver_name == "Eve1-Alice"
        assert res_eb.receiver_name == "Eve1-Bob"

        # Padding counts and block counts match path requirements
        assert res_ab.padding_count == res_ea.padding_count == res_eb.padding_count
        assert res_ab.num_blocks == res_ea.num_blocks == res_eb.num_blocks

        # Verify exact code parameters, block counts, and padding per path
        if path_name == "quant_2bit":
            assert res_ab.n == 511
            assert res_ab.k == 1
            assert res_ab.t == 198
            assert res_ab.designed_d == 397
            assert res_ab.num_blocks == 2
            assert res_ab.padding_count == 22
        elif path_name == "quant_4bit":
            assert res_ab.n == 255
            assert res_ab.k == 9
            assert res_ab.t == 62
            assert res_ab.designed_d == 125
            assert res_ab.num_blocks == 8
            assert res_ab.padding_count == 40
        elif path_name == "prbs_2bit":
            assert res_ab.n == 511
            assert res_ab.k == 1
            assert res_ab.t == 198
            assert res_ab.designed_d == 397
            assert res_ab.num_blocks == 8
            assert res_ab.padding_count == 88
        else:
            assert res_ab.n == 255
            assert res_ab.k == 9
            assert res_ab.t == 62
            assert res_ab.designed_d == 125
            assert res_ab.num_blocks == 16
            assert res_ab.padding_count == 80

        # Passive receiver isolation: Receiver bits are strictly the independent channel bits
        if path_name == "quant_2bit":
            assert res_ab.receiver_raw_unpadded == quant_res.bitstreams_2bit["Bob"]
            assert res_ea.receiver_raw_unpadded == quant_res.bitstreams_2bit["Eve1-Alice"]
            assert res_eb.receiver_raw_unpadded == quant_res.bitstreams_2bit["Eve1-Bob"]
        elif path_name == "quant_4bit":
            assert res_ab.receiver_raw_unpadded == quant_res.bitstreams_4bit["Bob"]
            assert res_ea.receiver_raw_unpadded == quant_res.bitstreams_4bit["Eve1-Alice"]
            assert res_eb.receiver_raw_unpadded == quant_res.bitstreams_4bit["Eve1-Bob"]
        elif path_name == "prbs_2bit":
            assert res_ab.receiver_raw_unpadded == prbs_res.channels["Bob"].bitstream_2bit
            assert res_ea.receiver_raw_unpadded == prbs_res.channels["Eve1-Alice"].bitstream_2bit
            assert res_eb.receiver_raw_unpadded == prbs_res.channels["Eve1-Bob"].bitstream_2bit
        else:
            assert res_ab.receiver_raw_unpadded == prbs_res.channels["Bob"].bitstream_4bit
            assert res_ea.receiver_raw_unpadded == prbs_res.channels["Eve1-Alice"].bitstream_4bit
            assert res_eb.receiver_raw_unpadded == prbs_res.channels["Eve1-Bob"].bitstream_4bit

        # Legitimate channel reaches 100% KAR; both Eve streams fail exact recovery
        assert res_ab.exact_recovery is True
        assert res_ea.exact_recovery is False
        assert res_eb.exact_recovery is False


def test_bounded_public_helper_candidate_check(pipeline_results: tuple) -> None:
    """Verify bounded public-helper candidate check on BCH(255, 9, 63).

    Confirms that:
    1. Pre-enumerating all 512 codewords of BCH(255, 9, 63) is bounded and fast.
    2. Candidate blocks A_cand = H XOR C can be filtered using strictly public constraints
       (known trailing zero-padding and CODE_4BIT_MAP alphabet prefix '10').
    3. Filtering reduces the 512 candidates to a single unique candidate matching Alice's block,
       proving that decoder failure and small k (k=9) do not establish cryptographic secrecy.
    """
    _, quant_res, _ = pipeline_results
    alice_q4 = quant_res.bitstreams_4bit["Alice"]
    bch = get_bch_code(255, 9, 63)

    # 1. Enumerate all 512 codewords once
    messages = np.array([[int(b) for b in f"{m:09b}"] for m in range(512)], dtype=np.uint8)
    codewords = np.array(bch.encode(messages), dtype=np.uint8)
    assert codewords.shape == (512, 255)

    # 2. Generate Alice's helper data
    rng = np.random.default_rng(42)
    helper_blocks, orig_len, pad_count = generate_helper_data(alice_q4, 255, 9, 63, rng=rng)
    assert orig_len == 2000
    assert len(helper_blocks) == 8
    assert pad_count == 40

    # 3. Verify linear constraint rank on generator matrix G
    # Having known bits only constrains the message space if G[:, known_indices] has full row rank (rank 9).
    # For Block 7, the 40 trailing zero-padding columns have rank 9 over GF(2):
    pad_cols = np.arange(215, 255)
    G_pad = bch.G[:, pad_cols]
    assert np.linalg.matrix_rank(galois.GF(2)(G_pad)) == 9

    # For Block 0, the fixed '10' prefixes on sample positions (128 bits) have rank 9 over GF(2):
    fixed_pos_0 = []
    for s in range(63):
        fixed_pos_0.extend([s * 4, s * 4 + 1])
    fixed_pos_0.extend([252, 253])
    G_fixed_0 = bch.G[:, fixed_pos_0]
    assert np.linalg.matrix_rank(galois.GF(2)(G_fixed_0)) == 9

    # 4. Check final block (Block 7) with 40 known zero padding bits
    H_final = helper_blocks[7]
    true_A_final = np.fromiter(alice_q4[7 * 255 : 2000] + "0" * 40, dtype=np.uint8)
    candidates_final = H_final ^ codewords

    # Filter by 40 trailing zero padding bits (public knowledge only)
    pad_match = np.all(candidates_final[:, 215:255] == 0, axis=1)
    survivors_final = np.where(pad_match)[0]

    # Full row rank ensures 40 linear constraints on 9-bit message space leave exactly 1 candidate
    assert len(survivors_final) == 1
    # Ground truth is used strictly AFTER selection to verify accuracy
    assert np.array_equal(candidates_final[survivors_final[0]], true_A_final)

    # 5. Check Block 0 with 63 full 4-bit samples using full public CODE_4BIT_MAP
    H_0 = helper_blocks[0]
    true_A_0 = np.fromiter(alice_q4[:255], dtype=np.uint8)
    candidates_0 = np.array(H_0, dtype=np.uint8) ^ codewords

    # Public 4-bit quantizer alphabet per PA.pdf Eq (3.23) and CODE_4BIT_MAP
    valid_symbols = {tuple(int(b) for b in s) for s in CODE_4BIT_MAP.values()}
    assert len(valid_symbols) == 3
    valid_survivors_0 = []
    for idx in range(512):
        cand = candidates_0[idx]
        cand_valid = True
        for s in range(63):
            sample_tuple = tuple(cand[s * 4 : (s + 1) * 4])
            if sample_tuple not in valid_symbols:
                cand_valid = False
                break
        if cand_valid:
            valid_survivors_0.append(idx)

    assert len(valid_survivors_0) == 1
    assert np.array_equal(candidates_0[valid_survivors_0[0]], true_A_0)

    # 6. Verify prbs_4bit Block 15 (80 trailing padding bits)
    _, _, prbs_res = pipeline_results
    alice_p4 = prbs_res.channels["Alice"].bitstream_4bit
    h_p4, orig_len_p4, pad_p4 = generate_helper_data(alice_p4, 255, 9, 63, rng=rng)
    assert orig_len_p4 == 4000
    assert len(h_p4) == 16
    assert pad_p4 == 80

    H_p15 = h_p4[15]
    true_Ap15 = np.fromiter(alice_p4[15 * 255 : 4000] + "0" * 80, dtype=np.uint8)
    cands_p15 = H_p15 ^ codewords
    pad_match_p15 = np.all(cands_p15[:, 175:255] == 0, axis=1)
    survivors_p15 = np.where(pad_match_p15)[0]
    assert len(survivors_p15) == 1
    assert np.array_equal(cands_p15[survivors_p15[0]], true_Ap15)
