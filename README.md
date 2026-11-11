# SLAP2 Voltage Extraction

SLAP2 Voltage Extraction is a Python package for extracting integration-ROI voltage signals from SLAP2 recordings. It reads a GIAnT-compatible `trial_table.h5`, extracts native-rate fluorescence, computes baseline fluorescence (`f0`) and polarity-corrected voltage `dff`, and writes a GIAnT-style `VoltageSummary.h5`.

Image motion correction is outside this package's scope. Optional motion censoring uses recorded online offsets to mark samples acquired while correction was off target and sets their `f0` and `dff` values to NaN.

## Installation

Python 3.13 and 3.14 are supported.

With uv:

```bash
uv sync --group dev
```

With pip:

```bash
python -m pip install .
```

The low-level SLAP2 binary reader remains an external dependency. Public functions also accept injected reader factories for testing and specialized deployments.

## Python API

```python
from slap2_voltage_extraction import process_voltage, voltage

summary = voltage("/path/to/trial_table.h5", params)

summary, trial_table, params = process_voltage(
    "/path/to/slap2/session",
    "/path/to/output",
)
```

The package root exposes:

- `voltage`
- `process_voltage`
- `build_trial_table_slap2`
- `preview_motion_censor`
- `FORMAT_VERSION`

Supporting functionality is organized under `slap2_voltage_extraction.io`, `motion`, `parameters`, `presets`, `source_extraction`, and `trace`.

## Data conventions

Python internals use snake_case, zero-based indices, half-open ranges, one-dimensional time-series vectors, and C-order arrays.

Existing interchange formats retain their established compatibility contracts:

- `trial_table.h5` stores `first_line` and `last_line` as one-based inclusive values.
- HDF5 field names, dtypes, dimensions, axis orientations, and `row_major=0` remain unchanged.
- Serialized ROI identifiers remain one-based where required by existing consumers.
- Domain exceptions expose stable identifiers through `Slap2VoltageError.code`.

For example, convert a stored line range to a Python slice with:

```python
line_slice = slice(first_line - 1, last_line)
```

Several implementation details intentionally preserve the pipeline's MATLAB lineage where changing them would alter established results or interchange behavior: temporal bins, smoothing widths, and trial boundaries use half-up or half-away-from-zero rounding instead of Python's ties-to-even `round`; centered moving windows are forced to odd, data-bounded lengths; legacy motion readers, raw sample offsets, trial bounds, and serialized ROI identifiers retain one-based conventions at their boundaries; trace matrices are flattened in column-major acquisition order; transposed ROI masks and ScanImage TIFF axes are normalized to their established orientation; the raw-data `int16` minimum sentinel maps to zero; finite numeric motion flags retain zero/nonzero logical coercion; and HDF5 files retain `row_major=0`. Inline comments mark each of these lineage-dependent behaviors so they are not mistaken for accidental Python irregularities.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for package structure and compatibility boundaries.

## Testing

Run the complete unit and contract suite with:

```bash
uv run pytest
```

Tests use deterministic synthetic readers and files. Real-reader thread safety, performance, memory use, and representative full-session behavior belong in integration testing.

## Validation

The utilities under `validation/` inspect output structure, axis conventions, numerical consistency, and parity with established benchmark files without loading complete recordings into memory.
