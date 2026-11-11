from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

trace_module = pytest.importorskip(
    "dependencies.slap2_trace",
    reason="Python Trace/TracePixel translation has not been implemented yet",
)
TracePixel = trace_module.TracePixel


def make_pixel(
    filenames: Path | list[Path],
    byte_offsets: list[int],
    line_idxs: list[int],
) -> object:
    """Build a TracePixel using zero-based internal line indices."""
    if isinstance(filenames, Path):
        filenames = [filenames]
    return TracePixel(
        file_names=[str(path) for path in filenames],
        byte_offsets=np.asarray(byte_offsets, dtype=np.uint32),
        line_idxs=np.asarray(line_idxs, dtype=np.uint32),
        first_cycle_offset_bytes=0,
        bytes_per_cycle=8,
        lines_per_cycle=4,
        super_pixel_num_pixels=np.float32(1),
        super_pixel_num_pixels_selected=np.float32(1),
    )


def loaded_pixel(value: np.float32, spatial_weight: np.float32) -> object:
    return TracePixel(
        data=np.full((2, 2), value, dtype=np.float32),
        is_loaded=True,
        line_idxs=np.asarray([0, 1], dtype=np.uint32),
        lines_per_cycle=2,
        super_pixel_num_pixels=np.float32(1),
        super_pixel_num_pixels_selected=spatial_weight,
    )


class TestTracePixel:
    def test_load_reads_offsets_across_cycles_and_files(self, write_int16) -> None:
        file_a = write_int16(
            "a.dat",
            [11, 99, np.iinfo(np.int16).min, 88, 21, 77, 31, 66],
        )
        file_b = write_int16("b.dat", [-1, 9, -2, 8, -3, 7, -4, 6])
        pixel = make_pixel([file_a, file_b], [2, 6], [0, 2])

        pixel.load()

        assert pixel.is_loaded is True
        assert pixel.data.dtype == np.float32
        np.testing.assert_array_equal(
            pixel.data,
            np.asarray([[11, 21, -1, -3], [0, 31, -2, -4]], dtype=np.float32),
        )

    def test_load_is_idempotent_after_file_changes(self, write_int16) -> None:
        filename = write_int16("stable.dat", [3, 0, 3, 0, 3, 0, 3, 0])
        pixel = make_pixel(filename, [2], [0])
        pixel.load()
        original = pixel.data.copy()

        write_int16("stable.dat", np.full(8, 99, dtype=np.int16))
        pixel.load()

        np.testing.assert_array_equal(pixel.data, original)

    def test_load_replaces_int16_sentinel_only(self, write_int16) -> None:
        limits = np.iinfo(np.int16)
        filename = write_int16("sentinel.dat", [limits.min, 0, limits.max, 0])
        pixel = make_pixel(filename, [2, 6], [0, 1])
        pixel.bytes_per_cycle = 8

        pixel.load()

        np.testing.assert_array_equal(
            pixel.data,
            np.asarray([[0], [limits.max]], dtype=np.float32),
        )

    def test_process_single_pixel_has_analytical_constant_result(self, write_int16) -> None:
        filename = write_int16("constant.dat", np.full(8, 10, dtype=np.int16))
        pixel = make_pixel(filename, [2, 6], [1, 3])
        pixel.super_pixel_num_pixels = np.float32(4)
        pixel.super_pixel_num_pixels_selected = np.float32(2)

        trace, weighted, expected, expected_weighted = pixel.process(1, 1)

        sampled = np.asarray([1, 3, 5, 7])
        unsampled = np.setdiff1d(np.arange(8), sampled)
        assert pixel.is_loaded is False
        assert pixel.data.dtype == np.float32
        assert pixel.data.shape == (0,)
        for result in (trace, weighted, expected, expected_weighted):
            assert result.shape == (8,)
            assert result.dtype == np.float32
        np.testing.assert_allclose(trace[sampled], 5, atol=1e-5, rtol=0)
        np.testing.assert_array_equal(trace[unsampled], np.zeros(4, dtype=np.float32))
        np.testing.assert_allclose(expected[sampled], 10, atol=1e-5, rtol=0)
        assert np.all(weighted > 0)
        assert np.all(expected_weighted[sampled] > 0)

    def test_process_aggregates_pixels_before_normalization(self) -> None:
        pixels = [
            loaded_pixel(np.float32(10), np.float32(0.5)),
            loaded_pixel(np.float32(20), np.float32(0.5)),
        ]

        trace, _, _, _ = TracePixel.process(pixels, 1, 1)

        np.testing.assert_allclose(
            trace,
            np.full(4, 15, dtype=np.float32),
            atol=1e-5,
            rtol=0,
        )
        for pixel in pixels:
            assert pixel.is_loaded is False
            assert pixel.data.dtype == np.float32
            assert pixel.data.shape == (0,)

    def test_process_empty_array_returns_empty_vectors(self) -> None:
        pixels: list[object] = []

        trace, weighted, expected, expected_weighted = TracePixel.process(pixels, 1, 1)

        assert pixels == []
        for result in (trace, weighted, expected, expected_weighted):
            assert result.shape == (0,)
            assert result.dtype == np.float32
