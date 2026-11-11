from __future__ import annotations

import numpy as np
import pytest

normalization = pytest.importorskip(
    "slap2_voltage_extraction.source_extraction.compute_voltage_dff"
)
compute_voltage_dff = normalization.compute_voltage_dff


def assert_code(exc: BaseException, code: str) -> None:
    assert getattr(exc, "code", None) == code or code in str(exc)


class TestComputeVoltageDFF:
    def test_auto_asap8_uses_increasing_formula(self) -> None:
        dff, meta = compute_voltage_dff(
            np.array([100, 110, 90], dtype=np.float32),
            np.full(3, 100, dtype=np.float32),
            "ASAP8",
            "auto",
            "single",
        )
        np.testing.assert_allclose(dff, [0, 0.1, -0.1], atol=1e-6, rtol=0)
        assert meta == {
            "indicator_name": "ASAP8",
            "indicator_direction_requested": "auto",
            "indicator_direction_resolved": "increases",
            "direction_source": "indicator_name",
            "dff_sign": 1,
            "formula": "dff = (F - F0) / F0",
        }

    def test_auto_asap7_uses_decreasing_formula(self) -> None:
        dff, meta = compute_voltage_dff(
            np.array([100, 90, 110], dtype=np.float32),
            np.full(3, 100, dtype=np.float32),
            "AsAp7y",
            "auto",
            "single",
        )
        np.testing.assert_allclose(dff, [0, 0.1, -0.1], atol=1e-6, rtol=0)
        assert meta["indicator_direction_resolved"] == "decreases"
        assert meta["direction_source"] == "indicator_name"
        assert meta["dff_sign"] == -1
        assert meta["formula"] == "dff = (F0 - F) / F0"

    @pytest.mark.parametrize("alias", ["increases", "increase", "standard", "positive", "brightens"])
    def test_explicit_increasing_aliases(self, alias: str) -> None:
        dff, meta = compute_voltage_dff(np.float32(12), np.float32(10), "unknown", alias, "single")
        np.testing.assert_allclose(dff, np.float32(0.2), atol=1e-6, rtol=0)
        assert meta["indicator_direction_resolved"] == "increases"
        assert meta["direction_source"] == "explicit"
        assert meta["indicator_direction_requested"] == alias

    @pytest.mark.parametrize(
        "alias", ["decreases", "decrease", "inverted", "negative", "quenched", "quenching", " DECREASE "]
    )
    def test_explicit_decreasing_aliases_and_normalization(self, alias: str) -> None:
        dff, meta = compute_voltage_dff(np.float32(8), np.float32(10), "unknown", alias, "single")
        np.testing.assert_allclose(dff, np.float32(0.2), atol=1e-6, rtol=0)
        assert meta["indicator_direction_resolved"] == "decreases"
        assert meta["direction_source"] == "explicit"

    def test_explicit_direction_overrides_indicator_name(self) -> None:
        dff, meta = compute_voltage_dff(np.float32(12), np.float32(10), "ASAP7", "increases", "single")
        np.testing.assert_allclose(dff, np.float32(0.2), atol=1e-6, rtol=0)
        assert meta["direction_source"] == "explicit"

    def test_direction_trims_whitespace_and_ignores_case(self) -> None:
        requested = " PoSiTiVe "
        _, meta = compute_voltage_dff(np.float32(12), np.float32(10), "unknown", requested, "single")
        assert meta["indicator_direction_requested"] == requested
        assert meta["indicator_direction_resolved"] == "increases"

    @pytest.mark.parametrize("direction", ["posi-tive", "quench ing"])
    def test_embedded_hyphens_and_spaces_are_invalid(self, direction: str) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_dff(np.float32(1), np.float32(1), "unknown", direction, "single")
        assert_code(caught.value, "computeVoltageDFF:InvalidDirection")

    def test_bad_baselines_use_median_absolute_raw_fallback(self) -> None:
        dff, _ = compute_voltage_dff(
            np.array([2, 4, 6], dtype=np.float32),
            np.array([0, np.nan, np.inf], dtype=np.float32),
            "unknown",
            "increases",
            "single",
        )
        np.testing.assert_allclose(dff, [-0.5, 0, 0.5], atol=1e-6, rtol=0)

    def test_all_zero_raw_uses_unit_fallback(self) -> None:
        dff, _ = compute_voltage_dff(
            np.zeros(2, dtype=np.float32),
            np.array([0, np.nan], dtype=np.float32),
            "unknown",
            "increases",
            "single",
        )
        np.testing.assert_array_equal(dff, np.full(2, -1, dtype=np.float32))

    def test_negative_finite_baseline_is_not_replaced(self) -> None:
        dff, _ = compute_voltage_dff(
            np.array([-12, -8], dtype=np.float32),
            np.array([-10, -10], dtype=np.float32),
            "unknown",
            "increases",
            "single",
        )
        np.testing.assert_allclose(dff, [0.2, -0.2], atol=1e-6, rtol=0)

    def test_raw_nan_propagates_to_output(self) -> None:
        dff, _ = compute_voltage_dff(
            np.array([10, np.nan, 12], dtype=np.float32),
            np.full(3, 10, dtype=np.float32),
            "unknown",
            "increases",
            "single",
        )
        np.testing.assert_allclose(dff[[0, 2]], [0, 0.2], atol=1e-6, rtol=0)
        assert np.isnan(dff[1])

    def test_output_preserves_multidimensional_shape(self) -> None:
        raw = np.arange(1, 25, dtype=np.float32).reshape((2, 3, 4))
        expected = (raw - np.float32(10)) / np.float32(10)
        dff, _ = compute_voltage_dff(raw, np.full(raw.shape, 10, dtype=np.float32), "unknown", "increases", "single")
        assert dff.shape == (2, 3, 4)
        np.testing.assert_allclose(dff, expected, atol=1e-6, rtol=0)

    @pytest.mark.parametrize(
        ("precision", "dtype"), [("single", np.float32), ("double", np.float64), ("half", np.float32)]
    )
    def test_precision_and_input_casting_behavior(self, precision: str, dtype: type[np.floating]) -> None:
        dff, _ = compute_voltage_dff(
            np.array([10, 12], dtype=np.uint16),
            np.array([10, 10], dtype=np.float64),
            "unknown",
            "increases",
            precision,
        )
        assert dff.dtype == dtype
        np.testing.assert_allclose(dff, [0, 0.2], atol=1e-6, rtol=0)

    def test_empty_inputs_return_empty_with_metadata(self) -> None:
        dff, meta = compute_voltage_dff(
            np.empty(0, dtype=np.float32), np.empty(0, dtype=np.float32), "ASAP8", "increases", "double"
        )
        assert dff.shape == (0,)
        assert dff.dtype == np.float64
        assert meta["indicator_name"] == "ASAP8"
        assert meta["indicator_direction_requested"] == "increases"
        assert meta["dff_sign"] == 1

    def test_optional_arguments_default_before_direction_resolution(self) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_dff(np.float32(1), np.float32(1))
        assert_code(caught.value, "computeVoltageDFF:UnknownIndicatorDirection")
        dff, meta = compute_voltage_dff(np.float32(2), np.float32(1), "ASAP8", None, None)
        assert np.asarray(dff).dtype == np.float32
        np.testing.assert_allclose(dff, np.float32(1), atol=1e-6, rtol=0)
        assert meta["indicator_direction_requested"] == "auto"

    @pytest.mark.parametrize(
        ("raw", "f0"),
        [
            (np.array([[1, 2]], dtype=np.float32), np.array([[1], [2]], dtype=np.float32)),
            (np.array([[1, 2]], dtype=np.float32), np.float32(1)),
            (np.ones((2, 2), dtype=np.float32), np.ones((2, 2, 1, 2), dtype=np.float32)),
        ],
    )
    def test_size_mismatch_error(self, raw: np.ndarray, f0: np.ndarray) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_dff(raw, f0, "ASAP8", "auto", "single")
        assert_code(caught.value, "computeVoltageDFF:SizeMismatch")

    def test_unknown_auto_direction_error(self) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_dff(np.float32(1), np.float32(1), "unknown", "auto", "single")
        assert_code(caught.value, "computeVoltageDFF:UnknownIndicatorDirection")

    @pytest.mark.parametrize("direction", ["sideways", "increasing"])
    def test_invalid_direction_error(self, direction: str) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_dff(np.float32(1), np.float32(1), "unknown", direction, "single")
        assert_code(caught.value, "computeVoltageDFF:InvalidDirection")

    def test_auto_prefers_asap8_when_name_contains_both_families(self) -> None:
        dff, meta = compute_voltage_dff(np.float32(12), np.float32(10), "ASAP7-ASAP8", "auto", "single")
        np.testing.assert_allclose(dff, np.float32(0.2), atol=1e-6, rtol=0)
        assert meta["indicator_direction_resolved"] == "increases"


class TestComputeVoltageDFFRegression:
    @pytest.mark.parametrize(
        ("raw", "indicator", "expected_sign"),
        [
            (np.array([100, 110, 90], dtype=np.float32), "ASAP8", 1),
            (np.array([100, 90, 110], dtype=np.float32), "ASAP7y", -1),
        ],
    )
    def test_asap_regressions(self, raw: np.ndarray, indicator: str, expected_sign: int) -> None:
        dff, meta = compute_voltage_dff(raw, np.full(3, 100, dtype=np.float32), indicator, "auto", "single")
        np.testing.assert_allclose(dff, [0, 0.1, -0.1], atol=1e-6, rtol=0)
        assert meta["dff_sign"] == expected_sign

    def test_unknown_auto_fails(self) -> None:
        with pytest.raises(Exception) as caught:
            compute_voltage_dff(np.float32(1), np.float32(1), "unknown", "auto", "single")
        assert_code(caught.value, "computeVoltageDFF:UnknownIndicatorDirection")
