"""Tests for Pearson correlation calculation according to PA.pdf Eq (3.62)."""

import math
import pytest
from scipy import stats

from rssi_skg.correlation import pearson_correlation


def test_perfect_positive_correlation() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 20.0, 30.0, 40.0, 50.0]

    rho = pearson_correlation(x, y)
    ref_rho = stats.pearsonr(x, y).statistic

    assert math.isclose(rho, 1.0, rel_tol=1e-12)
    assert math.isclose(rho, ref_rho, rel_tol=1e-12)


def test_perfect_negative_correlation() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [-3.0, -6.0, -9.0, -12.0, -15.0]

    rho = pearson_correlation(x, y)
    ref_rho = stats.pearsonr(x, y).statistic

    assert math.isclose(rho, -1.0, rel_tol=1e-12)
    assert math.isclose(rho, ref_rho, rel_tol=1e-12)


def test_known_zero_correlation() -> None:
    # Orthogonal centered vectors: sum(x)=0, sum(y)=0, sum(x*y)=0
    x = [1.0, -1.0, 1.0, -1.0]
    y = [1.0, 1.0, -1.0, -1.0]

    rho = pearson_correlation(x, y)
    ref_rho = stats.pearsonr(x, y).statistic

    assert math.isclose(rho, 0.0, abs_tol=1e-12)
    assert math.isclose(ref_rho, 0.0, abs_tol=1e-12)


def test_constant_input_raises_explicit_error() -> None:
    # Constant x series has zero variance -> undefined correlation
    x_const = [-50.0, -50.0, -50.0, -50.0]
    y_var = [-45.0, -48.0, -52.0, -49.0]

    with pytest.raises(ValueError, match="undefined for constant input.*zero variance"):
        pearson_correlation(x_const, y_var)

    with pytest.raises(ValueError, match="undefined for constant input.*zero variance"):
        pearson_correlation(y_var, x_const)


def test_unequal_lengths_raises_error() -> None:
    x = [1.0, 2.0, 3.0]
    y = [1.0, 2.0]

    with pytest.raises(ValueError, match="must have identical length"):
        pearson_correlation(x, y)


def test_fewer_than_two_samples_raises_error() -> None:
    with pytest.raises(ValueError, match="At least two paired observations"):
        pearson_correlation([10.0], [20.0])

    with pytest.raises(ValueError, match="At least two paired observations"):
        pearson_correlation([], [])


def test_non_finite_or_nan_raises_error() -> None:
    with pytest.raises(ValueError, match="Non-finite value"):
        pearson_correlation([1.0, float("nan"), 3.0], [4.0, 5.0, 6.0])

    with pytest.raises(ValueError, match="Non-finite value"):
        pearson_correlation([1.0, 2.0, 3.0], [4.0, float("inf"), 6.0])


def test_scipy_reference_comparison() -> None:
    # Arbitrary realistic RSSI sequence
    x = [-45.5, -46.2, -44.1, -47.0, -48.3, -45.0, -46.8]
    y = [-46.0, -45.9, -43.8, -47.5, -48.0, -45.2, -47.1]

    rho = pearson_correlation(x, y)
    ref_rho = stats.pearsonr(x, y).statistic

    assert math.isclose(rho, ref_rho, rel_tol=1e-12)
