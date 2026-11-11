"""Array-like access to ScanImage TIFF data."""

from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np
import tifffile

from .scan_image_tiff_reader import ScanImageTiffReader


def _fallback(filename: str | Path) -> np.ndarray:
    with tifffile.TiffFile(filename) as tif:
        pages = [page.asarray() for page in tif.pages]
    if not pages:
        raise ValueError(f"safeScanImageData:EmptyTiff: No TIFF frames found in file: {filename}")
    # MATLAB lineage: fallback reads retain the same established ScanImage axis orientation.
    oriented = [page.T if page.ndim == 2 else np.swapaxes(page, 0, 1) for page in pages]
    return oriented[0] if len(oriented) == 1 else np.stack(oriented, axis=-1)


def scan_image_tiff_data_wrapper(
    reader: ScanImageTiffReader,
    tiff_file: str | Path,
) -> np.ndarray:
    """Read through ``reader``, falling back to tifffile after a reader failure."""

    try:
        return reader.data()
    except Exception as exc:
        warnings.warn(
            "ScanImageTiffDataWrapper:Fallback: "
            f"reader.data() failed ({exc}); falling back to tifffile.",
            RuntimeWarning,
            stacklevel=2,
        )
        return _fallback(tiff_file)


# Alias matching the established test/API spelling.
__all__ = ["scan_image_tiff_data_wrapper"]
