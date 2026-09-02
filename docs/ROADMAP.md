# Development roadmap

## Step 1 — repository scaffold

- Keep the GIAnT-compatible `buildTrialTableSLAP2.m` entry point.
- Keep the current `extractDendrites.m` as the initial reference source-extraction implementation.
- Establish explicit dependency, test, preset, and documentation locations.

## Step 2 — MATLAB voltage summary contract

1. Load GIAnT `trial_table.h5` directly.
2. Preserve integration-ROI extraction without motion correction.
3. Rename output concepts from dendrite-specific naming to voltage/session naming.
4. Write a SILo-like `experiment_summary.h5` hierarchy.
5. Add raw fluorescence, F0, and dF/F.
6. Add voltage-indicator polarity and F0/baseline parameters.
7. Implement dF/F using the voltage processing method used by `vip-slap2-analysis`, after freezing its exact numerical definition.
8. Add schema and numerical regression tests.

## Step 3 — MATLAB reference run

Run one selected voltage session and freeze:

- trial table
- parameter file
- package versions / commits
- output HDF5
- dataset shapes/dtypes/attributes
- checksums for deterministic datasets

## Step 4 — Python port

Translate parsing, ROI extraction orchestration, numerical transforms, and HDF5 serialization into a Python package. Keep the MATLAB implementation unchanged as the oracle during the port.

## Step 5 — same-session Python run

Run the identical raw session using the frozen parameter set.

## Step 6 — parity validation

Compare in increasing strictness:

1. group/dataset/attribute schema
2. shapes and dtypes
3. NaN masks
4. exact numeric equality
5. raw dataset byte equality
6. whole-file byte equality only if deterministic HDF5 creation metadata/layout has been intentionally standardized

Whole-HDF5-file byte identity is stricter than scientific/numerical identity because HDF5 object ordering, timestamps, library versions, chunk layout, and metadata serialization can differ across writers. We should explicitly distinguish these two targets when the output contract is frozen.
