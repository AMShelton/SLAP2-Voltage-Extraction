from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

voltage_module = pytest.importorskip("slap2_voltage_extraction.voltage")
hdf5_module = pytest.importorskip("slap2_voltage_extraction.io")
voltage = voltage_module.voltage
FORMAT_VERSION = voltage_module.FORMAT_VERSION
save_struct_to_h5 = hdf5_module.save_struct_to_h5


@dataclass
class Header:
    dmd_pixels_per_row: int = 2
    dmd_pixels_per_column: int = 2
    bytes_per_cycle: int = 16
    first_cycle_offset_bytes: int = 0
    lines_per_cycle: int = 8


@dataclass
class DataFile:
    filename: str


class FakeMultiDataFiles:
    """Faithful tiny SLAP2 reader double selected from the requested DAT path."""

    def __init__(self, filename: str | Path) -> None:
        path = Path(filename)
        if not path.is_file():
            raise FileNotFoundError(f"Fake raw data file does not exist: {path}")
        roi = {
            "mask": np.asarray([[True, False], [False, False]], dtype=bool),
            # Deliberately not "Integrate": classification must use parse-plan membership.
            "imagingMode": "test-double",
        }
        self.metadata = {
            "dmdPixelsPerRow": 2,
            "dmdPixelsPerColumn": 2,
            "samplesPerLine": 1,
            "channelsSave": 1,
            "linePeriod_s": 0.001,
            "AcquisitionContainer": {
                "ROIs": {"rois": [roi]},
                "ParsePlan": {"lineRateHz": 1000, "zs": np.asarray([12.5])},
            },
        }
        # Alias retained for readers that expose the established meta_data spelling.
        self.meta_data = self.metadata
        self.fast_zs = np.asarray([12.5], dtype=np.float64)
        self.header = Header()
        self.line_super_pixel_ids = [np.asarray([5], dtype=np.uint32) for _ in range(8)]
        self.line_fast_z_idxs = np.zeros(8, dtype=np.int64)
        # Public positions use the established one-based int16 sample contract.
        self.line_data_start_idxs = np.arange(1, 9, dtype=np.int64)
        self.h_data_files = [DataFile(str(path))]
        replacement = 1 if "no_voltage" in path.name.lower() else 5
        self.z_pixel_replacement_maps = [np.asarray([[0, replacement]], dtype=np.uint32)]

    def close(self) -> None:
        pass

    def __enter__(self) -> FakeMultiDataFiles:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def params(output_dir: Path, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "output_dir": str(output_dir),
        "output_filename": "result.h5",
        "overwrite": False,
        "use_parallel": False,
        "precision": "single",
        "indicator_name": "test",
        "indicator_direction": "increases",
        "f0_method": "static",
        "f0_percentile": 50,
        "h5_chunk_samples": 16,
        "h5_deflate": 0,
    }
    values.update(overrides)
    return values


def write_trial_table(
    work_dir: Path,
    filename: str | list[str],
    first_line: int | list[int],
    last_line: int | list[int],
) -> Path:
    filenames = [filename] if isinstance(filename, str) else filename
    first_lines = [first_line] if isinstance(first_line, int) else first_line
    last_lines = [last_line] if isinstance(last_line, int) else last_line
    table = {
        "datadr": str(work_dir),
        "filename": np.asarray(filenames, dtype=object).reshape(1, -1),
        "epoch": np.ones((1, len(filenames)), dtype=np.int32),
        "slap2_info": {
            "first_line": np.asarray(first_lines, dtype=np.int64).reshape(1, -1),
            "last_line": np.asarray(last_lines, dtype=np.int64).reshape(1, -1),
            "line_range_convention": "inclusive",
        },
    }
    path = work_dir / "trial_table.h5"
    save_struct_to_h5(table, path)
    return path


def assert_error_code(exc: BaseException, expected: str) -> None:
    assert getattr(exc, "code", None) == expected or expected in str(exc)


def scalar(group: h5py.File, path: str) -> Any:
    value = group[path][()]
    return value.item() if isinstance(value, np.ndarray) and value.size == 1 else value


def text(group: h5py.File, path: str) -> str:
    value = scalar(group, path)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        return "".join(chr(int(item)) for item in value.ravel(order="F"))
    return str(value)


@pytest.fixture(autouse=True)
def install_fake_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voltage_module, "MultiDataFiles", FakeMultiDataFiles, raising=False)


