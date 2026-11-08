"""Unit tests for Stage 7 — NIST SP 800-22 Randomness Testing (PA.pdf Section 3.2.8.d & Eqs 3.65–3.73).

Verifies:
1. NIST official SP 800-22 Rev. 1a Section 2.1.8 reference test vector for Frequency (Monobit).
2. Frequency (Monobit) edge cases (all zeros, all ones, perfectly balanced).
3. NIST official SP 800-22 Rev. 1a Section 2.3.8 reference test vector for Runs.
4. Runs prerequisite enforcement (|pi - 0.5| >= tau => applicable=False, p_value=0.0).
5. Runs edge cases (strictly alternating, single run).
6. NIST official SP 800-22 Rev. 1a Section 2.12.8 reference test vector for Approximate Entropy (m=2).
7. Approximate Entropy constraint enforcement (m < floor(log2(n)) - 5).
8. Input validation (non-binary characters, non-string, empty string, short bitstreams n < 100, invalid m).
9. KeyRandomnessResult overall acceptance logic (all three tests must be applicable AND passed).
10. Full pipeline evaluation on dummy dataset across quant_2bit and prbs_2bit preserving channel/pair roles.
11. Artifact exporters (CSV metrics and config JSON with scientific validation disclaimer).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.nist import (
    CHI2_NEGATIVE_TOLERANCE,
    NIST_DEFAULT_ALPHA,
    NIST_DEFAULT_APEN_M,
    NIST_MIN_RECOMMENDED_LENGTH,
    SCIENTIFIC_DISCLAIMER,
    KeyRandomnessResult,
    MultiPathNISTResult,
    NISTConfig,
    NISTTestResult,
    approximate_entropy_test,
    evaluate_key_randomness,
    evaluate_pa_keys_randomness,
    export_nist_config_json,
    export_nist_metrics_csv,
    monobit_test,
    runs_test,
    validate_bitstream,
)
from rssi_skg.prbs import PRBSConfig, expand_channels_prbs
from rssi_skg.privacy_amplification import PrivacyAmplificationConfig, amplify_privacy_all_paths
from rssi_skg.quantization import QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import ReconciliationConfig, reconcile_all_paths


# ==============================================================================
# NIST SP 800-22 Rev. 1a Official 100-Bit Reference Sequence (Sections 2.1.8, 2.3.8, 2.12.8)
# ==============================================================================
NIST_REF_100_BITS = (
    "11001001000011111101"
    "10101010001000100001"
    "01101000110000100011"
    "01001100010011000110"
    "01100010100010111000"
)


# ==============================================================================
# 1. Frequency (Monobit) Test Tests
# ==============================================================================


def test_monobit_nist_reference_vector() -> None:
    """Verify Frequency (Monobit) against NIST SP 800-22 Rev. 1a Section 2.1.8.

    Reference values for n=100 bits:
        S_n = -16
        s_obs = 1.6
        p_value = 0.109599
        Decision: Pass (p_value >= 0.01)
    """
    assert len(NIST_REF_100_BITS) == 100
    res = monobit_test(NIST_REF_100_BITS, alpha=0.01)

    assert res.test_name == "Frequency (Monobit)"
    assert res.applicable is True
    assert res.passed is True
    assert res.details["n"] == 100
    assert res.details["Sn"] == -16
    assert res.statistic == pytest.approx(1.6, abs=1e-5)
    assert res.p_value == pytest.approx(0.109599, abs=1e-5)
    assert res.reason is None


def test_monobit_edge_cases() -> None:
    """Verify Frequency (Monobit) edge cases."""
    # All zeros (n=100): S_n = -100, s_obs = 10.0, p_val ~ 1.52e-23 -> Fail
    res_zeros = monobit_test("0" * 100)
    assert res_zeros.applicable is True
    assert res_zeros.passed is False
    assert res_zeros.statistic == pytest.approx(10.0, abs=1e-5)
    assert res_zeros.p_value < 1e-10
    assert res_zeros.reason is not None

    # All ones (n=100): S_n = +100, s_obs = 10.0, p_val ~ 1.52e-23 -> Fail
    res_ones = monobit_test("1" * 100)
    assert res_ones.applicable is True
    assert res_ones.passed is False
    assert res_ones.statistic == pytest.approx(10.0, abs=1e-5)
    assert res_ones.p_value < 1e-10

    # Perfectly balanced sequence (n=100): S_n = 0, s_obs = 0.0, p_val = 1.0 -> Pass
    res_bal = monobit_test("10" * 50)
    assert res_bal.applicable is True
    assert res_bal.passed is True
    assert res_bal.statistic == 0.0
    assert res_bal.p_value == 1.0


# ==============================================================================
# 2. Runs Test Tests
# ==============================================================================


def test_runs_nist_reference_vector() -> None:
    """Verify Runs Test against NIST SP 800-22 Rev. 1a Section 2.3.8.

    Reference values for n=100 bits:
        pi = 42/100 = 0.42
        tau = 2 / sqrt(100) = 0.2
        |pi - 0.5| = 0.08 < 0.2 (Prerequisite satisfied)
        V_n(obs) = 52
        p_value = 0.500798
        Decision: Pass (p_value >= 0.01)
    """
    res = runs_test(NIST_REF_100_BITS, alpha=0.01)

    assert res.test_name == "Runs"
    assert res.applicable is True
    assert res.passed is True
    assert res.details["n"] == 100
    assert res.details["pi"] == pytest.approx(0.42, abs=1e-5)
    assert res.details["tau"] == pytest.approx(0.20, abs=1e-5)
    assert res.statistic == 52.0
    assert res.p_value == pytest.approx(0.500798, abs=1e-5)
    assert res.reason is None


def test_runs_prerequisite_failure() -> None:
    """Verify that Runs prerequisite failure explicitly records p=0 and applicable=False."""
    # Sequence with 90 ones and 10 zeros: pi = 0.90, |pi - 0.5| = 0.40 >= tau = 0.20
    skewed = "1" * 90 + "0" * 10
    res = runs_test(skewed, alpha=0.01)

    assert res.applicable is False
    assert res.passed is False
    assert res.p_value == 0.0
    assert res.statistic == 0.0
    assert res.reason is not None
    assert "Prerequisite failed" in res.reason


def test_runs_edge_cases() -> None:
    """Verify Runs edge cases."""
    # Strictly alternating sequence: "101010..." -> V_n(obs) = 100, excessively many runs -> Fail
    alt = "10" * 50
    res_alt = runs_test(alt, alpha=0.01)
    assert res_alt.applicable is True
    assert res_alt.details["Vn_obs"] == 100
    assert res_alt.passed is False  # p_value extremely close to 0

    # Half zeros, half ones: "0"*50 + "1"*50 -> V_n(obs) = 2, too few runs -> Fail
    half = "0" * 50 + "1" * 50
    res_half = runs_test(half, alpha=0.01)
    assert res_half.applicable is True
    assert res_half.details["Vn_obs"] == 2
    assert res_half.passed is False


# ==============================================================================
# 3. Approximate Entropy Test Tests
# ==============================================================================


def test_approximate_entropy_nist_reference_vector() -> None:
    """Verify Approximate Entropy against NIST SP 800-22 Rev. 1a Section 2.12.8.

    Reference values for n=100 bits, m=2 (relaxing recommendation 3 for verification):
        phi(2) = -1.358310
        phi(3) = -2.023704
        ApEn(2) = 0.665393
        chi^2 = 5.550792
        p_value = 0.235301
        Decision: Pass (p_value >= 0.01)
    """
    res = approximate_entropy_test(NIST_REF_100_BITS, m=2, alpha=0.01, enforce_m_bound=False)

    assert res.test_name == "Approximate Entropy"
    assert res.applicable is True
    assert res.passed is True
    assert res.details["n"] == 100
    assert res.details["m"] == 2
    assert res.details["phi_m"] == pytest.approx(-1.358310, abs=1e-5)
    assert res.details["phi_m_plus_1"] == pytest.approx(-2.023704, abs=1e-5)
    assert res.details["ApEn"] == pytest.approx(0.665393, abs=1e-5)
    assert res.statistic == pytest.approx(5.550792, abs=1e-5)
    assert res.p_value == pytest.approx(0.235301, abs=1e-5)


def test_approximate_entropy_m_bound_constraint() -> None:
    """Verify Approximate Entropy recommendation constraint m < floor(log2(n)) - 5."""
    # For n=100: floor(log2(100)) - 5 = 6 - 5 = 1.
    # With m=2, m >= 1 => violates constraint when enforce_m_bound=True
    res_100 = approximate_entropy_test(NIST_REF_100_BITS, m=2, alpha=0.01, enforce_m_bound=True)
    assert res_100.applicable is False
    assert res_100.passed is False
    assert res_100.p_value == 0.0
    assert "violates constraint" in str(res_100.reason)

    # For 256-bit SHA-256 keys: floor(log2(256)) - 5 = 8 - 5 = 3.
    # m=2 satisfies m < 3, so it is strictly valid and applicable!
    dummy_256 = ("11001010" * 32)
    res_256 = approximate_entropy_test(dummy_256, m=2, alpha=0.01, enforce_m_bound=True)
    assert res_256.applicable is True


def test_approximate_entropy_chi2_negative_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that chi2 within [-1e-9, 0) is clamped to 0.0, while chi2 < -1e-9 raises ValueError."""
    import math

    dummy_256 = "11001010" * 32
    orig_log = math.log

    # 1. Materially negative chi^2 (< -1e-9) raises ValueError
    def mock_log_materially_neg(x: float, *args: object) -> float:
        if x == 2.0:
            return -10.0
        return orig_log(x, *args)

    with monkeypatch.context() as m:
        m.setattr(math, "log", mock_log_materially_neg)
        with pytest.raises(ValueError, match="Materially negative chi-square statistic encountered"):
            approximate_entropy_test(dummy_256, m=2, alpha=0.01)

    # 2. Tiny negative chi^2 within numerical tolerance is clamped to 0.0
    res_normal = approximate_entropy_test(dummy_256, m=2, alpha=0.01)
    target_apen = res_normal.details["ApEn"]

    # Target: chi2 = 2 * n * (log(2) - apen) = -5e-10 (within [-1e-9, 0))
    delta = 5e-10 / (2.0 * len(dummy_256))
    def mock_log_tiny_neg(x: float, *args: object) -> float:
        if x == 2.0:
            return target_apen - delta
        return orig_log(x, *args)

    with monkeypatch.context() as m:
        m.setattr(math, "log", mock_log_tiny_neg)
        res_clamped = approximate_entropy_test(dummy_256, m=2, alpha=0.01)
        assert res_clamped.statistic == 0.0
        assert res_clamped.passed is True
        assert res_clamped.p_value == 1.0


