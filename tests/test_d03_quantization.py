"""
test_d03_quantization.py

Verification test suite for Milestone D03:
Modified Adaptive Dual-Threshold Quantization (ADQ) based on LoRa-PRIME (2026).

Coverage:
1. Deterministic quantization output across repeated runs.
2. Threshold calculation correctness (mu, sigma, q^+ = mu + alpha*sigma, q^- = mu - alpha*sigma).
3. Correct 3-level symbol mapping (Level 0: X < q^-, Level 1: q^- <= X <= q^+, Level 2: X > q^+).
4. Multi-bit encoding correctness:
   - 2-bit Gray coding: Level 0 -> '00', Level 1 -> '01', Level 2 -> '11'.
   - 4-bit LoRa-PRIME mapping: Level 0 -> '1010', Level 1 -> '1011', Level 2 -> '1001'.
5. Preservation of intermediate samples between adaptive thresholds (100% retention).
6. Edge cases handling:
   - Constant / zero-variance RSSI sequences.
   - Low variance RSSI sequences.
   - Highly noisy / fluctuating RSSI sequences.
   - Short sequences (e.g. 1 sample, 2 samples, 5 samples).
   - Empty input sequence.
7. Key Agreement Rate (KAR) and Bit Error Rate (BER) mathematical properties (0 <= KAR <= 1, KAR + BER == 1).
8. Key Generation Rate (KGR) computation support (total_bits, bits_per_sample, bps).
9. End-to-end D03 pipeline execution on D02 filtered RSSI with schema and output verification.
10. Physical layer security sanity check: Legitimate KAR(Alice vs Bob) > Eavesdropper KAR(Alice vs Eve1).
"""

import json
import os
import sys
import numpy as np
import pandas as pd
import pytest

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.quantization import (
    ModifiedAdaptiveDualThresholdQuantizer,
    QuantizationResult,
    compute_bit_error_rate,
    compute_key_agreement_rate,
    compute_key_generation_rate,
)
from src.analysis.d03_runner import (
    APPROVED_RAW_COLUMNS,
    FILTERED_COLUMNS,
    run_d03_pipeline,
)

INPUT_CSV_PATH = os.path.join(project_root, "results", "dummy", "d02_mshkf_filtered.csv")
OUTPUT_JSON_PATH = os.path.join(project_root, "results", "dummy", "d03_quantization_results.json")
OUTPUT_BITS_CSV_PATH = os.path.join(project_root, "results", "dummy", "d03_quantized_bits.csv")
FIGURES_DIR = os.path.join(project_root, "results", "dummy", "figures", "d03")


def test_quantizer_threshold_calculation():
    """Verify adaptive threshold computation matches LoRa-PRIME Eq. 4 exactly."""
    data = np.array([10.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float64)
    expected_mu = 30.0
    expected_sigma = float(np.std(data))

    alpha = 0.5
    quantizer = ModifiedAdaptiveDualThresholdQuantizer(alpha=alpha, bit_depth=2)
    mu, sigma, q_upper, q_lower = quantizer.compute_thresholds(data)

    assert np.isclose(mu, expected_mu)
    assert np.isclose(sigma, expected_sigma)
    assert np.isclose(q_upper, expected_mu + alpha * expected_sigma)
    assert np.isclose(q_lower, expected_mu - alpha * expected_sigma)


def test_quantizer_3level_symbol_mapping():
    """Verify mapping into discrete Levels 0, 1, 2 per LoRa-PRIME Eq. 5."""
    data = np.array([-10.0, -2.0, 0.0, 2.0, 10.0], dtype=np.float64)
    quantizer = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=2)

    res = quantizer.quantize(data)
    assert res.symbols[0] == 0
    assert res.symbols[1] == 1
    assert res.symbols[2] == 1
    assert res.symbols[3] == 1
    assert res.symbols[4] == 2
    assert res.retained_samples == 5
    assert res.discarded_samples == 0


