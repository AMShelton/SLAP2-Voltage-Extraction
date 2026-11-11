"""Semantic Python counterpart of MATLAB ``setup.m``.

Package installation and path configuration are handled by ``pyproject.toml``
and uv. Calling :func:`setup_environment` verifies the vendored trace kernel.
"""

from __future__ import annotations


def setup_environment() -> None:
    """Verify that required directly translated modules can be imported."""

    from dependencies.slap2_trace import Trace, TracePixel

    if not isinstance(Trace, type) or not isinstance(TracePixel, type):
        raise ImportError("Voltage:MissingVendoredTraceKernel")


__all__ = ["setup_environment"]