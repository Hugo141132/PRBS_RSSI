"""Unit tests for Modified Adaptive Dual-Threshold Quantization (MADQ) stage.

Governing Specification:
    PA.pdf Section 3.2.3, Equations (3.21)–(3.23), pages 27–28.
    PA.pdf Section 3.2.8.c, Equation (3.64), page 35 (Key Agreement Rate).
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import openpyxl
import pytest

from rssi_skg.cli import main, run_correlation_analysis
from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.plotting import plot_kar_comparison_figure
from rssi_skg.quantization import (
    CODE_4BIT_MAP,
    EXCEL_MAX_CELL_CHARS,
    GRAY_2BIT_MAP,
    ChannelQuantizationResult,
    QuantizationConfig,
    SegmentThresholds,
    calculate_kar,
    calculate_level_agreement,
    calculate_level_frequencies,
    encode_levels_to_bits,
    export_quantized_workbook_xlsx,
    quantize_channels,
    quantize_series,
)



def test_independent_threshold_and_boundary_calculation() -> None:
    """Validate hand-calculated thresholds and exact boundary classification.

    Given a segment with 4 samples: [10.0, 20.0, 30.0, 40.0]
    Mean = 25.0
    Variance (ddof=0) = ((10-25)^2 + (20-25)^2 + (30-25)^2 + (40-25)^2) / 4
                     = (225 + 25 + 25 + 225) / 4 = 500 / 4 = 125.0
    Std = sqrt(125.0) = 11.18033988749895
    For alpha = 0.5:
        lower = 25.0 - 0.5 * 11.18033988749895 = 25.0 - 5.5901699437494745 = 19.409830056250527
        upper = 25.0 + 0.5 * 11.18033988749895 = 30.590169943749473

    Boundary classifications:
        Sample 10.0 < lower (19.41) -> Level 0
        Sample 20.0 in [lower, upper] -> Level 1
        Sample 30.0 in [lower, upper] -> Level 1
        Sample 40.0 > upper (30.59) -> Level 2
    """
    samples = [10.0, 20.0, 30.0, 40.0]
    cfg = QuantizationConfig(window_size=4, alpha=0.5)

    levels, segments = quantize_series(samples, config=cfg, channel_name="TestChannel")

    assert len(segments) == 1
    seg = segments[0]
    assert seg.segment_index == 0
    assert seg.sample_count == 4
    assert math.isclose(seg.mean, 25.0, rel_tol=1e-12)
    expected_std = math.sqrt(125.0)
    assert math.isclose(seg.std, expected_std, rel_tol=1e-12)

    expected_lower = 25.0 - 0.5 * expected_std
    expected_upper = 25.0 + 0.5 * expected_std
    assert math.isclose(seg.lower_threshold, expected_lower, rel_tol=1e-12)
    assert math.isclose(seg.upper_threshold, expected_upper, rel_tol=1e-12)

    assert levels == [0, 1, 1, 2]


def test_exact_boundary_conditions() -> None:
    """Verify exact inclusive boundaries for level 1: x == lower and x == upper.

    PA.pdf Eq (3.23):
        Q(x) = 0 if x < lower
        Q(x) = 1 if lower <= x <= upper
        Q(x) = 2 if x > upper
    """
    # Create segment where mean=0, std=2, alpha=1.0 -> lower=-2.0, upper=+2.0
    # Samples: -3.0 (0), -2.0 (1), 0.0 (1), +2.0 (1), +3.0 (2)
    # Mean of [-3, -2, 0, 2, 3] = 0.
    # Variance = (9 + 4 + 0 + 4 + 9)/5 = 26/5 = 5.2. std = sqrt(5.2).
    # To test exact equality, manually test with known mean and std:
    # Construct points: [-2.0, -1.0, 1.0, 2.0], mean = 0.0, std = sqrt((4+1+1+4)/4) = sqrt(2.5)
    # Instead, let's construct explicit samples and test exact threshold comparison:
    mean = 50.0
    std = 10.0
    alpha = 0.5
    lower = mean - alpha * std  # 45.0
    upper = mean + alpha * std  # 55.0

    # Test values around exact boundaries
    boundary_samples = [44.999, 45.0, 50.0, 55.0, 55.001]
    # We can quantize with a large window size, or test the classification directly:
    levels, segs = quantize_series(boundary_samples, config=QuantizationConfig(window_size=10, alpha=0.5))

    # Check boundaries calculated
    s = segs[0]
    expected_levels = []
    for x in boundary_samples:
        if x < s.lower_threshold:
            expected_levels.append(0)
        elif x > s.upper_threshold:
            expected_levels.append(2)
        else:
            expected_levels.append(1)

    assert levels == expected_levels


def test_both_encodings_mappings() -> None:
    """Verify 2-bit Gray code and 4-bit mappings per specification."""
    assert GRAY_2BIT_MAP[0] == "00"
    assert GRAY_2BIT_MAP[1] == "01"
    assert GRAY_2BIT_MAP[2] == "11"

    assert CODE_4BIT_MAP[0] == "1010"
    assert CODE_4BIT_MAP[1] == "1011"
    assert CODE_4BIT_MAP[2] == "1001"

    levels = [0, 1, 2, 1, 0]
    bitstream_2bit = encode_levels_to_bits(levels, GRAY_2BIT_MAP)
    bitstream_4bit = encode_levels_to_bits(levels, CODE_4BIT_MAP)

    assert bitstream_2bit == "0001110100"
    assert bitstream_4bit == "10101011100110111010"
    assert len(bitstream_2bit) == 2 * len(levels)
    assert len(bitstream_4bit) == 4 * len(levels)


def test_bit_ordering_preserves_sample_sequence() -> None:
    """Verify bitstream concatenation strictly preserves temporal sample sequence."""
    levels = [2, 0, 1]
    # 2 -> 11, 0 -> 00, 1 -> 01
    bs2 = encode_levels_to_bits(levels, GRAY_2BIT_MAP)
    assert bs2[:2] == "11"
    assert bs2[2:4] == "00"
    assert bs2[4:6] == "01"

    # 2 -> 1001, 0 -> 1010, 1 -> 1011
    bs4 = encode_levels_to_bits(levels, CODE_4BIT_MAP)
    assert bs4[:4] == "1001"
    assert bs4[4:8] == "1010"
    assert bs4[8:12] == "1011"


def test_constant_segment_produces_level_1() -> None:
    """Verify constant segments (std = 0) unconditionally produce level 1."""
    constant_series = [-75.0] * 50
    levels, segments = quantize_series(constant_series, config=QuantizationConfig(window_size=50, alpha=0.5))

    assert len(segments) == 1
    assert segments[0].std == 0.0
    assert segments[0].lower_threshold == -75.0
    assert segments[0].upper_threshold == -75.0
    assert len(levels) == 50
    assert all(lvl == 1 for lvl in levels)

    # Encode to bits
    bs2 = encode_levels_to_bits(levels, GRAY_2BIT_MAP)
    bs4 = encode_levels_to_bits(levels, CODE_4BIT_MAP)
    assert bs2 == "01" * 50
    assert bs4 == "1011" * 50


def test_partial_final_segment() -> None:
    """Verify that a shorter final segment is properly processed with its own mean and std."""
    # 125 samples with window_size = 50 -> Seg 0 (50), Seg 1 (50), Seg 2 (25)
    samples = [float(i) for i in range(125)]
    levels, segments = quantize_series(samples, config=QuantizationConfig(window_size=50, alpha=0.5))

    assert len(segments) == 3
    assert len(levels) == 125

    assert segments[0].sample_count == 50
    assert segments[0].start_index == 0
    assert segments[0].end_index == 50

    assert segments[1].sample_count == 50
    assert segments[1].start_index == 50
    assert segments[1].end_index == 100

    assert segments[2].sample_count == 25
    assert segments[2].start_index == 100
    assert segments[2].end_index == 125

    # Check segment 2 stats
    seg2_vals = samples[100:125]
    expected_mean = sum(seg2_vals) / 25.0
    expected_var = sum((x - expected_mean) ** 2 for x in seg2_vals) / 25.0
    expected_std = math.sqrt(expected_var)

    assert math.isclose(segments[2].mean, expected_mean, rel_tol=1e-12)
    assert math.isclose(segments[2].std, expected_std, rel_tol=1e-12)


def test_channel_isolation() -> None:
    """Verify that each channel computes its own mean and thresholds with zero cross-leakage."""
    # Alice is centered around -70 with std ~ 2
    alice = [-72.0, -70.0, -68.0, -70.0]
    # Bob is centered around -50 with std ~ 5
    bob = [-55.0, -50.0, -45.0, -50.0]

    channels = {
        "Alice": alice,
        "Bob": bob,
        "Eve1-Alice": [-30.0] * 4,
        "Eve1-Bob": [-80.0] * 4,
    }

    res = quantize_channels(channels, config=QuantizationConfig(window_size=4, alpha=0.5))

    alice_seg = res.thresholds["Alice"][0]
    bob_seg = res.thresholds["Bob"][0]

    assert math.isclose(alice_seg.mean, -70.0)
    assert math.isclose(bob_seg.mean, -50.0)
    assert alice_seg.lower_threshold < -70.0 < alice_seg.upper_threshold
    assert bob_seg.lower_threshold < -50.0 < bob_seg.upper_threshold
    # Ensure Alice's thresholds do not depend on Bob
    assert alice_seg.mean != bob_seg.mean


def test_kar_calculation_formula() -> None:
    """Verify KAR calculation per PA.pdf Eq (3.64): KAR = ((N_total - N_mismatch) / N_total) * 100%."""
    # Perfect match: 4 bits, 0 mismatches -> 100%
    assert calculate_kar("1010", "1010") == 100.0

    # 1 mismatch out of 4 -> 3/4 = 75%
    assert calculate_kar("1010", "1011") == 75.0

    # 2 mismatches out of 4 -> 2/4 = 50%
    assert calculate_kar("1010", "1001") == 50.0

    # Total mismatch: 4 mismatches out of 4 -> 0%
    assert calculate_kar("1010", "0101") == 0.0

    # 10 bits: 8 match, 2 mismatch -> 80%
    b_a = "1100110011"
    b_b = "1100110000"  # last 2 mismatch
    assert calculate_kar(b_a, b_b) == 80.0


def test_level_agreement_and_frequency() -> None:
    """Verify sample-level agreement and frequency calculation."""
    lvl_a = [0, 1, 2, 1, 0]
    lvl_b = [0, 1, 1, 1, 2]
    # Matches: index 0 (0==0), index 1 (1==1), index 3 (1==1) -> 3 out of 5 -> 60%
    assert calculate_level_agreement(lvl_a, lvl_b) == 60.0

    freqs = calculate_level_frequencies(lvl_a)
    assert freqs[0]["count"] == 2
    assert freqs[0]["percentage"] == 40.0
    assert freqs[1]["count"] == 2
    assert freqs[1]["percentage"] == 40.0
    assert freqs[2]["count"] == 1
    assert freqs[2]["percentage"] == 20.0


def test_invalid_quantization_configs() -> None:
    """Verify validation of configuration parameters."""
    with pytest.raises(ValueError, match="window_size must be a positive integer"):
        QuantizationConfig(window_size=0)

    with pytest.raises(ValueError, match="window_size must be a positive integer"):
        QuantizationConfig(window_size=-5)

    with pytest.raises(TypeError, match="window_size must be an integer"):
        QuantizationConfig(window_size=50.0)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="window_size must be an integer"):
        QuantizationConfig(window_size=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="alpha must be non-negative"):
        QuantizationConfig(alpha=-0.1)

    with pytest.raises(ValueError, match="alpha must be finite"):
        QuantizationConfig(alpha=float("nan"))

    with pytest.raises(ValueError, match="alpha must be finite"):
        QuantizationConfig(alpha=float("inf"))

    with pytest.raises(TypeError, match="alpha must be a real number"):
        QuantizationConfig(alpha="0.5")  # type: ignore[arg-type]


def test_invalid_inputs_raise_errors() -> None:
    """Verify validation of input data to quantization functions."""
    # Empty series
    with pytest.raises(ValueError, match="Input series must not be empty"):
        quantize_series([])

    # Non-numeric input
    with pytest.raises(ValueError, match="Invalid non-numeric value"):
        quantize_series([1.0, "bad", 3.0])

    # NaN input
    with pytest.raises(ValueError, match="Non-finite value"):
        quantize_series([1.0, float("nan"), 3.0])

    # Inf input
    with pytest.raises(ValueError, match="Non-finite value"):
        quantize_series([1.0, float("inf"), 3.0])

    # Channel length mismatch
    with pytest.raises(ValueError, match="Channel length mismatch"):
        quantize_channels({
            "Alice": [1.0, 2.0, 3.0],
            "Bob": [1.0, 2.0],
        })

    # Empty channels dict
    with pytest.raises(ValueError, match="Channels mapping must not be empty"):
        quantize_channels({})

    # Channel with zero samples
    with pytest.raises(ValueError, match="zero samples"):
        quantize_channels({"Alice": []})

    # KAR with unequal lengths
    with pytest.raises(ValueError, match="Bitstreams must have identical length"):
        calculate_kar("1010", "101")

    # KAR with empty string
    with pytest.raises(ValueError, match="Bitstreams must not be empty"):
        calculate_kar("", "")

    # KAR with non-binary characters
    with pytest.raises(ValueError, match="Non-binary character"):
        calculate_kar("1012", "1010")

    # Encode with invalid level
    with pytest.raises(ValueError, match="Invalid quantization level"):
        encode_levels_to_bits([0, 1, 3], GRAY_2BIT_MAP)


def test_dummy_dataset_quantization_verification() -> None:
    """Verify quantization stage on the full dummy dataset (500 samples).

    Specification:
        - 500 samples -> 10 segments of 50 samples each.
        - 2-bit Gray encoding -> 1,000 bits per channel.
        - 4-bit encoding -> 2,000 bits per channel.
        - Alice–Bob level agreement and KAR correctly calculated.
    """
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(dummy_path)
    filtered_data = filter_rssi_channels(raw_data, FilterConfig())

    cfg = QuantizationConfig(window_size=50, alpha=0.5)
    res = quantize_channels(channels=filtered_data, config=cfg)

    # 1. Structural dimensions
    assert res.sample_count == 500
    assert res.num_segments == 10

    for ch in ("Alice", "Bob", "Eve1-Alice", "Eve1-Bob"):
        assert len(res.levels[ch]) == 500
        assert len(res.thresholds[ch]) == 10
        assert len(res.bitstreams_2bit[ch]) == 1000
        assert len(res.bitstreams_4bit[ch]) == 2000

        # Verify all levels are in {0, 1, 2}
        assert all(lvl in (0, 1, 2) for lvl in res.levels[ch])

        # Verify all characters in bitstreams are '0' or '1'
        assert set(res.bitstreams_2bit[ch]).issubset({"0", "1"})
        assert set(res.bitstreams_4bit[ch]).issubset({"0", "1"})

    # 2. Specific verified metrics on dummy dataset
    ab_metric = next(pm for pm in res.pair_metrics if pm["pair"] == "Alice–Bob")
    assert ab_metric["sample_count"] == 500
    assert ab_metric["bit_count_2bit"] == 1000
    assert ab_metric["bit_count_4bit"] == 2000
    assert math.isclose(ab_metric["level_agreement_rate"], 64.4, abs_tol=1e-6)
    assert math.isclose(ab_metric["kar_2bit"], 80.4, abs_tol=1e-6)
    assert math.isclose(ab_metric["kar_4bit"], 90.2, abs_tol=1e-6)

    # Eavesdropper metrics
    ae_metric = next(pm for pm in res.pair_metrics if pm["pair"] == "Alice–Eve1-Alice")
    assert math.isclose(ae_metric["level_agreement_rate"], 34.8, abs_tol=1e-6)
    assert math.isclose(ae_metric["kar_2bit"], 58.2, abs_tol=1e-6)
    assert math.isclose(ae_metric["kar_4bit"], 79.1, abs_tol=1e-6)

    be_metric = next(pm for pm in res.pair_metrics if pm["pair"] == "Bob–Eve1-Bob")
    assert math.isclose(be_metric["level_agreement_rate"], 34.4, abs_tol=1e-6)
    assert math.isclose(be_metric["kar_2bit"], 55.4, abs_tol=1e-6)
    assert math.isclose(be_metric["kar_4bit"], 77.7, abs_tol=1e-6)


def test_cli_quantization_workflow_and_artifact_export(tmp_path: Path) -> None:
    """Verify CLI execution and export of all 5 quantization artifacts."""
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    csv_corr = str(tmp_path / "corr.csv")
    samples_filt = str(tmp_path / "samples_filt.csv")
    meta_filt = str(tmp_path / "meta_filt.json")
    samples_quant = str(tmp_path / "samples_quant.csv")
    segments_quant = str(tmp_path / "segments_quant.csv")
    bitstreams_quant = str(tmp_path / "bitstreams_quant.csv")
    metrics_quant = str(tmp_path / "metrics_quant.csv")
    meta_quant = str(tmp_path / "meta_quant.json")

    ret = main([
        "-i", dummy_path,
        "-o", csv_corr,
        "--filter",
        "--quantize",
        "--quantize-window", "50",
        "--quantize-alpha", "0.5",
        "--filtered-samples-output", samples_filt,
        "--filter-config-output", meta_filt,
        "--quantized-samples-output", samples_quant,
        "--quantized-segments-output", segments_quant,
        "--quantized-bitstreams-output", bitstreams_quant,
        "--quantize-metrics-output", metrics_quant,
        "--quantize-config-output", meta_quant,
    ])

    assert ret == 0

    # 1. Aligned quantized samples CSV
    assert Path(samples_quant).is_file()
    with open(samples_quant, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        assert "sample_index" in header
        assert "segment_index" in header
        assert "Alice_filtered" in header
        assert "Alice_lower_threshold" in header
        assert "Alice_upper_threshold" in header
        assert "Alice_level" in header
        assert "Alice_bits_2bit" in header
        assert "Alice_bits_4bit" in header
        assert "alice_bob_level_match" in header
        rows = list(reader)
        assert len(rows) == 500

    # 2. Segments CSV
    assert Path(segments_quant).is_file()
    with open(segments_quant, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        # 10 segments * 4 channels = 40 rows
        assert len(rows) == 40
        assert rows[0]["segment_index"] == "0"
        assert rows[0]["sample_count"] == "50"

    # 3. Bitstreams CSV
    assert Path(bitstreams_quant).is_file()
    with open(bitstreams_quant, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        # 4 channels * 2 encodings = 8 rows
        assert len(rows) == 8
        alice_2b = next(r for r in rows if r["channel"] == "Alice" and r["encoding"] == "2-bit Gray")
        alice_4b = next(r for r in rows if r["channel"] == "Alice" and r["encoding"] == "4-bit")
        assert alice_2b["bit_count"] == "1000"
        assert len(alice_2b["bitstream"]) == 1000
        assert alice_4b["bit_count"] == "2000"
        assert len(alice_4b["bitstream"]) == 2000

    # 4. Metrics CSV
    assert Path(metrics_quant).is_file()
    with open(metrics_quant, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        ab_row = rows[0]
        assert ab_row["pair"] == "Alice–Bob"
        assert ab_row["sample_count"] == "500"
        assert float(ab_row["level_agreement_rate"]) == 64.4
        assert float(ab_row["kar_2bit"]) == 80.4
        assert float(ab_row["kar_4bit"]) == 90.2

    # 5. Metadata JSON
    assert Path(meta_quant).is_file()
    with open(meta_quant, encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["algorithm"] == "Modified Adaptive Dual-Threshold Quantization (MADQ)"
        assert meta["parameters"]["window_size"] == 50
        assert meta["parameters"]["alpha"] == 0.5
        assert meta["parameters"]["ddof"] == 0
        assert meta["execution_summary"]["sample_count"] == 500
        assert meta["execution_summary"]["num_segments"] == 10
        assert "bitstreams" in meta


def test_kar_invariants_equal_mismatches_and_mathematical_relation() -> None:
    """Verify that Hamming distances and mismatch counts are identical between 2-bit Gray and 4-bit encodings.

    Mathematical Basis:
        Mapping:
            0 -> 2-bit: "00",   4-bit: "1010"
            1 -> 2-bit: "01",   4-bit: "1011"
            2 -> 2-bit: "11",   4-bit: "1001"

        Pairwise Hamming distances:
            d_H(0, 0) = 0 (2-bit), 0 (4-bit)
            d_H(1, 1) = 0 (2-bit), 0 (4-bit)
            d_H(2, 2) = 0 (2-bit), 0 (4-bit)
            d_H(0, 1) = 1 (2-bit), 1 (4-bit)
            d_H(1, 2) = 1 (2-bit), 1 (4-bit)
            d_H(0, 2) = 2 (2-bit), 2 (4-bit)

        Because d_H,4bit(a, b) == d_H,2bit(a, b) for all (a, b) in {0,1,2}^2:
            N_mismatch,4bit == N_mismatch,2bit.

        Consequently:
            KAR_4bit = ((4N - N_mismatch) / 4N) * 100%
                     = (1 - (N_mismatch / 4N)) * 100%
                     = (1 - 0.5 * (N_mismatch / 2N)) * 100%
                     = (0.5 + 0.5 * (1 - N_mismatch / 2N)) * 100%
                     = 50% + KAR_2bit / 2.
    """
    # 1. Verify pairwise Hamming distance equality across all 9 level pairs
    for lvl_a in (0, 1, 2):
        for lvl_b in (0, 1, 2):
            b2_a = GRAY_2BIT_MAP[lvl_a]
            b2_b = GRAY_2BIT_MAP[lvl_b]
            b4_a = CODE_4BIT_MAP[lvl_a]
            b4_b = CODE_4BIT_MAP[lvl_b]

            d2 = sum(1 for a, b in zip(b2_a, b2_b) if a != b)
            d4 = sum(1 for a, b in zip(b4_a, b4_b) if a != b)
            assert d2 == d4, f"Mismatch in Hamming distance for pair ({lvl_a}, {lvl_b}): d2={d2}, d4={d4}"

    # 2. Verify on arbitrary sequences
    seq_a = [0, 1, 2, 0, 1, 2, 1, 0, 2, 2, 1, 0] * 5
    seq_b = [0, 2, 1, 0, 1, 1, 2, 0, 2, 0, 1, 2] * 5

    bs2_a = encode_levels_to_bits(seq_a, GRAY_2BIT_MAP)
    bs2_b = encode_levels_to_bits(seq_b, GRAY_2BIT_MAP)
    bs4_a = encode_levels_to_bits(seq_a, CODE_4BIT_MAP)
    bs4_b = encode_levels_to_bits(seq_b, CODE_4BIT_MAP)

    mismatches_2bit = sum(1 for a, b in zip(bs2_a, bs2_b) if a != b)
    mismatches_4bit = sum(1 for a, b in zip(bs4_a, bs4_b) if a != b)
    assert mismatches_2bit == mismatches_4bit

    kar_2b = calculate_kar(bs2_a, bs2_b)
    kar_4b = calculate_kar(bs4_a, bs4_b)
    assert math.isclose(kar_4b, 50.0 + kar_2b / 2.0, rel_tol=1e-12)

    # 3. Verify on full dummy dataset pairs
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(dummy_path)
    filt_data = filter_rssi_channels(raw_data, FilterConfig())
    res = quantize_channels(filt_data, QuantizationConfig())

    expected_mismatches = {
        "Alice–Bob": 196,
        "Alice–Eve1-Alice": 418,
        "Bob–Eve1-Bob": 446,
    }

    for pm in res.pair_metrics:
        p_name = pm["pair"]
        ch_a = pm["channel_a"]
        ch_b = pm["channel_b"]

        b2_a = res.bitstreams_2bit[ch_a]
        b2_b = res.bitstreams_2bit[ch_b]
        b4_a = res.bitstreams_4bit[ch_a]
        b4_b = res.bitstreams_4bit[ch_b]

        m2 = sum(1 for a, b in zip(b2_a, b2_b) if a != b)
        m4 = sum(1 for a, b in zip(b4_a, b4_b) if a != b)

        assert m2 == m4 == expected_mismatches[p_name]
        assert math.isclose(pm["kar_4bit"], 50.0 + pm["kar_2bit"] / 2.0, rel_tol=1e-12)


def test_cli_quantize_without_filter_auto_enables_filtering(tmp_path: Path) -> None:
    """Verify that specifying --quantize without --filter auto-enables filtering as prerequisite."""
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    csv_corr = str(tmp_path / "corr.csv")
    metrics_quant = str(tmp_path / "metrics.csv")

    # Run CLI with --quantize but WITHOUT --filter
    ret = main([
        "-i", dummy_path,
        "-o", csv_corr,
        "--quantize",
        "--quantize-metrics-output", metrics_quant,
    ])
    assert ret == 0

    # Ensure correlation output contains filtered correlation columns
    assert Path(csv_corr).is_file()
    with open(csv_corr, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        assert "raw_correlation" in header
        assert "filtered_correlation" in header
        assert "correlation_delta" in header

    # Ensure quantization metrics output exists and is populated
    assert Path(metrics_quant).is_file()
    with open(metrics_quant, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0]["pair"] == "Alice–Bob"
        assert float(rows[0]["kar_2bit"]) == 80.4


def test_cli_raw_only_and_filter_only_modes(tmp_path: Path) -> None:
    """Verify CLI behavior for raw-only and filtering-only modes."""
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"

    # 1. Raw-only mode: no --filter, no --quantize
    raw_csv = str(tmp_path / "raw.csv")
    ret_raw = main(["-i", dummy_path, "-o", raw_csv])
    assert ret_raw == 0
    with open(raw_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        assert header == ["pair", "sample_count", "correlation_coefficient", "data_kind"]
        rows = list(reader)
        assert len(rows) == 3
        # Check raw Alice-Bob correlation
        assert math.isclose(float(rows[0]["correlation_coefficient"]), 0.6322634354, rel_tol=1e-5)

    # 2. Filter-only mode: --filter, no --quantize
    filt_csv = str(tmp_path / "filt.csv")
    ret_filt = main(["-i", dummy_path, "-o", filt_csv, "--filter"])
    assert ret_filt == 0
    with open(filt_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        assert "raw_correlation" in header
        assert "filtered_correlation" in header
        rows = list(reader)
        assert len(rows) == 3
        assert math.isclose(float(rows[0]["filtered_correlation"]), 0.8422441999, rel_tol=1e-5)


def test_xlsx_companion_export_preserves_leading_zeros_and_structure(tmp_path: Path) -> None:
    """Verify that companion XLSX export stores exact binary strings with Text format ('@').

    Crucial Verification:
        - Excel drops leading zeros when opening CSVs (00 -> 0, 01 -> 1).
        - In the companion XLSX workbook, cells containing '00' and '01' must be
          stored as explicit string cells (data_type == 's') with Text number format ('@').
        - Bitstreams (1,000 and 2,000 bits) must be completely preserved.
        - All 4 sheets ('Quantized Samples', 'Bitstreams', 'Agreement Metrics', 'Segment Thresholds')
          must be correctly populated.
    """
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(dummy_path)
    filt_data = filter_rssi_channels(raw_data, FilterConfig())
    res = quantize_channels(filt_data, QuantizationConfig())

    xlsx_path = tmp_path / "test_quantized.xlsx"
    out = export_quantized_workbook_xlsx(
        filtered_data=filt_data,
        quant_result=res,
        output_path=xlsx_path,
    )
    assert out.is_file()

    # Reopen and inspect with openpyxl
    wb = openpyxl.load_workbook(xlsx_path)
    sheet_names = wb.sheetnames
    assert "Quantized Samples" in sheet_names
    assert "Bitstreams" in sheet_names
    assert "Agreement Metrics" in sheet_names
    assert "Segment Thresholds" in sheet_names

    # 1. Inspect 'Quantized Samples' sheet
    ws_samples = wb["Quantized Samples"]
    assert ws_samples.max_row == 501  # 1 header + 500 samples

    header_row = [cell.value for cell in ws_samples[1]]
    assert "sample_index" in header_row
    assert "Alice_filtered" in header_row
    assert "Alice_bits_2bit" in header_row
    assert "Alice_bits_4bit" in header_row
    assert "alice_bob_level_match" in header_row

    col_alice_2b = header_row.index("Alice_bits_2bit") + 1
    col_alice_4b = header_row.index("Alice_bits_4bit") + 1

    # Check sample 0: Alice level is 0 -> 2bit is '00', 4bit is '1010'
    c_s0_2b = ws_samples.cell(row=2, column=col_alice_2b)
    c_s0_4b = ws_samples.cell(row=2, column=col_alice_4b)

    assert c_s0_2b.value == "00"
    assert isinstance(c_s0_2b.value, str)
    assert c_s0_2b.data_type == "s"
    assert c_s0_2b.number_format == "@"

    assert c_s0_4b.value == "1010"
    assert isinstance(c_s0_4b.value, str)
    assert c_s0_4b.data_type == "s"
    assert c_s0_4b.number_format == "@"

    # Check sample 7: Alice level is 1 -> 2bit is '01', 4bit is '1011'
    c_s7_2b = ws_samples.cell(row=9, column=col_alice_2b)
    assert c_s7_2b.value == "01"
    assert isinstance(c_s7_2b.value, str)
    assert c_s7_2b.data_type == "s"
    assert c_s7_2b.number_format == "@"

    # Verify none of the 2-bit cells were coerced to integers 0 or 1
    for r in range(2, 502):
        cell_val = ws_samples.cell(row=r, column=col_alice_2b).value
        assert isinstance(cell_val, str)
        assert cell_val in ("00", "01", "11")

    # 2. Inspect 'Bitstreams' sheet
    ws_bits = wb["Bitstreams"]
    # 4 channels * 2 encodings = 8 rows (+ 1 header = 9 rows)
    assert ws_bits.max_row == 9
    bits_header = [cell.value for cell in ws_bits[1]]
    assert bits_header == ["channel", "encoding", "part", "total_parts", "bit_count", "bitstream"]

    alice_2b_row = next(r for r in range(2, 10) if ws_bits.cell(row=r, column=1).value == "Alice" and ws_bits.cell(row=r, column=2).value == "2-bit Gray")
    alice_2b_val = ws_bits.cell(row=alice_2b_row, column=6).value
    assert isinstance(alice_2b_val, str)
    assert len(alice_2b_val) == 1000
    assert alice_2b_val == res.bitstreams_2bit["Alice"]
    assert ws_bits.cell(row=alice_2b_row, column=6).data_type == "s"
    assert ws_bits.cell(row=alice_2b_row, column=6).number_format == "@"

    alice_4b_row = next(r for r in range(2, 10) if ws_bits.cell(row=r, column=1).value == "Alice" and ws_bits.cell(row=r, column=2).value == "4-bit")
    alice_4b_val = ws_bits.cell(row=alice_4b_row, column=6).value
    assert isinstance(alice_4b_val, str)
    assert len(alice_4b_val) == 2000
    assert alice_4b_val == res.bitstreams_4bit["Alice"]

    # 3. Inspect 'Agreement Metrics' sheet
    ws_metrics = wb["Agreement Metrics"]
    assert ws_metrics.max_row == 4  # 1 header + 3 pairs
    ab_kar2 = float(ws_metrics.cell(row=2, column=6).value)
    ab_kar4 = float(ws_metrics.cell(row=2, column=7).value)
    assert math.isclose(ab_kar2, 80.4, rel_tol=1e-5)
    assert math.isclose(ab_kar4, 90.2, rel_tol=1e-5)


def test_xlsx_handles_excel_32767_character_limit_without_truncation(tmp_path: Path) -> None:
    """Verify that bitstreams exceeding 32,767 characters are safely chunked across parts without loss."""
    # Create synthetic bitstream of 70,000 bits (exceeds 32,767 limit)
    synthetic_bs = "01" * 35000
    assert len(synthetic_bs) == 70000

    cfg = QuantizationConfig(window_size=50, alpha=0.5)
    res = ChannelQuantizationResult(
        config=cfg,
        sample_count=50,
        num_segments=1,
        levels={"Alice": [1] * 50},
        thresholds={"Alice": [SegmentThresholds(0, "Alice", 0, 50, 50, -50.0, 1.0, -50.5, -49.5)]},
        bitstreams_2bit={"Alice": synthetic_bs},
        bitstreams_4bit={"Alice": synthetic_bs},
        level_frequencies={"Alice": {0: {"count": 0, "percentage": 0.0}, 1: {"count": 50, "percentage": 100.0}, 2: {"count": 0, "percentage": 0.0}}},
        pair_metrics=[],
    )

    xlsx_path = tmp_path / "long_bitstream.xlsx"
    export_quantized_workbook_xlsx(
        filtered_data={"Alice": [0.0] * 50},
        quant_result=res,
        output_path=xlsx_path,
        max_cell_chars=32767,
    )

    wb = openpyxl.load_workbook(xlsx_path)
    ws_bits = wb["Bitstreams"]

    # 70,000 / 32,767 = 3 parts: Part 1 (32767), Part 2 (32767), Part 3 (4466)
    # 2 encodings (2-bit Gray and 4-bit) * 3 parts = 6 rows (+ 1 header = 7 rows)
    assert ws_bits.max_row == 7

    reconstructed_chunks = []
    for r in range(2, 5):  # 2-bit Gray parts 1, 2, 3
        part_idx = ws_bits.cell(row=r, column=3).value
        total_parts = ws_bits.cell(row=r, column=4).value
        chunk_len = ws_bits.cell(row=r, column=5).value
        chunk = ws_bits.cell(row=r, column=6).value

        assert total_parts == 3
        assert len(chunk) <= 32767
        assert len(chunk) == chunk_len
        reconstructed_chunks.append(chunk)

    reconstructed_bs = "".join(reconstructed_chunks)
    assert reconstructed_bs == synthetic_bs
    assert len(reconstructed_bs) == 70000

    # Test invalid non-positive max_cell_chars raises ValueError
    with pytest.raises(ValueError, match="max_cell_chars must be a positive integer"):
        export_quantized_workbook_xlsx(
            filtered_data={"Alice": [0.0] * 50},
            quant_result=res,
            output_path=tmp_path / "err.xlsx",
            max_cell_chars=0,
        )


def test_kar_comparison_figure_and_cli_export(tmp_path: Path) -> None:
    """Verify plot_kar_comparison_figure generation and CLI integration with distinct suffix."""
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    raw_data = load_rssi_workbook(dummy_path)
    filt_data = filter_rssi_channels(raw_data, FilterConfig())
    res = quantize_channels(filt_data, QuantizationConfig())

    # 1. Direct plotting function call
    fig_prefix = tmp_path / "test_kar_fig"
    png_p, pdf_p = plot_kar_comparison_figure(res, fig_prefix)

    assert png_p.is_file()
    assert pdf_p.is_file()
    assert png_p.stat().st_size > 50000  # 300 dpi image
    assert pdf_p.stat().st_size > 10000  # Vector PDF

    # 2. CLI integration test
    cli_fig_prefix = str(tmp_path / "cli_fig_filtered")
    xlsx_out = str(tmp_path / "cli_quantized.xlsx")

    ret = main([
        "-i", dummy_path,
        "--quantize",
        "--figure-prefix", cli_fig_prefix,
        "--quantized-xlsx-output", xlsx_out,
    ])
    assert ret == 0

    # Should export filtering figure to cli_fig_filtered.png / .pdf
    assert Path(f"{cli_fig_prefix}.png").is_file()
    assert Path(f"{cli_fig_prefix}.pdf").is_file()

    # Should export quantization figure to cli_fig_quantization.png / .pdf (distinct suffix)
    quant_png = tmp_path / "cli_fig_quantization.png"
    quant_pdf = tmp_path / "cli_fig_quantization.pdf"
    assert quant_png.is_file()
    assert quant_pdf.is_file()
    assert quant_png.stat().st_size > 50000
    assert quant_pdf.stat().st_size > 10000

    # Should export companion xlsx
    assert Path(xlsx_out).is_file()
    wb = openpyxl.load_workbook(xlsx_out)
    assert "Quantized Samples" in wb.sheetnames
