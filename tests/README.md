# Python unit tests

This suite validates the installable `slap2_voltage_extraction` package.

## Contract policy

- Scientific values, meaningful axes, dtypes, tolerances, failure behavior, and serialized schemas are regression-tested.
- Internals use snake_case, zero-based indices, half-open ranges, one-dimensional vectors, and C-order arrays.
- Legacy conversions occur only at explicit boundaries. Trial tables retain one-based inclusive `first_line` and `last_line` values, and HDF5 output retains established names, dimensions, orientations, and layout markers.
- NumPy `float32` and `float64` represent the supported single- and double-precision modes.
- Structured data uses nested dictionaries unless another result type is explicitly appropriate.
- Domain exceptions expose stable identifiers through a `code` attribute.

## Package API under test

Primary entry points are imported from `slap2_voltage_extraction`:

- `voltage`
- `process_voltage`
- `build_trial_table_slap2`
- `preview_motion_censor`

Supporting APIs are imported from package submodules:

- `slap2_voltage_extraction.source_extraction`
- `slap2_voltage_extraction.parameters`
- `slap2_voltage_extraction.io`
- `slap2_voltage_extraction.motion`
- `slap2_voltage_extraction.trace`
- `slap2_voltage_extraction.presets`

Tests use dependency injection and Python-native synthetic readers.

## Running

From the repository root:

```bash
uv run pytest
```

These are unit and contract tests. Real SLAP2 readers, representative sessions, thread safety, memory use, and performance are reserved for integration testing.