class TestVoltage:
    def test_extracts_single_roi_and_writes_public_contract(
        self, tmp_path: Path, write_int16
    ) -> None:
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        trial_table_path = write_trial_table(work_dir, "source.dat", 1, 8)
        write_int16(str(work_dir / "source.dat"), np.arange(100, 132, dtype=np.int16))

        summary = voltage(trial_table_path, params(output_dir))

        output_path = output_dir / "result.h5"
        assert Path(summary["trial_table_path"]) == trial_table_path
        assert Path(summary["output_path"]) == output_path
        assert summary["n_paths"] == 1
        assert summary["n_trials"] == 1
        path_summary = summary["path"][0]
        assert path_summary["n_acquisition_rois"] == 1
        assert path_summary["n_rois"] == 1
        np.testing.assert_array_equal(path_summary["source_roi_idx"], [0])
        assert path_summary["sample_rate_hz"] == 1000
        assert path_summary["total_samples"] == 8
        np.testing.assert_array_equal(path_summary["trial_num_samples"], [8])
        np.testing.assert_array_equal(path_summary["trial_epoch"], [1])
        np.testing.assert_array_equal(path_summary["in_memory_epoch_ids"], [1])
        assert np.asarray(path_summary["fallback_epoch_ids"]).size == 0
        assert output_path.is_file()

        with h5py.File(output_path, "r") as handle:
            assert text(handle, "/format_version") == "0.2.3"
            assert FORMAT_VERSION == "0.2.3"
            assert scalar(handle, "/Path1/sample_rate_hz") == 1000
            np.testing.assert_array_equal(handle["/Path1/frame_info/trial_num_frames"][...].ravel(), [8])
            np.testing.assert_array_equal(handle["/Path1/frame_info/frame_line_idxs"][...].ravel(), np.arange(1, 9))
            np.testing.assert_array_equal(handle["/Path1/frame_info/sample_epoch"][...].ravel(), np.ones(8))
            np.testing.assert_array_equal(handle["/Path1/sources/spatial/source_roi_index"][...].ravel(), [1])
            np.testing.assert_array_equal(handle["/Path1/sources/spatial/roi_pixel_count"][...].ravel(), [1])
            raw = handle["/Path1/sources/temporal/raw_f"][...]
            f0 = handle["/Path1/sources/temporal/f0"][...]
            dff = handle["/Path1/sources/temporal/dff"][...]
            assert raw.dtype == np.float32
            assert raw.shape == f0.shape == dff.shape == (1, 1, 8)
            assert np.all(np.isfinite(raw))
            assert np.min(raw) > 0
            np.testing.assert_allclose(f0, np.full_like(f0, np.median(raw)), atol=1e-5, rtol=0)
            np.testing.assert_allclose(dff, (raw - f0) / f0, atol=1e-5, rtol=0)
            attrs = handle["/Path1/sources/temporal/dff"].attrs
            direction = attrs["indicator_direction"]
            convention = attrs["sign_convention"]
            if isinstance(direction, bytes):
                direction = direction.decode()
            if isinstance(convention, bytes):
                convention = convention.decode()
            assert direction == "increases"
            assert convention == "Positive dff corresponds to positive membrane-voltage deflection."

    def test_directory_input_resolves_trial_table(self, tmp_path: Path, write_int16) -> None:
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        write_trial_table(work_dir, "source.dat", 1, 4)
        write_int16(str(work_dir / "source.dat"), np.arange(20, 36, dtype=np.int16))

        summary = voltage(work_dir, params(output_dir))

        assert Path(summary["trial_table_path"]) == work_dir / "trial_table.h5"

    def test_existing_output_is_preserved_without_overwrite(self, tmp_path: Path) -> None:
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        trial_table_path = write_trial_table(work_dir, "source.dat", 1, 4)
        output_path = output_dir / "result.h5"
        output_path.write_text("sentinel", encoding="utf-8")

        with pytest.raises(Exception) as caught:
            voltage(trial_table_path, params(output_dir))

        assert_error_code(caught.value, "Voltage:OutputExists")
        assert output_path.read_text(encoding="utf-8") == "sentinel"

    def test_shape_mismatch_cleans_partial_output(self, tmp_path: Path) -> None:
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        trial_table_path = write_trial_table(
            work_dir, ["source.dat", "source.dat"], [1, 5], [8]
        )
        output_path = output_dir / "result.h5"

        with pytest.raises(Exception) as caught:
            voltage(trial_table_path, params(output_dir))

        assert_error_code(caught.value, "Voltage:TrialTableShapeMismatch")
        assert not output_path.exists()

    def test_no_voltage_rois_fails_without_leaving_output(
        self, tmp_path: Path, write_int16
    ) -> None:
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        trial_table_path = write_trial_table(work_dir, "no_voltage.dat", 1, 4)
        write_int16(str(work_dir / "no_voltage.dat"), np.arange(1, 17, dtype=np.int16))
        output_path = output_dir / "result.h5"

        with pytest.raises(Exception) as caught:
            voltage(trial_table_path, params(output_dir))

        assert_error_code(caught.value, "Voltage:NoVoltageROIs")
        assert not output_path.exists()

    def test_missing_trial_table_reports_public_error(self, tmp_path: Path) -> None:
        with pytest.raises(Exception) as caught:
            voltage(tmp_path / "missing.h5", params(tmp_path))
        assert_error_code(caught.value, "Voltage:TrialTableNotFound")


class TestVoltageRoiDiscoveryContract:
    def test_parse_plan_classification_ignores_imaging_mode_string(
        self, tmp_path: Path, write_int16
    ) -> None:
        """The integration mapping above is valid despite imagingMode='test-double'."""
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        trial_table_path = write_trial_table(work_dir, "source.dat", 1, 8)
        write_int16(str(work_dir / "source.dat"), np.arange(100, 132, dtype=np.int16))

        summary = voltage(trial_table_path, params(output_dir))

        discovery = summary["path"][0]["roi_discovery"]
        assert discovery["method"] == "parse_plan_integration_membership"
        np.testing.assert_array_equal(discovery["source_roi_idx"], [0])
        np.testing.assert_array_equal(discovery["integration_super_pixel_counts"], [1])
        assert discovery["imaging_mode"] == ["test-double"]

    def test_all_zero_rois_fail_and_delete_output(self, tmp_path: Path, write_int16) -> None:
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"
        work_dir.mkdir()
        output_dir.mkdir()
        trial_table_path = write_trial_table(work_dir, "no_voltage.dat", 1, 4)
        write_int16(str(work_dir / "no_voltage.dat"), np.arange(1, 17, dtype=np.int16))
        output_path = output_dir / "result.h5"

        with pytest.raises(Exception) as caught:
            voltage(trial_table_path, params(output_dir, use_parallel=True))

        assert_error_code(caught.value, "Voltage:NoVoltageROIs")
        assert not output_path.exists()
