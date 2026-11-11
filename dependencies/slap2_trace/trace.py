"""Direct Python translation of MATLAB ``Trace``."""

from __future__ import annotations

from concurrent.futures import Executor, Future
from typing import Any

import numpy as np

from .trace_pixel import TracePixel


class Trace:
    def __init__(self, multi_data_files: object, z_idx: int = 0, ch_idx: int = 0) -> None:
        self.multi_data_files = multi_data_files
        self.z_idx = int(z_idx)
        self.ch_idx = int(ch_idx)
        self.trace_pixels: list[TracePixel] = []
        self.pixel_idxs = np.empty(0, dtype=np.uint32)

    @property
    def super_pixel_ids(self) -> np.ndarray:
        return np.asarray([pixel.super_pixel_id for pixel in self.trace_pixels], dtype=np.uint32)

    def _logical_indices(self, value: object, integration: bool) -> np.ndarray:
        array = np.asarray(value)
        rows = int(self.multi_data_files.header.dmd_pixels_per_row)
        columns = int(self.multi_data_files.header.dmd_pixels_per_column)
        if array.shape == (columns, rows) and columns != rows:
            array = array.T
        if array.shape != (rows, columns):
            raise AssertionError(f"Map must have shape ({rows}, {columns})")
        indices = np.flatnonzero(array.reshape(-1, order="C"))
        if integration:
            indices += array.size
        return indices.astype(np.uint32)

    @staticmethod
    def _numeric_indices(value: object) -> np.ndarray:
        array = np.asarray(value)
        if array.size == 0:
            return np.empty(0, dtype=np.uint32)
        if not np.issubdtype(array.dtype, np.number) or np.any(~np.isfinite(array)) or np.any(array != np.round(array)):
            raise ValueError("Pixel indices must be finite integers")
        if np.any(array < 0):
            raise ValueError("Pixel indices must be nonnegative")
        return array.astype(np.uint32).reshape(-1)

    def set_pixel_idxs(self, raster_pixels: object = (), integration_pixels: object = ()) -> None:
        raster_array = np.asarray(raster_pixels)
        integration_array = np.asarray(integration_pixels)
        raster = (
            self._logical_indices(raster_array, False)
            if raster_array.dtype == bool and raster_array.size
            else self._numeric_indices(raster_pixels)
        )
        integration = (
            self._logical_indices(integration_array, True)
            if integration_array.dtype == bool and integration_array.size
            else self._numeric_indices(integration_pixels)
        )
        self.pixel_idxs = np.concatenate((raster, integration)).astype(np.uint32)
        self.trace_pixels = self._get_trace_pixels(self.pixel_idxs)

    def _get_trace_pixels(self, pixel_idxs: np.ndarray) -> list[TracePixel]:
        requested = np.unique(pixel_idxs.astype(np.uint32))
        replacement = np.asarray(self.multi_data_files.z_pixel_replacement_maps[self.z_idx], dtype=np.uint32).copy()
        dmd_pixels = (
            int(self.multi_data_files.header.dmd_pixels_per_row)
            * int(self.multi_data_files.header.dmd_pixels_per_column)
        )
        integration = replacement[:, 1] >= dmd_pixels
        replacement[integration, 0] += dmd_pixels
        by_pixel = {int(source): int(target) for source, target in replacement}
        mapped = [by_pixel[int(index)] for index in requested if int(index) in by_pixel]
        if not mapped:
            return []
        super_ids, selected_counts = np.unique(mapped, return_counts=True)
        all_ids, all_counts = np.unique(replacement[:, 1], return_counts=True)
        full_counts = dict(zip(all_ids.tolist(), all_counts.tolist(), strict=True))
        files = [str(item.filename) for item in self.multi_data_files.h_data_files]
        pixels = [
            TracePixel(
                file_names=files,
                first_cycle_offset_bytes=int(self.multi_data_files.header.first_cycle_offset_bytes),
                bytes_per_cycle=int(self.multi_data_files.header.bytes_per_cycle),
                lines_per_cycle=int(self.multi_data_files.header.lines_per_cycle),
                super_pixel_id=int(super_id),
                super_pixel_num_pixels=np.float32(full_counts[int(super_id)]),
                super_pixel_num_pixels_selected=np.float32(selected),
            )
            for super_id, selected in zip(super_ids, selected_counts, strict=True)
        ]
        by_id = {pixel.super_pixel_id: pixel for pixel in pixels}
        for line_index, line_ids in enumerate(self.multi_data_files.line_super_pixel_ids):
            if int(self.multi_data_files.line_fast_z_idxs[line_index]) != self.z_idx:
                continue
            ids = np.asarray(line_ids, dtype=np.uint32).reshape(-1)
            for super_id in super_ids:
                matches = np.flatnonzero(ids == super_id)
                if not matches.size:
                    continue
                offset = int(matches[0]) * 2
                offset += ids.size * 2 * self.ch_idx
                # line_data_start_idxs retains the source reader's one-based int16 position.
                offset += int(self.multi_data_files.line_data_start_idxs[line_index]) * 2
                offset -= int(self.multi_data_files.header.first_cycle_offset_bytes)
                pixel = by_id[int(super_id)]
                pixel.byte_offsets = np.append(pixel.byte_offsets, np.uint32(offset))
                pixel.line_idxs = np.append(pixel.line_idxs, np.uint32(line_index))
        return sorted(pixels, key=lambda pixel: pixel.super_pixel_id)

    def load_data(self) -> None:
        for pixel in self.trace_pixels:
            pixel.load()

    def process(self, window_width_lines: int, expected_window_width_lines: int) -> tuple[np.ndarray, np.ndarray]:
        trace, weight, _, _ = TracePixel.process(
            self.trace_pixels, window_width_lines, expected_window_width_lines
        )
        return trace, weight

    def process_async(
        self,
        window_width_lines: int,
        expected_window_width_lines: int,
        *,
        executor: Executor | None = None,
    ) -> Future[tuple[np.ndarray, np.ndarray]]:
        """Schedule trace processing and return a future for ``(trace, weight)``."""

        pixel_future = TracePixel.process_async(
            self.trace_pixels,
            window_width_lines,
            expected_window_width_lines,
            executor=executor,
        )
        result: Future[tuple[np.ndarray, np.ndarray]] = Future()

        def finalize(completed: Future[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]) -> None:
            try:
                trace, weight, _, _ = completed.result()
                result.set_result((trace, weight))
            except BaseException as exc:
                result.set_exception(exc)

        pixel_future.add_done_callback(finalize)
        return result


__all__ = ["Trace"]
