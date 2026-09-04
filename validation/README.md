# SLAP2 Voltage validation harness

This folder is the next validation stage after a successful MATLAB `Voltage` run.

It is designed for large `VoltageSummary.h5` files that are impractical to upload.
The validator runs locally beside the HDF5 and emits small reports plus a compact,
**native-rate and unfiltered** HDF5 subset that can be uploaded for inspection.

## What the GIAnT comparison means

The supplied GIAnT glutamate `experiment_summary.h5` has the following core layout:

```text
/params
/Path#
    /Z_depths
    /frame_info
        /trial_num_frames
        /frame_line_idxs
        ... motion/source-specific fields ...
    /global/F
    /sources
        /spatial
            /profiles
            /coords
        /temporal
            /F0
            /SNR
            /dF_ls
            /dF_denoised
            /events
    /visualizations
```

Its h5py axis conventions are:

```text
sources/spatial/profiles : [X, Y, Z, source]
sources/spatial/coords   : [3, source]
sources/temporal/*       : [time, channel, source]
```

The Voltage output should preserve that organizational/axis contract, while using
modality-specific temporal signals:

```text
/Path#/sources/temporal/raw_f
/Path#/sources/temporal/f0
/Path#/sources/temporal/dff
```

and Voltage-specific timing/ROI metadata:

```text
/Path#/sample_rate_hz
/Path#/frame_info/trial_epoch
/Path#/frame_info/sample_epoch
/Path#/sources/spatial/source_roi_index
/Path#/sources/spatial/roi_pixel_count
```

GIAnT/SILo uses upper-case `F0`; Voltage deliberately keeps lower-case `f0` to
match the current `vip-slap2-analysis` voltage HDF5 convention (`raw_f`, `f0`, `dff`).

GIAnT-only motion, source-extraction, denoising, event, global-F, and visualization
datasets are not expected in a direct Voltage extraction.

## First run: structure + internal consistency

On the 2026-07-23 ASAP8 reference session, use the old summary MAT file so the
validator automatically expects 4 ROIs on Path1 and 3 on Path2.

Example:

```powershell
python .\validation\validate_voltage_output.py `
  --voltage "\\allen\aind\scratch\ophys\Andrew\VIP_synaptic_dynamics\ASAP8\852835\852835_2026-07-23_14-27-27\852835_2026-07-23_14-27-27\slap2\dynamic_data\Voltage\VoltageSummary.h5" `
  --old-summary "D:\PATH\TO\dendriticVoltageSummary-260723-170417.mat"
```

If the old `dendriticVoltageTraces-260723-170417.h5` is still accessible at the
path recorded in the MAT summary, raw-F parity runs automatically. Otherwise
provide it explicitly:

```powershell
  --old-traces "D:\PATH\TO\dendriticVoltageTraces-260723-170417.h5"
```

## Independent F0/dFF comparison with current vip-slap2-analysis

Add:

```powershell
  --vip-repo "C:\Users\andrew.shelton\Dropbox\allen institute\Python_Code\ams\ophys\vip-slap2-analysis"
```

For this single-epoch reference session the validator processes one ROI at a time,
so it does not require the entire session to fit into RAM.

## Outputs

The default output directory is:

```text
<VoltageSummary.h5 parent>\validation\
```

Important files:

```text
validation_summary.txt
validation_report.json
voltage_h5_manifest.csv
giant_glutamate_reference_manifest.json
internal_signal_qc.csv
raw_f_parity_vs_extractDendrites.csv          # when old traces are available
f0_dff_parity_vs_vip_slap2_analysis.csv       # when --vip-repo is provided
validation_subset.h5
```

`validation_subset.h5` contains full-rate start/middle/end snippets for every ROI
plus ROI spatial profiles. It does **not** smooth, filter, resample, or otherwise
temporally transform `raw_f` or `dff`.

Upload the small reports and `validation_subset.h5` back to ChatGPT for the next
review stage.

## Acceptance order

Do not freeze the MATLAB reference until these pass in order:

1. HDF5 structure / GIAnT organizational and axis contract.
2. Expected Path1=4 and Path2=3 ROI counts.
3. Trial/sample metadata consistency.
4. Internal `dff == sign * (raw_f - f0) / f0` consistency.
5. Raw-F parity against the old `extractDendrites` extraction.
6. F0/dFF parity against the current `vip-slap2-analysis` implementation.
7. Native-rate visual QC of all seven ROIs.
8. Freeze the MATLAB golden reference and only then begin the Python port.
