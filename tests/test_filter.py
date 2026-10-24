"""Tests for Modified Sage–Husa Adaptive Kalman Filter (MSHKF).

Verifies implementation against PA.pdf Section 3.2.2, Equations (3.10)–(3.20):
- Step-by-step intermediate calculation validation against independent numerical example.
- Strict channel isolation across independent filter states.
- Sample indexing policy avoiding double-counting of first observation.
- Numerical safeguards and finite input validation.
- End-to-end integration with dummy dataset and CLI.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import pytest

from rssi_skg.cli import main, run_correlation_analysis
from rssi_skg.filter import (
    FilterConfig,
    ModifiedSageHusaFilter,
    filter_rssi_channels,
)
from rssi_skg.loader import load_rssi_workbook


def test_step_by_step_independent_numerical_example() -> None:
    """Validate all intermediate filter variables against an independently computed 2-step example.

    Ground-truth parameters:
        b = 0.99, D0 = 1.0, x0 = -80.0 dBm, P0 = 1.0 dBm^2,
        q0 = 0.0 dBm, r0 = 0.0 dBm, Q = 0.1 dBm^2, R0 = 1.0 dBm^2.

    Observations:
        Z_1 = -79.0 dBm, Z_2 = -78.0 dBm.
    """
    cfg = FilterConfig(
        b=0.99,
        d0=1.0,
        q=0.1,
        r0=1.0,
        p0=1.0,
        q0=0.0,
        r0_mean=0.0,
        phi=1.0,
        h=1.0,
    )

    kf = ModifiedSageHusaFilter(config=cfg)
    kf.initialize_state(initial_x=-80.0)

    # --- STEP 1 ---
    # 1. D_1 = 1.0 / (1.0 + 0.99) = 100/199 ~ 0.502512562814
    # 2. X_pred = -80.0 + 0 = -80.0
    # 3. P_pred = 1.0 + 0.1 = 1.1
    # 4. r_1 = (1 - D_1)*0 + D_1*(-79.0 - (-80.0)) = 100/199 ~ 0.502512562814
    # 5. e_1 = -79.0 - (-80.0) - r_1 = 1.0 - 100/199 = 99/199 ~ 0.497487437186
    # 6. R_1 = (1 - D_1)*1.0 + D_1*(e_1^2) ~ 0.621856155858
    # 7. K_1 = 1.1 / (1.1 + R_1) ~ 0.638845467002
    # 8. X_1 = -80.0 + K_1 * e_1 ~ -79.682182405863
    # 9. P_1 = (1 - K_1) * 1.1 ~ 0.397269986298
    # 10. q_1 = (1 - D_1)*0 + D_1*(X_1 - (-80.0)) ~ 0.159707333737
    x1, rec1 = kf.step(-79.0)

    assert math.isclose(rec1.d_k, 1.0 / 1.99, rel_tol=1e-11)
    assert math.isclose(rec1.x_pred, -80.0, rel_tol=1e-11)
    assert math.isclose(rec1.p_pred, 1.1, rel_tol=1e-11)
    assert math.isclose(rec1.r_k, 0.5025125628140703, rel_tol=1e-11)
    assert math.isclose(rec1.e_k, 0.49748743718592964, rel_tol=1e-11)
    assert math.isclose(rec1.r_cov_k, 0.6218561558580879, rel_tol=1e-11)
    assert math.isclose(rec1.k_gain, 0.6388454670018597, rel_tol=1e-11)
    assert math.isclose(rec1.x_est, -79.68218240586326, rel_tol=1e-11)
    assert math.isclose(x1, -79.68218240586326, rel_tol=1e-11)
    assert math.isclose(rec1.p_est, 0.3972699862979544, rel_tol=1e-11)
    assert math.isclose(rec1.q_k, 0.15970733373722254, rel_tol=1e-11)

    # --- STEP 2 ---
    # With observation Z_2 = -78.0
    x2, rec2 = kf.step(-78.0)

    assert math.isclose(rec2.d_k, 0.3366890003704381, rel_tol=1e-11)
    assert math.isclose(rec2.x_pred, -79.52247507212604, rel_tol=1e-11)
    assert math.isclose(rec2.p_pred, 0.4972699862979544, rel_tol=1e-11)
    assert math.isclose(rec2.r_k, 0.8459227204901962, rel_tol=1e-11)
    assert math.isclose(rec2.e_k, 0.6765523516358437, rel_tol=1e-11)
    assert math.isclose(rec2.r_cov_k, 0.5665943561373574, rel_tol=1e-11)
    assert math.isclose(rec2.k_gain, 0.4674186044814524, rel_tol=1e-11)
    assert math.isclose(rec2.x_est, -79.20624191606552, rel_tol=1e-11)
    assert math.isclose(x2, -79.20624191606552, rel_tol=1e-11)
    assert math.isclose(rec2.p_est, 0.2648367432523297, rel_tol=1e-11)
    assert math.isclose(rec2.q_k, 0.2661795589347895, rel_tol=1e-11)


def test_channel_isolation() -> None:
    """Verify strict channel isolation: filtering a channel is completely independent of other channels."""
    channel_a = [-75.0, -74.0, -76.0, -73.0, -75.0]
    channel_b = [-30.0, -32.0, -31.0, -29.0, -30.0]
    channel_c = [-85.0, -84.0, -86.0, -85.0, -83.0]

    cfg = FilterConfig()

    # Filter isolated
    filt_a_alone = filter_rssi_channels({"A": channel_a}, config=cfg)["A"]
    filt_b_alone = filter_rssi_channels({"B": channel_b}, config=cfg)["B"]
    filt_c_alone = filter_rssi_channels({"C": channel_c}, config=cfg)["C"]

    # Filter grouped in forward order
    grouped_fwd = filter_rssi_channels({"A": channel_a, "B": channel_b, "C": channel_c}, config=cfg)
    assert grouped_fwd["A"] == filt_a_alone
    assert grouped_fwd["B"] == filt_b_alone
    assert grouped_fwd["C"] == filt_c_alone

    # Filter grouped in reverse order
    grouped_rev = filter_rssi_channels({"C": channel_c, "B": channel_b, "A": channel_a}, config=cfg)
    assert grouped_rev["A"] == filt_a_alone
    assert grouped_rev["B"] == filt_b_alone
    assert grouped_rev["C"] == filt_c_alone


def test_sample_indexing_no_double_counting() -> None:
    """Verify that auto-initialization from z[0] starts updates from sample 1 and does not double-count."""
    series = [-80.0, -79.0, -78.0]
    cfg = FilterConfig(x0=None)

    kf = ModifiedSageHusaFilter(config=cfg)
    filtered = kf.filter_series(series)

    # First output must be exactly z[0] without filtering update
    assert filtered[0] == -80.0

    # Second output must be the result of filtering z[1] with initial state z[0]
    # which matches the Step 1 from test_step_by_step_independent_numerical_example
    assert math.isclose(filtered[1], -79.68218240586326, rel_tol=1e-11)
    assert math.isclose(filtered[2], -79.20624191606552, rel_tol=1e-11)


def test_explicit_x0_prior_processes_all_samples() -> None:
    """Verify that when an explicit x0 prior is provided, sample 0 is processed as measurement 1."""
    series = [-79.0, -78.0]
    cfg = FilterConfig(x0=-80.0)

    kf = ModifiedSageHusaFilter(config=cfg)
    filtered = kf.filter_series(series)

    assert len(filtered) == 2
    assert math.isclose(filtered[0], -79.68218240586326, rel_tol=1e-11)
    assert math.isclose(filtered[1], -79.20624191606552, rel_tol=1e-11)


def test_constant_input_behavior() -> None:
    """Verify that constant input series remains constant and stable."""
    series = [-75.0, -75.0, -75.0, -75.0, -75.0]
    kf = ModifiedSageHusaFilter()
    filtered = kf.filter_series(series)

    assert len(filtered) == 5
    for val in filtered:
        assert math.isclose(val, -75.0, abs_tol=1e-12)


def test_numerical_safeguard_non_finite_or_negative_covariance_raises_error() -> None:
    """Verify that non-finite or negative covariances trigger explicit FloatingPointError."""
    kf = ModifiedSageHusaFilter()
    kf.initialize_state(initial_x=-70.0)

    # Artificially set an illegal non-finite error covariance state
    kf.p_est = float("nan")
    with pytest.raises(FloatingPointError, match="non-finite or negative"):
        kf.step(-70.0)


def test_invalid_filter_config_raises_error() -> None:
    """Verify that illegal configuration parameters raise ValueError."""
    with pytest.raises(ValueError, match="Forgetting factor b"):
        FilterConfig(b=0.0)

    with pytest.raises(ValueError, match="Forgetting factor b"):
        FilterConfig(b=1.0)

    with pytest.raises(ValueError, match="Initial weight d0"):
        FilterConfig(d0=-1.0)

    with pytest.raises(ValueError, match="Process noise covariance q"):
        FilterConfig(q=0.0)

    with pytest.raises(ValueError, match="Initial measurement noise covariance r0"):
        FilterConfig(r0=-0.5)

    with pytest.raises(ValueError, match="Initial error covariance p0"):
        FilterConfig(p0=-1.0)

    with pytest.raises(ValueError, match="Phi must be non-zero"):
        FilterConfig(phi=0.0)

    with pytest.raises(ValueError, match="H must be non-zero"):
        FilterConfig(h=0.0)


def test_non_finite_inputs_raise_error() -> None:
    """Verify that NaN and Inf in series raise ValueError with index."""
    kf = ModifiedSageHusaFilter()

    with pytest.raises(ValueError, match="Non-finite value"):
        kf.filter_series([-70.0, float("nan"), -72.0])

    with pytest.raises(ValueError, match="Non-finite value"):
        kf.filter_series([-70.0, float("inf"), -72.0])

    with pytest.raises(ValueError, match="Invalid non-numeric value"):
        kf.filter_series([-70.0, "bad_val", -72.0])  # type: ignore[list-item]

    with pytest.raises(ValueError, match="Series must contain at least 2 samples"):
        kf.filter_series([-70.0])


def test_filter_dummy_dataset_integrity() -> None:
    """Verify filter execution on the real 500-sample dummy dataset."""
    dummy_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    assert dummy_path.is_file()

    data = load_rssi_workbook(dummy_path)
    cfg = FilterConfig()
    filtered = filter_rssi_channels(data, config=cfg)

    for col in ("Alice", "Bob", "Eve1-Alice", "Eve1-Bob"):
        assert len(filtered[col]) == 500
        assert all(math.isfinite(val) for val in filtered[col])

    # Raw data must not have been mutated
    assert len(data["Alice"]) == 500
    assert data["Alice"][0] == -80.0


def test_cli_filtering_artifacts_export(tmp_path: Path) -> None:
    """Verify CLI with --filter exports all requested artifacts with proper contents."""
    dummy_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
    csv_out = tmp_path / "filtered_corr.csv"
    samples_out = tmp_path / "aligned_samples.csv"
    meta_out = tmp_path / "filter_meta.json"
    fig_prefix = tmp_path / "comparison_figure"

    results, fig_paths = run_correlation_analysis(
        input_path=dummy_path,
        output_path=csv_out,
        figure_prefix=fig_prefix,
        data_kind="dummy",
        enable_filter=True,
        filtered_samples_output=samples_out,
        filter_config_output=meta_out,
    )

    # 1. Verify results structure
    assert len(results) == 3
    for r in results:
        assert "raw_correlation" in r
        assert "filtered_correlation" in r
        assert "correlation_delta" in r
        assert r["sample_count"] == 500

    # 2. Verify correlation CSV
    assert csv_out.is_file()
    with open(csv_out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        assert "raw_correlation" in rows[0]
        assert "filtered_correlation" in rows[0]
        assert "correlation_delta" in rows[0]

    # 3. Verify aligned samples CSV
    assert samples_out.is_file()
    with open(samples_out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        assert "sample_index" in header
        assert "Alice_raw" in header
        assert "Alice_filtered" in header
        assert "Bob_raw" in header
        assert "Bob_filtered" in header
        assert "Eve1-Alice_raw" in header
        assert "Eve1-Alice_filtered" in header
        assert "Eve1-Bob_raw" in header
        assert "Eve1-Bob_filtered" in header
        sample_rows = list(reader)
        assert len(sample_rows) == 500

    # 4. Verify metadata JSON
    assert meta_out.is_file()
    with open(meta_out, encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["algorithm"] == "Modified Sage–Husa Adaptive Kalman Filter (Scalar MSHKF)"
        assert meta["parameters"]["b"]["value"] == 0.99
        assert meta["parameters"]["D0"]["value"] == 1.0
        assert meta["parameters"]["Q"]["value"] == 0.1
        assert "omission_of_adaptive_q_update" in meta["modeling_assumptions"]
        assert "sample_indexing_policy" in meta["modeling_assumptions"]

    # 5. Verify figures
    assert fig_paths is not None
    png_p, pdf_p = fig_paths
    assert png_p.is_file()
    assert pdf_p.is_file()
    assert png_p.stat().st_size > 1000
    assert pdf_p.stat().st_size > 1000


def test_cli_main_entrypoint_with_filter(tmp_path: Path) -> None:
    """Verify executing CLI main() with --filter arguments runs successfully."""
    dummy_path = "data/raw/dummy/Dummy RSSI (data Indoor).xlsx"
    csv_out = str(tmp_path / "cli_corr.csv")
    samples_out = str(tmp_path / "cli_samples.csv")
    meta_out = str(tmp_path / "cli_meta.json")
    fig_prefix = str(tmp_path / "cli_fig")

    ret = main(
        [
            "-i",
            dummy_path,
            "-o",
            csv_out,
            "--filter",
            "--filtered-samples-output",
            samples_out,
            "--filter-config-output",
            meta_out,
            "--figure-prefix",
            fig_prefix,
        ]
    )

    assert ret == 0
    assert Path(csv_out).is_file()
    assert Path(samples_out).is_file()
    assert Path(meta_out).is_file()
    assert Path(f"{fig_prefix}.png").is_file()
    assert Path(f"{fig_prefix}.pdf").is_file()
