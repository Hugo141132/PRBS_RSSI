"""Unit tests for Stage 6 — Privacy Amplification (PA.pdf Section 3.2.6).

Verifies:
1. 100-bit non-overlapping segmentation and dynamic chunk count derivation across all 4 paths:
   - quant_2bit: 1,000 bits -> 10 keys
   - quant_4bit: 2,000 bits -> 20 keys
   - prbs_2bit:  4,000 bits -> 40 keys
   - prbs_4bit:  4,000 bits -> 40 keys
2. Explicit rejection of incomplete segments, empty bitstreams, and non-binary inputs.
3. FIPS PUB 180-4 bit-level padding correctness for arbitrary bit lengths (L=100, L=1000, L=4000).
4. Standard NIST SHA-256 test vectors (empty string, 'abc', 448-bit message).
5. Parity checks against hashlib.sha256 for byte-aligned bitstreams.
6. Cryptographic avalanche effect (1-bit input flip alters ~50% of 256 output bits).
7. Channel and receiver isolation across all 4 channels (Alice, Bob, Eve1-Alice, Eve1-Bob).
8. Alice-reference threat model preservation and 4-channel, 3-pair evaluation.
9. Full pipeline evaluation on dummy dataset across all four paths.
10. Artifact exporters (CSV metrics, per-chunk keys CSV, config JSON, companion XLSX preserving '@' text format).
11. Plotting 2x2 comparison figure across all four paths (PNG 300 dpi and vector PDF).
12. CLI integration with --privacy-amplify, auto prerequisite chaining, and --reconcile-keys-output alias.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import openpyxl
import pytest

from rssi_skg.cli import main, run_correlation_analysis
from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import plot_privacy_amplification_figure
from rssi_skg.prbs import PRBSConfig, expand_channels_prbs
from rssi_skg.privacy_amplification import (
    PA_PATHS,
    SCIENTIFIC_DISCLAIMER,
    SEGMENT_SIZE_BITS,
    ChannelPrivacyAmplificationResult,
    ChunkKeyResult,
    ChunkPairPAResult,
    MultiPathPrivacyAmplificationResult,
    PairPrivacyAmplificationResult,
    PrivacyAmplificationConfig,
    amplify_privacy_all_paths,
    export_pa_config_json,
    export_pa_keys_csv,
    export_pa_metrics_csv,
    export_pa_workbook_xlsx,
    pad_bitstream,
    segment_bitstream,
    sha256_bitstream,
    verify_against_hashlib,
)
from rssi_skg.quantization import QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import ReconciliationConfig, reconcile_all_paths


# ==============================================================================
# 1. 100-Bit Segmentation & Incomplete Segment Rejection
# ==============================================================================


def test_segment_bitstream_valid_lengths() -> None:
    """Verify consecutive non-overlapping 100-bit segmentation across all 4 path lengths."""
    for total_bits, expected_chunks in [(1000, 10), (2000, 20), (4000, 40)]:
        raw_bits = "10" * (total_bits // 2)
        segments = segment_bitstream(raw_bits, segment_size=100)
        assert len(segments) == expected_chunks
        # Verify temporal order and exact length
        assert "".join(segments) == raw_bits
        for idx, seg in enumerate(segments):
            assert len(seg) == 100
            assert seg == raw_bits[idx * 100 : (idx + 1) * 100]


def test_segment_bitstream_rejects_incomplete_segments() -> None:
    """Verify that incomplete segments are rejected explicitly (never silently truncated or padded)."""
    for invalid_len in [1, 50, 99, 101, 150, 999, 1001, 1999, 2001, 3999, 4001]:
        raw_bits = "1" * invalid_len
        with pytest.raises(ValueError, match="not an exact multiple of segment size"):
            segment_bitstream(raw_bits, segment_size=100)


def test_segment_bitstream_rejects_invalid_inputs() -> None:
    """Verify that empty bitstreams and non-binary inputs raise ValueError."""
    with pytest.raises(ValueError, match="Cannot segment an empty bitstream"):
        segment_bitstream("")

    with pytest.raises(ValueError, match="only '0' and '1'"):
        segment_bitstream("10102010" * 15)

    with pytest.raises(ValueError, match="only binary integers"):
        segment_bitstream([1, 0, 2, 1] * 25)

    with pytest.raises(ValueError, match="positive integer"):
        segment_bitstream("1" * 100, segment_size=0)


# ==============================================================================
# 2. Bit-Level Padding Correctness (FIPS 180-4 & PA.pdf Eqs 3.37–3.39)
# ==============================================================================


def test_sha256_padding_arbitrary_lengths() -> None:
    """Verify bit-level padding for arbitrary lengths including L=100, L=1000, and L=4000."""
    for L in [0, 1, 7, 8, 100, 447, 448, 511, 512, 1000, 2000, 4000]:
        raw_bits = "10" * (L // 2) + ("1" if L % 2 == 1 else "")
        assert len(raw_bits) == L

        padded = pad_bitstream(raw_bits)
        total_len = len(padded)

        # 1. Total length must be an exact multiple of 512 bits
        assert total_len % 512 == 0
        assert total_len >= 512

        # 2. First L bits match original bitstream
        assert padded[:L] == raw_bits

        # 3. Bit L is '1'
        assert padded[L] == "1"

        # 4. Trailing 64 bits represent L in big-endian binary
        l_64 = format(L, "064b")
        assert padded[-64:] == l_64

        # 5. Intermediate padding bits are all '0'
        p = (448 - 1 - L) % 512
        zero_part = padded[L + 1 : -64]
        assert len(zero_part) == p
        assert set(zero_part).issubset({"0"})


def test_sha256_padding_segment_100_bits() -> None:
    """Verify exact bit-level padding for a 100-bit segment (PA stage building block)."""
    raw_100 = "10" * 50
    assert len(raw_100) == 100
    padded = pad_bitstream(raw_100)
    # L=100, p = (448 - 1 - 100) % 512 = 347. Total = 100 + 1 + 347 + 64 = 512 bits (1 block)
    assert len(padded) == 512
    assert padded[:100] == raw_100
    assert padded[100] == "1"
    assert padded[101:448] == "0" * 347
    assert padded[448:] == format(100, "064b")


# ==============================================================================
# 3. NIST Standard Test Vectors & hashlib.sha256 Parity
# ==============================================================================


def test_sha256_nist_standard_vectors() -> None:
    """Verify known independently-sourced NIST SHA-256 test vectors."""
    # 1. NIST CAVP Len = 0: Msg = 00 ("")
    key_bin, key_hex = sha256_bitstream("")
    assert len(key_bin) == 256
    assert len(key_hex) == 64
    assert key_hex == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # 2. NIST CAVP Len = 1: Msg = 00 ("0")
    _, key_hex_1 = sha256_bitstream("0")
    assert key_hex_1 == "bd4f9e98beb68c6ead3243b1b4c7fed75fa4feaab1f84795cbd8a98676a2a375"

    # 3. NIST CAVP Len = 2: Msg = 80 ("10")
    _, key_hex_2 = sha256_bitstream("10")
    assert key_hex_2 == "18f331f626210ff9bad6995d8cff6e891adba50eb2fdbddcaa921221cdc333ae"

    # 4. FIPS 180-4 Section B.1 byte-aligned test vector: "abc" (24 bits)
    abc_bits = "".join(format(ord(c), "08b") for c in "abc")
    assert len(abc_bits) == 24
    _, key_hex_abc = sha256_bitstream(abc_bits)
    assert key_hex_abc == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    # 5. FIPS 180-4 Section B.2 block boundary test vector: 448 bits
    msg_str = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
    msg_bits = "".join(format(ord(c), "08b") for c in msg_str)
    assert len(msg_bits) == 448
    _, key_hex_msg = sha256_bitstream(msg_bits)
    assert key_hex_msg == "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
    assert key_hex_msg == hashlib.sha256(msg_str.encode("utf-8")).hexdigest()


def test_parity_check_with_hashlib() -> None:
    """Verify complete parity between bitstream SHA-256 and hashlib.sha256 for byte multiples."""
    rng = np.random.default_rng(2026)
    for num_bytes in [1, 2, 8, 16, 64, 125, 250, 500]:
        raw_bytes = bytes(rng.integers(0, 256, size=num_bytes, dtype=np.uint8))
        bitstream = "".join(format(b, "08b") for b in raw_bytes)
        assert len(bitstream) == num_bytes * 8
        assert verify_against_hashlib(bitstream) is True
        _, our_hex = sha256_bitstream(bitstream)
        ref_hex = hashlib.sha256(raw_bytes).hexdigest()
        assert our_hex == ref_hex


# ==============================================================================
# 4. Cryptographic Avalanche Effect Verification
# ==============================================================================


def test_cryptographic_avalanche_effect() -> None:
    """Verify statistical bit-diffusion property on 1-bit input flip for 100-bit segments."""
    rng = np.random.default_rng(999)
    base_bits = list(rng.integers(0, 2, size=100))
    base_str = "".join(str(b) for b in base_bits)

    k_base_bin, _ = sha256_bitstream(base_str)

    # Test flipping bits at multiple locations (start, middle, end)
    for flip_idx in [0, 25, 50, 75, 99]:
        flipped_bits = list(base_bits)
        flipped_bits[flip_idx] ^= 1
        flipped_str = "".join(str(b) for b in flipped_bits)

        k_flipped_bin, _ = sha256_bitstream(flipped_str)
        mismatches = sum(1 for a, b in zip(k_base_bin, k_flipped_bin) if a != b)
        flip_percentage = (mismatches / 256.0) * 100.0

        # Strict avalanche criterion check: ~50% bit flip
        assert 40.0 <= flip_percentage <= 60.0
        assert 102 <= mismatches <= 154


# ==============================================================================
# 5. Channel and Receiver Isolation
# ==============================================================================


def test_channel_isolation() -> None:
    """Verify that each channel's key is derived strictly from its own bitstream without cross-contamination."""
    alice_bits = "10" * 50  # 100 bits
    bob_bits = "10" * 50
    eve_bits = "01" * 50

    k_a_bin, k_a_hex = sha256_bitstream(alice_bits)
    k_b_bin, k_b_hex = sha256_bitstream(bob_bits)
    k_e_bin, k_e_hex = sha256_bitstream(eve_bits)

    # Identical bitstreams yield identical keys
    assert k_a_bin == k_b_bin
    assert k_a_hex == k_b_hex

    # Different bitstream yields completely different key (avalanche)
    assert k_a_hex != k_e_hex
    mismatches = sum(1 for a, b in zip(k_a_bin, k_e_bin) if a != b)
    assert mismatches > 100


