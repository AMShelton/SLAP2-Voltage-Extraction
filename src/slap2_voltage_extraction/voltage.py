"""Extract native-rate voltage signals and write the public HDF5 contract.

For compatibility with established consumers, path names are ``Path1`` based,
trial-table line bounds are one-based and inclusive, and temporal data
are stored with shape ``(n_rois, 1, n_samples)``. Python implementation details
use zero-based indices and half-open slices.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import time
from typing import Any
import warnings

import h5py
import numpy as np

from .parameters.set_params import set_params
from .io import load_struct_from_h5, save_struct_to_h5
from .trace import Trace
from .source_extraction import (
    compute_source_motion_mask,
    compute_voltage_dff,
    compute_voltage_f0,
)
from .exceptions import Slap2VoltageError

try:
    from slap2 import MultiDataFiles as MultiDataFiles  # type: ignore[import-not-found]
except ImportError:
    MultiDataFiles = None  # type: ignore[assignment,misc]


FORMAT_VERSION = "0.2.3"
ReaderFactory = Callable[[str | Path], object]


def _error(code: str, message: str) -> Slap2VoltageError:
    return Slap2VoltageError(code, message)


def _get(value: object, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _close(value: object | None) -> None:
    if value is not None:
        closer = getattr(value, "close", None)
        if callable(closer):
            closer()


def _reader_factory(factory: ReaderFactory | None) -> ReaderFactory:
    selected = factory or MultiDataFiles
    if selected is None:
        raise _error(
            "Voltage:MissingSLAP2Reader",
            "Cannot resolve slap2.MultiDataFiles. Install the full SLAP2 binary reader package.",
        )
    return selected


def resolve_trial_table_path(input_path: str | Path) -> Path:
    path = Path(input_path)
    if path.is_dir():
        path = path / "trial_table.h5"
    if not path.is_file():
        raise _error("Voltage:TrialTableNotFound", f"Could not find trial table: {path}")
    return path


def validate_trial_table(trial_table: Mapping[str, Any]) -> None:
    for name in ("filename", "slap2_info"):
        if name not in trial_table:
            raise _error("Voltage:InvalidTrialTable", f"trial_table.h5 is missing /{name}.")
    info = trial_table["slap2_info"]
    if not isinstance(info, Mapping) or "first_line" not in info or "last_line" not in info:
        raise _error(
            "Voltage:InvalidTrialTable",
            "trial_table.h5 must contain slap2_info/first_line and last_line.",
        )


def normalize_filename_grid(value: object) -> np.ndarray:
    array = np.asarray(value, dtype=object)
    if array.ndim == 0:
        array = array.reshape(1, 1)
    elif array.ndim == 1:
        array = array.reshape(1, -1)
    elif array.ndim != 2:
        raise _error("Voltage:InvalidFilenameGrid", "trial_table.filename must be a two-dimensional grid.")
    result = np.empty(array.shape, dtype=object)
    for index, item in np.ndenumerate(array):
        if item is None or (isinstance(item, np.ndarray) and item.size == 0):
            result[index] = ""
        elif isinstance(item, bytes):
            result[index] = item.decode("utf-8")
        else:
            result[index] = str(item)
    return result


def normalize_line_ranges(
    trial_table: Mapping[str, Any],
    filenames: np.ndarray,
    first_line_raw: object,
    last_line_raw: object,
) -> tuple[np.ndarray, np.ndarray]:
    """Normalize serialized one-based bounds to one-based inclusive integers."""

    first_line = np.rint(np.asarray(first_line_raw, dtype=np.float64)).astype(np.int64)
    last_line = np.rint(np.asarray(last_line_raw, dtype=np.float64)).astype(np.int64)
    if first_line.ndim == 1:
        first_line = first_line.reshape(1, -1)
    if last_line.ndim == 1:
        last_line = last_line.reshape(1, -1)
    info = trial_table.get("slap2_info", {})
    convention = str(info.get("line_range_convention", "")).strip().lower() if isinstance(info, Mapping) else ""
    if convention != "inclusive":
        for index, filename in np.ndenumerate(filenames):
            if filename and "-cycle-" in str(filename).lower():
                last_line[index] -= 1
    return first_line, last_line


def acquisition_prefix(filename: str) -> str:
    name = Path(filename).stem
    prefix = re.sub(r"_DMD\d+.*$", "", name, flags=re.IGNORECASE)
    prefix = re.sub(r"-DMD\d+.*$", "", prefix, flags=re.IGNORECASE)
    return prefix or name


def relabel_stable(values: object) -> np.ndarray:
    vals = np.asarray(values, dtype=np.float64).reshape(-1)
    result = np.ones(vals.size, dtype=np.int32)
    seen: list[float] = []
    for index, value in enumerate(vals):
        if not np.isfinite(value):
            result[index] = max(1, len(seen))
            continue
        if value not in seen:
            seen.append(float(value))
        result[index] = seen.index(float(value)) + 1
    return result


def infer_analysis_epochs(trial_table: Mapping[str, Any], filenames: np.ndarray) -> np.ndarray:
    n_paths, n_trials = filenames.shape
    result = np.ones((n_paths, n_trials), dtype=np.int32)
    explicit = np.asarray(trial_table.get("epoch", []), dtype=np.float64)
    if explicit.ndim == 1 and n_paths == 1:
        explicit = explicit.reshape(1, -1)
    for path_index in range(n_paths):
        use_explicit = explicit.shape == filenames.shape
        if use_explicit:
            finite = explicit[path_index, np.isfinite(explicit[path_index])]
            use_explicit = np.unique(finite).size > 1
        if use_explicit:
            result[path_index] = relabel_stable(explicit[path_index])
            continue
        current = 1
        previous = ""
        for trial_index in range(n_trials):
            filename = str(filenames[path_index, trial_index])
            if filename:
                prefix = acquisition_prefix(filename)
                if not previous:
                    previous = prefix
                elif prefix != previous:
                    current += 1
                    previous = prefix
            result[path_index, trial_index] = current
    return result


def resolve_data_dir(trial_table: Mapping[str, Any], trial_table_dir: Path) -> Path:
    data_dir = trial_table.get("datadr", "")
    if isinstance(data_dir, np.ndarray) and data_dir.size == 1:
        data_dir = data_dir.item()
    if data_dir:
        return Path(str(data_dir))
    dynamic = trial_table_dir / "dynamic_data"
    return dynamic if dynamic.is_dir() else trial_table_dir


def resolve_data_file_path(data_dir: Path, trial_table_dir: Path, filename: str) -> Path:
    candidates = (
        Path(filename),
        data_dir / filename,
        trial_table_dir / filename,
        trial_table_dir / "dynamic_data" / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise _error("Voltage:MissingDataFile", f"Could not find raw SLAP2 file: {filename}")


def build_acquisition_roi_mask(roi: object, n_rows: int, n_cols: int, source_roi_idx: int) -> np.ndarray:
    stored = _get(roi, "mask", default=None)
    if stored is not None and np.asarray(stored).size:
        mask = np.asarray(stored, dtype=bool).squeeze()
        # MATLAB lineage: accept acquisition masks whose spatial axes arrive transposed.
        if mask.shape == (n_cols, n_rows) and mask.shape != (n_rows, n_cols):
            mask = mask.T
        if mask.shape != (n_rows, n_cols):
            raise _error(
                "Voltage:UnexpectedMaskSize",
                f"Acquisition ROI {source_roi_idx + 1} mask size is {mask.shape}; expected {(n_rows, n_cols)}.",
            )
    else:
        shape = np.asarray(_get(roi, "shape_data", "shapeData", default=[]), dtype=np.float64)
        if shape.ndim != 2 or shape.shape[1] < 2 or shape.size == 0:
            raise _error(
                "Voltage:MissingRoiMask",
                f"Acquisition ROI {source_roi_idx + 1} has no usable mask/shapeData.",
            )
        coordinates = np.rint(shape[:, :2]).astype(np.int64) - 1
        valid = (
            (coordinates[:, 0] >= 0)
            & (coordinates[:, 0] < n_rows)
            & (coordinates[:, 1] >= 0)
            & (coordinates[:, 1] < n_cols)
        )
        if not np.all(valid):
            warnings.warn(
                f"Voltage:RoiShapeOutOfBounds: Acquisition ROI {source_roi_idx + 1} has "
                f"{np.count_nonzero(~valid)} out-of-bounds shapeData pixels; ignoring them.",
                RuntimeWarning,
                stacklevel=2,
            )
        mask = np.zeros((n_rows, n_cols), dtype=bool)
        coordinates = coordinates[valid]
        if coordinates.size:
            mask[coordinates[:, 0], coordinates[:, 1]] = True
    if not np.any(mask):
        warnings.warn(
            f"Voltage:EmptyAcquisitionROI: Acquisition ROI {source_roi_idx + 1} produced an empty mask.",
            RuntimeWarning,
            stacklevel=2,
        )
    return mask


def safe_roi_mode_string(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return f"<{type(value).__name__}>"


def discover_voltage_rois(
    multi_data_files: object, z_idx: int, ch_idx: int
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    metadata = _get(multi_data_files, "metadata", "meta_data", "metaData")
    acquisition = _get(metadata, "AcquisitionContainer")
    roi_container = _get(acquisition, "ROIs")
    rois = _get(roi_container, "rois")
    if rois is None:
        raise _error(
            "Voltage:MissingAcquisitionROIs",
            "SLAP2 metadata are missing AcquisitionContainer.ROIs.rois.",
        )
    if isinstance(rois, np.ndarray):
        roi_items = list(rois.reshape(-1))
    elif isinstance(rois, Sequence) and not isinstance(rois, (str, bytes)):
        roi_items = list(rois)
    else:
        roi_items = [rois]
    n_rows = int(_get(metadata, "dmd_pixels_per_column", "dmdPixelsPerColumn"))
    n_cols = int(_get(metadata, "dmd_pixels_per_row", "dmdPixelsPerRow"))
    masks: list[np.ndarray] = []
    source_indices: list[int] = []
    counts: list[int] = []
    modes: list[str] = []
    for source_index, roi in enumerate(roi_items):
        mask = build_acquisition_roi_mask(roi, n_rows, n_cols, source_index)
        modes.append(safe_roi_mode_string(_get(roi, "imaging_mode", "imagingMode", default="")))
        trace = Trace(multi_data_files, z_idx, ch_idx)
        trace.set_pixel_idxs((), mask)
        count = len(trace.trace_pixels)
        counts.append(count)
        if count:
            source_indices.append(source_index)
            masks.append(mask)
    mask_stack = (
        np.stack(masks, axis=2)
        if masks
        else np.zeros((n_rows, n_cols, 0), dtype=bool)
    )
    indices = np.asarray(source_indices, dtype=np.int32)
    discovery = {
        "method": "parse_plan_integration_membership",
        "n_acquisition_rois": len(roi_items),
        "n_voltage_rois": len(source_indices),
        "source_roi_idx": indices,
        "integration_super_pixel_counts": np.asarray(counts, dtype=np.int64),
        "imaging_mode": modes,
    }
    return mask_stack, indices, discovery


def resolve_sample_rate_hz(multi_data_files: object) -> float:
    metadata = _get(multi_data_files, "metadata", "meta_data", "metaData")
    period = _get(metadata, "line_period_s", "linePeriod_s")
    if period is not None and np.asarray(period).size:
        rate = 1.0 / float(np.asarray(period).reshape(-1)[0])
    else:
        parse_plan = _get(_get(metadata, "AcquisitionContainer"), "ParsePlan")
        rate_value = _get(parse_plan, "line_rate_hz", "lineRateHz")
        if rate_value is None:
            raise _error("Voltage:MissingSampleRate", "Could not resolve SLAP2 line/sample rate.")
        rate = float(rate_value)
    if not np.isfinite(rate) or rate <= 0:
        raise _error("Voltage:MissingSampleRate", "SLAP2 line/sample rate must be finite and positive.")
    return rate


def resolve_z_depth(multi_data_files: object) -> float:
    values = _get(multi_data_files, "fast_zs", "fastZs")
    if values is None or not np.asarray(values).size:
        metadata = _get(multi_data_files, "metadata", "meta_data", "metaData")
        parse_plan = _get(_get(metadata, "AcquisitionContainer"), "ParsePlan")
        values = _get(parse_plan, "zs", default=[])
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    return float(array[0]) if array.size else float("nan")


def get_geometry_meta(multi_data_files: object) -> dict[str, Any]:
    metadata = _get(multi_data_files, "metadata", "meta_data", "metaData")
    header = _get(multi_data_files, "header")
    return {
        "dmd_pixels_per_row": _get(metadata, "dmd_pixels_per_row", "dmdPixelsPerRow"),
        "dmd_pixels_per_column": _get(metadata, "dmd_pixels_per_column", "dmdPixelsPerColumn"),
        "samples_per_line": _get(metadata, "samples_per_line", "samplesPerLine"),
        "channels_save": _get(metadata, "channels_save", "channelsSave"),
        "lines_per_cycle": _get(header, "lines_per_cycle", "linesPerCycle"),
    }


def validate_parse_plan_compatibility(multi_data_files: object, path_idx: int) -> None:
    for snake, camel in (
        ("line_super_pixel_ids", "lineSuperPixelIDs"),
        ("line_fast_z_idxs", "lineFastZIdxs"),
        ("z_pixel_replacement_maps", "zPixelReplacementMaps"),
    ):
        if _get(multi_data_files, snake, camel) is None:
            raise _error(
                "Voltage:ParsePlanMissingField",
                f"Path{path_idx + 1} MultiDataFiles is missing {snake}.",
            )
    if not len(_get(multi_data_files, "z_pixel_replacement_maps", "zPixelReplacementMaps")) or not len(
        _get(multi_data_files, "line_super_pixel_ids", "lineSuperPixelIDs")
    ):
        raise _error("Voltage:EmptyParsePlan", f"Path{path_idx + 1} has an empty SLAP2 parse plan.")


def validate_source_compatibility(
    path_idx: int,
    source_name: str,
    canonical_meta: Mapping[str, Any],
    source_meta: Mapping[str, Any],
    canonical_masks: np.ndarray,
    source_masks: np.ndarray,
    canonical_source_roi_idx: np.ndarray,
    source_roi_idx: np.ndarray,
    canonical_rate: float,
    source_rate: float,
) -> None:
    for name, value in canonical_meta.items():
        if not np.array_equal(np.asarray(value), np.asarray(source_meta.get(name))):
            raise _error(
                "Voltage:IncompatibleSource",
                f"Path{path_idx + 1} source {source_name} changed {name}.",
            )
    if not np.array_equal(canonical_masks, source_masks):
        raise _error(
            "Voltage:IncompatibleSourceROIs",
            f"Path{path_idx + 1} source {source_name} has different integration ROI masks.",
        )
    if not np.array_equal(canonical_source_roi_idx, source_roi_idx):
        raise _error(
            "Voltage:IncompatibleSourceROIs",
            f"Path{path_idx + 1} source {source_name} changed integration ROI order/identity.",
        )
    if abs(canonical_rate - source_rate) > max(1e-9, 1e-9 * abs(canonical_rate)):
        raise _error(
            "Voltage:IncompatibleSampleRate",
            f"Path{path_idx + 1} source {source_name} changed sample rate.",
        )


def compute_trial_offsets(lengths: object) -> tuple[np.ndarray, int]:
    values = np.asarray(lengths, dtype=np.int64).reshape(-1)
    offsets = np.zeros(values.size, dtype=np.int64)
    running = 0
    for index, length in enumerate(values):
        if length > 0:
            offsets[index] = running
            running += int(length)
    return offsets, running


def _create_dataset(handle: h5py.File, path: str, value: object, dtype: object) -> h5py.Dataset:
    parent, name = path.rsplit("/", 1)
    group = handle.require_group(parent)
    array = np.asarray(value, dtype=dtype)
    if array.ndim == 0:
        array = array.reshape(1, 1)
    return group.create_dataset(name, data=array, dtype=dtype)


def initialize_path_output(
    filename: Path,
    path_name: str,
    masks: np.ndarray,
    source_roi_idx: np.ndarray,
    sample_rate_hz: float,
    z_depth: float,
    trial_lengths: np.ndarray,
    trial_epoch: np.ndarray,
    first_line: np.ndarray,
    last_line: np.ndarray,
    trial_offsets: np.ndarray,
    params: Mapping[str, object],
) -> None:
    _, total_samples = compute_trial_offsets(trial_lengths)
    chunk_samples = min(total_samples, int(params["h5_chunk_samples"])) if total_samples else 1
    with h5py.File(filename, "a") as handle:
        _create_dataset(handle, f"{path_name}/Z_depths", [z_depth], np.float64)
        _create_dataset(handle, f"{path_name}/sample_rate_hz", sample_rate_hz, np.float64)
        _create_dataset(handle, f"{path_name}/frame_info/trial_num_frames", trial_lengths.reshape(-1, 1), np.int32)
        _create_dataset(handle, f"{path_name}/frame_info/trial_epoch", trial_epoch.reshape(-1, 1), np.int32)
        if total_samples:
            frame = handle.require_group(f"{path_name}/frame_info")
            line_dataset = frame.create_dataset(
                "frame_line_idxs", (total_samples, 1), dtype=np.int32, chunks=(chunk_samples, 1)
            )
            epoch_dataset = frame.create_dataset(
                "sample_epoch", (total_samples, 1), dtype=np.int32, chunks=(chunk_samples, 1)
            )
            if bool(params["motion_censor_enable"]):
                frame.create_dataset(
                    "motion_censor",
                    (total_samples, 1),
                    dtype=np.uint8,
                    chunks=(chunk_samples, 1),
                    fillvalue=0,
                )
            for trial_index, length in enumerate(trial_lengths):
                n = int(length)
                if n <= 0:
                    continue
                lines = np.arange(int(first_line[trial_index]), int(last_line[trial_index]) + 1, dtype=np.int32)
                if lines.size != n:
                    raise _error(
                        "Voltage:InternalTrialLengthMismatch",
                        f"Trial {trial_index + 1} line vector length mismatch.",
                    )
                offset = int(trial_offsets[trial_index])
                line_dataset[offset : offset + n, 0] = lines
                epoch_dataset[offset : offset + n, 0] = int(trial_epoch[trial_index])
        n_rois = masks.shape[2]
        if not n_rois or not total_samples:
            return
        n_rows, n_cols = masks.shape[:2]
        profiles = np.moveaxis(masks, 2, 0).astype(np.float32)[:, None, :, :]
        coords = np.zeros((n_rois, 3), dtype=np.float64)
        pixel_count = np.zeros((n_rois, 1), dtype=np.int32)
        row_grid, column_grid = np.indices((n_rows, n_cols))
        for roi_index in range(n_rois):
            mask = masks[:, :, roi_index]
            pixel_count[roi_index, 0] = np.count_nonzero(mask)
            if np.any(mask):
                coords[roi_index, 1] = np.mean(row_grid[mask])
                coords[roi_index, 2] = np.mean(column_grid[mask])
        _create_dataset(handle, f"{path_name}/sources/spatial/profiles", profiles, np.float32)
        _create_dataset(handle, f"{path_name}/sources/spatial/coords", coords, np.float64)
        # MATLAB lineage: serialized source ROI identifiers remain one-based for existing consumers.
        _create_dataset(
            handle,
            f"{path_name}/sources/spatial/source_roi_index",
            (source_roi_idx + 1).reshape(-1, 1),
            np.int32,
        )
        _create_dataset(handle, f"{path_name}/sources/spatial/roi_pixel_count", pixel_count, np.int32)
        temporal = handle.require_group(f"{path_name}/sources/temporal")
        dtype = np.float64 if params["precision"] == "double" else np.float32
        compression = "gzip" if int(params["h5_deflate"]) > 0 else None
        compression_opts = int(params["h5_deflate"]) if compression else None
        for name in ("raw_f", "f0", "dff"):
            temporal.create_dataset(
                name,
                (n_rois, 1, total_samples),
                dtype=dtype,
                chunks=(1, 1, chunk_samples),
                fillvalue=np.nan,
                compression=compression,
                compression_opts=compression_opts,
            )
        dff = temporal["dff"]
        dff.attrs["sign_convention"] = "Positive dff corresponds to positive membrane-voltage deflection."
        dff.attrs["indicator_direction"] = str(params["indicator_direction"])
        dff.attrs["indicator_name"] = str(params["indicator_name"])


def _extract_one_roi(
    multi_data_files: object, mask: np.ndarray, params: Mapping[str, object]
) -> np.ndarray:
    trace = Trace(multi_data_files, int(params["z_idx"]), int(params["ch_idx"]))
    trace.set_pixel_idxs(mask, mask)
    result = trace.process(int(params["trace_window_lines"]), int(params["trace_expected_window_lines"]))
    return np.asarray(result[0] if isinstance(result, tuple) else result)


def extract_roi_batch(
    multi_data_files: object,
    masks: np.ndarray,
    batch: Sequence[int],
    params: Mapping[str, object],
) -> tuple[list[np.ndarray | None], list[str | None]]:
    traces: list[np.ndarray | None] = [None] * len(batch)
    errors: list[str | None] = [None] * len(batch)
    if bool(params["use_parallel"]) and len(batch) > 1:
        with ThreadPoolExecutor(max_workers=min(len(batch), int(params["n_workers"]))) as executor:
            futures = {
                executor.submit(_extract_one_roi, multi_data_files, masks[:, :, roi_index], params): slot
                for slot, roi_index in enumerate(batch)
            }
            for future in as_completed(futures):
                slot = futures[future]
                try:
                    traces[slot] = future.result()
                except Exception as exc:  # retain all asynchronous ROI failures
                    errors[slot] = repr(exc)
    else:
        for slot, roi_index in enumerate(batch):
            try:
                traces[slot] = _extract_one_roi(multi_data_files, masks[:, :, roi_index], params)
            except Exception as exc:
                errors[slot] = repr(exc)
    return traces, errors


def cast_trace(trace: object, precision: str) -> np.ndarray:
    dtype = np.float64 if precision.lower() == "double" else np.float32
    return np.asarray(trace, dtype=dtype).reshape(-1)


def trials_are_contiguous_in_source_and_output(
    trials: np.ndarray,
    first_line: np.ndarray,
    last_line: np.ndarray,
    trial_offsets: np.ndarray,
    trial_lengths: np.ndarray,
) -> bool:
    for previous, current in zip(trials[:-1], trials[1:], strict=True):
        if int(first_line[current]) != int(last_line[previous]) + 1:
            return False
        if int(trial_offsets[current]) != int(trial_offsets[previous]) + int(trial_lengths[previous]):
            return False
    return True


def _valid_trials(trials: object, trial_lengths: np.ndarray) -> np.ndarray:
    result = np.sort(np.asarray(trials, dtype=np.int64).reshape(-1))
    return result[trial_lengths[result] > 0]


def write_raw_source_slices(
    filename: Path,
    path_name: str,
    trace: np.ndarray,
    roi_idx: int,
    trial_indices: object,
    first_line: np.ndarray,
    last_line: np.ndarray,
    trial_offsets: np.ndarray,
    trial_lengths: np.ndarray,
) -> int:
    trials = _valid_trials(trial_indices, trial_lengths)
    if not trials.size:
        return 0
    with h5py.File(filename, "a") as handle:
        dataset = handle[f"{path_name}/sources/temporal/raw_f"]
        if trials_are_contiguous_in_source_and_output(
            trials, first_line, last_line, trial_offsets, trial_lengths
        ):
            n = int(np.sum(trial_lengths[trials]))
            start = int(first_line[trials[0]]) - 1
            stop = int(last_line[trials[-1]])
            if start < 0 or stop > trace.size or stop < start:
                raise _error(
                    "Voltage:TraceTooShort",
                    f"ROI{roi_idx + 1} contiguous source range is outside trace length {trace.size}.",
                )
            segment = trace[start:stop]
            if segment.size != n:
                raise _error("Voltage:TraceLengthMismatch", "Contiguous source block length mismatch.")
            output_start = int(trial_offsets[trials[0]])
            dataset[roi_idx, 0, output_start : output_start + n] = segment
            return 1
        writes = 0
        for trial_index in trials:
            n = int(trial_lengths[trial_index])
            start = int(first_line[trial_index]) - 1
            stop = int(last_line[trial_index])
            if start < 0 or stop > trace.size or stop < start:
                raise _error(
                    "Voltage:TraceTooShort",
                    f"ROI{roi_idx + 1} trial{trial_index + 1} range is outside trace length {trace.size}.",
                )
            segment = trace[start:stop]
            if segment.size != n:
                raise _error("Voltage:TraceLengthMismatch", "Trial source block length mismatch.")
            output_start = int(trial_offsets[trial_index])
            dataset[roi_idx, 0, output_start : output_start + n] = segment
            writes += 1
    return writes


def write_motion_mask_slices(
    filename: Path,
    path_name: str,
    line_mask: np.ndarray,
    trial_indices: object,
    first_line: np.ndarray,
    last_line: np.ndarray,
    trial_offsets: np.ndarray,
    trial_lengths: np.ndarray,
) -> None:
    trials = _valid_trials(trial_indices, trial_lengths)
    if not trials.size:
        return
    with h5py.File(filename, "a") as handle:
        dataset = handle[f"{path_name}/frame_info/motion_censor"]
        if trials_are_contiguous_in_source_and_output(
            trials, first_line, last_line, trial_offsets, trial_lengths
        ):
            n = int(np.sum(trial_lengths[trials]))
            start = int(first_line[trials[0]]) - 1
            stop = int(last_line[trials[-1]])
            segment = line_mask[start:stop]
            if start < 0 or stop > line_mask.size or segment.size != n:
                raise _error("Voltage:MotionMaskLengthMismatch", "Contiguous motion-mask length mismatch.")
            output_start = int(trial_offsets[trials[0]])
            dataset[output_start : output_start + n, 0] = segment.astype(np.uint8)
            return
        for trial_index in trials:
            n = int(trial_lengths[trial_index])
            start = int(first_line[trial_index]) - 1
            stop = int(last_line[trial_index])
            segment = line_mask[start:stop]
            if start < 0 or stop > line_mask.size or segment.size != n:
                raise _error(
                    "Voltage:MotionMaskLengthMismatch",
                    f"Trial{trial_index + 1} motion-mask length mismatch.",
                )
            output_start = int(trial_offsets[trial_index])
            dataset[output_start : output_start + n, 0] = segment.astype(np.uint8)


def complete_epochs_for_source(
    source_trials: object, valid_trials: np.ndarray, trial_epoch: np.ndarray
) -> np.ndarray:
    source = np.asarray(source_trials, dtype=np.int64).reshape(-1)
    result: list[int] = []
    for epoch_id in dict.fromkeys(trial_epoch[source].tolist()):
        source_in_epoch = np.sort(source[trial_epoch[source] == epoch_id])
        all_in_epoch = np.sort(valid_trials[trial_epoch[valid_trials] == epoch_id])
        if np.array_equal(source_in_epoch, all_in_epoch):
            result.append(int(epoch_id))
    return np.asarray(result, dtype=np.int32)


def append_unique_stable(values: list[int], additions: object) -> list[int]:
    for value in np.asarray(additions).reshape(-1):
        integer = int(value)
        if integer not in values:
            values.append(integer)
    return values


def concatenate_trace_trials(
    trace: np.ndarray,
    trials: object,
    first_line: np.ndarray,
    last_line: np.ndarray,
    trial_lengths: np.ndarray,
) -> np.ndarray:
    selected = _valid_trials(trials, trial_lengths)
    if not selected.size:
        return np.empty(0, dtype=trace.dtype)
    source_contiguous = all(
        int(first_line[current]) == int(last_line[previous]) + 1
        for previous, current in zip(selected[:-1], selected[1:], strict=True)
    )
    if source_contiguous:
        start = int(first_line[selected[0]]) - 1
        stop = int(last_line[selected[-1]])
        if start < 0 or stop > trace.size or stop < start:
            raise _error("Voltage:TraceTooShort", "Epoch source range is outside extracted trace.")
        result = trace[start:stop]
        if result.size != int(np.sum(trial_lengths[selected])):
            raise _error("Voltage:TraceLengthMismatch", "Epoch contiguous source length mismatch.")
        return result.reshape(-1)
    pieces: list[np.ndarray] = []
    for trial_index in selected:
        start = int(first_line[trial_index]) - 1
        stop = int(last_line[trial_index])
        segment = trace[start:stop]
        if start < 0 or stop > trace.size or segment.size != int(trial_lengths[trial_index]):
            raise _error("Voltage:TraceLengthMismatch", "Trial source length mismatch.")
        pieces.append(segment)
    return np.concatenate(pieces)


def write_derived_epoch(
    filename: Path,
    path_name: str,
    roi_idx: int,
    trials: object,
    trial_offsets: np.ndarray,
    trial_lengths: np.ndarray,
    f0: np.ndarray,
    dff: np.ndarray,
) -> None:
    selected = _valid_trials(trials, trial_lengths)
    if not selected.size:
        return
    n_epoch = int(np.sum(trial_lengths[selected]))
    if f0.size != n_epoch or dff.size != n_epoch:
        raise _error("Voltage:DerivedLengthMismatch", "Derived epoch length mismatch.")
    for previous, current in zip(selected[:-1], selected[1:], strict=True):
        if trial_offsets[current] != trial_offsets[previous] + trial_lengths[previous]:
            raise _error("Voltage:DisjointEpoch", "Epoch trials are not contiguous on the output axis.")
    start = int(trial_offsets[selected[0]])
    with h5py.File(filename, "a") as handle:
        handle[f"{path_name}/sources/temporal/f0"][roi_idx, 0, start : start + n_epoch] = f0
        handle[f"{path_name}/sources/temporal/dff"][roi_idx, 0, start : start + n_epoch] = dff


def transform_path_epochs(
    filename: Path,
    path_name: str,
    n_rois: int,
    trial_epoch: np.ndarray,
    trial_offsets: np.ndarray,
    trial_lengths: np.ndarray,
    sample_rate_hz: float,
    params: Mapping[str, object],
    epoch_ids: object,
) -> dict[str, float]:
    timing = {"read_s": 0.0, "compute_s": 0.0, "write_s": 0.0}
    valid_trials = np.flatnonzero(trial_lengths > 0)
    for roi_idx in range(n_rois):
        for epoch_id in np.asarray(epoch_ids).reshape(-1):
            trials = valid_trials[trial_epoch[valid_trials] == epoch_id]
            if not trials.size:
                continue
            expected = np.arange(trials[0], trials[-1] + 1)
            expected = expected[trial_lengths[expected] > 0]
            if not np.array_equal(trials, expected):
                raise _error("Voltage:DisjointEpoch", f"Path epoch {epoch_id} occurs in disjoint blocks.")
            start = int(trial_offsets[trials[0]])
            n_epoch = int(np.sum(trial_lengths[trials]))
            started = time.perf_counter()
            with h5py.File(filename, "r") as handle:
                raw = np.asarray(
                    handle[f"{path_name}/sources/temporal/raw_f"][roi_idx, 0, start : start + n_epoch]
                ).reshape(-1)
                censor = (
                    np.asarray(
                        handle[f"{path_name}/frame_info/motion_censor"][start : start + n_epoch, 0],
                        dtype=bool,
                    )
                    if bool(params["motion_censor_enable"])
                    else np.zeros(n_epoch, dtype=bool)
                )
            timing["read_s"] += time.perf_counter() - started
            started = time.perf_counter()
            raw_for_derived = raw.copy()
            raw_for_derived[censor] = np.nan
            f0, _ = compute_voltage_f0(raw_for_derived, sample_rate_hz, params)
            dff, _ = compute_voltage_dff(
                raw_for_derived,
                f0,
                params["indicator_name"],
                params["indicator_direction"],
                params["precision"],
            )
            f0[censor] = np.nan
            dff[censor] = np.nan
            timing["compute_s"] += time.perf_counter() - started
            started = time.perf_counter()
            write_derived_epoch(filename, path_name, roi_idx, trials, trial_offsets, trial_lengths, f0, dff)
            timing["write_s"] += time.perf_counter() - started
    return timing


def empty_timing() -> dict[str, float]:
    return {
        "metadata_s": 0.0,
        "source_open_s": 0.0,
        "output_init_s": 0.0,
        "raw_trace_s": 0.0,
        "raw_write_s": 0.0,
        "raw_h5_writes": 0.0,
        "fallback_read_s": 0.0,
        "derived_compute_s": 0.0,
        "derived_write_s": 0.0,
        "total_s": 0.0,
    }


def make_batches(items: object, batch_size: int) -> list[np.ndarray]:
    values = np.asarray(items, dtype=np.int64).reshape(-1)
    size = max(1, int(round(batch_size)))
    return [values[start : start + size] for start in range(0, values.size, size)]


def configure_parallel_pool(params: Mapping[str, object]) -> dict[str, object]:
    """Return parameters configured for Python's per-batch thread executor."""

    result = dict(params)
    if bool(result["use_parallel"]) and int(result["n_workers"]) < 1:
        warnings.warn(
            "Voltage:ParallelPoolFailed: invalid worker count; using synchronous extraction.",
            RuntimeWarning,
            stacklevel=2,
        )
        result["use_parallel"] = False
    return result


