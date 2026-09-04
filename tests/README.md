# Tests

Run from MATLAB after `setup`:

```matlab
results = runtests('tests');
table(results)
```

The synthetic tests do not require raw SLAP2 data. The next milestone is a golden-session integration test that runs `Voltage.m` against one representative session and validates the complete HDF5 output.

- `test_voltage_roi_discovery_contract.m` protects the parse-plan ROI selector, legacy raw-F mask semantics, all-zero-ROI failure, and lazy parallel-pool startup.
