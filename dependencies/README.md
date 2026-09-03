# Dependencies

This repository vendors only the small generic MATLAB helpers it directly owns:

- `io/`: HDF5 struct I/O and ScanImage TIFF readers used by `buildTrialTableSLAP2.m`.
- `gui/`: the parameter GUI and `setParams('Voltage', ...)`.

The SLAP2 binary reader is intentionally **external**, not copied into this repository. MATLAB must already resolve:

```matlab
which slap2.Slap2DataFile -all
which slap2.util.MultiDataFiles -all
which slap2.util.datafile.trace.Trace -all
```

`Voltage.m` uses `MultiDataFiles` and `Trace` as the reference raw-fluorescence extraction backend. Those classes define the scientific extraction kernel that the later Python implementation must reproduce.
