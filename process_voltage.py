"""Direct Python translation of MATLAB ``processVoltage.m`` orchestration.

The MATLAB file embeds a private copy of the extraction engine. The Python
translation calls the direct :mod:`voltage` translation so both public entry
points execute the same implementation without introducing a façade package.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from build_trial_table_slap2 import build_trial_table_slap2
from dependencies.gui.options_gui import options_gui
from dependencies.gui.set_params import set_params
from dependencies.io import load_struct_from_h5
from source_extraction._errors import Slap2VoltageError
from voltage import ReaderFactory, voltage


def _error(code: str, message: str) -> Slap2VoltageError:
    return Slap2VoltageError(code, message)


def logical_scalar(value: object, name: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        numeric = float(value)
        if np.isfinite(numeric) and numeric in (0.0, 1.0):
            return bool(numeric)
    raise _error("setParams:InvalidLogical", f"{name} must be a scalar logical or 0/1.")


def local_voltage_params(
    params_in: object | None,
    force_gui: bool,
    *,
    option_updates: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Merge defaults, apply the headless GUI adapter, and validate parameters."""

    params = set_params("Voltage", params_in)
    known_names = set(set_params("Voltage"))
    unknown_names = sorted(set(params) - known_names)
    if unknown_names:
        raise _error(
            "processVoltage:UnknownParameter",
            f"Unknown voltage parameter: {unknown_names[0]}",
        )
    if force_gui:
        params = options_gui(params, function_name="Voltage", updates=option_updates)
        params = set_params("Voltage", params)
    return params


def validate_process_trial_table(trial_table: Mapping[str, Any]) -> None:
    required = ("datadr", "savedr", "filename", "true_trial_ix", "epoch", "slap2_info")
    for name in required:
        if name not in trial_table:
            raise _error(
                "processVoltage:IncompleteTrialTable",
                f'Trial table missing field "{name}".',
            )
    filenames = np.asarray(trial_table["filename"], dtype=object)
    info = trial_table["slap2_info"]
    if (
        filenames.size == 0
        or not isinstance(info, Mapping)
        or "first_line" not in info
        or "last_line" not in info
    ):
        raise _error(
            "processVoltage:IncompleteTrialTable",
            "Trial table is empty or missing first_line/last_line metadata.",
        )


def process_voltage(
    directory: str | Path,
    save_directory: str | Path | None = None,
    use_all_files: bool = False,
    params_in: object | None = None,
    show_params_gui: bool = True,
    *,
    existing_trial_table: str = "reuse",
    option_updates: Mapping[str, Any] | None = None,
    data_reader: Callable[[str | Path], object] | None = None,
    tiff_reader: Callable[[str | Path], tuple[np.ndarray, str, list[Any]]] | None = None,
    reader_factory: ReaderFactory | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, object]]:
    """Build/reuse a trial table, configure parameters, and run extraction.

    ``existing_trial_table`` replaces MATLAB's ``questdlg`` and accepts
    ``"reuse"``, ``"rebuild"``, or ``"cancel"``. ``option_updates`` is passed
    to the headless :func:`options_gui` adapter when ``show_params_gui`` is true.
    """

    root = Path(directory)
    save_dir = Path(save_directory) if save_directory is not None else root
    use_all = logical_scalar(use_all_files, "use_all_files")
    show_gui = logical_scalar(show_params_gui, "show_params_gui")
    if not root.is_dir():
        raise _error(
            "processVoltage:InvalidDataDirectory",
            f"SLAP2 directory not found: {root}",
        )
    save_dir.mkdir(parents=True, exist_ok=True)

    action = str(existing_trial_table).strip().lower()
    if action not in {"reuse", "rebuild", "cancel"}:
        raise ValueError("existing_trial_table must be 'reuse', 'rebuild', or 'cancel'")
    if action == "cancel":
        raise _error("processVoltage:Cancelled", "Processing cancelled by user.")

    trial_table_path = save_dir / "trial_table.h5"
    if trial_table_path.is_file() and action == "reuse":
        trial_table = load_struct_from_h5(trial_table_path)
    else:
        trial_table = build_trial_table_slap2(
            root,
            save_dir,
            use_all,
            data_reader=data_reader,
            tiff_reader=tiff_reader,
        )
    if not trial_table:
        raise _error(
            "processVoltage:EmptyTrialTable",
            "No trial table returned; epoch selection may have been cancelled.",
        )
    if not trial_table_path.is_file():
        raise _error(
            "processVoltage:MissingTrialTable",
            f"No trial table created: {trial_table_path}",
        )
    validate_process_trial_table(trial_table)

    voltage_params = local_voltage_params(
        params_in,
        show_gui,
        option_updates=option_updates,
    )
    voltage_output_dir = (
        Path(str(voltage_params["output_dir"]))
        if voltage_params["output_dir"]
        else save_dir / "Voltage"
    )
    expected_voltage_path = voltage_output_dir / str(voltage_params["output_filename"])
    if expected_voltage_path.is_file() and not bool(voltage_params["overwrite"]):
        raise _error(
            "processVoltage:OutputExists",
            "Voltage output already exists: "
            f"{expected_voltage_path}. Enable overwrite or change output_dir/output_filename.",
        )

    summary = voltage(
        trial_table_path,
        voltage_params,
        reader_factory=reader_factory,
    )
    final_trial_table = load_struct_from_h5(trial_table_path)
    return summary, final_trial_table, voltage_params


__all__ = ["process_voltage"]