# ==============================================================================
# 4. Input Validation & Error Handling
# ==============================================================================


def test_nist_input_validation() -> None:
    """Verify validation on bitstreams and m parameters."""
    # Non-binary character
    with pytest.raises(ValueError, match="strictly binary characters"):
        monobit_test("01010201")

    with pytest.raises(ValueError, match="strictly binary characters"):
        runs_test("0101A010")

    with pytest.raises(ValueError, match="strictly binary characters"):
        approximate_entropy_test("0101b01")

    # Empty string
    with pytest.raises(ValueError, match="Bitstream cannot be empty"):
        validate_bitstream("")

    # Non-string input
    with pytest.raises(ValueError, match="Bitstream must be a string"):
        validate_bitstream(10101)  # type: ignore[arg-type]

    # Invalid m
    with pytest.raises(ValueError, match="Block length m must be a positive integer"):
        approximate_entropy_test(NIST_REF_100_BITS, m=0)

    with pytest.raises(ValueError, match="Block length m must be a positive integer"):
        approximate_entropy_test(NIST_REF_100_BITS, m=-2)


def test_nist_length_rejection() -> None:
    """Verify that sequences shorter than NIST minimum (n < 100) are marked not applicable."""
    short = "11001010" * 10  # 80 bits < 100
    res_m = monobit_test(short)
    assert res_m.applicable is False
    assert res_m.passed is False
    assert res_m.p_value == 0.0
    assert "Input length n=80 < 100" in str(res_m.reason)

    res_r = runs_test(short)
    assert res_r.applicable is False
    assert res_r.passed is False

    res_a = approximate_entropy_test(short)
    assert res_a.applicable is False
    assert res_a.passed is False


