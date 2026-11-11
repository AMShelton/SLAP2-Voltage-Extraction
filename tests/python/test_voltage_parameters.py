from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

parameters = pytest.importorskip(
    "dependencies.gui.set_params",
    reason="Python parameter translation has not been implemented yet",
)
set_params = parameters.set_params
asap7_params = pytest.importorskip("presets.asap7_params").asap7_params
asap8_params = pytest.importorskip("presets.asap8_params").asap8_params


EXPECTED_DEFAULTS = {
    "ch_idx": 0,
    "z_idx": 0,
    "trace_window_lines": 16,
    "trace_expected_window_lines": 5000,
    "indicator_name": "",
    "indicator_direction": "auto",
    "f0_method": "robust",
    "f0_percentile": 50,
    "f0_bin_s": 5,
    "f0_smooth_s": 180,
    "use_parallel": True,
    "n_workers": 4,
    "max_concurrent_rois": 2,
    "precision": "single",
    "output_dir": "",
    "output_filename": "VoltageSummary.h5",
    "overwrite": False,
    "h5_chunk_samples": 100000,
    "h5_deflate": 0,
    "motion_censor_enable": False,
    "motion_pixel_size_um": 0.25,
    "motion_median_window_s": 4,
    "motion_thresh": 2.5,
    "motion_scale_floor_um": 0.25,
    "motion_abs_max_um": 0,
    "motion_pad_s": 0.025,
    "motion_merge_gap_s": 0.05,
    "motion_discard_initial_s": 0,
    "motion_samples_per_cycle": 1,
    "motion_max_frac_censored": 0.25,
}


def _assert_code(exc: BaseException, code: str) -> None:
    assert getattr(exc, "code", None) == code or code in str(exc)


