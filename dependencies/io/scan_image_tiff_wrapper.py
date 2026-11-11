"""Direct Python translation of ``ScanImageTiffWrapper.m``."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .scan_image_tiff_data_wrapper import scan_image_tiff_data_wrapper
from .scan_image_tiff_reader import ScanImageTiffReader


def scan_image_tiff_wrapper(filename: str | Path) -> tuple[np.ndarray, str, list[str]]:
    """Return TIFF data, ScanImage metadata, and page descriptions from one open."""

    with ScanImageTiffReader(filename) as reader:
        data = scan_image_tiff_data_wrapper(reader, filename)
        metadata = reader.metadata()
        descriptions = reader.descriptions()
    return data, metadata, descriptions


# Alias matching the established test/API spelling.
scanimage_tiff_wrapper = scan_image_tiff_wrapper

__all__ = ["scan_image_tiff_wrapper", "scanimage_tiff_wrapper"]
