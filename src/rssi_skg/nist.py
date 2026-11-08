"""NIST SP 800-22 statistical randomness tests for SKG secret keys.

Governing Specification:
    PA.pdf Section 3.2.8.d, Equations (3.65)–(3.73), pages 35–37:
        1. Frequency (Monobit) Test (Eqs 3.65–3.66)
        2. Runs Test (Eqs 3.67–3.69)
        3. Approximate Entropy Test (Eqs 3.70–3.73)
    Cross-checked against official:
        NIST SP 800-22 Rev. 1a: "A Statistical Test Suite for Random and
        Pseudorandom Number Generators for Cryptographic Applications"
        - Section 2.1: Frequency (Monobit) Test
        - Section 2.3: Runs Test
        - Section 2.12: Approximate Entropy Test

Mathematical Formulation & Governing Equations:
    1. Frequency (Monobit) Test (PA.pdf Eqs 3.65–3.66, NIST Section 2.1):
       Maps bits epsilon_i in {0, 1} to X_i = 2*epsilon_i - 1 in {-1, +1}.
       Sn = sum_{i=1}^n X_i
       s_obs = |Sn| / sqrt(n)
       P-value = erfc(s_obs / sqrt(2))
       Decision: Pass if P-value >= alpha (default alpha = 0.01).

    2. Runs Test (PA.pdf Eqs 3.67–3.69, NIST Section 2.3):
       Prerequisite check:
           pi = (1/n) * sum_{i=1}^n epsilon_i
           tau = 2 / sqrt(n)
           If |pi - 0.5| >= tau, the test is NOT applicable (prerequisite fails).
           P-value is set to 0.0, and the reason is recorded.
       Observed runs count:
           V_n(obs) = 1 + sum_{k=1}^{n-1} (epsilon_k != epsilon_{k+1})
       P-value calculation:
           P-value = erfc(|V_n(obs) - 2*n*pi*(1 - pi)| / (2 * sqrt(2*n) * pi * (1 - pi)))
       Decision: Pass if P-value >= alpha (default alpha = 0.01).

    3. Approximate Entropy Test (PA.pdf Eqs 3.70–3.73, NIST Section 2.12):
       Block lengths k in {m, m+1}. Sequence is augmented circularly by appending
       the first (k-1) bits to form n overlapping blocks of length k.
       For pattern i in {0, ..., 2^k - 1}:
           C_i(k) = #(pattern_i) / n
           phi(k) = sum_{i=0}^{2^k - 1} C_i(k) * ln(C_i(k))  (with 0 * ln(0) = 0)
       ApEn(m) = phi(m) - phi(m+1)
       chi^2 = 2*n * [ln(2) - ApEn(m)]
       P-value = igamc(2^(m-1), chi^2 / 2) = scipy.special.gammaincc(2^(m-1), chi^2 / 2)
       Decision: Pass if P-value >= alpha (default alpha = 0.01).
       Length constraint: m < floor(log2(n)) - 5. For 256-bit keys, floor(log2(256)) - 5 = 3,
       so default m = 2 strictly satisfies the recommendation.

Documentation Discrepancies & Errata Notes:
    1. PA.pdf Section 3.2.8.d page 36 typographical error:
       The Runs test prerequisite is typeset as '|pi - 12 \\right | < tau'.
       This is a malformed LaTeX typesetting artifact for '|pi - 1/2| < tau'.
       The official NIST SP 800-22 Section 2.3 specification (|pi - 0.5| < 2/sqrt(n))
       is implemented strictly.
    2. Denominator grouping in Runs Test (PA.pdf Eq 3.69):
       Typeset as 2*sqrt(2n)*pi*(1-pi). Official NIST SP 800-22 Section 2.3.4 explicitly
       groups 2 * sqrt(2*n) * pi * (1 - pi), where the square root applies only to 2*n.
       This is strictly followed.
    3. Non-negativity of chi-squared in Approximate Entropy (PA.pdf Eq 3.72):
       For highly regular sequences, ApEn(m) can slightly exceed ln(2) due to finite length
       effects or floating-point rounding, yielding tiny negative chi^2. A numerical tolerance
       (-1e-9) clamps tiny negative values to 0.0, while surfacing materially invalid values.
       consistent with NIST STS reference code.

Scientific & Disclaimer Scope:
    Evaluated keys originate from synthetic indoor dummy RSSI data.
    Passing these three NIST tests on individual 256-bit keys confirms software
    algorithmic validity, but does NOT establish true physical entropy, cryptographic
    secrecy, or a full 15-test NIST suite certification.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Sequence

from scipy.special import erfc, gammaincc

from rssi_skg.privacy_amplification import (
    MultiPathPrivacyAmplificationResult,
    SCIENTIFIC_DISCLAIMER,
)

NIST_DEFAULT_ALPHA: float = 0.01
NIST_DEFAULT_APEN_M: int = 2
NIST_MIN_RECOMMENDED_LENGTH: int = 100
CHI2_NEGATIVE_TOLERANCE: float = -1e-9

RESEARCH_DISCLAIMER_NIST: str = (
    "Dummy-data software validation only. Statistical testing of 256-bit SHA-256 keys "
    "evaluates algorithmic compliance with NIST SP 800-22 Rev. 1a (PA.pdf Eqs 3.65–3.73). "
    "Passing three statistical tests on synthetic dummy keys does NOT imply physical min-entropy, "
    "cryptographic secrecy, or a comprehensive 15-test NIST suite pass."
)


def validate_bitstream(bitstream: str) -> None:
    """Validate that the input bitstream is a non-empty string of binary characters.

    Args:
        bitstream: Bitstream string to validate.

    Raises:
        ValueError: If bitstream is not a string, is empty, or contains non-binary characters.
    """
    if not isinstance(bitstream, str):
        raise ValueError(
            f"Bitstream must be a string, got {type(bitstream).__name__}."
        )
    if len(bitstream) == 0:
        raise ValueError("Bitstream cannot be empty.")
    if any(c not in ("0", "1") for c in bitstream):
        raise ValueError(
            "Bitstream must contain strictly binary characters ('0' and '1')."
        )


@dataclass(frozen=True)
class NISTConfig:
    """Configuration container for NIST SP 800-22 statistical evaluations."""

    alpha: float = NIST_DEFAULT_ALPHA
    approximate_entropy_m: int = NIST_DEFAULT_APEN_M
    min_length: int = NIST_MIN_RECOMMENDED_LENGTH
    disclaimer: str = RESEARCH_DISCLAIMER_NIST

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert configuration to metadata dictionary."""
        return {
            "significance_level_alpha": self.alpha,
            "approximate_entropy_m": self.approximate_entropy_m,
            "min_recommended_length": self.min_length,
            "governing_specifications": {
                "frequency_monobit": "PA.pdf Eq (3.65)–(3.66), NIST SP 800-22 Rev. 1a Sec 2.1",
                "runs": "PA.pdf Eq (3.67)–(3.69), NIST SP 800-22 Rev. 1a Sec 2.3",
                "approximate_entropy": "PA.pdf Eq (3.70)–(3.73), NIST SP 800-22 Rev. 1a Sec 2.12",
            },
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class NISTTestResult:
    """Container holding outcome of an individual NIST statistical test."""

    test_name: str
    statistic: float
    p_value: float
    applicable: bool
    passed: bool
    alpha: float
    details: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


@dataclass(frozen=True)
class KeyRandomnessResult:
    """Container holding complete NIST evaluation for a single 256-bit key."""

    path_name: str
    channel_name: str
    channel_role: str
    key_length: int
    key_hex: str
    key_bin: str
    monobit: NISTTestResult
    runs: NISTTestResult
    approximate_entropy: NISTTestResult
    overall_accepted: bool

    @property
    def all_applicable(self) -> bool:
        """True if all three NIST tests were applicable."""
        return self.monobit.applicable and self.runs.applicable and self.approximate_entropy.applicable


@dataclass
class MultiPathNISTResult:
    """Master container holding NIST evaluation results across all paths and channels."""

    config: NISTConfig
    channel_evaluations: dict[str, dict[str, KeyRandomnessResult]]

    @property
    def paths(self) -> dict[str, dict[str, KeyRandomnessResult]]:
        """Alias for channel_evaluations."""
        return self.channel_evaluations

    @property
    def all_results(self) -> list[KeyRandomnessResult]:
        """Return flattened list of all key evaluations."""
        out: list[KeyRandomnessResult] = []
        for path_name in sorted(self.channel_evaluations.keys()):
            for ch_name in sorted(self.channel_evaluations[path_name].keys()):
                out.append(self.channel_evaluations[path_name][ch_name])
        return out


# ==============================================================================
# Core NIST Test Implementations
# ==============================================================================


def monobit_test(bitstream: str, alpha: float = NIST_DEFAULT_ALPHA) -> NISTTestResult:
    """Execute Frequency (Monobit) Test per PA.pdf Eqs (3.65)–(3.66) & NIST Sec 2.1.

    Args:
        bitstream: Binary sequence string (e.g. '10110...').
        alpha: Significance level threshold (default: 0.01).

    Returns:
        NISTTestResult: Detailed test outcome, test statistic s_obs, and p_value.
    """
    validate_bitstream(bitstream)
    n = len(bitstream)

    if n < NIST_MIN_RECOMMENDED_LENGTH:
        return NISTTestResult(
            test_name="Frequency (Monobit)",
            statistic=0.0,
            p_value=0.0,
            applicable=False,
            passed=False,
            alpha=alpha,
            details={"n": n},
            reason=f"Input length n={n} < {NIST_MIN_RECOMMENDED_LENGTH} (NIST minimum recommendation).",
        )

    # Eq 3.65: X_i = 2*epsilon_i - 1, S_n = sum(X_i)
    sn = sum(2 * int(b) - 1 for b in bitstream)
    # s_obs = |S_n| / sqrt(n)
    s_obs = abs(sn) / math.sqrt(n)

    # Eq 3.66: P-value = erfc(s_obs / sqrt(2))
    p_val = float(erfc(s_obs / math.sqrt(2.0)))
    passed = bool(p_val >= alpha)

    return NISTTestResult(
        test_name="Frequency (Monobit)",
        statistic=float(s_obs),
        p_value=p_val,
        applicable=True,
        passed=passed,
        alpha=alpha,
        details={"n": n, "Sn": sn, "s_obs": float(s_obs)},
        reason=None if passed else f"P-value ({p_val:.6f}) < alpha ({alpha}).",
    )


def runs_test(bitstream: str, alpha: float = NIST_DEFAULT_ALPHA) -> NISTTestResult:
    """Execute Runs Test per PA.pdf Eqs (3.67)–(3.69) & NIST Sec 2.3.

    Handles prerequisite check explicitly: |pi - 0.5| < tau = 2 / sqrt(n).
    If prerequisite fails, test is not applied, p_value=0.0, and reason is recorded.

    Args:
        bitstream: Binary sequence string.
        alpha: Significance level threshold (default: 0.01).

    Returns:
        NISTTestResult: Detailed test outcome, test statistic V_n(obs), and p_value.
    """
    validate_bitstream(bitstream)
    n = len(bitstream)

    if n < NIST_MIN_RECOMMENDED_LENGTH:
        return NISTTestResult(
            test_name="Runs",
            statistic=0.0,
            p_value=0.0,
            applicable=False,
            passed=False,
            alpha=alpha,
            details={"n": n},
            reason=f"Input length n={n} < {NIST_MIN_RECOMMENDED_LENGTH} (NIST minimum recommendation).",
        )

    # Eq 3.67: pi = (1/n) * sum(epsilon_i), tau = 2 / sqrt(n)
    ones_count = sum(1 for b in bitstream if b == "1")
    pi = ones_count / float(n)
    tau = 2.0 / math.sqrt(n)
    diff = abs(pi - 0.5)

    # Prerequisite evaluation (PA.pdf page 36: |pi - 0.5| < tau)
    if diff >= tau:
        return NISTTestResult(
            test_name="Runs",
            statistic=0.0,
            p_value=0.0,
            applicable=False,
            passed=False,
            alpha=alpha,
            details={"n": n, "pi": pi, "tau": tau, "diff": diff},
            reason=(
                f"Prerequisite failed: |pi - 0.5| ({diff:.6f}) >= tau ({tau:.6f}). "
                "Frequency of zeros and ones is heavily skewed; test is not applicable "
                "per PA.pdf Eq (3.67) and NIST SP 800-22 Section 2.3."
            ),
        )

    # Eq 3.68: V_n(obs) = 1 + sum_{k=1}^{n-1} r(k), where r(k) = 1 if eps_k != eps_{k+1}
    vn_obs = 1 + sum(1 for k in range(n - 1) if bitstream[k] != bitstream[k + 1])

    # Eq 3.69: P-value = erfc(|V_n(obs) - 2*n*pi*(1-pi)| / (2 * sqrt(2*n) * pi * (1-pi)))
    num = abs(vn_obs - 2.0 * n * pi * (1.0 - pi))
    den = 2.0 * math.sqrt(2.0 * n) * pi * (1.0 - pi)

    if den == 0.0:
        p_val = 0.0
    else:
        p_val = float(erfc(num / den))

    passed = bool(p_val >= alpha)

    return NISTTestResult(
        test_name="Runs",
        statistic=float(vn_obs),
        p_value=p_val,
        applicable=True,
        passed=passed,
        alpha=alpha,
        details={
            "n": n,
            "pi": pi,
            "tau": tau,
            "diff": diff,
            "Vn_obs": vn_obs,
            "expected_runs": 2.0 * n * pi * (1.0 - pi),
        },
        reason=None if passed else f"P-value ({p_val:.6f}) < alpha ({alpha}).",
    )


def approximate_entropy_test(
    bitstream: str,
    m: int = NIST_DEFAULT_APEN_M,
    alpha: float = NIST_DEFAULT_ALPHA,
    enforce_m_bound: bool = True,
) -> NISTTestResult:
    """Execute Approximate Entropy Test per PA.pdf Eqs (3.70)–(3.73) & NIST Sec 2.12.

    Args:
        bitstream: Binary sequence string.
        m: Block length parameter (default: 2 for 256-bit keys).
        alpha: Significance level threshold (default: 0.01).
        enforce_m_bound: Whether to enforce the NIST constraint m < floor(log2(n)) - 5.
            Defaults to True. Set to False when verifying reference test vectors
            such as NIST SP 800-22 Section 2.12.8 (which deliberately chose m=2
            for n=100 for illustrative calculation purposes).

    Returns:
        NISTTestResult: Detailed test outcome, test statistic chi^2, and p_value.
    """
    validate_bitstream(bitstream)
    if not isinstance(m, int) or m < 1:
        raise ValueError(f"Block length m must be a positive integer, got {m}.")

    n = len(bitstream)

    if n < NIST_MIN_RECOMMENDED_LENGTH:
        return NISTTestResult(
            test_name="Approximate Entropy",
            statistic=0.0,
            p_value=0.0,
            applicable=False,
            passed=False,
            alpha=alpha,
            details={"n": n, "m": m},
            reason=f"Input length n={n} < {NIST_MIN_RECOMMENDED_LENGTH} (NIST minimum recommendation).",
        )

    # Constraint per NIST Sec 2.12.7 & PA.pdf page 36: m < floor(log2(n)) - 5
    max_m = math.floor(math.log2(n)) - 5
    if enforce_m_bound and m >= max_m:
        return NISTTestResult(
            test_name="Approximate Entropy",
            statistic=0.0,
            p_value=0.0,
            applicable=False,
            passed=False,
            alpha=alpha,
            details={"n": n, "m": m, "max_recommended_m": max_m},
            reason=(
                f"Block length m={m} violates constraint m < floor(log2(n)) - 5 "
                f"(max allowed m={max_m - 1} for n={n}) per NIST SP 800-22 Sec 2.12.7."
            ),
        )

    def _compute_phi(k: int) -> float:
        # Augment bitstream with first (k - 1) bits so exactly n overlapping blocks of length k exist
        aug = bitstream + (bitstream[: k - 1] if k > 1 else "")
        counts: dict[str, int] = {}
        for i in range(n):
            pat = aug[i : i + k]
            counts[pat] = counts.get(pat, 0) + 1

        val = 0.0
        for cnt in counts.values():
            if cnt > 0:
                p_i = cnt / float(n)
                val += p_i * math.log(p_i)
        return val

    # Eq 3.70 & 3.71: ApEn(m) = phi(m) - phi(m + 1)
    phi_m = _compute_phi(m)
    phi_m1 = _compute_phi(m + 1)
    apen = phi_m - phi_m1

    # Eq 3.72: chi^2 = 2*n * [ln(2) - ApEn(m)]
    chi2 = 2.0 * n * (math.log(2.0) - apen)
    # Safeguard against tiny numerical rounding errors within tolerance; surface materially invalid values
    if chi2 < CHI2_NEGATIVE_TOLERANCE:
        raise ValueError(
            f"Materially negative chi-square statistic encountered in Approximate Entropy: {chi2:.9e} < {CHI2_NEGATIVE_TOLERANCE}."
        )
    if chi2 < 0.0:
        chi2 = 0.0

    # Eq 3.73: P-value = igamc(2^(m-1), chi^2 / 2)
    # scipy.special.gammaincc(a, x) implements Q(a, x), the normalized upper incomplete gamma function
    p_val = float(gammaincc(2 ** (m - 1), chi2 / 2.0))
    passed = bool(p_val >= alpha)

    return NISTTestResult(
        test_name="Approximate Entropy",
        statistic=float(chi2),
        p_value=p_val,
        applicable=True,
        passed=passed,
        alpha=alpha,
        details={
            "n": n,
            "m": m,
            "phi_m": phi_m,
            "phi_m_plus_1": phi_m1,
            "ApEn": apen,
            "chi2": chi2,
        },
        reason=None if passed else f"P-value ({p_val:.6f}) < alpha ({alpha}).",
    )


def evaluate_key_randomness(
    bitstream: str,
    path_name: str,
    channel_name: str,
    channel_role: str,
    key_hex: str,
    config: NISTConfig | None = None,
) -> KeyRandomnessResult:
    """Evaluate all three NIST randomness tests for a single derived key.

    Overall acceptance strictly requires all three tests to be applicable AND passed.

    Args:
        bitstream: 256-bit binary key string.
        path_name: Name of the pipeline path ('quant_2bit' or 'prbs_2bit').
        channel_name: Name of channel (e.g. 'Alice', 'Bob', 'Eve1-Alice').
        channel_role: Role description string.
        key_hex: 64-character lowercase hex digest.
        config: NISTConfig instance (defaults if None).

    Returns:
        KeyRandomnessResult: Complete per-test and overall acceptance outcome.
    """
    cfg = config if config is not None else NISTConfig()

    res_mono = monobit_test(bitstream, alpha=cfg.alpha)
    res_runs = runs_test(bitstream, alpha=cfg.alpha)
    res_apen = approximate_entropy_test(bitstream, m=cfg.approximate_entropy_m, alpha=cfg.alpha)

    # Overall acceptance requires all three tests to be applicable and passed
    overall = (
        res_mono.applicable
        and res_mono.passed
        and res_runs.applicable
        and res_runs.passed
        and res_apen.applicable
        and res_apen.passed
    )

    return KeyRandomnessResult(
        path_name=path_name,
        channel_name=channel_name,
        channel_role=channel_role,
        key_length=len(bitstream),
        key_hex=key_hex,
        key_bin=bitstream,
        monobit=res_mono,
        runs=res_runs,
        approximate_entropy=res_apen,
        overall_accepted=overall,
    )


def evaluate_pa_keys_randomness(
    pa_result: MultiPathPrivacyAmplificationResult,
    config: NISTConfig | None = None,
) -> MultiPathNISTResult:
    """Evaluate NIST SP 800-22 tests across all 256-bit keys from Privacy Amplification.

    Preserves channel and pair roles across both reconciled paths ('quant_2bit' and 'prbs_2bit').

    Args:
        pa_result: Completed MultiPathPrivacyAmplificationResult.
        config: NISTConfig instance.

    Returns:
        MultiPathNISTResult: Master container holding all evaluations.
    """
    cfg = config if config is not None else NISTConfig()
    evaluations: dict[str, dict[str, KeyRandomnessResult]] = {}

    for path_name, channels in pa_result.channel_keys.items():
        evaluations[path_name] = {}
        for ch_name, ch_res in channels.items():
            k_eval = evaluate_key_randomness(
                bitstream=ch_res.key_bin,
                path_name=path_name,
                channel_name=ch_name,
                channel_role=ch_res.channel_role,
                key_hex=ch_res.key_hex,
                config=cfg,
            )
            evaluations[path_name][ch_name] = k_eval

    return MultiPathNISTResult(
        config=cfg,
        channel_evaluations=evaluations,
    )


# ==============================================================================
# Artifact Exporters (CSV, JSON)
# ==============================================================================


def export_nist_metrics_csv(
    nist_result: MultiPathNISTResult,
    output_path: str | Path,
) -> Path:
    """Export detailed NIST test statistics, p-values, applicability, and pass/fail to CSV.

    Columns:
        path, channel, channel_role, key_length, key_hex,
        monobit_stat, monobit_p_value, monobit_applicable, monobit_passed,
        runs_stat, runs_p_value, runs_applicable, runs_passed, runs_reason,
        apen_stat, apen_p_value, apen_applicable, apen_passed, apen_reason,
        overall_accepted
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
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
        "runs_reason",
        "apen_stat",
        "apen_p_value",
        "apen_applicable",
        "apen_passed",
        "apen_reason",
        "overall_accepted",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in nist_result.all_results:
            writer.writerow(
                {
                    "path": res.path_name,
                    "channel": res.channel_name,
                    "channel_role": res.channel_role,
                    "key_length": res.key_length,
                    "key_hex": res.key_hex,
                    "monobit_stat": round(res.monobit.statistic, 6),
                    "monobit_p_value": round(res.monobit.p_value, 6),
                    "monobit_applicable": "TRUE" if res.monobit.applicable else "FALSE",
                    "monobit_passed": "TRUE" if res.monobit.passed else "FALSE",
                    "runs_stat": round(res.runs.statistic, 6),
                    "runs_p_value": round(res.runs.p_value, 6),
                    "runs_applicable": "TRUE" if res.runs.applicable else "FALSE",
                    "runs_passed": "TRUE" if res.runs.passed else "FALSE",
                    "runs_reason": res.runs.reason or "",
                    "apen_stat": round(res.approximate_entropy.statistic, 6),
                    "apen_p_value": round(res.approximate_entropy.p_value, 6),
                    "apen_applicable": "TRUE" if res.approximate_entropy.applicable else "FALSE",
                    "apen_passed": "TRUE" if res.approximate_entropy.passed else "FALSE",
                    "apen_reason": res.approximate_entropy.reason or "",
                    "overall_accepted": "TRUE" if res.overall_accepted else "FALSE",
                }
            )
    return out


def export_nist_config_json(
    nist_result: MultiPathNISTResult,
    output_path: str | Path,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Export NIST evaluation configuration and summary metadata to JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    for res in nist_result.all_results:
        summary.append(
            {
                "path": res.path_name,
                "channel": res.channel_name,
                "channel_role": res.channel_role,
                "overall_accepted": res.overall_accepted,
                "tests": {
                    "monobit": {
                        "statistic": res.monobit.statistic,
                        "p_value": res.monobit.p_value,
                        "applicable": res.monobit.applicable,
                        "passed": res.monobit.passed,
                        "reason": res.monobit.reason,
                    },
                    "runs": {
                        "statistic": res.runs.statistic,
                        "p_value": res.runs.p_value,
                        "applicable": res.runs.applicable,
                        "passed": res.runs.passed,
                        "reason": res.runs.reason,
                    },
                    "approximate_entropy": {
                        "statistic": res.approximate_entropy.statistic,
                        "p_value": res.approximate_entropy.p_value,
                        "applicable": res.approximate_entropy.applicable,
                        "passed": res.approximate_entropy.passed,
                        "reason": res.approximate_entropy.reason,
                    },
                },
            }
        )

    meta = {
        "scientific_disclaimer": nist_result.config.disclaimer,
        "nist_config": nist_result.config.to_metadata_dict(),
        "summary": summary,
    }
    if extra_metadata:
        meta.update(extra_metadata)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out
