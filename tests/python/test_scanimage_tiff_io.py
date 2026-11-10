from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import struct
from typing import Any
import warnings

import numpy as np
import pytest

tiff_io = pytest.importorskip(
    "slap2_voltage_extraction.io.tiff",
    reason="Python ScanImage TIFF I/O translation has not been implemented yet",
)
ScanImageTiffReader = tiff_io.ScanImageTiffReader
scanimage_tiff_wrapper = tiff_io.scanimage_tiff_wrapper
scanimage_tiff_data_wrapper = tiff_io.scanimage_tiff_data_wrapper


def _assert_code(exc: BaseException, code: str) -> None:
    assert getattr(exc, "code", None) == code or code in str(exc)


def _call(reader: Any, snake_name: str, matlab_name: str, *args: Any) -> Any:
    """Use snake case when supplied, while tolerating MATLAB-style reader methods."""
    method = getattr(reader, snake_name, None) or getattr(reader, matlab_name)
    return method(*args)


def _is_open(reader: Any) -> bool:
    return bool(_call(reader, "is_open", "isOpen"))


def _api_version() -> str:
    method = getattr(ScanImageTiffReader, "api_version", None) or getattr(
        ScanImageTiffReader, "apiVersion"
    )
    return str(method())


def _write_tiff(path: Path, stack: np.ndarray) -> Path:
    """Write uncompressed pages; TIFF libraries replace MATLAB imwrite only in fixtures."""
    try:
        tifffile = pytest.importorskip("tifffile")
        with tifffile.TiffWriter(path) as writer:
            pages = stack.shape[2] if stack.ndim == 3 else 1
            for frame_index in range(pages):
                frame = stack[:, :, frame_index] if stack.ndim == 3 else stack
                writer.write(
                    frame, compression=None, photometric="minisblack", metadata=None
                )
        return path
    except pytest.skip.Exception:
        image_module = pytest.importorskip("PIL.Image")
        pages = stack.shape[2] if stack.ndim == 3 else 1
        images = [
            image_module.fromarray(stack[:, :, index] if stack.ndim == 3 else stack)
            for index in range(pages)
        ]
        images[0].save(path, format="TIFF", compression="raw", save_all=True, append_images=images[1:])
        return path


@pytest.fixture
def write_tiff(tmp_path: Path) -> Callable[[np.ndarray], Path]:
    counter = 0

    def write(stack: np.ndarray) -> Path:
        nonlocal counter
        counter += 1
        return _write_tiff(tmp_path / f"stack_{counter}.tif", stack)

    return write


def _append_legacy_metadata(path: Path, metadata: bytes) -> None:
    with path.open("ab") as stream:
        stream.write(metadata)
        stream.write(struct.pack("<I", len(metadata)))


def _close(reader: Any) -> None:
    reader.close()


def test_api_version() -> None:
    # Preserve the implementation-identity contract without falsely labelling Python as MATLAB.
    assert _api_version() == "ScanImageTiffReader (pure Python)"


def test_constructor_opens_and_close_is_idempotent(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    reader = ScanImageTiffReader(write_tiff(frame))

    assert _is_open(reader)
    reader.close()
    assert not _is_open(reader)
    reader.close()
    assert not _is_open(reader)


def test_open_on_default_constructed_reader(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 21, dtype=np.uint8).reshape((4, 5), order="F")
    filename = write_tiff(frame)
    reader = ScanImageTiffReader()

    assert not _is_open(reader)
    returned = reader.open(filename)

    assert returned is reader
    assert _is_open(reader)
    np.testing.assert_array_equal(reader.data(), frame.T)
    _close(reader)


def test_reads_single_page_uint8_with_current_orientation(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    frame = np.array([[1, 2, 3, 4], [11, 12, 13, 14], [21, 22, 23, 24]], dtype=np.uint8)
    reader = ScanImageTiffReader(write_tiff(frame))

    actual = reader.data()
    shape = reader.shape()

    assert actual.dtype == np.dtype(np.uint8)
    np.testing.assert_array_equal(actual, frame.T)
    assert shape.ndim == 2
    assert list(shape.dims) == [4, 3]
    assert shape.type == 0
    assert list(shape.strides) == [1, 4, 12]
    _close(reader)


def test_reads_multi_page_uint16_stack(write_tiff: Callable[[np.ndarray], Path]) -> None:
    first = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]], dtype=np.uint16)
    second = first + np.uint16(100)
    reader = ScanImageTiffReader(write_tiff(np.stack((first, second), axis=2)))

    actual = reader.data()
    expected = np.stack((first.T, second.T), axis=2)
    shape = reader.shape()

    assert actual.dtype == np.dtype(np.uint16)
    np.testing.assert_array_equal(actual, expected)
    assert actual.shape == (4, 3, 2)
    assert shape.ndim == 3
    assert list(shape.dims) == [4, 3, 2]
    assert shape.type == 1
    assert list(shape.strides) == [1, 4, 12, 24]
    _close(reader)


