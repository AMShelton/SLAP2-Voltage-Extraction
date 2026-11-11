"""Build GIAnT-compatible trial tables from SLAP2 recordings."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
from typing import Any

import numpy as np

from .io import save_struct_to_h5, scan_image_tiff_wrapper
from .exceptions import Slap2VoltageError


LINE_DIFFERENCE_THRESHOLD = 2_000
MULTICYCLE_LINES_PER_TRIAL = 200_000


def _default_data_reader(path: str | Path) -> object:
    try:
        from slap2 import Slap2DataFile  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "A SLAP2 data reader is required; pass data_reader or install the slap2 reader."
        ) from exc
    return Slap2DataFile(str(path))


def _line_count_and_period(reader: object) -> tuple[int, float]:
    count = int(getattr(reader, "total_num_lines", getattr(reader, "totalNumLines", 0)))
    if hasattr(reader, "line_period_s"):
        return count, float(reader.line_period_s)
    for container_name in ("hDataFile", "hMultiDataFiles"):
        container = getattr(reader, container_name, None)
        if container is not None:
            metadata = getattr(container, "metadata", getattr(container, "metaData", None))
            if isinstance(metadata, dict):
                return count, float(metadata.get("line_period_s", metadata["linePeriod_s"]))
            return count, float(getattr(metadata, "line_period_s", getattr(metadata, "linePeriod_s")))
    raise ValueError("Could not read data-file line period")


def _reference_file(root: Path, dmd: int) -> Path:
    all_references = [
        path for path in root.rglob("*.tif*") if f"DMD{dmd}" in path.name and "REFERENCE" in path.name
    ]
    preferred = [path for path in all_references if "_CONFIG1-REFERENCE" in path.name]
    candidates = preferred or [path for path in all_references if "-REFERENCE" in path.name]
    if not candidates:
        raise FileNotFoundError(f"Could not find DMD{dmd} reference image within {root}")
    if len(candidates) != 1:
        qualifier = "CONFIG1 " if preferred else ""
        raise ValueError(f"Too many {qualifier}reference stacks found for DMD{dmd}")
    return candidates[0]


def _reference_stack(
    root: Path,
    tiff_reader: Callable[[str | Path], tuple[np.ndarray, str, list[Any]]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dmd in (1, 2):
        image, _, descriptions = tiff_reader(_reference_file(root, dmd))
        decoded = [json.loads(item) if isinstance(item, str) else item for item in descriptions]
        channels: list[Any] = []
        depths: list[Any] = []
        first_channel = decoded[0]["channel"]
        for description in decoded:
            channel = description["channel"]
            if channel not in channels:
                channels.append(channel)
            if channel == first_channel:
                depths.append(description["z"])
        result[f"Path{dmd}"] = {
            "IM": np.asarray(image),
            "channels": np.asarray(channels),
            "Zs": np.asarray(depths),
            "dmdPixel2SampleTransform": np.asarray(
                decoded[-1]["dmdPixel2SampleTransform"]
            ),
        }
    return result


def _rounded_edges(total: int, count: int) -> np.ndarray:
    # MATLAB lineage: trial boundaries use positive half-up rounding, not Python's ties-to-even round().
    values = np.linspace(1, total + 1, count + 1)
    return np.floor(values + 0.5).astype(np.int64)


def build_trial_table_slap2(
    directory: str | Path,
    save_directory: str | Path | None = None,
    use_all_files: bool = False,
    *,
    data_reader: Callable[[str | Path], object] | None = None,
    tiff_reader: Callable[[str | Path], tuple[np.ndarray, str, list[Any]]] | None = None,
) -> dict[str, Any]:
    """Build and write the GIAnT-compatible one-based inclusive trial table."""

    root = Path(directory)
    save_dir = Path(save_directory) if save_directory is not None else root
    save_dir.mkdir(parents=True, exist_ok=True)
    data_dir = root / "dynamic_data" if (root / "dynamic_data").is_dir() else root
    files = sorted(data_dir.glob("*.dat"), key=lambda path: path.stat().st_mtime)
    files = [
        path
        for path in files
        if not (match := re.search(r"CYCLE-?(\d+)", path.name)) or int(match.group(1)) == 0
    ]
    if not files:
        raise Slap2VoltageError(
            "buildTrialTableSLAP2:NoDatFiles", f"No SLAP2 .dat files found in: {data_dir}"
        )
    if not use_all_files:
        # Interactive epoch selection has no headless equivalent. A caller that needs
        # selected epochs should invoke this function separately for each selection.
        raise ValueError("use_all_files=False requires an interactive frontend")

    read_data = data_reader or _default_data_reader
    read_tiff = tiff_reader or scan_image_tiff_wrapper
    references = _reference_stack(root, read_tiff)
    records: list[tuple[Path, int, float]] = []
    for path in files:
        count, period = _line_count_and_period(read_data(path))
        records.append((path, count, period))

    dmd1 = sorted((item for item in records if "DMD1" in item[0].name), key=lambda item: item[0].stat().st_mtime)
    dmd2 = sorted((item for item in records if "DMD1" not in item[0].name), key=lambda item: item[0].stat().st_mtime)
    if not dmd1 or not dmd2:
        raise ValueError("Both DMD1 and DMD2 files are required")

    filenames: list[list[str]] = [[], []]
    first_lines: list[list[int]] = [[], []]
    last_lines: list[list[int]] = [[], []]
    end_times: list[float] = []
    start_times: list[float] = []

    if "-CYCLE" in dmd1[0][0].name:
        if len(dmd1) != len(dmd2):
            raise ValueError("Unequal DMD source counts for continuous acquisition")
        for left, right in zip(dmd1, dmd2, strict=True):
            total = min(left[1], right[1])
            trial_count = int(np.ceil(total / MULTICYCLE_LINES_PER_TRIAL))
            edges = _rounded_edges(total, trial_count)
            for first, stop in zip(edges[:-1], edges[1:], strict=True):
                last = int(stop - 1)
                filenames[0].append(left[0].name)
                filenames[1].append(right[0].name)
                for path_index in (0, 1):
                    first_lines[path_index].append(int(first))
                    last_lines[path_index].append(last)
                end = left[0].stat().st_mtime - (left[1] - last) * left[2]
                start = left[0].stat().st_mtime - (left[1] - int(first)) * left[2]
                end_times.append(end)
                start_times.append(start)
    else:
        left_index = right_index = 0
        accumulated = [0, 0]
        while left_index < len(dmd1) and right_index < len(dmd2):
            left_future = np.cumsum([item[1] for item in dmd1[left_index : left_index + 5]]) - accumulated[0]
            right_future = np.cumsum([item[1] for item in dmd2[right_index : right_index + 5]]) - accumulated[1]
            if np.min(np.abs(left_future[:, None] - right_future[None, :])) >= LINE_DIFFERENCE_THRESHOLD:
                raise ValueError("Error lining up trials across DMDs")
            lines = int(min(left_future[0], right_future[0]))
            left, right = dmd1[left_index], dmd2[right_index]
            filenames[0].append(left[0].name)
            filenames[1].append(right[0].name)
            first_lines[0].append(accumulated[0] + 1)
            first_lines[1].append(accumulated[1] + 1)
            last_lines[0].append(accumulated[0] + lines)
            last_lines[1].append(accumulated[1] + lines)
            difference = int(left_future[0] - right_future[0])
            if abs(difference) < LINE_DIFFERENCE_THRESHOLD:
                source = left
                left_index += 1
                right_index += 1
                accumulated = [0, 0]
            elif difference < 0:
                source = left
                left_index += 1
                accumulated = [0, accumulated[1] + lines]
            else:
                source = right
                right_index += 1
                accumulated = [accumulated[0] + lines, 0]
            end_times.append(source[0].stat().st_mtime)
            start_times.append(source[0].stat().st_mtime - lines * source[2])

    trial_count = len(end_times)
    trial_table: dict[str, Any] = {
        "datadr": str(data_dir),
        "savedr": str(save_dir),
        "filename": np.asarray(filenames, dtype=object),
        "true_trial_ix": np.tile(np.arange(1, trial_count + 1), (2, 1)),
        "epoch": np.ones((2, trial_count), dtype=np.int64),
        "slap2_info": {
            "ref_stack": references,
            "first_line": np.asarray(first_lines, dtype=np.int64),
            "last_line": np.asarray(last_lines, dtype=np.int64),
            "trial_end_time_from_pc": np.asarray(end_times),
            "trial_start_time_inferred": np.asarray(start_times),
            "line_range_convention": "inclusive",
        },
    }
    save_struct_to_h5(trial_table, save_dir / "trial_table.h5")
    return trial_table


__all__ = ["build_trial_table_slap2"]
