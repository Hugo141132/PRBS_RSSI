"""Privacy Amplification module using bit-level SHA-256 with 100-bit segmentation.

Governing Specification:
    PA.pdf Section 3.2.6, Equations (3.37)–(3.53), pages 30–33 (Privacy Amplification using SHA-256).
    PA.pdf Section 3.2.8.c, Equation (3.64), page 35 (Key Agreement Rate).
    FIPS PUB 180-4: Secure Hash Standard (SHS) for SHA-256 specification.

Mathematical Formulation & Segmentation Architecture:
    1. 100-Bit Consecutive Non-Overlapping Segmentation:
       Given an unpadded reconciled bitstream M in {0, 1}^L:
           - Incomplete segments are strictly rejected (L must be a multiple of SEGMENT_SIZE_BITS=100).
           - The bitstream is partitioned into M_chunks = L // 100 segments:
                 S_c = M[c * 100 : (c + 1) * 100],  c in {0, ..., M_chunks - 1}
           - Temporal ordering of segments is strictly preserved.
           - No padding or truncation of the source/reconciled stream is applied during chunking.

    2. Bit-level SHA-256 Hash Compression per Segment (PA.pdf Section 3.2.6, Equations 3.37–3.39):
       Each 100-bit segment S_c (L_c = 100) is independently padded per FIPS 180-4:
           S'_c = S_c || 1 || 0^p || [100]_64
       where p = (448 - 1 - 100) mod 512 = 347 bits, and [100]_64 is the 64-bit big-endian
       representation of integer 100. Total padded length |S'_c| = 100 + 1 + 347 + 64 = 512 bits (1 block).

    3. Message Scheduling & 64-Round Compression Loop (Equations 3.40–3.53):
       Each 512-bit block is parsed into sixteen 32-bit big-endian words W_0 .. W_15,
       expanded to W_16 .. W_63, and processed through the 64-round SHA-256 compression
       loop to yield a 256-bit digest:
           K_c = H_0 || H_1 || ... || H_7 in {0, 1}^256 (64 hex characters).

    4. Supported Paths & Chunk Counts:
       - quant_2bit: 1,000 bits -> 10 keys
       - quant_4bit: 2,000 bits -> 20 keys
       - prbs_2bit:  4,000 bits -> 40 keys
       - prbs_4bit:  4,000 bits -> 40 keys

    5. Key Agreement Rate (KAR) per Segment & Summary Aggregation (PA.pdf Section 3.2.8.c, Eq 3.64):
       For each chunk c between source digest K_s^(c) and receiver digest K_r^(c):
           KAR^(c) = ((256 - mismatches) / 256) * 100%
           exact_key_match^(c) = (K_s^(c) == K_r^(c))
       Summary metrics aggregate mean KAR, total matching chunks, and overall exact match status.

Scientific & Secrecy Disclaimer:
    256-bit SHA-256 output does not imply 256 bits of physical entropy when upstream
    PRBS expansion is deterministic and public BCH helper data leaks parity relations.
    Evaluation on synthetic indoor dummy data is for software validation only.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from rssi_skg.reconciliation import (
    MultiPathReconciliationResult,
    PairReconciliationResult,
    PATHS,
)

# Supported 4-path architecture
PA_PATHS: tuple[str, ...] = ("quant_2bit", "quant_4bit", "prbs_2bit", "prbs_4bit")
SEGMENT_SIZE_BITS: int = 100

# Canonical PA evaluation pairs under bidirectional transmission observation model:
#   1. Alice–Bob: Legitimate communication pair (Alice reference, Bob receiver)
#   2. Alice–Eve1-Alice: Passive observer overhearing Alice (Alice reference, Eve1-Alice receiver)
#   3. Bob–Eve1-Bob: Passive observer overhearing Bob (Bob reference, Eve1-Bob receiver)
PA_EVALUATION_PAIRS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("Alice", "Bob", "Alice–Bob", "Alice", True),
    ("Alice", "Eve1-Alice", "Alice–Eve1-Alice", "Alice", False),
    ("Bob", "Eve1-Bob", "Bob–Eve1-Bob", "Bob", False),
)

SCIENTIFIC_DISCLAIMER: str = (
    "Synthetic software validation only; 256-bit SHA-256 output does not imply "
    "256 bits of physical entropy when upstream PRBS expansion is deterministic "
    "and public BCH helper data leaks parity relations. An attacker recovering "
    "source bits algebraically from helper data can compute the identical SHA-256 digest; "
    "~50% Post-PA KAR under ordinary decoding failure does not establish empirical secrecy."
)

# SHA-256 Round Constants K_0 .. K_63
SHA256_K: tuple[int, ...] = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3, 0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13, 0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208, 0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)

# Initial Hash Values H^(0)
SHA256_H_INIT: tuple[int, ...] = (
    0x6A09E667,
    0xBB67AE85,
    0x3C6EF372,
    0xA54FF53A,
    0x510E527F,
    0x9B05688C,
    0x1F83D9AB,
    0x5BE0CD19,
)

MASK_32: int = 0xFFFFFFFF


# ==============================================================================
# Bitwise Primitive Operations on 32-bit Words (FIPS PUB 180-4)
# ==============================================================================


def rotr32(n: int, x: int) -> int:
    """Right rotate 32-bit word x by n positions (ROTR^n(x))."""
    n %= 32
    return ((x >> n) | ((x << (32 - n)) & MASK_32)) & MASK_32


def shr32(n: int, x: int) -> int:
    """Right shift 32-bit word x by n positions (SHR^n(x))."""
    return (x >> n) & MASK_32


def sigma0_32(x: int) -> int:
    """sigma_0(x) = ROTR^7(x) XOR ROTR^18(x) XOR SHR^3(x) per PA.pdf Eq (3.40)."""
    return rotr32(7, x) ^ rotr32(18, x) ^ shr32(3, x)


def sigma1_32(x: int) -> int:
    """sigma_1(x) = ROTR^17(x) XOR ROTR^19(x) XOR SHR^10(x) per PA.pdf Eq (3.42)."""
    return rotr32(17, x) ^ rotr32(19, x) ^ shr32(10, x)


def big_sigma0_32(x: int) -> int:
    """Sigma_0(x) = ROTR^2(x) XOR ROTR^13(x) XOR ROTR^22(x) per PA.pdf Eq (3.46)."""
    return rotr32(2, x) ^ rotr32(13, x) ^ rotr32(22, x)


def big_sigma1_32(x: int) -> int:
    """Sigma_1(x) = ROTR^6(x) XOR ROTR^11(x) XOR ROTR^25(x) per PA.pdf Eq (3.47)."""
    return rotr32(6, x) ^ rotr32(11, x) ^ rotr32(25, x)


def ch32(x: int, y: int, z: int) -> int:
    """Ch(x, y, z) = (x AND y) XOR (NOT x AND z) per PA.pdf Eq (3.44)."""
    return (x & y) ^ ((~x) & z) & MASK_32


def maj32(x: int, y: int, z: int) -> int:
    """Maj(x, y, z) = (x AND y) XOR (x AND z) XOR (y AND z) per PA.pdf Eq (3.45)."""
    return (x & y) ^ (x & z) ^ (y & z)


# ==============================================================================
# Bit-level Padding, Segmentation, and SHA-256 Engine
# ==============================================================================


def pad_bitstream(bitstream: str | Sequence[int]) -> str:
    """Pad arbitrary-length bitstream strictly following PA.pdf Section 3.2.6 (Eqs 3.37-3.39).

    Padding: M' = M || '1' || '0'*p || [L]_64
    where (L + 1 + p) = 448 (mod 512) and p >= 0.

    Args:
        bitstream: Unpadded bitstream as binary string ('0101...') or int sequence.

    Returns:
        str: Padded binary bitstream with length a strict multiple of 512 bits.

    Raises:
        ValueError: If bitstream contains non-binary values.
    """
    if isinstance(bitstream, str):
        bits = bitstream.strip()
        if any(c not in ("0", "1") for c in bits):
            raise ValueError("Bitstream string must contain only '0' and '1'.")
    else:
        bits = "".join(str(int(b)) for b in bitstream)
        if any(c not in ("0", "1") for c in bits):
            raise ValueError("Bitstream sequence must contain only binary integers (0 or 1).")

    L = len(bits)
    p = (448 - 1 - L) % 512
    l_64 = format(L, "064b")
    padded = bits + "1" + ("0" * p) + l_64
    return padded


def sha256_bitstream(bitstream: str | Sequence[int]) -> tuple[str, str]:
    """Execute FIPS 180-4 SHA-256 on arbitrary-length bitstream per PA.pdf Eqs (3.37)–(3.53).

    Operates natively on arbitrary bit lengths without assuming byte-alignment.

    Args:
        bitstream: Unpadded binary bitstream.

    Returns:
        tuple[str, str]: (key_bin, key_hex)
            key_bin: 256-character binary string ('0' and '1').
            key_hex: 64-character lowercase hexadecimal digest.
    """
    padded = pad_bitstream(bitstream)
    total_bits = len(padded)
    num_blocks = total_bits // 512

    H = list(SHA256_H_INIT)

    for i in range(num_blocks):
        block_str = padded[i * 512 : (i + 1) * 512]

        # Parse 512-bit block into sixteen 32-bit big-endian words
        W = [0] * 64
        for t in range(16):
            word_str = block_str[t * 32 : (t + 1) * 32]
            W[t] = int(word_str, 2)

        # Message schedule expansion: t = 16 .. 63 (Eq 3.43)
        for t in range(16, 64):
            s1 = sigma1_32(W[t - 2])
            s0 = sigma0_32(W[t - 15])
            W[t] = (s1 + W[t - 7] + s0 + W[t - 16]) & MASK_32

        # Initialize working variables
        a, b, c, d, e, f, g, h = H

        # 64-round compression loop (Eqs 3.48–3.53)
        for t in range(64):
            T1 = (h + big_sigma1_32(e) + ch32(e, f, g) + SHA256_K[t] + W[t]) & MASK_32
            T2 = (big_sigma0_32(a) + maj32(a, b, c)) & MASK_32
            h = g
            g = f
            f = e
            e = (d + T1) & MASK_32
            d = c
            c = b
            b = a
            a = (T1 + T2) & MASK_32

        # Update intermediate hash values
        H[0] = (H[0] + a) & MASK_32
        H[1] = (H[1] + b) & MASK_32
        H[2] = (H[2] + c) & MASK_32
        H[3] = (H[3] + d) & MASK_32
        H[4] = (H[4] + e) & MASK_32
        H[5] = (H[5] + f) & MASK_32
        H[6] = (H[6] + g) & MASK_32
        H[7] = (H[7] + h) & MASK_32

    # Assemble 256-bit final key
    key_bin = "".join(format(h_val, "032b") for h_val in H)
    key_hex = "".join(format(h_val, "08x") for h_val in H)

    return key_bin, key_hex


def segment_bitstream(
    bitstream: str | Sequence[int],
    segment_size: int = SEGMENT_SIZE_BITS,
) -> list[str]:
    """Divide bitstream into consecutive, non-overlapping segments of segment_size bits.

    Validates bitstream length and rejects incomplete segments explicitly;
    never silently truncates or pads. Preserves temporal order.

    Args:
        bitstream: Input bitstream string or int sequence.
        segment_size: Bit length of each segment (default: 100).

    Returns:
        list[str]: Consecutive non-overlapping segments of length segment_size.

    Raises:
        ValueError: If input length is empty, contains non-binary characters,
                    or is not an exact positive integer multiple of segment_size.
    """
    if isinstance(bitstream, str):
        bits = bitstream.strip()
        if any(c not in ("0", "1") for c in bits):
            raise ValueError("Bitstream string must contain only '0' and '1'.")
    else:
        bits = "".join(str(int(b)) for b in bitstream)
        if any(c not in ("0", "1") for c in bits):
            raise ValueError("Bitstream sequence must contain only binary integers (0 or 1).")

    total_len = len(bits)
    if total_len == 0:
        raise ValueError("Cannot segment an empty bitstream.")

    if segment_size <= 0:
        raise ValueError(f"segment_size must be a positive integer, got {segment_size}.")

    remainder = total_len % segment_size
    if remainder != 0:
        raise ValueError(
            f"Bitstream length ({total_len} bits) is not an exact multiple of segment size "
            f"({segment_size} bits); incomplete segment of {remainder} bits would remain. "
            "Silent truncation and padding are prohibited."
        )

    num_segments = total_len // segment_size
    return [bits[i * segment_size : (i + 1) * segment_size] for i in range(num_segments)]


def verify_against_hashlib(bitstream: str) -> bool:
    """Verify bitstream hash against hashlib.sha256 if bitstream is byte-aligned (L % 8 == 0).

    Args:
        bitstream: Binary string of length L.

    Returns:
        bool: True if hex digest matches hashlib, False otherwise (or raises ValueError if not byte-aligned).
    """
    if len(bitstream) % 8 != 0:
        raise ValueError(
            f"Cross-verification with hashlib.sha256 requires byte-aligned bitstream (len % 8 == 0), got len={len(bitstream)}."
        )

    _, our_hex = sha256_bitstream(bitstream)
    raw_bytes = bytes(int(bitstream[j : j + 8], 2) for j in range(0, len(bitstream), 8))
    ref_hex = hashlib.sha256(raw_bytes).hexdigest()
    return our_hex == ref_hex


# ==============================================================================
# Privacy Amplification Data Containers
# ==============================================================================


@dataclass(frozen=True)
class PrivacyAmplificationConfig:
    """Configuration container for Privacy Amplification stage."""

    hash_algorithm: str = "SHA-256"
    key_length_bits: int = 256
    segment_size_bits: int = SEGMENT_SIZE_BITS
    supported_paths: tuple[str, ...] = PA_PATHS
    scientific_disclaimer: str = SCIENTIFIC_DISCLAIMER

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert configuration to metadata dictionary."""
        return {
            "algorithm": "Privacy Amplification via Segmented Bit-Level SHA-256",
            "hash_algorithm": self.hash_algorithm,
            "key_length_bits": self.key_length_bits,
            "segment_size_bits": self.segment_size_bits,
            "supported_paths": list(self.supported_paths),
            "path_key_counts": {
                "quant_2bit": 10,
                "quant_4bit": 20,
                "prbs_2bit": 40,
                "prbs_4bit": 40,
            },
            "governing_specification": {
                "privacy_amplification": "PA.pdf Section 3.2.6, Equations (3.37)–(3.53), pages 30–33",
                "key_agreement_rate": "PA.pdf Section 3.2.8.c, Equation (3.64), page 35",
                "standard": "FIPS PUB 180-4 Secure Hash Standard (SHS)",
            },
            "scientific_disclaimer": self.scientific_disclaimer,
        }


