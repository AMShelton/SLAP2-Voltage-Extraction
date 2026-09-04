#!/usr/bin/env python3
"""
Validate a SLAP2 VoltageSummary.h5 without loading the full file into memory.

Primary checks
--------------
1. Voltage HDF5 structure and axis conventions.
2. Contract comparison against the GIAnT glutamate experiment_summary.h5 layout.
3. Session metadata / ROI counts, optionally derived from an old extractDendrites MAT summary.
4. Internal raw_f / f0 / dff consistency.
5. Direct raw-F parity against old extractDendrites trial-sliced HDF5 output.
6. Optional F0 parity against the current vip-slap2-analysis Python implementation.
7. Export a compact, unfiltered, full-rate snippet HDF5 for external inspection.

This script does not filter, smooth, resample, or otherwise temporally transform
raw_f or dff. Snippets are copied at native sample rate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import h5py
import numpy as np


GIANT_REFERENCE = {
    "source": "GIAnT glutamate experiment_summary.h5 supplied during SLAP2-Voltage-Extraction validation",
    "paths": {
        "Path1": {
            "Z_depths": [1, 1],
            "frame_info/trial_num_frames": [1, 1],
            "frame_info/frame_line_idxs": [1, 60001],
            "global/F": [60001, 2],
            "sources/spatial/coords": [3, 21],
            "sources/spatial/profiles": [640, 379, 1, 21],
            "sources/temporal/F0": [60001, 2, 21],
            "sources/temporal/SNR": [1, 21],
            "sources/temporal/dF_denoised": [60001, 2, 21],
            "sources/temporal/dF_ls": [60001, 2, 21],
            "sources/temporal/events": [60001, 2, 21],
            "visualizations/act_im": [640, 379, 1],
            "visualizations/act_im_peaks": [3, 21],
            "visualizations/mean_im": [640, 379, 1, 2],
        },
        "Path2": {
            "Z_depths": [1, 1],
            "frame_info/trial_num_frames": [1, 1],
            "frame_info/frame_line_idxs": [1, 60001],
            "global/F": [60001, 2],
            "sources/spatial/coords": [3, 11],
            "sources/spatial/profiles": [334, 337, 1, 11],
            "sources/temporal/F0": [60001, 2, 11],
            "sources/temporal/SNR": [1, 11],
            "sources/temporal/dF_denoised": [60001, 2, 11],
            "sources/temporal/dF_ls": [60001, 2, 11],
            "sources/temporal/events": [60001, 2, 11],
            "visualizations/act_im": [334, 337, 1],
            "visualizations/act_im_peaks": [3, 11],
            "visualizations/mean_im": [334, 337, 1, 2],
        },
    },
    "shared_contract": {
        "root_groups": ["params"],
        "per_path_groups": ["frame_info", "sources/spatial", "sources/temporal"],
        "per_path_datasets": ["Z_depths", "frame_info/trial_num_frames",
                              "frame_info/frame_line_idxs",
                              "sources/spatial/profiles", "sources/spatial/coords"],
        "spatial_axis_contract": "profiles is [X,Y,Z,source] in h5py; coords is [3,source]",
        "temporal_axis_contract": "temporal source arrays are [time,channel,source] in h5py",
    },
    "voltage_specific_differences_expected": {
        "voltage_only": [
            "Path#/sample_rate_hz",
            "Path#/frame_info/trial_epoch",
            "Path#/frame_info/sample_epoch",
            "Path#/sources/spatial/source_roi_index",
            "Path#/sources/spatial/roi_pixel_count",
            "Path#/sources/temporal/raw_f",
            "Path#/sources/temporal/f0",
            "Path#/sources/temporal/dff",
        ],
        "giant_only": [
            "Path#/global/F",
            "Path#/visualizations/*",
            "Path#/frame_info/discard_frames",
            "Path#/frame_info/online/offline motion shifts",
            "Path#/sources/temporal/F0",
            "Path#/sources/temporal/SNR",
            "Path#/sources/temporal/dF_ls",
            "Path#/sources/temporal/dF_denoised",
            "Path#/sources/temporal/events",
        ],
        "note": (
            "Voltage intentionally keeps vip-slap2-analysis-compatible lower-case 'f0'. "
            "GIAnT/SILo uses upper-case 'F0'. This is a naming difference, not an axis-contract difference."
        ),
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--voltage", required=True, type=Path,
                   help="Completed VoltageSummary.h5")
    p.add_argument("--outdir", type=Path, default=None,
                   help="Validation output directory. Default: <VoltageSummary parent>/validation")
    p.add_argument("--old-summary", type=Path, default=None,
                   help="Old dendriticVoltageSummary-*.mat (MATLAB v7.3) for benchmark metadata")
    p.add_argument("--old-traces", type=Path, default=None,
                   help="Old dendriticVoltageTraces-*.h5. If omitted, try the path recorded in --old-summary.")
    p.add_argument("--vip-repo", type=Path, default=None,
                   help="Local vip-slap2-analysis repo root for independent F0 parity.")
    p.add_argument("--expected-rois", type=str, default=None,
                   help="Comma-separated expected ROI counts, e.g. 4,3. Old summary takes precedence.")
    p.add_argument("--snippet-sec", type=float, default=2.0,
                   help="Native-rate snippet duration for start/middle/end export (default 2 s).")
    p.add_argument("--sample-chunk", type=int, default=131072,
                   help="Chunk size for sampled internal QC.")
    p.add_argument("--no-subset", action="store_true",
                   help="Do not export validation_subset.h5")
    return p.parse_args()


def jsonable(x: Any) -> Any:
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        v = float(x)
        return v if math.isfinite(v) else str(v)
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (bytes, np.bytes_)):
        return x.decode("utf-8", errors="replace")
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    return x


def sorted_paths(f: h5py.File) -> List[str]:
    out = [k for k in f.keys() if k.startswith("Path") and k[4:].isdigit()]
    return sorted(out, key=lambda s: int(s[4:]))


def dataset_manifest(filename: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with h5py.File(filename, "r") as f:
        def visit(name: str, obj: Any) -> None:
            if isinstance(obj, h5py.Dataset):
                rows.append({
                    "path": "/" + name,
                    "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                    "chunks": list(obj.chunks) if obj.chunks else None,
                    "compression": obj.compression,
                    "attrs": {k: jsonable(v) for k, v in obj.attrs.items()},
                })
        f.visititems(visit)
    return rows


def read_string_dataset(f: h5py.File, path: str, default: str = "") -> str:
    if path not in f:
        return default
    x = f[path][()]
    arr = np.asarray(x)
    if arr.size == 0:
        return default
    v = arr.reshape(-1)[0]
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, str):
        return v
    # MATLAB char arrays in v7.3 MAT summaries.
    if arr.dtype.kind in {"u", "i"} and arr.ndim >= 1 and arr.size > 1:
        try:
            return "".join(chr(int(c)) for c in arr.reshape(-1, order="F") if int(c) != 0)
        except Exception:
            pass
    return str(v)


def read_numeric_scalar(f: h5py.File, path: str, default: float = float("nan")) -> float:
    if path not in f:
        return default
    arr = np.asarray(f[path][()])
    if arr.size == 0:
        return default
    try:
        return float(arr.reshape(-1)[0])
    except Exception:
        return default


def roi_count(f: h5py.File, path_name: str) -> int:
    base = f"{path_name}/sources/spatial"
    sri = f"{base}/source_roi_index"
    coords = f"{base}/coords"
    if sri in f:
        return int(np.asarray(f[sri].shape).prod())
    if coords in f:
        shape = f[coords].shape
        if len(shape) != 2 or 3 not in shape:
            raise ValueError(f"Cannot infer ROI count from {coords} shape={shape}")
        return int(shape[1] if shape[0] == 3 else shape[0])
    return 0


def temporal_layout(ds: h5py.Dataset, n_rois: int) -> Tuple[int, int, int, int, int, int]:
    """Return time_axis, channel_axis, roi_axis, n_time, n_channel, n_roi."""
    shape = tuple(int(x) for x in ds.shape)
    if len(shape) != 3:
        raise ValueError(f"Expected 3-D temporal dataset, got {ds.name} shape={shape}")
    # MATLAB writer should appear as [time, channel, source] in h5py.
    if shape[1] == 1 and shape[2] == n_rois:
        return 0, 1, 2, shape[0], shape[1], shape[2]
    # Defensive fallback if a non-MATLAB writer is used later.
    roi_axes = [i for i, x in enumerate(shape) if x == n_rois]
    ch_axes = [i for i, x in enumerate(shape) if x == 1]
    for rax in roi_axes:
        for cax in ch_axes:
            if cax == rax:
                continue
            tax = ({0, 1, 2} - {rax, cax}).pop()
            return tax, cax, rax, shape[tax], shape[cax], shape[rax]
    raise ValueError(f"Cannot infer temporal axes for {ds.name}: shape={shape}, n_rois={n_rois}")


def read_trace(ds: h5py.Dataset, roi0: int, start: int, stop: int, n_rois: int) -> np.ndarray:
    tax, cax, rax, _, _, _ = temporal_layout(ds, n_rois)
    sl: List[Any] = [slice(None)] * 3
    sl[tax] = slice(int(start), int(stop))
    sl[cax] = 0
    sl[rax] = int(roi0)
    out = np.asarray(ds[tuple(sl)], dtype=np.float32).reshape(-1)
    return out


def read_1d_dataset(ds: h5py.Dataset) -> np.ndarray:
    return np.asarray(ds[()]).reshape(-1)


def sample_windows(n: int, width: int) -> List[Tuple[str, int, int]]:
    width = max(1, min(int(width), int(n)))
    starts = {
        "start": 0,
        "middle": max(0, n // 2 - width // 2),
        "end": max(0, n - width),
    }
    return [(label, int(s), int(min(n, s + width))) for label, s in starts.items()]


def accumulator() -> Dict[str, float]:
    return {
        "n": 0.0, "sum_abs": 0.0, "sum_sq": 0.0, "max_abs": 0.0,
        "sum_x": 0.0, "sum_y": 0.0, "sum_x2": 0.0, "sum_y2": 0.0, "sum_xy": 0.0,
        "nan_mismatch": 0.0, "exact": 0.0,
    }


def update_acc(acc: Dict[str, float], x: np.ndarray, y: np.ndarray) -> None:
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    if x.size != y.size:
        raise ValueError(f"Comparison size mismatch {x.size} != {y.size}")
    fx = np.isfinite(x)
    fy = np.isfinite(y)
    acc["nan_mismatch"] += float(np.count_nonzero(fx != fy))
    good = fx & fy
    if not np.any(good):
        return
    xx = x[good]
    yy = y[good]
    d = xx - yy
    a = np.abs(d)
    n = float(xx.size)
    acc["n"] += n
    acc["sum_abs"] += float(a.sum(dtype=np.float64))
    acc["sum_sq"] += float(np.square(d).sum(dtype=np.float64))
    acc["max_abs"] = max(acc["max_abs"], float(a.max(initial=0.0)))
    acc["sum_x"] += float(xx.sum(dtype=np.float64))
    acc["sum_y"] += float(yy.sum(dtype=np.float64))
    acc["sum_x2"] += float(np.square(xx).sum(dtype=np.float64))
    acc["sum_y2"] += float(np.square(yy).sum(dtype=np.float64))
    acc["sum_xy"] += float((xx * yy).sum(dtype=np.float64))
    acc["exact"] += float(np.count_nonzero(xx == yy))


def finalize_acc(acc: Dict[str, float]) -> Dict[str, Any]:
    n = acc["n"]
    if n <= 0:
        return {"n_finite": 0, "mae": None, "rmse": None, "max_abs": None,
                "pearson_r": None, "exact_fraction": None,
                "nan_mismatch": int(acc["nan_mismatch"])}
    num = n * acc["sum_xy"] - acc["sum_x"] * acc["sum_y"]
    denx = n * acc["sum_x2"] - acc["sum_x"] ** 2
    deny = n * acc["sum_y2"] - acc["sum_y"] ** 2
    den = math.sqrt(max(0.0, denx) * max(0.0, deny))
    r = num / den if den > 0 else (1.0 if acc["max_abs"] == 0 else float("nan"))
    return {
        "n_finite": int(n),
        "mae": acc["sum_abs"] / n,
        "rmse": math.sqrt(acc["sum_sq"] / n),
        "max_abs": acc["max_abs"],
        "pearson_r": r,
        "exact_fraction": acc["exact"] / n,
        "nan_mismatch": int(acc["nan_mismatch"]),
    }


def old_summary_metadata(path: Path) -> Dict[str, Any]:
    """Read only the benchmark fields required from an extractDendrites MATLAB v7.3 summary."""
    out: Dict[str, Any] = {"path": str(path)}
    with h5py.File(path, "r") as f:
        out["n_analysis_rois"] = np.asarray(f["summary/nAnalysisROIs"][()]).reshape(-1).astype(int).tolist()
        out["n_trials"] = int(read_numeric_scalar(f, "summary/nTrials"))
        out["n_epochs"] = int(read_numeric_scalar(f, "summary/nEpochs"))
        out["output_h5"] = read_string_dataset(f, "summary/outputH5")
        out["created_at"] = read_string_dataset(f, "summary/createdAt")
        out["completed_at"] = read_string_dataset(f, "summary/completedAt")
        out["output_mode"] = read_string_dataset(f, "summary/outputMode")
        out["roi_global_offsets"] = np.asarray(f["summary/roiGlobalOffsets"][()]).reshape(-1).astype(int).tolist()
        out["n_total_rois"] = int(read_numeric_scalar(f, "summary/nTotalROIs"))
        out["trace_window_lines"] = read_numeric_scalar(f, "summary/params/windowWidth_lines")
        out["trace_expected_window_lines"] = read_numeric_scalar(f, "summary/params/expectedWindowWidth_lines")
        out["n_workers"] = read_numeric_scalar(f, "summary/params/numWorkers")
        out["max_concurrent_rois"] = read_numeric_scalar(f, "summary/params/maxConcurrentROIs")

        z = []
        line_rates = []
        lines_per_cycle = []
        total_lines = []
        if "summary/dmd/metadata" in f:
            refs = np.asarray(f["summary/dmd/metadata"][()]).reshape(-1)
            for ref in refs:
                obj = f[ref]
                z.append(float(np.asarray(obj["parsePlanZs"][()]).reshape(-1)[0])
                         if "parsePlanZs" in obj else float("nan"))
                line_rates.append(float(np.asarray(obj["lineRateHz"][()]).reshape(-1)[0])
                                  if "lineRateHz" in obj else float("nan"))
        if "summary/dmd/linesPerCycle" in f:
            for ref in np.asarray(f["summary/dmd/linesPerCycle"][()]).reshape(-1):
                lines_per_cycle.append(int(np.asarray(f[ref][()]).reshape(-1)[0]))
        if "summary/dmd/totalNumLines" in f:
            for ref in np.asarray(f["summary/dmd/totalNumLines"][()]).reshape(-1):
                total_lines.append(int(np.asarray(f[ref][()]).reshape(-1)[0]))
        out["z_depths"] = z
        out["line_rate_hz"] = line_rates
        out["lines_per_cycle"] = lines_per_cycle
        out["total_num_lines"] = total_lines
    return out


def voltage_param(f: h5py.File, name: str, default: Any = None) -> Any:
    p = f"params/{name}"
    if p not in f:
        return default
    ds = f[p]
    arr = np.asarray(ds[()])
    if arr.size == 0:
        return default
    if arr.dtype.kind in {"O", "S", "U"}:
        return read_string_dataset(f, p, str(default) if default is not None else "")
    return jsonable(arr.reshape(-1)[0])


def validate_structure(voltage: Path, expected_rois: Optional[List[int]]) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "voltage_file": str(voltage),
        "checks": [],
        "paths": {},
        "giant_contract": {},
    }
    with h5py.File(voltage, "r") as f:
        paths = sorted_paths(f)
        report["n_paths"] = len(paths)
        report["format_version"] = read_string_dataset(f, "format_version", "")
        report["row_major"] = read_numeric_scalar(f, "row_major")
        report["params"] = {
            k: voltage_param(f, k) for k in [
                "indicatorName", "indicatorDirection", "f0Method", "f0Percentile",
                "f0Bin_s", "f0Smooth_s", "traceWindow_lines",
                "traceExpectedWindow_lines", "precision", "nWorkers",
                "maxConcurrentROIs", "h5ChunkSamples", "h5Deflate"
            ]
        }

        shared_required = [
            "Z_depths", "frame_info/trial_num_frames", "frame_info/frame_line_idxs",
            "sources/spatial/profiles", "sources/spatial/coords", "sources/temporal"
        ]
        contract_paths: Dict[str, Any] = {}
        for pi, pn in enumerate(paths):
            nr = roi_count(f, pn)
            pd: Dict[str, Any] = {"n_rois": nr, "checks": []}
            if expected_rois is not None and pi < len(expected_rois):
                pd["expected_rois"] = int(expected_rois[pi])
                pd["checks"].append({
                    "name": "expected_roi_count",
                    "pass": nr == int(expected_rois[pi]),
                    "observed": nr,
                    "expected": int(expected_rois[pi]),
                })

            for rel in shared_required:
                exists = f"{pn}/{rel}" in f
                pd["checks"].append({"name": f"exists:{rel}", "pass": exists})

            temporal_info = {}
            for name in ["raw_f", "f0", "dff"]:
                p = f"{pn}/sources/temporal/{name}"
                if p not in f:
                    pd["checks"].append({"name": f"exists:temporal/{name}", "pass": False})
                    continue
                ds = f[p]
                layout = temporal_layout(ds, nr)
                temporal_info[name] = {
                    "shape_h5py": list(ds.shape),
                    "time_axis": layout[0],
                    "channel_axis": layout[1],
                    "roi_axis": layout[2],
                    "n_time": layout[3],
                    "n_channel": layout[4],
                    "n_rois": layout[5],
                    "dtype": str(ds.dtype),
                }
            pd["temporal"] = temporal_info

            if {"raw_f", "f0", "dff"}.issubset(temporal_info):
                shapes = [tuple(temporal_info[k]["shape_h5py"]) for k in ("raw_f", "f0", "dff")]
                pd["checks"].append({"name": "temporal_shapes_match", "pass": len(set(shapes)) == 1,
                                     "shapes": [list(s) for s in shapes]})
                nt = temporal_info["raw_f"]["n_time"]
                tn_path = f"{pn}/frame_info/trial_num_frames"
                if tn_path in f:
                    trial_lengths = read_1d_dataset(f[tn_path]).astype(np.int64)
                    pd["n_trials"] = int(trial_lengths.size)
                    pd["trial_samples_sum"] = int(trial_lengths.sum())
                    pd["checks"].append({
                        "name": "trial_lengths_sum_to_temporal_length",
                        "pass": int(trial_lengths.sum()) == int(nt),
                        "observed": int(trial_lengths.sum()),
                        "expected": int(nt),
                    })
                for rel in ["frame_info/frame_line_idxs", "frame_info/sample_epoch"]:
                    q = f"{pn}/{rel}"
                    if q in f:
                        n_meta = int(np.prod(f[q].shape))
                        pd["checks"].append({
                            "name": f"{rel}_length_matches_temporal",
                            "pass": n_meta == int(nt),
                            "observed": n_meta,
                            "expected": int(nt),
                        })

            sr = read_numeric_scalar(f, f"{pn}/sample_rate_hz")
            pd["sample_rate_hz"] = sr
            pd["z_depths"] = read_1d_dataset(f[f"{pn}/Z_depths"]).astype(float).tolist() \
                if f"{pn}/Z_depths" in f else []

            # GIAnT role/axis contract, not equality of modality-specific dataset names.
            gi = {
                "has_path_frame_info_sources_scaffold": all(
                    f"{pn}/{g}" in f for g in ["frame_info", "sources/spatial", "sources/temporal"]
                ),
                "coords_shape": list(f[f"{pn}/sources/spatial/coords"].shape)
                    if f"{pn}/sources/spatial/coords" in f else None,
                "profiles_shape": list(f[f"{pn}/sources/spatial/profiles"].shape)
                    if f"{pn}/sources/spatial/profiles" in f else None,
            }
            coords_ok = False
            if gi["coords_shape"]:
                coords_ok = len(gi["coords_shape"]) == 2 and gi["coords_shape"][0] == 3 and gi["coords_shape"][1] == nr
            profiles_ok = False
            if gi["profiles_shape"]:
                s = gi["profiles_shape"]
                profiles_ok = len(s) == 4 and s[2] == 1 and s[3] == nr
            temporal_axis_ok = all(
                x.get("time_axis") == 0 and x.get("channel_axis") == 1 and x.get("roi_axis") == 2
                for x in temporal_info.values()
            ) if temporal_info else False
            gi["coords_axis_contract_pass"] = coords_ok
            gi["profiles_axis_contract_pass"] = profiles_ok
            gi["temporal_axis_contract_pass"] = temporal_axis_ok
            contract_paths[pn] = gi

            report["paths"][pn] = pd

        report["giant_contract"] = {
            "reference": GIANT_REFERENCE,
            "voltage_paths": contract_paths,
            "interpretation": (
                "Pass means Voltage follows the same HDF5 organizational and axis conventions as GIAnT. "
                "GIAnT-only source-extraction/motion datasets are intentionally not required for Voltage."
            ),
        }

    all_checks = []
    for pd in report["paths"].values():
        all_checks.extend(pd.get("checks", []))
    all_checks.extend({
        "name": f"GIAnT_contract:{pn}:{k}",
        "pass": bool(v),
    } for pn, gd in report["giant_contract"]["voltage_paths"].items()
      for k, v in gd.items() if k.endswith("_pass") or k == "has_path_frame_info_sources_scaffold")
    report["all_required_checks_pass"] = all(bool(c.get("pass")) for c in all_checks)
    report["checks"] = all_checks
    return report


def internal_signal_qc(voltage: Path, sample_chunk: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with h5py.File(voltage, "r") as f:
        indicator = str(voltage_param(f, "indicatorName", "") or "")
        direction = str(voltage_param(f, "indicatorDirection", "") or "").lower()
        # ASAP8 / increases -> +1; ASAP7 / decreases -> -1.
        if direction == "decreases" or ("asap7" in indicator.lower() and direction == "auto"):
            sign = -1.0
        else:
            sign = 1.0

        for pn in sorted_paths(f):
            nr = roi_count(f, pn)
            raw_ds = f[f"{pn}/sources/temporal/raw_f"]
            f0_ds = f[f"{pn}/sources/temporal/f0"]
            dff_ds = f[f"{pn}/sources/temporal/dff"]
            nt = temporal_layout(raw_ds, nr)[3]
            width = min(int(sample_chunk), int(nt))
            wins = sample_windows(nt, width)
            for r in range(nr):
                algebra_acc = accumulator()
                hash_obj = hashlib.blake2b(digest_size=16)
                finite_raw = finite_f0 = finite_dff = total = 0
                raw_min = float("inf")
                raw_max = float("-inf")
                dff_min = float("inf")
                dff_max = float("-inf")
                for label, a, b in wins:
                    raw = read_trace(raw_ds, r, a, b, nr)
                    f0 = read_trace(f0_ds, r, a, b, nr)
                    dff = read_trace(dff_ds, r, a, b, nr)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        expected = sign * (raw - f0) / f0
                    update_acc(algebra_acc, dff, expected)
                    hash_obj.update(np.ascontiguousarray(raw).view(np.uint8))
                    hash_obj.update(np.ascontiguousarray(f0).view(np.uint8))
                    hash_obj.update(np.ascontiguousarray(dff).view(np.uint8))
                    total += raw.size
                    finite_raw += int(np.isfinite(raw).sum())
                    finite_f0 += int(np.isfinite(f0).sum())
                    finite_dff += int(np.isfinite(dff).sum())
                    if np.any(np.isfinite(raw)):
                        raw_min = min(raw_min, float(np.nanmin(raw)))
                        raw_max = max(raw_max, float(np.nanmax(raw)))
                    if np.any(np.isfinite(dff)):
                        dff_min = min(dff_min, float(np.nanmin(dff)))
                        dff_max = max(dff_max, float(np.nanmax(dff)))
                alg = finalize_acc(algebra_acc)
                rows.append({
                    "path": pn,
                    "roi": r + 1,
                    "n_time": nt,
                    "sampled_values": total,
                    "sample_windows": ",".join(x[0] for x in wins),
                    "raw_finite_fraction": finite_raw / total if total else None,
                    "f0_finite_fraction": finite_f0 / total if total else None,
                    "dff_finite_fraction": finite_dff / total if total else None,
                    "raw_min_sampled": raw_min if math.isfinite(raw_min) else None,
                    "raw_max_sampled": raw_max if math.isfinite(raw_max) else None,
                    "dff_min_sampled": dff_min if math.isfinite(dff_min) else None,
                    "dff_max_sampled": dff_max if math.isfinite(dff_max) else None,
                    "dff_formula_mae": alg["mae"],
                    "dff_formula_max_abs": alg["max_abs"],
                    "dff_formula_nan_mismatch": alg["nan_mismatch"],
                    "sample_fingerprint_blake2b16": hash_obj.hexdigest(),
                })
    return rows


def old_trial_dataset_read(ds: h5py.Dataset, global_roi0: int, row0: int, n: int,
                           n_total_rois: int) -> np.ndarray:
    shape = tuple(int(x) for x in ds.shape)
    if len(shape) != 2:
        raise ValueError(f"Old trial dataset {ds.name} is not 2-D: {shape}")
    if shape[0] == n_total_rois:
        return np.asarray(ds[global_roi0, row0:row0+n], dtype=np.float32).reshape(-1)
    if shape[1] == n_total_rois:
        return np.asarray(ds[row0:row0+n, global_roi0], dtype=np.float32).reshape(-1)
    raise ValueError(f"Cannot infer ROI axis in old dataset {ds.name}, shape={shape}, nTotalROIs={n_total_rois}")


def raw_parity(voltage: Path, old_summary: Path, old_traces: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with h5py.File(old_summary, "r") as sm, h5py.File(old_traces, "r") as oldf, h5py.File(voltage, "r") as newf:
        n_rois_by_dmd = np.asarray(sm["summary/nAnalysisROIs"][()]).reshape(-1).astype(int)
        offsets = np.asarray(sm["summary/roiGlobalOffsets"][()]).reshape(-1).astype(int)
        n_total = int(np.asarray(sm["summary/nTotalROIs"][()]).reshape(-1)[0])

        first = np.asarray(sm["summary/trialLineRanges/firstLineRounded"][()], dtype=float)
        last = np.asarray(sm["summary/trialLineRanges/lastLineRounded"][()], dtype=float)
        global_first = np.asarray(sm["summary/trialLineRanges/trialFirstLineGlobal"][()], dtype=float).reshape(-1)
        # HDF5 representation is expected trials x DMD. Defensive transpose if needed.
        if first.shape[0] != global_first.size and first.shape[1] == global_first.size:
            first = first.T
            last = last.T

        for dmd0, pn in enumerate(sorted_paths(newf)):
            if dmd0 >= len(n_rois_by_dmd):
                break
            nr = int(n_rois_by_dmd[dmd0])
            new_nr = roi_count(newf, pn)
            if new_nr != nr:
                rows.append({
                    "path": pn, "roi": None, "status": "ROI_COUNT_MISMATCH",
                    "old_n_rois": nr, "new_n_rois": new_nr
                })
                continue
            new_ds = newf[f"{pn}/sources/temporal/raw_f"]
            new_nt = temporal_layout(new_ds, new_nr)[3]

            for r0 in range(nr):
                acc = accumulator()
                last_compared_source_line = 0
                n_segments = 0
                global_roi0 = int(offsets[dmd0]) + r0
                for t0 in range(first.shape[0]):
                    a0 = first[t0, dmd0] if dmd0 < first.shape[1] else np.nan
                    b0 = last[t0, dmd0] if dmd0 < last.shape[1] else np.nan
                    gf = global_first[t0]
                    if not (np.isfinite(a0) and np.isfinite(b0) and np.isfinite(gf)):
                        continue
                    a = int(round(a0))
                    b = int(round(b0))
                    if b < a or a < 1:
                        continue
                    # Avoid counting historical one-sample trial-boundary overlaps twice.
                    a = max(a, last_compared_source_line + 1)
                    b = min(b, int(new_nt))
                    if b < a:
                        continue
                    trial_name = f"traces/trial_{t0+1:04d}"
                    if trial_name not in oldf:
                        raise KeyError(f"Missing old dataset /{trial_name}")
                    row0 = a - int(round(gf))
                    n = b - a + 1
                    old_seg = old_trial_dataset_read(oldf[trial_name], global_roi0, row0, n, n_total)
                    new_seg = read_trace(new_ds, r0, a - 1, b, new_nr)
                    update_acc(acc, old_seg, new_seg)
                    last_compared_source_line = b
                    n_segments += 1
                result = finalize_acc(acc)
                rows.append({
                    "path": pn,
                    "roi": r0 + 1,
                    "status": "OK",
                    "old_global_roi": global_roi0 + 1,
                    "segments_compared": n_segments,
                    "last_source_line_compared": last_compared_source_line,
                    **result,
                })
    return rows


def vip_f0_parity(voltage: Path, vip_repo: Path) -> List[Dict[str, Any]]:
    src = vip_repo / "src"
    if not src.exists():
        raise FileNotFoundError(f"vip-slap2-analysis src directory not found: {src}")
    sys.path.insert(0, str(src))
    mod = importlib.import_module("vip_slap2_analysis.voltage.extraction")
    compute_voltage_f0 = getattr(mod, "compute_voltage_f0")
    compute_voltage_dff = getattr(mod, "compute_voltage_dff")

    rows: List[Dict[str, Any]] = []
    with h5py.File(voltage, "r") as f:
        percentile = float(voltage_param(f, "f0Percentile", 50.0))
        bin_sec = float(voltage_param(f, "f0Bin_s", 5.0))
        smooth_sec = float(voltage_param(f, "f0Smooth_s", 180.0))
        method = str(voltage_param(f, "f0Method", "robust"))
        indicator = str(voltage_param(f, "indicatorName", "ASAP8"))
        direction = str(voltage_param(f, "indicatorDirection", "auto")).lower()
        if direction == "increases":
            polarity = "depolarization_increases_fluorescence"
        elif direction == "decreases":
            polarity = "depolarization_decreases_fluorescence"
        else:
            polarity = "auto"

        for pn in sorted_paths(f):
            nr = roi_count(f, pn)
            raw_ds = f[f"{pn}/sources/temporal/raw_f"]
            stored_f0_ds = f[f"{pn}/sources/temporal/f0"]
            stored_dff_ds = f[f"{pn}/sources/temporal/dff"]
            nt = temporal_layout(raw_ds, nr)[3]
            sr = float(read_numeric_scalar(f, f"{pn}/sample_rate_hz"))
            trial_epoch_path = f"{pn}/frame_info/trial_epoch"
            if trial_epoch_path in f:
                unique_trial_epochs = np.unique(read_1d_dataset(f[trial_epoch_path]).astype(int))
                unique_trial_epochs = unique_trial_epochs[unique_trial_epochs > 0]
            else:
                unique_trial_epochs = np.array([1], dtype=int)
            if unique_trial_epochs.size != 1:
                rows.append({
                    "path": pn, "roi": None, "status": "SKIPPED_MULTI_EPOCH",
                    "reason": "This compact validator calls compute_voltage_f0 on one complete epoch at a time; current session expected one epoch."
                })
                continue

            for r0 in range(nr):
                # One ROI at a time: ~78 MB for a 19.5M-sample float32 trace.
                raw = read_trace(raw_ds, r0, 0, nt, nr)
                py_f0, meta = compute_voltage_f0(
                    raw,
                    sample_rate_hz=sr,
                    method=method,
                    percentile=percentile,
                    robust_bin_sec=bin_sec,
                    robust_smooth_sec=smooth_sec,
                )
                f0_acc = accumulator()
                dff_acc = accumulator()
                chunk = 262144
                for a in range(0, nt, chunk):
                    b = min(nt, a + chunk)
                    stored_f0 = read_trace(stored_f0_ds, r0, a, b, nr)
                    stored_dff = read_trace(stored_dff_ds, r0, a, b, nr)
                    py_f0_chunk = np.asarray(py_f0[a:b], dtype=np.float32)
                    py_dff = compute_voltage_dff(
                        raw[a:b], py_f0_chunk, indicator=indicator, dff_polarity=polarity
                    )
                    update_acc(f0_acc, stored_f0, py_f0_chunk)
                    update_acc(dff_acc, stored_dff, py_dff)
                fm = finalize_acc(f0_acc)
                dm = finalize_acc(dff_acc)
                rows.append({
                    "path": pn,
                    "roi": r0 + 1,
                    "status": "OK",
                    "sample_rate_hz": sr,
                    "f0_method_python": meta.get("f0_method"),
                    "f0_mae": fm["mae"],
                    "f0_rmse": fm["rmse"],
                    "f0_max_abs": fm["max_abs"],
                    "f0_pearson_r": fm["pearson_r"],
                    "f0_exact_fraction": fm["exact_fraction"],
                    "f0_nan_mismatch": fm["nan_mismatch"],
                    "dff_mae": dm["mae"],
                    "dff_rmse": dm["rmse"],
                    "dff_max_abs": dm["max_abs"],
                    "dff_pearson_r": dm["pearson_r"],
                    "dff_exact_fraction": dm["exact_fraction"],
                    "dff_nan_mismatch": dm["nan_mismatch"],
                })
                del raw, py_f0
    return rows


def export_subset(voltage: Path, out: Path, snippet_sec: float) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": str(out), "paths": {}}
    if out.exists():
        out.unlink()
    with h5py.File(voltage, "r") as src, h5py.File(out, "w") as dst:
        dst.attrs["source_voltage_summary"] = str(voltage)
        dst.attrs["description"] = (
            "Native-rate, unfiltered start/middle/end snippets copied from VoltageSummary.h5. "
            "No smoothing, filtering, resampling, or temporal transformation was applied."
        )
        for pn in sorted_paths(src):
            nr = roi_count(src, pn)
            sr = float(read_numeric_scalar(src, f"{pn}/sample_rate_hz"))
            raw_ds = src[f"{pn}/sources/temporal/raw_f"]
            nt = temporal_layout(raw_ds, nr)[3]
            width = max(1, int(round(float(snippet_sec) * sr)))
            wins = sample_windows(nt, width)
            gp = dst.require_group(pn)
            gp.attrs["sample_rate_hz"] = sr
            gp.attrs["n_rois"] = nr
            gp.attrs["n_time_source"] = nt
            gp.attrs["snippet_sec_requested"] = float(snippet_sec)

            # Sparse ROI profiles compress well and are useful for mask/geometry QC.
            prof_path = f"{pn}/sources/spatial/profiles"
            if prof_path in src:
                prof = np.asarray(src[prof_path][()])
                gp.create_dataset("profiles", data=prof, compression="gzip", compression_opts=4)
            coord_path = f"{pn}/sources/spatial/coords"
            if coord_path in src:
                gp.create_dataset("coords", data=np.asarray(src[coord_path][()]))
            sri_path = f"{pn}/sources/spatial/source_roi_index"
            if sri_path in src:
                gp.create_dataset("source_roi_index", data=np.asarray(src[sri_path][()]))

            for label, a, b in wins:
                gw = gp.require_group(label)
                gw.attrs["source_start_sample_0based"] = a
                gw.attrs["source_stop_sample_exclusive"] = b
                time = np.arange(b - a, dtype=np.float64) / sr
                gw.create_dataset("time_sec", data=time)
                for signal in ["raw_f", "f0", "dff"]:
                    ds = src[f"{pn}/sources/temporal/{signal}"]
                    data = np.stack([read_trace(ds, r, a, b, nr) for r in range(nr)], axis=0)
                    # Stored ROI x time in compact subset for easy notebook use.
                    gw.create_dataset(signal, data=data, compression="gzip", compression_opts=4,
                                      chunks=(1, min(data.shape[1], 65536)))
            info["paths"][pn] = {
                "n_rois": nr, "sample_rate_hz": sr, "n_time": nt,
                "windows": [{"label": l, "start": a, "stop": b} for l, a, b in wins]
            }
    info["size_bytes"] = out.stat().st_size
    return info


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: jsonable(r.get(k)) for k in keys})


def main() -> None:
    args = parse_args()
    voltage = args.voltage.expanduser().resolve()
    if not voltage.exists():
        raise FileNotFoundError(voltage)
    outdir = (args.outdir or (voltage.parent / "validation")).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    benchmark = None
    expected_rois = None
    if args.old_summary is not None:
        old_summary = args.old_summary.expanduser().resolve()
        benchmark = old_summary_metadata(old_summary)
        expected_rois = list(map(int, benchmark["n_analysis_rois"]))
    elif args.expected_rois:
        expected_rois = [int(x.strip()) for x in args.expected_rois.split(",") if x.strip()]

    manifest = dataset_manifest(voltage)
    write_csv(outdir / "voltage_h5_manifest.csv", manifest)

    structure = validate_structure(voltage, expected_rois)
    if benchmark is not None:
        structure["old_extractDendrites_benchmark"] = benchmark
    with (outdir / "validation_report.json").open("w", encoding="utf-8") as f:
        json.dump(jsonable(structure), f, indent=2)

    with (outdir / "giant_glutamate_reference_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(GIANT_REFERENCE, f, indent=2)

    internal = internal_signal_qc(voltage, args.sample_chunk)
    write_csv(outdir / "internal_signal_qc.csv", internal)

    parity_rows: List[Dict[str, Any]] = []
    old_traces = args.old_traces.expanduser().resolve() if args.old_traces else None
    old_summary_path = args.old_summary.expanduser().resolve() if args.old_summary else None
    if old_summary_path is not None and old_traces is None and benchmark:
        recorded = Path(str(benchmark.get("output_h5", "")))
        if recorded.exists():
            old_traces = recorded
    if old_summary_path is not None and old_traces is not None:
        if old_traces.exists():
            parity_rows = raw_parity(voltage, old_summary_path, old_traces)
            write_csv(outdir / "raw_f_parity_vs_extractDendrites.csv", parity_rows)
        else:
            print(f"Old traces H5 not found; raw parity skipped: {old_traces}")

    vip_rows: List[Dict[str, Any]] = []
    if args.vip_repo is not None:
        vip_rows = vip_f0_parity(voltage, args.vip_repo.expanduser().resolve())
        write_csv(outdir / "f0_dff_parity_vs_vip_slap2_analysis.csv", vip_rows)

    subset_info = None
    if not args.no_subset:
        subset_info = export_subset(voltage, outdir / "validation_subset.h5", args.snippet_sec)

    summary_lines = []
    summary_lines.append("SLAP2 Voltage validation")
    summary_lines.append("=" * 72)
    summary_lines.append(f"Voltage file: {voltage}")
    summary_lines.append(f"Required structure checks pass: {structure['all_required_checks_pass']}")
    for pn, pd in structure["paths"].items():
        temporal = pd.get("temporal", {}).get("raw_f", {})
        summary_lines.append(
            f"{pn}: ROIs={pd.get('n_rois')}  samples={temporal.get('n_time')}  "
            f"sample_rate={pd.get('sample_rate_hz')} Hz  Z={pd.get('z_depths')}"
        )
    if benchmark:
        summary_lines.append("")
        summary_lines.append(
            f"Old extractDendrites benchmark: ROIs={benchmark['n_analysis_rois']}, "
            f"trials={benchmark['n_trials']}, epochs={benchmark['n_epochs']}, "
            f"traceWindow={benchmark['trace_window_lines']}, "
            f"created={benchmark['created_at']}, completed={benchmark['completed_at']}"
        )
    if parity_rows:
        summary_lines.append("")
        summary_lines.append("Raw-F parity vs extractDendrites:")
        for r in parity_rows:
            if r.get("roi") is not None:
                summary_lines.append(
                    f"  {r['path']} ROI{r['roi']}: r={r.get('pearson_r'):.12g}, "
                    f"RMSE={r.get('rmse'):.6g}, max_abs={r.get('max_abs'):.6g}, "
                    f"exact={r.get('exact_fraction'):.6g}, n={r.get('n_finite')}"
                )
    if vip_rows:
        summary_lines.append("")
        summary_lines.append("F0/dFF parity vs vip-slap2-analysis:")
        for r in vip_rows:
            if r.get("roi") is not None and r.get("status") == "OK":
                summary_lines.append(
                    f"  {r['path']} ROI{r['roi']}: "
                    f"F0 RMSE={r.get('f0_rmse'):.6g}, max={r.get('f0_max_abs'):.6g}; "
                    f"dFF RMSE={r.get('dff_rmse'):.6g}, max={r.get('dff_max_abs'):.6g}"
                )
    if subset_info:
        summary_lines.append("")
        summary_lines.append(
            f"Compact native-rate subset: {subset_info['path']} "
            f"({subset_info['size_bytes']/1024**2:.1f} MiB)"
        )
    summary_lines.append("")
    summary_lines.append("Upload back to ChatGPT:")
    summary_lines.append("  validation_summary.txt")
    summary_lines.append("  validation_report.json")
    summary_lines.append("  internal_signal_qc.csv")
    if parity_rows:
        summary_lines.append("  raw_f_parity_vs_extractDendrites.csv")
    if vip_rows:
        summary_lines.append("  f0_dff_parity_vs_vip_slap2_analysis.csv")
    if subset_info:
        summary_lines.append("  validation_subset.h5")

    text = "\n".join(summary_lines) + "\n"
    (outdir / "validation_summary.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
