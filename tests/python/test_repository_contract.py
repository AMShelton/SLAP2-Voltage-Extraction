from __future__ import annotations

import importlib
import multiprocessing
import threading

import pytest

package = pytest.importorskip(
    "slap2_voltage_extraction",
    reason="Python package translation has not been implemented yet",
)


def test_setup_replacement_imports_package_and_resolves_dependencies() -> None:
    """Python imports replace MATLAB setup and path mutation."""
    assert importlib.import_module("slap2_voltage_extraction") is package
    trace = importlib.import_module("slap2_voltage_extraction.trace")
    assert trace.Trace is not None
    assert trace.TracePixel is not None


def test_required_public_modules_and_symbols_import() -> None:
    """Python replacement for the required MATLAB repository-file list."""
    contracts = {
        "slap2_voltage_extraction": ("FORMAT_VERSION",),
        "slap2_voltage_extraction.trial_table": ("build_trial_table_slap2",),
        "slap2_voltage_extraction.motion": (
            "motion_censor_defaults",
            "validate_motion_censor_params",
            "compute_motion_censor",
            "expand_motion_mask_to_lines",
        ),
        "slap2_voltage_extraction.baseline": ("compute_voltage_f0",),
        "slap2_voltage_extraction.normalization": ("compute_voltage_dff",),
        "slap2_voltage_extraction.parameters": ("set_params",),
        "slap2_voltage_extraction.trace": ("Trace", "TracePixel"),
        "slap2_voltage_extraction.io.hdf5": ("load_struct_from_h5", "save_struct_to_h5"),
    }
    for module_name, names in contracts.items():
        module = importlib.import_module(module_name)
        for name in names:
            assert hasattr(module, name), f"{module_name} must publicly expose {name}"


def test_repeated_import_is_idempotent() -> None:
    """Importing replaces MATLAB's setup function and must require no path mutation."""
    first = importlib.import_module("slap2_voltage_extraction")
    second = importlib.import_module("slap2_voltage_extraction")
    assert first is second
    assert first is package


def test_trace_classes_resolve_from_public_module() -> None:
    """Python replacement for vendored MATLAB trace-package path resolution."""
    trace = importlib.import_module("slap2_voltage_extraction.trace")
    assert isinstance(trace.Trace, type)
    assert isinstance(trace.TracePixel, type)
    assert trace.Trace.__module__.startswith("slap2_voltage_extraction")
    assert trace.TracePixel.__module__.startswith("slap2_voltage_extraction")


def test_importing_trace_does_not_create_a_worker_pool() -> None:
    """Python behavior contract replacing the MATLAB-specific MOST pool check."""
    threads_before = set(threading.enumerate())
    children_before = set(multiprocessing.active_children())
    trace = importlib.import_module("slap2_voltage_extraction.trace")
    importlib.reload(trace)
    assert set(threading.enumerate()) == threads_before
    assert set(multiprocessing.active_children()) == children_before


def test_voltage_orchestrator_bootstraps_through_import_and_exposes_format_version() -> None:
    """Behavioral import contract replacing MATLAB bootstrap source inspection."""
    voltage_module = importlib.import_module("slap2_voltage_extraction.voltage")
    assert callable(voltage_module.voltage)
    assert package.FORMAT_VERSION == "0.2.3"
    assert isinstance(package.FORMAT_VERSION, str)


@pytest.mark.xfail(
    strict=True,
    reason="Output cleanup cannot be exercised until the Python voltage orchestrator accepts injectable failing dependencies",
)
def test_voltage_removes_partial_output_after_failure() -> None:
    """Python replacement for the MATLAB cleanup source-string assertion."""
    voltage_module = importlib.import_module("slap2_voltage_extraction.voltage")
    exercise = getattr(voltage_module, "_test_partial_output_cleanup", None)
    assert exercise is not None
    assert exercise() is True
