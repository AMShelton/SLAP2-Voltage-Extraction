from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .compute_motion_censor import compute_motion_censor
from .expand_motion_mask_to_lines import expand_motion_mask_to_lines
from .read_source_online_motion import read_source_online_motion
from .validate_motion_censor_params import validate_motion_censor_params


def compute_source_motion_mask(
    multi_data_files: object,
    params: Mapping[str, object] | None,
    line_rate_hz: float,
) -> tuple[np.ndarray, dict[str, object]]:
    """Compute a line-resolution motion-censor mask for one SLAP2 source."""

    options = validate_motion_censor_params(params)
    motion = read_source_online_motion(
        multi_data_files,
        int(options["motion_samples_per_cycle"]),
        line_rate_hz,
    )
    sample_mask, info = compute_motion_censor(
        motion["x"],
        motion["y"],
        motion["fs_offsets"],
        options,
    )
    line_mask = expand_motion_mask_to_lines(
        sample_mask,
        motion["line_ids"],
        int(motion["total_lines"]),
    )
    info.update(
        {
            "line_ids": motion["line_ids"],
            "x_offset_pix": motion["x"],
            "y_offset_pix": motion["y"],
            "z_offset_um": motion["z"],
            "lines_per_cycle": motion["lines_per_cycle"],
            "num_cycles": motion["num_cycles"],
            "total_lines": motion["total_lines"],
            "sample_times_s": motion["sample_times_s"],
        }
    )
    return line_mask, info


__all__ = ["compute_source_motion_mask"]
