from __future__ import annotations

import importlib
import multiprocessing
import threading

def test_setup_replacement_resolves_dependencies() -> None:
    """Python imports replace MATLAB setup and path mutation."""
    setup = importlib.import_module("setup_environment")
    setup.setup_environment()
    trace = importlib.import_module("dependencies.slap2_trace")
    assert trace.Trace is not None
    assert trace.TracePixel is not None


def test_required_public_modules_and_symbols_import() -> None:
    """Python replacement for the required MATLAB repository-file list."""
    contracts = {
        "voltage": ("FORMAT_VERSION", "voltage"),
        "process_voltage": ("process_voltage",),
        "build_trial_table_slap2": ("build_trial_table_slap2",),
        "source_extraction": (
            "motion_censor_defaults",
            "validate_motion_censor_params",
            "compute_motion_censor",
            "expand_motion_mask_to_lines",
            "compute_voltage_f0",
            "compute_voltage_dff",
        ),
        "dependencies.gui.set_params": ("set_params",),
        "dependencies.slap2_trace": ("Trace", "TracePixel"),
        "dependencies.io": ("load_struct_from_h5", "save_struct_to_h5"),
    }
    for module_name, names in contracts.items():
        module = importlib.import_module(module_name)
        for name in names:
            assert hasattr(module, name), f"{module_name} must publicly expose {name}"


def test_repeated_import_is_idempotent() -> None:
    """Importing replaces MATLAB's setup function and must require no path mutation."""
    first = importlib.import_module("voltage")
    second = importlib.import_module("voltage")
    assert first is second


def test_trace_classes_resolve_from_public_module() -> None:
    """Python replacement for vendored MATLAB trace-package path resolution."""
    trace = importlib.import_module("dependencies.slap2_trace")
    assert isinstance(trace.Trace, type)
    assert isinstance(trace.TracePixel, type)
    assert trace.Trace.__module__.startswith("dependencies.slap2_trace")
    assert trace.TracePixel.__module__.startswith("dependencies.slap2_trace")


def test_importing_trace_does_not_create_a_worker_pool() -> None:
    """Python behavior contract replacing the MATLAB-specific MOST pool check."""
    threads_before = set(threading.enumerate())
    children_before = set(multiprocessing.active_children())
    trace = importlib.import_module("dependencies.slap2_trace")
    importlib.reload(trace)
    assert set(threading.enumerate()) == threads_before
    assert set(multiprocessing.active_children()) == children_before


def test_voltage_orchestrator_bootstraps_through_import_and_exposes_format_version() -> None:
    """Behavioral import contract replacing MATLAB bootstrap source inspection."""
    voltage_module = importlib.import_module("voltage")
    assert callable(voltage_module.voltage)
    assert voltage_module.FORMAT_VERSION == "0.2.3"
    assert isinstance(voltage_module.FORMAT_VERSION, str)
