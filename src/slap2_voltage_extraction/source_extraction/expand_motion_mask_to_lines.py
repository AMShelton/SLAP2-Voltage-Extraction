from __future__ import annotations

from typing import Any

import numpy as np

from ..exceptions import Slap2VoltageError


def expand_motion_mask_to_lines(
    mask_samples: Any,
    line_ids: Any,
    total_lines: int,
) -> np.ndarray:
    """Zero-order-hold a sampled mask onto zero-based SLAP2 line indices."""

    mask = np.asarray(mask_samples, dtype=bool).reshape(-1)
    lines_raw = np.asarray(line_ids)
    if lines_raw.ndim > 1 and np.count_nonzero(np.asarray(lines_raw.shape) != 1) > 1:
        raise Slap2VoltageError(
            "expandMotionMaskToLines:InvalidLineIds",
            "line_ids must be a one-dimensional sequence.",
        )
    lines_float = np.asarray(lines_raw, dtype=np.float64).reshape(-1)
    if mask.size != lines_float.size:
        raise Slap2VoltageError(
            "expandMotionMaskToLines:SizeMismatch",
            "Mask and line_ids must have the same length.",
        )
    if isinstance(total_lines, (bool, np.bool_)) or not isinstance(
        total_lines, (int, np.integer)
    ) or total_lines < 0:
        raise ValueError("total_lines must be a nonnegative integer")
    total = int(total_lines)
    if not lines_float.size:
        return np.zeros(total, dtype=bool)
    if (
        not np.isfinite(lines_float).all()
        or not np.equal(lines_float, np.floor(lines_float)).all()
        or np.any(np.diff(lines_float) <= 0)
        or lines_float[0] < 0
        or lines_float[-1] >= total
    ):
        raise Slap2VoltageError(
            "expandMotionMaskToLines:InvalidLineIds",
            f"line_ids must increase within [0, {total}).",
        )

    lines = lines_float.astype(np.int64)
    result = np.empty(total, dtype=bool)
    result[: lines[0]] = mask[0]
    for index, start in enumerate(lines):
        stop = lines[index + 1] if index + 1 < lines.size else total
        result[start:stop] = mask[index]
    if result.size != total:
        raise Slap2VoltageError(
            "expandMotionMaskToLines:LengthMismatch",
            f"Expanded mask has {result.size} lines but the source has {total}.",
        )
    return result


__all__ = ["expand_motion_mask_to_lines"]
