# Tests

Run from MATLAB after `setup`:

```matlab
results = runtests('tests');
table(results)
```

The synthetic tests do not require raw SLAP2 data. The next milestone is a golden-session integration test that runs `Voltage.m` against one representative session and validates the complete HDF5 output.

- `test_voltage_roi_discovery_contract.m` protects the parse-plan ROI selector, legacy raw-F mask semantics, all-zero-ROI failure, and lazy parallel-pool startup.
- `test_motion_censor.m` covers the online-offset censoring rule, mask-to-line expansion, parameter wiring in `setParams`, engine integration, and NaN-safe F0/dF/F with censored samples.
