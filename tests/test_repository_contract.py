from __future__ import annotations

import importlib
import multiprocessing
import threading


def test_required_public_modules_and_symbols_import() -> None:
    """The installed package exposes its documented API and subpackages."""

    contracts = {
        "slap2_voltage_extraction": (
            "FORMAT_VERSION",
            "voltage",
            "process_voltage",
            "build_trial_table_slap2",
            "preview_motion_censor",
        ),
        "slap2_voltage_extraction.source_extraction": (
            "motion_censor_defaults",
            "validate_motion_censor_params",
            "compute_motion_censor",
            "expand_motion_mask_to_lines",
            "compute_voltage_f0",
            "compute_voltage_dff",
        ),
        "slap2_voltage_extraction.parameters.set_params": ("set_params",),
        "slap2_voltage_extraction.trace": ("Trace", "TracePixel"),
        "slap2_voltage_extraction.io": (
            "load_struct_from_h5",
            "save_struct_to_h5",
        ),
    }
    for module_name, names in contracts.items():
        module = importlib.import_module(module_name)
        for name in names:
            assert hasattr(module, name), f"{module_name} must publicly expose {name}"


def test_repeated_import_is_idempotent() -> None:
    first = importlib.import_module("slap2_voltage_extraction")
    second = importlib.import_module("slap2_voltage_extraction")
    assert first is second


def test_trace_classes_resolve_from_package_submodule() -> None:
    trace = importlib.import_module("slap2_voltage_extraction.trace")
    assert isinstance(trace.Trace, type)
    assert isinstance(trace.TracePixel, type)
    assert trace.Trace.__module__.startswith("slap2_voltage_extraction.trace")
    assert trace.TracePixel.__module__.startswith("slap2_voltage_extraction.trace")


def test_importing_trace_does_not_create_a_worker_pool() -> None:
    threads_before = set(threading.enumerate())
    children_before = set(multiprocessing.active_children())
    trace = importlib.import_module("slap2_voltage_extraction.trace")
    importlib.reload(trace)
    assert set(threading.enumerate()) == threads_before
    assert set(multiprocessing.active_children()) == children_before


def test_package_exposes_format_version() -> None:
    package = importlib.import_module("slap2_voltage_extraction")
    assert callable(package.voltage)
    assert package.FORMAT_VERSION == "0.2.3"
