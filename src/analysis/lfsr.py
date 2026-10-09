"""
lfsr.py

Pure Galois Linear Feedback Shift Register (LFSR) PRBS bit expansion module
for the Physical Layer Secret Key Generation (SKG) pipeline (Milestone D04.0).

Scientific References & Fidelity:
1. Vimalathithan, R., Rossi, D., Omana, M., Metra, C., & Valarmathi, M. L. (2013).
   "Polynomial Based Key Distribution Scheme for WPAN."
   Malaysian Journal of Mathematical Sciences, 7(S), pp. 59-72.
   - Section 2 (pp. 62-63): Key generation with LFSR, primitive polynomials, period 2^L - 1,
     and reciprocal polynomial properties.
   - Section 4 (pp. 66-67): Polynomial-based key distribution scheme.
     NOTE ON REFERENCE FIDELITY: The paper's 16->128 expansion repeats the rolling code
     sequence 8 times, and its 128-bit Galois LFSR then generates the key.
     The repetition is NOT an LFSR expansion. In D04.0, we use a pure Galois LFSR
     to expand quantization seeds directly without artificial repetition, hashing,
     scrambling, or nonlinear functions.
2. Menezes, A. J., van Oorschot, P. C., & Vanstone, S. A. (1996).
   "Handbook of Applied Cryptography." CRC Press, Chapter 6 (Stream Ciphers, Section 6.2.2).
3. Xilinx Application Note XAPP052 (v1.1):
   "Efficient Shift Registers, LFSR Counters, and Long Pseudo-Random Sequence Generators."
   Table 3: Taps for degree-32 primitive polynomial: taps {32, 22, 2, 1, 0}.
4. Stahnke, W. C. (1973).
   "Primitive Binary Polynomials of Degree n." Mathematics of Computation, 27(124), pp. 977-980.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


# Degree-2 verified primitive polynomial:
# P(x) = x^2 + x^1 + 1 (taps: 2, 1, 0)
# Period: 2^2 - 1 = 3, tap mask: (1 << 1) | (1 << 0) = 0x3
DEGREE_2 = 2
DEGREE_2_TAPS = (2, 1, 0)
DEGREE_2_TAP_MASK = 0x3

# Degree-4 verified primitive polynomial:
# P(x) = x^4 + x^1 + 1 (taps: 4, 1, 0)
# Period: 2^4 - 1 = 15, tap mask: (1 << 1) | (1 << 0) = 0x3
DEGREE_4 = 4
DEGREE_4_TAPS = (4, 1, 0)
DEGREE_4_TAP_MASK = 0x3

# Historical verified degree-32 primitive polynomial:
# P(x) = x^32 + x^22 + x^2 + x^1 + 1
# Source: Xilinx Application Note XAPP052, Table 3 / Stahnke (1973)
DEFAULT_DEGREE = 32
DEFAULT_POLYNOMIAL_TAPS = (32, 22, 2, 1, 0)
DEFAULT_TAP_MASK = 0x00400007  # (1 << 22) | (1 << 2) | (1 << 1) | (1 << 0)


def taps_to_tap_mask(
    taps: Sequence[int],
    degree: int,
    shift_direction: str = "left",
) -> int:
    """
    Convert polynomial tap exponents into an integer bitmask.

    Convention:
    A monic polynomial P(x) = x^L + c_{L-1}*x^{L-1} + ... + c_1*x + c_0 is given by tap
    exponents where c_i = 1.
    For degree L, the leading term x^L defines the register length.
    - Left-shift Galois LFSR (multiplication by x in GF(2^L) / P(x)):
      When bit (L-1) is shifted out, it wraps around to the lower coefficients.
      tap_mask = sum(1 << i for i in taps if 0 <= i < degree).
      For P(x) = x^32 + x^22 + x^2 + x + 1:
      tap_mask = 2^22 + 2^2 + 2^1 + 2^0 = 0x00400007.
    - Right-shift Galois LFSR:
      When bit 0 is shifted out, it feeds back into the MSB and intermediate taps:
      tap_mask = (1 << (degree - 1)) | sum(1 << (degree - 1 - i) for i in taps if 0 < i < degree).

    Args:
        taps: Exponents of non-zero terms, e.g. (32, 22, 2, 1, 0).
        degree: Degree of the polynomial (L).
        shift_direction: 'left' or 'right'.

    Returns:
        Integer bitmask representing the feedback taps.
    """
    if degree not in taps and max(taps) != degree:
        raise ValueError(f"Taps {taps} do not include the degree term x^{degree}.")

    if shift_direction.lower() == "left":
        mask = 0
        for p in taps:
            if 0 <= p < degree:
                mask |= (1 << p)
        return mask
    elif shift_direction.lower() == "right":
        # Right shift feedback mask: bit (degree - 1) is always set, plus internal taps
        mask = (1 << (degree - 1))
        for p in taps:
            if 0 < p < degree:
                # In right shift, tap p corresponds to bit (degree - p - 1)
                mask |= (1 << (degree - 1 - p))
        return mask
    else:
        raise ValueError(f"Unsupported shift direction: '{shift_direction}'. Must be 'left' or 'right'.")


class GaloisLFSR:
    """
    Pure Galois Linear Feedback Shift Register (LFSR).

    In a Galois LFSR (modular LFSR), feedback is applied simultaneously to internal flip-flops
    rather than collecting taps through an external XOR tree (Fibonacci LFSR).
    This architecture enables high-speed single-cycle operation in hardware and direct
    representation of polynomial multiplication in Galois fields GF(2^L).

    Key Specifications:
    - Register width: L bits (configurable, default: 32).
    - Primitive polynomial: Configurable via taps or tap mask (default: x^32 + x^22 + x^2 + x + 1).
    - Shift direction: 'left' (default) or 'right'.
    - Output bit: 'msb' (default for left) or 'lsb' (default for right).
    - Output timing: 'before_update' (default) or 'after_update'.
    - Seed bit order: 'msb_first' (default) or 'lsb_first'.
    """

    def __init__(
        self,
        degree: int = DEFAULT_DEGREE,
        polynomial_taps: Optional[Sequence[int]] = DEFAULT_POLYNOMIAL_TAPS,
        tap_mask: Optional[int] = None,
        shift_direction: str = "left",
        output_bit: Optional[str] = None,
        output_timing: str = "before_update",
        seed_bit_order: str = "msb_first",
    ) -> None:
        if degree < 2:
            raise ValueError(f"Degree must be at least 2, got {degree}.")

        self.degree = degree
        self.shift_direction = shift_direction.lower()
        if self.shift_direction not in ("left", "right"):
            raise ValueError(f"shift_direction must be 'left' or 'right', got '{shift_direction}'.")

        self.output_timing = output_timing.lower()
        if self.output_timing not in ("before_update", "after_update"):
            raise ValueError(f"output_timing must be 'before_update' or 'after_update', got '{output_timing}'.")

        self.seed_bit_order = seed_bit_order.lower()
        if self.seed_bit_order not in ("msb_first", "lsb_first"):
            raise ValueError(f"seed_bit_order must be 'msb_first' or 'lsb_first', got '{seed_bit_order}'.")

        if output_bit is None:
            self.output_bit = "msb" if self.shift_direction == "left" else "lsb"
        else:
            self.output_bit = output_bit.lower()
            if self.output_bit not in ("msb", "lsb"):
                raise ValueError(f"output_bit must be 'msb' or 'lsb', got '{output_bit}'.")

        self.full_mask = (1 << degree) - 1

        if tap_mask is not None:
            self.tap_mask = tap_mask & self.full_mask
            self.polynomial_taps = polynomial_taps
        elif polynomial_taps is not None:
            self.polynomial_taps = tuple(polynomial_taps)
            self.tap_mask = taps_to_tap_mask(self.polynomial_taps, degree, self.shift_direction)
        else:
            raise ValueError("Either polynomial_taps or tap_mask must be specified.")

        self.state: int = 0
        self.initial_seed: int = 0
        self.is_zero_seed: bool = True
        self.total_clocks: int = 0

    @property
    def is_zero_state(self) -> bool:
        """True if current register state is zero."""
        return self.state == 0

    def reset(self, seed: Union[int, str, Sequence[int]]) -> "GaloisLFSR":
        """
        Reset LFSR state with a new seed.

        Args:
            seed: Seed value provided as:
                - integer: directly loaded into register (modulo 2^degree).
                - binary string (e.g. '101001...'): parsed according to seed_bit_order.
                - sequence of bits (e.g. [1, 0, 1]): parsed according to seed_bit_order.

        Returns:
            self for chained operations.
        """
        parsed_seed: int = 0

        if isinstance(seed, str):
            clean_str = seed.strip()
            if not all(c in "01" for c in clean_str):
                raise ValueError(f"Invalid characters in binary seed string: '{clean_str}'. Only '0' and '1' allowed.")
            if len(clean_str) > self.degree:
                raise ValueError(f"Seed string length {len(clean_str)} exceeds register width {self.degree}.")
            if self.seed_bit_order == "msb_first":
                parsed_seed = int(clean_str, 2) if clean_str else 0
            else:
                parsed_seed = sum(int(b) << i for i, b in enumerate(clean_str))
        elif isinstance(seed, (int, np.integer)):
            if seed < 0:
                raise ValueError(f"Seed integer cannot be negative: {seed}.")
            parsed_seed = int(seed) & self.full_mask
        elif isinstance(seed, (list, tuple, np.ndarray)):
            bit_list = [int(b) for b in seed]
            if not all(b in (0, 1) for b in bit_list):
                raise ValueError("All elements in seed sequence must be 0 or 1.")
            if len(bit_list) > self.degree:
                raise ValueError(f"Seed sequence length {len(bit_list)} exceeds register width {self.degree}.")
            if self.seed_bit_order == "msb_first":
                parsed_seed = int("".join(str(b) for b in bit_list), 2) if bit_list else 0
            else:
                parsed_seed = sum(b << i for i, b in enumerate(bit_list))
        else:
            raise TypeError(f"Unsupported seed type: {type(seed)}.")

        self.initial_seed = parsed_seed & self.full_mask
        self.state = self.initial_seed
        self.is_zero_seed = (self.initial_seed == 0)
        self.total_clocks = 0
        return self

    def _extract_output_bit(self, state: int) -> int:
        """Extract the designated output bit from given state."""
        if self.output_bit == "msb":
            return (state >> (self.degree - 1)) & 1
        else:
            return state & 1

    def step(self) -> int:
        """
        Advance the LFSR by 1 clock cycle and return the generated output bit.

        Returns:
            Generated bit (0 or 1).
        """
        if self.state == 0:
            # In a pure Galois LFSR, state 0 is an absorbing degenerate state.
            # Shifting 0 produces 0 without transitions.
            self.total_clocks += 1
            return 0

        if self.output_timing == "before_update":
            out_bit = self._extract_output_bit(self.state)

            if self.shift_direction == "left":
                msb = (self.state >> (self.degree - 1)) & 1
                if msb == 1:
                    self.state = ((self.state << 1) & self.full_mask) ^ self.tap_mask
                else:
                    self.state = (self.state << 1) & self.full_mask
            else:  # right
                lsb = self.state & 1
                if lsb == 1:
                    self.state = (self.state >> 1) ^ self.tap_mask
                else:
                    self.state = self.state >> 1

            self.total_clocks += 1
            return out_bit

        else:  # after_update
            if self.shift_direction == "left":
                msb = (self.state >> (self.degree - 1)) & 1
                if msb == 1:
                    self.state = ((self.state << 1) & self.full_mask) ^ self.tap_mask
                else:
                    self.state = (self.state << 1) & self.full_mask
            else:  # right
                lsb = self.state & 1
                if lsb == 1:
                    self.state = (self.state >> 1) ^ self.tap_mask
                else:
                    self.state = self.state >> 1

            out_bit = self._extract_output_bit(self.state)
            self.total_clocks += 1
            return out_bit

    def generate(self, length: int) -> str:
        """
        Generate a pseudorandom binary sequence of specified length.

        Args:
            length: Number of bits to generate.

        Returns:
            Binary string of length `length`.
        """
        if length < 0:
            raise ValueError(f"Generation length cannot be negative: {length}.")
        if length == 0:
            return ""

        bits = [str(self.step()) for _ in range(length)]
        return "".join(bits)

    def generate_bits(self, length: int) -> List[int]:
        """
        Generate a list of integer bits [0, 1, ...].

        Args:
            length: Number of bits to generate.

        Returns:
            List of integers (0 or 1).
        """
        if length < 0:
            raise ValueError(f"Generation length cannot be negative: {length}.")
        return [self.step() for _ in range(length)]


@dataclass
class BlockExpansionDetail:
    """Detailed record of a single block's LFSR expansion."""
    block_index: int
    seed_string: str
    seed_int: int
    is_zero_seed: bool
    output_length: int
    expanded_string: str


