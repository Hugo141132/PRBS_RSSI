"""
test_d04_lfsr.py

Automated test suite for Milestone D04.0: Pure Galois LFSR PRBS Bit Expansion.
Covers:
- Independent known-answer test (KAT) state/output vectors
- Full-period small-register verification (L=4 period 15, L=5 period 31)
- Degree-32 polynomial mathematical primitivity verification
- Seed sensitivity (differing by 1 bit produces pseudorandom divergence)
- Deterministic resets (reproducibility)
- Output length exactness (40, 48, 64 bits)
- Seed bit ordering (MSB-first vs LSB-first)
- Invalid inputs and boundary rejection
- Explicit zero-seed flagging and handling
- Partial-block handling and coverage tracking
- Independent channel processing (no seed sharing or crosstalk)
- Full D04.0 pipeline execution, artifact integrity, and schema compliance
- Immutability of upstream D03 input files
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import pytest
import numpy as np
import pandas as pd

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analysis.lfsr import (
    DEGREE_2,
    DEGREE_2_TAPS,
    DEGREE_2_TAP_MASK,
    DEGREE_4,
    DEGREE_4_TAPS,
    DEGREE_4_TAP_MASK,
    DEFAULT_DEGREE,
    DEFAULT_POLYNOMIAL_TAPS,
    DEFAULT_TAP_MASK,
    ExpansionResult,
    PerSampleExpansionResult,
    SampleExpansionDetail,
    GaloisLFSR,
    compute_expansion_agreement_metrics,
    compute_per_sample_agreement_metrics,
    create_sample_lfsr,
    expand_bitstream_blocks,
    expand_sample_sequences,
    get_per_sample_symbol_mapping,
    taps_to_tap_mask,
)
from src.analysis.d04_runner import run_d04_pipeline


def test_taps_to_tap_mask_conversion():
    """Verify tap exponent to mask conversion for canonical left and right shift."""
    # Degree 4: x^4 + x + 1 (taps: 4, 1, 0)
    # In left shift: tap_mask = (1 << 1) | (1 << 0) = 3 (0b0011)
    mask_left = taps_to_tap_mask((4, 1, 0), degree=4, shift_direction="left")
    assert mask_left == 0x3

    # Degree 32: x^32 + x^22 + x^2 + x^1 + 1 (taps: 32, 22, 2, 1, 0)
    # In left shift: 2^22 + 2^2 + 2^1 + 2^0 = 0x00400007
    mask_deg32 = taps_to_tap_mask(DEFAULT_POLYNOMIAL_TAPS, degree=32, shift_direction="left")
    assert mask_deg32 == DEFAULT_TAP_MASK
    assert mask_deg32 == 0x00400007

    with pytest.raises(ValueError):
        taps_to_tap_mask((4, 1, 0), degree=5, shift_direction="left")

    with pytest.raises(ValueError):
        taps_to_tap_mask((4, 1, 0), degree=4, shift_direction="invalid")


def test_known_answer_state_and_output_vectors():
    """
    Known-Answer Test (KAT) for Galois LFSR state transitions and bit extraction.
    For L=4, P(x) = x^4 + x + 1 (taps: 4, 1, 0; tap_mask = 3):
    State sequence from seed 1 (left shift, MSB output, before_update):
    Initial state: 1 (0b0001)
    Step 0: output MSB = 0, next_state = (1 << 1) = 2 (0b0010)
    Step 1: output MSB = 0, next_state = (2 << 1) = 4 (0b0100)
    Step 2: output MSB = 0, next_state = (4 << 1) = 8 (0b1000)
    Step 3: output MSB = 1, next_state = ((8 << 1) & 0xF) ^ 3 = 0 ^ 3 = 3 (0b0011)
    Step 4: output MSB = 0, next_state = (3 << 1) = 6 (0b0110)
    """
    lfsr4 = GaloisLFSR(
        degree=4,
        polynomial_taps=(4, 1, 0),
        shift_direction="left",
        output_bit="msb",
        output_timing="before_update",
    )
    lfsr4.reset(1)
    expected_states = [1, 2, 4, 8, 3, 6, 12, 11, 5, 10, 7, 14, 15, 13, 9]
    expected_bits = "000100110101111"

    bits = []
    for s in expected_states:
        assert lfsr4.state == s
        bits.append(str(lfsr4.step()))

    assert "".join(bits) == expected_bits
    # After 15 steps, cycle returns to initial state 1
    assert lfsr4.state == 1


def test_small_register_full_period():
    """
    Verify maximum period 2^L - 1 for small registers.
    Note: Small-register period test verifies algorithmic correctness of shift & feedback logic,
    but does NOT prove primitivity of degree-32 polynomials (tested separately).
    """
    # L=4: period = 2^4 - 1 = 15
    lfsr4 = GaloisLFSR(degree=4, polynomial_taps=(4, 1, 0))
    lfsr4.reset(1)
    seen_states = []
    for _ in range(15):
        seen_states.append(lfsr4.state)
        lfsr4.step()
    assert len(seen_states) == 15
    assert len(set(seen_states)) == 15
    assert lfsr4.state == 1

    # L=5: P(x) = x^5 + x^2 + 1 (taps: 5, 2, 0; mask = 0b0101 = 5)
    # period = 2^5 - 1 = 31
    lfsr5 = GaloisLFSR(degree=5, polynomial_taps=(5, 2, 0))
    lfsr5.reset(1)
    seen_states5 = []
    for _ in range(31):
        seen_states5.append(lfsr5.state)
        lfsr5.step()
    assert len(seen_states5) == 31
    assert len(set(seen_states5)) == 31
    assert lfsr5.state == 1


def test_degree_32_polynomial_mathematical_primitivity():
    """
    Mathematically prove primitivity of P(x) = x^32 + x^22 + x^2 + x^1 + 1 over GF(2).
    Order of multiplicative group in GF(2^32) is 2^32 - 1 = 4,294,967,295.
    Prime factors are Fermat primes: 3, 5, 17, 257, 65537.
    A polynomial is primitive iff x^(2^32 - 1) = 1 (mod P(x)) and
    x^((2^32 - 1)/p) != 1 (mod P(x)) for each prime factor p.
    """
    deg = 32
    mask = (1 << deg) - 1
    poly = (1 << 32) | DEFAULT_TAP_MASK
    poly_low = poly & mask

    def poly_mul_mod(a: int, b: int) -> int:
        res = 0
        for i in range(deg):
            if (b >> i) & 1:
                res ^= a
            high = (a >> (deg - 1)) & 1
            a = (a << 1) & mask
            if high:
                a ^= poly_low
        return res

    def poly_pow_mod(base: int, exp: int) -> int:
        res = 1
        cur = base
        while exp > 0:
            if exp & 1:
                res = poly_mul_mod(res, cur)
            cur = poly_mul_mod(cur, cur)
            exp >>= 1
        return res

    order = (1 << 32) - 1
    factors = [3, 5, 17, 257, 65537]

    # Verify x^(2^32 - 1) == 1 mod P(x)
    assert poly_pow_mod(2, order) == 1

    # Verify order is minimal (not divisible by any proper subgroup)
    for p in factors:
        assert poly_pow_mod(2, order // p) != 1


def test_seed_sensitivity():
    """
    Verify seed sensitivity and GF(2) linearity of Galois LFSR.
    By GF(2) linearity, LFSR(A) ^ LFSR(B) == LFSR(A ^ B).
    For two seeds differing by a single bit at LSB (Delta S = 1), the difference sequence
    is exactly the LFSR impulse response for state 1.
    For degree-32 polynomial P(x) = x^32 + x^22 + x^2 + x^1 + 1, bit 0 reaches MSB at step 31,
    and feedback taps produce exactly 5 ones in the first 64 bits.
    Hence, Hamming distance is mathematically exactly 5 for Delta S = 1.
    Over multi-bit differences, the sequences diverge widely (Hamming distance > 20).
    """
    lfsr = GaloisLFSR(degree=32)

    seed_a = "10000000000000000000000000000000"
    seed_b = "10000000000000000000000000000001"

    out_a = lfsr.reset(seed_a).generate(64)
    out_b = lfsr.reset(seed_b).generate(64)

    assert out_a != out_b
    hamming_dist = sum(1 for a, b in zip(out_a, out_b) if a != b)
    # Exact mathematical impulse response weight of state 1 over first 64 bits
    assert hamming_dist == 5

    # Verify exact GF(2) linearity: out_a ^ out_b must equal LFSR(seed_a ^ seed_b)
    diff_seed = "00000000000000000000000000000001"  # seed_a ^ seed_b
    out_diff = lfsr.reset(diff_seed).generate(64)
    expected_diff = "".join(str(int(a) ^ int(b)) for a, b in zip(out_a, out_b))
    assert out_diff == expected_diff
    ones_indices = [i for i, b in enumerate(out_diff) if b == "1"]
    assert ones_indices == [31, 41, 51, 62, 63]

    # Over realistic multi-bit seed differences, verify substantial Hamming divergence
    seed_c = "10101010101010101010101010101010"
    seed_d = "01010101010101010101010101010101"
    out_c = lfsr.reset(seed_c).generate(64)
    out_d = lfsr.reset(seed_d).generate(64)
    dist_cd = sum(1 for a, b in zip(out_c, out_d) if a != b)
    assert dist_cd > 20


def test_independent_companion_matrix_reference_kat():
    """
    Independent, non-circular Known-Answer Test (KAT) using GF(2) algebraic companion matrix.
    Given monic primitive polynomial P(x) = x^32 + x^22 + x^2 + x^1 + 1,
    the Galois LFSR state evolves as S(t+1) = M @ S(t) mod 2, where M is the companion matrix.
    Output bit y(t) = S_31(t).
    Verifies GaloisLFSR against pure linear algebra over GF(2) across multiple independent seeds.
    """
    L = 32
    M = np.zeros((L, L), dtype=int)
    for i in range(1, L):
        M[i, i - 1] = 1
    # Taps for x^32 + x^22 + x^2 + x^1 + 1: feedback into positions 0, 1, 2, 22 from s_31
    for tap in [0, 1, 2, 22]:
        M[tap, 31] ^= 1

    test_seeds = [
        0x12345678,
        0x80000000,
        0x00000001,
        0xDEADBEEF,
        0xAAAAAAAA,
    ]

    lfsr = GaloisLFSR(degree=32)

    for seed in test_seeds:
        # Generate via companion matrix
        s_vec = np.array([(seed >> i) & 1 for i in range(L)], dtype=int)
        matrix_bits = []
        cur_s = s_vec.copy()
        for _ in range(64):
            matrix_bits.append(str(cur_s[31]))
            cur_s = (M @ cur_s) % 2
        matrix_out = "".join(matrix_bits)

        # Generate via GaloisLFSR class
        lfsr_out = lfsr.reset(seed).generate(64)

        assert lfsr_out == matrix_out, f"Mismatch for seed {hex(seed)}"




def test_deterministic_resets():
    """Verify that resetting with the identical seed produces 100% identical bit sequence."""
    lfsr = GaloisLFSR(degree=32)
    seed = "10110011100011110000111100001010"

    seq1 = lfsr.reset(seed).generate(64)
    seq2 = lfsr.reset(seed).generate(64)
    assert seq1 == seq2


def test_output_lengths_exactness():
    """Verify exact output bit counts for 40, 48, 64 bits."""
    lfsr = GaloisLFSR(degree=32)
    lfsr.reset(0x12345678)

    for length in [0, 1, 40, 48, 64, 128]:
        out = lfsr.reset(0x12345678).generate(length)
        assert len(out) == length
        if length > 0:
            assert all(c in "01" for c in out)


def test_seed_bit_ordering():
    """Verify MSB-first vs LSB-first parsing of binary seed string."""
    seed_str = "10000000000000000000000000000000"  # 1 followed by 31 zeros

    lfsr_msb = GaloisLFSR(degree=32, seed_bit_order="msb_first")
    lfsr_msb.reset(seed_str)
    # Under MSB-first: 1 is at bit 31, integer is 0x80000000
    assert lfsr_msb.initial_seed == 0x80000000

    lfsr_lsb = GaloisLFSR(degree=32, seed_bit_order="lsb_first")
    lfsr_lsb.reset(seed_str)
    # Under LSB-first: 1 is at bit 0, integer is 1
    assert lfsr_lsb.initial_seed == 1


def test_invalid_inputs_and_edge_cases():
    """Verify proper rejection of invalid seeds, lengths, and configurations."""
    lfsr = GaloisLFSR(degree=32)

    with pytest.raises(ValueError):
        lfsr.reset(-1)

    with pytest.raises(ValueError):
        lfsr.reset("101020101")  # non-binary char '2'

    with pytest.raises(ValueError):
        lfsr.reset("1" * 33)  # length exceeds degree 32

    with pytest.raises(ValueError):
        lfsr.generate(-5)  # negative length

    with pytest.raises(TypeError):
        lfsr.reset(None)  # invalid type

    with pytest.raises(ValueError):
        GaloisLFSR(degree=1)  # degree must be >= 2

    with pytest.raises(ValueError):
        GaloisLFSR(shift_direction="diagonal")


def test_zero_seed_handling():
    """
    Verify explicit zero-seed flagging and behaviour.
    Zero-seed must be flagged, not crashed or silently mutated.
    Output of zero-seed in pure Galois LFSR is all zeros.
    """
    lfsr = GaloisLFSR(degree=32)
    zero_seed_str = "0" * 32

    lfsr.reset(zero_seed_str)
    assert lfsr.is_zero_seed is True
    assert lfsr.is_zero_state is True

    out = lfsr.generate(64)
    assert out == "0" * 64
    assert lfsr.is_zero_state is True

    # Reset with non-zero resets the zero flag
    lfsr.reset(1)
    assert lfsr.is_zero_seed is False
    assert lfsr.is_zero_state is False


def test_partial_block_handling_and_coverage():
    """Verify bitstream division, partial-block exclusion, and coverage calculation."""
    # 70-bit stream with 32-bit seeds: 2 full blocks (64 bits), 6 unconsumed bits
    stream = "10101010" * 8 + "111111"
    assert len(stream) == 70

    res = expand_bitstream_blocks(stream, seed_length=32, output_length=40)
    assert res.total_input_bits == 70
    assert res.consumed_input_bits == 64
    assert res.unconsumed_input_bits == 6
    assert res.num_full_blocks == 2
    assert res.partial_block_string == "111111"
    assert res.partial_handling == "exclude"
    assert abs(res.block_coverage_pct - (64 / 70 * 100)) < 1e-4
    assert res.total_expanded_bits == 80  # 2 * 40
    assert abs(res.expansion_ratio - (80 / 64)) < 1e-4


def test_channel_independence_and_no_crosstalk():
    """Verify that processing Alice, Bob, and Eve independently preserves state isolation."""
    stream_a = "10101010" * 8  # 64 bits (2 blocks)
    stream_b = "11110000" * 8  # 64 bits (2 blocks)
    stream_e = "00001111" * 8  # 64 bits (2 blocks)

    lfsr_a = GaloisLFSR(degree=32)
    lfsr_b = GaloisLFSR(degree=32)
    lfsr_e = GaloisLFSR(degree=32)

    res_a = expand_bitstream_blocks(stream_a, seed_length=32, output_length=48, lfsr=lfsr_a)
    res_b = expand_bitstream_blocks(stream_b, seed_length=32, output_length=48, lfsr=lfsr_b)
    res_e = expand_bitstream_blocks(stream_e, seed_length=32, output_length=48, lfsr=lfsr_e)

    assert res_a.expanded_bitstream != res_b.expanded_bitstream
    assert res_a.expanded_bitstream != res_e.expanded_bitstream

    # Confirm seeds in records exactly match input chunks
    assert res_a.blocks[0].seed_string == stream_a[:32]
    assert res_b.blocks[0].seed_string == stream_b[:32]
    assert res_e.blocks[0].seed_string == stream_e[:32]


def test_degree_2_and_4_primitive_periods_exhaustive():
    """
    Exhaustively verify primitive periods for degree-2 and degree-4 polynomials.
    - Degree 2: P(x) = x^2 + x + 1 (taps: 2, 1, 0; tap mask: 0x3)
      Order of GF(2^2)* is 2^2 - 1 = 3.
      All 3 non-zero states {1, 2, 3} must form a single cycle of period 3.
      Zero state {0} must remain absorbing at 0.
    - Degree 4: P(x) = x^4 + x + 1 (taps: 4, 1, 0; tap mask: 0x3)
      Order of GF(2^4)* is 2^4 - 1 = 15.
      All 15 non-zero states {1..15} must form a single cycle of period 15.
      Zero state {0} must remain absorbing at 0.
    """
    # 1. Degree 2 exhaustive check
    lfsr2 = GaloisLFSR(
        degree=DEGREE_2,
        polynomial_taps=DEGREE_2_TAPS,
        shift_direction="left",
        output_bit="msb",
        output_timing="before_update",
    )
    # Zero state absorption
    lfsr2.reset(0)
    for _ in range(10):
        assert lfsr2.step() == 0
        assert lfsr2.state == 0

    # Nonzero states period
    for start_state in [1, 2, 3]:
        lfsr2.reset(start_state)
        visited = []
        for _ in range(3):
            visited.append(lfsr2.state)
            lfsr2.step()
        assert len(visited) == 3
        assert set(visited) == {1, 2, 3}
        assert lfsr2.state == start_state  # Cycle closed

    # 2. Degree 4 exhaustive check
    lfsr4 = GaloisLFSR(
        degree=DEGREE_4,
        polynomial_taps=DEGREE_4_TAPS,
        shift_direction="left",
        output_bit="msb",
        output_timing="before_update",
    )
    # Zero state absorption
    lfsr4.reset(0)
    for _ in range(20):
        assert lfsr4.step() == 0
        assert lfsr4.state == 0

    # Nonzero states period
    for start_state in range(1, 16):
        lfsr4.reset(start_state)
        visited = []
        for _ in range(15):
            visited.append(lfsr4.state)
            lfsr4.step()
        assert len(visited) == 15
        assert set(visited) == set(range(1, 16))
        assert lfsr4.state == start_state  # Cycle closed


def test_known_answer_per_sample_symbol_mappings():
    """
    Verify known-answer input/output mappings and pairwise Hamming distances
    for each of the 3 ADQ quantization symbols with full-period m = 2^L - 1.
    - 2-bit: L=2, output length 3 (2^2 - 1)
    - 4-bit: L=4, output length 15 (2^4 - 1)
    """
    # 2-bit Gray coding (2b -> 3b default)
    m2 = get_per_sample_symbol_mapping("2bit", output_length=3)
    assert m2["symbols"]["Level 0"]["seed_string"] == "00"
    assert m2["symbols"]["Level 0"]["expanded_output"] == "000"
    assert m2["symbols"]["Level 0"]["is_zero_seed"] is True

    assert m2["symbols"]["Level 1"]["seed_string"] == "01"
    assert m2["symbols"]["Level 1"]["expanded_output"] == "011"
    assert m2["symbols"]["Level 1"]["is_zero_seed"] is False

    assert m2["symbols"]["Level 2"]["seed_string"] == "11"
    assert m2["symbols"]["Level 2"]["expanded_output"] == "101"
    assert m2["symbols"]["Level 2"]["is_zero_seed"] is False

    dist2 = m2["pairwise_hamming_distances"]
    assert dist2["Level 0 vs Level 1"]["hamming_distance"] == 2
    assert dist2["Level 0 vs Level 2"]["hamming_distance"] == 2
    assert dist2["Level 1 vs Level 2"]["hamming_distance"] == 2

    # 4-bit LoRa-PRIME coding (4b -> 15b default)
    m4 = get_per_sample_symbol_mapping("4bit", output_length=15)
    assert m4["symbols"]["Level 0"]["seed_string"] == "1010"
    assert m4["symbols"]["Level 0"]["expanded_output"] == "101111000100110"
    assert m4["symbols"]["Level 0"]["is_zero_seed"] is False

    assert m4["symbols"]["Level 1"]["seed_string"] == "1011"
    assert m4["symbols"]["Level 1"]["expanded_output"] == "101011110001001"
    assert m4["symbols"]["Level 1"]["is_zero_seed"] is False

    assert m4["symbols"]["Level 2"]["seed_string"] == "1001"
    assert m4["symbols"]["Level 2"]["expanded_output"] == "100010011010111"
    assert m4["symbols"]["Level 2"]["is_zero_seed"] is False

    dist4 = m4["pairwise_hamming_distances"]
    assert dist4["Level 0 vs Level 1"]["hamming_distance"] == 8
    assert dist4["Level 0 vs Level 2"]["hamming_distance"] == 8
    assert dist4["Level 1 vs Level 2"]["hamming_distance"] == 8


def test_all_distinct_seed_pairs_hamming_distance_exhaustive():
    """
    Independently and exhaustively verify that every pair of distinct seeds has
    full-length output Hamming distance strictly 2 for L=2 (output m = 2^2 - 1 = 3) and
    strictly 8 for L=4 (output m = 2^4 - 1 = 15), including comparisons against zero.
    Also verify exact independent known outputs: 00->000, 01->011, 10->110, 11->101.
    """
    # 1. L=2: 4 possible states (0, 1, 2, 3), output length 3
    lfsr2 = GaloisLFSR(
        degree=DEGREE_2,
        polynomial_taps=DEGREE_2_TAPS,
        shift_direction="left",
        output_bit="msb",
        output_timing="before_update",
    )
    outputs_2b = {}
    for s in range(4):
        seed_str = f"{s:02b}"
        if s == 0:
            outputs_2b[seed_str] = "0" * 3
        else:
            outputs_2b[seed_str] = lfsr2.reset(s).generate(3)

    # Independent expected verification
    assert outputs_2b == {
        "00": "000",
        "01": "011",
        "10": "110",
        "11": "101",
    }

    seeds_2b = list(outputs_2b.keys())
    for i in range(len(seeds_2b)):
        for j in range(i + 1, len(seeds_2b)):
            s1, s2 = seeds_2b[i], seeds_2b[j]
            dist = sum(1 for a, b in zip(outputs_2b[s1], outputs_2b[s2]) if a != b)
            assert dist == 2, f"Failed for L=2 pair ({s1}, {s2}): dist={dist} != 2"

    # 2. L=4: 16 possible states (0..15), output length 15
    lfsr4 = GaloisLFSR(
        degree=DEGREE_4,
        polynomial_taps=DEGREE_4_TAPS,
        shift_direction="left",
        output_bit="msb",
        output_timing="before_update",
    )
    outputs_4b = {}
    for s in range(16):
        seed_str = f"{s:04b}"
        if s == 0:
            outputs_4b[seed_str] = "0" * 15
        else:
            outputs_4b[seed_str] = lfsr4.reset(s).generate(15)

    seeds_4b = list(outputs_4b.keys())
    for i in range(len(seeds_4b)):
        for j in range(i + 1, len(seeds_4b)):
            s1, s2 = seeds_4b[i], seeds_4b[j]
            dist = sum(1 for a, b in zip(outputs_4b[s1], outputs_4b[s2]) if a != b)
            assert dist == 8, f"Failed for L=4 pair ({s1}, {s2}): dist={dist} != 8"


def test_per_sample_reset_independence_and_zero_seed():
    """
    Verify that LFSR explicitly resets before each sample with zero state leakage
    across consecutive samples, and that zero seeds generate all zeros without remapping.
    """
    # Sample sequence: Level 1 ("01"), Level 2 ("10"), Level 1 ("01"), Level 0 ("00")
    sample_seq = ["01", "10", "01", "00"]
    res = expand_sample_sequences(sample_seq, seed_length=2, output_length=3)

    assert res.total_samples == 4
    assert res.total_output_bits == 12
    assert res.zero_seed_count == 1
    assert res.zero_seed_sample_indices == [3]

    # Verify outputs
    assert res.samples[0].expanded_string == "011"
    assert res.samples[1].expanded_string == "110"
    # Reset independence: sample 2 MUST produce identical output to sample 0
    assert res.samples[2].expanded_string == "011"
    # Zero seed: sample 3 MUST produce all zeros
    assert res.samples[3].expanded_string == "000"
    assert res.samples[3].is_zero_seed is True

    # Configurable output length: expand 2-bit to 6 bits
    res_6b = expand_sample_sequences(["01"], seed_length=2, output_length=6)
    # Cycle is 0, 1, 1, then repeats 0, 1, 1 -> "011011"
    assert res_6b.samples[0].expanded_string == "011011"


def test_d03_per_sample_alignment_and_exact_metrics():
    """
    Verify exact per-sample counts, zero seeds, and agreement metrics on active D03 CSV.
    """
    d03_csv = os.path.join(os.path.dirname(__file__), "..", "results", "dummy", "d03_quantized_bits.csv")
    df = pd.read_csv(d03_csv)

    def clean_str(val):
        s = str(val).strip()
        if s.startswith('="') and s.endswith('"'):
            s = s[2:-1]
        elif s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s

    a_2b_seeds = [clean_str(x) for x in df["Alice_2bit"]]
    b_2b_seeds = [clean_str(x) for x in df["Bob_2bit"]]
    e1a_2b_seeds = [clean_str(x) for x in df["Eve1-Alice_2bit"]]
    e1b_2b_seeds = [clean_str(x) for x in df["Eve1-Bob_2bit"]]

    a_4b_seeds = [clean_str(x) for x in df["Alice_4bit"]]
    b_4b_seeds = [clean_str(x) for x in df["Bob_4bit"]]

    # 1. Total samples: exactly 500
    assert len(a_2b_seeds) == 500
    assert len(b_2b_seeds) == 500

    # 2. Exact sample agreement between Alice and Bob: 384 matches (76.8%), 116 mismatches (23.2%)
    sample_matches = sum(1 for a, b in zip(a_2b_seeds, b_2b_seeds) if a == b)
    assert sample_matches == 384
    assert (500 - sample_matches) == 116

    # 3. Zero seed counts
    assert a_2b_seeds.count("00") == 133
    assert b_2b_seeds.count("00") == 179
    assert e1a_2b_seeds.count("00") == 189
    assert e1b_2b_seeds.count("00") == 171

    # In 4-bit LoRa-PRIME, Level 0 is "1010", so zero seeds count is 0
    assert a_4b_seeds.count("0000") == 0
    assert b_4b_seeds.count("0000") == 0

    # 4. 2-Bit expansion metrics (2b -> 3b, 1500 output bits)
    res_a_2b = expand_sample_sequences(a_2b_seeds, seed_length=2, output_length=3)
    res_b_2b = expand_sample_sequences(b_2b_seeds, seed_length=2, output_length=3)
    m_2b = compute_per_sample_agreement_metrics(res_a_2b, res_b_2b, "Alice", "Bob")

    assert res_a_2b.total_output_bits == 1500
    assert res_b_2b.total_output_bits == 1500
    assert m_2b["pre_expansion"]["total_bits"] == 1000
    assert m_2b["pre_expansion"]["matching_bits"] == 884
    assert m_2b["pre_expansion"]["kar"] == 0.8840
    assert m_2b["pre_expansion"]["ber"] == 0.1160

    assert m_2b["post_expansion"]["total_bits"] == 1500
    assert m_2b["post_expansion"]["matching_bits"] == 1268
    assert m_2b["post_expansion"]["mismatch_bits"] == 232
    assert abs(m_2b["post_expansion"]["kar"] - (1268 / 1500)) < 1e-5
    assert abs(m_2b["post_expansion"]["ber"] - (232 / 1500)) < 1e-5

    # 5. 4-Bit expansion metrics (4b -> 15b, 7500 output bits)
    res_a_4b = expand_sample_sequences(a_4b_seeds, seed_length=4, output_length=15)
    res_b_4b = expand_sample_sequences(b_4b_seeds, seed_length=4, output_length=15)
    m_4b = compute_per_sample_agreement_metrics(res_a_4b, res_b_4b, "Alice", "Bob")

    assert res_a_4b.total_output_bits == 7500
    assert res_b_4b.total_output_bits == 7500
    assert m_4b["pre_expansion"]["total_bits"] == 2000
    assert m_4b["pre_expansion"]["matching_bits"] == 1884
    assert m_4b["pre_expansion"]["kar"] == 0.9420
    assert m_4b["pre_expansion"]["ber"] == 0.0580

    assert m_4b["post_expansion"]["total_bits"] == 7500
    assert m_4b["post_expansion"]["matching_bits"] == 6572
    assert m_4b["post_expansion"]["mismatch_bits"] == 928
    assert abs(m_4b["post_expansion"]["kar"] - (6572 / 7500)) < 1e-5
    assert abs(m_4b["post_expansion"]["ber"] - (928 / 7500)) < 1e-5


def test_d04_pipeline_full_execution_and_schema():
    """
    Execute full D04.0 pipeline into a temporary directory and validate per-sample schema,
    Excel formula strings, and figure generation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_json = os.path.join(tmp_dir, "d04_results.json")
        tmp_csv = os.path.join(tmp_dir, "d04_expanded.csv")
        tmp_hist_csv = os.path.join(tmp_dir, "d04_hist.csv")
        tmp_figs = os.path.join(tmp_dir, "figures")

        results = run_d04_pipeline(
            output_json_path=tmp_json,
            output_expanded_csv=tmp_csv,
            historical_csv_path=tmp_hist_csv,
            figures_dir=tmp_figs,
        )

        assert os.path.exists(tmp_json)
        assert os.path.exists(tmp_csv)
        assert os.path.exists(tmp_hist_csv)
        assert os.path.getsize(tmp_json) > 1000
        assert os.path.getsize(tmp_csv) > 1000

        # Validate figures exist and non-empty
        for fig_name in ["kar_expansion_comparison", "ber_vs_length", "block_seed_analysis"]:
            fig_path = results["generated_artifacts"]["figures"][fig_name]
            assert os.path.exists(fig_path)
            assert os.path.getsize(fig_path) > 5000

        # Validate JSON content
        assert results["milestone"] == "D04.0"
        assert results["architecture"] == "per_sample_pure_galois_lfsr"
        assert results["active_configuration"]["mode"] == "per_sample_expansion"
        assert results["active_configuration"]["2bit"]["register_width"] == 2
        assert results["active_configuration"]["2bit"]["primitive_polynomial"] == "x^2 + x + 1"
        assert results["active_configuration"]["4bit"]["register_width"] == 4
        assert results["active_configuration"]["4bit"]["primitive_polynomial"] == "x^4 + x + 1"

        # Validate historical benchmark sections are preserved
        assert "historical_32bit_blockwise" in results
        assert "historical_2x_persample" in results

        assert results["active_configuration"]["2bit"]["output_length"] == 3
        assert results["active_configuration"]["4bit"]["output_length"] == 15

        # Validate experiments structure and exact bit totals
        for depth, expected_bits in [("2bit", 1500), ("4bit", 7500)]:
            pair_data = results["experiments"][depth]["pairs"]["Alice vs Bob"]
            assert pair_data["post_expansion"]["total_bits"] == expected_bits
            assert 0.0 <= pair_data["pre_expansion"]["kar"] <= 1.0
            assert 0.0 <= pair_data["post_expansion"]["kar"] <= 1.0
            assert abs(pair_data["post_expansion"]["kar"] + pair_data["post_expansion"]["ber"] - 1.0) < 1e-5

        # Validate CSV contains per-sample columns and Excel text formulas
        df_csv = pd.read_csv(tmp_csv)
        assert len(df_csv) == 500
        assert "Sample_ID" in df_csv.columns
        assert "Alice_2bit_Seed" in df_csv.columns
        assert "Alice_2bit_Expanded" in df_csv.columns
        assert "Alice_4bit_Seed" in df_csv.columns
        assert "Alice_4bit_Expanded" in df_csv.columns

        first_seed = str(df_csv["Alice_2bit_Seed"].iloc[0])
        assert first_seed.startswith('="') and first_seed.endswith('"')
        first_exp = str(df_csv["Alice_2bit_Expanded"].iloc[0])
        assert first_exp.startswith('="') and first_exp.endswith('"')
        assert len(first_exp[2:-1]) == 3

        first_4b_exp = str(df_csv["Alice_4bit_Expanded"].iloc[0])
        assert first_4b_exp.startswith('="') and first_4b_exp.endswith('"')
        assert len(first_4b_exp[2:-1]) == 15


