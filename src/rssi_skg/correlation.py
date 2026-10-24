"""Pearson correlation calculation module.

Implements Pearson correlation coefficient according to PA.pdf, Equation (3.62), page 34:
    rho_{X, Y} = sum((X_i - mean(X)) * (Y_i - mean(Y))) /
                 (sqrt(sum((X_i - mean(X))^2)) * sqrt(sum((Y_i - mean(Y))^2)))
"""

from __future__ import annotations

import math
from typing import Sequence


def pearson_correlation(
    x: Sequence[float | int],
    y: Sequence[float | int],
) -> float:
    """Calculate Pearson correlation coefficient at zero lag between two series.

    Implements Equation (3.62), page 34 of PA.pdf using float64 arithmetic:
        rho = sum((x_i - mean_x) * (y_i - mean_y)) / (sqrt(sum((x_i - mean_x)^2)) * sqrt(sum((y_i - mean_y)^2)))

    Args:
        x: First series of numeric observations.
        y: Second series of numeric observations.

    Returns:
        float: Pearson correlation coefficient in [-1.0, 1.0].

    Raises:
        ValueError: If input series have unequal lengths, fewer than 2 samples,
            contain non-finite / NaN values, or if either series has zero variance (constant input).
    """
    n_x = len(x)
    n_y = len(y)

    if n_x != n_y:
        raise ValueError(
            f"Input series must have identical length: len(x)={n_x}, len(y)={n_y}."
        )

    if n_x < 2:
        raise ValueError(
            f"At least two paired observations are required to calculate Pearson correlation, got {n_x}."
        )

    # Convert to float64 and validate numeric finite values
    fx: list[float] = []
    fy: list[float] = []

    for i in range(n_x):
        val_x = x[i]
        val_y = y[i]

        try:
            f_val_x = float(val_x)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"Invalid non-numeric value in series X at index {i} (row {i + 2}): {val_x!r}."
            ) from err

        try:
            f_val_y = float(val_y)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"Invalid non-numeric value in series Y at index {i} (row {i + 2}): {val_y!r}."
            ) from err

        if not math.isfinite(f_val_x):
            raise ValueError(
                f"Non-finite value (NaN/Inf) encountered in series X at index {i} (row {i + 2}): {f_val_x}."
            )

        if not math.isfinite(f_val_y):
            raise ValueError(
                f"Non-finite value (NaN/Inf) encountered in series Y at index {i} (row {i + 2}): {f_val_y}."
            )

        fx.append(f_val_x)
        fy.append(f_val_y)

    # Compute means using float64 precision
    mean_x = math.fsum(fx) / float(n_x)
    mean_y = math.fsum(fy) / float(n_y)

    # Centered sums
    sum_xy = 0.0
    sum_xx = 0.0
    sum_yy = 0.0

    for i in range(n_x):
        dx = fx[i] - mean_x
        dy = fy[i] - mean_y
        sum_xy += dx * dy
        sum_xx += dx * dx
        sum_yy += dy * dy

    # Explicit check for constant input / zero variance (undefined correlation)
    if sum_xx == 0.0 or sum_yy == 0.0:
        constant_series = []
        if sum_xx == 0.0:
            constant_series.append("X")
        if sum_yy == 0.0:
            constant_series.append("Y")
        raise ValueError(
            f"Pearson correlation is undefined for constant input (zero variance in series: {', '.join(constant_series)})."
        )

    denominator = math.sqrt(sum_xx) * math.sqrt(sum_yy)
    if denominator == 0.0:
        raise ValueError(
            "Pearson correlation denominator evaluated to zero (zero variance)."
        )

    rho = sum_xy / denominator

    # Clamp small floating-point rounding errors to exact [-1.0, 1.0] interval
    if rho > 1.0:
        rho = 1.0
    elif rho < -1.0:
        rho = -1.0

    return rho
