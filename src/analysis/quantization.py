"""
quantization.py

Milestone D03: Modified Adaptive Dual-Threshold Quantization (ADQ)
for the Physical Layer Secret Key Generation (SKG) pipeline.

Implements exclusively the Modified Adaptive Dual-Threshold Quantization (ADQ)
scheme from LoRa-PRIME (IEEE OJ-COMS 2026, Section IV-C):
1. Adaptive dual thresholds:
       q_i^+ = mu_X + alpha * sigma_X
       q_i^- = mu_X - alpha * sigma_X
2. 3-Level Quantization Mapping (preserving intermediate samples):
       Level 0: X_i < q_i^-
       Level 1: q_i^- <= X_i <= q_i^+  (Intermediate samples retained)
       Level 2: X_i > q_i^+
3. Binary Encodings:
       - 2-bit Gray coding: Level 0 -> '00', Level 1 -> '01', Level 2 -> '11'
       - 4-bit LoRa-PRIME representation: Level 0 -> '1010', Level 1 -> '1011', Level 2 -> '1001'
4. Metrics:
       - Key Agreement Rate (KAR): KAR = (1 / n) * sum_{i=1}^n I(K_A[i] == K_B[i])
       - Bit Error Rate (BER): BER = 1.0 - KAR
       - Key Generation Rate (KGR) calculation support
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import numpy as np


@dataclass
class QuantizationResult:
    """Structured container for single-channel quantization outputs."""
    symbols: List[int]
    bits: str
    num_samples: int
    retained_samples: int
    discarded_samples: int
    bit_length: int
    thresholds: Dict[str, Union[float, List[float]]]
    level_counts: Dict[int, int]
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert result object to dictionary."""
        return asdict(self)


class ModifiedAdaptiveDualThresholdQuantizer:
    """
    Modified Adaptive Dual-Threshold Quantization (ADQ) engine.

    Formulation (LoRa-PRIME, IEEE OJ-COMS 2026, Eq. 4-5):
        q^+ = mu_X + alpha * sigma_X
        q^- = mu_X - alpha * sigma_X

        Q(X_i):
            Level 0: X_i < q^-
            Level 1: q^- <= X_i <= q^+  (Intermediate retained samples)
            Level 2: X_i > q^+

    Encoding:
        2-bit: Level 0 -> '00', Level 1 -> '01', Level 2 -> '11'
        4-bit: Level 0 -> '1010', Level 1 -> '1011', Level 2 -> '1001'
    """

    ENCODING_2BIT = {
        0: "00",
        1: "01",
        2: "11",
    }

    ENCODING_4BIT = {
        0: "1010",
        1: "1011",
        2: "1001",
    }

    def __init__(
        self,
        alpha: float = 0.5,
        bit_depth: Literal[2, 4] = 2,
        segment_size: Optional[int] = None,
        custom_encoding: Optional[Dict[int, str]] = None,
        epsilon: float = 1e-9,
    ) -> None:
        """
        Initialize the Modified ADQ quantizer.

        Args:
            alpha: Multiplier coefficient controlling sensitivity to signal variations.
            bit_depth: Target bit resolution per symbol (2 or 4 bits).
            segment_size: Window size for local adaptive threshold estimation.
                          If None, thresholds are computed globally over the sequence.
            custom_encoding: Optional custom mapping from integer level to bit string.
            epsilon: Minimum variance safeguard to prevent division-by-zero on flat signals.
        """
        if alpha < 0:
            raise ValueError(f"alpha must be non-negative, got {alpha}")
        if bit_depth not in (2, 4):
            raise ValueError(f"bit_depth must be 2 or 4, got {bit_depth}")
        if segment_size is not None and segment_size <= 0:
            raise ValueError(f"segment_size must be a positive integer, got {segment_size}")

        self.alpha = float(alpha)
        self.bit_depth = bit_depth
        self.segment_size = segment_size
        self.epsilon = epsilon

        if custom_encoding is not None:
            self.encoding_table = custom_encoding
        elif bit_depth == 2:
            self.encoding_table = self.ENCODING_2BIT
        else:
            self.encoding_table = self.ENCODING_4BIT

    def compute_thresholds(
        self,
        segment: np.ndarray,
    ) -> Tuple[float, float, float, float]:
        """
        Compute mean, standard deviation, and upper/lower thresholds for a segment.

        Returns:
            Tuple of (mu, sigma, q_upper, q_lower)
        """
        mu = float(np.mean(segment))
        sigma = float(np.std(segment))

        effective_sigma = max(sigma, self.epsilon) if sigma > 0 else 0.0

        q_upper = mu + self.alpha * effective_sigma
        q_lower = mu - self.alpha * effective_sigma

        return mu, sigma, q_upper, q_lower

    def quantize(self, x: Union[List[float], np.ndarray]) -> QuantizationResult:
        """
        Quantize input signal into discrete levels and bit strings.

        Args:
            x: Input 1D array of filtered RSSI values.

        Returns:
            QuantizationResult containing symbols, bits, counts, and metadata.
        """
        arr = np.asarray(x, dtype=np.float64)
        n = len(arr)

        if n == 0:
            return QuantizationResult(
                symbols=[],
                bits="",
                num_samples=0,
                retained_samples=0,
                discarded_samples=0,
                bit_length=0,
                thresholds={"q_upper": [], "q_lower": [], "mean": [], "std": []},
                level_counts={0: 0, 1: 0, 2: 0},
                parameters={
                    "alpha": self.alpha,
                    "bit_depth": self.bit_depth,
                    "segment_size": self.segment_size,
                },
            )

        symbols: List[int] = []
        bit_chunks: List[str] = []
        level_counts = {0: 0, 1: 0, 2: 0}

        q_uppers: List[float] = []
        q_lowers: List[float] = []
        means: List[float] = []
        stds: List[float] = []

        if self.segment_size is None or self.segment_size >= n:
            # Global thresholding
            mu, sigma, q_upper, q_lower = self.compute_thresholds(arr)
            means.append(mu)
            stds.append(sigma)
            q_uppers.append(q_upper)
            q_lowers.append(q_lower)

            for val in arr:
                lvl = self._classify_sample(val, q_upper, q_lower)
                symbols.append(lvl)
                bit_chunks.append(self.encoding_table[lvl])
                level_counts[lvl] += 1
        else:
            # Segmented / block adaptive thresholding
            step = self.segment_size
            for i in range(0, n, step):
                chunk = arr[i : i + step]
                mu, sigma, q_upper, q_lower = self.compute_thresholds(chunk)
                means.append(mu)
                stds.append(sigma)
                q_uppers.append(q_upper)
                q_lowers.append(q_lower)

                for val in chunk:
                    lvl = self._classify_sample(val, q_upper, q_lower)
                    symbols.append(lvl)
                    bit_chunks.append(self.encoding_table[lvl])
                    level_counts[lvl] += 1

        full_bits = "".join(bit_chunks)

        threshold_metadata: Dict[str, Union[float, List[float]]]
        if len(q_uppers) == 1:
            threshold_metadata = {
                "q_upper": q_uppers[0],
                "q_lower": q_lowers[0],
                "mean": means[0],
                "std": stds[0],
            }
        else:
            threshold_metadata = {
                "q_upper": q_uppers,
                "q_lower": q_lowers,
                "mean": means,
                "std": stds,
                "num_segments": len(q_uppers),
            }

        return QuantizationResult(
            symbols=symbols,
            bits=full_bits,
            num_samples=n,
            retained_samples=n,
            discarded_samples=0,
            bit_length=len(full_bits),
            thresholds=threshold_metadata,
            level_counts=level_counts,
            parameters={
                "alpha": self.alpha,
                "bit_depth": self.bit_depth,
                "segment_size": self.segment_size,
                "encoding_table": self.encoding_table,
            },
        )

    def _classify_sample(
        self,
        val: float,
        q_upper: float,
        q_lower: float,
    ) -> int:
        """Classify a single sample into Level 0, 1, or 2 (all samples retained)."""
        if val > q_upper:
            return 2
        elif val < q_lower:
            return 0
        else:
            return 1


