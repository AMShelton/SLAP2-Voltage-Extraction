"""Direct Python translation of ``ASAP7_params.m``."""

from __future__ import annotations

from collections.abc import Mapping

from dependencies.gui.set_params import set_params


def asap7_params(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    """Return voltage parameters for ASAP7-family quenched indicators."""

    values: dict[str, object] = {
        "indicator_name": "ASAP7",
        "indicator_direction": "decreases",
    }
    if overrides:
        values.update(overrides)
    return set_params("Voltage", values)


__all__ = ["asap7_params"]