class TestVoltageParameters:
    def test_voltage_defaults(self) -> None:
        assert set_params("Voltage", {}) == EXPECTED_DEFAULTS

    def test_struct_overrides_are_merged_and_unknown_fields_survive(self) -> None:
        params = set_params(
            "Voltage",
            {
                "ch_idx": 1,
                "indicator_name": "ASAP8",
                "indicator_direction": "increases",
                "f0_method": "static",
                "precision": "double",
                "output_dir": "custom",
                "output_filename": "result.h5",
                "custom_metadata": 17,
            },
        )
        assert params["ch_idx"] == 1
        assert params["indicator_name"] == "ASAP8"
        assert params["indicator_direction"] == "increases"
        assert params["f0_method"] == "static"
        assert params["precision"] == "double"
        assert params["output_dir"] == "custom"
        assert params["output_filename"] == "result.h5"
        assert params["custom_metadata"] == 17
        assert params["trace_window_lines"] == 16

    def test_count_and_compression_values_are_rounded(self) -> None:
        params = set_params(
            "Voltage",
            {
                "n_workers": 2.6,
                "max_concurrent_rois": 1.5,
                "h5_chunk_samples": 10.6,
                "h5_deflate": 2.6,
            },
        )
        assert params["n_workers"] == 3
        assert params["max_concurrent_rois"] == 2
        assert params["h5_chunk_samples"] == 11
        assert params["h5_deflate"] == 3
        assert isinstance(params["n_workers"], int) and not isinstance(params["n_workers"], bool)

    def test_logical_flags_accept_logical_and_numeric_binary_values(self) -> None:
        numeric = set_params("Voltage", {"use_parallel": 0, "overwrite": 1})
        assert numeric["use_parallel"] is False
        assert numeric["overwrite"] is True
        logical = set_params("Voltage", {"use_parallel": True, "overwrite": False})
        assert logical["use_parallel"] is True
        assert logical["overwrite"] is False

    def test_json_text_input(self) -> None:
        params = set_params(
            "Voltage",
            '{"indicator_name":"ASAP7y","indicator_direction":"decreases",'
            '"n_workers":3.7,"use_parallel":false}',
        )
        assert params["indicator_name"] == "ASAP7y"
        assert params["indicator_direction"] == "decreases"
        assert params["n_workers"] == 4
        assert params["use_parallel"] is False

    def test_json_file_input(self, tmp_path: Path) -> None:
        path = tmp_path / "params.json"
        path.write_text(
            json.dumps({"f0_method": "static", "f0_percentile": 25, "precision": "double"}),
            encoding="utf-8",
        )
        params = set_params("Voltage", path)
        assert params["f0_method"] == "static"
        assert params["f0_percentile"] == 25
        assert params["precision"] == "double"

    @pytest.mark.parametrize(
        ("variable_name", "values", "expected"),
        [
            ("optsOut", {"indicator_name": "ASAP8", "indicator_direction": "increases"}, {"indicator_name": "ASAP8", "indicator_direction": "increases"}),
            ("params", {"f0_bin_s": 2, "f0_smooth_s": 7}, {"f0_bin_s": 2, "f0_smooth_s": 7}),
            ("customPreset", {"h5_chunk_samples": 12.7}, {"h5_chunk_samples": 13}),
        ],
    )
    def test_mat_file_inputs(
        self, tmp_path: Path, variable_name: str, values: dict[str, object], expected: dict[str, object]
    ) -> None:
        scipy_io = pytest.importorskip("scipy.io")
        path = tmp_path / f"{variable_name}.mat"
        scipy_io.savemat(path, {variable_name: values})
        params = set_params("Voltage", path)
        for key, value in expected.items():
            assert params[key] == value

    def test_asap7_preset_and_overrides(self) -> None:
        params = asap7_params()
        assert params["indicator_name"] == "ASAP7"
        assert params["indicator_direction"] == "decreases"
        assert params["f0_method"] == "robust"
        params = asap7_params({"indicator_name": "ASAP7b", "precision": "double", "f0_percentile": 20})
        assert params["indicator_name"] == "ASAP7b"
        assert params["indicator_direction"] == "decreases"
        assert params["precision"] == "double"
        assert params["f0_percentile"] == 20

    def test_asap8_preset_and_overrides(self) -> None:
        params = asap8_params()
        assert params["indicator_name"] == "ASAP8"
        assert params["indicator_direction"] == "increases"
        params = asap8_params({"indicator_direction": "decreases", "output_filename": "custom.h5"})
        assert params["indicator_name"] == "ASAP8"
        assert params["indicator_direction"] == "decreases"
        assert params["output_filename"] == "custom.h5"

    def test_unknown_function_error(self) -> None:
        with pytest.raises(Exception) as caught:
            set_params("NotVoltage", {})
        _assert_code(caught.value, "setParams:UnknownFunction")

    def test_invalid_input_type_error(self) -> None:
        with pytest.raises(Exception) as caught:
            set_params("Voltage", [{}])
        _assert_code(caught.value, "setParams:InvalidInput")

    def test_invalid_mat_preset_error(self, tmp_path: Path) -> None:
        scipy_io = pytest.importorskip("scipy.io")
        path = tmp_path / "invalid.mat"
        scipy_io.savemat(path, {"first": {"value": 1}, "second": 2})
        with pytest.raises(Exception) as caught:
            set_params("Voltage", path)
        _assert_code(caught.value, "setParams:InvalidPreset")

    @pytest.mark.parametrize("value", [-1, 0.5, 2, [0, 1], np.nan, "true"])
    def test_invalid_logical_values_error(self, value: object) -> None:
        with pytest.raises(Exception) as caught:
            set_params("Voltage", {"use_parallel": value})
        _assert_code(caught.value, "setParams:InvalidLogical")

    @pytest.mark.parametrize("value", ["", "   "])
    def test_invalid_output_filename_error(self, value: str) -> None:
        with pytest.raises(Exception) as caught:
            set_params("Voltage", {"output_filename": value})
        _assert_code(caught.value, "setParams:InvalidOutputFilename")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"indicator_direction": "sideways"},
            {"f0_method": "mean"},
            {"precision": "half"},
        ],
    )
    def test_invalid_choice_values_fail_validation(self, overrides: dict[str, object]) -> None:
        with pytest.raises(Exception):
            set_params("Voltage", overrides)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"ch_idx": -1},
            {"z_idx": 1.5},
            {"trace_window_lines": np.inf},
            {"trace_expected_window_lines": -1},
            {"f0_percentile": -1},
            {"f0_percentile": 101},
            {"f0_bin_s": 0},
            {"f0_smooth_s": np.nan},
            {"n_workers": 0},
            {"max_concurrent_rois": np.inf},
            {"h5_chunk_samples": 0},
            {"h5_deflate": -1},
            {"h5_deflate": 10},
        ],
    )
    def test_invalid_numeric_values_fail_validation(self, overrides: dict[str, object]) -> None:
        with pytest.raises(Exception):
            set_params("Voltage", overrides)
