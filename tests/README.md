# Tests

Run from MATLAB after `setup`:

```matlab
results = runtests('tests');
table(results)
```

The synthetic tests do not require raw SLAP2 data. The next milestone is a golden-session integration test that runs `Voltage.m` against one representative session and validates the complete HDF5 output.
