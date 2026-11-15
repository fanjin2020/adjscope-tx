# Count-to-paired-contrast calibration

Integrated stage:
`python run.py run --stages counts --profile full --workers 36 --output NEW_DIR`.

Each dataset runs NB counts -> filterByExpr(X0) -> TMM -> voom(adaptive.span=TRUE)
-> two lmFit models -> paired coefficient difference -> BH.
The established paired_weights kernel is used without empirical-Bayes moderation
of the paired variance. Both shared and design-specific weights are evaluated.

Full: 24 scenarios x 1,000 replicates x 3,000 genes.
Pilot: 24 x 20 x 1,000. Smoke: four x one x 250.
Sample sizes: 40, 80, 160; exposure/quality correlation: 0.3 or 0.7.

All paired mean contrasts are null, including genes with exposure effects.
Count generation is exchangeable within exposure strata. TMM/filtering preserve
that exchangeability; expected transformed responses lie in X0's column space.
Unequal depths are redrawn independently; their null is marginal over depth.
Normalization and voom weights are re-estimated for each dataset.

Reports separate planned and retained BH families, availability, coverage,
marginal rejection and dataset-level FDR. Under the global paired null, FDR
equals the probability of any discovery. Wilson intervals use independent
datasets, not genes, as the replication unit.

Resume uses validated receipts; job-only and partial tasks are rerun. Runtime
replicate metrics stay in the run directory. The framework's compact exporter
exports Table S22 and Fig. S14 through the manuscript schema, not tasks or
per-replicate files.
