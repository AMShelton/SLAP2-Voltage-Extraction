from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def assert_error_code(expected: str) -> Callable[[BaseException], None]:
    """Return an assertion that accepts a domain error code or its text form."""

    def check(exc: BaseException) -> None:
        code = getattr(exc, "code", None)
        assert code == expected or expected in str(exc), (
            f"Expected error code {expected!r}, got code={code!r}, text={str(exc)!r}"
        )

    return check


@pytest.fixture
def write_int16(tmp_path: Path) -> Callable[[str, Any], Path]:
    """Write native little-endian int16 values exactly as the MATLAB fixtures do."""

    def write(name: str, values: Any) -> Path:
        path = tmp_path / name
        np.asarray(values, dtype="<i2").tofile(path)
        return path

    return write


@pytest.fixture
def default_voltage_overrides() -> dict[str, Any]:
    return {
        "outputFilename": "result.h5",
        "overwrite": False,
        "useParallel": False,
        "precision": "single",
        "indicatorName": "test",
        "indicatorDirection": "increases",
        "f0Method": "static",
        "f0Percentile": 50,
        "h5ChunkSamples": 16,
        "h5Deflate": 0,
    }
