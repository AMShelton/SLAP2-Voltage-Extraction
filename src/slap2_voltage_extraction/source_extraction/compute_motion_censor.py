from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..exceptions import Slap2VoltageError
from .validate_motion_censor_params import validate_motion_censor_params


def _round_positive_half_up(value: float) -> int:
    # MATLAB lineage: sample windows use positive half-up rounding rather than ties-to-even rounding.
    return int(np.floor(value + 0.5))


def _odd_window(value: float, length: int) -> int:
    window = max(1, _round_positive_half_up(value))
    if window % 2 == 0:
        window += 1
    # MATLAB lineage: centered moving-window operations retain an odd, data-bounded window length.
    window = min(window, 2 * ((length - 1) // 2) + 1)
    return max(window, 1)


def _moving_statistic(values: np.ndarray, window: int, statistic: str) -> np.ndarray:
    half = window // 2
    result = np.empty(values.size, dtype=np.float64)
    for index in range(values.size):
        lo = max(0, index - half)
        hi = min(values.size, index + half + 1)
        segment = values[lo:hi]
        if statistic == "median":
            finite = segment[np.isfinite(segment)]
            result[index] = np.median(finite) if finite.size else np.nan
        elif statistic == "max":
            result[index] = np.max(segment)
        elif statistic == "min":
            result[index] = np.min(segment)
        else:  # pragma: no cover - private programming error
            raise ValueError(f"Unsupported statistic: {statistic}")
    return result


def _empty_info(
    magnitude: np.ndarray,
    params: Mapping[str, object],
    fs_hz: float,
) -> dict[str, object]:
    return {
        "fs_hz": fs_hz,
        "magnitude_um": magnitude,
        "baseline_um": magnitude.copy(),
        "deviation_um": magnitude.copy(),
        "normalized_deviation": magnitude.copy(),
        "scale_um": params["motion_scale_floor_um"],
        "lower_tail_um": 0,
        "median_window_samples": 1,
        "threshold_um": float(params["motion_thresh"])
        * float(params["motion_scale_floor_um"]),
        "fraction_censored": 0,
    }


def compute_motion_censor(
    x_offset_pix: Any,
    y_offset_pix: Any,
    fs_hz: Any,
    params: Mapping[str, object] | None,
) -> tuple[np.ndarray, dict[str, object]]:
    """Flag samples contaminated by online XY motion offsets."""

    if (
        isinstance(fs_hz, (bool, np.bool_))
        or not np.isscalar(fs_hz)
        or not np.isreal(fs_hz)
        or not np.isfinite(fs_hz)
        or float(fs_hz) <= 0
    ):
        raise ValueError("fs_hz must be a positive finite real scalar")
    rate = float(fs_hz)
    options = validate_motion_censor_params(params)
    x = np.asarray(x_offset_pix, dtype=np.float64).reshape(-1)
    y = np.asarray(y_offset_pix, dtype=np.float64).reshape(-1)
    if x.size != y.size:
        raise Slap2VoltageError(
            "computeMotionCensor:SizeMismatch",
            "x and y offsets must have the same length.",
        )

    bad = ~np.isfinite(x) | ~np.isfinite(y)
    magnitude = float(options["motion_pixel_size_um"]) * np.hypot(x, y)
    magnitude[bad] = np.nan
    if not x.size:
        return np.empty(0, dtype=bool), _empty_info(magnitude, options, rate)

    window = _odd_window(float(options["motion_median_window_s"]) * rate, x.size)
    baseline = _moving_statistic(magnitude, window, "median")
    deviation = magnitude - baseline
    finite_deviation = deviation[np.isfinite(deviation)]
    lower_tail = float(np.percentile(finite_deviation, 5)) if finite_deviation.size else 0.0
    if not np.isfinite(lower_tail):
        lower_tail = 0.0
    scale = max(abs(lower_tail), float(options["motion_scale_floor_um"]))
    normalized = deviation / scale

    threshold = float(options["motion_thresh"])
    flag = normalized > threshold
    pad_samples = int(np.ceil(float(options["motion_pad_s"]) * rate))
    if pad_samples:
        padded = _moving_statistic(flag.astype(np.float64), 2 * pad_samples + 1, "max") > 0
    else:
        padded = flag
    candidate = padded & (normalized > threshold / 2)

    gap_samples = int(np.ceil(float(options["motion_merge_gap_s"]) * rate))
    if gap_samples:
        close_window = 2 * gap_samples + 1
        candidate = _moving_statistic(
            _moving_statistic(candidate.astype(np.float64), close_window, "max"),
            close_window,
            "min",
        ) > 0
    mask = candidate

    absolute_max = float(options["motion_abs_max_um"])
    if absolute_max > 0:
        mask |= magnitude > absolute_max
    mask |= bad
    initial = min(x.size, int(np.ceil(float(options["motion_discard_initial_s"]) * rate)))
    mask[:initial] = True
    mask = np.asarray(mask, dtype=bool)

    info: dict[str, object] = {
        "fs_hz": rate,
        "magnitude_um": magnitude,
        "baseline_um": baseline,
        "deviation_um": deviation,
        "normalized_deviation": normalized,
        "scale_um": scale,
        "lower_tail_um": lower_tail,
        "median_window_samples": window,
        "threshold_um": threshold * scale,
        "fraction_censored": float(np.mean(mask)),
    }
    return mask, info


__all__ = ["compute_motion_censor"]
