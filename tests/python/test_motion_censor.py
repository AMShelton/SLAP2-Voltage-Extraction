from __future__ import annotations

import numpy as np
import pytest

motion = pytest.importorskip(
    "slap2_voltage_extraction.motion",
    reason="Python motion-censor translation has not been implemented yet",
)

motion_censor_defaults = motion.motion_censor_defaults
validate_motion_censor_params = motion.validate_motion_censor_params
compute_motion_censor = motion.compute_motion_censor
expand_motion_mask_to_lines = motion.expand_motion_mask_to_lines


def base_params() -> dict[str, object]:
    params = motion_censor_defaults()
    params["motionCensorEnable"] = True
    return params


def _mask(result: object) -> np.ndarray:
    if isinstance(result, tuple):
        result = result[0]
    mask = np.asarray(result)
    assert mask.dtype == np.bool_
    assert mask.ndim == 2 and mask.shape[1] == 1
    return mask[:, 0]


def test_defaults_validate() -> None:
    params = validate_motion_censor_params({})
    assert params["motionCensorEnable"] is False
    assert params["motionPixelSize_um"] == 0.25
    assert params["motionThresh"] == 2.5


def test_set_params_exposes_motion_fields() -> None:
    parameters = pytest.importorskip(
        "slap2_voltage_extraction.parameters",
        reason="Python parameter translation has not been implemented yet",
    )
    set_params = parameters.set_params
    params = set_params("Voltage", {})
    assert set(motion_censor_defaults()) <= set(params)
    assert params["motionCensorEnable"] is False


def test_stationary_nothing_censored() -> None:
    mask = _mask(compute_motion_censor(np.zeros((1000, 1)), np.zeros((1000, 1)), 50, base_params()))
    assert not mask.any()


def test_constant_offset_is_drift_not_motion() -> None:
    mask = _mask(
        compute_motion_censor(np.full((1000, 1), 8), np.full((1000, 1), -6), 50, base_params())
    )
    assert not mask.any()


def test_jump_is_censored_and_padded() -> None:
    x = np.zeros((1000, 1))
    y = np.zeros((1000, 1))
    # MATLAB samples 500:504 map to Python positions 499:504.
    x[499:504] = 12
    x[[497, 498, 504, 505]] = 2
    params = base_params()
    params.update(motionPad_s=0, motionMergeGap_s=0)
    mask = _mask(compute_motion_censor(x, y, 50, params))
    np.testing.assert_array_equal(np.flatnonzero(mask) + 1, np.arange(500, 505))

    # Two samples of padding per side, extending only into shoulders above threshold/2.
    params["motionPad_s"] = 0.04
    padded = _mask(compute_motion_censor(x, y, 50, params))
    np.testing.assert_array_equal(np.flatnonzero(padded) + 1, np.arange(498, 507))


def test_nearby_spans_merge() -> None:
    x = np.zeros((1000, 1))
    y = np.zeros((1000, 1))
    x[499:502] = 12
    x[504:507] = 12
    params = base_params()
    params.update(motionPad_s=0, motionMergeGap_s=0.1)
    mask = _mask(compute_motion_censor(x, y, 50, params))
    assert mask[499:507].all()


def test_absolute_cap() -> None:
    x = np.full((1000, 1), 20)
    y = np.zeros((1000, 1))
    params = base_params()
    params["motionAbsMax_um"] = 3
    mask = _mask(compute_motion_censor(x, y, 50, params))
    assert mask.all()


def test_nonfinite_offsets_censored() -> None:
    x = np.zeros((200, 1))
    y = np.zeros((200, 1))
    x[49] = np.nan
    mask = _mask(compute_motion_censor(x, y, 50, base_params()))
    assert mask[49]


def test_discard_initial() -> None:
    params = base_params()
    params["motionDiscardInitial_s"] = 1
    mask = _mask(compute_motion_censor(np.zeros((500, 1)), np.zeros((500, 1)), 50, params))
    assert mask[:50].all()
    assert not mask[50:].any()


