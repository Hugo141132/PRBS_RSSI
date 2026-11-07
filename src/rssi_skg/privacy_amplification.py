"""Privacy Amplification module using bit-level SHA-256.

Governing Specification:
    PA.pdf Section 3.2.6, Equations (3.37)–(3.53), pages 30–33 (Privacy Amplification using SHA-256).
    PA.pdf Section 3.2.8.c, Equation (3.64), page 35 (Key Agreement Rate).
    FIPS PUB 180-4: Secure Hash Standard (SHS) for SHA-256 specification.

Mathematical Formulation:
    1. Bit-level Padding (Section 3.2.6, Equations 3.37–3.39):
       Given an unpadded bitstream M in {0, 1}^L of arbitrary length L:
           M' = M || 1 || 0^p || [L]_64
       where p is the smallest non-negative integer satisfying:
           L + 1 + p = 448 (mod 512)   ==>   p = (448 - 1 - L) mod 512
       and [L]_64 is the 64-bit big-endian binary representation of integer L.
       Total padded length |M'| = L + 1 + p + 64 = N * 512 bits.

    2. Message Scheduling (Section 3.2.6, Equations 3.40–3.43):
       Each 512-bit block is parsed into sixteen 32-bit big-endian words W_0 .. W_15.
       Words W_16 .. W_63 are generated via:
           sigma_0(x) = ROTR^7(x) XOR ROTR^18(x) XOR SHR^3(x)   (Eq 3.40)
           sigma_1(x) = ROTR^17(x) XOR ROTR^19(x) XOR SHR^10(x) (Eq 3.42)
           W_t = (sigma_1(W_{t-2}) + W_{t-7} + sigma_0(W_{t-15}) + W_{t-16}) mod 2^32 (Eq 3.43)

    3. 64-Round Compression Loop (Section 3.2.6, Equations 3.44–3.53):
       Functions on 32-bit words:
           Ch(x, y, z) = (x AND y) XOR (NOT x AND z)            (Eq 3.44)
           Maj(x, y, z) = (x AND y) XOR (x AND z) XOR (y AND z) (Eq 3.45)
           Sigma_0(x) = ROTR^2(x) XOR ROTR^13(x) XOR ROTR^22(x) (Eq 3.46)
           Sigma_1(x) = ROTR^6(x) XOR ROTR^11(x) XOR ROTR^25(x) (Eq 3.47)
       Round update for t = 0 .. 63:
           T1 = (h + Sigma_1(e) + Ch(e, f, g) + K_t + W_t) mod 2^32 (Eq 3.48)
           T2 = (Sigma_0(a) + Maj(a, b, c)) mod 2^32                (Eq 3.49)
           h = g; g = f; f = e; e = (d + T1) mod 2^32
           d = c; c = b; b = a; a = (T1 + T2) mod 2^32
       Intermediate hash update:
           H_j^(i) = (H_j^(i-1) + {a..h}_j) mod 2^32

    4. Final 256-bit Secret Key:
       K = H_0 || H_1 || ... || H_7 (256 bits, represented as 256-char binary string and 64-char hex digest).

Supported Paths:
    Strictly restricted to the two reconciled paths:
    1. quant_2bit (L = 1,000 bits)
    2. prbs_2bit  (L = 1,500 bits)

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
    EVALUATION_PAIRS,
    MultiPathReconciliationResult,
    PairReconciliationResult,
    PATHS,
)

SCIENTIFIC_DISCLAIMER: str = (
    "Synthetic software validation only; 256-bit SHA-256 output does not imply "
    "256 bits of physical entropy when upstream PRBS expansion is deterministic "
    "and public BCH helper data leaks parity relations. An attacker recovering "
    "source bits algebraically from helper data can compute the identical SHA-256 digest; "
    "~50% Post-PA KAR under ordinary decoding failure does not establish empirical secrecy."
)

# SHA-256 Round Constants K_0 .. K_63 (first 32 bits of fractional parts of cube roots of first 64 primes)
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

# Initial Hash Values H^(0) (first 32 bits of fractional parts of square roots of first 8 primes)
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
# Bit-level Padding and SHA-256 Engine
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
    # p is the smallest non-negative integer such that (L + 1 + p) % 512 == 448
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
    supported_paths: tuple[str, ...] = PATHS
    scientific_disclaimer: str = SCIENTIFIC_DISCLAIMER

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert configuration to metadata dictionary."""
        return {
            "algorithm": "Privacy Amplification via Bit-Level SHA-256",
            "hash_algorithm": self.hash_algorithm,
            "key_length_bits": self.key_length_bits,
            "supported_paths": list(self.supported_paths),
            "governing_specification": {
                "privacy_amplification": "PA.pdf Section 3.2.6, Equations (3.37)–(3.53), pages 30–33",
                "key_agreement_rate": "PA.pdf Section 3.2.8.c, Equation (3.64), page 35",
                "standard": "FIPS PUB 180-4 Secure Hash Standard (SHS)",
            },
            "scientific_disclaimer": self.scientific_disclaimer,
        }


