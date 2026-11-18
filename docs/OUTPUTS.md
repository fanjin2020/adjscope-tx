# Outputs

## Manuscript CSV bundle

`run` exports to `RUN/results/` automatically after all selected stages succeed.
It then renders `RUN/figures/` before reporting the workflow as complete.
`report --source RUN --output NEW_DIR` exports the same layout independently.
Explicit `--study`, `--design`, `--counts` and `--tails` accept completed sources.

| Path | Contents |
| --- | --- |
| tables/Table1.csv ... Table3.csv | Main-paper overview, diagnostic actions and testing families; quantities derived from current summaries |
| tables/TableS1.csv ... TableS23.csv | 98 manuscript sections combined by table number |
| figure_data/*.csv | Eight independent plot inputs; all other plot inputs are explicit views of table sections |
| manifest.csv | Section/figure mapping, columns, types, row counts and SHA256 fingerprints |

Each table has `section` and `record` columns. Columns unused by a section are
blank. The manifest supplies each section's native column list and types.
S2.1 is the reported threshold-crossing union; S4.1 includes the prespecified
display set and the two reported paired-test threshold unions. Full-family
adjusted p-values are retained, never recalculated after display selection.

The full export has exactly 35 CSV files: 3 main tables, 23 supplementary tables,
8 additional figure datasets and one manifest. S20.7 aliases S17.7; its rows are
stored once, with both table IDs retained. Explicit schema projections, not
floating-point equality, determine which files exist. Missing sections and
undeclared files are errors, even if their manifest entries have also been removed.
Partial workflows export only selected stages. Dataset counts in rows apply to
that run; a smoke or pilot run is not publication evidence.

`inputs/publication.json` is the machine-readable schema for tables and figures.
Both computed results and `--kind publication` replay use it. Replay is labeled
`recorded_publication_evidence`; new calculation exports are labeled
`computed_results`. Missing calculation inputs never fall back to the replay.

Raw matrices, task-level metrics, logs, receipts and source snapshots stay in the
run directory for computation and resume. They are not copied into the CSV bundle.
No workbook, per-replicate export, narrative report or review archive is generated.

## Submission correspondence

Main Tables 1-3 are the three main-table CSVs. Supplementary methods (ESM_1)
are authored text; its 15 figures are generated below. The 98 sections of ESM_2
are fully represented by the supplementary CSVs and manifest, without exporting
a redundant workbook. ESM_3 is the framework release archive. The calculation
pipeline does not rewrite the manuscript or reuse old narrative as a new result.

## Figures

The full `run` command produces these files automatically in `RUN/figures/`.
For a separate redraw:

`python run.py figures --source CSV_BUNDLE --output NEW_DIR`

| Output | Contents |
| --- | --- |
| Fig1.pdf ... Fig10.pdf | Ten main figures |
| FigS1.pdf ... FigS15.pdf | Fifteen supplementary figures |
| plot_environment.json | Renderer, packages and font |
| layout_checks.json | Dimensions and text-boundary checks |

Available figure IDs come from the bundle. `--figures 1 10 S15` selects a subset.
TIFF requires `--tiff`; SVG and PNG require `--editable`. All renderers use the
same supplied CSV bundle and preserve manuscript figure numbering.
`RUN/figures.json` is an internal resume receipt; it is not a submission file.
Figures are published together after layout checks, so an interrupted renderer
does not leave a partially completed final figure directory.

## Optional user-data diagnostics

`design`: summary.json and inputs.json.
`compare`: genes.csv, summary.json and inputs.json.
These commands do not run as part of the manuscript CSV export.