# ==============================================================================
# 6. Full Four-Path Ground-Truth Pipeline Verification (Dummy Dataset)
# ==============================================================================


def test_full_pipeline_privacy_amplification_dummy_dataset() -> None:
    """Verify 100-bit segmented PA across all four supported paths on the dummy dataset."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(input_file)
    filtered = filter_rssi_channels(raw_data, FilterConfig())
    quant_res = quantize_channels(filtered, QuantizationConfig())
    prbs_res = expand_channels_prbs(quant_res, PRBSConfig())
    reconcile_res = reconcile_all_paths(quant_res, prbs_res, ReconciliationConfig(seed=42))

    cfg = PrivacyAmplificationConfig()
    pa_res = amplify_privacy_all_paths(reconcile_result=reconcile_res, config=cfg)

    assert cfg.hash_algorithm == "SHA-256"
    assert cfg.key_length_bits == 256
    assert cfg.segment_size_bits == 100
    assert cfg.supported_paths == ("quant_2bit", "quant_4bit", "prbs_2bit", "prbs_4bit")

    expected_path_specs = {
        "quant_2bit": {"bits": 1000, "chunks": 10},
        "quant_4bit": {"bits": 2000, "chunks": 20},
        "prbs_2bit": {"bits": 4000, "chunks": 40},
        "prbs_4bit": {"bits": 4000, "chunks": 40},
    }

    for path_name, spec in expected_path_specs.items():
        assert path_name in pa_res.pair_results
        p_pairs = pa_res.pair_results[path_name]

        # 1. Alice–Bob (legitimate)
        ab = p_pairs["Alice–Bob"]
        assert ab.input_bit_length == spec["bits"]
        assert ab.num_chunks == spec["chunks"]
        assert ab.chunk_size_bits == 100
        assert ab.pre_pa_kar == pytest.approx(100.00, abs=0.01)
        assert ab.post_pa_kar == pytest.approx(100.00, abs=0.01)
        assert ab.exact_key_match is True
        assert ab.exact_match_count == spec["chunks"]
        assert ab.exact_match_rate_percent == 100.0
        assert ab.mismatched_key_bits == 0
        for ck in ab.chunk_results:
            assert ck.exact_key_match is True
            assert ck.post_pa_kar == 100.0
            assert ck.source_key_hex == ck.receiver_key_hex

        # 2. Alice–Eve1-Alice (eavesdropper stream 1)
        ea = p_pairs["Alice–Eve1-Alice"]
        assert ea.input_bit_length == spec["bits"]
        assert ea.num_chunks == spec["chunks"]
        assert ea.is_legitimate is False
        assert ea.exact_key_match is False  # Cannot achieve 100% match across all chunks

        # 3. Bob–Eve1-Bob (eavesdropper stream 2)
        eb = p_pairs["Bob–Eve1-Bob"]
        assert eb.input_bit_length == spec["bits"]
        assert eb.num_chunks == spec["chunks"]
        assert eb.is_legitimate is False
        assert eb.source_name == "Bob"
        assert eb.receiver_name == "Eve1-Bob"
        assert eb.exact_key_match is False

        # Channel keys verification
        ch_dict = pa_res.channel_keys[path_name]
        assert set(ch_dict.keys()) == {"Alice", "Bob", "Eve1-Alice", "Eve1-Bob"}
        for ch_name, ch_res in ch_dict.items():
            assert ch_res.num_chunks == spec["chunks"]
            assert ch_res.chunk_size_bits == 100
            assert len(ch_res.chunk_keys) == spec["chunks"]
            for ck in ch_res.chunk_keys:
                assert len(ck.key_bin) == 256
                assert len(ck.key_hex) == 64
                assert len(ck.input_segment_bits) == 100


# ==============================================================================
# 7. Eavesdropper Threat Model & Channel Pair Regression
# ==============================================================================


def test_eavesdropper_threat_model_pa_keys_and_reference_comparison() -> None:
    """Regression test proving:
    1. Exactly 4 channels exist per path (Alice, Bob, Eve1-Alice, Eve1-Bob).
    2. 'Bob (Source)' key does not exist.
    3. Evaluated pairs:
       - Alice–Bob: Alice source keys vs Bob receiver keys.
       - Alice–Eve1-Alice: Alice source keys vs Eve1-Alice receiver keys.
       - Bob–Eve1-Bob: Bob source keys vs Eve1-Bob receiver keys.
    4. Legitimate keys match 100% across all chunks.
    5. Eavesdropper streams fail 100% match across all chunks.
    """
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(input_file)
    filtered = filter_rssi_channels(raw_data, FilterConfig())
    quant_res = quantize_channels(filtered, QuantizationConfig())
    prbs_res = expand_channels_prbs(quant_res, PRBSConfig())
    reconcile_res = reconcile_all_paths(quant_res, prbs_res, ReconciliationConfig(seed=42))
    pa_res = amplify_privacy_all_paths(reconcile_result=reconcile_res)

    for path_name in PA_PATHS:
        ch_keys = pa_res.channel_keys[path_name]
        assert set(ch_keys.keys()) == {"Alice", "Bob", "Eve1-Alice", "Eve1-Bob"}
        assert "Bob (Source)" not in ch_keys

        # Correct channel roles
        assert ch_keys["Alice"].channel_role == "Legitimate Source (Reference Key)"
        assert ch_keys["Bob"].channel_role == "Legitimate Receiver (Reconciled to Alice)"
        assert ch_keys["Eve1-Alice"].channel_role == "Passive Eavesdropper (Overhearing Alice)"
        assert ch_keys["Eve1-Bob"].channel_role == "Passive Eavesdropper (Overhearing Bob)"

        p_pairs = pa_res.pair_results[path_name]
        assert set(p_pairs.keys()) == {"Alice–Bob", "Alice–Eve1-Alice", "Bob–Eve1-Bob"}

        # Pair-specific reference mapping:
        assert p_pairs["Alice–Bob"].source_name == "Alice"
        assert p_pairs["Alice–Bob"].receiver_name == "Bob"

        assert p_pairs["Alice–Eve1-Alice"].source_name == "Alice"
        assert p_pairs["Alice–Eve1-Alice"].receiver_name == "Eve1-Alice"

        assert p_pairs["Bob–Eve1-Bob"].source_name == "Bob"
        assert p_pairs["Bob–Eve1-Bob"].receiver_name == "Eve1-Bob"

        # Verify Bob–Eve1-Bob compares Bob reference digest against Eve1-Bob digest
        bob_k = ch_keys["Bob"].chunk_keys
        eb_k = ch_keys["Eve1-Bob"].chunk_keys
        pair_eb_chunks = p_pairs["Bob–Eve1-Bob"].chunk_results
        for idx in range(len(bob_k)):
            assert pair_eb_chunks[idx].source_key_hex == bob_k[idx].key_hex
            assert pair_eb_chunks[idx].receiver_key_hex == eb_k[idx].key_hex

        # Legitimate keys match 100% across all chunks
        assert p_pairs["Alice–Bob"].exact_key_match is True
        assert ch_keys["Alice"].all_keys_hex == ch_keys["Bob"].all_keys_hex

        # Both Eve streams fail all-chunks match
        assert p_pairs["Alice–Eve1-Alice"].exact_key_match is False
        assert p_pairs["Bob–Eve1-Bob"].exact_key_match is False


# ==============================================================================
# 8. Artifact Exporters & Companion XLSX Text Format Verification
# ==============================================================================


def test_pa_artifact_exporters(tmp_path: Path) -> None:
    """Verify that all Privacy Amplification exporters write valid files with '@' cell formatting."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(input_file)
    filtered = filter_rssi_channels(raw_data, FilterConfig())
    quant_res = quantize_channels(filtered, QuantizationConfig())
    prbs_res = expand_channels_prbs(quant_res, PRBSConfig())
    reconcile_res = reconcile_all_paths(quant_res, prbs_res, ReconciliationConfig(seed=42))
    pa_res = amplify_privacy_all_paths(reconcile_result=reconcile_res)

    csv_metrics = tmp_path / "pa_metrics.csv"
    csv_keys = tmp_path / "pa_keys.csv"
    json_config = tmp_path / "pa_config.json"
    xlsx_wb = tmp_path / "pa_workbook.xlsx"
    fig_prefix = tmp_path / "pa_figure"

    export_pa_metrics_csv(pa_res, csv_metrics)
    export_pa_keys_csv(pa_res, csv_keys)
    export_pa_config_json(pa_res, json_config)
    export_pa_workbook_xlsx(pa_res, xlsx_wb)
    png_p, pdf_p = plot_privacy_amplification_figure(pa_res, fig_prefix)

    # 1. Metrics CSV: 4 paths * 3 pairs = 12 rows
    assert csv_metrics.exists()
    with open(csv_metrics, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 12
        for r in reader:
            assert r["path"] in PA_PATHS
            assert r["key_bits"] == "256"
            assert r["chunk_size_bits"] == "100"
            assert "pre_pa_kar_percent" in r
            assert "post_pa_kar_percent" in r
            assert "exact_match_count" in r
            assert "exact_match_rate_percent" in r

    # 2. Keys CSV: (10 + 20 + 40 + 40) chunks * 4 channels = 110 * 4 = 440 rows
    assert csv_keys.exists()
    with open(csv_keys, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 440
        for r in reader:
            assert len(r["key_bin"]) == 256
            assert len(r["key_hex"]) == 64
            assert len(r["input_segment_bits"]) == 100

    # 3. JSON Config
    assert json_config.exists()
    with open(json_config, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["hash_algorithm"] == "SHA-256"
        assert data["key_length_bits"] == 256
        assert data["segment_size_bits"] == 100
        for p in PA_PATHS:
            assert p in data["privacy_amplification_summary"]

    # 4. Excel Workbook (.xlsx)
    assert xlsx_wb.exists()
    wb = openpyxl.load_workbook(xlsx_wb, data_only=True)
    assert "PA Metrics" in wb.sheetnames
    assert "Per-Chunk Metrics" in wb.sheetnames
    assert "Channel Keys" in wb.sheetnames
    assert "Config & Disclaimers" in wb.sheetnames

    # Check that Text format '@' is explicitly preserved for key cells
    ws_keys = wb["Channel Keys"]
    for row in ws_keys.iter_rows(min_row=2, max_row=15, min_col=7, max_col=8):
        for cell in row:
            assert cell.number_format == "@"

    # 5. Figure plots
    assert png_p.exists() and png_p.stat().st_size > 10000
    assert pdf_p.exists() and pdf_p.stat().st_size > 10000


# ==============================================================================
# 9. CLI Integration with Prerequisite Chaining
# ==============================================================================


def test_cli_privacy_amplification_full(tmp_path: Path) -> None:
    """Verify CLI execution with --privacy-amplify across all 4 paths."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    metrics_csv = tmp_path / "pa_metrics.csv"
    keys_csv = tmp_path / "pa_keys.csv"
    config_json = tmp_path / "pa_config.json"
    xlsx_out = tmp_path / "pa_workbook.xlsx"
    fig_prefix = tmp_path / "fig_pa"

    cmd = [
        "-i",
        input_file,
        "--privacy-amplify",
        "--pa-metrics-output",
        str(metrics_csv),
        "--pa-keys-output",
        str(keys_csv),
        "--pa-config-output",
        str(config_json),
        "--pa-xlsx-output",
        str(xlsx_out),
        "--pa-figure-prefix",
        str(fig_prefix),
    ]

    ret = main(cmd)
    assert ret == 0

    assert metrics_csv.exists()
    assert keys_csv.exists()
    assert config_json.exists()
    assert xlsx_out.exists()
    assert Path(f"{fig_prefix}_pa_comparison.png").exists()
    assert Path(f"{fig_prefix}_pa_comparison.pdf").exists()


def test_cli_pa_candidate_keys_alias(tmp_path: Path) -> None:
    """Verify that candidate-key output flag --reconcile-keys-output is accepted when PA is active."""
    input_file = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    keys_csv = tmp_path / "pa_reconciled_keys.csv"

    cmd = [
        "-i",
        input_file,
        "--privacy-amplify",
        "--reconcile-keys-output",
        str(keys_csv),
    ]

    ret = main(cmd)
    assert ret == 0
    assert keys_csv.exists()
    with open(keys_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 440
