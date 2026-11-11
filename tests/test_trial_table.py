from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

trial_table = pytest.importorskip(
    "slap2_voltage_extraction.build_trial_table_slap2",
    reason="Python trial-table translation has not been implemented yet",
)
build_trial_table_slap2 = trial_table.build_trial_table_slap2

LINE_PERIOD_S = 1e-4
START_TIME = datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
MTIME_ATOL_S = 1e-9 * 86_400


@dataclass(frozen=True)
class FakeDataFile:
    total_num_lines: int
    line_period_s: float = LINE_PERIOD_S


class FakeDataReader:
    """Read the line count from the tiny text fixture used in place of a DAT file."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, path: str | Path) -> FakeDataFile:
        source = Path(path)
        self.paths.append(source)
        return FakeDataFile(int(source.read_text(encoding="ascii")))


class FakeTiffReader:
    """Return equivalent scientific metadata using Python-native values."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, path: str | Path) -> tuple[np.ndarray, str, list[dict[str, Any]]]:
        self.paths.append(Path(path))
        image = np.arange(1, 8 * 8 * 6 + 1, dtype=np.uint16).reshape((8, 8, 6))
        descriptions = [
            {
                "channel": channel,
                "z": z,
                "dmdPixel2SampleTransform": np.eye(3).tolist(),
            }
            for channel, z in zip([1, 2, 1, 2, 1, 2], [0, 0, 1, 1, 2, 2], strict=True)
        ]
        return image, "fake ScanImage metadata", descriptions


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    save_dir = tmp_path / "save"
    data_root.mkdir()
    save_dir.mkdir()
    return data_root, save_dir


@pytest.fixture
def readers() -> tuple[FakeDataReader, FakeTiffReader]:
    return FakeDataReader(), FakeTiffReader()


def _build(
    data_root: Path,
    save_dir: Path,
    readers: tuple[FakeDataReader, FakeTiffReader],
) -> dict[str, Any]:
    data_reader, tiff_reader = readers
    return build_trial_table_slap2(
        data_root,
        save_dir,
        use_all_files=True,
        data_reader=data_reader,
        tiff_reader=tiff_reader,
    )