@dataclass(frozen=True)
class ChunkKeyResult:
    """Derived secret key and metadata for an individual segment."""

    chunk_index: int
    input_segment_bits: str
    key_bin: str
    key_hex: str


@dataclass(frozen=True)
class ChannelPrivacyAmplificationResult:
    """Container holding derived secret keys for a single communication channel."""

    path_name: str
    channel_name: str
    channel_role: str
    input_bit_length: int
    num_chunks: int
    chunk_size_bits: int
    chunk_keys: list[ChunkKeyResult]

    @property
    def key_bin(self) -> str:
        """First chunk key binary string (backward-compatibility convenience)."""
        return self.chunk_keys[0].key_bin if self.chunk_keys else ""

    @property
    def key_hex(self) -> str:
        """First chunk key hexadecimal digest (backward-compatibility convenience)."""
        return self.chunk_keys[0].key_hex if self.chunk_keys else ""

    @property
    def all_keys_hex(self) -> list[str]:
        """List of all chunk hexadecimal digests."""
        return [ck.key_hex for ck in self.chunk_keys]

    @property
    def all_keys_bin(self) -> list[str]:
        """List of all chunk binary strings."""
        return [ck.key_bin for ck in self.chunk_keys]


@dataclass(frozen=True)
class ChunkPairPAResult:
    """Evaluation metrics between source and receiver for a single segment."""

    chunk_index: int
    source_segment_bits: str
    receiver_segment_bits: str
    source_key_bin: str
    source_key_hex: str
    receiver_key_bin: str
    receiver_key_hex: str
    post_pa_kar: float
    exact_key_match: bool
    mismatched_key_bits: int


