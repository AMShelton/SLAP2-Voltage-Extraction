from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from preview_motion_censor import preview_motion_censor


class FakeMotionReader:
    """Minimal Python-native reader exposing zero-based line IDs."""

    def __init__(self, filename: str | Path) -> None:
        path = Path(filename)
        if not path.is_file():
            raise FileNotFoundError(path)
        self.metadata = {"line_period_s": 0.001}
        self.line_header_idxs = np.arange(8)
        self.num_cycles = 2
        self.closed = False

    def get_online_motion(
        self, line_ids: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        ids = np.asarray(line_ids, dtype=np.int64)
        return np.zeros(ids.size), np.zeros(ids.size), ids.astype(float)

    def close(self) -> None:
        self.closed = True


def test_headless_stationary_preview_returns_scientific_result(tmp_path: Path) -> None:
    filename = tmp_path / "stationary.dat"
    filename.touch()

    params, info = preview_motion_censor(
        filename, {}, False, reader_factory=FakeMotionReader
    )

    assert params["motion_censor_enable"] is True
    assert not np.any(info["mask"])
    assert info["fraction_censored"] == 0
    motion = info["motion"]
    np.testing.assert_array_equal(motion["x"], np.zeros(2))
    np.testing.assert_array_equal(motion["y"], np.zeros(2))
    np.testing.assert_array_equal(motion["z"], [0, 8])
    np.testing.assert_array_equal(motion["line_ids"], [0, 8])
    assert motion["num_cycles"] == 2
    assert motion["lines_per_cycle"] == 8
    assert motion["fs_offsets"] == 125


def test_headless_preview_merges_known_overrides_only(tmp_path: Path) -> None:
    filename = tmp_path / "overrides.dat"
    filename.touch()

    params, info = preview_motion_censor(
        filename,
        {
            "motion_pixel_size_um": 0.5,
            "motion_samples_per_cycle": 2,
            "unknown_field": 123,
        },
        False,
        reader_factory=FakeMotionReader,
    )

    assert params["motion_pixel_size_um"] == 0.5
    assert params["motion_samples_per_cycle"] == 2
    assert "unknown_field" not in params
    motion = info["motion"]
    np.testing.assert_array_equal(motion["line_ids"], [0, 4, 8, 12])
    assert motion["fs_offsets"] == 250
    assert not np.any(info["mask"])


def test_invalid_motion_override_is_rejected(tmp_path: Path) -> None:
    filename = tmp_path / "invalid.dat"
    filename.touch()

    with pytest.raises(ValueError, match="motion_samples_per_cycle must be positive"):
        preview_motion_censor(
            filename,
            {"motion_samples_per_cycle": 0},
            False,
            reader_factory=FakeMotionReader,
        )