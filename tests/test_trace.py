from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest

trace_module = pytest.importorskip(
    "slap2_voltage_extraction.trace",
    reason="Python Trace/TracePixel translation has not been implemented yet",
)
Trace = trace_module.Trace


@dataclass
class Header:
    dmd_pixels_per_row: int
    dmd_pixels_per_column: int
    bytes_per_cycle: int
    first_cycle_offset_bytes: int
    lines_per_cycle: int


@dataclass
class DataFile:
    filename: str


@dataclass
class FakeMultiDataFiles:
    """Concrete-compatible metadata surface read by Trace."""

    header: Header
    z_pixel_replacement_maps: list[np.ndarray]
    h_data_files: list[DataFile]
    line_super_pixel_ids: list[np.ndarray]
    line_fast_z_idxs: np.ndarray
    line_data_start_idxs: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    fast_zs: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float64))


def mapping_source() -> FakeMultiDataFiles:
    return FakeMultiDataFiles(
        header=Header(3, 2, 64, 2, 4),
        z_pixel_replacement_maps=[
            np.asarray(
                [
                    [0, 1], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5],
                    [0, 6], [1, 6], [2, 7], [3, 8], [4, 9], [5, 10],
                ],
                dtype=np.uint32,
            )
        ],
        h_data_files=[DataFile("first.dat"), DataFile("second.dat")],
        line_super_pixel_ids=[
            np.asarray([1, 2, 6], dtype=np.uint32),
            np.asarray([2, 1], dtype=np.uint32),
            np.asarray([6, 1], dtype=np.uint32),
            np.asarray([1], dtype=np.uint32),
        ],
        line_fast_z_idxs=np.asarray([0, 0, 1, 0]),
        line_data_start_idxs=np.asarray([1, 10, 20, 30]),
    )


def processing_source(filename: Path) -> FakeMultiDataFiles:
    return FakeMultiDataFiles(
        header=Header(2, 2, 8, 0, 2),
        z_pixel_replacement_maps=[np.asarray([[0, 1]], dtype=np.uint32)],
        h_data_files=[DataFile(str(filename))],
        line_super_pixel_ids=[
            np.asarray([1], dtype=np.uint32),
            np.asarray([1], dtype=np.uint32),
        ],
        line_fast_z_idxs=np.asarray([0, 0]),
        line_data_start_idxs=np.asarray([1, 3]),
    )


class TestTrace:
    def test_constructor_stores_typed_inputs_and_defaults(self) -> None:
        source = mapping_source()

        trace = Trace(source)

        assert trace.multi_data_files is source
        assert trace.z_idx == 0
        assert trace.ch_idx == 0
        assert np.asarray(trace.pixel_idxs).size == 0
        assert np.asarray(trace.super_pixel_ids).size == 0

    def test_numeric_pixel_lists_create_expected_trace_pixels(self) -> None:
        trace = Trace(mapping_source(), z_idx=0, ch_idx=1)

        trace.set_pixel_idxs([0, 1], [6])

        np.testing.assert_array_equal(trace.pixel_idxs, np.asarray([0, 1, 6], dtype=np.uint32))
        np.testing.assert_array_equal(trace.super_pixel_ids, [1, 6])
        np.testing.assert_array_equal(
            [pixel.super_pixel_num_pixels for pixel in trace.trace_pixels],
            np.asarray([2, 2], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            [pixel.super_pixel_num_pixels_selected for pixel in trace.trace_pixels],
            np.asarray([2, 1], dtype=np.float32),
        )
        np.testing.assert_array_equal(trace.trace_pixels[0].line_idxs, np.asarray([0, 1, 3], dtype=np.uint32))
        np.testing.assert_array_equal(trace.trace_pixels[0].byte_offsets, np.asarray([6, 24, 60], dtype=np.uint32))
        np.testing.assert_array_equal(trace.trace_pixels[1].line_idxs, np.asarray([0], dtype=np.uint32))
        np.testing.assert_array_equal(trace.trace_pixels[1].byte_offsets, np.asarray([10], dtype=np.uint32))
        assert trace.trace_pixels[0].file_names == ["first.dat", "second.dat"]

    def test_logical_maps_and_transposed_map_match_numeric_indices(self) -> None:
        from_maps = Trace(mapping_source())
        from_lists = Trace(mapping_source())
        raster_map = np.zeros((3, 2), dtype=bool)
        raster_map[0, [0, 1]] = True
        integration_map = np.zeros((3, 2), dtype=bool)
        integration_map[0, 0] = True

        from_maps.set_pixel_idxs(raster_map, integration_map.T)
        from_lists.set_pixel_idxs([0, 1], [6])

        np.testing.assert_array_equal(from_maps.pixel_idxs, from_lists.pixel_idxs)
        np.testing.assert_array_equal(from_maps.super_pixel_ids, from_lists.super_pixel_ids)

    def test_incorrect_logical_map_size_fails(self) -> None:
        with pytest.raises((AssertionError, ValueError)):
            Trace(mapping_source()).set_pixel_idxs(np.zeros((4, 4), dtype=bool), [])

    def test_noninteger_pixel_list_fails_validation(self) -> None:
        with pytest.raises((TypeError, ValueError)) as caught:
            Trace(mapping_source()).set_pixel_idxs([1.5], [])
        assert "integer" in str(caught.value).lower()

    def test_unknown_pixels_are_retained_as_request_but_not_traces(self) -> None:
        trace = Trace(mapping_source())

        trace.set_pixel_idxs([0, 98], [])

        np.testing.assert_array_equal(trace.pixel_idxs, np.asarray([0, 98], dtype=np.uint32))
        np.testing.assert_array_equal(trace.super_pixel_ids, [1])

    def test_repeated_selection_does_not_duplicate_trace_pixels(self) -> None:
        trace = Trace(mapping_source())

        trace.set_pixel_idxs([0, 1], [6])
        trace.set_pixel_idxs([0, 1], [6])

        np.testing.assert_array_equal(trace.super_pixel_ids, [1, 6])
        assert len(trace.trace_pixels) == 2

    def test_load_data_and_process_delegate_to_trace_pixels(self, write_int16) -> None:
        filename = write_int16("trace.dat", np.full(8, 10, dtype=np.int16))
        trace_object = Trace(processing_source(filename))
        trace_object.set_pixel_idxs([0], [])

        trace_object.load_data()
        pixel = trace_object.trace_pixels[0]
        assert pixel.is_loaded is True
        np.testing.assert_array_equal(pixel.data, np.full((2, 2), 10, dtype=np.float32))

        trace, weight = trace_object.process(1, 1)

        assert pixel.is_loaded is False
        assert pixel.data.dtype == np.float32
        assert pixel.data.shape == (0,)
        assert trace.shape == (4,)
        assert weight.shape == (4,)
        np.testing.assert_allclose(trace, np.full(4, 10, dtype=np.float32), atol=1e-5, rtol=0)
        assert np.all(weight > 0)
