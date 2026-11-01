"""Information Reconciliation module.

Governing Specification:
    PA.pdf Section 3.2.5, Equations (3.27)–(3.36), pages 29–30 (Information Reconciliation with BCH Codes).
    PA.pdf Section 3.2.8.c, Equation (3.64), page 35 (Key Agreement Rate).
    (Note: Privacy amplification from Section 3.2.6 is NOT part of this stage and requires a separate request.)

Mathematical Formulation (Codeword-Based Helper Data / Code-Offset / Secure Sketch):
    1. Source A partitions its unpadded bitstream of length L into M = ceil(L / n) blocks.
       The final block is zero-padded to n bits if (L mod n) != 0.
    2. For each block i:
       - Generate an independent random k-bit message u_i in {0, 1}^k.
       - Encode u_i into a valid BCH codeword C_i = Encode(u_i) in {0, 1}^n (Eq 3.29–3.31).
       - Compute public auxiliary / helper data (Eq 3.32):
             H_i = A_i XOR C_i
       - Publish H_i. The random message u_i and codeword C_i are never published.
    3. Receiver B combines helper data with its own observation B_i (Eq 3.33):
             C'_i = H_i XOR B_i = C_i XOR (A_i XOR B_i) = C_i XOR Noise_i
    4. Receiver B decodes C'_i using BCH syndrome and Berlekamp–Massey / Chien search (Eq 3.34–3.35):
             C_hat_i = Decode(C'_i)
       If errors <= t, C_hat_i = C_i. If errors > t, either detected failure or miscorrection occurs.
    5. Receiver B reconstructs source bits (Eq 3.36):
             A_hat_i = H_i XOR C_hat_i
    6. Stripping padding:
       The final pad_count bits are removed from A_hat: A_hat_unpad = A_hat[:L].

Security & Scientific Boundaries:
    - PRBS deterministic expansion adds NO physical channel entropy.
    - Helper data H leaks information regarding source bits (up to n - k bits per block).
    - Software validation on dummy indoor data cannot establish empirical secrecy.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import functools
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import galois
import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from rssi_skg.prbs import MultiChannelPRBSResult
from rssi_skg.quantization import ChannelQuantizationResult, EXCEL_MAX_CELL_CHARS

# ==============================================================================
# Global BCH Configuration Source
# ==============================================================================
# Single editable configuration source used across both paths (quant_2bit, prbs_2bit)
# and all legitimate and eavesdropper receivers.
#
# Rules for editing parameters:
#   1. n must be a valid primitive BCH block length: n = 2^m - 1 (e.g. 15, 31, 63, 127, 255, 511, 1023).
#   2. t is the requested error-correction capability.
#   3. designed_d is derived automatically as designed_d = 2 * t + 1.
#   4. k is the message dimension returned by galois.BCH(n, d=designed_d).
#   5. The tuple (n, k, t) must be strictly consistent with Galois; inconsistent values raise ValueError.
DEFAULT_BCH_CODE: tuple[int, int, int] = (1023, 46, 200)
GLOBAL_BCH_CODE: tuple[int, int, int] = DEFAULT_BCH_CODE
INTERLEAVING_STATUS: str = "OFF"

PATHS: tuple[str, ...] = ("quant_2bit", "prbs_2bit")
OBSOLETE_PATHS: tuple[str, ...] = ("quant_4bit", "prbs_4bit")

EVALUATION_PAIRS: tuple[tuple[str, str, str, str], ...] = (
    ("Alice", "Bob", "Alice–Bob", "Alice"),
    ("Alice", "Eve1-Alice", "Alice–Eve1-Alice", "Alice"),
    ("Bob", "Eve1-Bob", "Bob–Eve1-Bob", "Bob"),
)

RESEARCH_ARTIFACT_LABEL: str = "[DUMMY RESEARCH ARTIFACT - SYNTHETIC DATA ONLY]"


@functools.lru_cache(maxsize=32)
def get_bch_code(n: int, k: int, t: int | None = None) -> galois.BCH:
    """Retrieve or construct a verified galois BCH instance.

    Constructs galois.BCH(n, d=designed_d) where designed_d = 2 * t + 1,
    then verifies actual n, k, and t against the requested configuration.
    Invalid combinations raise an actionable ValueError; parameters are
    never silently substituted.

    Args:
        n: Codeword length (e.g. 1023).
        k: Message length (e.g. 46).
        t: Error-correction capability (e.g. 200). If None, t is derived from galois.BCH(n, k=k).

    Returns:
        galois.BCH: Verified BCH code instance.

    Raises:
        ValueError: If n, k, t parameters cannot form a valid code or do not match actual Galois parameters.
    """
    if n <= 0 or k <= 0 or (t is not None and t <= 0):
        raise ValueError(f"BCH parameters must be positive integers, got (n={n}, k={k}, t={t}).")
    if k >= n:
        raise ValueError(f"BCH message length k ({k}) must be strictly less than codeword length n ({n}).")

    if t is None:
        try:
            temp = galois.BCH(n, k=k)
            t = int(temp.t)
        except Exception as err:
            raise ValueError(f"Failed to find valid BCH code for n={n}, k={k}: {err}") from err

    designed_d = 2 * t + 1
    try:
        bch = galois.BCH(n, d=designed_d)
    except Exception as err:
        raise ValueError(
            f"Failed to construct galois.BCH(n={n}, d={designed_d}) (derived from t={t}): {err}"
        ) from err

    if bch.n != n or bch.k != k or bch.t != t:
        raise ValueError(
            f"Requested BCH configuration (n={n}, k={k}, t={t}) is inconsistent with Galois code: "
            f"galois.BCH({n}, d={designed_d}) yields actual parameters (n={bch.n}, k={bch.k}, t={bch.t}, d={bch.d}). "
            "Silent parameter substitution is prohibited."
        )

    return bch


@dataclass(frozen=True)
class ReconciliationConfig:
    """Configuration for BCH reconciliation and candidate-key extraction.

    Supports ONLY 2-bit paths (quant_2bit and prbs_2bit).
    Both paths and all receivers obtain their BCH code from a single global configuration source.

    Attributes:
        code: (n, k, t) tuple for the BCH code (default: (1023, 46, 200)).
        random_seed: Optional integer seed for reproducible random codeword generation.
        seed: Optional alias for random_seed.
        interleaving: Interleaving status (strictly 'OFF').
    """

    code: tuple[int, int, int] = DEFAULT_BCH_CODE
    random_seed: int | None = None
    seed: int | None = None
    interleaving: str = "OFF"

    def __init__(
        self,
        code: tuple[int, int, int] | None = None,
        random_seed: int | None = None,
        seed: int | None = None,
        interleaving: str = "OFF",
        **kwargs: Any,
    ) -> None:
        for obsolete_param in (
            "code_quant_2bit",
            "code_prbs_2bit",
            "mode",
            "code_quant_4bit",
            "code_prbs_4bit",
            "designed_distance",
        ):
            if obsolete_param in kwargs:
                raise ValueError(
                    f"Parameter '{obsolete_param}' is obsolete and has been removed. "
                    "A single global BCH configuration (default n=1023, k=46, t=200) is now used for both paths. "
                    "Configure 'code=(n, k, t)' instead."
                )
        if kwargs:
            unexpected = next(iter(kwargs))
            raise TypeError(f"ReconciliationConfig.__init__() got an unexpected keyword argument '{unexpected}'.")

        effective_code = code if code is not None else DEFAULT_BCH_CODE
        if not (isinstance(effective_code, (tuple, list)) and len(effective_code) == 3):
            raise TypeError(f"code must be a 3-tuple (n, k, t), got {effective_code!r}.")
        n, k, t = effective_code
        if not (isinstance(n, int) and isinstance(k, int) and isinstance(t, int)):
            raise TypeError(f"All elements of code must be integers, got {effective_code!r}.")

        # Verify and cache BCH code immediately to reject invalid combinations
        get_bch_code(n, k, t)

        effective_seed = seed if seed is not None else random_seed
        if effective_seed is not None:
            if isinstance(effective_seed, bool) or not isinstance(effective_seed, int):
                raise TypeError(
                    f"random_seed must be an integer or None, got {type(effective_seed).__name__}."
                )

        if interleaving != "OFF":
            raise ValueError(f"Interleaving must be 'OFF', got {interleaving!r}.")

        object.__setattr__(self, "code", (n, k, t))
        object.__setattr__(self, "random_seed", effective_seed)
        object.__setattr__(self, "seed", effective_seed)
        object.__setattr__(self, "interleaving", interleaving)

    @property
    def n(self) -> int:
        return self.code[0]

    @property
    def k(self) -> int:
        return self.code[1]

    @property
    def t(self) -> int:
        return self.code[2]

    @property
    def designed_distance(self) -> int:
        return 2 * self.code[2] + 1

    @property
    def designed_d(self) -> int:
        return 2 * self.code[2] + 1

    @property
    def code_quant_2bit(self) -> tuple[int, int, int]:
        return self.code

    @property
    def code_prbs_2bit(self) -> tuple[int, int, int]:
        return self.code

    def get_code_for_path(self, path_name: str) -> tuple[int, int, int]:
        """Return the (n, k, t) code tuple for the specified path."""
        if path_name in OBSOLETE_PATHS:
            raise ValueError(
                f"Obsolete reconciliation path '{path_name}': 4-bit reconciliation has been removed. "
                f"Only {PATHS} are supported."
            )
        if path_name in PATHS:
            return self.code
        raise ValueError(f"Unknown path name: {path_name!r}. Must be one of {PATHS}.")

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert configuration to structured metadata dictionary."""
        d_val = self.designed_distance
        rate = float(self.k / self.n)
        return {
            "algorithm": "Codeword-Based BCH Information Reconciliation",
            "governing_specification": {
                "bch_reconciliation": "PA.pdf Section 3.2.5, Equations (3.27)–(3.36), pages 29–30",
                "key_agreement_rate": "PA.pdf Section 3.2.8.c, Equation (3.64), page 35",
            },
            "parameters": {
                "n": self.n,
                "k": self.k,
                "t": self.t,
                "designed_d": d_val,
                "interleaving": self.interleaving,
                "rate": rate,
                "paths": {
                    "quant_2bit": {
                        "n": self.n,
                        "k": self.k,
                        "t": self.t,
                        "designed_d": d_val,
                        "interleaving": self.interleaving,
                        "rate": rate,
                    },
                    "prbs_2bit": {
                        "n": self.n,
                        "k": self.k,
                        "t": self.t,
                        "designed_d": d_val,
                        "interleaving": self.interleaving,
                        "rate": rate,
                    },
                },
                "random_seed": self.random_seed,
            },
            "methodology_and_security_notes": {
                "entropy_warning": (
                    "PRBS bit expansion is a deterministic linear state machine and does not add physical channel entropy. "
                    "Public helper data H = A XOR C leaks up to (n - k) bits per block."
                ),
                "evaluation_boundary": (
                    "Software validation on synthetic dummy indoor data; physical channel probing postponed. "
                    "Dummy-data comparison; global configuration has reported public-information leakage. "
                    "KAR does not establish secrecy."
                ),
                "leakage_mechanism": (
                    "Without interleaving, known padding reveals the final PRBS block; the reported full-stream "
                    "attack additionally uses per-sample PRBS parity constraints."
                ),
            },
        }


