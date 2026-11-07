"""Unit tests for Stage 6 — Privacy Amplification (PA.pdf Section 3.2.6).

Verifies:
1. FIPS PUB 180-4 bit-level padding correctness for arbitrary bit lengths (L=1000, L=1500, etc.).
2. Standard NIST SHA-256 test vectors (empty string, 'abc', 448-bit message).
3. Parity checks against hashlib.sha256 for byte-aligned bitstreams.
4. Native arbitrary bit length support for non-byte-aligned bitstreams (e.g. L=1500).
5. Cryptographic avalanche effect (1-bit input flip alters ~50% of 256 output bits).
6. Channel and receiver isolation.
7. Full pipeline evaluation on dummy dataset across both supported paths (quant_2bit and prbs_2bit).
8. Artifact exporters (CSV metrics, keys CSV, config JSON, and companion XLSX preserving '@' text format).
9. Plotting 2x2 comparison figure (PNG 300 dpi and vector PDF).
10. CLI integration with --privacy-amplify, auto prerequisite chaining, and --reconcile-keys-output alias.
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
    SCIENTIFIC_DISCLAIMER,
    ChannelPrivacyAmplificationResult,
    MultiPathPrivacyAmplificationResult,
    PairPrivacyAmplificationResult,
    PrivacyAmplificationConfig,
    amplify_privacy_all_paths,
    export_pa_config_json,
    export_pa_keys_csv,
    export_pa_metrics_csv,
    export_pa_workbook_xlsx,
    pad_bitstream,
    sha256_bitstream,
    verify_against_hashlib,
)
from rssi_skg.quantization import QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import ReconciliationConfig, reconcile_all_paths


# ==============================================================================
# 1. Bit-Level Padding Correctness (FIPS 180-4 & PA.pdf Eqs 3.37–3.39)
# ==============================================================================


def test_sha256_padding_arbitrary_lengths() -> None:
    """Verify bit-level padding for arbitrary lengths including L=1000 and L=1500."""
    for L in [0, 1, 7, 8, 447, 448, 511, 512, 1000, 1500]:
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


def test_sha256_padding_invalid_input() -> None:
    """Verify invalid bitstream inputs raise ValueError."""
    with pytest.raises(ValueError, match="only '0' and '1'"):
        pad_bitstream("1010201")

    with pytest.raises(ValueError, match="only binary integers"):
        pad_bitstream([1, 0, 2, 1])


# ==============================================================================
# 2. NIST Standard Test Vectors & hashlib.sha256 Parity
# ==============================================================================


def test_sha256_nist_standard_vectors() -> None:
    """Verify known independently-sourced NIST SHA-256 test vectors.

    Official Provenance:
    - Base URL: https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/secure-hashing
    - Archive: https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/shs/shabittestvectors.zip
    - Member: shabittestvectors/SHA256ShortMsg.rsp (NIST Cryptographic Algorithm Validation Program - CAVP)
      * Len = 0: Msg = 00 ("") -> e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
      * Len = 1: Msg = 00 ("0") -> bd4f9e98beb68c6ead3243b1b4c7fed75fa4feaab1f84795cbd8a98676a2a375
      * Len = 2: Msg = 80 ("10") -> 18f331f626210ff9bad6995d8cff6e891adba50eb2fdbddcaa921221cdc333ae
      * Len = 3: Msg = 60 ("011") -> 1f7794d4b0b67d3a6edcd17aba2144a95828032f7943ed26bf0c7c7628945f48
      * Len = 4: Msg = f0 ("1111") -> f30f6f1aa8675bcc33733b26baef25b9766f13256f0dba02f42f89d69db538f8
      * Len = 7: Msg = dc ("1101110") -> 83e848e33f2aec12959a5de8232989ee09e7841f9f031147a651d286e8c7218e
      * Len = 8: Msg = e5 ("11100101") -> ab61ba11a38b007ff98baa3ab20e2a584e15269fd428db3c857e2a2d568b5725
      * Len = 16: Msg = 4719 ("0100011100011001") -> 60acb27227ef97fb8ad343bf910cf5f451d8af50498e4b7d293bbd97e6c50c9b
    - FIPS 180-4 Section B.1 byte-aligned test vector: "abc" (24 bits)
    - FIPS 180-4 Section B.2 block boundary test vector: 448 bits
    """
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

    # 4. NIST CAVP Len = 3: Msg = 60 ("011")
    _, key_hex_3 = sha256_bitstream("011")
    assert key_hex_3 == "1f7794d4b0b67d3a6edcd17aba2144a95828032f7943ed26bf0c7c7628945f48"

    # 5. NIST CAVP Len = 4: Msg = f0 ("1111")
    _, key_hex_4 = sha256_bitstream("1111")
    assert key_hex_4 == "f30f6f1aa8675bcc33733b26baef25b9766f13256f0dba02f42f89d69db538f8"

    # 6. NIST CAVP Len = 7: Msg = dc ("1101110")
    _, key_hex_7 = sha256_bitstream("1101110")
    assert key_hex_7 == "83e848e33f2aec12959a5de8232989ee09e7841f9f031147a651d286e8c7218e"

    # 7. NIST CAVP Len = 8: Msg = e5 ("11100101")
    _, key_hex_8 = sha256_bitstream("11100101")
    assert key_hex_8 == "ab61ba11a38b007ff98baa3ab20e2a584e15269fd428db3c857e2a2d568b5725"

    # 8. NIST CAVP Len = 16: Msg = 4719 ("0100011100011001")
    _, key_hex_16 = sha256_bitstream("0100011100011001")
    assert key_hex_16 == "60acb27227ef97fb8ad343bf910cf5f451d8af50498e4b7d293bbd97e6c50c9b"

    # 9. FIPS 180-4 "abc" -> ASCII 'a'=0x61, 'b'=0x62, 'c'=0x63 (24 bits)
    abc_bits = "".join(format(ord(c), "08b") for c in "abc")
    assert len(abc_bits) == 24
    _, key_hex_abc = sha256_bitstream(abc_bits)
    assert key_hex_abc == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    # 10. FIPS 180-4 448-bit message "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
    msg_str = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
    msg_bits = "".join(format(ord(c), "08b") for c in msg_str)
    assert len(msg_bits) == 448
    _, key_hex_msg = sha256_bitstream(msg_bits)
    assert key_hex_msg == "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
    assert key_hex_msg == hashlib.sha256(msg_str.encode("utf-8")).hexdigest()


def test_sha256_padding_boundaries_and_hashlib_cross_verification() -> None:
    """Verify padding block transitions around 447/448 and 511/512 bit boundaries.

    FIPS 180-4 padding formula: p = (448 - 1 - L) mod 512.
    - L = 447: p = 0, total = 512 bits (1 block).
    - L = 448: p = 511, total = 1024 bits (2 blocks). Byte-aligned (56 bytes), verified vs hashlib.
    - L = 511: p = 448, total = 1024 bits (2 blocks).
    - L = 512: p = 447, total = 1024 bits (2 blocks). Byte-aligned (64 bytes), verified vs hashlib.
    - L = 1000 (quant_2bit): p = 471, total = 1536 bits (3 blocks). Byte-aligned (125 bytes), verified vs hashlib.
    - L = 1500 (prbs_2bit): p = 483, total = 2048 bits (4 blocks). Non-byte-aligned.
    """
    rng = np.random.default_rng(777)

    # 1. Boundary L = 447 bits (p = 0, single block of 512 bits)
    raw_447 = "".join(str(b) for b in rng.integers(0, 2, size=447))
    pad_447 = pad_bitstream(raw_447)
    assert len(pad_447) == 512
    assert pad_447[:447] == raw_447
    assert pad_447[447] == "1"
    assert pad_447[-64:] == format(447, "064b")
    # Intermediate zeros between bit 448 and trailing 64 bits: length = 0
    assert len(pad_447[448:-64]) == 0

    # 2. Boundary L = 448 bits (p = 511, crosses into block 2: total 1024 bits)
    raw_448_bytes = bytes(rng.integers(0, 256, size=56, dtype=np.uint8))
    raw_448_bits = "".join(format(b, "08b") for b in raw_448_bytes)
    assert len(raw_448_bits) == 448
    pad_448 = pad_bitstream(raw_448_bits)
    assert len(pad_448) == 1024
    assert pad_448[:448] == raw_448_bits
    assert pad_448[448] == "1"
    assert pad_448[-64:] == format(448, "064b")
    assert len(pad_448[449:-64]) == 511
    # Byte-aligned cross-verification against hashlib using packed bytes
    _, hex_448 = sha256_bitstream(raw_448_bits)
    assert hex_448 == hashlib.sha256(raw_448_bytes).hexdigest()

    # 3. Boundary L = 511 bits (p = 448, total 1024 bits)
    raw_511 = "".join(str(b) for b in rng.integers(0, 2, size=511))
    pad_511 = pad_bitstream(raw_511)
    assert len(pad_511) == 1024
    assert pad_511[:511] == raw_511
    assert pad_511[511] == "1"
    assert pad_511[-64:] == format(511, "064b")
    assert len(pad_511[512:-64]) == 448

    # 4. Boundary L = 512 bits (p = 447, total 1024 bits)
    raw_512_bytes = bytes(rng.integers(0, 256, size=64, dtype=np.uint8))
    raw_512_bits = "".join(format(b, "08b") for b in raw_512_bytes)
    assert len(raw_512_bits) == 512
    pad_512 = pad_bitstream(raw_512_bits)
    assert len(pad_512) == 1024
    assert pad_512[:512] == raw_512_bits
    assert pad_512[512] == "1"
    assert pad_512[-64:] == format(512, "064b")
    assert len(pad_512[513:-64]) == 447
    _, hex_512 = sha256_bitstream(raw_512_bits)
    assert hex_512 == hashlib.sha256(raw_512_bytes).hexdigest()

    # 5. Production path L = 1000 bits (p = 471, total 1536 bits = 3 blocks)
    raw_1000_bytes = bytes(rng.integers(0, 256, size=125, dtype=np.uint8))
    raw_1000_bits = "".join(format(b, "08b") for b in raw_1000_bytes)
    assert len(raw_1000_bits) == 1000
    pad_1000 = pad_bitstream(raw_1000_bits)
    assert len(pad_1000) == 1536
    assert pad_1000[-64:] == format(1000, "064b")
    assert len(pad_1000[1001:-64]) == 471
    _, hex_1000 = sha256_bitstream(raw_1000_bits)
    assert hex_1000 == hashlib.sha256(raw_1000_bytes).hexdigest()

    # 6. Production path L = 1500 bits (p = 483, total 2048 bits = 4 blocks)
    raw_1500_bits = "".join(str(b) for b in rng.integers(0, 2, size=1500))
    pad_1500 = pad_bitstream(raw_1500_bits)
    assert len(pad_1500) == 2048
    assert pad_1500[-64:] == format(1500, "064b")
    assert len(pad_1500[1501:-64]) == 483


def test_parity_check_with_hashlib() -> None:
    """Verify complete parity between bitstream SHA-256 and hashlib.sha256 for byte multiples."""
    rng = np.random.default_rng(2026)

    for num_bytes in [1, 2, 8, 16, 64, 125, 256]:  # 125 bytes = 1,000 bits (quant_2bit)
        raw_bytes = bytes(rng.integers(0, 256, size=num_bytes, dtype=np.uint8))
        bitstream = "".join(format(b, "08b") for b in raw_bytes)
        assert len(bitstream) == num_bytes * 8

        assert verify_against_hashlib(bitstream) is True

        _, our_hex = sha256_bitstream(bitstream)
        ref_hex = hashlib.sha256(raw_bytes).hexdigest()
        assert our_hex == ref_hex


def test_non_byte_aligned_bitstream_handling() -> None:
    """Verify arbitrary non-byte-aligned lengths (such as L=1500 for prbs_2bit)."""
    # 1500 bits is 187.5 bytes — cannot be directly hashed via standard byte interfaces without bit padding
    rng = np.random.default_rng(42)
    bits_1500 = "".join(str(b) for b in rng.integers(0, 2, size=1500))
    assert len(bits_1500) == 1500

    key_bin, key_hex = sha256_bitstream(bits_1500)
    assert len(key_bin) == 256
    assert len(key_hex) == 64
    assert set(key_bin).issubset({"0", "1"})
    assert int(key_bin, 2) == int(key_hex, 16)

    # Calling verify_against_hashlib on non-byte-aligned stream raises ValueError
    with pytest.raises(ValueError, match="requires byte-aligned bitstream"):
        verify_against_hashlib(bits_1500)


# ==============================================================================
# 3. Cryptographic Avalanche Effect Verification
# ==============================================================================


def test_cryptographic_avalanche_effect() -> None:
    """Verify statistical bit-diffusion property (strict avalanche criterion) on 1-bit input flip.

    Note: This test serves as a sanity check of SHA-256 bit diffusion, not as formal proof
    of cryptographic secrecy or entropy preservation. Mathematical correctness is established
    by the NIST CAVP test vectors and hashlib parity tests above.
    """
    rng = np.random.default_rng(999)

    for length in [1000, 1500]:
        base_bits = list(rng.integers(0, 2, size=length))
        base_str = "".join(str(b) for b in base_bits)

        k_base_bin, _ = sha256_bitstream(base_str)

        # Test flipping bits at multiple locations (start, middle, end)
        for flip_idx in [0, length // 4, length // 2, length - 1]:
            flipped_bits = list(base_bits)
            flipped_bits[flip_idx] ^= 1
            flipped_str = "".join(str(b) for b in flipped_bits)

            k_flipped_bin, _ = sha256_bitstream(flipped_str)

            mismatches = sum(1 for a, b in zip(k_base_bin, k_flipped_bin) if a != b)
            flip_percentage = (mismatches / 256.0) * 100.0

            # Statistical diffusion check: flipped bits disperse across the 256-bit block
            assert 40.0 <= flip_percentage <= 60.0
            assert 102 <= mismatches <= 154


# ==============================================================================
# 4. Channel and Receiver Isolation
# ==============================================================================


def test_channel_isolation() -> None:
    """Verify that each channel's key is derived strictly from its own bitstream without cross-contamination."""
    alice_bits = "10" * 500  # 1000 bits
    bob_bits = "10" * 500
    eve_bits = "01" * 500

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
# 5. Full Pipeline & Dummy Dataset Ground-Truth Verification
# ==============================================================================


