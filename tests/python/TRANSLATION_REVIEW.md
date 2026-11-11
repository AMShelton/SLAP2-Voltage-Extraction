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
- **Translation caveats:** canonical internal signals are one-dimensional, C-order NumPy arrays. Any MATLAB column-vector or Fortran-order conversion belongs at a characterized legacy input/output boundary. Percentile interpolation and moving-window endpoint behavior must match MATLAB exactly. Empty input deliberately bypasses sample-rate validation.
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
- **Post-translation critique:** Fortran-order fixture construction is limited to serialized-schema compatibility tests and prevents accidental value-order drift at that boundary. It is not an internal array-layout requirement. The standalone trial-table regression remains duplicated intentionally.

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
- **Translation caveats:** files are explicitly little-endian int16. Internal line IDs, masks, and slices are zero-based and half-open; conversion to one-based IDs occurs only when reading or writing a legacy contract. Processing must clear loaded data to preserve the merged memory contract.
- **Post-translation critique:** state, dtype, shape, sampled and unsampled values are all checked. The proposed Python `process` return omits MATLAB's value-class object return because Python mutates the object in place.

## Trace tests

Source: `TestTrace.m`
Target: `test_trace.py`

- **Examined behavior:** constructor identity/defaults, pixel-to-superpixel mapping, logical map equivalence, validation, unknown pixels, idempotent selection, load/process delegation, and memory release.
- **Translation caveats:** Python config/result metadata uses snake_case, internal identifiers are zero-based, and logical masks are canonical one-dimensional C-order arrays. One-based identifiers, legacy names, and Fortran linearization are retained only where a serialized or external MATLAB contract requires them. Object identity uses Python `is`.
- **Post-translation critique:** exact byte offsets and selected/full superpixel counts remain asserted. This intentionally constrains the implementation rather than accepting a superficially equivalent aggregate.

## Voltage orchestration tests

Sources: `TestVoltage.m`, `test_voltage_roi_discovery_contract.m`
Target: `test_voltage.py`

- **Examined behavior:** single-ROI extraction, public summary, HDF5 schema and attributes, directory resolution, overwrite safety, cleanup, no-ROI handling, missing input, ROI classification, legacy masks, and lazy parallel startup.
- **Translation caveats:** the fake reader is injected at the module boundary. HDF5 dimensions remain `(1, 1, samples)`. MATLAB source-string tests are not copied literally because Python formatting is not behavior.
- **Post-translation critique:** runtime tests replace source inspection wherever an observable contract exists. Legacy dual-mask Trace construction and lazy executor creation need injectable factories before they can become meaningful spy-based behavioral tests; placeholder expected failures are intentionally excluded from the executable suite.

## Trial-table tests

Source: `TestBuildTrialTableSLAP2.m`
Target: `test_trial_table.py`

- **Examined behavior:** triggered repair, continuous inclusive chunking and boundaries, shorter-path truncation, source ambiguity, AIND layout, reference selection/metadata, HDF5 round trip, missing inputs, and alignment threshold.
- **Translation caveats:** this repository generates `trial_table.h5`, but the generated file is also its established GIAnT-compatible public interchange contract. Its `first_line` and `last_line` fields therefore remain one-based and inclusive, with legacy keys and shapes unchanged. Trial construction may use zero-based, half-open values internally but must convert when creating the returned table and serialized file. Python fixtures use UTC Unix timestamps instead of MATLAB datenums; this preserves elapsed-time behavior while avoiding a MATLAB-only representation. Fake DAT/TIFF readers are explicit dependencies rather than import shadowing.
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
- **Post-translation critique:** import and worker-side-effect checks are behavioral. The end-to-end shape/no-ROI tests cover two concrete cleanup paths; broader partial-output cleanup needs an injectable failing dependency before it can be tested meaningfully and is not represented by a placeholder expected failure.

## Open implementation decisions

1. Define domain exception classes with stable MATLAB-compatible `code` values.
2. Use snake_case for Python configuration and result metadata; preserve legacy metadata/HDF5 names only in existing serialized schemas and convert at those boundaries.
3. Expose injectable `Trace`, executor, and failing I/O dependencies in the voltage orchestrator so legacy-mask selection, lazy executor creation, and broader partial-output cleanup can gain observable behavioral tests.
4. Decide whether TIFF support uses a dependency or a pure-Python parser; behavior, not implementation choice, is constrained.
5. Keep internal line/trial/ROI identifiers zero-based with half-open slices, converting to legacy one-based inclusive identifiers only at serialized boundaries.
