from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib

import pytest

from slap2_voltage_extraction.process_voltage import process_voltage

process_voltage_module = importlib.import_module(
    "slap2_voltage_extraction.process_voltage"
)


def assert_error_code(exception: BaseException, expected: str) -> None:
    assert getattr(exception, "code", None) == expected


class TrialTableBuilder:
    """Controllable Python test double for trial-table construction."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        directory: str | Path,
        save_directory: str | Path,
        use_all_files: bool,
        **_: object,
    ) -> dict[str, Any]:
        root = Path(directory)
        save_dir = Path(save_directory)
        self.calls.append(
            {
                "directory": root,
                "save_directory": save_dir,
                "use_all_files": use_all_files,
            }
        )
        if self.mode == "empty":
            return {}

        trial_table: dict[str, Any]
        if self.mode == "incomplete":
            trial_table = {"datadr": str(root)}
        else:
            trial_table = {
                "datadr": str(root),
                "savedr": str(save_dir),
                "filename": ["fixture.dat"],
                "true_trial_ix": [0],
                "epoch": [1],
                "slap2_info": {"first_line": [1], "last_line": [1]},
            }
        if self.mode != "missing-file":
            (save_dir / "trial_table.h5").touch()
        return trial_table


def install_builder(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> TrialTableBuilder:
    builder = TrialTableBuilder(mode)
    monkeypatch.setattr(process_voltage_module, "build_trial_table_slap2", builder)
    return builder


def test_rejects_missing_data_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as caught:
        process_voltage(tmp_path / "missing", tmp_path, False, {}, False)

    assert_error_code(caught.value, "processVoltage:InvalidDataDirectory")


@pytest.mark.parametrize(
    ("argument", "value"),
    [("use_all_files", 2), ("show_params_gui", "yes")],
)
def test_rejects_nonlogical_flags(
    tmp_path: Path, argument: str, value: object
) -> None:
    kwargs = {argument: value}
    with pytest.raises(ValueError) as caught:
        process_voltage(tmp_path, tmp_path, params_in={}, **kwargs)

    assert_error_code(caught.value, "setParams:InvalidLogical")


def test_empty_builder_result_uses_requested_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = install_builder(monkeypatch, "empty")

    with pytest.raises(ValueError) as caught:
        process_voltage(tmp_path, tmp_path, True, {}, False)

    assert_error_code(caught.value, "processVoltage:EmptyTrialTable")
    assert builder.calls == [
        {
            "directory": tmp_path,
            "save_directory": tmp_path,
            "use_all_files": True,
        }
    ]


def test_builder_must_create_trial_table_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_builder(monkeypatch, "missing-file")

    with pytest.raises(ValueError) as caught:
        process_voltage(tmp_path, tmp_path, False, {}, False)

    assert_error_code(caught.value, "processVoltage:MissingTrialTable")


def test_incomplete_trial_table_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_builder(monkeypatch, "incomplete")

    with pytest.raises(ValueError) as caught:
        process_voltage(tmp_path, tmp_path, False, {}, False)

    assert_error_code(caught.value, "processVoltage:IncompleteTrialTable")


def test_unknown_voltage_parameter_is_rejected_before_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_builder(monkeypatch, "valid")

    with pytest.raises(ValueError) as caught:
        process_voltage(
            tmp_path,
            tmp_path,
            False,
            {"not_a_voltage_parameter": 1},
            False,
        )

    assert_error_code(caught.value, "processVoltage:UnknownParameter")


def test_existing_output_stops_before_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_builder(monkeypatch, "valid")
    output_dir = tmp_path / "custom-output"
    output_dir.mkdir()
    output_path = output_dir / "already-there.h5"
    output_path.touch()

    with pytest.raises(ValueError) as caught:
        process_voltage(
            tmp_path,
            tmp_path,
            False,
            {
                "output_dir": str(output_dir),
                "output_filename": output_path.name,
                "overwrite": False,
            },
            False,
        )

    assert_error_code(caught.value, "processVoltage:OutputExists")