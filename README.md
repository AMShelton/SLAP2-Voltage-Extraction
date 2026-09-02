# SLAP2 Voltage Extraction

A focused SLAP2 voltage-imaging extraction pipeline derived from the voltage extraction workflow in `vip-slap2-analysis` and organized after the SLAP2 path in GIAnT-MATLAB.

## Project goal

The project will proceed in two implementations:

1. A MATLAB reference implementation that consumes GIAnT-compatible `trial_table.h5` files and writes a SILo-like `experiment_summary.h5` containing voltage fluorescence, F0, and dF/F outputs.
2. A Python implementation that reproduces the MATLAB reference outputs exactly for a fixed input/configuration, with byte-level validation where HDF5 serialization permits it and dataset/value-level validation otherwise.

Motion correction is intentionally out of scope for the initial voltage extraction path.

## Current status

Step 1 scaffold only. The repository currently contains the existing voltage extractor and the GIAnT-compatible SLAP2 trial-table builder. `extractDendrites.m` has **not yet** been converted to read `trial_table.h5` or to write the new SILo-like voltage summary format; those changes belong to Step 2.

## Layout

```text
SLAP2-Voltage-Extraction/
├── buildTrialTableSLAP2.m
├── source_extraction/
│   └── extractDendrites.m
├── dependencies/
│   └── README.md
├── presets/
├── tests/
│   ├── test_repository_layout.m
│   └── README.md
├── docs/
│   └── ROADMAP.md
├── .gitignore
└── README.md
```

The layout deliberately mirrors GIAnT-MATLAB at a smaller scope: the SLAP2 trial-table builder remains at repository root and extraction code lives under `source_extraction/`.

## MATLAB dependencies

The current MATLAB reference code expects:

- MATLAB R2024b (the development environment currently in use)
- Parallel Computing Toolbox for parallel extraction
- Image Processing Toolbox for mask/QC utilities
- SLAP2 data reader / Trace backend providing the `slap2` namespace used by the extractor
- ScanImage TIFF reader used by the reference-image helpers
- GIAnT helper utilities described in `dependencies/README.md`

The future Python port should not call MATLAB; it should reproduce the same parsing, extraction, numerical transforms, and output schema independently.

## Intended MATLAB workflow

Current scaffold:

```matlab
addpath(genpath('/path/to/SLAP2-Voltage-Extraction'));
trialTable = buildTrialTableSLAP2(slap2Root, outputDir, true);
% extractDendrites(...) still uses its pre-Step-2 input/output contract.
```

Target workflow after Step 2:

```matlab
buildTrialTableSLAP2(slap2Root, outputDir, true);
extractDendrites(fullfile(outputDir, 'trial_table.h5'), params);
```

Target outputs will be documented and frozen before the Python translation begins.

## Development rule for MATLAB/Python parity

Once the MATLAB output contract is frozen, changes affecting numerical output or HDF5 schema must be accompanied by regression fixtures and cross-language comparison tests. The MATLAB implementation is the reference implementation until parity is demonstrated.
