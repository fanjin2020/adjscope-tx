"""Restricted randomization tests with finite-sample calibration for paired contrasts.

The observed contrast direction is held fixed while responses are permuted
within blocks, so the test reflects treatment-assignment randomness and stays
exact under the sharp null without Gaussian or homoscedastic assumptions.
Also provides allocation enumeration and outcome-free information screening.
"""
import numpy as np


def wls_map(design, weights=None):
    """Return the WLS coefficient map A = (X' W X)^-1 X' W."""
    x = np.asarray(design, dtype=float)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError('design must be a finite two-dimensional matrix')
    if np.linalg.matrix_rank(x) != x.shape[1]:
        raise ValueError('design has deficient column rank')
    n = x.shape[0]
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    if w.shape != (n,) or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError('weights must be a positive vector of length n')
    xtw = x.T * w
    return np.linalg.solve(xtw @ x, xtw)


def contrast_direction(design0, design1, target, weights=None):
    """Return the paired contrast d = A1[target] - A0[target] with geometry."""
    a0, a1 = wls_map(design0, weights), wls_map(design1, weights)
    n = design1.shape[0]
    if not 0 <= target < min(design0.shape[1], design1.shape[1]):
        raise ValueError('target column out of range')
    if not np.array_equal(np.asarray(design0)[:, target],
                          np.asarray(design1)[:, target]):
        raise ValueError('target column must be identical in both designs')
    df = n - design1.shape[1]
    leverage = np.sum(np.asarray(design1) * a1.T, axis=1)
    return a1[target] - a0[target], dict(df=df, leverage=leverage, a1=a1)


def restricted_allocations(block_ids, block_counts, n_draws, rng):
    """Draw n_draws allocations with fixed treated counts inside each block."""
    blocks = np.asarray(block_ids)
    unique, inverse = np.unique(blocks, return_inverse=True)
    counts = np.asarray(block_counts)
    if counts.shape != unique.shape:
        raise ValueError('block_counts length must equal the number of blocks')
    n = len(blocks)
    out = np.zeros((n_draws, n))
    for k, label in enumerate(unique):
        members = np.flatnonzero(inverse == k)
        nt = int(counts[k])
        if not 0 <= nt <= len(members):
            raise ValueError(f'treated count out of range for block {label}')
        for b in range(n_draws):
            chosen = rng.choice(members, nt, replace=False)
            out[b, chosen] = 1.0
    return out


def _block_permute(response, block_ids, rng):
    """Permute responses independently within every block."""
    out = np.empty_like(response)
    for lab in np.unique(block_ids):
        members = np.flatnonzero(block_ids == lab)
        out[members] = response[rng.permutation(members)]
    return out


def randomization_test(response, design0, design1, target, block_ids,
                       block_counts=None, n_draws=2000, *, weights=None,
                       continuous=True, rng=None):
    """Exact restricted randomization test for the paired adjusted contrast.

    The observed contrast direction d_obs is fixed; responses are permuted
    within blocks to represent treatment-assignment randomness. Under the
    sharp null the observed statistic is exchangeable with the null draws,
    giving finite-sample calibration regardless of normality or variance.
    block_counts only documents the allocation space and may be omitted.
    """
    y = np.asarray(response, dtype=float)
    if y.ndim == 1:
        y = y[:, None]
    if y.ndim != 2:
        raise ValueError('response must be sample by gene')
    n = y.shape[0]
    if any(np.asarray(d).shape[0] != n for d in (design0, design1)):
        raise ValueError('designs and response must share the sample count')
    if rng is None:
        rng = np.random.default_rng()
    block_ids = np.asarray(block_ids)
    if block_ids.shape != (n,):
        raise ValueError('block_ids length must equal the sample count')

    d_obs, geom = contrast_direction(design0, design1, target, weights)
    delta_obs = d_obs @ y
    g_obs = np.asarray(design1)[:, target]

    null_stats = np.empty((n_draws, y.shape[1]))
    for b in range(n_draws):
        null_stats[b] = d_obs @ _block_permute(y, block_ids, rng)

    rank = np.sum(np.abs(null_stats) >= np.abs(delta_obs), axis=0)
    if continuous:
        p_values = (rank + rng.uniform(size=y.shape[1])) / (n_draws + 1)
    else:
        p_values = (1 + rank) / (n_draws + 1)

    return dict(p_values=p_values, delta=delta_obs, rank=rank, df=geom['df'],
                n_draws=n_draws, continuous=continuous,
                observed_treatment=g_obs)


def information_screen(df, ewi=None, min_df=5, min_ewi=None):
    """Decide from design-only quantities whether a contrast is testable."""
    if df < min_df:
        return False, 'insufficient_residual_df'
    if min_ewi is not None and (ewi is None or ewi < min_ewi):
        return False, 'insufficient_information'
    return True, 'estimable'
