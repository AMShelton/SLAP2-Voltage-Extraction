from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

hdf5 = pytest.importorskip(
    "slap2_voltage_extraction.io.hdf5",
    reason="Python HDF5 I/O translation has not been implemented yet",
)
save_struct_to_h5 = hdf5.save_struct_to_h5
load_struct_from_h5 = hdf5.load_struct_from_h5


def _assert_code(exc: BaseException, code: str) -> None:
    assert getattr(exc, "code", None) == code or code in str(exc)


@pytest.fixture
def h5_file(tmp_path: Path) -> Path:
    return tmp_path / "values.h5"


def test_nested_numeric_and_logical_round_trip(h5_file: Path) -> None:
    input_value = {
        # order="F" reproduces MATLAB reshape rather than NumPy's C-order default.
        "doubleMatrix": np.arange(1, 13, dtype=np.float64).reshape((3, 4), order="F"),
        "singleCube": np.arange(1, 25, dtype=np.float32).reshape((2, 3, 4), order="F"),
        "uint16Row": np.array([[0, 1, 65535]], dtype=np.uint16),
        "int32Column": np.array([[-2], [0], [7]], dtype=np.int32),
        "flags": np.array([[True, False], [False, True]], dtype=np.bool_),
        "nested": {
            "scalar": np.int8(-3),
            "vector": np.array([[1, 2, 3]], dtype=np.uint64),
        },
    }

    save_struct_to_h5(input_value, h5_file)
    actual = load_struct_from_h5(h5_file)

    np.testing.assert_array_equal(actual["doubleMatrix"], input_value["doubleMatrix"])
    np.testing.assert_array_equal(actual["singleCube"], input_value["singleCube"])
    np.testing.assert_array_equal(actual["uint16Row"], input_value["uint16Row"])
    np.testing.assert_array_equal(actual["int32Column"], input_value["int32Column"])
    np.testing.assert_array_equal(actual["flags"], input_value["flags"].astype(np.int8))
    assert np.asarray(actual["nested"]["scalar"]).dtype == np.dtype(np.int8)
    assert actual["nested"]["scalar"] == input_value["nested"]["scalar"]
    np.testing.assert_array_equal(actual["nested"]["vector"], input_value["nested"]["vector"])


def test_text_and_cell_shapes_round_trip(h5_file: Path) -> None:
    input_value = {
        "title": "voltage extraction",
        "label": "single string",
        "labels": np.array([["alpha", "beta"], ["gamma", "delta"]], dtype=np.str_),
        "notes": np.array([["one", "two"], ["", None]], dtype=object),
        "filename": np.array([["only.dat"]], dtype=object),
        "fn_raw": np.array([["a.dat", "b.dat"], ["c.dat", "d.dat"]], dtype=object),
    }

    save_struct_to_h5(input_value, h5_file)
    actual = load_struct_from_h5(h5_file)

    assert actual["title"] == input_value["title"]
    assert actual["label"] == "single string"
    np.testing.assert_array_equal(
        actual["labels"], np.array([["alpha", "beta"], ["gamma", "delta"]], dtype=object)
    )
    np.testing.assert_array_equal(
        actual["notes"], np.array([["one", "two"], ["", ""]], dtype=object)
    )
    np.testing.assert_array_equal(actual["filename"], input_value["filename"])
    np.testing.assert_array_equal(actual["fn_raw"], input_value["fn_raw"])


def test_dataset_dimensions_and_layout_marker(h5_file: Path) -> None:
    h5py = pytest.importorskip("h5py")
    input_value = {
        "matrix": np.arange(1, 25, dtype=np.uint16).reshape((2, 3, 4), order="F"),
        "filename": np.array([["a", "b", "c"]], dtype=object),
    }

    save_struct_to_h5(input_value, h5_file)

    with h5py.File(h5_file, "r") as handle:
        assert handle["matrix"].shape == (2, 3, 4)
        assert handle["filename"].shape == (1, 3)
        row_major = handle["row_major"][()]
    assert np.asarray(row_major).dtype == np.dtype(np.uint8)
    assert row_major == np.uint8(0)


def test_empty_values_are_skipped(h5_file: Path) -> None:
    input_value = {
        "emptyNumeric": np.empty((0, 0), dtype=np.float64),
        "emptyCell": np.empty((0, 0), dtype=object),
        "present": np.uint8(9),
    }

    save_struct_to_h5(input_value, h5_file)
    actual = load_struct_from_h5(h5_file)

    assert "emptyNumeric" not in actual
    assert "emptyCell" not in actual
    assert actual["present"] == np.uint8(9)
    assert actual["row_major"] == np.uint8(0)


def test_existing_file_is_overwritten(h5_file: Path) -> None:
    save_struct_to_h5({"oldValue": np.float64(1)}, h5_file)
    save_struct_to_h5({"newValue": np.uint16(2)}, h5_file)

    actual = load_struct_from_h5(h5_file)
    assert "oldValue" not in actual
    assert actual["newValue"] == np.uint16(2)


