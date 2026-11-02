# Tests

This directory contains synthetic MATLAB characterization tests for the current implementation. They define contracts that can later be copied to the Python implementation. They are not yet a substitute for golden-session regression against real SLAP2 recordings.

## Requirements

- MATLAB R2023b Update 7 on Linux is the characterization reference runtime.
- Run from the repository root.
- No raw SLAP2 session is required for the synthetic suite.
- Parallel Computing Toolbox is not needed unless parallel tests are added.

Run the complete suite in a fresh MATLAB process:

```matlab
clear classes
setup
results = runtests('tests');
table(results)
assertSuccess(results)
```

From a cloned checkout on a workstation with Git and MATLAB on `PATH`, update
the `python_translation` branch and run the same suite with:

```bash
bash run_matlab_tests.sh
```

`clear classes` matters when rerunning tests interactively because MATLAB can cache package classes after paths change. The suite uses one shared `slap2.util.MultiDataFiles` test double under `tests/fakes`; production `Trace` and `TracePixel` remain under test.

## Characterization sections

- `TestBuildTrialTableSLAP2.m`: triggered and continuous-CYCLE trial-table construction, mismatch repair, AIND layout, references, HDF5 output, and expected failures. External SLAP2/TIFF parsing is replaced by test doubles.
- `TestVoltageParameters.m`: defaults, overrides, coercion, JSON/MAT input, ASAP7/ASAP8 presets, and validation.
- `TestComputeVoltageF0.m`: static and robust baselines, float32 staging, interpolation, moving medians, fallback values, shape, precision, and metadata.
- `TestComputeVoltageDFF.m`: indicator polarity, aliases, fallback baselines, float32 arithmetic, shape, precision, metadata, and errors.
- `TestHdf5StructIO.m`: recursive struct round trips, text/cell semantics, dimensions, overwrite behavior, legacy field normalization, and errors.
- `TestScanImageTiffIO.m`: generated uncompressed TIFFs, orientation, stacks, wrappers, metadata, lifecycle, fallback, and invalid input.
- `TestTracePixel.m`: real temporary `int16` files, cycle/offset addressing, sentinel handling, loading, weighting kernels, and empty arrays.
- `TestTrace.m`: production raster/integration mapping, superpixel grouping, channel offsets, z filtering, selection counts, and processing.
- `TestVoltage.m`: public pipeline orchestration with tiny trial-table HDF5 and raw `int16` files. It uses the shared fake only for `MultiDataFiles` metadata parsing and executes production `Trace`, `TracePixel`, F0, dF/F, and HDF5 code.
- `TestRepositorySetup.m`: path setup, dependency resolution, and idempotence.

The older lowercase `test_*.m` files remain temporarily as complementary regression/contract tests. Some behavior overlaps with the class-based suite; remove them only after the new suite passes on the MATLAB workstation and their unique assertions have been compared.

Run one class while diagnosing a failure:

```matlab
clear classes
setup
results = runtests('tests/TestTracePixel.m');
table(results)
```

## Test-double boundary

Dummy data replaces only unavailable external parsing or metadata assembly. Low-level numerical and binary algorithms use production code. In particular, `TestVoltage` is not an end-to-end validation of the external SLAP2 reader; that boundary must be covered by the future real-session test.

The next milestone is a golden-session integration test that runs `Voltage.m` against a representative Neuron2/Neuron5 session and validates the complete HDF5 output against approved reference values.
