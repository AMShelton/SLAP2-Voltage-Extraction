from __future__ import annotations


def motion_censor_defaults() -> dict[str, object]:
    """Return the canonical motion-censor parameters."""

    return {
        "motion_censor_enable": False,
        "motion_pixel_size_um": 0.25,
        "motion_median_window_s": 4,
        "motion_thresh": 2.5,
        "motion_scale_floor_um": 0.25,
        "motion_abs_max_um": 0,
        "motion_pad_s": 0.025,
        "motion_merge_gap_s": 0.05,
        "motion_discard_initial_s": 0,
        "motion_samples_per_cycle": 1,
        "motion_max_frac_censored": 0.25,
    }


__all__ = ["motion_censor_defaults"]