@dataclass
class ExpansionResult:
    """Comprehensive result of expanding a complete bitstream."""
    total_input_bits: int
    consumed_input_bits: int
    unconsumed_input_bits: int
    num_full_blocks: int
    seed_length: int
    output_length_per_block: int
    expansion_ratio: float
    block_coverage_pct: float
    zero_seed_block_indices: List[int]
    zero_seed_count: int
    partial_block_string: str
    partial_handling: str
    expanded_bitstream: str
    total_expanded_bits: int
    blocks: List[BlockExpansionDetail] = field(default_factory=list)

    def to_dict(self, include_blocks: bool = False) -> Dict[str, Any]:
        """Serialize expansion summary to dictionary."""
        d: Dict[str, Any] = {
            "total_input_bits": self.total_input_bits,
            "consumed_input_bits": self.consumed_input_bits,
            "unconsumed_input_bits": self.unconsumed_input_bits,
            "num_full_blocks": self.num_full_blocks,
            "seed_length": self.seed_length,
            "output_length_per_block": self.output_length_per_block,
            "expansion_ratio": round(self.expansion_ratio, 4),
            "block_coverage_pct": round(self.block_coverage_pct, 4),
            "zero_seed_count": self.zero_seed_count,
            "zero_seed_block_indices": self.zero_seed_block_indices,
            "partial_block_length": len(self.partial_block_string),
            "partial_handling": self.partial_handling,
            "total_expanded_bits": self.total_expanded_bits,
        }
        if include_blocks:
            d["blocks"] = [
                {
                    "block_index": b.block_index,
                    "seed_string": b.seed_string,
                    "seed_int": b.seed_int,
                    "is_zero_seed": b.is_zero_seed,
                    "output_length": b.output_length,
                    "expanded_string": b.expanded_string,
                }
                for b in self.blocks
            ]
        return d


