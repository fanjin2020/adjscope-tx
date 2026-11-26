# AdjScope-Tx

Reusable diagnostics and reproducible workflows for covariate adjustment in transcriptomic analysis.
One entry: `python run.py COMMAND`, also available as `python -m adjscope_tx COMMAND`.
Computation, manuscript CSV export and figure rendering share one publication schema.

## Compute from public inputs

Use an existing Linux Python 3.12 / R 4.5.3 environment matching requirements.txt,
requirements-supplementary.txt and inputs/environment.json. No packages are installed automatically.

If no matching Python is installed, explicitly create an isolated runtime with
the existing Python 3.12 interpreter:

```bash
python run.py setup-python --output "$HOME/adjscope/python330"
"$HOME/adjscope/python330/environment/bin/python" run.py run --output "$HOME/adjscope/p1_full" --workers 36
```

Setup installs both requirements files, including `openpyxl` for original Excel
sample annotations and expression tables. It leaves existing Python and R
environments unchanged. A completed runtime is checked and reused without
installing; a changed validated runtime is not repaired in place. Installation
logs and the readiness record stay in the runtime directory, outside paper outputs.
Use `setup-python --output DIRECTORY --check-only` for a check without installation.
The server launcher also accepts `--setup-python --python-env DIRECTORY` and then
runs the study using that interpreter. Installation cannot be combined with resume
or plan. R must already match the recorded specification.

```bash
conda activate paper1
python run.py run --output "$HOME/adjscope/p1_full" --workers 36 --plan
python run.py run --output "$HOME/adjscope/p1_full" --workers 36 --check-env
python run.py run --output "$HOME/adjscope/p1_full" --workers 36
```

| Sequential stage | Computation |
| --- | --- |
| study | Public downloads, preparation, human/mouse analyses, paired comparisons and supplementary analyses |
| design | Design information, Gaussian sensitivity and count-model benchmark |
| counts | Count generation, TMM, voom, two fits and paired-difference calibration |
| tails | Fresh-seed weight-source and extreme-tail controls |

A single stage runs at a time. Worker BLAS threads are limited to one.
The same run exports manuscript CSVs under `p1_full/results/` and renders all
available manuscript figures under `p1_full/figures/`. Completion requires both
outputs to pass verification. Rendering reads these CSVs, not the bundled evidence.
Full count experiments can take days. Use a new output outside the checkout.

```bash
python run.py run --stages counts tails --profile smoke --workers 2 --output "$HOME/adjscope/p1_smoke"
python run.py status --output "$HOME/adjscope/p1_full"
python run.py run --resume --output "$HOME/adjscope/p1_full" --workers 36
python run.py report --kind workflow --source "$HOME/adjscope/p1_full" --output "$HOME/adjscope/p1_results"
```

Resume restores settings and validates dataset receipts. Only workers may change.
A job.json file alone never makes a task complete. Changed source or software needs
a fresh experiment; resume older experiments with their original source snapshot.
An interrupted rendering is retried without repeating verified model fits.

When every analysis stage and its CSV export are complete, publication can also
finish through the framework's export-only entry:

```bash
python run.py finalize --output "$HOME/adjscope/p1_full"
```

This command verifies the completed stages, CSV checksums and their analysis
inputs, then renders figures without downloading data or fitting models. It
preserves the original analysis identity and records publication changes
separately. Only rendering and framework entry-point changes are accepted.
For legacy runs without a per-file source record, supply
`--analysis-source-manifest ORIGINAL_SOURCE_MANIFEST.json`, captured from the
original code before editing and matching the run's source checksum. Do not
replace source checksums to bypass validation.

For design-only work use `--stages design --data-work /path/to/study/core`.
The study stage has no reduced profile. Optional installed runtimes are selected
with --python, --rscript, repeated --r-library and --python-package-path.
--raw-cache reuses verified download objects, not fitted results.

## Export completed calculations

The `report` command reads completed results without rerunning models. It accepts
a framework run (`--source RUN`) or explicit stage directories:

```bash
python run.py report --study "$STUDY_RUN" --design "$DESIGN_RUN" \
  --counts "$COUNT_RUN" --tails "$TAIL_RUN" --output "$HOME/adjscope/p1_results"
python run.py figures --source "$HOME/adjscope/p1_results" --output "$HOME/adjscope/p1_figures"
```

Set these variables to actual completed directories. Missing or changed inputs
stop export; no fixed-result substitution is performed. Omitting stages exports
only their available tables and figures. An older tail run without its Gaussian
geometry summary requires an installed R/limma/edgeR environment to calculate
that design-only summary; it does not refit expression outcomes.

## Replay the recorded manuscript evidence

```bash
python run.py verify
python run.py report --kind publication --output "$HOME/adjscope/p1_tables"
python run.py figures --source "$HOME/adjscope/p1_tables" --output "$HOME/adjscope/p1_figures"
```

