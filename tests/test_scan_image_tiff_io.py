from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import struct
import warnings

import numpy as np
import pytest

tiff_io = pytest.importorskip(
    "slap2_voltage_extraction.io",
    reason="Python ScanImage TIFF I/O translation has not been implemented yet",
)
ScanImageTiffReader = tiff_io.ScanImageTiffReader
scan_image_tiff_wrapper = tiff_io.scan_image_tiff_wrapper
scan_image_tiff_data_wrapper = tiff_io.scan_image_tiff_data_wrapper


def _assert_code(exc: BaseException, code: str) -> None:
    assert getattr(exc, "code", None) == code or code in str(exc)


def _write_tiff(path: Path, stack: np.ndarray) -> Path:
    """Write uncompressed TIFF pages for deterministic fixtures."""
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


def test_api_version() -> None:
    # Preserve the implementation-identity contract.
    assert ScanImageTiffReader.api_version() == "ScanImageTiffReader (pure Python)"


def test_constructor_opens_and_close_is_idempotent(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    reader = ScanImageTiffReader(write_tiff(frame))

    assert reader.is_open()
    reader.close()
    assert not reader.is_open()
    reader.close()
    assert not reader.is_open()


def test_open_on_default_constructed_reader(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 21, dtype=np.uint8).reshape((4, 5), order="F")
    filename = write_tiff(frame)
    reader = ScanImageTiffReader()

    assert not reader.is_open()
    returned = reader.open(filename)

    assert returned is reader
    assert reader.is_open()
    np.testing.assert_array_equal(reader.data(), frame.T)
    reader.close()


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
    reader.close()


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
    reader.close()


def test_descriptions_and_metadata_for_plain_tiff(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    reader = ScanImageTiffReader(write_tiff(frame))

    descriptions = reader.descriptions()
    assert len(descriptions) == 1
    assert str(descriptions[0]).strip() == ""
    # Keep strict: a NUL is not empty and exposed the legacy metadata bug.
    assert reader.metadata() == ""
    reader.close()


def test_wrapper_returns_data_metadata_and_descriptions(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    first = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
    second = first + np.uint16(10)
    filename = write_tiff(np.stack((first, second), axis=2))

    data, metadata, descriptions = scan_image_tiff_wrapper(filename)

    np.testing.assert_array_equal(data, np.stack((first.T, second.T), axis=2))
    assert metadata == ""
    assert len(descriptions) == 2
    assert all(str(value).strip() == "" for value in descriptions)


def test_reads_validated_legacy_metadata_trailer(write_tiff: Callable[[np.ndarray], Path]) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    filename = write_tiff(frame)
    expected = "state.acq.numberOfFrames = 1\n"
    _append_legacy_metadata(filename, expected.encode("latin-1"))

    reader = ScanImageTiffReader(filename)
    assert reader.metadata() == expected
    reader.close()


def test_rejects_null_only_legacy_metadata_candidate(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    filename = write_tiff(frame)
    _append_legacy_metadata(filename, b"\x00")

    reader = ScanImageTiffReader(filename)
    assert reader.metadata() == ""
    reader.close()


def test_rejects_implausible_legacy_metadata_length(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    frame = np.arange(1, 13, dtype=np.uint16).reshape((3, 4), order="F")
    filename = write_tiff(frame)
    with filename.open("ab") as stream:
        stream.write(struct.pack("<I", np.iinfo(np.uint32).max))

    reader = ScanImageTiffReader(filename)
    assert reader.metadata() == ""
    reader.close()


def test_data_wrapper_falls_back_after_reader_is_closed(
    write_tiff: Callable[[np.ndarray], Path],
) -> None:
    first = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
    second = first + np.uint16(10)
    filename = write_tiff(np.stack((first, second), axis=2))
    reader = ScanImageTiffReader(filename)
    reader.close()

    # Stable warning identifiers may be exposed as codes or embedded in warning text.
    with pytest.warns(Warning) as caught:
        scan_image_tiff_data_wrapper(reader, filename)
    assert any(
        getattr(item.message, "code", None) == "ScanImageTiffDataWrapper:Fallback"
        or "ScanImageTiffDataWrapper:Fallback" in str(item.message)
        for item in caught
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        actual = scan_image_tiff_data_wrapper(reader, filename)
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