@dataclass(frozen=True)
class ChannelPrivacyAmplificationResult:
    """Container holding derived secret key for a single communication channel."""

    path_name: str
    channel_name: str
    channel_role: str
    input_bit_length: int
    key_bin: str
    key_hex: str


@dataclass(frozen=True)
class PairPrivacyAmplificationResult:
    """Container holding privacy amplification evaluation between a channel pair."""

    path_name: str
    pair_name: str
    source_name: str
    receiver_name: str
    is_legitimate: bool
    input_bit_length: int
    source_key_bin: str
    source_key_hex: str
    receiver_key_bin: str
    receiver_key_hex: str
    pre_pa_kar: float
    post_pa_kar: float
    exact_key_match: bool
    mismatched_key_bits: int

    @property
    def kar_delta(self) -> float:
        """Change in KAR from pre-PA to post-PA (in percentage points)."""
        return self.post_pa_kar - self.pre_pa_kar


@dataclass
class MultiPathPrivacyAmplificationResult:
    """Master container holding Privacy Amplification results across both paths and all pairs."""

    config: PrivacyAmplificationConfig
    channel_keys: dict[str, dict[str, ChannelPrivacyAmplificationResult]]
    pair_results: dict[str, dict[str, PairPrivacyAmplificationResult]]
    figure_paths: tuple[Path, Path] | None = None

    @property
    def metrics(self) -> list[PairPrivacyAmplificationResult]:
        """Return flattened list of pair results in canonical order."""
        res: list[PairPrivacyAmplificationResult] = []
        for path_name in PATHS:
            if path_name in self.pair_results:
                for pair_info in EVALUATION_PAIRS:
                    pair_name = pair_info[2]
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
    """Execute Stage 6 Privacy Amplification across both reconciled 2-bit paths.

    Computes 256-bit secret keys for all 4 channels independently:
        - Alice (source)
        - Bob (recovered from Alice's helper data)
        - Eve1-Alice (recovered from Alice's helper data)
        - Eve1-Bob (recovered from Bob's helper data)

    Evaluates metrics across the 3 evaluation pairs:
        1. Alice–Bob (legitimate)
        2. Alice–Eve1-Alice (eavesdropper)
        3. Bob–Eve1-Bob (eavesdropper)

    Args:
        reconcile_result: Completed MultiPathReconciliationResult from Stage 5.
        config: PrivacyAmplificationConfig instance (uses defaults if None).

    Returns:
        MultiPathPrivacyAmplificationResult: Master container holding all keys and metrics.
    """
    cfg = config if config is not None else PrivacyAmplificationConfig()

    channel_keys: dict[str, dict[str, ChannelPrivacyAmplificationResult]] = {}
    pair_results: dict[str, dict[str, PairPrivacyAmplificationResult]] = {}

    for path_name in PATHS:
        if path_name not in reconcile_result.path_results:
            continue

        p_pairs = reconcile_result.path_results[path_name]
        res_ab = p_pairs["Alice–Bob"]
        res_ea = p_pairs["Alice–Eve1-Alice"]
        res_eb = p_pairs["Bob–Eve1-Bob"]

        # Derive independent 256-bit keys for all 4 channels
        # Alice: Alice unpadded source bitstream
        alice_bin, alice_hex = sha256_bitstream(res_ab.source_unpadded)
        # Bob: Bob recovered bitstream from Alice–Bob reconciliation
        bob_bin, bob_hex = sha256_bitstream(res_ab.recovered_unpadded)
        # Eve1-Alice: Eve1-Alice recovered bitstream from Alice–Eve1-Alice reconciliation
        ea_bin, ea_hex = sha256_bitstream(res_ea.recovered_unpadded)
        # Eve1-Bob: Eve1-Bob recovered bitstream from Bob–Eve1-Bob reconciliation
        eb_bin, eb_hex = sha256_bitstream(res_eb.recovered_unpadded)

        # Bob raw source key (for Bob–Eve1-Bob pair evaluation)
        bob_src_bin, bob_src_hex = sha256_bitstream(res_eb.source_unpadded)

        channel_keys[path_name] = {
            "Alice": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Alice",
                channel_role="Legitimate Source",
                input_bit_length=len(res_ab.source_unpadded),
                key_bin=alice_bin,
                key_hex=alice_hex,
            ),
            "Bob": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Bob",
                channel_role="Legitimate Receiver (Reconciled to Alice)",
                input_bit_length=len(res_ab.recovered_unpadded),
                key_bin=bob_bin,
                key_hex=bob_hex,
            ),
            "Bob (Source)": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Bob (Source)",
                channel_role="Transmitter / Source in Bob–Eve1-Bob",
                input_bit_length=len(res_eb.source_unpadded),
                key_bin=bob_src_bin,
                key_hex=bob_src_hex,
            ),
            "Eve1-Alice": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Eve1-Alice",
                channel_role="Eavesdropper (Overhearing Alice)",
                input_bit_length=len(res_ea.recovered_unpadded),
                key_bin=ea_bin,
                key_hex=ea_hex,
            ),
            "Eve1-Bob": ChannelPrivacyAmplificationResult(
                path_name=path_name,
                channel_name="Eve1-Bob",
                channel_role="Eavesdropper (Overhearing Bob)",
                input_bit_length=len(res_eb.recovered_unpadded),
                key_bin=eb_bin,
                key_hex=eb_hex,
            ),
        }

        # Evaluate pairs per PA.pdf Eq (3.64)
        def evaluate_pa_pair(
            pair_name: str,
            source_name: str,
            receiver_name: str,
            is_legitimate: bool,
            recon_res: PairReconciliationResult,
            s_bin: str,
            s_hex: str,
            r_bin: str,
            r_hex: str,
        ) -> PairPrivacyAmplificationResult:
            pre_kar = recon_res.post_reconcile_kar  # Reconciled bitstream KAR is pre-PA input
            mismatches = sum(1 for a, b in zip(s_bin, r_bin) if a != b)
            post_kar = ((256 - mismatches) / 256.0) * 100.0
            exact_match = (s_bin == r_bin)

            return PairPrivacyAmplificationResult(
                path_name=path_name,
                pair_name=pair_name,
                source_name=source_name,
                receiver_name=receiver_name,
                is_legitimate=is_legitimate,
                input_bit_length=recon_res.original_length,
                source_key_bin=s_bin,
                source_key_hex=s_hex,
                receiver_key_bin=r_bin,
                receiver_key_hex=r_hex,
                pre_pa_kar=pre_kar,
                post_pa_kar=post_kar,
                exact_key_match=exact_match,
                mismatched_key_bits=mismatches,
            )

        pair_ab = evaluate_pa_pair(
            pair_name="Alice–Bob",
            source_name="Alice",
            receiver_name="Bob",
            is_legitimate=True,
            recon_res=res_ab,
            s_bin=alice_bin,
            s_hex=alice_hex,
            r_bin=bob_bin,
            r_hex=bob_hex,
        )
        pair_ea = evaluate_pa_pair(
            pair_name="Alice–Eve1-Alice",
            source_name="Alice",
            receiver_name="Eve1-Alice",
            is_legitimate=False,
            recon_res=res_ea,
            s_bin=alice_bin,
            s_hex=alice_hex,
            r_bin=ea_bin,
            r_hex=ea_hex,
        )
        pair_eb = evaluate_pa_pair(
            pair_name="Bob–Eve1-Bob",
            source_name="Bob",
            receiver_name="Eve1-Bob",
            is_legitimate=False,
            recon_res=res_eb,
            s_bin=bob_src_bin,
            s_hex=bob_src_hex,
            r_bin=eb_bin,
            r_hex=eb_hex,
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
    """Export privacy amplification summary metrics to CSV.

    Columns:
        path, pair, source, receiver, is_legitimate, input_bits, key_bits,
        pre_pa_kar_percent, post_pa_kar_percent, kar_delta_pp,
        exact_key_match, mismatched_key_bits, source_key_hex, receiver_key_hex
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
        "key_bits",
        "pre_pa_kar_percent",
        "post_pa_kar_percent",
        "kar_delta_pp",
        "exact_key_match",
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
                    "key_bits": 256,
                    "pre_pa_kar_percent": round(p_res.pre_pa_kar, 4),
                    "post_pa_kar_percent": round(p_res.post_pa_kar, 4),
                    "kar_delta_pp": round(p_res.kar_delta, 4),
                    "exact_key_match": "TRUE" if p_res.exact_key_match else "FALSE",
                    "source_key_hex": p_res.source_key_hex,
                    "receiver_key_hex": p_res.receiver_key_hex,
                }
            )
    return out


def export_pa_keys_csv(
    pa_result: MultiPathPrivacyAmplificationResult,
    output_path: str | Path,
) -> Path:
    """Export channel secret keys to CSV (binary string and hex digest).

    Columns:
        path, channel, channel_role, input_bits, key_bits, key_hex, key_bin
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "path",
        "channel",
        "channel_role",
        "input_bits",
        "key_bits",
        "key_hex",
        "key_bin",
    ]

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for path_name, channels in pa_result.channel_keys.items():
            for ch_name, k_res in channels.items():
                writer.writerow(
                    {
                        "path": path_name,
                        "channel": ch_name,
                        "channel_role": k_res.channel_role,
                        "input_bits": k_res.input_bit_length,
                        "key_bits": 256,
                        "key_hex": k_res.key_hex,
                        "key_bin": k_res.key_bin,
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
                "key_length_bits": 256,
                "pre_pa_kar_percent": round(res.pre_pa_kar, 4),
                "post_pa_kar_percent": round(res.post_pa_kar, 4),
                "kar_delta_pp": round(res.kar_delta, 4),
                "exact_key_match": res.exact_key_match,
                "mismatched_key_bits": res.mismatched_key_bits,
                "source_key_hex": res.source_key_hex,
                "receiver_key_hex": res.receiver_key_hex,
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
        1. PA Metrics: Pre-PA vs Post-PA KAR and key match status across 2 paths x 3 pairs.
        2. Channel Keys: 256-bit binary strings and 64-char hex digests for all 4 channels.
        3. Config & Disclaimers: Full methodology, parameter tracking, and scientific disclaimers.
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

    # Sheet 1: PA Metrics
    ws1 = wb.active
    ws1.title = "PA Metrics"
    headers1 = [
        "Path",
        "Pair",
        "Legitimate",
        "Input Bits",
        "Key Bits",
        "Pre-PA KAR (%)",
        "Post-PA KAR (%)",
        "Delta (pp)",
        "Exact Key Match",
        "Source Key Hex",
        "Receiver Key Hex",
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
                256,
                round(p_res.pre_pa_kar, 4),
                round(p_res.post_pa_kar, 4),
                round(p_res.kar_delta, 4),
                "TRUE" if p_res.exact_key_match else "FALSE",
                p_res.source_key_hex,
                p_res.receiver_key_hex,
            ]
        )
        for c_idx in range(1, len(headers1) + 1):
            c = ws1.cell(row=r1_idx, column=c_idx)
            if c_idx in (10, 11):
                c.font = mono_font
                c.data_type = "s"
                c.number_format = "@"
                c.alignment = left_align
            else:
                c.font = data_font
                c.alignment = center_align
        r1_idx += 1

    # Sheet 2: Channel Keys
    ws2 = wb.create_sheet(title="Channel Keys")
    headers2 = ["Path", "Channel", "Channel Role", "Input Bits", "Key Bits", "Key Hex (64-char)", "Key Binary (256-bit)"]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    r2_idx = 2
    for path_name, channels in pa_result.channel_keys.items():
        for ch_name, k_res in channels.items():
            ws2.append(
                [
                    path_name,
                    ch_name,
                    k_res.channel_role,
                    k_res.input_bit_length,
                    256,
                    k_res.key_hex,
                    k_res.key_bin,
                ]
            )
            for c_idx in range(1, len(headers2) + 1):
                c = ws2.cell(row=r2_idx, column=c_idx)
                if c_idx in (6, 7):
                    c.font = mono_font
                    c.data_type = "s"
                    c.number_format = "@"
                    c.alignment = left_align
                else:
                    c.font = data_font
                    c.alignment = center_align
            r2_idx += 1

    # Sheet 3: Config & Disclaimers
    ws3 = wb.create_sheet(title="Config & Disclaimers")
    ws3.append(["Parameter / Property", "Value / Description"])
    ws3.cell(row=1, column=1).fill = header_fill
    ws3.cell(row=1, column=1).font = header_font
    ws3.cell(row=1, column=2).fill = header_fill
    ws3.cell(row=1, column=2).font = header_font

    cfg_rows = [
        ("Algorithm", "Bit-Level SHA-256 Privacy Amplification"),
        ("Standard Specification", "FIPS PUB 180-4 (Secure Hash Standard) / PA.pdf Section 3.2.6"),
        ("Key Agreement Rate Metric", "PA.pdf Section 3.2.8.c, Equation (3.64)"),
        ("Output Key Length", "256 bits (32 bytes / 64 hexadecimal characters)"),
        ("Supported Paths", "quant_2bit (1,000 bits) and prbs_2bit (1,500 bits)"),
        ("Evaluated Channels", "Alice, Bob, Eve1-Alice, Eve1-Bob"),
        ("Evaluated Pairs", "Alice–Bob (legitimate), Alice–Eve1-Alice (eavesdropper), Bob–Eve1-Bob (eavesdropper)"),
        ("Scientific Disclaimer", pa_result.config.scientific_disclaimer),
    ]

    for r_idx, (prop, val) in enumerate(cfg_rows, 2):
        ws3.append([prop, val])
        ws3.cell(row=r_idx, column=1).font = data_font
        ws3.cell(row=r_idx, column=1).alignment = left_align
        c_val = ws3.cell(row=r_idx, column=2)
        c_val.font = data_font
        c_val.alignment = left_align
        if "Disclaimer" in prop:
            c_val.fill = notice_fill
            c_val.font = notice_font

    # Adjust column widths
    for ws in [ws1, ws2, ws3]:
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 70)

    wb.save(out)
    return out

