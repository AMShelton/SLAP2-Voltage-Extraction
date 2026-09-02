# Tests

Step 1 only includes smoke tests for repository structure and MATLAB parser diagnostics.

Step 2 should add fixture-based tests for:

- loading `trial_table.h5`
- DMD/ROI identity and ordering
- line-range slicing
- continuous/multi-epoch behavior
- voltage F0 and dF/F transforms
- HDF5 schema, dtype, chunking, fill values, and attributes
- deterministic reruns with the same input and parameters
