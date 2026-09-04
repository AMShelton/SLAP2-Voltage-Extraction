# Dependencies

This repository vendors the small MATLAB components needed to keep the Voltage reference extraction reproducible:

- `io/`: HDF5 struct I/O and ScanImage TIFF readers used by `buildTrialTableSLAP2.m`.
- `gui/`: the parameter GUI and `setParams('Voltage', ...)`.
- `slap2_trace/`: the pinned `slap2.util.datafile.trace.Trace` and `TracePixel` classes used by Voltage ROI discovery and raw-fluorescence extraction.

The full SLAP2 binary reader remains **external**. MATLAB must already resolve:

```matlab
which slap2.Slap2DataFile -all
which slap2.util.MultiDataFiles -all
```

Run `setup` before `Voltage`. `setup` adds the vendored trace-package root and prints the exact `Trace`/`TracePixel` files MATLAB resolves.

The numerical `TracePixel.process` extraction kernel is retained from the supplied SLAP2 implementation. Its asynchronous pool bootstrap uses MATLAB's current `parpool` directly rather than the ScanImage/MOST `ParallelPoolManager`, removing an otherwise unnecessary environment dependency without changing the trace calculation itself.
