"""Direct Python translation of ``previewMotionCensor.m``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from source_extraction import (
    compute_motion_censor,
    motion_censor_defaults,
    read_source_online_motion,
    validate_motion_censor_params,
)


def preview_motion_censor(
    data_file: str | Path,
    params_in: Mapping[str, object] | None = None,
    show_gui: bool = False,
    *,
    reader_factory: Callable[[str | Path], object] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Read online offsets and return validated censor parameters and diagnostics.

    ``show_gui`` is accepted for API parity; interactive editing belongs in a
    frontend and does not change scientific computation.
    """

    del show_gui
    if reader_factory is None:
        try:
            from slap2 import MultiDataFiles  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "previewMotionCensor:MissingSLAP2Reader: pass reader_factory or install slap2"
            ) from exc
        reader_factory = MultiDataFiles

    params = motion_censor_defaults()
    if params_in:
        params.update({name: value for name, value in params_in.items() if name in params})
    params["motion_censor_enable"] = True
    params = validate_motion_censor_params(params)

    reader = reader_factory(data_file)
    try:
        metadata = getattr(reader, "metadata", getattr(reader, "metaData", {}))
        if isinstance(metadata, Mapping):
            line_period = metadata.get("line_period_s", metadata.get("linePeriod_s"))
        else:
            line_period = getattr(metadata, "line_period_s", getattr(metadata, "linePeriod_s"))
        line_rate_hz = 1.0 / float(line_period)
        motion = read_source_online_motion(
            reader, int(params["motion_samples_per_cycle"]), line_rate_hz
        )
        mask, info = compute_motion_censor(
            motion["x"], motion["y"], motion["fs_offsets"], params
        )
        info = dict(info)
        info["mask"] = np.asarray(mask, dtype=bool)
        info["motion"] = motion
        return params, info
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()


__all__ = ["preview_motion_censor"]
