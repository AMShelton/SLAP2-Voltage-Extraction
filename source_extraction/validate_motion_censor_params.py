from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ._errors import Slap2VoltageError
from .motion_censor_defaults import motion_censor_defaults


def _logical(value: object, name: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        numeric = float(value)
        if np.isfinite(numeric):
            return numeric != 0
    raise Slap2VoltageError(
        "validateMotionCensorParams:InvalidLogical",
        f"{name} must be a logical scalar.",
    )


def _real_scalar(value: object, name: str, *, positive: bool = False) -> int | float:
    if (
        isinstance(value, (bool, np.bool_))
        or not np.isscalar(value)
        or not np.isreal(value)
        or not np.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite real scalar")
    numeric = float(value)
    if positive and numeric <= 0:
        raise ValueError(f"{name} must be positive")
    if not positive and numeric < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value.item() if isinstance(value, np.generic) else value  # type: ignore[union-attr]


def validate_motion_censor_params(
    params: Mapping[str, object] | None,
) -> dict[str, object]:
    """Fill missing motion parameters and validate their values."""

    result = motion_censor_defaults()
    if params is not None:
        result.update(params)

    result["motion_censor_enable"] = _logical(
        result["motion_censor_enable"], "motion_censor_enable"
    )
    for name in (
        "motion_pixel_size_um",
        "motion_median_window_s",
        "motion_thresh",
        "motion_scale_floor_um",
    ):
        result[name] = _real_scalar(result[name], name, positive=True)
    for name in (
        "motion_abs_max_um",
        "motion_pad_s",
        "motion_merge_gap_s",
        "motion_discard_initial_s",
    ):
        result[name] = _real_scalar(result[name], name)

    samples = _real_scalar(result["motion_samples_per_cycle"], "motion_samples_per_cycle", positive=True)
    if not float(samples).is_integer():
        raise ValueError("motion_samples_per_cycle must be an integer")
    result["motion_samples_per_cycle"] = int(samples)

    fraction = float(
        _real_scalar(result["motion_max_frac_censored"], "motion_max_frac_censored", positive=True)
    )
    if fraction > 1:
        raise ValueError("motion_max_frac_censored must be at most 1")
    result["motion_max_frac_censored"] = fraction
    return result


__all__ = ["validate_motion_censor_params"]