def test_quantizer_2bit_and_4bit_encodings():
    """Verify 2-bit Gray coding and 4-bit LoRa-PRIME encodings."""
    data = np.array([-100.0, 0.0, 100.0], dtype=np.float64)

    # 2-bit: Level 0 -> '00', Level 1 -> '01', Level 2 -> '11'
    q2 = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=2)
    res2 = q2.quantize(data)
    assert res2.symbols == [0, 1, 2]
    assert res2.bits == "000111"
    assert res2.bit_length == 6

    # 4-bit: Level 0 -> '1010', Level 1 -> '1011', Level 2 -> '1001'
    q4 = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=4)
    res4 = q4.quantize(data)
    assert res4.symbols == [0, 1, 2]
    assert res4.bits == "101010111001"
    assert res4.bit_length == 12


def test_intermediate_sample_retention():
    """Verify that Modified ADQ preserves intermediate samples between thresholds."""
    data = np.array([-10.0, -2.0, 0.0, 3.0, 10.0], dtype=np.float64)

    quantizer = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=2)
    res = quantizer.quantize(data)
    assert res.retained_samples == 5
    assert res.discarded_samples == 0
    assert len(res.symbols) == 5
    assert res.level_counts[1] == 3  # -2, 0, 3 are in intermediate region


def test_deterministic_output():
    """Verify multiple executions on identical input yield identical bits and symbols."""
    np.random.seed(42)
    signal = np.random.normal(loc=-75.0, scale=1.5, size=200)

    q = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.6, bit_depth=4)
    r1 = q.quantize(signal)
    r2 = q.quantize(signal)

    assert r1.symbols == r2.symbols
    assert r1.bits == r2.bits
    assert r1.bit_length == r2.bit_length
    assert r1.level_counts == r2.level_counts


def test_edge_case_constant_signal():
    """Verify quantizer handles constant (zero variance) signals without crashing or NaN."""
    const_data = np.array([-75.0] * 100, dtype=np.float64)
    q = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=2)
    res = q.quantize(const_data)

    assert res.num_samples == 100
    assert res.retained_samples == 100
    assert res.discarded_samples == 0
    # Every sample val == -75 is in intermediate region [q^-, q^+] => Level 1
    assert all(s == 1 for s in res.symbols)
    assert res.bits == "01" * 100


def test_edge_case_low_variance_signal():
    """Verify quantizer operates stably on extremely low-variance signals."""
    low_var = np.array([-75.0001, -75.0000, -74.9999] * 30, dtype=np.float64)
    q = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=4)
    res = q.quantize(low_var)

    assert res.num_samples == 90
    assert res.retained_samples == 90
    assert len(res.bits) == 90 * 4
    assert set(res.symbols).issubset({0, 1, 2})


def test_edge_case_short_and_empty_sequences():
    """Verify behavior on very short sequences and empty arrays."""
    q = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=2)

    # Empty
    empty_res = q.quantize([])
    assert empty_res.num_samples == 0
    assert empty_res.retained_samples == 0
    assert empty_res.bits == ""
    assert empty_res.bit_length == 0

    # Single sample
    single_res = q.quantize([-76.5])
    assert single_res.num_samples == 1
    assert single_res.retained_samples == 1
    assert single_res.symbols == [1]

    # Two samples
    two_res = q.quantize([-78.0, -74.0])
    assert two_res.num_samples == 2
    assert two_res.retained_samples == 2
    assert two_res.symbols[0] == 0
    assert two_res.symbols[1] == 2


def test_segmented_adaptive_quantization():
    """Verify segmented / windowed quantization updates thresholds across blocks."""
    seg_size = 20
    data = np.concatenate([
        np.full(seg_size, -80.0),
        np.full(seg_size, -70.0),
    ])

    q = ModifiedAdaptiveDualThresholdQuantizer(alpha=0.5, bit_depth=2, segment_size=seg_size)
    res = q.quantize(data)

    assert res.num_samples == 40
    assert res.retained_samples == 40
    assert all(s == 1 for s in res.symbols)
    assert res.thresholds["num_segments"] == 2


def test_key_agreement_rate_and_ber_metrics():
    """Verify KAR and BER arithmetic and boundary properties."""
    k1 = "110011"
    k2 = "110000"  # 4 matches, 2 mismatches

    kar = compute_key_agreement_rate(k1, k2)
    ber = compute_bit_error_rate(k1, k2)

    assert np.isclose(kar, 4.0 / 6.0)
    assert np.isclose(ber, 2.0 / 6.0)
    assert np.isclose(kar + ber, 1.0)

    # Identical keys
    assert np.isclose(compute_key_agreement_rate("1010", "1010"), 1.0)
    assert np.isclose(compute_bit_error_rate("1010", "1010"), 0.0)

    # Fully inverted keys
    assert np.isclose(compute_key_agreement_rate("0000", "1111"), 0.0)
    assert np.isclose(compute_bit_error_rate("0000", "1111"), 1.0)

    # Length mismatch error
    with pytest.raises(ValueError):
        compute_key_agreement_rate("101", "1010")