@dataclass(frozen=True)
class PairPrivacyAmplificationResult:
    """Aggregated privacy amplification evaluation between a channel pair across all segments."""

    path_name: str
    pair_name: str
    source_name: str
    receiver_name: str
    is_legitimate: bool
    input_bit_length: int
    num_chunks: int
    chunk_size_bits: int
    pre_pa_kar: float
    post_pa_kar: float  # Mean post-PA KAR across all chunks
    exact_key_match: bool  # True if all chunks match exactly
    exact_match_count: int
    exact_match_rate_percent: float
    chunk_results: list[ChunkPairPAResult]

    @property
    def kar_delta(self) -> float:
        """Change in KAR from pre-PA to post-PA (in percentage points)."""
        return self.post_pa_kar - self.pre_pa_kar

    @property
    def source_key_hex(self) -> str:
        """First chunk source key hex (convenience property)."""
        return self.chunk_results[0].source_key_hex if self.chunk_results else ""

    @property
    def receiver_key_hex(self) -> str:
        """First chunk receiver key hex (convenience property)."""
        return self.chunk_results[0].receiver_key_hex if self.chunk_results else ""

    @property
    def source_key_bin(self) -> str:
        """First chunk source key bin (convenience property)."""
        return self.chunk_results[0].source_key_bin if self.chunk_results else ""

    @property
    def receiver_key_bin(self) -> str:
        """First chunk receiver key bin (convenience property)."""
        return self.chunk_results[0].receiver_key_bin if self.chunk_results else ""

    @property
    def mismatched_key_bits(self) -> int:
        """Total mismatched bits across all chunks."""
        return sum(c.mismatched_key_bits for c in self.chunk_results)