def generate_helper_data(
    source_bits: Sequence[int] | str,
    n: int,
    k: int,
    t: int | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[list[np.ndarray], int, int]:
    """Generate codeword-based helper data H = A XOR C per PA.pdf Eq (3.32).

    Args:
        source_bits: Source party bitstream (e.g. Alice's bits).
        n: BCH codeword length.
        k: BCH message length.
        t: BCH error-correction capability (optional; derived if omitted).
        rng: NumPy random generator for independent k-bit message generation.

    Returns:
        tuple: (helper_blocks, original_length, padding_count) where helper_blocks
            is a list of 1D numpy arrays of length n with dtype int.
    """
    if isinstance(source_bits, str):
        src_arr = np.array([1 if c == "1" else 0 for c in source_bits], dtype=int)
    else:
        src_arr = np.array(source_bits, dtype=int)

    original_length = len(src_arr)
    if original_length == 0:
        raise ValueError("Source bitstream must not be empty.")

    num_blocks = (original_length + n - 1) // n
    padding_count = num_blocks * n - original_length

    if padding_count > 0:
        padded_src = np.pad(src_arr, (0, padding_count), mode="constant", constant_values=0)
    else:
        padded_src = src_arr

    bch = get_bch_code(n, k, t)
    active_rng = rng if rng is not None else np.random.default_rng()

    helper_blocks: list[np.ndarray] = []
    for b_idx in range(num_blocks):
        src_blk = padded_src[b_idx * n : (b_idx + 1) * n]
        # Independent random k-bit message
        u = active_rng.integers(0, 2, size=k, dtype=int)
        c = np.array(bch.encode(u), dtype=int)
        # Helper data: H = A XOR C
        h = src_blk ^ c
        helper_blocks.append(h)

    return helper_blocks, original_length, padding_count


def reconstruct_receiver_bitstream(
    receiver_bits: Sequence[int] | str,
    helper_blocks: Sequence[np.ndarray],
    n: int,
    k: int,
    original_length: int,
    padding_count: int,
    t: int | None = None,
) -> tuple[np.ndarray, list[int]]:
    """Reconstruct source bitstream at receiver using helper data per PA.pdf Eqs (3.33)-(3.36).

    Receiver strictly operates on its own bits, public helper data H, and code parameters.
    No access to source bits or random messages is permitted.

    Args:
        receiver_bits: Receiver party bitstream (e.g. Bob's bits).
        helper_blocks: List of helper blocks H published by source.
        n: BCH codeword length.
        k: BCH message length.
        original_length: Original unpadded source bit length.
        padding_count: Number of zero-padding bits appended to final block.
        t: BCH error-correction capability (optional; derived if omitted).

    Returns:
        tuple: (recovered_unpadded, corrected_errors_per_block)
            where recovered_unpadded is a 1D numpy array of length original_length.
    """
    if isinstance(receiver_bits, str):
        rcv_arr = np.array([1 if c == "1" else 0 for c in receiver_bits], dtype=int)
    else:
        rcv_arr = np.array(receiver_bits, dtype=int)

    num_blocks = len(helper_blocks)
    expected_padded_len = num_blocks * n
    if len(rcv_arr) < original_length:
        raise ValueError(
            f"Receiver bitstream length {len(rcv_arr)} is less than original length {original_length}."
        )

    if padding_count > 0:
        padded_rcv = np.pad(rcv_arr[:original_length], (0, padding_count), mode="constant", constant_values=0)
    else:
        padded_rcv = rcv_arr[:expected_padded_len]

    bch = get_bch_code(n, k, t)
    recovered_blocks: list[np.ndarray] = []
    corrections_list: list[int] = []

    for b_idx in range(num_blocks):
        rcv_blk = padded_rcv[b_idx * n : (b_idx + 1) * n]
        h_blk = helper_blocks[b_idx]
        # Eq 3.33: C' = H XOR B = C XOR (A XOR B)
        c_prime = h_blk ^ rcv_blk

        try:
            c_hat, num_corr = bch.decode(c_prime, output="codeword", errors=True)
            num_corr_int = int(num_corr)
        except Exception:
            num_corr_int = -1
            c_hat = None

        corrections_list.append(num_corr_int)

        if num_corr_int == -1 or c_hat is None:
            # Decoder failed: uncorrectable error detected; retain receiver block as fallback
            recovered_blocks.append(rcv_blk.copy())
        else:
            # Eq 3.36: A_hat = H XOR C_hat
            c_hat_arr = np.array(c_hat, dtype=int)
            a_hat_blk = h_blk ^ c_hat_arr
            recovered_blocks.append(a_hat_blk)

    recovered_full = np.concatenate(recovered_blocks)
    recovered_unpadded = recovered_full[:original_length]
    return recovered_unpadded, corrections_list


@dataclass(frozen=True)
class BlockReconciliationDetail:
    """Ground-truth evaluation detail for a single reconciliation block."""

    block_index: int
    n: int
    actual_errors: int
    corrected_errors: int
    status: str  # 'success', 'detected_failure', 'miscorrected'


@dataclass
class PairReconciliationResult:
    """Complete reconciliation and key agreement evaluation container for a channel pair."""

    path_name: str
    pair_name: str
    source_name: str
    receiver_name: str
    n: int
    k: int
    t: int
    original_length: int
    num_blocks: int
    padding_count: int
    helper_data_bits: int
    source_unpadded: str
    receiver_raw_unpadded: str
    recovered_unpadded: str
    exact_recovery: bool
    pre_reconcile_kar: float
    post_reconcile_kar: float
    success_blocks: int
    detected_failure_blocks: int
    miscorrected_blocks: int
    block_details: list[BlockReconciliationDetail]
    is_legitimate: bool
    designed_d: int = 0
    interleaving: str = "OFF"

    @property
    def pre_reconcile_ber(self) -> float:
        """Pre-reconciliation Bit Error Rate (100 - KAR)."""
        return 100.0 - self.pre_reconcile_kar

    @property
    def post_reconcile_ber(self) -> float:
        """Post-reconciliation Bit Error Rate (100 - KAR)."""
        return 100.0 - self.post_reconcile_kar

    @property
    def block_success_rate(self) -> float:
        """Percentage of blocks successfully reconciled."""
        return (self.success_blocks / self.num_blocks * 100.0) if self.num_blocks > 0 else 0.0

    @property
    def helper_overhead_ratio(self) -> float:
        """Ratio of helper data bits to original payload bits."""
        return (self.helper_data_bits / self.original_length) if self.original_length > 0 else 0.0

    # Aliases for CLI and testing compatibility
    @property
    def path(self) -> str:
        return self.path_name

    @property
    def pair(self) -> str:
        return self.pair_name

    @property
    def pre_kar(self) -> float:
        return self.pre_reconcile_kar

    @property
    def post_kar(self) -> float:
        return self.post_reconcile_kar

    @property
    def exact_block_recovery(self) -> bool:
        return self.exact_recovery

    @property
    def successful_blocks(self) -> int:
        return self.success_blocks

    @property
    def detected_failures(self) -> int:
        return self.detected_failure_blocks

    @property
    def total_helper_data_bits(self) -> int:
        return self.helper_data_bits

    @property
    def helper_data_overhead_ratio(self) -> float:
        return self.helper_overhead_ratio


def evaluate_reconciliation_pair(
    source_bits: str,
    receiver_bits: str,
    helper_blocks: Sequence[np.ndarray],
    n: int,
    k: int,
    t: int,
    path_name: str,
    pair_name: str,
    source_name: str,
    receiver_name: str,
    is_legitimate: bool,
    padding_count: int,
    designed_d: int = 0,
    interleaving: str = "OFF",
) -> PairReconciliationResult:
    """Perform ground-truth evaluation of reconciliation and candidate-key extraction for a pair.

    Distinguishes decoder success, detected failure, and miscorrection by comparing
    reconstructed blocks against source blocks in the offline evaluator.

    Args:
        source_bits: Ground-truth source bitstream string.
        receiver_bits: Receiver party raw bitstream string.
        helper_blocks: Sequence of helper data blocks.
        n: BCH codeword length.
        k: BCH message length.
        t: BCH error-correction capability.
        path_name: Name of path ('quant_2bit', 'quant_4bit', 'prbs_2bit', 'prbs_4bit').
        pair_name: Pair name ('Alice–Bob', 'Alice–Eve1-Alice', 'Bob–Eve1-Bob').
        source_name: Name of source channel.
        receiver_name: Name of receiver channel.
        is_legitimate: True for Alice–Bob, False for eavesdropper pairs.
        padding_count: Zero-padding bits on final block.
        designed_d: Designed or actual minimum distance of the BCH code.
        interleaving: Interleaving configuration (strictly 'OFF').

    Returns:
        PairReconciliationResult: Complete populated evaluation container.
    """
    original_length = len(source_bits)
    eff_d = designed_d if designed_d > 0 else (2 * t + 1)
    recovered_arr, corrections_list = reconstruct_receiver_bitstream(
        receiver_bits=receiver_bits,
        helper_blocks=helper_blocks,
        n=n,
        k=k,
        original_length=original_length,
        padding_count=padding_count,
        t=t,
    )

    src_arr = np.array([1 if c == "1" else 0 for c in source_bits], dtype=int)
    rcv_arr = np.array([1 if c == "1" else 0 for c in receiver_bits[:original_length]], dtype=int)

    num_blocks = len(helper_blocks)
    padded_src = np.pad(src_arr, (0, padding_count), mode="constant", constant_values=0)
    padded_rcv = np.pad(rcv_arr, (0, padding_count), mode="constant", constant_values=0)

    # Reconstruct full padded recovered blocks for per-block analysis
    recovered_full = np.pad(recovered_arr, (0, padding_count), mode="constant", constant_values=0)

    block_details: list[BlockReconciliationDetail] = []
    n_succ = 0
    n_fail = 0
    n_misc = 0

    for b_idx in range(num_blocks):
        s_blk = padded_src[b_idx * n : (b_idx + 1) * n]
        r_blk = padded_rcv[b_idx * n : (b_idx + 1) * n]
        rec_blk = recovered_full[b_idx * n : (b_idx + 1) * n]
        actual_errs = int(np.sum(s_blk != r_blk))
        corr_errs = corrections_list[b_idx]

        if corr_errs == -1:
            status = "detected_failure"
            n_fail += 1
        elif np.array_equal(rec_blk, s_blk):
            status = "success"
            n_succ += 1
        else:
            status = "miscorrected"
            n_misc += 1

        block_details.append(
            BlockReconciliationDetail(
                block_index=b_idx,
                n=n,
                actual_errors=actual_errs,
                corrected_errors=corr_errs,
                status=status,
            )
        )

    exact_recovery = bool(np.array_equal(recovered_arr, src_arr))

    # Pre- and post-reconciliation KAR
    pre_mismatches = int(np.sum(src_arr != rcv_arr))
    post_mismatches = int(np.sum(src_arr != recovered_arr))

    pre_kar = ((original_length - pre_mismatches) / original_length) * 100.0
    post_kar = ((original_length - post_mismatches) / original_length) * 100.0

    recovered_str = "".join(str(b) for b in recovered_arr)

    return PairReconciliationResult(
        path_name=path_name,
        pair_name=pair_name,
        source_name=source_name,
        receiver_name=receiver_name,
        n=n,
        k=k,
        t=t,
        original_length=original_length,
        num_blocks=num_blocks,
        padding_count=padding_count,
        helper_data_bits=num_blocks * n,
        source_unpadded=source_bits,
        receiver_raw_unpadded=receiver_bits[:original_length],
        recovered_unpadded=recovered_str,
        exact_recovery=exact_recovery,
        pre_reconcile_kar=pre_kar,
        post_reconcile_kar=post_kar,
        success_blocks=n_succ,
        detected_failure_blocks=n_fail,
        miscorrected_blocks=n_misc,
        block_details=block_details,
        is_legitimate=is_legitimate,
        designed_d=designed_d,
        interleaving=interleaving,
    )


@dataclass
class MultiPathReconciliationResult:
    """Master container holding reconciliation results across all 4 paths and channel pairs."""

    config: ReconciliationConfig
    path_results: dict[str, dict[str, PairReconciliationResult]]
    figure_paths: tuple[Path, Path] | None = None

    @property
    def metrics(self) -> list[PairReconciliationResult]:
        """Return flattened list of PairReconciliationResult in canonical path/pair order."""
        res: list[PairReconciliationResult] = []
        for path_name in PATHS:
            if path_name in self.path_results:
                for pair_info in EVALUATION_PAIRS:
                    pair_name = pair_info[2]
                    if pair_name in self.path_results[path_name]:
                        res.append(self.path_results[path_name][pair_name])
        return res


def reconcile_all_paths(
    quant_result: ChannelQuantizationResult,
    prbs_result: MultiChannelPRBSResult,
    config: ReconciliationConfig | None = None,
) -> MultiPathReconciliationResult:
    """Execute information reconciliation across both supported 2-bit paths and all evaluation pairs.

    Paths:
        1. quant_2bit: 2-bit Gray quantized bitstreams (1,000 bits)
        2. prbs_2bit: PRBS expanded bitstreams from 2-bit seed (1,500 bits)

    Pairs per path:
        - Alice–Bob (legitimate, using Alice helper data)
        - Alice–Eve1-Alice (eavesdropper, using Alice helper data)
        - Bob–Eve1-Bob (eavesdropper, using Bob helper data)

    Args:
        quant_result: Completed ChannelQuantizationResult.
        prbs_result: Completed MultiChannelPRBSResult.
        config: ReconciliationConfig instance (uses calibrated defaults if None).

    Returns:
        MultiPathReconciliationResult: Master result container.
    """
    cfg = config if config is not None else ReconciliationConfig()
    rng = np.random.default_rng(cfg.random_seed)

    # Gather bitstreams for each supported 2-bit path
    path_bitstreams: dict[str, dict[str, str]] = {
        "quant_2bit": {
            "Alice": quant_result.bitstreams_2bit["Alice"],
            "Bob": quant_result.bitstreams_2bit["Bob"],
            "Eve1-Alice": quant_result.bitstreams_2bit["Eve1-Alice"],
            "Eve1-Bob": quant_result.bitstreams_2bit["Eve1-Bob"],
        },
        "prbs_2bit": {
            ch: prbs_result.channels[ch].bitstream_2bit for ch in prbs_result.channels
        },
    }

    path_results: dict[str, dict[str, PairReconciliationResult]] = {}

    for path_name in PATHS:
        n, k, t = cfg.get_code_for_path(path_name)
        bitstreams = path_bitstreams[path_name]

        d_val = 2 * t + 1

        # Generate Alice helper data (used for Bob and Eve1-Alice)
        alice_helpers, alice_orig_len, alice_pad = generate_helper_data(
            source_bits=bitstreams["Alice"],
            n=n,
            k=k,
            t=t,
            rng=rng,
        )

        # Generate Bob helper data (used for Eve1-Bob)
        bob_helpers, bob_orig_len, bob_pad = generate_helper_data(
            source_bits=bitstreams["Bob"],
            n=n,
            k=k,
            t=t,
            rng=rng,
        )

        # 1. Alice -> Bob
        res_ab = evaluate_reconciliation_pair(
            source_bits=bitstreams["Alice"],
            receiver_bits=bitstreams["Bob"],
            helper_blocks=alice_helpers,
            n=n,
            k=k,
            t=t,
            path_name=path_name,
            pair_name="Alice–Bob",
            source_name="Alice",
            receiver_name="Bob",
            is_legitimate=True,
            padding_count=alice_pad,
            designed_d=d_val,
            interleaving=cfg.interleaving,
        )

        # 2. Alice -> Eve1-Alice
        res_ea = evaluate_reconciliation_pair(
            source_bits=bitstreams["Alice"],
            receiver_bits=bitstreams["Eve1-Alice"],
            helper_blocks=alice_helpers,
            n=n,
            k=k,
            t=t,
            path_name=path_name,
            pair_name="Alice–Eve1-Alice",
            source_name="Alice",
            receiver_name="Eve1-Alice",
            is_legitimate=False,
            padding_count=alice_pad,
            designed_d=d_val,
            interleaving=cfg.interleaving,
        )

        # 3. Bob -> Eve1-Bob
        res_eb = evaluate_reconciliation_pair(
            source_bits=bitstreams["Bob"],
            receiver_bits=bitstreams["Eve1-Bob"],
            helper_blocks=bob_helpers,
            n=n,
            k=k,
            t=t,
            path_name=path_name,
            pair_name="Bob–Eve1-Bob",
            source_name="Bob",
            receiver_name="Eve1-Bob",
            is_legitimate=False,
            padding_count=bob_pad,
            designed_d=d_val,
            interleaving=cfg.interleaving,
        )

        path_results[path_name] = {
            "Alice–Bob": res_ab,
            "Alice–Eve1-Alice": res_ea,
            "Bob–Eve1-Bob": res_eb,
        }

    return MultiPathReconciliationResult(
        config=cfg,
        path_results=path_results,
    )


def export_reconciliation_metrics_csv(
    reconcile_result: MultiPathReconciliationResult,
    output_path: str | Path,
) -> Path:
    """Export reconciliation KAR and key-match metrics to CSV."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "path",
        "pair",
        "source",
        "receiver",
        "is_legitimate",
        "n",
        "k",
        "t",
        "designed_d",
        "interleaving",
        "code_rate",
        "original_length",
        "num_blocks",
        "padding_bits",
        "helper_data_bits",
        "helper_overhead_ratio",
        "pre_reconcile_kar_percent",
        "post_reconcile_kar_percent",
        "kar_delta_pp",
        "exact_recovery",
        "success_blocks",
        "detected_failure_blocks",
        "miscorrected_blocks",
        "block_success_rate_percent",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for path_name, pairs in reconcile_result.path_results.items():
            for pair_name, res in pairs.items():
                writer.writerow(
                    {
                        "path": path_name,
                        "pair": pair_name,
                        "source": res.source_name,
                        "receiver": res.receiver_name,
                        "is_legitimate": res.is_legitimate,
                        "n": res.n,
                        "k": res.k,
                        "t": res.t,
                        "designed_d": res.designed_d,
                        "interleaving": res.interleaving,
                        "code_rate": f"{res.k / res.n:.6f}",
                        "original_length": res.original_length,
                        "num_blocks": res.num_blocks,
                        "padding_bits": res.padding_count,
                        "helper_data_bits": res.helper_data_bits,
                        "helper_overhead_ratio": f"{res.helper_overhead_ratio:.4f}",
                        "pre_reconcile_kar_percent": f"{res.pre_reconcile_kar:.4f}",
                        "post_reconcile_kar_percent": f"{res.post_reconcile_kar:.4f}",
                        "kar_delta_pp": f"{res.post_reconcile_kar - res.pre_reconcile_kar:+.4f}",
                        "exact_recovery": res.exact_recovery,
                        "success_blocks": res.success_blocks,
                        "detected_failure_blocks": res.detected_failure_blocks,
                        "miscorrected_blocks": res.miscorrected_blocks,
                        "block_success_rate_percent": f"{res.block_success_rate:.2f}",
                    }
                )
    return out


def export_reconciliation_blocks_csv(
    reconcile_result: MultiPathReconciliationResult,
    output_path: str | Path,
) -> Path:
    """Export per-block reconciliation details to CSV."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "path",
        "pair",
        "block_index",
        "n",
        "k",
        "t",
        "designed_d",
        "interleaving",
        "actual_errors",
        "corrected_errors",
        "status",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for path_name, pairs in reconcile_result.path_results.items():
            for pair_name, res in pairs.items():
                for blk in res.block_details:
                    writer.writerow(
                        {
                            "path": path_name,
                            "pair": pair_name,
                            "block_index": blk.block_index,
                            "n": blk.n,
                            "k": res.k,
                            "t": res.t,
                            "designed_d": res.designed_d,
                            "interleaving": res.interleaving,
                            "actual_errors": blk.actual_errors,
                            "corrected_errors": blk.corrected_errors,
                            "status": blk.status,
                        }
                    )
    return out


def export_reconciliation_config_json(
    reconcile_result: MultiPathReconciliationResult,
    output_path: str | Path,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Export reconciliation metadata and configuration to JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = reconcile_result.config.to_metadata_dict()
    if extra_metadata is not None:
        meta["execution_context"] = extra_metadata

    summary: dict[str, Any] = {}
    for p_name, pairs in reconcile_result.path_results.items():
        summary[p_name] = {}
        for pair_name, res in pairs.items():
            summary[p_name][pair_name] = {
                "n": res.n,
                "k": res.k,
                "t": res.t,
                "designed_d": res.designed_d,
                "interleaving": res.interleaving,
                "original_length": res.original_length,
                "num_blocks": res.num_blocks,
                "padding_bits": res.padding_count,
                "exact_recovery": res.exact_recovery,
                "pre_kar": round(res.pre_reconcile_kar, 4),
                "post_kar": round(res.post_reconcile_kar, 4),
                "success_blocks": res.success_blocks,
                "failed_blocks": res.detected_failure_blocks,
                "miscorrected_blocks": res.miscorrected_blocks,
            }
    meta["reconciliation_summary"] = summary

    with open(out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out


def export_reconciliation_workbook_xlsx(
    reconcile_result: MultiPathReconciliationResult,
    output_path: str | Path,
) -> Path:
    """Export companion multi-sheet Excel workbook (.xlsx).

    Preserves text cell format (@) for bitstrings,
    chunks streams > 32,767 characters, and explicitly labels dummy research artifacts.

    Sheets:
        1. Reconciliation Metrics
        2. Block Details
        3. Recovered Bitstreams
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    mono_font = Font(name="Consolas", size=9)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    notice_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    notice_font = Font(name="Calibri", size=10, italic=True, bold=True, color="7F6000")

    # Sheet 1: Reconciliation Metrics
    ws1 = wb.active
    ws1.title = "Reconciliation Metrics"
    headers1 = [
        "Path",
        "Pair",
        "Legitimate",
        "BCH Code (n,k,t)",
        "Designed d",
        "Interleaving",
        "Orig Bits",
        "Blocks",
        "Pad Bits",
        "Pre-KAR (%)",
        "Post-KAR (%)",
        "Delta (pp)",
        "Exact Recovery",
        "Success Blks",
        "Failed Blks",
        "Miscorr Blks",
    ]
    ws1.append(headers1)
    for col_idx in range(1, len(headers1) + 1):
        cell = ws1.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r_idx = 2
    for path_name, pairs in reconcile_result.path_results.items():
        for pair_name, res in pairs.items():
            delta = res.post_reconcile_kar - res.pre_reconcile_kar
            row_data = [
                path_name,
                pair_name,
                "YES" if res.is_legitimate else "NO",
                f"BCH({res.n},{res.k},{res.t})",
                res.designed_d,
                res.interleaving,
                res.original_length,
                res.num_blocks,
                res.padding_count,
                round(res.pre_reconcile_kar, 4),
                round(res.post_reconcile_kar, 4),
                round(delta, 4),
                "TRUE" if res.exact_recovery else "FALSE",
                res.success_blocks,
                res.detected_failure_blocks,
                res.miscorrected_blocks,
            ]
            ws1.append(row_data)
            for c_idx in range(1, len(row_data) + 1):
                c = ws1.cell(row=r_idx, column=c_idx)
                c.font = data_font
                c.alignment = center_align
            r_idx += 1

    # Sheet 2: Block Details
    ws2 = wb.create_sheet(title="Block Details")
    headers2 = ["Path", "Pair", "Block Index", "n", "k", "t", "Designed d", "Interleaving", "Actual Errors", "Corrected Errors", "Status"]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r2_idx = 2
    for path_name, pairs in reconcile_result.path_results.items():
        for pair_name, res in pairs.items():
            for blk in res.block_details:
                ws2.append(
                    [
                        path_name,
                        pair_name,
                        blk.block_index,
                        blk.n,
                        res.k,
                        res.t,
                        res.designed_d,
                        res.interleaving,
                        blk.actual_errors,
                        blk.corrected_errors,
                        blk.status,
                    ]
                )
                for c_idx in range(1, len(headers2) + 1):
                    c = ws2.cell(row=r2_idx, column=c_idx)
                    c.font = data_font
                    c.alignment = center_align
                r2_idx += 1

    # Sheet 3: Recovered Bitstreams (with chunking for > 32k)
    ws3 = wb.create_sheet(title="Recovered Bitstreams")
    headers3 = ["Path", "Pair", "Stream Type", "Part", "Total Parts", "Bit Count", "Bitstream"]
    ws3.append(headers3)
    for col_idx in range(1, len(headers3) + 1):
        cell = ws3.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r3_idx = 2
    for path_name, pairs in reconcile_result.path_results.items():
        for pair_name, res in pairs.items():
            for stream_type, s_data in [
                ("Source Unpadded", res.source_unpadded),
                ("Receiver Raw Unpadded", res.receiver_raw_unpadded),
                ("Recovered Unpadded", res.recovered_unpadded),
            ]:
                # Split stream into chunks if exceeds Excel max cell characters
                chunks = (
                    [s_data[i : i + EXCEL_MAX_CELL_CHARS] for i in range(0, len(s_data), EXCEL_MAX_CELL_CHARS)]
                    if len(s_data) > EXCEL_MAX_CELL_CHARS
                    else [s_data]
                )
                tot_parts = len(chunks)
                for part_idx, chunk in enumerate(chunks, 1):
                    ws3.append(
                        [
                            path_name,
                            pair_name,
                            stream_type,
                            part_idx,
                            tot_parts,
                            len(chunk),
                            chunk,
                        ]
                    )
                    # Text format for bitstream string
                    cell_stream = ws3.cell(row=r3_idx, column=7)
                    cell_stream.data_type = "s"
                    cell_stream.number_format = "@"
                    cell_stream.font = mono_font
                    for c_idx in range(1, 7):
                        ws3.cell(row=r3_idx, column=c_idx).font = data_font
                        ws3.cell(row=r3_idx, column=c_idx).alignment = center_align
                    r3_idx += 1

    # Adjust column widths across all sheets
    for ws in [ws1, ws2, ws3]:
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    wb.save(out)
    return out
