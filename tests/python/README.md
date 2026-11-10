# Python characterization tests

This directory is the Python counterpart of `tests/matlab`. The tests are written before the Python production implementation so that translation can proceed test-first.

## Contract policy

- Every MATLAB test has a named Python counterpart. Duplicate MATLAB regressions remain duplicated intentionally until parity is established.
- Numerical values, shapes, dtypes, tolerances, metadata, file schemas, and failure behavior follow the MATLAB R2023b characterization suite.
- MATLAB 1-based scientific identifiers and inclusive line ranges remain 1-based in public metadata. Python array indexing remains 0-based internally.
- MATLAB `single` and `double` map to NumPy `float32` and `float64`.
- MATLAB structs map to nested dictionaries unless a public result object is explicitly more suitable.
- MATLAB error identifiers map to domain exceptions exposing a `code` attribute with the original identifier. During early implementation, matching the identifier in the exception text is also accepted.
- HDF5 array shapes follow the existing MATLAB file contract rather than silently adopting different C-order shapes.

## Intended package API

The tests target a package named `slap2_voltage_extraction` with snake-case Python APIs:

- `parameters`: `set_params`, `asap7_params`, `asap8_params`
- `baseline`: `compute_voltage_f0`
- `normalization`: `compute_voltage_dff`
- `motion`: motion-default, validation, censoring, and expansion functions
- `trace`: `Trace`, `TracePixel`
- `io.hdf5`: `save_struct_to_h5`, `load_struct_from_h5`
- `io.tiff`: `ScanImageTiffReader` and wrapper functions
- `trial_table`: `build_trial_table_slap2`
- `voltage`: `voltage`

Until those modules exist, each translated module is skipped with an explicit reason rather than failing during collection. Once a production module is added, its corresponding tests immediately become active.

## Running

From the repository root:

    python -m pytest tests/python

## Translation critique

Some MATLAB tests inspect source strings or MATLAB path mechanics. Their Python counterparts prefer behavioral tests where possible. A small number of architecture tests remain, but they assert Python-relevant properties such as importability, lazy executor creation, output cleanup, and the public format version. These intentional adaptations are documented in the relevant test modules.