def cleanup_partial_output(output_path: Path, original_error: BaseException) -> None:
    if not output_path.is_file():
        return
    try:
        output_path.unlink()
    except OSError as cleanup_error:
        warnings.warn(
            f"Voltage:PartialOutputCleanupFailed: extraction failed with {original_error!r}, and "
            f"the incomplete output could not be removed: {cleanup_error}.",
            RuntimeWarning,
            stacklevel=2,
        )


def voltage(
    dr_or_path_to_trial_table: str | Path,
    params_in: object | None = None,
    *,
    reader_factory: ReaderFactory | None = None,
) -> dict[str, Any]:
    """Extract SLAP2 integration-ROI voltage fluorescence to ``VoltageSummary.h5``."""

    run_started = time.perf_counter()
    trial_table_path = resolve_trial_table_path(dr_or_path_to_trial_table)
    params = set_params("Voltage", params_in)
    trial_table = load_struct_from_h5(trial_table_path)
    validate_trial_table(trial_table)
    trial_table_dir = trial_table_path.parent
    data_dir = resolve_data_dir(trial_table, trial_table_dir)
    output_dir = Path(str(params["output_dir"])) if params["output_dir"] else trial_table_dir / "Voltage"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / str(params["output_filename"])
    if output_path.exists():
        if bool(params["overwrite"]):
            output_path.unlink()
        else:
            raise _error(
                "Voltage:OutputExists",
                f"Output already exists: {output_path}. Set overwrite=true to replace it.",
            )

    filenames = normalize_filename_grid(trial_table["filename"])
    info = trial_table["slap2_info"]
    assert isinstance(info, Mapping)
    first_line, last_line = normalize_line_ranges(
        trial_table, filenames, info["first_line"], info["last_line"]
    )
    if first_line.shape != filenames.shape or last_line.shape != filenames.shape:
        raise _error(
            "Voltage:TrialTableShapeMismatch",
            "filename, slap2_info.first_line, and slap2_info.last_line must have identical size.",
        )
    analysis_epoch = infer_analysis_epochs(trial_table, filenames)
    n_paths, n_trials = filenames.shape
    trial_num_samples = np.zeros((n_paths, n_trials), dtype=np.int64)
    valid_bounds = (first_line >= 1) & (last_line >= first_line)
    trial_num_samples[valid_bounds & (filenames != "")] = (
        last_line[valid_bounds & (filenames != "")] - first_line[valid_bounds & (filenames != "")] + 1
    )

    try:
        save_struct_to_h5({"format_version": FORMAT_VERSION, "params": params}, output_path)
        summary: dict[str, Any] = {
            "trial_table_path": str(trial_table_path),
            "output_path": str(output_path),
            "params": params,
            "n_paths": n_paths,
            "n_trials": n_trials,
            "path": [{} for _ in range(n_paths)],
            "timing": {"path": [empty_timing() for _ in range(n_paths)]},
        }
        factory = _reader_factory(reader_factory)
        parallel_configured = False
        total_voltage_rois = 0
        for path_idx in range(n_paths):
            path_started = time.perf_counter()
            timing = empty_timing()
            valid_trials = np.flatnonzero((filenames[path_idx] != "") & (trial_num_samples[path_idx] > 0))
            if not valid_trials.size:
                warnings.warn(
                    f"Voltage:NoValidTrials: Path{path_idx + 1} has no valid trials; skipping.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                timing["total_s"] = time.perf_counter() - path_started
                summary["timing"]["path"][path_idx] = timing
                continue
            source_names = filenames[path_idx, valid_trials].tolist()
            unique_sources = list(dict.fromkeys(source_names))
            source_groups = np.asarray([unique_sources.index(name) for name in source_names])
            first_source = resolve_data_file_path(data_dir, trial_table_dir, unique_sources[0])
            metadata_started = time.perf_counter()
            first_mdf = factory(first_source)
            validate_parse_plan_compatibility(first_mdf, path_idx)
            masks, source_roi_idx, discovery = discover_voltage_rois(
                first_mdf, int(params["z_idx"]), int(params["ch_idx"])
            )
            sample_rate_hz = resolve_sample_rate_hz(first_mdf)
            z_depth = resolve_z_depth(first_mdf)
            canonical_meta = get_geometry_meta(first_mdf)
            timing["metadata_s"] += time.perf_counter() - metadata_started
            n_rois = masks.shape[2]
            total_voltage_rois += n_rois
            trial_offsets, total_samples = compute_trial_offsets(trial_num_samples[path_idx])
            path_name = f"/Path{path_idx + 1}"
            path_summary: dict[str, Any] = {
                "n_acquisition_rois": discovery["n_acquisition_rois"],
                "n_rois": n_rois,
                "source_roi_idx": source_roi_idx,
                "roi_discovery": discovery,
                "sample_rate_hz": sample_rate_hz,
                "total_samples": total_samples,
                "trial_num_samples": trial_num_samples[path_idx].copy(),
                "trial_epoch": analysis_epoch[path_idx].copy(),
            }
            summary["path"][path_idx] = path_summary
            if not n_rois:
                _close(first_mdf)
                timing["total_s"] = time.perf_counter() - path_started
                summary["timing"]["path"][path_idx] = timing
                path_summary["timing"] = timing
                continue
            started = time.perf_counter()
            initialize_path_output(
                output_path,
                path_name,
                masks,
                source_roi_idx,
                sample_rate_hz,
                z_depth,
                trial_num_samples[path_idx],
                analysis_epoch[path_idx],
                first_line[path_idx],
                last_line[path_idx],
                trial_offsets,
                params,
            )
            timing["output_init_s"] += time.perf_counter() - started
            if not parallel_configured:
                params = configure_parallel_pool(params)
                summary["params"] = params
                parallel_configured = True
            all_epoch_ids = list(dict.fromkeys(analysis_epoch[path_idx, valid_trials].tolist()))
            in_memory_epoch_ids: list[int] = []
            for source_idx in range(len(unique_sources)):
                source_trials = valid_trials[source_groups == source_idx]
                append_unique_stable(
                    in_memory_epoch_ids,
                    complete_epochs_for_source(
                        source_trials, valid_trials, analysis_epoch[path_idx]
                    ),
                )
            fallback_epoch_ids = [value for value in all_epoch_ids if value not in in_memory_epoch_ids]
            path_summary["in_memory_epoch_ids"] = np.asarray(in_memory_epoch_ids, dtype=np.int32)
            path_summary["fallback_epoch_ids"] = np.asarray(fallback_epoch_ids, dtype=np.int32)
            path_summary["motion"] = []
            for source_idx, source_name in enumerate(unique_sources):
                source_trials = valid_trials[source_groups == source_idx]
                if source_idx == 0:
                    mdf = first_mdf
                    first_mdf = None
                    source_masks = masks
                    source_indices = source_roi_idx
                else:
                    started = time.perf_counter()
                    source_path = resolve_data_file_path(data_dir, trial_table_dir, source_name)
                    mdf = factory(source_path)
                    timing["source_open_s"] += time.perf_counter() - started
                    validate_parse_plan_compatibility(mdf, path_idx)
                    source_masks, source_indices, _ = discover_voltage_rois(
                        mdf, int(params["z_idx"]), int(params["ch_idx"])
                    )
                try:
                    validate_source_compatibility(
                        path_idx,
                        source_name,
                        canonical_meta,
                        get_geometry_meta(mdf),
                        masks,
                        source_masks,
                        source_roi_idx,
                        source_indices,
                        sample_rate_hz,
                        resolve_sample_rate_hz(mdf),
                    )
                    complete_epoch_ids = complete_epochs_for_source(
                        source_trials, valid_trials, analysis_epoch[path_idx]
                    )
                    epoch_masks: list[np.ndarray] = [
                        np.zeros(0, dtype=bool) for _ in complete_epoch_ids
                    ]
                    if bool(params["motion_censor_enable"]):
                        motion_mask, motion_info = compute_source_motion_mask(mdf, params, sample_rate_hz)
                        write_motion_mask_slices(
                            output_path,
                            path_name,
                            motion_mask,
                            source_trials,
                            first_line[path_idx],
                            last_line[path_idx],
                            trial_offsets,
                            trial_num_samples[path_idx],
                        )
                        for slot, epoch_id in enumerate(complete_epoch_ids):
                            epoch_trials = source_trials[
                                analysis_epoch[path_idx, source_trials] == epoch_id
                            ]
                            epoch_masks[slot] = concatenate_trace_trials(
                                motion_mask.astype(np.float32),
                                epoch_trials,
                                first_line[path_idx],
                                last_line[path_idx],
                                trial_num_samples[path_idx],
                            ) > 0.5
                        path_summary["motion"].append(
                            {
                                "source": source_name,
                                "fraction_censored": motion_info["fraction_censored"],
                                "scale_um": motion_info["scale_um"],
                                "threshold_um": motion_info["threshold_um"],
                                "num_cycles": motion_info["num_cycles"],
                                "lines_per_cycle": motion_info["lines_per_cycle"],
                            }
                        )
                        if float(motion_info["fraction_censored"]) > float(
                            params["motion_max_frac_censored"]
                        ):
                            warnings.warn(
                                f"Voltage:MotionCensorHigh: {100 * float(motion_info['fraction_censored']):.1f}% "
                                f"of {source_name} is motion-censored.",
                                RuntimeWarning,
                                stacklevel=2,
                            )
                    for batch in make_batches(np.arange(n_rois), int(params["max_concurrent_rois"])):
                        started = time.perf_counter()
                        traces, errors = extract_roi_batch(mdf, masks, batch, params)
                        timing["raw_trace_s"] += time.perf_counter() - started
                        for slot, roi_idx_value in enumerate(batch):
                            roi_idx = int(roi_idx_value)
                            if errors[slot] is not None or traces[slot] is None:
                                raise _error(
                                    "Voltage:ROIExtractionFailed",
                                    f"Path{path_idx + 1} ROI{roi_idx + 1} failed for {source_name}: {errors[slot]}",
                                )
                            trace = cast_trace(traces[slot], str(params["precision"]))
                            started = time.perf_counter()
                            timing["raw_h5_writes"] += write_raw_source_slices(
                                output_path,
                                path_name,
                                trace,
                                roi_idx,
                                source_trials,
                                first_line[path_idx],
                                last_line[path_idx],
                                trial_offsets,
                                trial_num_samples[path_idx],
                            )
                            timing["raw_write_s"] += time.perf_counter() - started
                            for epoch_slot, epoch_id in enumerate(complete_epoch_ids):
                                epoch_trials = source_trials[
                                    analysis_epoch[path_idx, source_trials] == epoch_id
                                ]
                                raw_epoch = concatenate_trace_trials(
                                    trace,
                                    epoch_trials,
                                    first_line[path_idx],
                                    last_line[path_idx],
                                    trial_num_samples[path_idx],
                                )
                                started = time.perf_counter()
                                raw_for_derived = raw_epoch.copy()
                                censor = epoch_masks[epoch_slot]
                                if censor.size and np.any(censor):
                                    raw_for_derived[censor] = np.nan
                                f0, _ = compute_voltage_f0(raw_for_derived, sample_rate_hz, params)
                                dff, _ = compute_voltage_dff(
                                    raw_for_derived,
                                    f0,
                                    params["indicator_name"],
                                    params["indicator_direction"],
                                    params["precision"],
                                )
                                if censor.size and np.any(censor):
                                    f0[censor] = np.nan
                                    dff[censor] = np.nan
                                timing["derived_compute_s"] += time.perf_counter() - started
                                started = time.perf_counter()
                                write_derived_epoch(
                                    output_path,
                                    path_name,
                                    roi_idx,
                                    epoch_trials,
                                    trial_offsets,
                                    trial_num_samples[path_idx],
                                    f0,
                                    dff,
                                )
                                timing["derived_write_s"] += time.perf_counter() - started
                finally:
                    _close(mdf)
            if fallback_epoch_ids:
                fallback = transform_path_epochs(
                    output_path,
                    path_name,
                    n_rois,
                    analysis_epoch[path_idx],
                    trial_offsets,
                    trial_num_samples[path_idx],
                    sample_rate_hz,
                    params,
                    fallback_epoch_ids,
                )
                timing["fallback_read_s"] += fallback["read_s"]
                timing["derived_compute_s"] += fallback["compute_s"]
                timing["derived_write_s"] += fallback["write_s"]
            timing["total_s"] = time.perf_counter() - path_started
            summary["timing"]["path"][path_idx] = timing
            path_summary["timing"] = timing
        summary["timing"]["total_s"] = time.perf_counter() - run_started
        if total_voltage_rois == 0:
            output_path.unlink(missing_ok=True)
            raise _error(
                "Voltage:NoVoltageROIs",
                "No Voltage ROIs were found on any imaging path; no fluorescence data were extracted.",
            )
        return summary
    except Exception as exc:
        cleanup_partial_output(output_path, exc)
        raise


__all__ = ["FORMAT_VERSION", "voltage"]
