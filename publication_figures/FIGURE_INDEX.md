# Publication Figure Index

This order accompanies "AdjScope-Tx: a diagnostic framework for covariate
adjustment in transcriptomic analysis". Computed and recorded-evidence figures
use this same order, defined in `inputs/publication.json`.

## Main Figures

| Figure | Comparison | Supplementary source |
| --- | --- | --- |
| 1 | Count-to-inference FDR, power and interval coverage | S20.10 |
| 2 | Cage means and residual correlation | S17.1 |
| 3 | Within-cage genotype overlap | S17.1 |
| 4 | General paired coefficient-test calibration | S20.5 |
| 5 | Human coefficient estimates and discovery thresholds | figure_data/clinical_pairs.csv |
| 6 | Multiple-testing families | S3.6; figure_data/family_sizes.csv |
| 7 | Seven mouse analysis arms | S12.7-S12.8; figure_data/mouse_se_ratios.csv |
| 8 | Precision components and design information | S14.1; figure_data/precision_components.csv |
| 9 | Design information and conditional screening | S21.1-S21.2, S21.4, S21.7 |
| 10 | Paired-test coverage, FDR, Bonferroni and extreme tails | S23.1-S23.2 |

## Supplementary Figures

| Figure | Comparison | Supplementary source |
| --- | --- | --- |
| S1 | Human donor quality | S5.5 |
| S2 | Astrocyte coefficient estimates | S8.2 |
| S3 | Mouse panel consistency and focal genes | S13.3; figure_data/mouse_focal.csv |
| S4 | Cage ICC and precision | S15.4; figure_data/icc_density.csv |
| S5 | Cage allocation, rejection and power | S17.1 |
| S6 | Coefficient and precision changes across human contexts | figure_data/human_contexts.csv |
| S7 | Design-only precision approximation | S16.4; figure_data/design_errors.csv |
| S8 | Joint F and paired tests | S20.1 |
| S9 | Diagnostic workflow | Conceptual diagram; no numerical input |
| S10 | Selected human coefficient/SE components | S4.4 |
| S11 | Donor-conditioned calibration | S20.1 |
| S12 | Cancellation and paired-test power | S20.5 |
| S13 | Analytical and simulated cage-mean bias | S21.1, S21.3 |
| S14 | Full count paired-null coverage and both BH families | S22.1 |
| S15 | Six-arm tail controls with Monte Carlo intervals | S23.1 |

The exported bundle's `manifest.csv` maps every figure to its CSV inputs, columns
and checksums. `inputs/evidence/manifest.csv` describes the single recorded
evidence store included for verification and explicit replay.

For Fig. 7, `figure_data/mouse_se_ratios.csv` contains 36 specification-by-arm median SE
ratios derived from the gene-level seven-arm table. It is included alongside the
42-row arm summary and 30-row matched comparison summary.

`figures --source CSV_BUNDLE` renders the chosen computed or replay bundle.
It never reads fixed evidence as a substitute for missing calculation outputs.