def expand_bitstream_blocks(
    bitstream: str,
    seed_length: int = 32,
    output_length: int = 64,
    lfsr: Optional[GaloisLFSR] = None,
    partial_handling: str = "exclude",
) -> ExpansionResult:
    """
    Divide bitstream into non-overlapping seed_length blocks, reset LFSR per block,
    and expand each block into output_length bits.

    Args:
        bitstream: Input binary string containing only '0' and '1'.
        seed_length: Length of seed blocks (default: 32).
        output_length: Number of output bits generated per seed block.
        lfsr: Pre-configured GaloisLFSR instance. If None, default degree-32 LFSR is created.
        partial_handling: How to treat residual bits when len(bitstream) % seed_length != 0.
            - 'exclude': Exclude partial block from LFSR expansion (default, preserved provenance).

    Returns:
        ExpansionResult detailing coverage, zero seeds, and expanded bits.
    """
    clean_bits = bitstream.strip()
    if not all(c in "01" for c in clean_bits):
        raise ValueError("Input bitstream must contain only '0' and '1'.")

    if lfsr is None:
        lfsr = GaloisLFSR(degree=seed_length)
    elif lfsr.degree != seed_length:
        raise ValueError(f"LFSR degree {lfsr.degree} does not match seed length {seed_length}.")

    total_input_bits = len(clean_bits)
    num_full_blocks = total_input_bits // seed_length
    remainder = total_input_bits % seed_length
    partial_bits = clean_bits[num_full_blocks * seed_length:] if remainder > 0 else ""

    blocks: List[BlockExpansionDetail] = []
    zero_seed_indices: List[int] = []
    expanded_blocks: List[str] = []

    for b_idx in range(num_full_blocks):
        block_seed = clean_bits[b_idx * seed_length: (b_idx + 1) * seed_length]
        is_zero = (block_seed == "0" * seed_length)
        if is_zero:
            zero_seed_indices.append(b_idx)

        # Reset LFSR independently per block with clean state isolation
        lfsr.reset(block_seed)
        expanded_str = lfsr.generate(output_length)
        expanded_blocks.append(expanded_str)

        blocks.append(
            BlockExpansionDetail(
                block_index=b_idx,
                seed_string=block_seed,
                seed_int=lfsr.initial_seed,
                is_zero_seed=is_zero,
                output_length=output_length,
                expanded_string=expanded_str,
            )
        )

    consumed_bits = num_full_blocks * seed_length
    unconsumed_bits = len(partial_bits)
    total_expanded_bits = len(expanded_blocks) * output_length
    expansion_ratio = total_expanded_bits / consumed_bits if consumed_bits > 0 else 0.0
    block_coverage_pct = (consumed_bits / total_input_bits * 100.0) if total_input_bits > 0 else 0.0

    return ExpansionResult(
        total_input_bits=total_input_bits,
        consumed_input_bits=consumed_bits,
        unconsumed_input_bits=unconsumed_bits,
        num_full_blocks=num_full_blocks,
        seed_length=seed_length,
        output_length_per_block=output_length,
        expansion_ratio=expansion_ratio,
        block_coverage_pct=block_coverage_pct,
        zero_seed_block_indices=zero_seed_indices,
        zero_seed_count=len(zero_seed_indices),
        partial_block_string=partial_bits,
        partial_handling=partial_handling,
        expanded_bitstream="".join(expanded_blocks),
        total_expanded_bits=total_expanded_bits,
        blocks=blocks,
    )


