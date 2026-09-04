# SLAP2 Voltage Extraction

**SLAP2 Voltage Extraction** is a focused pipeline for extracting integration-ROI voltage signals from SLAP2 recordings.

The current MATLAB implementation is the reference implementation. It reads a GIAnT-compatible `trial_table.h5`, extracts native-rate fluorescence from SLAP2 integration ROIs, computes baseline fluorescence (`f0`) and polarity-corrected voltage `dff`, and writes a GIAnT-style `VoltageSummary.h5`.

A Python implementation is planned and will be validated against the MATLAB output dataset-by-dataset.

> **Scope:** this repository performs direct voltage trace extraction and normalization. Motion correction is intentionally out of scope.

---

## Install

### MATLAB

Current development and validation are performed with **MATLAB R2024b**.

Clone the repository:

```bash
git clone https://github.com/AMShelton/SLAP2-Voltage-Extraction.git
cd SLAP2-Voltage-Extraction
```

The repository contains its own helper code and pinned voltage trace kernel. From MATLAB:

```matlab
cd('C:\path\to\SLAP2-Voltage-Extraction')
setup
```

`setup.m` adds the repository-local source, GUI, I/O, preset, and vendored SLAP2 trace-kernel folders to the MATLAB path and reports the resolved `Trace` and `TracePixel` classes.

`Voltage.m` also bootstraps the repository-local paths when called directly, but running `setup` once is recommended because it performs dependency checks explicitly.

### MATLAB toolboxes

The reference pipeline uses:

- **Statistics and Machine Learning Toolbox** — required for percentile-based F0 estimation (`prctile`)
- **Parallel Computing Toolbox** — recommended for the default asynchronous ROI extraction path

Parallel extraction can be disabled with:

```matlab
params.useParallel = false;
```

### External SLAP2 reader

The low-level binary SLAP2 reader remains external. MATLAB must resolve:

```matlab
slap2.Slap2DataFile
slap2.util.MultiDataFiles
```

Use a compatible SLAP2 reader such as:

- [Slap2DataReader](https://github.com/m-xie/Slap2DataReader)
- the `slap2` package distributed by MBF Bioscience

Add the reader package to the MATLAB path before running `Voltage`.

The voltage trace classes that define the extraction kernel are pinned in this repository for reproducibility:

```matlab
slap2.util.datafile.trace.Trace
slap2.util.datafile.trace.TracePixel
```

They live under:

```text
dependencies/slap2_trace/+slap2/+util/+datafile/+trace/
```

After running `setup`, verify the resolved dependencies if needed:

```matlab
which slap2.Slap2DataFile -all
which slap2.util.MultiDataFiles -all
which slap2.util.datafile.trace.Trace -all
which slap2.util.datafile.trace.TracePixel -all
```

---

## How to run

### 1. Build or locate `trial_table.h5`

`Voltage.m` consumes the same GIAnT-compatible SLAP2 trial-table format used by GIAnT.

To build one from a SLAP2 recording:

```matlab
buildTrialTableSLAP2(slap2Root, outputDir, true);
```

Continuous CYCLE acquisitions are divided into analysis trials of approximately **200,000 SLAP2 lines**. These analysis trials are bookkeeping units; the raw CYCLE source is still extracted once and reused rather than reread separately for every pseudo-trial.

### 2. Run Voltage extraction

#### ASAP8 / fluorescence increases with depolarization

```matlab
params = ASAP8_params(struct( ...
    'nWorkers', 4, ...
    'maxConcurrentROIs', 2, ...
    'overwrite', true));

summary = Voltage(fullfile(outputDir, 'trial_table.h5'), params);
```

#### ASAP7 / fluorescence decreases with depolarization

```matlab
params = ASAP7_params(struct( ...
    'overwrite', true));

summary = Voltage(pathToTrialTable, params);
```

#### Interactive parameter GUI

```matlab
summary = Voltage(pathToTrialTable);
```

Calling `Voltage` without a parameter struct opens the Voltage parameter GUI.

### Typical benchmark configuration

For direct numerical comparison with the historical 2026-07-23 `extractDendrites` run, use the same Trace window that run used:

```matlab
params = ASAP8_params(struct( ...
    'traceWindow_lines', 12, ...
    'nWorkers', 8, ...
    'maxConcurrentROIs', 4, ...
    'overwrite', true));

summary = Voltage(pathToTrialTable, params);
```

The general repository default remains `traceWindow_lines = 16`.

---

## Epochs and analysis trials

As in GIAnT, the pipeline distinguishes **acquisition epochs** from **analysis trials**.

- An **epoch** is a contiguous SLAP2 acquisition block whose native line numbering belongs to one acquisition instance.
- An **analysis trial** is a contiguous temporal subset used for bookkeeping and downstream alignment.

For continuous SLAP2 CYCLE acquisitions, one raw acquisition commonly becomes many ~200,000-line analysis trials in `trial_table.h5`.

`Voltage` extracts each distinct raw SLAP2 source once, then maps the resulting native-rate trace into the analysis-trial layout recorded in the trial table.

When explicit epoch metadata are available they are used directly. Otherwise `Voltage` infers acquisition restarts from source filenames.

---

## Input: `trial_table.h5`

The required SLAP2 fields are:

```text
🗄️ trial_table.h5
 ├ 🔤 datadr
 ├ 🔤 savedr
 ├ 🔤 filename
 ├ 🔢 epoch                         (optional but preferred)
 ├ ☑️ row_major
 └ 📁 slap2_info
    ├ 📁 ref_stack
    │  └ 📁 Path{1,2,...}
    │     ├ 🖼️ IM
    │     ├ 🔢 channels
    │     ├ 📈 Zs
    │     └ 📈 dmdPixel2SampleTransform
    ├ 🔢 first_line
    ├ 🔢 last_line
    └ 🔤 line_range_convention
```

New trial tables written by this repository use:

```text
/slap2_info/line_range_convention = "inclusive"
```

so each analysis-trial range is:

```text
first_line <= line <= last_line
```

Older GIAnT continuous-CYCLE tables that lack this field are supported automatically. Their historical upper-bound convention is normalized internally so adjacent analysis trials do not duplicate boundary samples.

---

## Voltage ROI discovery

Voltage ROIs are identified from the **SLAP2 parse plan**, not from an `imagingMode == "Integrate"` metadata string.

For every acquisition ROI, `Voltage`:

1. loads the stored ROI mask when available;
2. otherwise reconstructs the mask from `shapeData`;
3. tests the mask against the integration-pixel portion of the SLAP2 parse plan;
4. retains the ROI if one or more integration `TracePixel`s are resolved.

This classification step uses:

```matlab
hTrace.setPixelIdxs([], mask)
```

to test integration-mode membership only.

Actual raw-fluorescence extraction intentionally preserves the historical optimized voltage behavior:

```matlab
hTrace.setPixelIdxs(mask, mask)
```

so ROI classification does not alter the scientific Trace calculation used for raw-F parity.

A path with zero Voltage ROIs is allowed if another imaging path contains valid Voltage ROIs. If **all** paths contain zero Voltage ROIs, the run fails with `Voltage:NoVoltageROIs` and removes the partial output rather than reporting an empty extraction as successful.

---

## Voltage dF/F

The default F0 pathway reproduces the robust normalization used by `vip-slap2-analysis`.

For each ROI and acquisition epoch:

1. divide native-rate fluorescence into **5 s bins**;
2. calculate the **50th percentile** fluorescence in each bin;
3. apply a centered moving median over **180 s** of bin estimates;
4. linearly interpolate the smoothed baseline back to the native SLAP2 sample rate;
5. replace invalid or near-zero F0 values with a robust fluorescence fallback.

Default parameters:

```text
f0Method     = robust
f0Percentile = 50
f0Bin_s      = 5
f0Smooth_s   = 180
```

A static percentile baseline is also available with:

```matlab
params.f0Method = 'static';
```

### Indicator polarity

Saved `dff` is sign-corrected so that **positive `dff` corresponds to a positive membrane-voltage deflection**.

- ASAP8 / brightening:
  ```text
  dff = (F - F0) / F0
  ```

- ASAP7 / quenching:
  ```text
  dff = (F0 - F) / F0
  ```

Set `indicatorName` or `indicatorDirection` explicitly. With `indicatorDirection = 'auto'`, indicator names containing `ASAP7` or `ASAP8` are recognized. Unknown indicators fail rather than silently choosing a polarity.

---

## Pipeline output

The default output is:

```text
<directory containing trial_table.h5>/Voltage/VoltageSummary.h5
```

The output intentionally follows the same high-level organization as GIAnT's `experiment_summary.h5`:

```text
Path#/
    frame_info/
    sources/
        spatial/
        temporal/
```

while containing voltage-specific source and timing fields rather than SILo source-extraction outputs.

### Reading H5 outside MATLAB

`VoltageSummary.h5` is written from MATLAB with:

```text
/row_major = 0
```

The dimensions below therefore match **MATLAB `size()`**.

Python/h5py readers will commonly see the dimensions in reverse order. For example:

```text
MATLAB: [nROIs, 1, totalSamples]
h5py:   [totalSamples, 1, nROIs]
```

This matches the MATLAB/HDF5 convention used by GIAnT.

### `VoltageSummary.h5` structure

Legend: 🗄️ file · 📁 group · 🔤 string · 🔢 integer · 📈 numeric · 🖼️ image/array · ☑️ bool

```text
🗄️ VoltageSummary.h5
 ├ ☑️ row_major
 ├ 🔤 format_version
 ├ 📁 params
 │  ├ 🔢 chIdx
 │  ├ 🔢 zIdx
 │  ├ 🔢 traceWindow_lines
 │  ├ 🔢 traceExpectedWindow_lines
 │  ├ 🔤 indicatorName
 │  ├ 🔤 indicatorDirection
 │  ├ 🔤 f0Method
 │  ├ 📈 f0Percentile
 │  ├ 📈 f0Bin_s
 │  ├ 📈 f0Smooth_s
 │  ├ ☑️ useParallel
 │  ├ 🔢 nWorkers
 │  ├ 🔢 maxConcurrentROIs
 │  ├ 🔤 precision
 │  ├ 🔤 outputDir
 │  ├ 🔤 outputFilename
 │  ├ ☑️ overwrite
 │  ├ 🔢 h5ChunkSamples
 │  └ 🔢 h5Deflate
 └ 📁 Path{1,2,...}
    ├ 📈 Z_depths
    ├ 📈 sample_rate_hz
    ├ 📁 frame_info
    │  ├ 🔢 trial_num_frames
    │  ├ 🔢 trial_epoch
    │  ├ 🔢 frame_line_idxs
    │  └ 🔢 sample_epoch
    └ 📁 sources
       ├ 📁 spatial
       │  ├ 🖼️ profiles
       │  ├ 📈 coords
       │  ├ 🔢 source_roi_index
       │  └ 🔢 roi_pixel_count
       └ 📁 temporal
          ├ 📈 raw_f
          ├ 📈 f0
          └ 📈 dff
```

### Output field descriptions

| Field | MATLAB size | Type | Description |
| --- | --- | --- | --- |
| `row_major` | `1 x 1` | `uint8` | Layout flag. `0` indicates MATLAB/column-major HDF5 convention. |
| `format_version` | scalar string | string | Voltage output-schema version. |
| `params` | group | — | Complete parameter set used for the run. |
| `Path#/Z_depths` | `nZ x 1` | double | Imaged Z depth(s) from SLAP2 metadata. Current single-plane voltage recordings normally contain one value. |
| `Path#/sample_rate_hz` | `1 x 1` | double | Native SLAP2 line/sample rate used for the extracted trace. |
| `Path#/frame_info/trial_num_frames` | `nTrials x 1` | int32 | Number of native-rate samples contributed by each analysis trial. |
| `Path#/frame_info/trial_epoch` | `nTrials x 1` | int32 | Acquisition-epoch index assigned to each analysis trial. |
| `Path#/frame_info/frame_line_idxs` | `totalSamples x 1` | int32 | Source SLAP2 line index corresponding to each concatenated output sample. |
| `Path#/frame_info/sample_epoch` | `totalSamples x 1` | int32 | Acquisition-epoch index for every output sample. |
| `Path#/sources/spatial/profiles` | `nROIs x 1 x rows x cols` | single | Binary spatial footprint for each extracted integration ROI. |
| `Path#/sources/spatial/coords` | `nROIs x 3` | double | Zero-indexed `[z, y, x]` ROI centroid. |
| `Path#/sources/spatial/source_roi_index` | `nROIs x 1` | int32 | 1-based index of each retained ROI in the acquisition ROI list. |
| `Path#/sources/spatial/roi_pixel_count` | `nROIs x 1` | int32 | Number of DMD pixels in each ROI mask. |
| `Path#/sources/temporal/raw_f` | `nROIs x 1 x totalSamples` | single/double | Native-rate fluorescence returned by the pinned SLAP2 `Trace` kernel. |
| `Path#/sources/temporal/f0` | `nROIs x 1 x totalSamples` | single/double | Baseline fluorescence used for voltage normalization. |
| `Path#/sources/temporal/dff` | `nROIs x 1 x totalSamples` | single/double | Polarity-corrected voltage dF/F. Positive values represent positive membrane-voltage deflections. |

The `dff` dataset also stores HDF5 attributes describing the requested indicator name, requested direction, and sign convention.

### Relationship to GIAnT `experiment_summary.h5`

The Voltage summary deliberately preserves GIAnT's organizational and axis conventions:

```text
/Path#/frame_info
/Path#/sources/spatial
/Path#/sources/temporal
```

GIAnT/SILo-specific fields such as:

```text
global/F
visualizations/*
sources/temporal/dF_ls
sources/temporal/dF_denoised
sources/temporal/events
sources/temporal/SNR
```

are **not** generated because direct voltage extraction does not perform SILo source detection, denoising, event inference, or motion correction.

GIAnT uses `F0`; Voltage uses lowercase `f0` to match the existing voltage-analysis convention (`raw_f`, `f0`, `dff`) used downstream in `vip-slap2-analysis`.

---

## Parameters

The default parameters are defined in `dependencies/gui/setParams.m`.

| Parameter | Default | Description |
| --- | ---: | --- |
| `chIdx` | `1` | SLAP2 channel index passed to `Trace`. |
| `zIdx` | `1` | SLAP2 Z-plane index passed to `Trace`. |
| `traceWindow_lines` | `16` | Temporal weighting window used by `Trace.process`. |
| `traceExpectedWindow_lines` | `5000` | Expected-fluorescence window used by `Trace.process`. |
| `indicatorName` | `''` | Indicator name used when polarity is inferred automatically. |
| `indicatorDirection` | `auto` | `auto`, `increases`, or `decreases`. |
| `f0Method` | `robust` | `robust` binned baseline or `static` percentile baseline. |
| `f0Percentile` | `50` | Baseline percentile. |
| `f0Bin_s` | `5` | Robust-F0 bin duration in seconds. |
| `f0Smooth_s` | `180` | Moving-median duration for robust-F0 bin estimates. |
| `useParallel` | `true` | Use asynchronous ROI extraction. |
| `nWorkers` | `4` | Requested MATLAB process workers. |
| `maxConcurrentROIs` | `2` | Maximum number of ROI traces active at once. |
| `precision` | `single` | Saved temporal datatype: `single` or `double`. |
| `outputDir` | `''` | Empty creates a `Voltage/` folder beside `trial_table.h5`. |
| `outputFilename` | `VoltageSummary.h5` | Output HDF5 filename. |
| `overwrite` | `false` | Replace an existing output file. |
| `h5ChunkSamples` | `100000` | HDF5 chunk length along the temporal dimension. |
| `h5Deflate` | `0` | HDF5 compression level. `0` is fastest and preferred for parity testing. |

The preset helpers set indicator polarity while retaining these defaults:

```matlab
ASAP7_params(...)
ASAP8_params(...)
```

Parameter overrides may be provided as a MATLAB struct, JSON string/file, or MAT preset accepted by `setParams`.

---

## Runtime and resource optimizations

The MATLAB reference implementation is optimized for long continuous-CYCLE voltage recordings without changing the underlying Trace calculation.

- **Reader reuse:** the first `MultiDataFiles` reader remains open from metadata/ROI discovery through extraction rather than being reopened immediately.
- **One extraction per raw source:** repeated analysis trials that reference the same CYCLE source do not cause repeated raw-data extraction.
- **Bounded asynchronous ROI extraction:** `nWorkers` and `maxConcurrentROIs` control process-pool size and simultaneous ROI traces.
- **Contiguous HDF5 writes:** adjacent pseudo-trials from one continuous source can be written as a single HDF5 block per ROI.
- **In-memory derived signals:** when one raw source contains a complete acquisition epoch, `f0` and `dff` are computed directly from the in-memory `raw_f` trace, avoiding a complete HDF5 readback.
- **Multi-source fallback:** epochs assembled from multiple raw source files use bounded HDF5 readback so F0 remains epoch-scoped.
- **Lazy worker startup:** the MATLAB process pool starts only after at least one path passes ROI discovery.
- **Fail-fast empty-session handling:** zero-ROI paths do not create large per-sample metadata arrays, and all-zero runs remove partial output.
- **Serial HDF5 writes:** parallel workers perform Trace extraction; HDF5 writes remain serialized for reliability.
- **No compression by default:** `h5Deflate = 0` minimizes write overhead and simplifies numerical-parity testing.

### Timing diagnostics

`Voltage` returns timing information in:

```matlab
summary.timing
summary.timing.path(1)
summary.timing.path(2)
```

Per-path fields include:

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

Timing values are returned in the MATLAB `summary` structure rather than written to `VoltageSummary.h5`, keeping the scientific HDF5 deterministic for later MATLAB/Python parity testing.

For the normal single-source continuous-CYCLE fast path:

```text
fallback_read_s = 0
```

is expected.

---

## Repository layout

```text
SLAP2-Voltage-Extraction/
├── Voltage.m
├── buildTrialTableSLAP2.m
├── setup.m
├── source_extraction/
│   ├── computeVoltageF0.m
│   └── computeVoltageDFF.m
├── dependencies/
│   ├── gui/
│   │   ├── optionsGUI.m
│   │   └── setParams.m
│   ├── io/
│   │   ├── loadStructFromH5.m
│   │   ├── saveStructToH5.m
│   │   └── ScanImageTiff*.m
│   └── slap2_trace/
│       └── +slap2/+util/+datafile/+trace/
│           ├── Trace.m
│           └── TracePixel.m
├── presets/
│   ├── ASAP7_params.m
│   └── ASAP8_params.m
├── tests/
└── docs/
    └── ROADMAP.md
```

---

## Tests

Run the MATLAB test suite from the repository root:

```matlab
setup
results = runtests('tests');
table(results)
```

Current tests cover:

- repository layout;
- robust/static Voltage F0 behavior;
- ASAP7/ASAP8 dF/F polarity;
- trial-table HDF5 round-trip behavior;
- the distinction between integration-only ROI classification and historical `mask, mask` Trace extraction semantics.

---

## Validation and development status

The MATLAB implementation is the reference implementation for the current development phase.

Validation proceeds in this order:

1. verify `VoltageSummary.h5` structure against GIAnT's `experiment_summary.h5` organization and HDF5 axis conventions;
2. verify ROI counts and masks against historical `extractDendrites` outputs;
3. verify trial/sample accounting and native sample rate;
4. compare `raw_f` numerically against the historical optimized extractor;
5. compare MATLAB `f0` and `dff` against the current `vip-slap2-analysis` implementation;
6. inspect full-rate, unfiltered traces for every reference ROI;
7. freeze the validated MATLAB output as the golden reference;
8. implement the Python port and require it to reproduce the same schema and numerical outputs.

The Python port is **not yet the reference implementation**.

---

## Design principles

- Preserve the raw SLAP2 Trace calculation unless an algorithm change is explicitly intended and validated.
- Keep raw voltage signals at native sample rate.
- Do not smooth or filter `raw_f` or `dff` for plotting or event selection as part of extraction.
- Keep output organization close to GIAnT where that improves interoperability.
- Keep voltage-specific semantics explicit rather than forcing SILo-specific fields into the file.
- Favor deterministic, inspectable HDF5 outputs suitable for numerical regression testing.
