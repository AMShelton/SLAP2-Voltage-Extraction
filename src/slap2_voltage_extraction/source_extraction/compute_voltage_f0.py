from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..exceptions import Slap2VoltageError


def _round_positive_half_up(value: float) -> int:
    # MATLAB lineage: F0 bin and smoothing widths use positive half-up rounding.
    return int(np.floor(value + 0.5))


def _canonical_trace(raw_f: Any) -> np.ndarray:
    raw = np.asarray(raw_f)
    if raw.ndim > 1 and np.count_nonzero(np.asarray(raw.shape) != 1) > 1:
        raise ValueError("raw_f must be a one-dimensional time series")
    return np.asarray(raw, dtype=np.float32).reshape(-1)


def _robust_percentile(values: np.ndarray, percentile: float) -> float:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return float("nan")
    return float(np.percentile(finite, percentile))


def _fallback(raw: np.ndarray) -> np.float32:
    finite = np.abs(raw[np.isfinite(raw)])
    value = np.median(finite) if finite.size else np.nan
    if not np.isfinite(value) or value <= np.finfo(np.float32).eps:
        value = 1.0
    return np.float32(value)


def _safe_baseline_scalar(value: float, raw: np.ndarray) -> np.float32:
    if not np.isfinite(value) or abs(value) <= np.finfo(np.float32).eps:
        return _fallback(raw)
    return np.float32(value)


def _safe_baseline_vector(values: np.ndarray, raw: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32).copy()
    bad = ~np.isfinite(result) | (np.abs(result) <= np.finfo(np.float32).eps)
    result[bad] = _fallback(raw)
    return result


def _fill_nonfinite(values: np.ndarray, fallback: np.float32) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32).reshape(-1).copy()
    valid = np.isfinite(result)
    if valid.all():
        return result
    if not valid.any():
        result.fill(fallback)
        return result
    positions = np.arange(result.size, dtype=np.float64)
    result[~valid] = np.interp(positions[~valid], positions[valid], result[valid]).astype(np.float32)
    return result


def _centered_moving_median(values: np.ndarray, window: int) -> np.ndarray:
    data = np.asarray(values, dtype=np.float32).reshape(-1)
    window = max(1, _round_positive_half_up(float(window)))
    if window % 2 == 0:
        window += 1
    if window <= 1:
        return data.copy()
    half = window // 2
    result = np.empty(data.size, dtype=np.float32)
    for index in range(data.size):
        lo = max(0, index - half)
        hi = min(data.size, index + half + 1)
        finite = data[lo:hi][np.isfinite(data[lo:hi])]
        result[index] = np.float32(np.median(finite)) if finite.size else np.float32(np.nan)
    return result


def _default_params() -> dict[str, object]:
    return {
        "f0_method": "robust",
        "f0_percentile": 50,
        "f0_bin_s": 5,
        "f0_smooth_s": 180,
        "precision": "single",
    }


def compute_voltage_f0(
    raw_f: Any,
    sample_rate_hz: Any,
    params: Mapping[str, object] | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    """Compute the static or robust slow baseline for one fluorescence trace."""

    options = _default_params()
    if params is not None:
        options.update(params)
    method = str(options["f0_method"])
    precision = str(options["precision"])
    raw = _canonical_trace(raw_f)

    if raw.size == 0:
        dtype = np.float64 if precision.lower() == "double" else np.float32
        return np.empty(0, dtype=dtype), {"method": method, "sample_rate_hz": sample_rate_hz}

    if (
        isinstance(sample_rate_hz, (bool, np.bool_))
        or not np.isscalar(sample_rate_hz)
        or not np.isreal(sample_rate_hz)
        or not np.isfinite(sample_rate_hz)
        or float(sample_rate_hz) <= 0
    ):
        raise ValueError("sample_rate_hz must be a positive finite real scalar")
    rate = float(sample_rate_hz)
    percentile = float(options["f0_percentile"])

    if method.lower() == "static":
        baseline = _safe_baseline_scalar(_robust_percentile(raw, percentile), raw)
        f0_single = np.full(raw.size, baseline, dtype=np.float32)
        metadata: dict[str, object] = {
            "method": "static_percentile",
            "percentile": percentile,
            "sample_rate_hz": rate,
            "time_varying": False,
        }
    elif method.lower() == "robust":
        bin_s = float(options["f0_bin_s"])
        smooth_s = float(options["f0_smooth_s"])
        bin_samples = max(1, _round_positive_half_up(bin_s * rate))
        n_bins = int(np.ceil(raw.size / bin_samples))
        if n_bins <= 1:
            baseline = _safe_baseline_scalar(_robust_percentile(raw, percentile), raw)
            f0_single = np.full(raw.size, baseline, dtype=np.float32)
            metadata = {
                "method": "static_percentile",
                "percentile": percentile,
                "sample_rate_hz": rate,
                "time_varying": False,
            }
        else:
            bin_centers = np.empty(n_bins, dtype=np.float64)
            bin_f0 = np.empty(n_bins, dtype=np.float32)
            for index in range(n_bins):
                first = index * bin_samples
                stop = min(raw.size, (index + 1) * bin_samples)
                bin_centers[index] = (first + stop - 1) / 2
                bin_f0[index] = np.float32(_robust_percentile(raw[first:stop], percentile))

            smooth_bins = max(1, _round_positive_half_up(smooth_s / bin_s))
            if smooth_bins % 2 == 0:
                smooth_bins += 1
            fallback = _fallback(raw)
            filled = _fill_nonfinite(bin_f0, fallback)
            smoothed = _fill_nonfinite(_centered_moving_median(filled, smooth_bins), fallback)
            sample_positions = np.arange(raw.size, dtype=np.float64)
            interpolated = np.interp(sample_positions, bin_centers, smoothed).astype(np.float32)
            f0_single = _safe_baseline_vector(interpolated, raw)
            metadata = {
                "method": "robust_binned_percentile_moving_median",
                "percentile": percentile,
                "bin_s": bin_s,
                "smooth_s": smooth_s,
                "bin_samples": bin_samples,
                "smooth_bins": smooth_bins,
                "n_bins": n_bins,
                "sample_rate_hz": rate,
                "time_varying": True,
            }
    else:
        raise Slap2VoltageError(
            "computeVoltageF0:UnknownMethod",
            f"Unknown F0 method: {method}",
        )

    f0 = f0_single.astype(np.float64) if precision.lower() == "double" else f0_single
    return f0, metadata


__all__ = ["compute_voltage_f0"]