def test_legacy_field_names_are_normalized(h5_file: Path) -> None:
    input_value = {
        "slap2_info": {
            "ref_stack": {
                "DMD1": {"channels": np.array([[1.0, 2.0]], dtype=np.float64)},
                "Path2": {"channels": np.float64(3)},
            }
        },
        "slap2": {"Z": np.array([[10.0, 20.0]], dtype=np.float64)},
    }

    save_struct_to_h5(input_value, h5_file)
    actual = load_struct_from_h5(h5_file)

    assert "DMD1" not in actual["slap2_info"]["ref_stack"]
    np.testing.assert_array_equal(
        actual["slap2_info"]["ref_stack"]["Path1"]["channels"],
        np.array([[1.0, 2.0]], dtype=np.float64),
    )
    assert actual["slap2_info"]["ref_stack"]["Path2"]["channels"] == np.float64(3)
    assert "Z" not in actual["slap2"]
    np.testing.assert_array_equal(
        actual["slap2"]["Z_depths"], np.array([[10.0, 20.0]], dtype=np.float64)
    )


def test_existing_normalized_names_take_precedence(h5_file: Path) -> None:
    input_value = {
        "slap2_info": {"ref_stack": {"DMD1": np.uint8(1), "Path1": np.uint8(2)}},
        "slap2": {"Z": np.float64(3), "Z_depths": np.float64(4)},
    }

    save_struct_to_h5(input_value, h5_file)
    actual = load_struct_from_h5(h5_file)

    assert actual["slap2_info"]["ref_stack"]["Path1"] == np.uint8(2)
    assert actual["slap2"]["Z"] == np.float64(3)
    assert actual["slap2"]["Z_depths"] == np.float64(4)


@pytest.mark.parametrize("call", [lambda: save_struct_to_h5({}), lambda: save_struct_to_h5({}, "")])
def test_save_rejects_missing_filename(call: Callable[[], Any]) -> None:
    with pytest.raises(Exception) as caught:
        call()
    _assert_code(caught.value, "saveStructToH5:MissingFilename")


def test_save_rejects_non_scalar_struct_input(h5_file: Path) -> None:
    # A 1x2 object array is the direct NumPy analogue of a MATLAB struct array.
    input_value = np.array([[{"value": 1.0}, {"value": 1.0}]], dtype=object)
    with pytest.raises(Exception) as caught:
        save_struct_to_h5(input_value, h5_file)
    _assert_code(caught.value, "saveStructToH5:UnsupportedInput")


def test_save_rejects_non_scalar_nested_struct(h5_file: Path) -> None:
    input_value = {
        "items": np.array([[{"value": 1.0}, {"value": 1.0}]], dtype=object)
    }
    with pytest.raises(Exception) as caught:
        save_struct_to_h5(input_value, h5_file)
    _assert_code(caught.value, "saveStructToH5:NonScalarStruct")


def test_save_rejects_unsupported_cell_contents(h5_file: Path) -> None:
    input_value = {"values": np.array([[1.0, 2.0]], dtype=object)}
    with pytest.raises(Exception) as caught:
        save_struct_to_h5(input_value, h5_file)
    _assert_code(caught.value, "saveStructToH5:UnsupportedCell")


def test_save_rejects_unsupported_value_type(h5_file: Path) -> None:
    with pytest.raises(Exception) as caught:
        save_struct_to_h5({"value": datetime(2024, 1, 1)}, h5_file)
    _assert_code(caught.value, "saveStructToH5:UnsupportedType")


@pytest.mark.parametrize("call", [lambda: load_struct_from_h5(), lambda: load_struct_from_h5("")])
def test_load_rejects_missing_filename(call: Callable[[], Any]) -> None:
    with pytest.raises(Exception) as caught:
        call()
    _assert_code(caught.value, "loadStructFromH5:MissingFilename")


def test_load_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(Exception) as caught:
        load_struct_from_h5(tmp_path / "missing.h5")
    _assert_code(caught.value, "loadStructFromH5:FileNotFound")


def test_trial_table_roundtrip_regression(tmp_path: Path) -> None:
    """Keep the standalone MATLAB roundtrip regression as a duplicate test."""
    path = tmp_path / "trial_table.h5"
    input_value = {
        "datadr": r"C:\data",
        "savedr": r"C:\out",
        "filename": np.array([["a.dat", "b.dat"], ["c.dat", "d.dat"]], dtype=object),
        "epoch": np.ones((2, 2), dtype=np.float64),
        "slap2_info": {
            "first_line": np.array([[1.0, 11.0], [1.0, 11.0]], dtype=np.float64),
            "last_line": np.array([[10.0, 20.0], [10.0, 20.0]], dtype=np.float64),
            "line_range_convention": "inclusive",
        },
    }

    save_struct_to_h5(input_value, path)
    actual = load_struct_from_h5(path)

    np.testing.assert_array_equal(actual["filename"], input_value["filename"])
    np.testing.assert_array_equal(
        np.asarray(actual["slap2_info"]["first_line"], dtype=np.float64),
        input_value["slap2_info"]["first_line"],
    )
    assert str(actual["slap2_info"]["line_range_convention"]) == "inclusive"
