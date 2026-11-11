"""Direct Python translation of ``ScanImageTiffReader.m``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import BinaryIO

import numpy as np
import tifffile

from source_extraction._errors import Slap2VoltageError


_ND_TYPES = {
    np.dtype(np.uint8): 0,
    np.dtype(np.uint16): 1,
    np.dtype(np.uint32): 2,
    np.dtype(np.uint64): 3,
    np.dtype(np.int8): 4,
    np.dtype(np.int16): 5,
    np.dtype(np.int32): 6,
    np.dtype(np.int64): 7,
    np.dtype(np.float32): 8,
    np.dtype(np.float64): 9,
}


@dataclass(frozen=True)
class TiffShape:
    ndim: int
    dims: tuple[int, ...]
    type: int
    strides: tuple[int, ...]


class ScanImageTiffReader:
    """Read ScanImage-compatible TIFF pages and metadata without a MEX file."""

    def __init__(self, filename: str | Path | None = None) -> None:
        self._filename: Path | None = None
        self._stream: BinaryIO | None = None
        self._byte_order = "<"
        self._end_of_tiff_data = 0
        self._file_size = 0
        if filename is not None:
            self.open(filename)

    @staticmethod
    def api_version() -> str:
        return "ScanImageTiffReader (pure Python)"

    def __enter__(self) -> ScanImageTiffReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def open(self, filename: str | Path) -> ScanImageTiffReader:
        self.close()
        path = Path(filename).resolve()
        if not path.is_file():
            raise Slap2VoltageError(
                "ScanImageTiffReader:FileNotFound", f"File {path} not found on disk."
            )
        self._filename = path
        self._stream = path.open("rb")
        self._file_size = path.stat().st_size
        self._identify()
        self._index_end()
        return self

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def is_open(self) -> bool:
        return self._stream is not None and not self._stream.closed

    def _ensure_open(self) -> tuple[Path, BinaryIO]:
        if not self.is_open() or self._filename is None or self._stream is None:
            raise Slap2VoltageError(
                "ScanImageTiffReader:NotOpen", "File is not open for reading."
            )
        return self._filename, self._stream

    def _identify(self) -> None:
        _, stream = self._ensure_open()
        stream.seek(0)
        bom = stream.read(2)
        if bom == b"II":
            self._byte_order = "<"
        elif bom == b"MM":
            self._byte_order = ">"
        else:
            raise Slap2VoltageError(
                "ScanImageTiffReader:InvalidFile",
                "Invalid TIFF: unrecognized byte order mark.",
            )
        subtype_bytes = stream.read(2)
        if len(subtype_bytes) != 2:
            raise Slap2VoltageError("ScanImageTiffReader:InvalidFile", "Truncated TIFF header.")
        subtype = struct.unpack(f"{self._byte_order}H", subtype_bytes)[0]
        if subtype not in (42, 43):
            raise Slap2VoltageError(
                "ScanImageTiffReader:InvalidFile", f"Unrecognized TIFF sub-type {subtype}."
            )

    def _index_end(self) -> None:
        filename, _ = self._ensure_open()
        try:
            with tifffile.TiffFile(filename) as tif:
                maximum = 0
                for page in tif.pages:
                    maximum = max(maximum, int(page.offset) + 2)
                    offsets = np.atleast_1d(page.dataoffsets)
                    counts = np.atleast_1d(page.databytecounts)
                    for offset, count in zip(offsets, counts, strict=True):
                        maximum = max(maximum, int(offset) + int(count))
                self._end_of_tiff_data = maximum
        except Exception as exc:
            raise Slap2VoltageError("ScanImageTiffReader:InvalidFile", str(exc)) from exc

    def _pages(self) -> tuple[list[np.ndarray], list[str]]:
        filename, _ = self._ensure_open()
        try:
            with tifffile.TiffFile(filename) as tif:
                pages = [page.asarray() for page in tif.pages]
                descriptions = [(page.description or "").strip("\x00").strip() for page in tif.pages]
        except Exception as exc:
            raise Slap2VoltageError("ScanImageTiffReader:InvalidFile", str(exc)) from exc
        if not pages:
            raise Slap2VoltageError("safeScanImageData:EmptyTiff", f"No TIFF frames found: {filename}")
        return pages, descriptions

    def data(self) -> np.ndarray:
        pages, _ = self._pages()
        oriented = [np.asarray(page).T if page.ndim == 2 else np.swapaxes(page, 0, 1) for page in pages]
        return oriented[0] if len(oriented) == 1 else np.stack(oriented, axis=-1)

    def descriptions(self) -> list[str]:
        _, descriptions = self._pages()
        return descriptions

    def shape(self) -> TiffShape:
        data = self.data()
        dtype = np.dtype(data.dtype)
        if dtype not in _ND_TYPES:
            raise Slap2VoltageError(
                "ScanImageTiffReader:BadPixel", f"Unsupported TIFF pixel dtype: {dtype}"
            )
        dims = tuple(int(value) for value in data.shape if value != 1)
        strides = [1]
        for dimension in dims:
            strides.append(strides[-1] * dimension)
        return TiffShape(len(dims), dims, _ND_TYPES[dtype], tuple(strides))

    @staticmethod
    def _null_terminate(value: bytes) -> bytes:
        return value.split(b"\x00", 1)[0]

    def _legacy_metadata(self) -> str:
        _, stream = self._ensure_open()
        if self._file_size < 4:
            return ""
        stream.seek(self._file_size - 4)
        trailer = stream.read(4)
        if len(trailer) != 4:
            return ""
        size = struct.unpack(f"{self._byte_order}I", trailer)[0]
        if size == 0 or size > self._file_size - 4:
            return ""
        start = self._file_size - 4 - size
        if start < self._end_of_tiff_data:
            return ""
        stream.seek(start)
        candidate = self._null_terminate(stream.read(size))
        if not candidate or not candidate.strip():
            return ""
        if any(byte not in (9, 10, 13) and not 32 <= byte <= 126 for byte in candidate):
            return ""
        return candidate.decode("latin-1")

    def metadata(self) -> str:
        _, stream = self._ensure_open()
        if self._file_size >= 32:
            stream.seek(16)
            magic_bytes = stream.read(4)
            if len(magic_bytes) == 4 and struct.unpack(f"{self._byte_order}I", magic_bytes)[0] == 0x07030301:
                stream.seek(24)
                header_size, roi_size = struct.unpack(f"{self._byte_order}II", stream.read(8))
                stream.seek(32)
                payload = stream.read(header_size + roi_size)
                if roi_size == 0:
                    return payload.decode("latin-1").rstrip()
                first = self._null_terminate(payload[:header_size]).decode("latin-1")
                second = self._null_terminate(payload[header_size:]).decode("latin-1")
                if payload.startswith(b"{"):
                    return "{" + first.strip("{}") + "," + second.strip("{}") + "}"
                return (payload[: max(header_size - 1, 0)] + b"\n" + payload[header_size:]).decode("latin-1")
        return self._legacy_metadata()


__all__ = ["ScanImageTiffReader", "TiffShape"]