def test_expand_mask_to_lines() -> None:
    # Public line IDs remain 1-based. Each sample covers its line through the line before the next ID.
    line_mask = np.asarray(expand_motion_mask_to_lines([False, True, False], [1, 5, 9], 12))
    assert line_mask.shape == (12, 1)
    assert line_mask.dtype == np.bool_
    np.testing.assert_array_equal(
        line_mask.reshape(-1), [False] * 4 + [True] * 4 + [False] * 4
    )

    # Lines preceding the first sampled line take the first sample.
    line_mask = np.asarray(expand_motion_mask_to_lines([True, False], [3, 7], 8))
    np.testing.assert_array_equal(line_mask.reshape(-1), [True] * 6 + [False] * 2)


def test_expand_rejects_bad_ids() -> None:
    with pytest.raises(Exception) as caught:
        expand_motion_mask_to_lines([True, False], [5, 3], 8)
    assert getattr(caught.value, "code", None) == "expandMotionMaskToLines:InvalidLineIds" or (
        "expandMotionMaskToLines:InvalidLineIds" in str(caught.value)
    )


def test_censored_samples_do_not_bias_f0() -> None:
    parameters = pytest.importorskip(
        "slap2_voltage_extraction.parameters",
        reason="Python parameter translation has not been implemented yet",
    )
    baseline = pytest.importorskip(
        "slap2_voltage_extraction.baseline",
        reason="Python F0 translation has not been implemented yet",
    )
    normalization = pytest.importorskip(
        "slap2_voltage_extraction.normalization",
        reason="Python dF/F translation has not been implemented yet",
    )
    set_params = parameters.set_params
    compute_voltage_f0 = baseline.compute_voltage_f0
    compute_voltage_dff = normalization.compute_voltage_dff
    # RandomState reproduces NumPy's stable MT19937 sequence for a deterministic fixture.
    rng = np.random.RandomState(1)
    fs = 100
    n = 6000
    raw = np.asarray(100 + 0.5 * rng.standard_normal((n, 1)), dtype=np.float32)
    censor = np.zeros((n, 1), dtype=bool)
    censor[1999:2600] = True
    raw[censor] = np.float32(300)
    params = set_params("Voltage", {"f0Method": "robust", "f0Bin_s": 1, "f0Smooth_s": 3})

    unmasked_f0, _ = compute_voltage_f0(raw, fs, params)
    assert np.max(unmasked_f0) > 150

    masked = raw.copy()
    masked[censor] = np.nan
    f0, _ = compute_voltage_f0(masked, fs, params)
    assert np.isfinite(f0).all()
    assert np.max(np.abs(f0 - 100)) < 2
    dff, _ = compute_voltage_dff(masked, f0, "ASAP8", "increases", "single")
    assert np.isnan(dff[censor]).all()
    assert np.isfinite(dff[~censor]).all()
    assert dff.dtype == np.float32


def test_all_censored_epoch_is_safe() -> None:
    parameters = pytest.importorskip(
        "slap2_voltage_extraction.parameters",
        reason="Python parameter translation has not been implemented yet",
    )
    baseline = pytest.importorskip(
        "slap2_voltage_extraction.baseline",
        reason="Python F0 translation has not been implemented yet",
    )
    set_params = parameters.set_params
    compute_voltage_f0 = baseline.compute_voltage_f0
    params = set_params("Voltage", {"f0Method": "robust", "f0Bin_s": 1, "f0Smooth_s": 3})
    raw = np.full((1000, 1), np.nan, dtype=np.float32)
    f0, _ = compute_voltage_f0(raw, 100, params)
    assert np.isfinite(f0).all()


def test_public_motion_api_is_importable() -> None:
    """Python replacement for MATLAB source/path wiring assertions."""
    expected = {
        "motion_censor_defaults",
        "validate_motion_censor_params",
        "compute_motion_censor",
        "expand_motion_mask_to_lines",
    }
    assert expected <= set(dir(motion))
    for name in expected:
        assert callable(getattr(motion, name))
