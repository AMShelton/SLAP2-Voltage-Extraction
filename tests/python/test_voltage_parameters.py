from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

parameters = pytest.importorskip(
    "slap2_voltage_extraction.parameters",
    reason="Python parameter translation has not been implemented yet",
)
set_params = parameters.set_params
asap7_params = parameters.asap7_params
asap8_params = parameters.asap8_params


EXPECTED_DEFAULTS = {
    "chIdx": 1,
    "zIdx": 1,
    "traceWindow_lines": 16,
    "traceExpectedWindow_lines": 5000,
    "indicatorName": "",
    "indicatorDirection": "auto",
    "f0Method": "robust",
    "f0Percentile": 50,
    "f0Bin_s": 5,
    "f0Smooth_s": 180,
    "useParallel": True,
    "nWorkers": 4,
    "maxConcurrentROIs": 2,
    "precision": "single",
    "outputDir": "",
    "outputFilename": "VoltageSummary.h5",
    "overwrite": False,
    "h5ChunkSamples": 100000,
    "h5Deflate": 0,
    "motionCensorEnable": False,
    "motionPixelSize_um": 0.25,
    "motionMedianWindow_s": 4,
    "motionThresh": 2.5,
    "motionScaleFloor_um": 0.25,
    "motionAbsMax_um": 0,
    "motionPad_s": 0.025,
    "motionMergeGap_s": 0.05,
    "motionDiscardInitial_s": 0,
    "motionSamplesPerCycle": 1,
    "motionMaxFracCensored": 0.25,
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
                "chIdx": 2,
                "indicatorName": "ASAP8",
                "indicatorDirection": "increases",
                "f0Method": "static",
                "precision": "double",
                "outputDir": "custom",
                "outputFilename": "result.h5",
                "customMetadata": 17,
            },
        )
        assert params["chIdx"] == 2
        assert params["indicatorName"] == "ASAP8"
        assert params["indicatorDirection"] == "increases"
        assert params["f0Method"] == "static"
        assert params["precision"] == "double"
        assert params["outputDir"] == "custom"
        assert params["outputFilename"] == "result.h5"
        assert params["customMetadata"] == 17
        assert params["traceWindow_lines"] == 16

    def test_count_and_compression_values_are_rounded(self) -> None:
        params = set_params(
            "Voltage",
            {
                "nWorkers": 2.6,
                "maxConcurrentROIs": 1.5,
                "h5ChunkSamples": 10.6,
                "h5Deflate": 2.6,
            },
        )
        assert params["nWorkers"] == 3
        assert params["maxConcurrentROIs"] == 2
        assert params["h5ChunkSamples"] == 11
        assert params["h5Deflate"] == 3
        # MATLAB stores these as doubles. Python should expose ordinary ints after validation.
        assert isinstance(params["nWorkers"], int) and not isinstance(params["nWorkers"], bool)

    def test_logical_flags_accept_logical_and_numeric_binary_values(self) -> None:
        numeric = set_params("Voltage", {"useParallel": 0, "overwrite": 1})
        assert numeric["useParallel"] is False
        assert numeric["overwrite"] is True
        logical = set_params("Voltage", {"useParallel": True, "overwrite": False})
        assert logical["useParallel"] is True
        assert logical["overwrite"] is False

    def test_json_text_input(self) -> None:
        params = set_params(
            "Voltage",
            '{"indicatorName":"ASAP7y","indicatorDirection":"decreases",'
            '"nWorkers":3.7,"useParallel":false}',
        )
        assert params["indicatorName"] == "ASAP7y"
        assert params["indicatorDirection"] == "decreases"
        assert params["nWorkers"] == 4
        assert params["useParallel"] is False

    def test_json_file_input(self, tmp_path: Path) -> None:
        path = tmp_path / "params.json"
        path.write_text(
            json.dumps({"f0Method": "static", "f0Percentile": 25, "precision": "double"}),
            encoding="utf-8",
        )
        params = set_params("Voltage", path)
        assert params["f0Method"] == "static"
        assert params["f0Percentile"] == 25
        assert params["precision"] == "double"

    @pytest.mark.parametrize(
        ("variable_name", "values", "expected"),
        [
            ("optsOut", {"indicatorName": "ASAP8", "indicatorDirection": "increases"}, {"indicatorName": "ASAP8", "indicatorDirection": "increases"}),
            ("params", {"f0Bin_s": 2, "f0Smooth_s": 7}, {"f0Bin_s": 2, "f0Smooth_s": 7}),
            ("customPreset", {"h5ChunkSamples": 12.7}, {"h5ChunkSamples": 13}),
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
        assert params["indicatorName"] == "ASAP7"
        assert params["indicatorDirection"] == "decreases"
        assert params["f0Method"] == "robust"
        params = asap7_params({"indicatorName": "ASAP7b", "precision": "double", "f0Percentile": 20})
        assert params["indicatorName"] == "ASAP7b"
        assert params["indicatorDirection"] == "decreases"
        assert params["precision"] == "double"
        assert params["f0Percentile"] == 20

    def test_asap8_preset_and_overrides(self) -> None:
        params = asap8_params()
        assert params["indicatorName"] == "ASAP8"
        assert params["indicatorDirection"] == "increases"
        params = asap8_params({"indicatorDirection": "decreases", "outputFilename": "custom.h5"})
        assert params["indicatorName"] == "ASAP8"
        assert params["indicatorDirection"] == "decreases"
        assert params["outputFilename"] == "custom.h5"

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
            set_params("Voltage", {"useParallel": value})
        _assert_code(caught.value, "setParams:InvalidLogical")

    @pytest.mark.parametrize("value", ["", "   "])
    def test_invalid_output_filename_error(self, value: str) -> None:
        with pytest.raises(Exception) as caught:
            set_params("Voltage", {"outputFilename": value})
        _assert_code(caught.value, "setParams:InvalidOutputFilename")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"indicatorDirection": "sideways"},
            {"f0Method": "mean"},
            {"precision": "half"},
        ],
    )
    def test_invalid_choice_values_fail_validation(self, overrides: dict[str, object]) -> None:
        with pytest.raises(Exception):
            set_params("Voltage", overrides)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"chIdx": 0},
            {"zIdx": 1.5},
            {"traceWindow_lines": np.inf},
            {"traceExpectedWindow_lines": -1},
            {"f0Percentile": -1},
            {"f0Percentile": 101},
            {"f0Bin_s": 0},
            {"f0Smooth_s": np.nan},
            {"nWorkers": 0},
            {"maxConcurrentROIs": np.inf},
            {"h5ChunkSamples": 0},
            {"h5Deflate": -1},
            {"h5Deflate": 10},
        ],
    )
    def test_invalid_numeric_values_fail_validation(self, overrides: dict[str, object]) -> None:
        with pytest.raises(Exception):
            set_params("Voltage", overrides)
