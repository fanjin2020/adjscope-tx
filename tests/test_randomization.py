"""受限随机化检验的单元测试：理论性质、校准与边界。"""
import numpy as np
import pytest

from adjscope_tx.randomization import (wls_map, contrast_direction,
                                       restricted_allocations,
                                       randomization_test, information_screen)


@pytest.fixture
def simple_design():
    rng = np.random.default_rng(0)
    K, m = 6, 4
    n = K * m
    block_ids = np.repeat(np.arange(K), m)
    counts = np.repeat([1, 2], 3)
    g = np.zeros(n)
    for k in range(K):
        idx = k * m + rng.choice(m, counts[k], replace=False)
        g[idx] = 1.0
    c = rng.normal(size=n)
    X0 = np.column_stack([np.ones(n), g, c])
    X1 = np.column_stack([np.ones(n), g, c,
                          np.repeat(np.eye(K)[:, :K - 1], m, axis=0)])
    return X0, X1, block_ids, counts


def test_contrast_orthogonal_to_residual(simple_design):
    X0, X1, _, _ = simple_design
    d, geom = contrast_direction(X0, X1, target=1)
    rng = np.random.default_rng(3)
    y = rng.normal(size=(X1.shape[0], 20))
    e1 = y - X1 @ (geom['a1'] @ y)
    assert np.allclose(d @ e1, 0.0, atol=1e-10)


def test_restricted_allocations_counts(simple_design):
    X0, X1, block_ids, counts = simple_design
    rng = np.random.default_rng(5)
    draws = restricted_allocations(block_ids, counts, 50, rng)
    for b in range(50):
        for k in range(len(counts)):
            members = np.flatnonzero(block_ids == k)
            assert int(draws[b, members].sum()) == int(counts[k])
    assert set(np.unique(draws)).issubset({0.0, 1.0})


def test_randomization_calibration(simple_design):
    X0, X1, block_ids, counts = simple_design
    rng = np.random.default_rng(12)
    n = X1.shape[0]
    rejections, total = 0, 0
    for _ in range(30):
        y = rng.normal(size=(n, 40))
        out = randomization_test(y, X0, X1, 1, block_ids, counts,
                                 n_draws=500, rng=rng)
        rejections += int(np.sum(out['p_values'] < 0.05))
        total += 40
    assert rejections / total < 0.09
    assert out['p_values'].min() >= 0 and out['p_values'].max() <= 1


def test_calibration_stable_across_seeds():
    def build(seed):
        rng = np.random.default_rng(seed)
        K, m = 6, 4; n = K * m
        block_ids = np.repeat(np.arange(K), m)
        counts = np.tile([1, 2], 3)
        g = np.zeros(n)
        for k in range(K):
            g[k*m+rng.choice(m, counts[k], replace=False)] = 1.0
        c = rng.normal(size=n)
        X0 = np.column_stack([np.ones(n), g, c])
        X1 = np.column_stack([np.ones(n), g, c,
                              np.repeat(np.eye(K)[:, :K-1], m, axis=0)])
        return X0, X1, block_ids, counts, rng, n

    for seed in (1, 2, 3):
        X0, X1, block_ids, counts, rng, n = build(seed)
        rates = []
        for _ in range(12):
            y = rng.normal(size=(n, 30))
            out = randomization_test(y, X0, X1, 1, block_ids, counts,
                                     n_draws=400, rng=rng)
            rates.append(np.mean(out['p_values'] < 0.05))
        assert np.mean(rates) < 0.10


def test_discrete_p_superuniform(simple_design):
    X0, X1, block_ids, counts = simple_design
    rng = np.random.default_rng(7)
    n = X1.shape[0]
    y = rng.normal(size=(n, 100))
    out = randomization_test(y, X0, X1, 1, block_ids, counts,
                             n_draws=400, continuous=False, rng=rng)
    assert out['p_values'].min() >= 1 / 401


def test_information_screen():
    assert information_screen(df=10) == (True, 'estimable')
    assert information_screen(df=3) == (False, 'insufficient_residual_df')
    ok, status = information_screen(df=10, ewi=0.2, min_ewi=0.3)
    assert ok is False and status == 'insufficient_information'
    assert information_screen(df=10, ewi=0.5, min_ewi=0.3)[0] is True


def test_rank_deficient_raises():
    x = np.array([[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]])
    with pytest.raises(ValueError):
        wls_map(x)


def test_target_mismatch_raises(simple_design):
    X0, X1, _, _ = simple_design
    X1b = X1.copy(); X1b[:, 1] = X1[:, 1] * 2
    with pytest.raises(ValueError):
        contrast_direction(X0, X1b, 1)