def compute_expansion_agreement_metrics(
    exp_a: ExpansionResult,
    exp_b: ExpansionResult,
    label_a: str = "Alice",
    label_b: str = "Bob",
) -> Dict[str, Any]:
    """
    Compute pre-expansion and post-expansion agreement metrics between two independent channels.

    Evaluates:
    - Pre-expansion seed agreement on consumed blocks (KAR and BER).
    - Seed block-level exact match count and percentage.
    - Post-expansion bit agreement on all generated bits (KAR and BER).
    - Post-expansion bit agreement excluding zero-seed blocks (to isolate pseudo-random diffusion).
    - Zero seed coincidence (both zero, one zero, neither zero).

    Args:
        exp_a: ExpansionResult for node A.
        exp_b: ExpansionResult for node B.
        label_a: Node A name.
        label_b: Node B name.

    Returns:
        Structured dictionary of agreement metrics.
    """
    if exp_a.num_full_blocks != exp_b.num_full_blocks:
        raise ValueError(f"Block count mismatch: {exp_a.num_full_blocks} vs {exp_b.num_full_blocks}.")

    n_blocks = exp_a.num_full_blocks
    out_len = exp_a.output_length_per_block

    # 1. Pre-expansion bit comparison on consumed blocks (retained prefix)
    seeds_a = [b.seed_string for b in exp_a.blocks]
    seeds_b = [b.seed_string for b in exp_b.blocks]

    pre_bits_a = "".join(seeds_a)
    pre_bits_b = "".join(seeds_b)
    total_pre_bits = len(pre_bits_a)

    pre_matching_bits = sum(1 for a, b in zip(pre_bits_a, pre_bits_b) if a == b)
    pre_kar = pre_matching_bits / total_pre_bits if total_pre_bits > 0 else 0.0
    pre_ber = 1.0 - pre_kar

    # Omitted tail comparison
    tail_a = exp_a.partial_block_string
    tail_b = exp_b.partial_block_string
    total_tail_bits = len(tail_a)
    tail_matching_bits = sum(1 for a, b in zip(tail_a, tail_b) if a == b) if total_tail_bits > 0 else 0
    tail_kar = tail_matching_bits / total_tail_bits if total_tail_bits > 0 else 0.0
    tail_ber = 1.0 - tail_kar if total_tail_bits > 0 else 0.0

    # Full input stream comparison
    full_matching_bits = pre_matching_bits + tail_matching_bits
    total_full_bits = total_pre_bits + total_tail_bits
    full_kar = full_matching_bits / total_full_bits if total_full_bits > 0 else 0.0
    full_ber = 1.0 - full_kar

    # Seed block matches (exact 32-bit equality)
    seed_block_matches = sum(1 for sa, sb in zip(seeds_a, seeds_b) if sa == sb)
    seed_block_match_pct = (seed_block_matches / n_blocks * 100.0) if n_blocks > 0 else 0.0

    # 2. Post-expansion bit comparison on all blocks
    post_bits_a = exp_a.expanded_bitstream
    post_bits_b = exp_b.expanded_bitstream
    total_post_bits = len(post_bits_a)

    post_matching_bits = sum(1 for a, b in zip(post_bits_a, post_bits_b) if a == b)
    post_kar = post_matching_bits / total_post_bits if total_post_bits > 0 else 0.0
    post_ber = 1.0 - post_kar

    # Expanded block matches (exact output equality)
    exp_block_matches = sum(
        1 for ba, bb in zip(exp_a.blocks, exp_b.blocks) if ba.expanded_string == bb.expanded_string
    )

    # 3. Filtered metrics excluding blocks where either node had a zero seed
    non_zero_block_indices = [
        i for i in range(n_blocks)
        if (i not in exp_a.zero_seed_block_indices) and (i not in exp_b.zero_seed_block_indices)
    ]
    non_zero_blocks_count = len(non_zero_block_indices)

    if non_zero_blocks_count > 0:
        nz_pre_a = "".join(seeds_a[i] for i in non_zero_block_indices)
        nz_pre_b = "".join(seeds_b[i] for i in non_zero_block_indices)
        nz_pre_matches = sum(1 for a, b in zip(nz_pre_a, nz_pre_b) if a == b)
        nz_pre_kar = nz_pre_matches / len(nz_pre_a)

        nz_post_a = "".join(exp_a.blocks[i].expanded_string for i in non_zero_block_indices)
        nz_post_b = "".join(exp_b.blocks[i].expanded_string for i in non_zero_block_indices)
        nz_post_matches = sum(1 for a, b in zip(nz_post_a, nz_post_b) if a == b)
        nz_post_kar = nz_post_matches / len(nz_post_a)
        nz_post_ber = 1.0 - nz_post_kar
    else:
        nz_pre_kar = 0.0
        nz_post_kar = 0.0
        nz_post_ber = 1.0

    # 4. Zero seed analysis
    zero_coincidence = {
        "both_zero": len(set(exp_a.zero_seed_block_indices) & set(exp_b.zero_seed_block_indices)),
        f"{label_a}_only_zero": len(set(exp_a.zero_seed_block_indices) - set(exp_b.zero_seed_block_indices)),
        f"{label_b}_only_zero": len(set(exp_b.zero_seed_block_indices) - set(exp_a.zero_seed_block_indices)),
        "total_zero_blocks_union": len(set(exp_a.zero_seed_block_indices) | set(exp_b.zero_seed_block_indices)),
    }

    return {
        "channel_pair": f"{label_a} vs {label_b}",
        "total_blocks": n_blocks,
        "seed_length": exp_a.seed_length,
        "output_length": out_len,
        "seed_block_matches": seed_block_matches,
        "seed_block_match_pct": round(seed_block_match_pct, 4),
        "expanded_block_matches": exp_block_matches,
        "input_provenance_comparison": {
            "full_stream_input": {
                "total_bits": total_full_bits,
                "matching_bits": full_matching_bits,
                "mismatch_bits": total_full_bits - full_matching_bits,
                "kar": round(full_kar, 6),
                "ber": round(full_ber, 6),
            },
            "retained_prefix_input": {
                "consumed_bits": total_pre_bits,
                "matching_bits": pre_matching_bits,
                "mismatch_bits": total_pre_bits - pre_matching_bits,
                "kar": round(pre_kar, 6),
                "ber": round(pre_ber, 6),
            },
            "omitted_tail_input": {
                "tail_bits": total_tail_bits,
                "matching_bits": tail_matching_bits,
                "mismatch_bits": total_tail_bits - tail_matching_bits,
                "kar": round(tail_kar, 6),
                "ber": round(tail_ber, 6),
            },
        },
        "pre_expansion": {
            "consumed_bits": total_pre_bits,
            "matching_bits": pre_matching_bits,
            "mismatch_bits": total_pre_bits - pre_matching_bits,
            "kar": round(pre_kar, 6),
            "ber": round(pre_ber, 6),
        },
        "post_expansion_all_blocks": {
            "total_generated_bits": total_post_bits,
            "matching_bits": post_matching_bits,
            "mismatch_bits": total_post_bits - post_matching_bits,
            "kar": round(post_kar, 6),
            "ber": round(post_ber, 6),
        },
        "post_expansion_non_zero_blocks_only": {
            "evaluated_blocks": non_zero_blocks_count,
            "total_bits": non_zero_blocks_count * out_len,
            "pre_kar": round(nz_pre_kar, 6),
            "post_kar": round(nz_post_kar, 6),
            "post_ber": round(nz_post_ber, 6),
        },
        "zero_seed_coincidence": zero_coincidence,
    }


