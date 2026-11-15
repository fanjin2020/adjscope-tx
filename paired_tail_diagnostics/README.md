# Tail and weight-source diagnostics

Integrated stage:
`python run.py run --stages tails --profile full --workers 36 --output NEW_DIR`.

Six scenarios were selected after examining the broad count grid. The full
experiment uses 500 fresh replicates per scenario, 3,000 genes and six arms:
estimated shared/design-specific weights, independent shared/design-specific
weights, fixed unit weights and an independent Gaussian control. Each uses
model-based and HC3 paired standard errors.

Outputs include coverage, BH FDR, Bonferroni error, small-p exceedances, expression
strata and paired arm comparisons. Planned and retained gene families are
separate. Monte Carlo uncertainty is computed over independent datasets.

Gaussian and independent-weight controls diagnose sources of tail distortion.
Neither automatically selects a replacement test. The variance moment-equivalent
degrees of freedom are descriptive, not a substituted testing reference.

Receipt-verified resume is integrated into run.py. Per-replicate metrics and
tail-event records stay in the run directory; compact export includes only the
five Table S23 sections, including Gaussian geometry, and Figs. 10 and S15.