@dataclass
class MultiPathPrivacyAmplificationResult:
    """Master container holding Privacy Amplification results across all four paths and all pairs."""

    config: PrivacyAmplificationConfig
    channel_keys: dict[str, dict[str, ChannelPrivacyAmplificationResult]]
    pair_results: dict[str, dict[str, PairPrivacyAmplificationResult]]
    figure_paths: tuple[Path, Path] | None = None

    @property
    def metrics(self) -> list[PairPrivacyAmplificationResult]:
        """Return flattened list of pair results in canonical order across supported paths."""
        res: list[PairPrivacyAmplificationResult] = []
        for path_name in self.config.supported_paths:
            if path_name in self.pair_results:
                for p_info in PA_EVALUATION_PAIRS:
                    pair_name = p_info[2]
                    if pair_name in self.pair_results[path_name]:
                        res.append(self.pair_results[path_name][pair_name])
        return res


# ==============================================================================
# Pipeline Execution Function
# ==============================================================================


def amplify_privacy_all_paths(
    reconcile_result: MultiPathReconciliationResult,
    config: PrivacyAmplificationConfig | None = None,
) -> MultiPathPrivacyAmplificationResult:
    """Execute Stage 6 Privacy Amplification across all four reconciled paths with 100-bit segmentation.

    Supported paths and chunk counts:
        - quant_2bit: 1,000 bits -> 10 keys (10 chunks of 100 bits)
        - quant_4bit: 2,000 bits -> 20 keys (20 chunks of 100 bits)
        - prbs_2bit:  4,000 bits -> 40 keys (40 chunks of 100 bits)
        - prbs_4bit:  4,000 bits -> 40 keys (40 chunks of 100 bits)

    Evaluates the 4 channels independently with strict isolation:
        - Alice (source / reference key generator for Alice–Bob & Alice–Eve1-Alice)
        - Bob (legitimate receiver reconciled to Alice; reference key generator for Bob–Eve1-Bob)
        - Eve1-Alice (passive eavesdropper overhearing Alice)
        - Eve1-Bob (passive eavesdropper overhearing Bob)

    Evaluates metrics across the 3 evaluation pairs under the bidirectional observation model:
        1. Alice–Bob (legitimate pair: Alice source keys vs Bob receiver keys)
        2. Alice–Eve1-Alice (eavesdropper stream 1: Alice source keys vs Eve1-Alice receiver keys)
        3. Bob–Eve1-Bob (eavesdropper stream 2: Bob source keys vs Eve1-Bob receiver keys)

    Args:
        reconcile_result: Completed MultiPathReconciliationResult from Stage 5.
        config: PrivacyAmplificationConfig instance (uses defaults if None).

    Returns:
        MultiPathPrivacyAmplificationResult: Master container holding all chunk keys and metrics.
    """
    cfg = config if config is not None else PrivacyAmplificationConfig()
    seg_size = cfg.segment_size_bits

    channel_keys: dict[str, dict[str, ChannelPrivacyAmplificationResult]] = {}
    pair_results: dict[str, dict[str, PairPrivacyAmplificationResult]] = {}

    for path_name in cfg.supported_paths:
        if path_name not in reconcile_result.path_results:
            continue

        p_pairs = reconcile_result.path_results[path_name]
        res_ab = p_pairs["Alice–Bob"]
        res_ea = p_pairs["Alice–Eve1-Alice"]
        res_eb = p_pairs["Bob–Eve1-Bob"]

        # Unpadded bitstreams from reconciliation
        alice_stream = res_ab.source_unpadded
        bob_stream = res_ab.recovered_unpadded
        ea_stream = res_ea.recovered_unpadded
        eb_stream = res_eb.recovered_unpadded

        # Segment each channel's bitstream into 100-bit non-overlapping chunks
        alice_segments = segment_bitstream(alice_stream, segment_size=seg_size)
        bob_segments = segment_bitstream(bob_stream, segment_size=seg_size)
        ea_segments = segment_bitstream(ea_stream, segment_size=seg_size)
        eb_segments = segment_bitstream(eb_stream, segment_size=seg_size)

        num_chunks = len(alice_segments)
        if not (len(bob_segments) == len(ea_segments) == len(eb_segments) == num_chunks):
            raise ValueError(
                f"Segment counts mismatch across channels in path '{path_name}': "
                f"Alice={len(alice_segments)}, Bob={len(bob_segments)}, "
                f"Eve1-Alice={len(ea_segments)}, Eve1-Bob={len(eb_segments)}."
            )

        # Compute SHA-256 digests for each channel's segments independently
        def hash_segments(segments: list[str]) -> list[ChunkKeyResult]:
            chunk_keys: list[ChunkKeyResult] = []
            for idx, seg in enumerate(segments):
                k_bin, k_hex = sha256_bitstream(seg)
                chunk_keys.append(
                    ChunkKeyResult(
                        chunk_index=idx,
                        input_segment_bits=seg,
                        key_bin=k_bin,
                        key_hex=k_hex,
                    )
                )
            return chunk_keys

        alice_keys = hash_segments(alice_segments)
        bob_keys = hash_segments(bob_segments)
        ea_keys = hash_segments(ea_segments)
        eb_keys = hash_segments(eb_segments)

        channel_keys[path_name] = {
            "Alice": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Alice",
                channel_role="Legitimate Source (Reference Key)",
                input_bit_length=len(alice_stream),
                num_chunks=num_chunks,
                chunk_size_bits=seg_size,
                chunk_keys=alice_keys,
            ),
            "Bob": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Bob",
                channel_role="Legitimate Receiver (Reconciled to Alice)",
                input_bit_length=len(bob_stream),
                num_chunks=num_chunks,
                chunk_size_bits=seg_size,
                chunk_keys=bob_keys,
            ),
            "Eve1-Alice": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Eve1-Alice",
                channel_role="Passive Eavesdropper (Overhearing Alice)",
                input_bit_length=len(ea_stream),
                num_chunks=num_chunks,
                chunk_size_bits=seg_size,
                chunk_keys=ea_keys,
            ),
            "Eve1-Bob": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Eve1-Bob",
                channel_role="Passive Eavesdropper (Overhearing Bob)",
                input_bit_length=len(eb_stream),
                num_chunks=num_chunks,
                chunk_size_bits=seg_size,
                chunk_keys=eb_keys,
            ),
        }

        # Evaluate pairs per PA.pdf Eq (3.64)
        def evaluate_pair(
            pair_name: str,
            source_name: str,
            receiver_name: str,
            is_legitimate: bool,
            pre_kar: float,
            s_keys: list[ChunkKeyResult],
            r_keys: list[ChunkKeyResult],
        ) -> PairPrivacyAmplificationResult:
            chunk_results: list[ChunkPairPAResult] = []
            match_count = 0
            kar_sum = 0.0

            for idx in range(num_chunks):
                sk = s_keys[idx]
                rk = r_keys[idx]
                mismatches = sum(1 for a, b in zip(sk.key_bin, rk.key_bin) if a != b)
                chunk_kar = ((256 - mismatches) / 256.0) * 100.0
                is_match = (sk.key_bin == rk.key_bin)
                if is_match:
                    match_count += 1
                kar_sum += chunk_kar

                chunk_results.append(
                    ChunkPairPAResult(
                        chunk_index=idx,
                        source_segment_bits=sk.input_segment_bits,
                        receiver_segment_bits=rk.input_segment_bits,
                        source_key_bin=sk.key_bin,
                        source_key_hex=sk.key_hex,
                        receiver_key_bin=rk.key_bin,
                        receiver_key_hex=rk.key_hex,
                        post_pa_kar=chunk_kar,
                        exact_key_match=is_match,
                        mismatched_key_bits=mismatches,
                    )
                )

            mean_post_kar = kar_sum / num_chunks if num_chunks > 0 else 0.0
            exact_match_rate = (match_count / num_chunks * 100.0) if num_chunks > 0 else 0.0
            all_matched = (match_count == num_chunks)

            return PairPrivacyAmplificationResult(
                path_name=path_name,
                pair_name=pair_name,
                source_name=source_name,
                receiver_name=receiver_name,
                is_legitimate=is_legitimate,
                input_bit_length=len(alice_stream),
                num_chunks=num_chunks,
                chunk_size_bits=seg_size,
                pre_pa_kar=pre_kar,
                post_pa_kar=mean_post_kar,
                exact_key_match=all_matched,
                exact_match_count=match_count,
                exact_match_rate_percent=exact_match_rate,
                chunk_results=chunk_results,
            )

        # Pre-PA KAR from Stage 5 BCH reconciliation outputs:
        #   Alice–Bob: post_reconcile_kar from res_ab
        #   Alice–Eve1-Alice: post_reconcile_kar from res_ea
        #   Bob–Eve1-Bob: post_reconcile_kar from res_eb
        pre_kar_ab = res_ab.post_reconcile_kar
        pre_kar_ea = res_ea.post_reconcile_kar
        pre_kar_eb = res_eb.post_reconcile_kar

        # Pair 1: Alice–Bob (legitimate: Alice source keys vs Bob receiver keys)
        pair_ab = evaluate_pair(
            pair_name="Alice–Bob",
            source_name="Alice",
            receiver_name="Bob",
            is_legitimate=True,
            pre_kar=pre_kar_ab,
            s_keys=alice_keys,
            r_keys=bob_keys,
        )
        # Pair 2: Alice–Eve1-Alice (eavesdropper stream 1: Alice source keys vs Eve1-Alice receiver keys)
        pair_ea = evaluate_pair(
            pair_name="Alice–Eve1-Alice",
            source_name="Alice",
            receiver_name="Eve1-Alice",
            is_legitimate=False,
            pre_kar=pre_kar_ea,
            s_keys=alice_keys,
            r_keys=ea_keys,
        )
        # Pair 3: Bob–Eve1-Bob (eavesdropper stream 2: Bob source keys vs Eve1-Bob receiver keys)
        pair_eb = evaluate_pair(
            pair_name="Bob–Eve1-Bob",
            source_name="Bob",
            receiver_name="Eve1-Bob",
            is_legitimate=False,
            pre_kar=pre_kar_eb,
            s_keys=bob_keys,
            r_keys=eb_keys,
        )

        pair_results[path_name] = {
            "Alice–Bob": pair_ab,
            "Alice–Eve1-Alice": pair_ea,
            "Bob–Eve1-Bob": pair_eb,
        }

    return MultiPathPrivacyAmplificationResult(
        config=cfg,
        channel_keys=channel_keys,
        pair_results=pair_results,
    )