# ============================================================================
# Milestone D04.0: Active Per-Sample Pure Galois LFSR Expansion Architecture
# ============================================================================

@dataclass
class SampleExpansionDetail:
    """Expansion details for a single quantization sample."""
    sample_id: int
    seed_string: str
    seed_int: int
    is_zero_seed: bool
    expanded_string: str
    output_bits: List[int]


@dataclass
class PerSampleExpansionResult:
    """Summary of per-sample LFSR expansion for a complete channel bitstream."""
    channel: str
    bit_depth: str
    seed_length: int
    output_length: int
    expansion_ratio: float
    total_samples: int
    total_output_bits: int
    zero_seed_count: int
    zero_seed_pct: float
    samples: List[SampleExpansionDetail]
    expanded_bitstream: str
    zero_seed_sample_indices: List[int]


def create_sample_lfsr(seed_length: int) -> GaloisLFSR:
    """
    Create a configured Galois LFSR matching the per-sample seed bit depth.

    Specifications:
    - 2-bit seed: Degree 2, P(x) = x^2 + x + 1, taps (2, 1, 0), tap_mask 0x3, period 3.
    - 4-bit seed: Degree 4, P(x) = x^4 + x + 1, taps (4, 1, 0), tap_mask 0x3, period 15.
    - 32-bit seed (historical): Degree 32, P(x) = x^32 + x^22 + x^2 + x + 1, tap_mask 0x00400007.
    All use left-shift, MSB output before register update, and MSB-first seed bit order.
    """
    if seed_length == 2:
        return GaloisLFSR(
            degree=2,
            polynomial_taps=DEGREE_2_TAPS,
            shift_direction="left",
            output_bit="msb",
            output_timing="before_update",
            seed_bit_order="msb_first",
        )
    elif seed_length == 4:
        return GaloisLFSR(
            degree=4,
            polynomial_taps=DEGREE_4_TAPS,
            shift_direction="left",
            output_bit="msb",
            output_timing="before_update",
            seed_bit_order="msb_first",
        )
    elif seed_length == 32:
        return GaloisLFSR(
            degree=32,
            polynomial_taps=DEFAULT_POLYNOMIAL_TAPS,
            shift_direction="left",
            output_bit="msb",
            output_timing="before_update",
            seed_bit_order="msb_first",
        )
    else:
        raise ValueError(f"Unsupported seed length {seed_length} for per-sample Galois LFSR.")


