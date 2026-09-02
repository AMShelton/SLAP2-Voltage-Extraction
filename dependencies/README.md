# MATLAB dependency boundary

This repository intentionally does not vendor the whole GIAnT-MATLAB repository.

The current files rely on a small set of external functions/classes. During Step 2 we should either vendor the stable helper functions or replace them with project-owned equivalents so that MATLAB/Python parity is under our control.

## GIAnT-compatible I/O helpers

From the `fix/aind-slap2-dynamic-data` branch of `AMShelton/GIAnT-MATLAB`:

- `dependencies/io/saveStructToH5.m` — required by `buildTrialTableSLAP2.m`
- `dependencies/io/loadStructFromH5.m` — planned canonical reader for `trial_table.h5`
- `dependencies/io/ScanImageTiffWrapper.m`
- `dependencies/io/ScanImageTiffDataWrapper.m`

## Optional interactive helpers

- `dependencies/gui/setParams.m`
- `dependencies/gui/optionsGUI.m`
- `dependencies/gui/drawROIs.m`

The planned voltage-specific parameter definitions should eventually live in this repository rather than depending on GIAnT's SILo parameter table.

## External SLAP2/ScanImage packages

The extractor currently calls the SLAP2 Trace backend (`slap2.util.MultiDataFiles`, `slap2.util.datafile.trace.Trace`) and a ScanImage TIFF reader. Exact package/commit pinning should be recorded before the reference MATLAB run used for Python equivalence testing.