# ==============================================================================
# Artifact Exporters (CSV, JSON, XLSX)
# ==============================================================================


def export_pa_metrics_csv(
    pa_result: MultiPathPrivacyAmplificationResult,
    output_path: str | Path,
) -> Path:
    """Export privacy amplification summary metrics to CSV across all paths and pairs.

    Columns:
        path, pair, source, receiver, is_legitimate, input_bits, chunk_size_bits,
        num_chunks, pre_pa_kar_percent, post_pa_kar_percent, kar_delta_pp,
        exact_key_match, exact_match_count, exact_match_rate_percent,
        source_key_hex, receiver_key_hex
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "path",
        "pair",
        "source",
        "receiver",
        "is_legitimate",
        "input_bits",
        "chunk_size_bits",
        "num_chunks",
        "key_bits",
        "pre_pa_kar_percent",
        "post_pa_kar_percent",
        "kar_delta_pp",
        "exact_key_match",
        "exact_match_count",
        "exact_match_rate_percent",
        "source_key_hex",
        "receiver_key_hex",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p_res in pa_result.metrics:
            writer.writerow(
                {
                    "path": p_res.path_name,
                    "pair": p_res.pair_name,
                    "source": p_res.source_name,
                    "receiver": p_res.receiver_name,
                    "is_legitimate": "TRUE" if p_res.is_legitimate else "FALSE",
                    "input_bits": p_res.input_bit_length,
                    "chunk_size_bits": p_res.chunk_size_bits,
                    "num_chunks": p_res.num_chunks,
                    "key_bits": 256,
                    "pre_pa_kar_percent": round(p_res.pre_pa_kar, 4),
                    "post_pa_kar_percent": round(p_res.post_pa_kar, 4),
                    "kar_delta_pp": round(p_res.kar_delta, 4),
                    "exact_key_match": "TRUE" if p_res.exact_key_match else "FALSE",
                    "exact_match_count": p_res.exact_match_count,
                    "exact_match_rate_percent": round(p_res.exact_match_rate_percent, 4),
                    "source_key_hex": p_res.source_key_hex,
                    "receiver_key_hex": p_res.receiver_key_hex,
                }
            )
    return out


def export_pa_keys_csv(
    pa_result: MultiPathPrivacyAmplificationResult,
    output_path: str | Path,
) -> Path:
    """Export channel secret keys for all chunks to CSV.

    Columns:
        path, channel, channel_role, chunk_index, input_segment_bits,
        key_bits, key_hex, key_bin
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "path",
        "channel",
        "channel_role",
        "chunk_index",
        "input_segment_bits",
        "key_bits",
        "key_hex",
        "key_bin",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for path_name, channels in pa_result.channel_keys.items():
            for ch_name, k_res in channels.items():
                for ck in k_res.chunk_keys:
                    writer.writerow(
                        {
                            "path": path_name,
                            "channel": ch_name,
                            "channel_role": k_res.channel_role,
                            "chunk_index": ck.chunk_index,
                            "input_segment_bits": ck.input_segment_bits,
                            "key_bits": 256,
                            "key_hex": ck.key_hex,
                            "key_bin": ck.key_bin,
                        }
                    )
    return out