def get_per_sample_symbol_mapping(
    bit_depth: str,
    output_length: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute deterministic input seed to output bitstream mapping for each of the
    three ADQ quantization levels, and calculate pairwise output Hamming distances.

    Default output length is full maximal-period sequence length m = 2^L - 1
    (3 bits for L=2, 15 bits for L=4).

    Levels:
    - 2-bit Gray coding: Level 0 = '00', Level 1 = '01', Level 2 = '11'.
    - 4-bit LoRa-PRIME:  Level 0 = '1010', Level 1 = '1011', Level 2 = '1001'.
    """
    clean_depth = bit_depth.lower().replace("-", "")
    if clean_depth in ("2bit", "2"):
        seed_len = 2
        out_len = ((1 << seed_len) - 1) if output_length is None else output_length
        symbols = [("Level 0", "00"), ("Level 1", "01"), ("Level 2", "11")]
        poly_str = "x^2 + x + 1"
        period = 3
    elif clean_depth in ("4bit", "4"):
        seed_len = 4
        out_len = ((1 << seed_len) - 1) if output_length is None else output_length
        symbols = [("Level 0", "1010"), ("Level 1", "1011"), ("Level 2", "1001")]
        poly_str = "x^4 + x + 1"
        period = 15
    else:
        raise ValueError(f"Unsupported bit depth: '{bit_depth}'. Must be '2bit' or '4bit'.")

    lfsr = create_sample_lfsr(seed_len)
    mapping: Dict[str, Any] = {}
    outputs: Dict[str, str] = {}

    for level_name, seed_str in symbols:
        lfsr.reset(seed_str)
        out_bits = [lfsr.step() for _ in range(out_len)]
        out_str = "".join(str(b) for b in out_bits)
        outputs[level_name] = out_str
        mapping[level_name] = {
            "seed_string": seed_str,
            "seed_int": int(seed_str, 2),
            "is_zero_seed": (int(seed_str, 2) == 0),
            "expanded_output": out_str,
            "output_length": out_len,
        }

    # Pairwise Hamming distances between symbol outputs
    level_names = [s[0] for s in symbols]
    pairwise_distances: Dict[str, Any] = {}
    for i in range(len(level_names)):
        for j in range(i + 1, len(level_names)):
            name_a, name_b = level_names[i], level_names[j]
            str_a, str_b = outputs[name_a], outputs[name_b]
            hd = sum(1 for a, b in zip(str_a, str_b) if a != b)
            pairwise_distances[f"{name_a} vs {name_b}"] = {
                "level_a": name_a,
                "seed_a": mapping[name_a]["seed_string"],
                "output_a": str_a,
                "level_b": name_b,
                "seed_b": mapping[name_b]["seed_string"],
                "output_b": str_b,
                "hamming_distance": hd,
                "relative_distance": round(hd / out_len, 4),
            }

    return {
        "bit_depth": bit_depth,
        "seed_length": seed_len,
        "output_length": out_len,
        "expansion_ratio": round(out_len / seed_len, 4),
        "polynomial": poly_str,
        "period": period,
        "symbols": mapping,
        "pairwise_hamming_distances": pairwise_distances,
    }


def expand_sample_sequences(
    seed_strings: Sequence[str],
    seed_length: int,
    output_length: Optional[int] = None,
    channel: str = "Unknown",
    bit_depth: str = "unknown",
    lfsr: Optional[GaloisLFSR] = None,
) -> PerSampleExpansionResult:
    """
    Expand a sequence of per-sample quantization seeds into pseudo-random bit sequences.

    For each sample:
    1. LFSR is explicitly reset with the sample's complete seed.
    2. Exactly output_length bits are generated (default: m = 2^L - 1).
    3. Zero seeds are preserved and flagged (is_zero_seed=True), generating all-zeros.
    4. No sample concatenation, padding, hashing, or scrambling is applied.

    Args:
        seed_strings: Sequence of seed strings (one per sample).
        seed_length: Bit length of each seed (2 for 2-bit, 4 for 4-bit).
        output_length: Number of output bits per sample (default: m = 2^seed_length - 1).
        channel: Channel label (e.g. 'Alice').
        bit_depth: Encoding label (e.g. '2bit').
        lfsr: Optional pre-configured GaloisLFSR instance.

    Returns:
        PerSampleExpansionResult containing all per-sample expansion details.
    """
    if output_length is None:
        output_length = (1 << seed_length) - 1

    if lfsr is None:
        lfsr = create_sample_lfsr(seed_length)

    samples_detail: List[SampleExpansionDetail] = []
    zero_seed_indices: List[int] = []

    for idx, raw_seed in enumerate(seed_strings):
        clean_seed = raw_seed.strip().replace("=", "").replace('"', "")
        if len(clean_seed) != seed_length:
            raise ValueError(
                f"Sample {idx} seed '{clean_seed}' length {len(clean_seed)} != expected {seed_length}."
            )

        seed_int = int(clean_seed, 2)
        is_zero = (seed_int == 0)
        if is_zero:
            zero_seed_indices.append(idx)

        # Reset LFSR before each sample
        lfsr.reset(clean_seed)
        output_bits = [lfsr.step() for _ in range(output_length)]
        expanded_str = "".join(str(b) for b in output_bits)

        samples_detail.append(
            SampleExpansionDetail(
                sample_id=idx,
                seed_string=clean_seed,
                seed_int=seed_int,
                is_zero_seed=is_zero,
                expanded_string=expanded_str,
                output_bits=output_bits,
            )
        )

    all_expanded_bits = "".join(s.expanded_string for s in samples_detail)
    total_samples = len(samples_detail)
    zero_count = len(zero_seed_indices)
    zero_pct = (zero_count / total_samples * 100.0) if total_samples > 0 else 0.0
    expansion_ratio = output_length / seed_length

    return PerSampleExpansionResult(
        channel=channel,
        bit_depth=bit_depth,
        seed_length=seed_length,
        output_length=output_length,
        expansion_ratio=round(expansion_ratio, 4),
        total_samples=total_samples,
        total_output_bits=len(all_expanded_bits),
        zero_seed_count=zero_count,
        zero_seed_pct=round(zero_pct, 4),
        samples=samples_detail,
        expanded_bitstream=all_expanded_bits,
        zero_seed_sample_indices=zero_seed_indices,
    )


def compute_per_sample_agreement_metrics(
    res_a: PerSampleExpansionResult,
    res_b: PerSampleExpansionResult,
    label_a: str = "Alice",
    label_b: str = "Bob",
) -> Dict[str, Any]:
    """
    Compute agreement metrics (KAR, BER) and mismatch breakdown between two channels
    for per-sample LFSR expansion.
    """
    if res_a.total_samples != res_b.total_samples:
        raise ValueError(f"Sample counts differ: {res_a.total_samples} vs {res_b.total_samples}")

    total_samples = res_a.total_samples
    seed_len = res_a.seed_length
    out_len = res_a.output_length

    # 1. Sample agreement (exact seed equality)
    sample_matches = sum(
        1 for sa, sb in zip(res_a.samples, res_b.samples) if sa.seed_string == sb.seed_string
    )
    sample_mismatches = total_samples - sample_matches
    sample_match_pct = (sample_matches / total_samples * 100.0) if total_samples > 0 else 0.0

    # Symbol mismatch classification
    mismatch_pairs: Dict[str, int] = {}
    for sa, sb in zip(res_a.samples, res_b.samples):
        if sa.seed_string != sb.seed_string:
            key = f"{sa.seed_string} vs {sb.seed_string}"
            mismatch_pairs[key] = mismatch_pairs.get(key, 0) + 1

    # 2. Pre-expansion bit comparison
    pre_bits_a = "".join(s.seed_string for s in res_a.samples)
    pre_bits_b = "".join(s.seed_string for s in res_b.samples)
    total_pre_bits = len(pre_bits_a)
    pre_matches = sum(1 for a, b in zip(pre_bits_a, pre_bits_b) if a == b)
    pre_mismatches = total_pre_bits - pre_matches
    pre_kar = pre_matches / total_pre_bits if total_pre_bits > 0 else 0.0
    pre_ber = 1.0 - pre_kar

    # 3. Post-expansion bit comparison
    post_bits_a = res_a.expanded_bitstream
    post_bits_b = res_b.expanded_bitstream
    total_post_bits = len(post_bits_a)
    post_matches = sum(1 for a, b in zip(post_bits_a, post_bits_b) if a == b)
    post_mismatches = total_post_bits - post_matches
    post_kar = post_matches / total_post_bits if total_post_bits > 0 else 0.0
    post_ber = 1.0 - post_kar

    # 4. Filtered comparison (excluding samples where either node had a zero seed)
    non_zero_indices = [
        i for i in range(total_samples)
        if (i not in res_a.zero_seed_sample_indices) and (i not in res_b.zero_seed_sample_indices)
    ]
    non_zero_count = len(non_zero_indices)
    if non_zero_count > 0:
        nz_pre_a = "".join(res_a.samples[i].seed_string for i in non_zero_indices)
        nz_pre_b = "".join(res_b.samples[i].seed_string for i in non_zero_indices)
        nz_pre_matches = sum(1 for a, b in zip(nz_pre_a, nz_pre_b) if a == b)
        nz_pre_kar = nz_pre_matches / len(nz_pre_a)
        nz_pre_ber = 1.0 - nz_pre_kar

        nz_post_a = "".join(res_a.samples[i].expanded_string for i in non_zero_indices)
        nz_post_b = "".join(res_b.samples[i].expanded_string for i in non_zero_indices)
        nz_post_matches = sum(1 for a, b in zip(nz_post_a, nz_post_b) if a == b)
        nz_post_kar = nz_post_matches / len(nz_post_a)
        nz_post_ber = 1.0 - nz_post_kar
    else:
        nz_pre_kar = 0.0
        nz_pre_ber = 1.0
        nz_post_kar = 0.0
        nz_post_ber = 1.0

    # 5. Zero seed coincidence
    zero_coincidence = {
        "both_zero": len(set(res_a.zero_seed_sample_indices) & set(res_b.zero_seed_sample_indices)),
        f"{label_a}_only_zero": len(set(res_a.zero_seed_sample_indices) - set(res_b.zero_seed_sample_indices)),
        f"{label_b}_only_zero": len(set(res_b.zero_seed_sample_indices) - set(res_a.zero_seed_sample_indices)),
        "union_zero": len(set(res_a.zero_seed_sample_indices) | set(res_b.zero_seed_sample_indices)),
    }

    return {
        "channel_pair": f"{label_a} vs {label_b}",
        "total_samples": total_samples,
        "seed_length": seed_len,
        "output_length": out_len,
        "expansion_ratio": round(out_len / seed_len, 4),
        "sample_matches": sample_matches,
        "sample_mismatches": sample_mismatches,
        "sample_match_pct": round(sample_match_pct, 4),
        "mismatch_pairs_distribution": mismatch_pairs,
        "pre_expansion": {
            "total_bits": total_pre_bits,
            "matching_bits": pre_matches,
            "mismatch_bits": pre_mismatches,
            "kar": round(pre_kar, 6),
            "ber": round(pre_ber, 6),
        },
        "post_expansion": {
            "total_bits": total_post_bits,
            "matching_bits": post_matches,
            "mismatch_bits": post_mismatches,
            "kar": round(post_kar, 6),
            "ber": round(post_ber, 6),
        },
        "post_expansion_non_zero_only": {
            "evaluated_samples": non_zero_count,
            "total_bits": non_zero_count * out_len,
            "pre_kar": round(nz_pre_kar, 6),
            "pre_ber": round(nz_pre_ber, 6),
            "post_kar": round(nz_post_kar, 6),
            "post_ber": round(nz_post_ber, 6),
        },
        "zero_seed_coincidence": zero_coincidence,
    }