def compute_key_agreement_rate(key_a: Union[str, List[int]], key_b: Union[str, List[int]]) -> float:
    """
    Compute Key Agreement Rate (KAR) between two key bit sequences (LoRa-PRIME Eq. 7).

    KAR = (1 / n) * sum_{i=1}^n I(K_A[i] == K_B[i])

    Args:
        key_a: Bit string or list of bits from user A (e.g. Alice).
        key_b: Bit string or list of bits from user B (e.g. Bob).

    Returns:
        KAR as float in [0.0, 1.0].
    """
    if len(key_a) != len(key_b):
        raise ValueError(f"Key lengths do not match: len(A)={len(key_a)}, len(B)={len(key_b)}")
    if len(key_a) == 0:
        return 1.0

    matches = sum(1 for a, b in zip(key_a, key_b) if a == b)
    return float(matches / len(key_a))


def compute_bit_error_rate(key_a: Union[str, List[int]], key_b: Union[str, List[int]]) -> float:
    """
    Compute Bit Error Rate (BER) = 1.0 - KAR.
    """
    return float(1.0 - compute_key_agreement_rate(key_a, key_b))


def compute_key_generation_rate(
    bit_length: int,
    duration_seconds: Optional[float] = None,
    num_samples: Optional[int] = None,
) -> Dict[str, float]:
    """
    Calculate Key Generation Rate (KGR) metrics.

    Args:
        bit_length: Total number of generated bits.
        duration_seconds: Optional elapsed duration in seconds.
        num_samples: Optional total number of input samples.

    Returns:
        Dictionary containing bits, bits_per_sample, and bps (if duration provided).
    """
    res: Dict[str, float] = {"total_bits": float(bit_length)}
    if num_samples is not None and num_samples > 0:
        res["bits_per_sample"] = float(bit_length / num_samples)
    if duration_seconds is not None and duration_seconds > 0:
        res["bps"] = float(bit_length / duration_seconds)
    return res
