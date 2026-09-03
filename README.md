# SLAP2 Voltage Extraction

Focused MATLAB/Python pipeline for extracting SLAP2 voltage-imaging integration ROIs. The MATLAB implementation is the reference implementation; a later Python port will reproduce its outputs exactly.

Motion correction is intentionally out of scope.

## Current MATLAB workflow

```matlab
cd('C:\path\to\SLAP2-Voltage-Extraction')
setup

% Build a GIAnT-compatible input table if needed.
buildTrialTableSLAP2(slap2Root, outputDir, true);

% ASAP8 example.
params = ASAP8_params(struct( ...
    'nWorkers', 4, ...
    'maxConcurrentROIs', 2, ...
    'overwrite', true));
summary = Voltage(fullfile(outputDir,'trial_table.h5'), params);
```

For ASAP7-family quenched indicators:

```matlab
params = ASAP7_params(struct('overwrite',true));
summary = Voltage(pathToTrialTable, params);
```

Calling `Voltage(pathToTrialTable)` without a parameter struct opens the parameter GUI.

## Input

`Voltage.m` consumes the GIAnT-compatible `trial_table.h5` produced by `buildTrialTableSLAP2.m`. The required SLAP2 fields are:

```text
/filename
/epoch                         (optional but preferred)
/slap2_info/first_line
/slap2_info/last_line
/slap2_info/ref_stack/...
```

New trial tables also include:

```text
/slap2_info/line_range_convention = "inclusive"
```

Older GIAnT CYCLE tables are supported automatically; their historical half-open `last_line` convention is normalized internally.

## Output

The default output is:

```text
<directory containing trial_table.h5>/Voltage/VoltageSummary.h5
```

The file intentionally resembles the useful parts of SILo's `experiment_summary.h5` while using voltage-specific datasets:

```text
/format_version
/params
/Path1
    /Z_depths
    /sample_rate_hz
    /frame_info
        /trial_num_frames
        /trial_epoch
        /frame_line_idxs
        /sample_epoch
    /sources
        /spatial
            /profiles
            /coords
            /source_roi_index
            /roi_pixel_count
        /temporal
            /raw_f
            /f0
            /dff
/Path2
    ...
```

`raw_f`, `f0`, and `dff` use shape `[nROIs x 1 x totalSamples]` in MATLAB. Because the file is written with MATLAB's column-major HDF5 convention (`/row_major = 0`), readers such as h5py will see the dimensions reversed.

## Runtime behavior

The MATLAB reference implementation is optimized around the common continuous-CYCLE voltage workflow:

- each distinct raw SLAP2 source file is opened once for extraction; the first source handle is reused after metadata/ROI discovery instead of being reopened;
- integration ROIs are extracted in bounded asynchronous batches (`nWorkers`, `maxConcurrentROIs`);
- repeated pseudo-trials from one continuous source are written as one contiguous HDF5 block per ROI whenever their source and output ranges are contiguous;
- F0 and dF/F are computed directly from the in-memory raw trace when one source file contains a complete acquisition epoch, avoiding a full `raw_f` HDF5 reread;
- only epochs assembled from multiple raw files use the bounded HDF5 readback fallback needed to preserve epoch-scoped F0 semantics;
- full trace arrays are released from the batch container before F0/dF/F processing to keep peak memory bounded.

`Voltage` returns per-path timing diagnostics in `summary.timing.path`, including:

```text
metadata_s
source_open_s
output_init_s
raw_trace_s
raw_write_s
raw_h5_writes
fallback_read_s
derived_compute_s
derived_write_s
total_s
```

Timing diagnostics are returned in the MATLAB `summary` structure rather than written into `VoltageSummary.h5`, keeping the scientific HDF5 output deterministic for later MATLAB/Python byte-parity work. For a normal single-source CYCLE epoch, `fallback_read_s` should be zero.

## Voltage dF/F

The default F0 model matches the robust pathway used in `vip-slap2-analysis`:

1. 5 s fluorescence bins.
2. 50th-percentile F0 estimate in each bin.
3. Centered moving median over 180 s of bin estimates.
4. Linear interpolation back to the native SLAP2 line/sample rate.
5. F0 is fit independently within each inferred acquisition epoch.

The saved `dff` signal is polarity-corrected so positive values correspond to positive membrane-voltage deflections:

- ASAP8 / brightening: `(F - F0) / F0`
- ASAP7 / quenching: `(F0 - F) / F0`

Set `indicatorName` and/or `indicatorDirection` explicitly. `auto` recognizes ASAP7 and ASAP8; unknown indicators fail rather than silently choosing a sign.

## Repository layout

```text
SLAP2-Voltage-Extraction/
├── setup.m
├── buildTrialTableSLAP2.m
├── Voltage.m
├── source_extraction/
│   ├── computeVoltageF0.m
│   └── computeVoltageDFF.m
├── dependencies/
│   ├── io/
│   └── gui/
├── presets/
│   ├── ASAP7_params.m
│   └── ASAP8_params.m
├── tests/
└── docs/
```

## External SLAP2 dependency

This repo does not vendor the full SLAP2 reader. Your MATLAB environment must resolve:

```matlab
slap2.Slap2DataFile
slap2.util.MultiDataFiles
slap2.util.datafile.trace.Trace
```

Run `setup` to add this repository to the MATLAB path and report missing SLAP2 classes.

## Development sequence

1. Run this MATLAB version on a representative voltage session.
2. Inspect `VoltageSummary.h5` and freeze it as the golden reference.
3. Add numerical/schema regression tests.
4. Port the code to Python.
5. Compare MATLAB and Python outputs dataset-by-dataset and then at the byte level where HDF5 serialization allows it.
