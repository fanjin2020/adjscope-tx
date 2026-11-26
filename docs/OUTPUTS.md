# Outputs

## Manuscript CSV bundle

`run` exports to `RUN/results/` automatically after all selected stages succeed.
It then renders `RUN/figures/` before reporting the workflow as complete.
`report --source RUN --output NEW_DIR` exports the same layout independently.
Explicit `--study`, `--design`, `--counts` and `--tails` accept completed sources.

| Path | Contents |
| --- | --- |
| tables/Table1.csv ... Table3.csv | Main-paper overview, diagnostic actions and testing families; quantities derived from current summaries |
| tables/TableS1.csv ... TableS23.csv | 100 CMPB supplementary sections combined by table number |
| Supplementary_Tables.xlsx | Complete export only: Catalogue plus S01-S23, generated from the same section frames |
| figure_data/*.csv | Eight independent plot inputs; all other plot inputs are explicit views of table sections |
| manifest.csv | Section/figure mapping, columns, types, row counts and SHA256 fingerprints |

Each table has `section` and `record` columns. Columns unused by a section are
blank. The manifest supplies each section's native column list and types.
S2.1 is the reported threshold-crossing union; S4.1 includes the prespecified
display set and the two reported paired-test threshold unions. Full-family
adjusted p-values are retained, never recalculated after display selection.

Alongside the workbook, the full export has 35 CSV files: 3 main tables, 23 supplementary tables,
8 additional figure datasets and one manifest. S20.7 aliases S17.7; its rows are
stored once, with both table IDs retained. Explicit schema projections, not
floating-point equality, determine which files exist. Missing sections and
undeclared files are errors, even if their manifest entries have also been removed.
Partial workflows export only selected stages. Dataset counts in rows apply to
that run; a smoke or pilot run is not publication evidence.

`inputs/publication.json` defines the original tables and figures; `adjscope_tx/cmpb_sections.py`
adds S9.5 and S11.7. Both computed results and `--kind publication` replay use these definitions. Replay is labeled
`recorded_publication_evidence`; new calculation exports are labeled
`computed_results`. Missing calculation inputs never fall back to the replay.

Raw matrices, task-level metrics, logs, receipts and source snapshots stay in the
run directory for computation and resume. They are not copied into the CSV bundle.
No per-replicate export, narrative report or review archive is generated.

## Submission correspondence

The CMPB workbook contains 100 sections (15,853 rows in the recorded evidence, including
the declared S20.7 alias). Its S22.1 presentation omits the planned gene-count field
used by the figure code; that field remains in the CSV. The original main-table and
figure mappings are unchanged. No Word manuscript or supplementary methods text is rewritten.

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

## CMPB main figures

For the CMPB main plates, use `python run.py figures --layout cmpb --source CSV_BUNDLE --output NEW_DIR`.
Use an independent interpreter with `artwork/cmpb/requirements.txt` (select it via `--python` if necessary).
The required input is one verified complete publication or workflow export. The six individual files
`Figures/Figure_1.pdf` through `Figure_6.pdf` are the figure deliverables. The combined
`All_Figures_Proof.pdf`, six PNGs in `Preview/` and `Checks/figure_audit.json` are for local review only.
No model is refitted. The layout verifies the paper-specific numerical annotations and the minimum
9 mm of white space above and below every figure. Existing output directories are not overwritten.

## CMPB supplementary figures

`python run.py figures --layout cmpb-supplement --source CSV_BUNDLE --output NEW_DIR`
uses the same plotting environment and full export. It produces `Figure_S1.pdf`
through `Figure_S20.pdf` and one `receipt.json` (input, renderer and output
hashes, font, package versions and top/bottom blank bands in points).
Fig. S9 is the paired-test comparison from S20.5, not the archived diagram.

## Independent paired-test check

`python run.py check-limma --output NEW_FILE.json` generates one receipt and
no figure or gene table. It reports the two maximum absolute discrepancies, tolerance,
software versions, input fingerprint and kernel hashes. The supplied reference
receipt is the original locked server result, not a substitute for running the check.

## Optional user-data diagnostics

`design`: summary.json and inputs.json.
`compare`: genes.csv, summary.json and inputs.json.
These commands do not run as part of the manuscript CSV export.