# ==============================================================================
# 5. KeyRandomnessResult Overall Acceptance Logic
# ==============================================================================


def test_evaluate_key_randomness_acceptance() -> None:
    """Verify overall acceptance strictly requires all three tests to pass and be applicable."""
    # Highly skewed key (e.g. 250 ones and 6 zeros): fails Monobit and Runs prerequisite
    bad_key = "1" * 250 + "0" * 6
    res_bad = evaluate_key_randomness(
        bitstream=bad_key,
        path_name="quant_2bit",
        channel_name="Alice",
        channel_role="Legitimate transmitter",
        key_hex="0" * 64,
    )
    assert res_bad.monobit.passed is False
    assert res_bad.runs.applicable is False
    assert res_bad.overall_accepted is False

    # A balanced pseudo-random 256-bit key
    # Generated from standard SHA-256 of "seed"
    import hashlib
    key_bytes = hashlib.sha256(b"skg_test_seed_12345").digest()
    key_bits = "".join(f"{b:08b}" for b in key_bytes)
    res_good = evaluate_key_randomness(
        bitstream=key_bits,
        path_name="quant_2bit",
        channel_name="Alice",
        channel_role="Legitimate transmitter",
        key_hex=key_bytes.hex(),
    )
    assert res_good.monobit.applicable is True
    assert res_good.monobit.passed is True
    assert res_good.runs.applicable is True
    assert res_good.runs.passed is True
    assert res_good.approximate_entropy.applicable is True
    assert res_good.approximate_entropy.passed is True
    assert res_good.overall_accepted is True


