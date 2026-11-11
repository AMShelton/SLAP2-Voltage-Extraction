# Python characterization tests

This directory is the Python counterpart of `tests/matlab`. The tests are written before the Python production implementation so that translation can proceed test-first.

## Contract policy

- Every MATLAB scientific and externally observable behavioral condition has a Python counterpart. MATLAB-only source/path checks are replaced by executable Python behavior where observable; currently unobservable contracts are listed in `TRANSLATION_REVIEW.md` rather than represented by tests that can only `xfail`.
- Numerical results, meaningful axes, dtypes, tolerances, scientific metadata, file schemas, and failure behavior follow the MATLAB R2023b characterization suite. Shapes that encode only MATLAB row/column-vector mechanics are intentionally canonicalized to one-dimensional Python vectors.
- Canonical internal vectors are one-dimensional NumPy arrays. Internal indices are zero-based, ranges are half-open, and newly created arrays use C order by default.
- Functions that conceptually consume one time series accept one-dimensional vectors (with row/column compatibility inputs canonicalized where useful) and reject ambiguous non-vector matrices rather than implicitly linearizing them.
- Python configuration and result metadata use snake_case names. Conversion to legacy names, one-based identifiers, inclusive ranges, MATLAB-oriented shapes, or column-major layout occurs only at an explicit legacy boundary.
- Existing serialized schemas are compatibility boundaries even when this repository produces them: they retain their legacy field names, one-based inclusive indexing, shapes, axis orientation, and storage-layout markers exactly. In particular, `build_trial_table_slap2` uses zero-based/half-open values only while computing internally, then writes `first_line` and `last_line` as the repository's established one-based, inclusive trial-table contract.
- MATLAB `single` and `double` map to NumPy `float32` and `float64`.
- MATLAB structs map to nested dictionaries unless a public result object is explicitly more suitable.
- MATLAB error identifiers map to domain exceptions exposing a `code` attribute with the original identifier. During early implementation, matching the identifier in the exception text is also accepted.
- HDF5 array shapes follow the existing MATLAB file contract rather than silently adopting Python-internal shapes.

## Repository API

The tests target the translated files in their actual repository locations:

- `voltage.py`: `voltage`
- `process_voltage.py`: `process_voltage`
- `build_trial_table_slap2.py`: `build_trial_table_slap2`
- `source_extraction`: F0, dF/F, motion-default, validation, censoring, and expansion functions
- `dependencies.gui.set_params`: `set_params`
- `dependencies.slap2_trace`: `Trace`, `TracePixel`
- `dependencies.io`: HDF5 and TIFF readers/writers
- `presets`: `asap7_params`, `asap8_params`

Until those modules exist, each translated module is skipped with an explicit reason rather than failing during collection. Once a production module is added, its corresponding tests immediately become active.

## Running

From the repository root:

    python -m pytest tests/python

## Translation critique

Some MATLAB tests inspect source strings or MATLAB path mechanics. Their Python counterparts use executable behavioral tests where the corresponding behavior is observable, such as importability, absence of eager worker creation, concrete output-cleanup paths, and the public format version. Unexecutable placeholders are not counted as unit tests; implementation seams needed for additional behavioral checks are documented in the translation review.
