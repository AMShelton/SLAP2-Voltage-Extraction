# Voltage output validation

This directory contains tools for validating generated `VoltageSummary.h5` files without loading complete recordings into memory.

The validator can:

- inspect HDF5 structure, dtypes, shapes, chunks, and compression;
- compare output organization with the established GIAnT contract;
- verify ROI, trial, epoch, and sample accounting;
- check internal `raw_f`, `f0`, and `dff` consistency;
- compare against existing benchmark traces and summaries;
- optionally compare F0 against `vip-slap2-analysis`;
- export compact native-rate snippets for external inspection.

## Usage

```bash
python validation/validate_voltage_output.py \
  --voltage /path/to/VoltageSummary.h5 \
  --outdir /path/to/validation
```

Optional legacy benchmark inputs may use v7.3 MAT/HDF5 encoding. Those readers exist solely for compatibility with established validation datasets.

Run `--help` for all available comparison and export options.