def export_pa_config_json(
    pa_result: MultiPathPrivacyAmplificationResult,
    output_path: str | Path,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Export Privacy Amplification metadata and summary results to JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = pa_result.config.to_metadata_dict()
    if extra_metadata is not None:
        meta["execution_context"] = extra_metadata

    summary: dict[str, Any] = {}
    for path_name, pairs in pa_result.pair_results.items():
        summary[path_name] = {}
        for pair_name, res in pairs.items():
            summary[path_name][pair_name] = {
                "source": res.source_name,
                "receiver": res.receiver_name,
                "is_legitimate": res.is_legitimate,
                "input_bits": res.input_bit_length,
                "chunk_size_bits": res.chunk_size_bits,
                "num_chunks": res.num_chunks,
                "key_length_bits": 256,
                "pre_pa_kar_percent": round(res.pre_pa_kar, 4),
                "post_pa_kar_percent": round(res.post_pa_kar, 4),
                "kar_delta_pp": round(res.kar_delta, 4),
                "exact_key_match": res.exact_key_match,
                "exact_match_count": res.exact_match_count,
                "exact_match_rate_percent": round(res.exact_match_rate_percent, 4),
                "source_first_key_hex": res.source_key_hex,
                "receiver_first_key_hex": res.receiver_key_hex,
            }
    meta["privacy_amplification_summary"] = summary

    with open(out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out


def export_pa_workbook_xlsx(
    pa_result: MultiPathPrivacyAmplificationResult,
    output_path: str | Path,
) -> Path:
    """Export companion multi-sheet Excel workbook (.xlsx).

    Preserves explicit Text formatting (@) for all bitstrings and hex digests,
    preventing Excel from stripping leading zeros.

    Sheets:
        1. PA Metrics: Summary across 4 paths x 3 pairs.
        2. Per-Chunk Metrics: Granular chunk-by-chunk KAR, mismatches, and match indicators.
        3. Channel Keys: 256-bit binary strings and 64-char hex digests for all channels and chunks.
        4. Config & Disclaimers: Full methodology, parameter tracking, and scientific disclaimers.
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

    # Sheet 1: PA Metrics (Summary)
    ws1 = wb.active
    ws1.title = "PA Metrics"
    headers1 = [
        "Path",
        "Pair",
        "Legitimate",
        "Input Bits",
        "Chunk Size",
        "Num Chunks",
        "Key Bits",
        "Pre-PA KAR (%)",
        "Post-PA Mean KAR (%)",
        "Delta (pp)",
        "Exact Match Count",
        "Exact Match Rate (%)",
        "All Chunks Match",
        "Source First Key Hex",
        "Receiver First Key Hex",
    ]
    ws1.append(headers1)
    for col_idx in range(1, len(headers1) + 1):
        cell = ws1.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r1_idx = 2
    for p_res in pa_result.metrics:
        ws1.append(
            [
                p_res.path_name,
                p_res.pair_name,
                "YES" if p_res.is_legitimate else "NO",
                p_res.input_bit_length,
                p_res.chunk_size_bits,
                p_res.num_chunks,
                256,
                round(p_res.pre_pa_kar, 4),
                round(p_res.post_pa_kar, 4),
                round(p_res.kar_delta, 4),
                p_res.exact_match_count,
                round(p_res.exact_match_rate_percent, 2),
                "TRUE" if p_res.exact_key_match else "FALSE",
                p_res.source_key_hex,
                p_res.receiver_key_hex,
            ]
        )
        for c_idx in range(1, len(headers1) + 1):
            c = ws1.cell(row=r1_idx, column=c_idx)
            if c_idx in (14, 15):
                c.font = mono_font
                c.data_type = "s"
                c.number_format = "@"
                c.alignment = left_align
            else:
                c.font = data_font
                c.alignment = center_align
        r1_idx += 1

    # Sheet 2: Per-Chunk Metrics
    ws2 = wb.create_sheet(title="Per-Chunk Metrics")
    headers2 = [
        "Path",
        "Pair",
        "Chunk Index",
        "Chunk Bits",
        "Key Bits",
        "Chunk Post-KAR (%)",
        "Exact Match",
        "Mismatched Bits",
        "Source Key Hex",
        "Receiver Key Hex",
    ]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r2_idx = 2
    for p_res in pa_result.metrics:
        for ck_res in p_res.chunk_results:
            ws2.append(
                [
                    p_res.path_name,
                    p_res.pair_name,
                    ck_res.chunk_index,
                    p_res.chunk_size_bits,
                    256,
                    round(ck_res.post_pa_kar, 4),
                    "TRUE" if ck_res.exact_key_match else "FALSE",
                    ck_res.mismatched_key_bits,
                    ck_res.source_key_hex,
                    ck_res.receiver_key_hex,
                ]
            )
            for c_idx in range(1, len(headers2) + 1):
                c = ws2.cell(row=r2_idx, column=c_idx)
                if c_idx in (9, 10):
                    c.font = mono_font
                    c.data_type = "s"
                    c.number_format = "@"
                    c.alignment = left_align
                else:
                    c.font = data_font
                    c.alignment = center_align
            r2_idx += 1

    # Sheet 3: Channel Keys
    ws3 = wb.create_sheet(title="Channel Keys")
    headers3 = [
        "Path",
        "Channel",
        "Channel Role",
        "Chunk Index",
        "Input Segment Bits",
        "Key Bits",
        "Key Hex (64-char)",
        "Key Binary (256-bit)",
    ]
    ws3.append(headers3)
    for col_idx in range(1, len(headers3) + 1):
        cell = ws3.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r3_idx = 2
    for path_name, channels in pa_result.channel_keys.items():
        for ch_name, k_res in channels.items():
            for ck in k_res.chunk_keys:
                ws3.append(
                    [
                        path_name,
                        ch_name,
                        k_res.channel_role,
                        ck.chunk_index,
                        ck.input_segment_bits,
                        256,
                        ck.key_hex,
                        ck.key_bin,
                    ]
                )
                for c_idx in range(1, len(headers3) + 1):
                    c = ws3.cell(row=r3_idx, column=c_idx)
                    if c_idx in (5, 7, 8):
                        c.font = mono_font
                        c.data_type = "s"
                        c.number_format = "@"
                        c.alignment = left_align
                    else:
                        c.font = data_font
                        c.alignment = center_align
                r3_idx += 1

    # Sheet 4: Config & Disclaimers
    ws4 = wb.create_sheet(title="Config & Disclaimers")
    ws4.append(["Parameter / Property", "Value / Description"])
    ws4.cell(row=1, column=1).fill = header_fill
    ws4.cell(row=1, column=1).font = header_font
    ws4.cell(row=1, column=2).fill = header_fill
    ws4.cell(row=1, column=2).font = header_font

    cfg_rows = [
        ("Algorithm", "Segmented Bit-Level SHA-256 Privacy Amplification"),
        ("Standard Specification", "FIPS PUB 180-4 (Secure Hash Standard) / PA.pdf Section 3.2.6"),
        ("Segmentation Size", f"{SEGMENT_SIZE_BITS} bits (consecutive non-overlapping chunks)"),
        ("Key Agreement Rate Metric", "PA.pdf Section 3.2.8.c, Equation (3.64)"),
        ("Digest Output Length", "256 bits per segment (32 bytes / 64 hexadecimal characters)"),
        ("Supported Paths & Key Counts", "quant_2bit: 10 keys; quant_4bit: 20 keys; prbs_2bit: 40 keys; prbs_4bit: 40 keys"),
        ("Evaluated Channels", "Alice, Bob, Eve1-Alice, Eve1-Bob"),
        ("Evaluated Pairs", "Alice–Bob (legitimate: Alice vs Bob), Alice–Eve1-Alice (eavesdropper stream 1: Alice vs Eve1-Alice), Bob–Eve1-Bob (eavesdropper stream 2: Bob vs Eve1-Bob)"),
        ("Scientific Disclaimer", pa_result.config.scientific_disclaimer),
    ]

    for r_idx, (prop, val) in enumerate(cfg_rows, 2):
        ws4.append([prop, val])
        ws4.cell(row=r_idx, column=1).font = data_font
        ws4.cell(row=r_idx, column=1).alignment = left_align
        c_val = ws4.cell(row=r_idx, column=2)
        c_val.font = data_font
        c_val.alignment = left_align
        if "Disclaimer" in prop:
            c_val.fill = notice_fill
            c_val.font = notice_font

    # Adjust column widths
    for ws in [ws1, ws2, ws3, ws4]:
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 70)

    wb.save(out)
    return out
