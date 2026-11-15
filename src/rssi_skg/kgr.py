"""Key Generation Rate (KGR) measurement and evaluation module.

Governing Specification:
    PA.pdf Section 3.2.8.b, Equation (3.63), page 35:
        KGR = N_bit / T  (bits per second / bps)
        where N_bit is the number of secret key bits accepted by NIST statistical tests,
        and T is the actual duration of key formation in seconds.

Methodological Implementation Rules:
    1. Acceptance Rule (Eq 3.63):
       For each path, Alice's derived final key is counted once:
           - N_accepted_bits = 256 if Alice's final key passes all three NIST tests
             (Frequency Monobit, Runs, Approximate Entropy) and all three were applicable.
           - N_accepted_bits = 0 if any NIST test fails or is not applicable.
       Accepted KGR is then computed as:
           KGR_accepted = N_accepted_bits / T (bps)
       Raw KGR is also reported for throughput comparison:
           KGR_raw = 256 / T (bps)

    2. Single Accounting of Generated Bits:
       Alice is the legitimate key generator. Alice–Bob agreement is reported separately
       (exact key match and post-PA KAR = 100%), but Bob's matching key is NOT counted
       as additional generated bits (no duplicate bit inflation).

    3. Monotonic High-Resolution Timing Policy:
       - Elapsed time T is measured using a monotonic high-resolution timer
         (default: time.perf_counter()).
       - Timed Scope: Each path is timed strictly and independently from the start of
         Modified Sage–Husa Adaptive Kalman Filtering (MSHKF) through bit-level SHA-256
         Privacy Amplification (including Galois XOR-LFSR PRBS expansion ONLY on prbs_2bit).
       - Excluded from Timer: Raw dataset reading/parsing, plotting/rendering, CSV/JSON/XLSX
         artifact exporting, and post-hoc NIST statistical testing.
       - Timing Boundaries:
           * Start Boundary: Immediately before scalar MSHKF filtering on raw RSSI samples.
           * End Boundary: Immediately after completing bit-level SHA-256 hash compression.
       - Never inferred from sample count or invented channel-probing duration.

    4. Cold-Start & BCH Cache Warm-up Policy:
       To eliminate timing-order bias between paths (where whichever path runs first incurs
       a multi-second Numba JIT compilation and Galois field table construction penalty in
       galois.BCH.decode), a standardized pre-warm step is executed before timing:
           bch = get_bch_code(*DEFAULT_BCH_CODE)
           dummy_c = bch.encode(np.zeros(bch.k, dtype=int))
           bch.decode(dummy_c)
       Both paths then execute under identical, warm-cache conditions.

    5. Controlled Clock for Deterministic Testing:
       The pipeline functions accept an optional `timer` callable (defaulting to time.perf_counter),
       enabling unit tests to inject controlled mock clocks.

    6. Research & Scientific Scope:
       All results are strictly labeled "dummy-data software validation".
       Repeated timing runs are not independent randomness samples.
       Does not claim physical entropy, cryptographic secrecy, or measured end-to-end KGR
       over an empirical wireless propagation channel.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any, Callable, Sequence

import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from rssi_skg.filter import FilterConfig, filter_rssi_channels
from rssi_skg.nist import (
    ChannelRandomnessResult,
    KeyRandomnessResult,
    MultiPathNISTResult,
    NISTConfig,
    evaluate_key_randomness,
)
from rssi_skg.prbs import PRBSConfig, expand_channels_prbs
from rssi_skg.privacy_amplification import (
    ChannelPrivacyAmplificationResult,
    ChunkKeyResult,
    PairPrivacyAmplificationResult,
    PrivacyAmplificationConfig,
    SCIENTIFIC_DISCLAIMER,
    evaluate_chunk_pair_keys,
    segment_bitstream,
    sha256_bitstream,
)
from rssi_skg.quantization import QuantizationConfig, quantize_channels
from rssi_skg.reconciliation import (
    DEFAULT_BCH_CODE,
    DEFAULT_BCH_CODE_2BIT,
    DEFAULT_BCH_CODE_4BIT,
    PairReconciliationResult,
    ReconciliationConfig,
    evaluate_reconciliation_pair,
    generate_helper_data,
    get_bch_code,
)

# Downstream Evaluation Status:
# Fully integrated across all 4 paths (quant_2bit, quant_4bit, prbs_2bit, prbs_4bit)
# with dynamic 100-bit chunking and dual BCH cache pre-warming.
KGR_PATHS: tuple[str, ...] = ("quant_2bit", "quant_4bit", "prbs_2bit", "prbs_4bit")
KGR_DOWNSTREAM_STATUS: str = "COMPLETED"

RESEARCH_DISCLAIMER_KGR: str = (
    "Dummy-data software validation only. KGR measures pure software processing throughput "
    "(bits per elapsed second) from scalar MSHKF filtering through SHA-256 privacy amplification "
    "on synthetic indoor dummy data with a pre-warmed BCH JIT cache. It does NOT represent "
    "empirical physical channel probing rate, hardware over-the-air throughput, or cryptographic secrecy."
)

TIMER_START_BOUNDARY: str = "Immediate entry to legitimate Alice–Bob filter_rssi_channels (scalar MSHKF filtering)"
TIMER_END_BOUNDARY: str = "Completion of sha256_bitstream for legitimate Alice and Bob chunk keys"
BCH_CACHE_POLICY_DESC: str = (
    "Pre-warmed galois.BCH instances and JIT decode kernels for both 2-bit BCH(511, 1, 198) "
    "and 4-bit BCH(255, 9, 62) before timing to eliminate multi-second Numba compilation order bias."
)


def warm_up_bch_cache(
    codes: Sequence[tuple[int, int, int]] | tuple[int, int, int] = (
        DEFAULT_BCH_CODE_2BIT,
        DEFAULT_BCH_CODE_4BIT,
    ),
) -> None:
    """Pre-warm BCH code construction and Numba JIT decode/encode kernels.

    Galois compiles JIT routines on the very first encode/decode call (taking 2–5 seconds).
    Pre-warming both 2-bit and 4-bit codes ensures no path suffers an asymmetric timing bias.

    Args:
        codes: Sequence of (n, k, t) code tuples or a single (n, k, t) tuple.
    """
    if isinstance(codes, tuple) and len(codes) == 3 and isinstance(codes[0], int):
        target_codes = [codes]
    else:
        target_codes = list(codes)

    for code in target_codes:
        n, k, t = code
        bch = get_bch_code(n, k, t)
        dummy_msg = np.zeros(k, dtype=int)
        dummy_codeword = bch.encode(dummy_msg)
        bch.decode(dummy_codeword)


@dataclass(frozen=True)
class KGRConfig:
    """Configuration container for Key Generation Rate measurement."""

    paths: tuple[str, ...] = KGR_PATHS
    key_length_bits: int = 256
    segment_size_bits: int = 100
    pre_warm_bch: bool = True
    disclaimer: str = RESEARCH_DISCLAIMER_KGR

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert configuration to metadata dictionary."""
        return {
            "supported_paths": list(self.paths),
            "key_length_bits": self.key_length_bits,
            "segment_size_bits": self.segment_size_bits,
            "pre_warm_bch": self.pre_warm_bch,
            "governing_equation": "PA.pdf Section 3.2.8.b, Equation (3.63): KGR = N_bit / T",
            "timer_boundaries": {
                "start": TIMER_START_BOUNDARY,
                "end": TIMER_END_BOUNDARY,
                "excluded": "Workbook loading, plotting/rendering, CSV/JSON/XLSX exports, NIST evaluation, Eve channels evaluation",
            },
            "bch_cache_policy": BCH_CACHE_POLICY_DESC,
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class PathKGRResult:
    """Container holding software duration and KGR evaluation for a single path."""

    path_name: str
    raw_generated_bits: int
    nist_overall_passed: bool
    accepted_bits: int
    duration_seconds: float
    accepted_kgr_bps: float
    raw_kgr_bps: float
    alice_bob_exact_match: bool
    alice_bob_kar: float
    channel_keys: dict[str, ChannelPrivacyAmplificationResult]
    pair_results: dict[str, PairPrivacyAmplificationResult]
    total_chunks: int = 0
    accepted_chunks: int = 0
    alice_chunk_evaluations: list[KeyRandomnessResult] = field(default_factory=list)
    timer_start_boundary: str = TIMER_START_BOUNDARY
    timer_end_boundary: str = TIMER_END_BOUNDARY
    bch_cache_policy: str = BCH_CACHE_POLICY_DESC
    label: str = "dummy-data software validation"

    @property
    def duration_ms(self) -> float:
        """Elapsed software duration in milliseconds."""
        return self.duration_seconds * 1000.0


@dataclass
class MultiPathKGRResult:
    """Master container holding KGR results across all evaluated paths."""

    config: KGRConfig
    path_results: dict[str, PathKGRResult]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def paths(self) -> dict[str, PathKGRResult]:
        """Alias for path_results."""
        return self.path_results

    @property
    def metrics(self) -> list[PathKGRResult]:
        """Return list of path results in canonical order."""
        return [self.path_results[p] for p in self.config.paths if p in self.path_results]


# ==============================================================================
# Single-Path Timed Execution
# ==============================================================================


def execute_timed_path_pipeline(
    path_name: str,
    raw_data: dict[str, list[float]],
    nist_alice_eval: ChannelRandomnessResult | KeyRandomnessResult | Sequence[KeyRandomnessResult] | None = None,
    filter_config: FilterConfig | None = None,
    quant_config: QuantizationConfig | None = None,
    prbs_config: PRBSConfig | None = None,
    recon_config: ReconciliationConfig | None = None,
    pa_config: PrivacyAmplificationConfig | None = None,
    nist_config: NISTConfig | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> PathKGRResult:
    """Execute and time a single path from filtering through SHA-256 Privacy Amplification.

    Args:
        path_name: 'quant_2bit', 'quant_4bit', 'prbs_2bit', or 'prbs_4bit'.
        raw_data: Raw RSSI samples dictionary (4 channels).
        nist_alice_eval: Pre-computed NIST evaluation on Alice's key(s) (computed if None).
        filter_config: FilterConfig instance.
        quant_config: QuantizationConfig instance.
        prbs_config: PRBSConfig instance (only utilized if path is PRBS expanded).
        recon_config: ReconciliationConfig instance.
        pa_config: PrivacyAmplificationConfig instance.
        nist_config: NISTConfig instance.
        timer: High-resolution monotonic timer callable (default: time.perf_counter).

    Returns:
        PathKGRResult: Complete timed metrics, keys, and KGR statistics.
    """
    if path_name not in KGR_PATHS:
        raise ValueError(f"Unsupported path '{path_name}'. Must be one of {KGR_PATHS}.")

    f_cfg = filter_config if filter_config is not None else FilterConfig()
    q_cfg = quant_config if quant_config is not None else QuantizationConfig()
    p_cfg = prbs_config if prbs_config is not None else PRBSConfig()
    r_cfg = recon_config if recon_config is not None else ReconciliationConfig()
    pa_cfg = pa_config if pa_config is not None else PrivacyAmplificationConfig()
    seg_size = pa_cfg.segment_size_bits

    n, k, t = r_cfg.get_code_for_path(path_name)
    d_val = 2 * t + 1

    rng = np.random.default_rng(r_cfg.random_seed)

    # --------------------------------------------------------------------------
    # TIMER START: Immediately before legitimate Alice & Bob MSHKF filtering
    # --------------------------------------------------------------------------
    t_start = timer()

    # 1. Scalar MSHKF Filtering (Legitimate Alice & Bob only)
    legit_raw = {"Alice": raw_data["Alice"], "Bob": raw_data["Bob"]}
    f_legit = filter_rssi_channels(legit_raw, f_cfg)

    # 2. Modified ADQ Quantization (Legitimate Alice & Bob only)
    q_legit = quantize_channels(f_legit, q_cfg)

    # 3. Expansion (PRBS only on prbs_2bit and prbs_4bit paths, for Legitimate Alice & Bob)
    if path_name == "quant_2bit":
        legit_bitstreams = {
            "Alice": q_legit.bitstreams_2bit["Alice"],
            "Bob": q_legit.bitstreams_2bit["Bob"],
        }
    elif path_name == "quant_4bit":
        legit_bitstreams = {
            "Alice": q_legit.bitstreams_4bit["Alice"],
            "Bob": q_legit.bitstreams_4bit["Bob"],
        }
    elif path_name == "prbs_2bit":
        p_legit = expand_channels_prbs(q_legit, p_cfg)
        legit_bitstreams = {
            "Alice": p_legit.channels["Alice"].bitstream_2bit,
            "Bob": p_legit.channels["Bob"].bitstream_2bit,
        }
    elif path_name == "prbs_4bit":
        p_legit = expand_channels_prbs(q_legit, p_cfg)
        legit_bitstreams = {
            "Alice": p_legit.channels["Alice"].bitstream_4bit,
            "Bob": p_legit.channels["Bob"].bitstream_4bit,
        }
    else:
        raise ValueError(f"Unknown path: {path_name}")

    # 4. BCH Codeword Helper Data Reconciliation (Alice -> Bob legitimate path)
    alice_helpers, alice_orig, alice_pad = generate_helper_data(
        source_bits=legit_bitstreams["Alice"], n=n, k=k, t=t, rng=rng
    )

    res_ab = evaluate_reconciliation_pair(
        source_bits=legit_bitstreams["Alice"],
        receiver_bits=legit_bitstreams["Bob"],
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
        interleaving=r_cfg.interleaving,
    )

    # 5. Bit-level SHA-256 Privacy Amplification (Legitimate Alice & Bob only, 100-bit chunks)
    alice_segments = segment_bitstream(res_ab.source_unpadded, segment_size=seg_size)
    bob_segments = segment_bitstream(res_ab.recovered_unpadded, segment_size=seg_size)

    alice_keys: list[ChunkKeyResult] = []
    for idx, seg in enumerate(alice_segments):
        k_bin, k_hex = sha256_bitstream(seg)
        alice_keys.append(
            ChunkKeyResult(
                chunk_index=idx,
                input_segment_bits=seg,
                key_bin=k_bin,
                key_hex=k_hex,
            )
        )

    bob_keys: list[ChunkKeyResult] = []
    for idx, seg in enumerate(bob_segments):
        k_bin, k_hex = sha256_bitstream(seg)
        bob_keys.append(
            ChunkKeyResult(
                chunk_index=idx,
                input_segment_bits=seg,
                key_bin=k_bin,
                key_hex=k_hex,
            )
        )

    # --------------------------------------------------------------------------
    # TIMER END: Immediately after Legitimate Alice & Bob Privacy Amplification
    # --------------------------------------------------------------------------
    t_end = timer()

    duration = max(1e-9, t_end - t_start)

    # --------------------------------------------------------------------------
    # POST-TIMING: Auxiliary / Eavesdropper Channel Evaluation (Excluded from KGR Timer)
    # --------------------------------------------------------------------------
    pair_ab = evaluate_chunk_pair_keys(
        path_name=path_name,
        pair_name="Alice–Bob",
        source_name="Alice",
        receiver_name="Bob",
        is_legitimate=True,
        pre_kar=res_ab.post_reconcile_kar,
        source_chunk_keys=alice_keys,
        receiver_chunk_keys=bob_keys,
        chunk_size_bits=seg_size,
    )

    channel_keys: dict[str, ChannelPrivacyAmplificationResult] = {
        "Alice": ChannelPrivacyAmplificationResult(
            path_name=path_name,
            channel_name="Alice",
            channel_role="Legitimate Source (Reference Key)",
            input_bit_length=len(res_ab.source_unpadded),
            num_chunks=len(alice_keys),
            chunk_size_bits=seg_size,
            chunk_keys=alice_keys,
        ),
        "Bob": ChannelPrivacyAmplificationResult(
            path_name=path_name,
            channel_name="Bob",
            channel_role="Legitimate Receiver (Reconciled to Alice)",
            input_bit_length=len(res_ab.recovered_unpadded),
            num_chunks=len(bob_keys),
            chunk_size_bits=seg_size,
            chunk_keys=bob_keys,
        ),
    }

    pair_results: dict[str, PairPrivacyAmplificationResult] = {
        "Alice–Bob": pair_ab,
    }

    # Process Eve channels if present in raw_data
    if "Eve1-Alice" in raw_data and "Eve1-Bob" in raw_data:
        eve_raw = {ch: raw_data[ch] for ch in ["Eve1-Alice", "Eve1-Bob"]}
        f_eve = filter_rssi_channels(eve_raw, f_cfg)
        q_eve = quantize_channels(f_eve, q_cfg)
        if path_name == "quant_2bit":
            eve_bitstreams = {
                "Eve1-Alice": q_eve.bitstreams_2bit["Eve1-Alice"],
                "Eve1-Bob": q_eve.bitstreams_2bit["Eve1-Bob"],
            }
        elif path_name == "quant_4bit":
            eve_bitstreams = {
                "Eve1-Alice": q_eve.bitstreams_4bit["Eve1-Alice"],
                "Eve1-Bob": q_eve.bitstreams_4bit["Eve1-Bob"],
            }
        elif path_name == "prbs_2bit":
            p_eve = expand_channels_prbs(q_eve, p_cfg)
            eve_bitstreams = {
                "Eve1-Alice": p_eve.channels["Eve1-Alice"].bitstream_2bit,
                "Eve1-Bob": p_eve.channels["Eve1-Bob"].bitstream_2bit,
            }
        elif path_name == "prbs_4bit":
            p_eve = expand_channels_prbs(q_eve, p_cfg)
            eve_bitstreams = {
                "Eve1-Alice": p_eve.channels["Eve1-Alice"].bitstream_4bit,
                "Eve1-Bob": p_eve.channels["Eve1-Bob"].bitstream_4bit,
            }
        else:
            eve_bitstreams = {}

        res_ea = evaluate_reconciliation_pair(
            source_bits=legit_bitstreams["Alice"],
            receiver_bits=eve_bitstreams["Eve1-Alice"],
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
            interleaving=r_cfg.interleaving,
        )

        bob_helpers, _, bob_pad = generate_helper_data(
            source_bits=legit_bitstreams["Bob"], n=n, k=k, t=t, rng=rng
        )
        res_eb = evaluate_reconciliation_pair(
            source_bits=legit_bitstreams["Bob"],
            receiver_bits=eve_bitstreams["Eve1-Bob"],
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
            interleaving=r_cfg.interleaving,
        )

        ea_segments = segment_bitstream(res_ea.recovered_unpadded, segment_size=seg_size)
        eb_segments = segment_bitstream(res_eb.recovered_unpadded, segment_size=seg_size)

        ea_keys: list[ChunkKeyResult] = []
        for idx, seg in enumerate(ea_segments):
            k_bin, k_hex = sha256_bitstream(seg)
            ea_keys.append(
                ChunkKeyResult(
                    chunk_index=idx,
                    input_segment_bits=seg,
                    key_bin=k_bin,
                    key_hex=k_hex,
                )
            )

        eb_keys: list[ChunkKeyResult] = []
        for idx, seg in enumerate(eb_segments):
            k_bin, k_hex = sha256_bitstream(seg)
            eb_keys.append(
                ChunkKeyResult(
                    chunk_index=idx,
                    input_segment_bits=seg,
                    key_bin=k_bin,
                    key_hex=k_hex,
                )
            )

        channel_keys["Eve1-Alice"] = ChannelPrivacyAmplificationResult(
            path_name=path_name,
            channel_name="Eve1-Alice",
            channel_role="Passive Eavesdropper (Overhearing Alice)",
            input_bit_length=len(res_ea.recovered_unpadded),
            num_chunks=len(ea_keys),
            chunk_size_bits=seg_size,
            chunk_keys=ea_keys,
        )
        channel_keys["Eve1-Bob"] = ChannelPrivacyAmplificationResult(
            path_name=path_name,
            channel_name="Eve1-Bob",
            channel_role="Passive Eavesdropper (Overhearing Bob)",
            input_bit_length=len(res_eb.recovered_unpadded),
            num_chunks=len(eb_keys),
            chunk_size_bits=seg_size,
            chunk_keys=eb_keys,
        )

        pair_ea = evaluate_chunk_pair_keys(
            path_name=path_name,
            pair_name="Alice–Eve1-Alice",
            source_name="Alice",
            receiver_name="Eve1-Alice",
            is_legitimate=False,
            pre_kar=res_ea.post_reconcile_kar,
            source_chunk_keys=alice_keys,
            receiver_chunk_keys=ea_keys,
            chunk_size_bits=seg_size,
        )
        pair_eb = evaluate_chunk_pair_keys(
            path_name=path_name,
            pair_name="Bob–Eve1-Bob",
            source_name="Bob",
            receiver_name="Eve1-Bob",
            is_legitimate=False,
            pre_kar=res_eb.post_reconcile_kar,
            source_chunk_keys=bob_keys,
            receiver_chunk_keys=eb_keys,
            chunk_size_bits=seg_size,
        )
        pair_results["Alice–Eve1-Alice"] = pair_ea
        pair_results["Bob–Eve1-Bob"] = pair_eb

    # Evaluate NIST Randomness on Alice's keys (excluded from timer)
    alice_evals: list[KeyRandomnessResult] = []
    if nist_alice_eval is not None:
        if hasattr(nist_alice_eval, "chunks"):
            alice_evals = list(nist_alice_eval.chunks)
        elif isinstance(nist_alice_eval, (list, tuple)):
            alice_evals = list(nist_alice_eval)
        else:
            alice_evals = [nist_alice_eval]
    else:
        n_cfg = nist_config if nist_config is not None else NISTConfig()
        for ck in alice_keys:
            eval_res = evaluate_key_randomness(
                bitstream=ck.key_bin,
                path_name=path_name,
                channel_name="Alice",
                channel_role="Legitimate Source (Reference Key)",
                key_hex=ck.key_hex,
                config=n_cfg,
                chunk_index=ck.chunk_index,
                pair_name="Alice–Bob",
            )
            alice_evals.append(eval_res)

    total_chunks = len(alice_evals)
    accepted_chunks = sum(1 for e in alice_evals if e.overall_accepted)
    raw_bits = 256 * total_chunks
    accepted_bits = 256 * accepted_chunks
    nist_overall_passed = bool(accepted_chunks == total_chunks and total_chunks > 0)
    accepted_kgr = accepted_bits / duration
    raw_kgr = raw_bits / duration

    return PathKGRResult(
        path_name=path_name,
        raw_generated_bits=raw_bits,
        nist_overall_passed=nist_overall_passed,
        accepted_bits=accepted_bits,
        duration_seconds=duration,
        accepted_kgr_bps=accepted_kgr,
        raw_kgr_bps=raw_kgr,
        alice_bob_exact_match=pair_ab.exact_key_match,
        alice_bob_kar=pair_ab.post_pa_kar,
        channel_keys=channel_keys,
        pair_results=pair_results,
        total_chunks=total_chunks,
        accepted_chunks=accepted_chunks,
        alice_chunk_evaluations=alice_evals,
    )


def measure_multipath_kgr(
    raw_data: dict[str, list[float]],
    nist_result: MultiPathNISTResult | None = None,
    filter_config: FilterConfig | None = None,
    quant_config: QuantizationConfig | None = None,
    prbs_config: PRBSConfig | None = None,
    recon_config: ReconciliationConfig | None = None,
    pa_config: PrivacyAmplificationConfig | None = None,
    nist_config: NISTConfig | None = None,
    config: KGRConfig | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> MultiPathKGRResult:
    """Measure software execution time and evaluate KGR across both paths independently.

    Pre-warms the BCH code cache to eliminate timing-order bias before beginning measurements.

    Args:
        raw_data: Raw RSSI samples dictionary.
        nist_result: Completed MultiPathNISTResult (used to check Alice acceptance).
        filter_config: FilterConfig instance.
        quant_config: QuantizationConfig instance.
        prbs_config: PRBSConfig instance.
        recon_config: ReconciliationConfig instance.
        pa_config: PrivacyAmplificationConfig instance.
        nist_config: NISTConfig instance.
        config: KGRConfig instance.
        timer: Monotonic high-resolution timer callable (default: time.perf_counter).

    Returns:
        MultiPathKGRResult: Master container holding per-path results.
    """
    cfg = config if config is not None else KGRConfig()

    # Pre-warm BCH cache to eliminate JIT compilation timing-order bias
    if cfg.pre_warm_bch:
        warm_up_bch_cache((DEFAULT_BCH_CODE_2BIT, DEFAULT_BCH_CODE_4BIT))

    path_results: dict[str, PathKGRResult] = {}

    for path_name in cfg.paths:
        alice_eval: Any = None
        if nist_result is not None:
            if path_name in nist_result.paths and "Alice" in nist_result.paths[path_name]:
                alice_eval = nist_result.paths[path_name]["Alice"]
            elif (
                path_name in nist_result.channel_evaluations
                and "Alice" in nist_result.channel_evaluations[path_name]
            ):
                alice_eval = nist_result.channel_evaluations[path_name]["Alice"]

        res = execute_timed_path_pipeline(
            path_name=path_name,
            raw_data=raw_data,
            nist_alice_eval=alice_eval,
            filter_config=filter_config,
            quant_config=quant_config,
            prbs_config=prbs_config,
            recon_config=recon_config,
            pa_config=pa_config,
            nist_config=nist_config,
            timer=timer,
        )
        path_results[path_name] = res

    return MultiPathKGRResult(
        config=cfg,
        path_results=path_results,
        metadata={
            "timer_boundaries": {
                "start": TIMER_START_BOUNDARY,
                "end": TIMER_END_BOUNDARY,
                "excluded": "Workbook loading, plotting/rendering, CSV/JSON/XLSX exports, NIST evaluation, Eve channels evaluation",
            },
            "bch_cache_policy": BCH_CACHE_POLICY_DESC,
            "disclaimer": cfg.disclaimer,
        },
    )


# ==============================================================================
# Artifact Exporters (CSV, JSON, Companion XLSX)
# ==============================================================================


def export_kgr_metrics_csv(
    kgr_result: MultiPathKGRResult,
    output_path: str | Path,
) -> Path:
    """Export KGR summary metrics to CSV.

    Columns:
        path, total_chunks, accepted_chunks, raw_generated_bits, accepted_bits,
        duration_seconds, duration_ms, accepted_kgr_bps, raw_kgr_bps,
        nist_overall_passed, alice_bob_exact_match, alice_bob_kar_percent, label
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "path",
        "total_chunks",
        "accepted_chunks",
        "raw_generated_bits",
        "accepted_bits",
        "duration_seconds",
        "duration_ms",
        "accepted_kgr_bps",
        "raw_kgr_bps",
        "nist_overall_passed",
        "alice_bob_exact_match",
        "alice_bob_kar_percent",
        "label",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in kgr_result.metrics:
            writer.writerow(
                {
                    "path": res.path_name,
                    "total_chunks": res.total_chunks,
                    "accepted_chunks": res.accepted_chunks,
                    "raw_generated_bits": res.raw_generated_bits,
                    "accepted_bits": res.accepted_bits,
                    "duration_seconds": round(res.duration_seconds, 6),
                    "duration_ms": round(res.duration_ms, 3),
                    "accepted_kgr_bps": round(res.accepted_kgr_bps, 2),
                    "raw_kgr_bps": round(res.raw_kgr_bps, 2),
                    "nist_overall_passed": "TRUE" if res.nist_overall_passed else "FALSE",
                    "alice_bob_exact_match": "TRUE" if res.alice_bob_exact_match else "FALSE",
                    "alice_bob_kar_percent": round(res.alice_bob_kar, 4),
                    "label": res.label,
                }
            )
    return out


def export_kgr_config_json(
    kgr_result: MultiPathKGRResult,
    output_path: str | Path,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Export KGR measurement metadata and configuration to JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    for res in kgr_result.metrics:
        summary.append(
            {
                "path": res.path_name,
                "total_chunks": res.total_chunks,
                "accepted_chunks": res.accepted_chunks,
                "raw_generated_bits": res.raw_generated_bits,
                "accepted_bits": res.accepted_bits,
                "duration_seconds": res.duration_seconds,
                "duration_ms": res.duration_ms,
                "accepted_kgr_bps": res.accepted_kgr_bps,
                "raw_kgr_bps": res.raw_kgr_bps,
                "nist_overall_passed": res.nist_overall_passed,
                "alice_bob_exact_match": res.alice_bob_exact_match,
                "alice_bob_kar_percent": res.alice_bob_kar,
                "label": res.label,
            }
        )

    meta = {
        "scientific_disclaimer": kgr_result.config.disclaimer,
        "kgr_config": kgr_result.config.to_metadata_dict(),
        "summary": summary,
        "timing_policy": {
            "start_boundary": TIMER_START_BOUNDARY,
            "end_boundary": TIMER_END_BOUNDARY,
            "bch_cache_policy": BCH_CACHE_POLICY_DESC,
        },
    }
    if extra_metadata:
        meta.update(extra_metadata)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out


def export_evaluation_workbook_xlsx(
    nist_result: MultiPathNISTResult,
    kgr_result: MultiPathKGRResult,
    output_path: str | Path,
) -> Path:
    """Export comprehensive companion evaluation Excel workbook (.xlsx).

    Preserves explicit Text formatting (@) for all bit/hex keys, preventing leading-zero truncation.

    Sheets:
        1. KGR Metrics: Throughput, duration, raw vs accepted bits, and Alice-Bob agreement.
        2. NIST Tests: Per-test statistics, p-values, applicability, and pass/fail across all channels.
        3. Config & Disclaimers: Governing equations, timing boundaries, cache policy, and disclaimers.
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

    # Sheet 1: KGR Metrics
    ws1 = wb.active
    ws1.title = "KGR Metrics"
    headers1 = [
        "Path",
        "Total Chunks",
        "Accepted Chunks",
        "Raw Bits (N_raw)",
        "NIST All-Passed",
        "Accepted Bits (N_bit)",
        "Duration (s)",
        "Duration (ms)",
        "Accepted KGR (bps)",
        "Raw KGR (bps)",
        "Alice–Bob Exact Match",
        "Alice–Bob Post-PA KAR (%)",
        "Validation Label",
    ]
    ws1.append(headers1)
    for col_idx in range(1, len(headers1) + 1):
        cell = ws1.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    for r_idx, res in enumerate(kgr_result.metrics, start=2):
        ws1.append(
            [
                res.path_name,
                res.total_chunks,
                res.accepted_chunks,
                res.raw_generated_bits,
                "YES" if res.nist_overall_passed else "NO",
                res.accepted_bits,
                round(res.duration_seconds, 6),
                round(res.duration_ms, 3),
                round(res.accepted_kgr_bps, 2),
                round(res.raw_kgr_bps, 2),
                "TRUE" if res.alice_bob_exact_match else "FALSE",
                round(res.alice_bob_kar, 4),
                res.label,
            ]
        )
        for c_idx in range(1, len(headers1) + 1):
            c = ws1.cell(row=r_idx, column=c_idx)
            c.font = data_font
            c.alignment = center_align if c_idx not in (1, 13) else left_align

    # Auto-adjust column widths for Sheet 1
    for col in ws1.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws1.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Sheet 2: NIST Tests
    ws2 = wb.create_sheet(title="NIST Randomness")
    headers2 = [
        "Path",
        "Pair",
        "Channel",
        "Role",
        "Chunk Index",
        "Key Length",
        "Key Hex Digest",
        "Monobit s_obs",
        "Monobit P-val",
        "Monobit Pass",
        "Runs Vn(obs)",
        "Runs P-val",
        "Runs Pass",
        "Runs Reason",
        "ApEn chi^2",
        "ApEn P-val",
        "ApEn Pass",
        "ApEn Reason",
        "Overall Accepted",
    ]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    for r_idx, res in enumerate(nist_result.all_results, start=2):
        ws2.append(
            [
                res.path_name,
                res.pair_name or "",
                res.channel_name,
                res.channel_role,
                res.chunk_index,
                res.key_length,
                res.key_hex,
                round(res.monobit.statistic, 4),
                round(res.monobit.p_value, 6),
                "PASS" if res.monobit.passed else "FAIL",
                round(res.runs.statistic, 4),
                round(res.runs.p_value, 6),
                "PASS" if res.runs.passed else "FAIL",
                res.runs.reason or "",
                round(res.approximate_entropy.statistic, 4),
                round(res.approximate_entropy.p_value, 6),
                "PASS" if res.approximate_entropy.passed else "FAIL",
                res.approximate_entropy.reason or "",
                "ACCEPTED" if res.overall_accepted else "REJECTED",
            ]
        )
        for c_idx in range(1, len(headers2) + 1):
            c = ws2.cell(row=r_idx, column=c_idx)
            if c_idx == 7:
                c.font = mono_font
                c.data_type = "s"
                c.number_format = "@"
                c.alignment = left_align
            else:
                c.font = data_font
                c.alignment = center_align if c_idx not in (1, 2, 3, 4, 14, 18) else left_align

    for col in ws2.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)

    # Sheet 3: Config & Disclaimers
    ws3 = wb.create_sheet(title="Config & Disclaimers")
    ws3.column_dimensions["A"].width = 28
    ws3.column_dimensions["B"].width = 85

    ws3.append(["Parameter / Topic", "Description / Value"])
    ws3.cell(row=1, column=1).fill = header_fill
    ws3.cell(row=1, column=1).font = header_font
    ws3.cell(row=1, column=2).fill = header_fill
    ws3.cell(row=1, column=2).font = header_font

    meta_rows = [
        ("KGR Formulation", "PA.pdf Section 3.2.8.b, Equation (3.63): KGR = N_bit / T (bps)"),
        ("Single-Accounting Rule", "Alice's chunks counted once (256 bits per passed chunk). Bob's matching chunks are not duplicate-counted."),
        ("Frequency (Monobit) Test", "PA.pdf Eq (3.65)–(3.66), NIST SP 800-22 Rev. 1a Sec 2.1 (alpha=0.01)"),
        ("Runs Test", "PA.pdf Eq (3.67)–(3.69), NIST SP 800-22 Rev. 1a Sec 2.3 (prerequisite: |pi - 0.5| < 2/sqrt(n))"),
        ("Approximate Entropy Test", "PA.pdf Eq (3.70)–(3.73), NIST SP 800-22 Rev. 1a Sec 2.12 (m=2, alpha=0.01)"),
        ("Timer Start Boundary", TIMER_START_BOUNDARY),
        ("Timer End Boundary", TIMER_END_BOUNDARY),
        ("Timer Exclusions", "Raw data reading/parsing, plotting/rendering, CSV/JSON/XLSX exports, NIST evaluation, Eve channels"),
        ("BCH Cache Policy", BCH_CACHE_POLICY_DESC),
        ("Research Disclaimer", RESEARCH_DISCLAIMER_KGR),
    ]

    for r_idx, (param, val) in enumerate(meta_rows, start=2):
        ws3.append([param, val])
        ws3.cell(row=r_idx, column=1).font = Font(name="Calibri", size=10, bold=True)
        ws3.cell(row=r_idx, column=2).font = data_font
        if "Disclaimer" in param:
            ws3.cell(row=r_idx, column=1).fill = notice_fill
            ws3.cell(row=r_idx, column=2).fill = notice_fill
            ws3.cell(row=r_idx, column=2).font = notice_font

    wb.save(out)
    return out
