"""Direct Python translation of MATLAB ``TracePixel``."""

from __future__ import annotations

from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def _kernel(width: int) -> np.ndarray:
    positions = np.arange(-4 * width, 4 * width + 1, dtype=np.float32)
    values = np.exp(-np.abs(positions) / np.float32(width)).astype(np.float32)
    return values / np.sum(values, dtype=np.float32)


def _same_convolution(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    full = np.convolve(values, kernel, mode="full")
    start = (kernel.size - 1) // 2
    return np.asarray(full[start : start + values.size], dtype=np.float32)


@dataclass
class TracePixel:
    file_names: list[str] = field(default_factory=list)
    byte_offsets: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.uint32))
    line_idxs: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.uint32))
    first_cycle_offset_bytes: int = 0
    bytes_per_cycle: int = 0
    lines_per_cycle: int = 0
    super_pixel_id: int = 0
    super_pixel_num_pixels: np.float32 = np.float32(0)
    super_pixel_num_pixels_selected: np.float32 = np.float32(0)
    data: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    is_loaded: bool = False

    def load(self) -> TracePixel:
        if self.is_loaded:
            return self
        columns: list[np.ndarray] = []
        offsets = np.asarray(self.byte_offsets, dtype=np.int64).reshape(-1)
        for filename in self.file_names:
            path = Path(filename)
            nbytes = path.stat().st_size
            cycle_starts = np.arange(
                self.first_cycle_offset_bytes,
                nbytes,
                self.bytes_per_cycle,
                dtype=np.int64,
            )
            column = np.empty((offsets.size, cycle_starts.size), dtype=np.float32)
            with path.open("rb") as stream:
                for offset_index, offset in enumerate(offsets):
                    for cycle_index, cycle_start in enumerate(cycle_starts):
                        stream.seek(int(cycle_start + offset - 2))
                        sample = np.frombuffer(stream.read(2), dtype="<i2", count=1)
                        value = sample[0] if sample.size else 0
                        column[offset_index, cycle_index] = 0 if value == np.iinfo(np.int16).min else value
            columns.append(column)
        self.data = np.concatenate(columns, axis=1) if columns else np.empty((offsets.size, 0), dtype=np.float32)
        self.is_loaded = True
        return self

    @staticmethod
    def _process_many(
        pixels: list[TracePixel], window_width_lines: int, expected_window_width_lines: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if not pixels:
            empty = np.empty(0, dtype=np.float32)
            return empty.copy(), empty.copy(), empty.copy(), empty.copy()
        temporal = _kernel(window_width_lines)
        expected_kernel = np.ones(expected_window_width_lines, dtype=np.float32)
        sum_weighted: np.ndarray | None = None
        sum_expected: np.ndarray | None = None
        sum_expected_weighted: np.ndarray | None = None

        for pixel in pixels:
            pixel.load()
            cycles = pixel.data.shape[1]
            line_data = np.zeros((pixel.lines_per_cycle, cycles), dtype=np.float32)
            line_data[np.asarray(pixel.line_idxs, dtype=np.int64), :] = pixel.data
            flattened = line_data.reshape(-1, order="F")
            spatial_weight = np.float32(
                pixel.super_pixel_num_pixels_selected / pixel.super_pixel_num_pixels
            )
            weighted = _same_convolution(flattened, temporal * spatial_weight)
            expected = _same_convolution(flattened, expected_kernel)
            sampled = np.zeros_like(line_data)
            sampled[np.asarray(pixel.line_idxs, dtype=np.int64), :] = 1
            sampled_flat = sampled.reshape(-1, order="F")
            expected_count = _same_convolution(sampled_flat, expected_kernel)
            expected = expected / (expected_count + np.finfo(np.float32).eps)
            temp_weights = _same_convolution(sampled_flat, temporal)
            sum_weighted = weighted if sum_weighted is None else sum_weighted + weighted
            sum_expected = expected if sum_expected is None else sum_expected + expected
            contribution = expected * temp_weights
            sum_expected_weighted = (
                contribution
                if sum_expected_weighted is None
                else sum_expected_weighted + contribution
            )
            pixel.data = np.empty(0, dtype=np.float32)
            pixel.is_loaded = False

        assert sum_weighted is not None and sum_expected is not None and sum_expected_weighted is not None
        trace = sum_weighted / (sum_expected_weighted + np.finfo(np.float32).eps) * sum_expected
        return (
            np.asarray(trace, dtype=np.float32),
            np.asarray(sum_weighted, dtype=np.float32),
            np.asarray(sum_expected, dtype=np.float32),
            np.asarray(sum_expected_weighted, dtype=np.float32),
        )

    def process(
        self_or_pixels: TracePixel | list[TracePixel],
        window_width_lines: int,
        expected_window_width_lines: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        pixels = self_or_pixels if isinstance(self_or_pixels, list) else [self_or_pixels]
        return TracePixel._process_many(pixels, window_width_lines, expected_window_width_lines)

    def process_async(
        self_or_pixels: TracePixel | list[TracePixel],
        window_width_lines: int,
        expected_window_width_lines: int,
        *,
        executor: Executor | None = None,
    ) -> Future[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """Schedule :meth:`process` and return a standard Python future.

        When no executor is supplied, a temporary worker is retained until the
        operation finishes and then shut down. Callers processing many traces
        can supply a shared thread or process executor.
        """

        pixels = self_or_pixels if isinstance(self_or_pixels, list) else [self_or_pixels]
        owned_executor = executor is None
        selected_executor = executor or ThreadPoolExecutor(max_workers=1)
        future = selected_executor.submit(
            TracePixel._process_many,
            pixels,
            window_width_lines,
            expected_window_width_lines,
        )
        if owned_executor:
            future.add_done_callback(
                lambda _future: selected_executor.shutdown(wait=False)
            )
        return future


__all__ = ["TracePixel"]