def test_descriptions_and_metadata_for_plain_tiff(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    reader = ScanImageTiffReader(write_tiff(frame))

    descriptions = reader.descriptions()
    assert np.asarray(descriptions, dtype=object).shape == (1, 1)
    assert str(np.asarray(descriptions, dtype=object)[0, 0]).strip() == ""
    # Keep strict: a NUL is not empty and exposed the legacy metadata bug.
    assert reader.metadata() == ""
    _close(reader)


def test_wrapper_returns_data_metadata_and_descriptions(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    first = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
    second = first + np.uint16(10)
    filename = write_tiff(np.stack((first, second), axis=2))

    data, metadata, descriptions = scanimage_tiff_wrapper(filename)

    np.testing.assert_array_equal(data, np.stack((first.T, second.T), axis=2))
    assert metadata == ""
    descriptions_array = np.asarray(descriptions, dtype=object)
    assert descriptions_array.shape == (2, 1)
    assert all(str(value).strip() == "" for value in descriptions_array.flat)


def test_reads_validated_legacy_metadata_trailer(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    filename = write_tiff(frame)
    expected = "state.acq.numberOfFrames = 1\n"
    _append_legacy_metadata(filename, expected.encode("latin-1"))

    reader = ScanImageTiffReader(filename)
    assert reader.metadata() == expected
    _close(reader)


def test_rejects_null_only_legacy_metadata_candidate(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    filename = write_tiff(frame)
    _append_legacy_metadata(filename, b"\x00")

    reader = ScanImageTiffReader(filename)
    assert reader.metadata() == ""
    _close(reader)


def test_rejects_implausible_legacy_metadata_length(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    filename = write_tiff(frame)
    with filename.open("ab") as stream:
        stream.write(struct.pack("<I", np.iinfo(np.uint32).max))

    reader = ScanImageTiffReader(filename)
    assert reader.metadata() == ""
    _close(reader)


def test_data_wrapper_falls_back_after_reader_is_closed(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    first = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
    second = first + np.uint16(10)
    filename = write_tiff(np.stack((first, second), axis=2))
    reader = ScanImageTiffReader(filename)
    reader.close()

    # MATLAB warning identifiers become either warning codes or warning text in Python.
    with pytest.warns(Warning) as caught:
        scanimage_tiff_data_wrapper(reader, filename)
    assert any(
        getattr(item.message, "code", None) == "ScanImageTiffDataWrapper:Fallback"
        or "ScanImageTiffDataWrapper:Fallback" in str(item.message)
        for item in caught
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        actual = scanimage_tiff_data_wrapper(reader, filename)
    np.testing.assert_array_equal(actual, np.stack((first.T, second.T), axis=2))


@pytest.mark.parametrize("method_name", ["data", "descriptions", "metadata", "shape"])
def test_closed_reader_methods_fail(
    write_tiff: Callable[[np.ndarray], Path], method_name: str
) -> None:
    reader = ScanImageTiffReader(write_tiff(np.ones((2, 3), dtype=np.uint8)))
    reader.close()

    with pytest.raises(Exception) as caught:
        getattr(reader, method_name)()
    _assert_code(caught.value, "ScanImageTiffReader:NotOpen")


def test_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(Exception) as caught:
        ScanImageTiffReader(tmp_path / "missing.tif")
    _assert_code(caught.value, "ScanImageTiffReader:FileNotFound")


def test_invalid_byte_order_mark_fails(tmp_path: Path) -> None:
    filename = tmp_path / "invalid.tif"
    filename.write_bytes(bytes([0, 1, 2, 3]))

    with pytest.raises(Exception) as caught:
        ScanImageTiffReader(filename)
    _assert_code(caught.value, "ScanImageTiffReader:InvalidFile")