# ==============================================================================
# 6. Full Pipeline Evaluation on Dummy Dataset
# ==============================================================================


def test_evaluate_pa_keys_randomness_dummy_data() -> None:
    """Verify evaluation of actual privacy-amplified keys on dummy dataset."""
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    filtered = filter_rssi_channels(raw, FilterConfig())
    quant = quantize_channels(filtered, QuantizationConfig())
    prbs = expand_channels_prbs(quant, PRBSConfig())
    recon = reconcile_all_paths(quant, prbs, ReconciliationConfig(seed=42))
    pa = amplify_privacy_all_paths(recon)

    nist_res = evaluate_pa_keys_randomness(pa, NISTConfig(alpha=0.01, approximate_entropy_m=2))

    assert isinstance(nist_res, MultiPathNISTResult)
    assert "quant_2bit" in nist_res.paths
    assert "prbs_2bit" in nist_res.paths

    for path_name in ["quant_2bit", "prbs_2bit"]:
        path_nist = nist_res.paths[path_name]
        # Check channels
        assert "Alice" in path_nist
        assert "Bob" in path_nist
        assert "Eve1-Alice" in path_nist
        assert "Eve1-Bob" in path_nist

        # Alice must be evaluated and accepted
        alice_res = path_nist["Alice"]
        assert alice_res.monobit.applicable is True
        assert alice_res.monobit.passed is True
        assert alice_res.runs.applicable is True
        assert alice_res.runs.passed is True
        assert alice_res.approximate_entropy.applicable is True
        assert alice_res.approximate_entropy.passed is True
        assert alice_res.overall_accepted is True


# ==============================================================================
# 7. NIST Exporters (CSV & JSON)
# ==============================================================================


def test_nist_exporters(tmp_path: Path) -> None:
    """Verify CSV and JSON export functions for NIST metrics."""
    raw = load_rssi_workbook("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    filtered = filter_rssi_channels(raw, FilterConfig())
    quant = quantize_channels(filtered, QuantizationConfig())
    prbs = expand_channels_prbs(quant, PRBSConfig())
    recon = reconcile_all_paths(quant, prbs, ReconciliationConfig(seed=42))
    pa = amplify_privacy_all_paths(recon)
    nist_res = evaluate_pa_keys_randomness(pa, NISTConfig())

    csv_out = tmp_path / "nist_metrics.csv"
    json_out = tmp_path / "nist_config.json"

    export_nist_metrics_csv(nist_res, csv_out)
    export_nist_config_json(nist_res, json_out, extra_metadata={"run": "unit_test"})

    assert csv_out.exists()
    assert json_out.exists()

    # Verify CSV format and contents
    with open(csv_out, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 2 paths * 4 channels = 8 rows (wide format per key)
    assert len(rows) == 8
    expected_fields = {
        "path",
        "channel",
        "channel_role",
        "key_length",
        "key_hex",
        "monobit_stat",
        "monobit_p_value",
        "monobit_applicable",
        "monobit_passed",
        "runs_stat",
        "runs_p_value",
        "runs_applicable",
        "runs_passed",
        "apen_stat",
        "apen_p_value",
        "apen_applicable",
        "apen_passed",
        "overall_accepted",
    }
    assert set(expected_fields).issubset(set(reader.fieldnames or []))

    # Verify JSON format and metadata
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["scientific_disclaimer"] == nist_res.config.disclaimer
    assert data["run"] == "unit_test"
    assert "summary" in data
    paths = {item["path"] for item in data["summary"]}
    assert "quant_2bit" in paths
    assert "prbs_2bit" in paths
