from __future__ import annotations

from typing import Any

import numpy as np

from ..exceptions import Slap2VoltageError


def _text(value: object, default: str) -> str:
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _resolve_direction(indicator_name: str, requested: str) -> tuple[int, str, str]:
    normalized = requested.strip().lower()
    indicator = indicator_name.strip().lower()

    if normalized in {"increases", "increase", "standard", "positive", "brightens"}:
        return 1, "increases", "explicit"
    if normalized in {
        "decreases",
        "decrease",
        "inverted",
        "negative",
        "quenched",
        "quenching",
    }:
        return -1, "decreases", "explicit"
    if normalized == "auto":
        if "asap8" in indicator:
            return 1, "increases", "indicator_name"
        if "asap7" in indicator:
            return -1, "decreases", "indicator_name"
        raise Slap2VoltageError(
            "computeVoltageDFF:UnknownIndicatorDirection",
            'indicator_direction="auto" requires indicator_name to identify the fluorescence '
            "polarity. Set indicator_name to ASAP7/ASAP8 or set indicator_direction explicitly.",
        )
    raise Slap2VoltageError(
        "computeVoltageDFF:InvalidDirection",
        "indicator_direction must be auto, increases, or decreases.",
    )


def _median_absolute_finite(raw: np.ndarray) -> np.float32:
    finite = np.abs(raw[np.isfinite(raw)])
    fallback = np.median(finite) if finite.size else np.nan
    if not np.isfinite(fallback) or fallback <= np.finfo(np.float32).eps:
        fallback = 1.0
    return np.float32(fallback)


def compute_voltage_dff(
    raw_f: Any,
    f0: Any,
    indicator_name: object = "",
    indicator_direction: object = "auto",
    precision: object = "single",
) -> tuple[np.ndarray, dict[str, object]]:
    """Compute polarity-corrected voltage dF/F.

    Positive output represents positive membrane-voltage deflection. Calculations
    are performed in float32 to preserve the reference implementation's behavior,
    then optionally cast to float64.
    """

    name = _text(indicator_name, "")
    requested = _text(indicator_direction, "auto")
    precision_name = _text(precision, "single")
    sign, resolved, source = _resolve_direction(name, requested)

    raw = np.asarray(raw_f, dtype=np.float32)
    baseline = np.asarray(f0, dtype=np.float32)
    if raw.shape != baseline.shape:
        raise Slap2VoltageError(
            "computeVoltageDFF:SizeMismatch",
            "raw_f and f0 must have identical shape.",
        )

    baseline = baseline.copy()
    fallback = _median_absolute_finite(raw)
    bad = ~np.isfinite(baseline) | (np.abs(baseline) <= np.finfo(np.float32).eps)
    baseline[bad] = fallback

    with np.errstate(divide="ignore", invalid="ignore"):
        dff_single = np.asarray(np.float32(sign) * (raw - baseline) / baseline, dtype=np.float32)
    dff = dff_single.astype(np.float64) if precision_name.lower() == "double" else dff_single

    formula = "dff = (F - F0) / F0" if sign > 0 else "dff = (F0 - F) / F0"
    metadata: dict[str, object] = {
        "indicator_name": name,
        "indicator_direction_requested": requested,
        "indicator_direction_resolved": resolved,
        "direction_source": source,
        "dff_sign": sign,
        "formula": formula,
    }
    return dff, metadata


__all__ = ["compute_voltage_dff"]
