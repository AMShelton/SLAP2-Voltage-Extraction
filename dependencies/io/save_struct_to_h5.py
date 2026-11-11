"""Direct Python translation of ``saveStructToH5.m``."""

from __future__ import annotations

from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from source_extraction._errors import Slap2VoltageError


def _error(code: str, message: str) -> Slap2VoltageError:
    return Slap2VoltageError(code, message)


def _is_non_scalar_struct(value: object) -> bool:
    if not isinstance(value, np.ndarray) or value.dtype != object or value.size <= 1:
        return False
    return all(isinstance(item, Mapping) for item in value.flat)


def _text_array(value: np.ndarray, path: str) -> np.ndarray:
    result = np.empty(value.shape, dtype=object)
    for index, item in np.ndenumerate(value):
        if item is None:
            result[index] = ""
        elif isinstance(item, (str, np.str_)):
            result[index] = str(item)
        elif isinstance(item, np.ndarray) and item.size == 0:
            result[index] = ""
        else:
            raise _error(
                "saveStructToH5:UnsupportedCell",
                f"Only object arrays of text are supported (at {path}).",
            )
    return result


def _write_value(group: h5py.Group, name: str, value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        child = group.create_group(name)
        _write_group(child, value, path)
        return
    if _is_non_scalar_struct(value):
        raise _error(
            "saveStructToH5:NonScalarStruct",
            f"Non-scalar structs are not supported (at {path}).",
        )

    if isinstance(value, str):
        group.create_dataset(name, data=value, dtype=h5py.string_dtype("utf-8"))
        return

    array = np.asarray(value) if isinstance(value, (np.ndarray, np.generic, bool, int, float, complex)) else None
    if array is not None:
        if array.size == 0:
            return
        if array.dtype == object:
            text = _text_array(array, path)
            group.create_dataset(name, data=text, dtype=h5py.string_dtype("utf-8"))
            return
        if np.issubdtype(array.dtype, np.str_) or np.issubdtype(array.dtype, np.bytes_):
            text = array.astype(object)
            group.create_dataset(name, data=text, dtype=h5py.string_dtype("utf-8"))
            return
        if np.issubdtype(array.dtype, np.bool_):
            array = array.astype(np.int8)
        if np.issubdtype(array.dtype, np.number):
            group.create_dataset(name, data=array, shape=array.shape or None, dtype=array.dtype)
            return

    raise _error(
        "saveStructToH5:UnsupportedType",
        f"Unsupported value type {type(value).__name__!r} at {path}.",
    )


def _write_group(group: h5py.Group, value: Mapping[str, Any], base_path: str) -> None:
    for name, item in value.items():
        if not isinstance(name, str):
            raise TypeError("HDF5 field names must be strings")
        path = f"{base_path}/{name}" if base_path else f"/{name}"
        _write_value(group, name, item, path)


def save_struct_to_h5(
    value: Mapping[str, Any] | object,
    filename: str | PathLike[str] | None = None,
) -> None:
    """Write one nested mapping using the established MATLAB-facing HDF5 schema."""

    if filename is None or str(filename) == "":
        raise _error("saveStructToH5:MissingFilename", "A destination filename must be provided.")
    if not isinstance(value, Mapping):
        raise _error("saveStructToH5:UnsupportedInput", "Input must be a scalar mapping.")

    path = Path(filename)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as handle:
        _write_group(handle, value, "")
        handle.create_dataset("row_major", data=np.uint8(0), dtype=np.uint8)


__all__ = ["save_struct_to_h5"]
