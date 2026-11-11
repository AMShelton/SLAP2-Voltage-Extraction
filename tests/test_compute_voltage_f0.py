from __future__ import annotations

import numpy as np
import pytest

baseline = pytest.importorskip(
    "slap2_voltage_extraction.source_extraction.compute_voltage_f0"
)
compute_voltage_f0 = baseline.compute_voltage_f0


def params(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "f0_method": "static",
        "f0_percentile": 50,
        "f0_bin_s": 1,
        "f0_smooth_s": 1,
        "precision": "single",
    }
    values.update(overrides)
    return values


def assert_code(exc: BaseException, code: str) -> None:
    assert getattr(exc, "code", None) == code or code in str(exc)


class TestComputeVoltageF0:
    def test_static_percentile_ignores_nonfinite_samples(self) -> None:
        raw = np.array([1, np.nan, 2, np.inf, 3, -np.inf], dtype=np.float32)
        f0, meta = compute_voltage_f0(raw, 1000, params())
        np.testing.assert_array_equal(f0, np.full(raw.shape, 2, dtype=np.float32))
        assert meta["method"] == "static_percentile"
        assert meta["percentile"] == 50
        assert meta["sample_rate_hz"] == 1000
        assert meta["time_varying"] is False

    def test_static_canonicalizes_row_and_column_vectors(self) -> None:
        row = np.array([[1, 2, 3]], dtype=np.float32)
        column = row.T
        row_f0, _ = compute_voltage_f0(row, 10, params())
        column_f0, _ = compute_voltage_f0(column, 10, params())
        assert row_f0.shape == (3,)
        assert column_f0.shape == (3,)
        np.testing.assert_array_equal(row_f0, np.full(3, 2, dtype=np.float32))
        np.testing.assert_array_equal(column_f0, row_f0)

    def test_static_rejects_nonvector_matrix_input(self) -> None:
        raw = np.array([[1, 3], [2, 4]], dtype=np.float32)
        with pytest.raises(ValueError):
            compute_voltage_f0(raw, 10, params())

    @pytest.mark.parametrize(("precision", "dtype"), [("single", np.float32), ("double", np.float64)])
    def test_precision_controls_output_class(self, precision: str, dtype: type[np.floating]) -> None:
        f0, _ = compute_voltage_f0(np.array([2, 4, 6], dtype=np.uint16), 10, params(precision=precision))
        assert f0.dtype == dtype
        np.testing.assert_array_equal(f0, np.full(3, 4, dtype=dtype))

    def test_zero_baseline_uses_median_absolute_fallback(self) -> None:
        f0, _ = compute_voltage_f0(np.array([-2, 0, 2], dtype=np.float32), 10, params())
        np.testing.assert_array_equal(f0, np.full(3, 2, dtype=np.float32))

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (np.array([np.nan, np.inf, -np.inf], dtype=np.float32), np.ones(3, dtype=np.float32)),
            (np.zeros(2, dtype=np.float32), np.ones(2, dtype=np.float32)),
        ],
    )
    def test_all_nonfinite_and_all_zero_inputs_use_unit_fallback(
        self, raw: np.ndarray, expected: np.ndarray
    ) -> None:
        f0, _ = compute_voltage_f0(raw, 10, params())
        np.testing.assert_array_equal(f0, expected)

    def test_empty_input_returns_before_validation(self) -> None:
        f0, meta = compute_voltage_f0(
            np.empty(0, dtype=np.float32), -1, params(f0_method="robust", precision="double")
        )
        assert f0.shape == (0,)
        assert f0.dtype == np.float64
        assert meta == {"method": "robust", "sample_rate_hz": -1}

    def test_robust_single_bin_falls_back_to_static_metadata(self) -> None:
        f0, meta = compute_voltage_f0(
            np.array([2, 4, 6], dtype=np.float32),
            1,
            params(f0_method="robust", f0_bin_s=10, f0_smooth_s=30),
        )
        np.testing.assert_array_equal(f0, np.full(3, 4, dtype=np.float32))
        assert meta["method"] == "static_percentile"
        assert meta["time_varying"] is False
        assert "n_bins" not in meta

    def test_robust_interpolation_and_endpoint_extension(self) -> None:
        f0, meta = compute_voltage_f0(
            np.array([10, 10, 20, 20], dtype=np.float32),
            2,
            params(f0_method="robust", f0_bin_s=1, f0_smooth_s=1),
        )
        np.testing.assert_allclose(f0, [10, 12.5, 17.5, 20], atol=1e-6, rtol=0)
        assert meta == {
            "method": "robust_binned_percentile_moving_median",
            "percentile": 50,
            "bin_s": 1,
            "smooth_s": 1,
            "bin_samples": 2,
            "smooth_bins": 1,
            "n_bins": 2,
            "sample_rate_hz": 2,
            "time_varying": True,
        }

    def test_robust_moving_median_rounds_even_window_up_to_odd(self) -> None:
        f0, meta = compute_voltage_f0(
            np.array([1, 100, 3, 4], dtype=np.float32),
            1,
            params(f0_method="robust", f0_smooth_s=2),
        )
        assert meta["smooth_bins"] == 3
        np.testing.assert_allclose(f0, [50.5, 3, 4, 3.5], atol=1e-6, rtol=0)

    def test_robust_missing_bins_are_linearly_filled(self) -> None:
        f0, _ = compute_voltage_f0(
            np.array([1, np.nan, 3], dtype=np.float32), 1, params(f0_method="robust")
        )
        np.testing.assert_allclose(f0, [1, 2, 3], atol=1e-6, rtol=0)

    def test_robust_missing_endpoint_bins_use_constant_extension(self) -> None:
        f0, _ = compute_voltage_f0(
            np.array([np.nan, 1, np.nan, 3, np.nan], dtype=np.float32),
            1,
            params(f0_method="robust"),
        )
        np.testing.assert_allclose(f0, [1, 1, 2, 3, 3], atol=1e-6, rtol=0)

    def test_robust_partial_final_bin_metadata(self) -> None:
        f0, meta = compute_voltage_f0(
            np.array([1, 1, 1, 5, 5], dtype=np.float32),
            2,
            params(f0_method="robust", f0_bin_s=2, f0_smooth_s=2, precision="double"),
        )
        assert f0.shape == (5,)
        assert f0.dtype == np.float64
        assert meta["bin_samples"] == 4
        assert meta["n_bins"] == 2
        np.testing.assert_array_equal(f0[[0, -1]], [1, 5])

    def test_default_parameters_are_used_when_omitted(self) -> None:
        raw = np.full(20, 7, dtype=np.float32)
        f0, meta = compute_voltage_f0(raw, 10)
        np.testing.assert_array_equal(f0, raw)
        assert f0.dtype == np.float32
        assert meta["method"] == "static_percentile"
        assert meta["percentile"] == 50

    def test_unknown_method_error(self) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_f0(np.ones(2, dtype=np.float32), 1, params(f0_method="unknown"))
        assert_code(caught.value, "computeVoltageF0:UnknownMethod")

    @pytest.mark.parametrize("sample_rate", [0, -1, np.nan, np.inf, [1, 2], 1 + 1j, "10"])
    def test_invalid_nonempty_sample_rates_fail_validation(self, sample_rate: object) -> None:
        with pytest.raises(Exception):
            compute_voltage_f0(np.ones(2, dtype=np.float32), sample_rate, params())


class TestComputeVoltageF0Regression:
    def test_static_constant(self) -> None:
        raw = np.full(100, 5, dtype=np.float32)
        f0, meta = compute_voltage_f0(raw, 1000, params())
        np.testing.assert_array_equal(f0, raw)
        assert meta["time_varying"] is False

    def test_robust_constant(self) -> None:
        raw = np.full(1000, 7, dtype=np.float32)
        f0, meta = compute_voltage_f0(
            raw, 100, params(f0_method="robust", f0_bin_s=1, f0_smooth_s=3)
        )
        np.testing.assert_allclose(f0, raw, atol=1e-6, rtol=0)
        assert meta["time_varying"] is True
