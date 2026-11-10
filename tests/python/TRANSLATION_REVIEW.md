# MATLAB-to-Python test translation review

This review records the test-by-test decisions made while translating the MATLAB characterization suite. The Python files are intentionally organized by production responsibility rather than by MATLAB test-framework style.

## Parameter tests

Source: `TestVoltageParameters.m`
Target: `test_voltage_parameters.py`

- **Examined behavior:** complete defaults, unknown-field preservation, MATLAB-style rounding, logical coercion, JSON text/files, MAT presets, ASAP presets, and invalid input/choice/range failures.
- **Translation caveats:** Python's built-in `round` uses ties-to-even, unlike MATLAB's relevant behavior; production must use explicit half-away-from-zero logic. Python booleans are subclasses of integers, so validation must reject accidental broad truthiness. MAT support requires SciPy and must distinguish standard variable names from a single custom struct variable.
- **Post-translation critique:** defaults are compared as one exact dictionary so newly added parameters cannot silently escape characterization. Invalid generic MATLAB `MException` cases remain broad Python exception assertions until the implementation defines a stable exception hierarchy.

## F0 tests

Sources: `TestComputeVoltageF0.m`, `test_computeVoltageF0.m`
Target: `test_compute_voltage_f0.py`

- **Examined behavior:** finite-only percentiles, row/column preservation, matrix flattening, precision, fallback values, empty early return, robust binning/interpolation/moving median, partial bins, defaults, and validation.
- **Translation caveats:** NumPy defaults to C-order; MATLAB flattening must use Fortran order. Percentile interpolation and moving-window endpoint behavior must match MATLAB exactly. Empty input deliberately bypasses sample-rate validation.
- **Post-translation critique:** exact comparisons are used for deterministic values and `rtol=0` for MATLAB absolute tolerances. Legacy duplicate tests remain to retain one-to-one traceability.

## dF/F tests

Sources: `TestComputeVoltageDFF.m`, `test_computeVoltageDFF.m`
Target: `test_compute_voltage_dff.py`

- **Examined behavior:** ASAP polarity, all aliases, normalization, explicit precedence, fallback baseline, NaN propagation, N-D shape, precision, optional arguments, exact shape rejection, and error conditions.
- **Translation caveats:** NumPy broadcasting must be prohibited because MATLAB requires exact sizes. Scalar NumPy outputs still need the requested dtype. Original direction text must survive in metadata while normalized text drives matching.
- **Post-translation critique:** both formula metadata and numerical output are checked. Unknown precision intentionally falls back to float32 because that is characterized MATLAB behavior, even though parameter validation rejects it upstream.

## HDF5 tests

Sources: `TestHdf5StructIO.m`, `test_trial_table_roundtrip.m`
Target: `test_hdf5_struct_io.py`

- **Examined behavior:** recursive numeric/text/cell round trips, exact shapes/dtypes, logical-to-int8 conversion, layout marker, skipped empties, overwrite, legacy normalization, unsupported values, and missing files.
- **Translation caveats:** Python lists are ambiguous between MATLAB cells and numeric arrays, so object arrays explicitly represent cells. HDF5 storage must preserve MATLAB-facing dimensions and `row_major=0`; it must not silently transpose to a new Python-only schema.
- **Post-translation critique:** Fortran-order fixture construction prevents accidental value-order drift. The standalone trial-table regression remains duplicated intentionally.

## TIFF tests

Source: `TestScanImageTiffIO.m`
Target: `test_scanimage_tiff_io.py`

- **Examined behavior:** lifecycle, orientation, page stacks, shape descriptors, descriptions, wrappers, validated legacy trailers, fallback warnings, and invalid inputs.
- **Translation caveats:** fixture writers may add benign TIFF descriptions, so tests retain semantic-empty checks. Legacy metadata uses terminal little-endian uint32 length. The reader's unusual stride descriptor is part of the existing contract rather than NumPy's byte-stride convention.
- **Post-translation critique:** API identity is adapted to `ScanImageTiffReader (pure Python)` instead of falsely retaining `pure MATLAB`; all data/metadata behavior remains equivalent.

## TracePixel tests

Source: `TestTracePixel.m`
Target: `test_trace_pixel.py`