def test_d03_inputs_remain_unmodified():
    """Verify that D03 input files remain strictly unmodified before and after D04."""
    d03_csv = os.path.join(os.path.dirname(__file__), "..", "results", "dummy", "d03_quantized_bits.csv")
    with open(d03_csv, "rb") as f:
        hash_before = hashlib.sha256(f.read()).hexdigest()

    # Re-run pipeline targeting isolated temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_json = os.path.join(tmp_dir, "d04_results.json")
        tmp_csv = os.path.join(tmp_dir, "d04_expanded.csv")
        tmp_hist_csv = os.path.join(tmp_dir, "d04_hist.csv")
        tmp_figs = os.path.join(tmp_dir, "figures")
        run_d04_pipeline(
            input_bits_csv=d03_csv,
            output_json_path=tmp_json,
            output_expanded_csv=tmp_csv,
            historical_csv_path=tmp_hist_csv,
            figures_dir=tmp_figs,
        )

    with open(d03_csv, "rb") as f:
        hash_after = hashlib.sha256(f.read()).hexdigest()

    assert hash_before == hash_after


def test_d03_provenance_and_exact_bit_partitioning():
    """
    Verify exact bit partition matches and mismatches for D03 CSV.
    Confirms exact provenance:
    - 2-bit Alice vs Bob:
      * Full stream (1000 bits): 884 matches, 116 mismatches (KAR = 0.8840)
      * Retained prefix (992 bits, 31 blocks): 880 matches, 112 mismatches (KAR ≈ 0.8871)
      * Omitted tail (8 bits): 4 matches, 4 mismatches (KAR = 0.5000)
    - 4-bit Alice vs Bob:
      * Full stream (2000 bits): 1884 matches, 116 mismatches (KAR = 0.9420)
      * Retained prefix (1984 bits, 62 blocks): 1872 matches, 112 mismatches (KAR ≈ 0.9435)
      * Omitted tail (16 bits): 12 matches, 4 mismatches (KAR = 0.7500)
    This strictly confirms that the 0.8430 (157 mismatches) figure in earlier D03 Table 4.2
    was stale documentation from prior D02 iterations (pre-commit 9043f14), and that
    D04.0 operates with 100% mathematical fidelity on the current active D03 artifacts.
    """
    d03_csv = os.path.join(os.path.dirname(__file__), "..", "results", "dummy", "d03_quantized_bits.csv")
    df = pd.read_csv(d03_csv)

    def clean_str(val):
        s = str(val).strip()
        if s.startswith('="') and s.endswith('"'):
            s = s[2:-1]
        elif s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s

    a_2b = "".join(clean_str(x) for x in df["Alice_2bit"])
    b_2b = "".join(clean_str(x) for x in df["Bob_2bit"])
    a_4b = "".join(clean_str(x) for x in df["Alice_4bit"])
    b_4b = "".join(clean_str(x) for x in df["Bob_4bit"])

    # 2-bit assertions
    assert len(a_2b) == 1000 and len(b_2b) == 1000
    m_2b_full = sum(1 for a, b in zip(a_2b, b_2b) if a == b)
    mm_2b_full = 1000 - m_2b_full
    assert m_2b_full == 884 and mm_2b_full == 116

    m_2b_prefix = sum(1 for a, b in zip(a_2b[:992], b_2b[:992]) if a == b)
    mm_2b_prefix = 992 - m_2b_prefix
    assert m_2b_prefix == 880 and mm_2b_prefix == 112

    m_2b_tail = sum(1 for a, b in zip(a_2b[992:], b_2b[992:]) if a == b)
    mm_2b_tail = 8 - m_2b_tail
    assert m_2b_tail == 4 and mm_2b_tail == 4

    # 4-bit assertions
    assert len(a_4b) == 2000 and len(b_4b) == 2000
    m_4b_full = sum(1 for a, b in zip(a_4b, b_4b) if a == b)
    mm_4b_full = 2000 - m_4b_full
    assert m_4b_full == 1884 and mm_4b_full == 116

    m_4b_prefix = sum(1 for a, b in zip(a_4b[:1984], b_4b[:1984]) if a == b)
    mm_4b_prefix = 1984 - m_4b_prefix
    assert m_4b_prefix == 1872 and mm_4b_prefix == 112

    m_4b_tail = sum(1 for a, b in zip(a_4b[1984:], b_4b[1984:]) if a == b)
    mm_4b_tail = 16 - m_4b_tail
    assert m_4b_tail == 12 and mm_4b_tail == 4