def test_full_pipeline_privacy_amplification_dummy_dataset() -> None:
    """Verify Stage 6 Privacy Amplification across both supported paths on the dummy dataset."""
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
    assert cfg.supported_paths == ("quant_2bit", "prbs_2bit")
    assert "Synthetic software validation only" in cfg.scientific_disclaimer

    # 1. Path: quant_2bit (1,000 bits)
    q_pairs = pa_res.pair_results["quant_2bit"]
    q_ab = q_pairs["Alice–Bob"]
    assert q_ab.input_bit_length == 1000
    assert q_ab.pre_pa_kar == pytest.approx(100.00, abs=0.01)
    assert q_ab.post_pa_kar == pytest.approx(100.00, abs=0.01)
    assert q_ab.exact_key_match is True
    assert q_ab.mismatched_key_bits == 0
    assert q_ab.source_key_hex == q_ab.receiver_key_hex

    q_ea = q_pairs["Alice–Eve1-Alice"]
    assert q_ea.exact_key_match is False
    assert q_ea.pre_pa_kar == pytest.approx(58.20, abs=0.01)
    # Eavesdropper residual mismatches induce ~50% post-PA KAR
    assert 40.0 <= q_ea.post_pa_kar <= 60.0
    assert q_ea.mismatched_key_bits > 90

    q_eb = q_pairs["Bob–Eve1-Bob"]
    assert q_eb.exact_key_match is False
    assert q_eb.pre_pa_kar == pytest.approx(55.40, abs=0.01)
    assert 40.0 <= q_eb.post_pa_kar <= 60.0
    assert q_eb.mismatched_key_bits > 90

    # 2. Path: prbs_2bit (1,500 bits)
    p_pairs = pa_res.pair_results["prbs_2bit"]
    p_ab = p_pairs["Alice–Bob"]
    assert p_ab.input_bit_length == 1500
    assert p_ab.pre_pa_kar == pytest.approx(100.00, abs=0.01)
    assert p_ab.post_pa_kar == pytest.approx(100.00, abs=0.01)
    assert p_ab.exact_key_match is True
    assert p_ab.mismatched_key_bits == 0
    assert p_ab.source_key_hex == p_ab.receiver_key_hex

    p_ea = p_pairs["Alice–Eve1-Alice"]
    assert p_ea.exact_key_match is False
    assert p_ea.pre_pa_kar == pytest.approx(68.93, abs=0.01)
    assert 40.0 <= p_ea.post_pa_kar <= 60.0
    assert p_ea.mismatched_key_bits > 90

    p_eb = p_pairs["Bob–Eve1-Bob"]
    assert p_eb.exact_key_match is False
    assert p_eb.pre_pa_kar == pytest.approx(56.27, abs=0.01)
    assert 40.0 <= p_eb.post_pa_kar <= 60.0
    assert p_eb.mismatched_key_bits > 90

    # 3. Channel Keys
    for p_name in ("quant_2bit", "prbs_2bit"):
        ch_dict = pa_res.channel_keys[p_name]
        assert set(ch_dict.keys()) == {"Alice", "Bob", "Bob (Source)", "Eve1-Alice", "Eve1-Bob"}
        for ch_name, k_res in ch_dict.items():
            assert len(k_res.key_bin) == 256
            assert len(k_res.key_hex) == 64
            assert k_res.key_hex == k_res.key_hex.lower()


