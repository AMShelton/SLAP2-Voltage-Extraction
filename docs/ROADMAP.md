# Roadmap

## MATLAB reference

- [x] GIAnT-compatible `trial_table.h5` input.
- [x] Canonical `Voltage.m` entry point and Voltage naming throughout.
- [x] SILo-like `VoltageSummary.h5` hierarchy.
- [x] Direct SLAP2 integration-ROI `raw_f` extraction without motion correction.
- [x] `f0` and polarity-corrected `dff` using the robust voltage baseline model used by `vip-slap2-analysis`.
- [x] ASAP7/ASAP8 direction configuration.
- [x] Epoch-scoped F0 so acquisition restarts are never bridged by the baseline model.
- [ ] Run on a representative voltage session and freeze a golden MATLAB output.
- [ ] Add session-level QC and numerical regression fixtures from that run.

## Python parity

- [ ] Translate trial-table loading and SLAP2 metadata handling.
- [ ] Translate raw integration-ROI trace extraction.
- [ ] Translate F0 and dF/F numerics.
- [ ] Reproduce `VoltageSummary.h5` dataset shapes, dtypes, values, and metadata.
- [ ] Compare MATLAB and Python outputs dataset-by-dataset, then pursue whole-file byte parity where HDF5 serialization permits it.
