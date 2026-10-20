"""Unit tests: weights use only past data, budgets and caps hold, costs bite."""
import numpy as np
import pandas as pd

from riskbud.pipeline import ASSETS, simulate, target_weights

CFG = {"vol_window_days": 63, "vol_target": 0.10, "max_leverage": 2.0, "cost_bps": 5, "borrow_spread_bps": 50}


def _returns(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    vols = np.array([0.18, 0.12, 0.15, 0.20]) / np.sqrt(252)
    return pd.DataFrame(rng.normal(0.0002, vols, (n, 4)), index=idx, columns=ASSETS)


def test_weights_have_no_lookahead():
    R = _returns()
    W1 = target_weights(R, CFG)["RISK_PARITY"]
    R2 = R.copy(); R2.iloc[400:] *= 5
    W2 = target_weights(R2, CFG)["RISK_PARITY"]
    common = W1.index[W1.index < R.index[400]]
    pd.testing.assert_frame_equal(W1.loc[common], W2.loc[common])


def test_unlevered_weights_sum_to_one_and_leverage_capped():
    W = target_weights(_returns(), CFG)
    assert np.allclose(W["RISK_PARITY"].sum(axis=1), 1.0)
    assert (W["RP_TARGET"].sum(axis=1) <= CFG["max_leverage"] + 1e-9).all()


def test_risk_parity_overweights_calm_asset():
    W = target_weights(_returns(), CFG)["RISK_PARITY"].mean()
    assert W["TLT"] > W["DBC"]


def test_costs_reduce_returns():
    R = _returns(); bill = pd.Series(0.02, index=R.index)
    W = target_weights(R, CFG)["RP_TARGET"]
    a = simulate(R, bill, W, CFG).ret.sum()
    b = simulate(R, bill, W, dict(CFG, cost_bps=50)).ret.sum()
    assert b < a
