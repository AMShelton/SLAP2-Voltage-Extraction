"""Direct Python translation of ``loadStructFromH5.m``."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import Any
import re

import h5py
import numpy as np

from source_extraction._errors import Slap2VoltageError


_CELL_TEXT_FIELDS = {"filename", "fn_reg_ds", "fn_raw", "fn_adata", "fn_ann"}


def _decode_text(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        decoded = np.empty(value.shape, dtype=object)
        for index, item in np.ndenumerate(value):
            decoded[index] = item.decode("utf-8") if isinstance(item, bytes) else str(item)
        return decoded
    return value


def _read_group(group: h5py.Group) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, item in group.items():
        if isinstance(item, h5py.Group):
            result[name] = _read_group(item)
            continue
        value = item[()]
        if h5py.check_string_dtype(item.dtype) is not None:
            value = _decode_text(value)
            if name not in _CELL_TEXT_FIELDS and isinstance(value, np.ndarray) and value.shape == ():
                value = value.item()
        if isinstance(value, np.ndarray) and value.shape == ():
            value = value.item()
        result[name] = value
    return result


def _normalize_legacy_fields(result: dict[str, Any]) -> None:
    slap2_info = result.get("slap2_info")
    if isinstance(slap2_info, dict) and isinstance(slap2_info.get("ref_stack"), dict):
        ref_stack = slap2_info["ref_stack"]
        for name in list(ref_stack):
            match = re.fullmatch(r"DMD(\d+)", name)
            if match is None:
                continue
            replacement = f"Path{match.group(1)}"
            if replacement not in ref_stack:
                ref_stack[replacement] = ref_stack[name]
            del ref_stack[name]

    slap2 = result.get("slap2")
    if isinstance(slap2, dict) and "Z" in slap2 and "Z_depths" not in slap2:
        slap2["Z_depths"] = slap2.pop("Z")


def load_struct_from_h5(
    filename: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load a nested mapping written by :func:`save_struct_to_h5`."""

    if filename is None or str(filename) == "":
        raise Slap2VoltageError(
            "loadStructFromH5:MissingFilename", "A source filename must be provided."
        )
    path = Path(filename)
    if not path.is_file():
        raise Slap2VoltageError("loadStructFromH5:FileNotFound", f"File not found: {path}")
    with h5py.File(path, "r") as handle:
        result = _read_group(handle)
    _normalize_legacy_fields(result)
    return result


__all__ = ["load_struct_from_h5"]