- **Examined behavior:** cycle/file byte offsets, caching, exact int16 sentinel replacement, analytical weights, pre-normalization aggregation, and empty arrays.
- **Translation caveats:** files are explicitly little-endian int16. Public line IDs remain 1-based while Python masks/indexing are 0-based. Processing must clear loaded data to preserve the merged memory contract.
- **Post-translation critique:** state, dtype, shape, sampled and unsampled values are all checked. The proposed Python `process` return omits MATLAB's value-class object return because Python mutates the object in place.

## Trace tests

Source: `TestTrace.m`
Target: `test_trace.py`

- **Examined behavior:** constructor identity/defaults, pixel-to-superpixel mapping, logical map equivalence, validation, unknown pixels, idempotent selection, load/process delegation, and memory release.
- **Translation caveats:** fake metadata uses snake-case Python fields but preserves MATLAB values and 1-based identifiers. Logical mask flattening is explicitly Fortran-order. Object identity uses Python `is`.
- **Post-translation critique:** exact byte offsets and selected/full superpixel counts remain asserted. This intentionally constrains the implementation rather than accepting a superficially equivalent aggregate.

## Voltage orchestration tests

Sources: `TestVoltage.m`, `test_voltage_roi_discovery_contract.m`
Target: `test_voltage.py`

- **Examined behavior:** single-ROI extraction, public summary, HDF5 schema and attributes, directory resolution, overwrite safety, cleanup, no-ROI handling, missing input, ROI classification, legacy masks, and lazy parallel startup.
- **Translation caveats:** the fake reader is injected at the module boundary. HDF5 dimensions remain `(1, 1, samples)`. MATLAB source-string tests are not copied literally because Python formatting is not behavior.
- **Post-translation critique:** runtime tests replace source inspection wherever an observable contract exists. Two contracts—legacy dual-mask Trace construction and lazy executor creation—are strict expected failures until the production API exposes injectable factories. They must be converted to spy-based behavioral tests during implementation.

## Trial-table tests

Source: `TestBuildTrialTableSLAP2.m`
Target: `test_trial_table.py`

- **Examined behavior:** triggered repair, continuous inclusive chunking and boundaries, shorter-path truncation, source ambiguity, AIND layout, reference selection/metadata, HDF5 round trip, missing inputs, and alignment threshold.
- **Translation caveats:** public line ranges remain 1-based and inclusive. Python fixtures use UTC Unix timestamps instead of MATLAB datenums; this preserves elapsed-time behavior while avoiding a MATLAB-only representation. Fake DAT/TIFF readers are explicit dependencies rather than import shadowing.
- **Post-translation critique:** ignored later CYCLE files are verified through the fake reader's call history, strengthening the MATLAB fixture's implicit trap. Chunk coverage and adjacency are both asserted to catch off-by-one errors.

## Motion-censor tests

Source: `test_motion_censor.m`
Target: `test_motion_censor.py`

- **Examined behavior:** defaults, parameter wiring, stationary/drift behavior, transient padding, gap merging, hard cap, nonfinite offsets, initial discard, line expansion, F0 isolation, and all-censored safety.
- **Translation caveats:** MATLAB sample numbers in expected masks are converted back to 1-based values for direct comparison. Random data uses a deterministic NumPy generator; exact random samples are not a cross-language contract, but the robust outcome is.
- **Post-translation critique:** the dF/F tuple is explicitly unpacked and dtype/NaN masks are checked. Source wiring inspection is replaced by public API importability.

## Repository contracts

Sources: `TestRepositorySetup.m`, `test_repository_layout.m`
Target: `test_repository_contract.py`

- **Examined behavior:** dependencies resolve, setup is idempotent, trace imports have no eager pool side effect, format version is public, and failed output is removed.
- **Translation caveats:** Python packages should not mutate `sys.path`, so repeated imports replace MATLAB path-entry counting. MATLAB-specific MOST and `gcp` strings have no Python counterpart.
- **Post-translation critique:** import and worker-side-effect checks are behavioral. Partial-output cleanup is a strict expected failure until a dependency-injection seam exists; the end-to-end shape/no-ROI tests already cover two concrete cleanup paths.

## Open implementation decisions

1. Define domain exception classes with stable MATLAB-compatible `code` values.
2. Preserve camel-case metadata/HDF5 keys for file compatibility while using snake-case Python function and attribute names.
3. Expose injectable `Trace` and executor factories in the voltage orchestrator so the two strict expected-failure contracts become observable tests.
4. Decide whether TIFF support uses a dependency or a pure-Python parser; behavior, not implementation choice, is constrained.
5. Keep public line/trial/ROI identifiers 1-based at file boundaries and convert only inside algorithms.
