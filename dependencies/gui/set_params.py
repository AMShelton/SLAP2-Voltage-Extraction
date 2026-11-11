"""Direct Python translation of ``setParams.m`` parameter handling."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

from source_extraction._errors import Slap2VoltageError
from source_extraction.motion_censor_defaults import motion_censor_defaults
from source_extraction.validate_motion_censor_params import validate_motion_censor_params


def _voltage_defaults() -> dict[str, object]:
    params: dict[str, object] = {
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
    }
    params.update(motion_censor_defaults())
    return params


def _matlab_round(value: float) -> int:
    """Match MATLAB's half-away-from-zero rounding for scalar values."""

    return int(np.floor(value + 0.5)) if value >= 0 else int(np.ceil(value - 0.5))


def _finite_real_scalar(value: object, name: str) -> float:
    if (
        isinstance(value, (bool, np.bool_))
        or not np.isscalar(value)
        or not np.isreal(value)
        or not np.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite real scalar")
    return float(value)


def _logical_scalar(value: object, name: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        numeric = float(value)
        if np.isfinite(numeric) and numeric in (0.0, 1.0):
            return bool(numeric)
    raise Slap2VoltageError(
        "setParams:InvalidLogical",
        f"{name} must be a scalar logical or 0/1.",
    )


def _choice(value: object, choices: set[str], name: str) -> str:
    text = str(value)
    if text not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)!r}")
    return text


def _mat_to_python(value: Any) -> Any:
    if hasattr(value, "_fieldnames"):
        return {name: _mat_to_python(getattr(value, name)) for name in value._fieldnames}
    if isinstance(value, np.ndarray):
        if value.shape == () or value.size == 1:
            return _mat_to_python(value.item())
        if value.dtype.names:
            if value.size != 1:
                return value
            record = value.reshape(-1)[0]
            return {name: _mat_to_python(record[name]) for name in value.dtype.names}
        return value
    if isinstance(value, np.generic):
        return value.item()
    return value


def _load_mat_preset(path: Path) -> dict[str, object]:
    loaded = {
        name: _mat_to_python(value)
        for name, value in loadmat(path, squeeze_me=True, struct_as_record=False).items()
        if not name.startswith("__")
    }
    if isinstance(loaded.get("optsOut"), Mapping):
        selected = loaded["optsOut"]
    elif isinstance(loaded.get("params"), Mapping):
        selected = loaded["params"]
    elif len(loaded) == 1 and isinstance(next(iter(loaded.values())), Mapping):
        selected = next(iter(loaded.values()))
    else:
        raise Slap2VoltageError(
            "setParams:InvalidPreset",
            "MAT preset must contain optsOut, params, or one struct variable.",
        )
    return dict(selected)


def _normalize_input(params_in: object | None) -> dict[str, object]:
    if params_in is None:
        return {}
    if isinstance(params_in, Mapping):
        return dict(params_in)
    if isinstance(params_in, (str, Path)):
        candidate = Path(params_in)
        if candidate.is_file():
            if candidate.suffix.lower() == ".mat":
                return _load_mat_preset(candidate)
            decoded = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            decoded = json.loads(str(params_in))
        if isinstance(decoded, Mapping):
            return dict(decoded)
    raise Slap2VoltageError(
        "setParams:InvalidInput",
        "params_in must be a mapping, JSON string/file, or MAT preset.",
    )


def _validate_voltage_params(params: Mapping[str, object]) -> dict[str, object]:
    result = dict(params)

    for name in ("ch_idx", "z_idx"):
        numeric = _finite_real_scalar(result[name], name)
        if numeric < 0 or not numeric.is_integer():
            raise ValueError(f"{name} must be a nonnegative integer")
        result[name] = int(numeric)

    for name in ("trace_window_lines", "trace_expected_window_lines"):
        numeric = _finite_real_scalar(result[name], name)
        if numeric <= 0 or not numeric.is_integer():
            raise ValueError(f"{name} must be a positive integer")
        result[name] = int(numeric)

    percentile = _finite_real_scalar(result["f0_percentile"], "f0_percentile")
    if not 0 <= percentile <= 100:
        raise ValueError("f0_percentile must be between 0 and 100")
    result["f0_percentile"] = int(percentile) if percentile.is_integer() else percentile

    for name in ("f0_bin_s", "f0_smooth_s"):
        numeric = _finite_real_scalar(result[name], name)
        if numeric <= 0:
            raise ValueError(f"{name} must be positive")
        result[name] = int(numeric) if numeric.is_integer() else numeric

    for name in ("n_workers", "max_concurrent_rois", "h5_chunk_samples"):
        numeric = _finite_real_scalar(result[name], name)
        if numeric <= 0:
            raise ValueError(f"{name} must be positive")
        result[name] = max(1, _matlab_round(numeric))

    deflate = _finite_real_scalar(result["h5_deflate"], "h5_deflate")
    if not 0 <= deflate <= 9:
        raise ValueError("h5_deflate must be between 0 and 9")
    result["h5_deflate"] = _matlab_round(deflate)

    result["use_parallel"] = _logical_scalar(result["use_parallel"], "use_parallel")
    result["overwrite"] = _logical_scalar(result["overwrite"], "overwrite")
    result["indicator_name"] = str(result["indicator_name"])
    result["indicator_direction"] = _choice(
        result["indicator_direction"],
        {"auto", "increases", "decreases"},
        "indicator_direction",
    )
    result["f0_method"] = _choice(result["f0_method"], {"robust", "static"}, "f0_method")
    result["precision"] = _choice(result["precision"], {"single", "double"}, "precision")
    result["output_dir"] = str(result["output_dir"])
    result["output_filename"] = str(result["output_filename"])
    if not result["output_filename"].strip():
        raise Slap2VoltageError(
            "setParams:InvalidOutputFilename",
            "output_filename cannot be empty.",
        )

    motion = validate_motion_censor_params(result)
    for name in motion_censor_defaults():
        result[name] = motion[name]
    return result


def set_params(
    function_name: str = "Voltage",
    params_in: object | None = None,
    force_gui: bool = False,
) -> dict[str, object]:
    """Return validated parameters for the requested function.

    ``force_gui`` is accepted for signature parity, but the Python translation
    deliberately has no interactive GUI. Passing ``True`` therefore raises
    ``NotImplementedError`` instead of silently ignoring the request.
    """

    if function_name != "Voltage":
        raise Slap2VoltageError(
            "setParams:UnknownFunction",
            f"Unknown function name: {function_name}",
        )
    if force_gui:
        raise NotImplementedError("The Python translation does not implement optionsGUI")

    params = _voltage_defaults()
    params.update(_normalize_input(params_in))
    return _validate_voltage_params(params)


__all__ = ["set_params"]