The full report writes **Supplementary_Tables.xlsx** (CMPB: S1-S23, 100 sections)
beside the manuscript CSVs. S9.5 gives the two GSE48350 regional summaries;
S11.7 gives the three prespecified GSE222007 library screens at seed 290.
The three main-table CSVs and the 10 main/15 supplementary figure mappings
retain the original release numbering. Replay performs no new fits.
The original 98-section evidence snapshot is identified in PUBLICATION_VERSION.json. Its
manifest is labeled `recorded_publication_evidence`; new calculations are
labeled `computed_results`. Both use the same export layout and figure mapping.

Default figures are PDF. The optional `figures` command redraws a CSV bundle:
--tiff adds 600-dpi TIFF; --editable adds SVG/PNG.
--figures 1 10 S15 selects a subset.
[Figure mapping](publication_figures/FIGURE_INDEX.md) | [Exact outputs](docs/OUTPUTS.md).

## Reproduce the CMPB figures

Use the complete CSV bundle from `report` above. Set `PLOT_PYTHON` to an
interpreter matching the [plotting requirements](artwork/cmpb/requirements.txt);
the statistical environment does not need to be changed. Choose new output directories.

```bash
python run.py figures --layout cmpb --source "$HOME/adjscope/p1_tables" --output "$HOME/adjscope/cmpb_main" --python "$PLOT_PYTHON"
python run.py figures --layout cmpb-supplement --source "$HOME/adjscope/p1_tables" --output "$HOME/adjscope/cmpb_supp" --python "$PLOT_PYTHON"
```

The first command produces six individual PDFs under `cmpb_main/Figures/`.
Fig. 1 preserves the supplied vector diagram and adds submission margins;
Figs. 2-6 are drawn in Python from the CSVs. The second draws all 20
supplementary PDFs in `cmpb_supp/`. Fig. S9 uses Table S20.5 to compare
pointwise rejection and power with and without paired covariance. The
[figure index](publication_figures/FIGURE_INDEX.md) maps each layout.
Neither command refits any model or changes the original archive numbering.

## Independent limma check (Supplementary Methods S11)

```bash
python run.py check-limma --output "$HOME/adjscope/paired_limma.json"
```

This small experiment generates 48 samples and 12 genes (seed 213), runs
AdjScope-Tx and independently fits an equivalent contrast with
limma's `contrastAsCoef` and `lmFit`. It checks extended-minus-baseline
coefficients and **unmoderated, model-based** paired standard errors with
shared weights. Both maximum absolute discrepancies must be below `1e-12`.
It uses no study data. The [original server receipt](validation/paired_limma_reference.json)
is for comparison only; it is not read by the experiment.
The default checks the study's Python and R environment before fitting.
`--smoke` runs a local compatibility check and never reports `PASS_LOCKED`.
Use `--rscript` and repeatable `--r-library` for an existing R installation;
without `--output` the JSON is printed only. Existing receipts are never overwritten.

## Reuse the diagnostics

```python
from adjscope_tx import diagnose_design, compare_models
design = diagnose_design(exposure, groups, covariates)
comparison = compare_models(expression, baseline, adjusted,
                            target=1, variance="model", gene_ids=gene_ids)
```

Expression is sample-by-gene; designs are nested, full-rank and share the target
column and sample order. The comparison API uses normalized expression with
shared fixed weights. Count/voom calibration uses the existing R kernels.
Results include paired coefficients, standard errors, intervals and BH-threshold
crossings. HC3 crossings are not presented as calibrated discoveries.

CLI commands `design` and `compare` accept CSVs with unique sample_id values.
Numeric covariates must be encoded explicitly. See --help for arguments.
Design geometry describes information and estimability, not a design-only FDR guarantee.

## Tests and modules

```bash
python run.py test
```

- adjscope_tx: public API, workflow, compact export and publication rendering.
- pipeline and analysis: public-input processing and Python/R statistical kernels.
- design_benchmark: design diagnostics and conditional benchmark.
- paired_count_calibration and paired_tail_diagnostics: count and tail calibration.
- inputs/evidence: one checksum-verified paper evidence store; table/plot aliases share data.
- publication_figures: renderers only; no second copy of numerical evidence.
- inputs and tests: settings, input definitions and regression tests.

Local tests and evidence replay require no research downloads. Full scientific
reproduction requires the pinned Linux environment.

To include a real R smoke test (four count datasets and six tail datasets), set
`ADJSCOPE_TEST_R` to an existing Rscript executable before `run.py test`.
`ADJSCOPE_TEST_R_LIBRARY` supplies its library path. Non-pinned local validation
requires `ADJSCOPE_TEST_ALLOW_VERSION_DRIFT=1` and does not reproduce full-study results.

[MIT license](LICENSE) covers software and documentation; public datasets retain
their original terms. [Data](docs/DATA.md) | [Methods](docs/METHODS.md) |
[中文说明](README_CN.md)
