# Architecture

## Package layout

Production code uses a conventional `src` layout under `src/slap2_voltage_extraction/`.

- `voltage.py`: main extraction engine
- `process_voltage.py`: trial-table and extraction orchestration
- `build_trial_table_slap2.py`: trial-table construction
- `preview_motion_censor.py`: motion-censor diagnostics
- `source_extraction/`: motion, baseline, and dF/F algorithms
- `trace/`: trace and pixel extraction kernels
- `io/`: HDF5 and TIFF utilities
- `parameters/`: defaults, loading, and validation
- `presets/`: indicator presets
- `motion/`: online-motion reader compatibility
- `exceptions.py`: stable domain exception type

The package root exposes only the primary workflow entry points and format version. Supporting APIs remain available from their focused subpackages.

## Internal conventions

Internal code uses:

- snake_case names;
- zero-based indices;
- half-open ranges;
- one-dimensional time-series vectors;
- C-order arrays by default;
- `Path` for filesystem paths;
- injected reader factories for unit testing.

## Compatibility boundaries

Some file formats predate this package and deliberately retain conventions that differ from Python internals:

- `trial_table.h5` stores `first_line` and `last_line` as one-based inclusive values.
- HDF5 field names, dtypes, dimensions, axis orientations, and `row_major=0` are stable contracts.
- Serialized ROI identifiers remain one-based where required by existing consumers.
- Stable domain error identifiers are exposed through `Slap2VoltageError.code`.

Conversions occur only at explicit reader and serialization boundaries. These contracts must not be changed as part of internal refactoring.

## External reader

The full SLAP2 binary reader is external. Normal operation imports a compatible `slap2` reader when no reader factory is supplied. The package's `trace` subpackage provides the pinned voltage trace kernel, not the complete acquisition reader.

## Testing boundaries

`tests/` contains deterministic unit and contract tests. Real SLAP2 files and readers, thread safety, memory use, performance, and full-session behavior should be covered by a separate integration suite.