# ==============================================================================
# 6. Artifact Exporters & Companion XLSX Text Format Verification
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

    # 1. Metrics CSV
    assert csv_metrics.exists()
    with open(csv_metrics, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 6  # 2 paths * 3 pairs
        for r in reader:
            assert r["path"] in ("quant_2bit", "prbs_2bit")
            assert r["key_bits"] == "256"
            assert "pre_pa_kar_percent" in r
            assert "post_pa_kar_percent" in r
            assert "exact_key_match" in r
            # Standalone Hamming-distance report column is omitted from exported CSV per specification
            assert "mismatched_key_bits" not in r
            assert "source_key_hex" in r
            assert "receiver_key_hex" in r

    # Mismatch counts are preserved internally on dataclass for KAR calculation
    assert pa_res.metrics[0].mismatched_key_bits == 0

    # 2. Keys CSV
    assert csv_keys.exists()
    with open(csv_keys, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 10  # 2 paths * 5 channel roles (Alice, Bob, Bob (Source), Eve1-Alice, Eve1-Bob)
        for r in reader:
            assert len(r["key_bin"]) == 256
            assert len(r["key_hex"]) == 64

    # 3. JSON Config
    assert json_config.exists()
    with open(json_config, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["hash_algorithm"] == "SHA-256"
        assert data["key_length_bits"] == 256
        assert "scientific_disclaimer" in data
        assert "quant_2bit" in data["privacy_amplification_summary"]
        assert "prbs_2bit" in data["privacy_amplification_summary"]

    # 4. Excel Workbook (.xlsx)
    assert xlsx_wb.exists()
    wb = openpyxl.load_workbook(xlsx_wb, data_only=True)
    assert "PA Metrics" in wb.sheetnames
    assert "Channel Keys" in wb.sheetnames
    assert "Config & Disclaimers" in wb.sheetnames

    # Check that Text format '@' is explicitly preserved for key cells
    ws_keys = wb["Channel Keys"]
    for row in ws_keys.iter_rows(min_row=2, max_row=11, min_col=6, max_col=7):
        for cell in row:
            assert cell.number_format == "@"

    # 5. Figure plots
    assert png_p.exists() and png_p.stat().st_size > 10000
    assert pdf_p.exists() and pdf_p.stat().st_size > 10000


# ==============================================================================
# 7. CLI Integration with Prerequisite Chaining
# ==============================================================================


def test_cli_privacy_amplification_full(tmp_path: Path) -> None:
    """Verify CLI execution with --privacy-amplify and dedicated artifact options."""
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
        assert len(reader) == 10