def _write_dat(folder: Path, name: str, n_lines: int, modified: datetime) -> Path:
    assert modified.tzinfo is not None
    path = folder / name
    path.write_text(str(n_lines), encoding="ascii")
    timestamp = modified.timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def _touch(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.touch()
    return path


def _write_references(root: Path) -> None:
    for dmd in (1, 2):
        _touch(root / "reference", f"acq_DMD{dmd}_CONFIG1-REFERENCE.tif")


def _as_counts(value: int | Sequence[int]) -> list[int]:
    if isinstance(value, int):
        return [value]
    return list(value)


def _write_triggered(
    folder: Path,
    dmd1_counts: int | Sequence[int],
    dmd2_counts: int | Sequence[int],
) -> tuple[list[str], list[str]]:
    first = _as_counts(dmd1_counts)
    second = _as_counts(dmd2_counts)
    dmd1 = [f"acq_DMD1-TRIAL{k:06d}.dat" for k in range(1, len(first) + 1)]
    dmd2 = [f"acq_DMD2-TRIAL{k:06d}.dat" for k in range(1, len(second) + 1)]
    for k, (name, count) in enumerate(zip(dmd1, first, strict=True), start=1):
        _write_dat(folder, name, count, START_TIME + timedelta(minutes=k))
    for k, (name, count) in enumerate(zip(dmd2, second, strict=True), start=1):
        _write_dat(folder, name, count, START_TIME + timedelta(minutes=k))
    return dmd1, dmd2


def _array(table: dict[str, Any], name: str) -> np.ndarray:
    return np.asarray(table[name])


def _info(table: dict[str, Any], name: str) -> np.ndarray:
    return np.asarray(table["slap2_info"][name])


def _assert_filenames(actual: Any, expected: Sequence[Sequence[str]]) -> None:
    np.testing.assert_array_equal(np.asarray(actual, dtype=object), np.asarray(expected, dtype=object))


def _mtime(folder: Path, name: str) -> float:
    return (folder / name).stat().st_mtime


class TestBuildTrialTableSlap2:
    def test_triggered_trials(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        n_lines = [100_000, 120_000, 110_000]
        dmd1, dmd2 = _write_triggered(data_root, n_lines, n_lines)
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)

        _assert_filenames(table["filename"], [dmd1, dmd2])
        np.testing.assert_array_equal(_array(table, "epoch"), np.ones((2, 3), dtype=int))
        np.testing.assert_array_equal(_array(table, "true_trial_ix"), [[1, 2, 3], [1, 2, 3]])
        np.testing.assert_array_equal(_info(table, "first_line"), np.ones((2, 3), dtype=int))
        np.testing.assert_array_equal(_info(table, "last_line"), [n_lines, n_lines])
        assert table["slap2_info"]["line_range_convention"] == "inclusive"

        end_times = np.asarray([_mtime(data_root, name) for name in dmd1])
        np.testing.assert_allclose(
            _info(table, "trial_end_time_from_pc"), end_times, atol=MTIME_ATOL_S, rtol=0
        )
        np.testing.assert_allclose(
            _info(table, "trial_start_time_inferred"),
            end_times - np.asarray(n_lines) * LINE_PERIOD_S,
            atol=MTIME_ATOL_S,
            rtol=0,
        )

    def test_triggered_trial_line_mismatch(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        dmd1, dmd2 = _write_triggered(data_root, [100_000, 220_000], [100_000, 100_000, 120_000])
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)

        _assert_filenames(table["filename"], [[dmd1[0], dmd1[1], dmd1[1]], dmd2])
        np.testing.assert_array_equal(_info(table, "first_line"), [[1, 1, 100_001], [1, 1, 1]])
        np.testing.assert_array_equal(
            _info(table, "last_line"), [[100_000, 100_000, 220_000], [100_000, 100_000, 120_000]]
        )
        np.testing.assert_allclose(
            _info(table, "trial_end_time_from_pc"),
            [_mtime(data_root, dmd1[0]), _mtime(data_root, dmd2[1]), _mtime(data_root, dmd1[1])],
            atol=MTIME_ATOL_S,
            rtol=0,
        )

    def test_continuous_cycle_files_use_inclusive_nonoverlapping_ranges(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        names = ["acq_DMD1-CYCLE-000000.dat", "acq_DMD2-CYCLE-000000.dat"]
        for name in names:
            _write_dat(data_root, name, 450_000, START_TIME)
        (data_root / "acq_DMD1-CYCLE-000001.dat").write_text("not a line count", encoding="ascii")
        (data_root / "acq_DMD2-CYCLE-000001.dat").write_text("not a line count", encoding="ascii")
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)

        first = np.asarray([1, 150_001, 300_001])
        last = np.asarray([150_000, 300_000, 450_000])
        _assert_filenames(table["filename"], [[names[0]] * 3, [names[1]] * 3])
        np.testing.assert_array_equal(_array(table, "true_trial_ix"), [[1, 2, 3], [1, 2, 3]])
        np.testing.assert_array_equal(_info(table, "first_line"), np.tile(first, (2, 1)))
        np.testing.assert_array_equal(_info(table, "last_line"), np.tile(last, (2, 1)))
        np.testing.assert_array_equal(_info(table, "first_line")[:, 1:], _info(table, "last_line")[:, :-1] + 1)
        assert int(np.sum(last - first + 1)) == 450_000
        assert all("000001" not in path.name for path in readers[0].paths)

        end = _mtime(data_root, names[0])
        np.testing.assert_allclose(
            _info(table, "trial_end_time_from_pc"),
            end - (450_000 - last) * LINE_PERIOD_S,
            atol=MTIME_ATOL_S,
            rtol=0,
        )
        np.testing.assert_allclose(
            _info(table, "trial_start_time_inferred"),
            end - (450_000 - first) * LINE_PERIOD_S,
            atol=MTIME_ATOL_S,
            rtol=0,
        )

    @pytest.mark.parametrize("n_lines", [1, 199_999, 200_000, 200_001, 399_999, 400_000, 400_001])
    def test_continuous_cycle_boundary_lengths(
        self,
        tmp_path: Path,
        n_lines: int,
        readers: tuple[FakeDataReader, FakeTiffReader],
    ) -> None:
        data_root = tmp_path / f"data_{n_lines}"
        save_dir = tmp_path / f"save_{n_lines}"
        data_root.mkdir()
        save_dir.mkdir()
        for dmd in (1, 2):
            _write_dat(data_root, f"acq_DMD{dmd}-CYCLE-000000.dat", n_lines, START_TIME)
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)
        first = _info(table, "first_line")[0]
        last = _info(table, "last_line")[0]

        assert len(first) == int(np.ceil(n_lines / 200_000))
        assert first[0] == 1
        assert last[-1] == n_lines
        np.testing.assert_array_equal(first[1:], last[:-1] + 1)
        assert int(np.sum(last - first + 1)) == n_lines

    def test_continuous_uses_minimum_path_line_count(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_dat(data_root, "acq_DMD1-CYCLE-000000.dat", 250_000, START_TIME)
        _write_dat(data_root, "acq_DMD2-CYCLE-000000.dat", 225_000, START_TIME)
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)

        np.testing.assert_array_equal(_info(table, "last_line")[:, -1], [225_000, 225_000])
        assert int(np.sum(_info(table, "last_line")[0] - _info(table, "first_line")[0] + 1)) == 225_000

    def test_unequal_continuous_source_counts_fail(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_dat(data_root, "acqA_DMD1-CYCLE-000000.dat", 100_000, START_TIME)
        _write_dat(data_root, "acqB_DMD1-CYCLE-000000.dat", 100_000, START_TIME + timedelta(minutes=1))
        _write_dat(data_root, "acqA_DMD2-CYCLE-000000.dat", 100_000, START_TIME)
        _write_references(data_root)
        with pytest.raises(Exception):
            _build(data_root, save_dir, readers)

    def test_aind_dynamic_data_layout(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        dynamic = data_root / "dynamic_data"
        dynamic.mkdir()
        dmd1, dmd2 = _write_triggered(dynamic, 100_000, 100_000)
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)

        assert Path(table["datadr"]) == dynamic
        _assert_filenames(table["filename"], [dmd1, dmd2])
        assert (save_dir / "trial_table.h5").is_file()

    def test_reference_stack_metadata(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 100_000)
        _write_references(data_root)

        table = _build(data_root, save_dir, readers)

        for path_name in ("Path1", "Path2"):
            reference = table["slap2_info"]["ref_stack"][path_name]
            np.testing.assert_array_equal(reference["channels"], [1, 2])
            np.testing.assert_array_equal(reference["Zs"], [0, 1, 2])
            np.testing.assert_array_equal(reference["dmdPixel2SampleTransform"], np.eye(3))
            assert np.asarray(reference["IM"]).shape == (8, 8, 6)
            assert np.asarray(reference["IM"]).dtype == np.uint16

    def test_config1_reference_preferred_when_multiple_references_exist(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 100_000)
        for dmd in (1, 2):
            _touch(data_root / "reference", f"old_DMD{dmd}-REFERENCE.tif")
            _touch(data_root / "reference", f"selected_DMD{dmd}_CONFIG1-REFERENCE.tif")

        table = _build(data_root, save_dir, readers)

        assert set(table["slap2_info"]["ref_stack"]) == {"Path1", "Path2"}
        assert {path.name for path in readers[1].paths} == {
            "selected_DMD1_CONFIG1-REFERENCE.tif",
            "selected_DMD2_CONFIG1-REFERENCE.tif",
        }

    def test_trial_table_h5_is_written_and_round_trips(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        hdf5 = pytest.importorskip(
            "slap2_voltage_extraction.io",
            reason="Python HDF5 translation has not been implemented yet",
        )
        data_root, save_dir = roots
        dmd1, dmd2 = _write_triggered(data_root, [100_000, 120_000], [100_000, 120_000])
        _write_references(data_root)
        _build(data_root, save_dir, readers)

        path = save_dir / "trial_table.h5"
        assert path.is_file(), "trial_table.h5 was not written"
        table = hdf5.load_struct_from_h5(path)
        assert Path(table["datadr"]) == data_root
        assert Path(table["savedr"]) == save_dir
        _assert_filenames(table["filename"], [dmd1, dmd2])
        np.testing.assert_array_equal(_info(table, "first_line").astype(float), [[1, 1], [1, 1]])
        np.testing.assert_array_equal(
            _info(table, "last_line").astype(float), [[100_000, 120_000], [100_000, 120_000]]
        )
        assert table["slap2_info"]["line_range_convention"] == "inclusive"
        assert set(table["slap2_info"]["ref_stack"]) >= {"Path1", "Path2"}

    def test_no_dat_files_error(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_references(data_root)
        with pytest.raises(Exception) as caught:
            _build(data_root, save_dir, readers)
        assert getattr(caught.value, "code", None) == "buildTrialTableSLAP2:NoDatFiles" or (
            "buildTrialTableSLAP2:NoDatFiles" in str(caught.value)
        )

    def test_no_reference_stack_error(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 100_000)
        with pytest.raises(Exception):
            _build(data_root, save_dir, readers)

    def test_ambiguous_config1_reference_stack_error(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 100_000)
        for dmd in (1, 2):
            _touch(data_root / "reference", f"a_DMD{dmd}_CONFIG1-REFERENCE.tif")
            _touch(data_root / "reference", f"b_DMD{dmd}_CONFIG1-REFERENCE.tif")
        with pytest.raises(Exception):
            _build(data_root, save_dir, readers)

    def test_unaligned_dmds_error(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 150_000)
        _write_references(data_root)
        with pytest.raises(Exception):
            _build(data_root, save_dir, readers)

    def test_triggered_alignment_difference_below_threshold_succeeds(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 101_999)
        _write_references(data_root)
        table = _build(data_root, save_dir, readers)
        np.testing.assert_array_equal(_info(table, "last_line")[:, 0], [100_000, 100_000])

    def test_triggered_alignment_difference_at_threshold_fails(
        self, roots: tuple[Path, Path], readers: tuple[FakeDataReader, FakeTiffReader]
    ) -> None:
        data_root, save_dir = roots
        _write_triggered(data_root, 100_000, 102_000)
        _write_references(data_root)
        with pytest.raises(Exception):
            _build(data_root, save_dir, readers)
