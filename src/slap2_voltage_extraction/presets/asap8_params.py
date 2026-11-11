"""ASAP8 voltage-extraction parameter preset."""

from __future__ import annotations

from collections.abc import Mapping

from ..parameters.set_params import set_params


def asap8_params(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    """Return voltage parameters for ASAP8-family brightening indicators."""

    values: dict[str, object] = {
        "indicator_name": "ASAP8",
        "indicator_direction": "increases",
    }
    if overrides:
        values.update(overrides)
    return set_params("Voltage", values)


__all__ = ["asap8_params"]
