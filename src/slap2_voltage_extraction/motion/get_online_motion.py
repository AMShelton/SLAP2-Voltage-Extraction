"""Read online motion offsets from SLAP2 line headers."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..exceptions import Slap2VoltageError


_HEADER_MODE_BY_CLASS: dict[type[object], str] = {}


def _field(header: object, name: str) -> Any:
    return header[name] if isinstance(header, dict) else getattr(header, name)


def _unpack(headers: object, count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    try:
        if isinstance(headers, (list, tuple, np.ndarray)) and np.asarray(headers, dtype=object).size == count:
            items = list(np.asarray(headers, dtype=object).reshape(-1))
            arrays = tuple(
                np.asarray([_field(item, name) for item in items], dtype=np.float64)
                for name in ("xOffset_pix", "yOffset_pix", "zOffset_um")
            )
        else:
            arrays = tuple(
                np.asarray(_field(headers, name), dtype=np.float64).reshape(-1)
                for name in ("xOffset_pix", "yOffset_pix", "zOffset_um")
            )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return arrays if all(array.size == count for array in arrays) else None


def _batch(data_file: object, residual: np.ndarray, cycles: np.ndarray) -> tuple[np.ndarray, ...] | None:
    for first, second in ((residual, cycles), (residual.reshape(1, -1), cycles.reshape(1, -1))):
        try:
            unpacked = _unpack(data_file.getLineHeader(first, second), residual.size)
            if unpacked is not None:
                return unpacked
        except Exception:
            pass
    return None


def _cycle_grouped(
    data_file: object, residual: np.ndarray, cycles: np.ndarray
) -> tuple[np.ndarray, ...] | None:
    output = [np.full(residual.size, np.nan, dtype=np.float64) for _ in range(3)]
    try:
        for cycle in dict.fromkeys(cycles.tolist()):
            selected = np.flatnonzero(cycles == cycle)
            line_ids = residual[selected]
            unpacked = None
            for candidate in (line_ids, line_ids.reshape(1, -1)):
                unpacked = _unpack(data_file.getLineHeader(candidate, int(cycle)), selected.size)
                if unpacked is not None:
                    break
            if unpacked is None:
                return None
            for destination, values in zip(output, unpacked, strict=True):
                destination[selected] = values
    except Exception:
        return None
    return tuple(output)


def _scalar(
    data_file: object, residual: np.ndarray, cycles: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    output = [np.full(residual.size, np.nan, dtype=np.float64) for _ in range(3)]
    for index, (line, cycle) in enumerate(zip(residual, cycles, strict=True)):
        header = data_file.getLineHeader(int(line), int(cycle))
        for destination, name in zip(
            output, ("xOffset_pix", "yOffset_pix", "zOffset_um"), strict=True
        ):
            destination[index] = float(_field(header, name))
    return tuple(output)  # type: ignore[return-value]


def get_online_motion(
    data_file: object, line_ids: object | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read online motion for zero-based global line indices."""

    lines_per_cycle = len(data_file.lineHeaderIdxs)
    total_lines = lines_per_cycle * int(data_file.numCycles)
    ids = (
        np.arange(0, total_lines, lines_per_cycle, dtype=np.int64)
        if line_ids is None or np.asarray(line_ids).size == 0
        else np.asarray(line_ids)
    )
    ids = ids.reshape(-1)
    if (
        not np.issubdtype(ids.dtype, np.number)
        or np.any(~np.isfinite(ids))
        or np.any(ids != np.round(ids))
        or np.any(ids < 0)
        or np.any(ids >= total_lines)
    ):
        raise Slap2VoltageError(
            "getOnlineMotion:InvalidLineIds",
            f"line_ids must be finite integer indices in [0, {total_lines}).",
        )
    ids = ids.astype(np.int64)
    cycles = ids // lines_per_cycle
    residual = ids % lines_per_cycle

    reader_type = type(data_file)
    mode = _HEADER_MODE_BY_CLASS.get(reader_type)
    if mode == "vector" and (values := _batch(data_file, residual, cycles)) is not None:
        return values  # type: ignore[return-value]
    if mode == "cycle-grouped" and (values := _cycle_grouped(data_file, residual, cycles)) is not None:
        return values  # type: ignore[return-value]
    if mode == "scalar":
        return _scalar(data_file, residual, cycles)
    _HEADER_MODE_BY_CLASS.pop(reader_type, None)

    values = _batch(data_file, residual, cycles)
    if values is not None:
        _HEADER_MODE_BY_CLASS[reader_type] = "vector"
        return values  # type: ignore[return-value]
    values = _cycle_grouped(data_file, residual, cycles)
    if values is not None:
        _HEADER_MODE_BY_CLASS[reader_type] = "cycle-grouped"
        return values  # type: ignore[return-value]
    _HEADER_MODE_BY_CLASS[reader_type] = "scalar"
    return _scalar(data_file, residual, cycles)


__all__ = ["get_online_motion"]
