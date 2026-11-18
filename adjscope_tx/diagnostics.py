"""Design geometry and paired coefficient comparisons using the tested kernels."""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import t

from design_benchmark.geometry import design_diagnostics
from pipeline.calibration import geometry, evaluate


def diagnose_design(exposure, groups, covariates=None):
    result = design_diagnostics(exposure, groups, covariates)
    result['interpretation'] = 'Design information and estimability; no design-only FDR guarantee.'
    return result


def adjust_bh(pvalues):
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1 or not len(p) or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError('BH requires a nonempty finite vector of probabilities')
    order = np.argsort(p, kind='stable')
    ranked = p[order] * len(p) / np.arange(1, len(p) + 1)
    result = np.empty(len(p))
    result[order] = np.minimum(1, np.minimum.accumulate(ranked[::-1])[::-1])
    return result


def compare_models(response, baseline, adjusted, *, weights=None, target=1,
                   variance='model', alpha=0.05, gene_ids=None):
    """Paired comparisons for fixed, shared positive weights and nested designs.

    Response rows are samples; columns are genes. The target column must be
    identical in both designs. The BH family contains every supplied gene;
    unavailable tests receive p=1 for adjustment and are explicitly marked.
    HC3 uses the adjusted-model leverage and residual degrees of freedom.
    Counts must first be normalized externally; this API does not run voom.
    """
    y, x0, x1 = [np.asarray(x, dtype=float) for x in (response, baseline, adjusted)]
    if y.ndim == 1:
        y = y[:, None]
    if y.ndim != 2 or not y.shape[1] or x0.ndim != 2 or x1.ndim != 2:
        raise ValueError('Use sample-by-gene responses and two-dimensional designs')
    if any(not np.isfinite(x).all() for x in (y, x0, x1)):
        raise ValueError('Responses and designs must be finite; specify one common sample set')
    if len(y) != len(x0) or len(y) != len(x1) or x1.shape[1] <= x0.shape[1]:
        raise ValueError('Designs must align and the adjusted design must add columns')
    if isinstance(target, bool) or not isinstance(target, (int, np.integer)) or not 0 <= target < min(x0.shape[1], x1.shape[1]):
        raise ValueError('Invalid target column')
    if not np.array_equal(x0[:, target], x1[:, target]):
        raise ValueError('Target column must be identical in both designs')
    if variance not in ('model', 'hc3') or not 0 < alpha < 1:
        raise ValueError('Choose model/hc3 variance and alpha in (0,1)')
    ids = list(map(str, range(y.shape[1]))) if gene_ids is None else list(map(str, gene_ids))
    if len(ids) != y.shape[1] or len(set(ids)) != len(ids) or any(not v.strip() for v in ids):
        raise ValueError('Gene IDs must be unique, nonempty and aligned')
    w = np.ones(len(y)) if weights is None else np.asarray(weights, dtype=float)
    if w.ndim != 1 or len(w) != len(y):
        raise ValueError('Weights must be a shared sample vector')
    g = geometry(x0, x1, w, target)
    beta0, beta1 = g['a0'][target] @ y, g['a1'][target] @ y
    with np.errstate(divide='ignore', invalid='ignore'):
        delta, se_model, se_hc3, _ = evaluate(y, g)
    residual0 = y - x0 @ (g['a0'] @ y)
    residual1 = y - x1 @ (g['a1'] @ y)
    a0, a1 = g['a0'][target], g['a1'][target]
    if variance == 'model':
        sigma0 = (w[:, None] * residual0**2).sum(axis=0) / (len(y) - x0.shape[1])
        sigma1 = (w[:, None] * residual1**2).sum(axis=0) / g['df']
        se0 = np.sqrt(sigma0 * np.sum(a0*a0/w))
        se1 = np.sqrt(sigma1 * np.sum(a1*a1/w))
        se = se_model
    else:
        h0 = np.sum(x0 * g['a0'].T, axis=1)
        if h0.max() >= 1 - 1e-10:
            raise ValueError('Baseline leverage is too high for HC3')
        se0 = np.sqrt((a0*a0 / (1-h0)**2) @ residual0**2)
        se1 = np.sqrt((a1*a1 / (1-g['h'])**2) @ residual1**2)
        se = se_hc3
    nondegenerate = np.linalg.norm(g['d']) > 1e-12 * max(np.linalg.norm(a0), np.linalg.norm(a1))
    usable = np.isfinite(se) & (se > 1e-12) & nondegenerate
    p = np.ones(y.shape[1])
    p[usable] = 2 * t.sf(np.abs(delta[usable]/se[usable]), g['df'])
    q = adjust_bh(p)
    critical = t.ppf(1-alpha/2, g['df'])
    rows = []
    for j, gene in enumerate(ids):
        rows.append(dict(gene_id=gene, beta_baseline=float(beta0[j]), beta_adjusted=float(beta1[j]),
                         delta=float(delta[j]), se_baseline=float(se0[j]), se_adjusted=float(se1[j]),
                         se_ratio=float(se1[j]/se0[j]) if se0[j] > 1e-12 else None,
                         paired_se=float(se[j]) if usable[j] else None,
                         ci_lower=float(delta[j]-critical*se[j]) if usable[j] else None,
                         ci_upper=float(delta[j]+critical*se[j]) if usable[j] else None,
                         p_value=float(p[j]) if usable[j] else None, q_value=float(q[j]),
                         bh_threshold_crossing=bool(usable[j] and q[j] <= alpha),
                         status='available' if usable[j] else 'unavailable'))
    return dict(summary=dict(samples=len(y), genes=y.shape[1], testing_family=y.shape[1],
                            available=int(usable.sum()), variance=variance, reference_df=g['df'], alpha=alpha,
                            bh_threshold_crossings=sum(r['bh_threshold_crossing'] for r in rows),
                            calibration_scope='Conditional fixed-weight comparison. BH crossings do not establish FDR calibration for estimated weights.'),
                genes=rows)


def read_numeric_csv(path, id_column='sample_id'):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if id_column not in columns or len(columns) != len(set(columns)):
            raise ValueError('Unique column names and sample_id are required: ' + str(path))
        rows = list(reader)
    ids = [r[id_column] for r in rows]
    if not ids or any(not v.strip() for v in ids) or len(set(ids)) != len(ids):
        raise ValueError('Sample IDs must be unique and nonempty')
    names = [n for n in columns if n != id_column]
    values = np.asarray([[float(r[n]) for n in names] for r in rows])
    if not names or not np.isfinite(values).all():
        raise ValueError('Numeric columns must be finite and nonempty')
    return ids, names, values