def test_key_generation_rate_metrics():
    """Verify KGR metrics calculation."""
    stats = compute_key_generation_rate(bit_length=1000, duration_seconds=10.0, num_samples=500)
    assert stats["total_bits"] == 1000.0
    assert stats["bits_per_sample"] == 2.0
    assert stats["bps"] == 100.0


def test_d03_pipeline_full_execution_and_schema():
    """Verify end-to-end execution of D03 pipeline produces expected CSV, JSON, and figures."""
    assert os.path.exists(INPUT_CSV_PATH), f"Input CSV {INPUT_CSV_PATH} not found"

    res = run_d03_pipeline(
        input_csv_path=INPUT_CSV_PATH,
        output_json_path=OUTPUT_JSON_PATH,
        output_bits_csv_path=OUTPUT_BITS_CSV_PATH,
        figures_dir=FIGURES_DIR,
        alpha=0.5,
    )

    # 1. Output files exist
    assert os.path.exists(OUTPUT_JSON_PATH)
    assert os.path.exists(OUTPUT_BITS_CSV_PATH)
    for fig_path in res["generated_artifacts"]["figures"].values():
        assert os.path.exists(fig_path)
        assert os.path.getsize(fig_path) > 1000

    # 2. Bits CSV schema and string format verification
    bit_dtypes = {f"{ch}_{b}": str for ch in APPROVED_RAW_COLUMNS for b in ["2bit", "4bit"]}
    df_bits = pd.read_csv(OUTPUT_BITS_CSV_PATH, dtype=bit_dtypes)
    assert len(df_bits) == 500
    for ch in APPROVED_RAW_COLUMNS:
        assert f"{ch}_Symbol" in df_bits.columns
        assert f"{ch}_2bit" in df_bits.columns
        assert f"{ch}_4bit" in df_bits.columns
        # Symbols must be in {0, 1, 2}
        assert set(df_bits[f"{ch}_Symbol"].unique()).issubset({0, 1, 2})

        # Bit sequences must be string, not integer, preserving leading zeros with Excel text format
        for raw_2b in df_bits[f"{ch}_2bit"]:
            assert isinstance(raw_2b, str)
            # Remove Excel formula escaping '=".."'
            val_2b = raw_2b.replace('=', '').replace('"', '')
            assert len(val_2b) == 2
            assert val_2b in {"00", "01", "11"}
        for raw_4b in df_bits[f"{ch}_4bit"]:
            assert isinstance(raw_4b, str)
            val_4b = raw_4b.replace('=', '').replace('"', '')
            assert len(val_4b) == 4
            assert val_4b in {"1010", "1011", "1001"}

    # Also verify that raw CSV contains string tokens preserving leading zeros with Excel text formatting
    import csv
    with open(OUTPUT_BITS_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Header
        first_row = next(reader)
        # Check that 2bit tokens are formatted as text formulas (e.g. '="00"') preserving leading zeros in Excel
        assert any(token == '="00"' for token in first_row), "Leading zeros in '00' must be preserved with Excel text format"

    # 3. JSON schema and physical layer SKG reciprocity sanity check
    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["milestone"] == "D03"
    assert data["configuration"]["sample_count"] == 500
    assert data["configuration"]["preserves_intermediate_samples"] is True

    kar_2b = data["pair_agreement_metrics"]["modified_adq_2bit"]
    kar_ab = kar_2b["Alice vs Bob"]["kar"]
    kar_ae1 = kar_2b["Alice vs Eve1-Alice"]["kar"]

    # Legitimate key agreement must significantly exceed eavesdropper correlation
    assert kar_ab > kar_ae1, f"Expected KAR_AB ({kar_ab}) > KAR_AE1 ({kar_ae1})"
    assert kar_ab > 0.80, f"Expected legitimate KAR_AB > 0.80, got {kar_ab}"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
