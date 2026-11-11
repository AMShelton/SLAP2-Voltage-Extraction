"""Direct headless counterpart of MATLAB ``optionsGUI.m``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def options_gui(
    options: Mapping[str, Any],
    tooltips: Mapping[str, Any] | None = None,
    function_name: str | None = None,
    *,
    updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return options with known updates merged.

    Python callers normally use JSON/MAT presets through ``set_params``;
    interactive presentation is intentionally delegated to frontends.
    """

    del tooltips, function_name
    result = dict(options)
    if updates:
        result.update({name: value for name, value in updates.items() if name in result})
    return result


__all__ = ["options_gui"]