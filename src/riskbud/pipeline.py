"""Sizing by risk versus sizing by dollars: a multi-asset test on real ETF data, 2006-2026.

Universe (real, public daily prices + dividends, Yahoo Finance via the defeatbeta mirror):
  SPY (US equities), TLT (20+ year Treasuries), GLD (gold), DBC (broad commodities).
Cash and financing: U.S. Treasury 3-month bill yield (Treasury daily par yield curve).

Portfolios (all rules fixed in configs/default.yaml before results were examined):
  60/40        60% SPY, 40% TLT, rebalanced monthly (the industry baseline)
  EQUAL        25% in each of the four assets
  RISK_PARITY  weights proportional to 1 / trailing volatility (unlevered, sums to 100%)
  RP_TARGET    risk-parity weights scaled to a 10% volatility target, leverage capped,
               borrowing at the T-bill rate plus a spread
  6040_TARGET  the 60/40 portfolio scaled to the same 10% volatility target
Weights use only data up to the rebalance date (trailing windows), then are held for the month.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

ASSETS = ["SPY", "TLT", "GLD", "DBC"]


def load_cfg(path):
    return yaml.safe_load(open(path))


def load_daily(raw: Path) -> tuple[pd.DataFrame, pd.Series]:
    c = duckdb.connect()
    syms = ",".join(f"'{s}'" for s in ASSETS)
    px = c.sql(f"select symbol, report_date d, cast(\"close\" as double) as px from '{raw/'prices.parquet'}' "
               f"where symbol in ({syms})").df()
    dv = c.sql(f"select symbol, report_date d, cast(amount as double) dv from '{raw/'stock_dividend_events.parquet'}' "
               f"where symbol in ({syms})").df()
    tb = c.sql(f"select report_date d, cast(bc_3month as double) y from '{raw/'daily_treasury_yield.parquet'}'").df()
    for x in (px, dv, tb):
        x["d"] = pd.to_datetime(x["d"])
    P = px.pivot(index="d", columns="symbol", values="px").sort_index()[ASSETS]
    D = dv.groupby(["d", "symbol"]).dv.sum().unstack().reindex(P.index).reindex(columns=ASSETS).fillna(0.0)
    P = P.dropna()
    D = D.reindex(P.index).fillna(0.0)
    R = (P + D) / P.shift(1) - 1
    R = R.dropna()
    y = tb.set_index("d").sort_index().y
    y = (y / 100 if y.max() > 1 else y).reindex(R.index).ffill()
    return R, y


def check_data(R: pd.DataFrame) -> dict:
    """Guard rails: no unexplained price jumps (splits) and no stale series."""
    big = (R.abs() > 0.25).sum().to_dict()
    assert all(v == 0 for v in big.values()), f"suspicious daily moves: {big}"
    return {"start": str(R.index[0].date()), "end": str(R.index[-1].date()), "days": int(len(R)),
            "max_abs_daily_move": {k: float(v) for k, v in R.abs().max().items()}}


def month_ends(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby(idx.to_period("M")).last().values)


def target_weights(R: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    rebal = month_ends(R.index)
    win = cfg["vol_window_days"]
    out = {k: [] for k in ("60/40", "EQUAL", "RISK_PARITY", "RP_TARGET", "6040_TARGET")}
    for d in rebal:
        hist = R.loc[:d].tail(win)
        if len(hist) < win:
            continue
        vol = hist.std() * np.sqrt(252)
        cov = hist.cov() * 252
        w6040 = pd.Series({"SPY": 0.6, "TLT": 0.4, "GLD": 0.0, "DBC": 0.0})
        weq = pd.Series(0.25, index=ASSETS)
        wrp = (1 / vol) / (1 / vol).sum()
        out["60/40"].append(w6040.rename(d))
        out["EQUAL"].append(weq.rename(d))
        out["RISK_PARITY"].append(wrp.rename(d))
        for name, w in (("RP_TARGET", wrp), ("6040_TARGET", w6040)):
            pvol = float(np.sqrt(w @ cov @ w))
            lev = min(cfg["vol_target"] / pvol, cfg["max_leverage"])
            out[name].append((w * lev).rename(d))
    return {k: pd.DataFrame(v) for k, v in out.items()}


def simulate(R: pd.DataFrame, bill: pd.Series, W: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Daily P&L. Weights set at month-end close apply from the next trading day; drift between rebalances."""
    cost = cfg["cost_bps"] / 1e4
    spread = cfg["borrow_spread_bps"] / 1e4
    days = R.index[R.index > W.index[0]]
    w = pd.Series(0.0, index=ASSETS)
    nxt = iter(list(W.index[1:]) + [None])
    pending = W.iloc[0]
    upcoming = next(nxt)
    rows = []
    for d in days:
        turnover = 0.0
        if pending is not None:
            turnover = float((pending - w).abs().sum())
            w = pending.copy()
            pending = None
        r = R.loc[d]
        cash_w = 1 - w.sum()  # negative = borrowing
        rf = bill.loc[d] / 252
        fin = cash_w * rf + (min(cash_w, 0.0) * spread / 252)
        pnl = float((w * r).sum()) + fin - turnover * cost
        rows.append((d, pnl, float(w.sum()), turnover))
        # drift weights with returns
        gross = 1 + pnl
        w = w * (1 + r) / gross
        if upcoming is not None and d >= upcoming:
            pending = W.loc[upcoming]
            upcoming = next(nxt)
    out = pd.DataFrame(rows, columns=["d", "ret", "gross_exposure", "turnover"]).set_index("d")
    out["rf"] = bill.reindex(out.index) / 252
    return out


def stats(s: pd.DataFrame) -> dict:
    r, rf = s.ret, s.rf
    yrs = len(r) / 252
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    yr = (1 + r).groupby(r.index.year).prod() - 1
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "vol": float(r.std() * np.sqrt(252)),
            "sharpe": float((r - rf).mean() / r.std() * np.sqrt(252)), "max_dd": float(dd.min()),
            "worst_year": float(yr.min()), "worst_year_label": int(yr.idxmin()),
            "y2008": float(yr.get(2008, np.nan)), "y2022": float(yr.get(2022, np.nan)),
            "avg_gross_exposure": float(s.gross_exposure.mean()),
            "turnover_per_year": float(s.turnover.sum() / yrs),
            "start": str(r.index[0].date()), "end": str(r.index[-1].date())}


def risk_contrib(R: pd.DataFrame, W: pd.DataFrame, win: int) -> pd.DataFrame:
    """Share of portfolio variance from each asset at each rebalance (ex ante)."""
    rows = []
    for d, w in W.iterrows():
        cov = R.loc[:d].tail(win).cov()
        mrc = cov @ w
        tot = float(w @ mrc)
        rows.append((w * mrc / tot).rename(d))
    return pd.DataFrame(rows)


def run(cfg_path="configs/default.yaml") -> dict:
    cfg = load_cfg(cfg_path)
    raw, out = Path(cfg["raw_dir"]), Path(cfg["out_dir"])
    (out / "figures").mkdir(parents=True, exist_ok=True)
    R, bill = load_daily(raw)
    res = {"data": check_data(R), "config": cfg}
    W = target_weights(R, cfg)
    sims = {k: simulate(R, bill, w, cfg) for k, w in W.items()}
    start = max(s.index[0] for s in sims.values())
    sims = {k: s[s.index >= start] for k, s in sims.items()}
    res["portfolios"] = {k: stats(s) for k, s in sims.items()}
    # cost stress
    stress = dict(cfg, cost_bps=cfg["cost_bps_stress"], borrow_spread_bps=cfg["borrow_spread_stress_bps"])
    s2 = simulate(R, bill, W["RP_TARGET"], stress)
    res["rp_target_stress_costs"] = stats(s2[s2.index >= start])
    # sub-periods
    cut = cfg["split_date"]
    res["subperiods"] = {k: {"first_half": stats(s[s.index < cut]), "second_half": stats(s[s.index >= cut])}
                         for k, s in sims.items()}
    # risk contributions, average
    rc = {k: risk_contrib(R, W[k], cfg["vol_window_days"]).mean().to_dict() for k in ("60/40", "RISK_PARITY")}
    res["avg_risk_contribution"] = rc
    # rolling stock-bond correlation
    corr = R.SPY.rolling(252).corr(R.TLT)
    res["stock_bond_corr"] = {"avg_2006_2020": float(corr[:"2020"].mean()), "avg_2022_2026": float(corr["2022":].mean()),
                              "min": float(corr.min()), "max": float(corr.max())}
    a = cfg["allocation_usd"]
    b, t = res["portfolios"]["6040_TARGET"], res["portfolios"]["RP_TARGET"]
    res["business"] = {"allocation_usd": a,
                       "max_loss_6040_target_usd": a * b["max_dd"], "max_loss_rp_target_usd": a * t["max_dd"],
                       "max_loss_6040_usd": a * res["portfolios"]["60/40"]["max_dd"],
                       "loss_2022_6040_usd": a * res["portfolios"]["60/40"]["y2022"],
                       "loss_2022_rp_target_usd": a * t["y2022"]}
    json.dump(res, open(out / "metrics.json", "w"), indent=2, default=float)
    figures(out / "figures", sims, rc, corr, W)
    return res


def _yaxis_years(ax, step=2):
    from matplotlib.ticker import MultipleLocator, FuncFormatter
    ax.xaxis.set_major_locator(MultipleLocator(step))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))


def figures(fd: Path, sims, rc, corr, W):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    col = {"60/40": "#8A8880", "6040_TARGET": "#1A1A1F", "EQUAL": "#B9A66A", "RISK_PARITY": "#7FA3C6", "RP_TARGET": "#3A6A9A"}
    lab = {"60/40": "60/40 (unscaled)", "6040_TARGET": "60/40 at 10% vol target", "EQUAL": "Equal weight",
           "RISK_PARITY": "Risk parity (unlevered)", "RP_TARGET": "Risk parity at 10% vol target"}

    def tt(ix):
        return ix.year + (ix.dayofyear - 1) / 365.25

    fig, ax = plt.subplots(figsize=(11, 4.6))
    for k in ("60/40", "6040_TARGET", "RP_TARGET"):
        eq = (1 + sims[k].ret).cumprod()
        ax.plot(tt(eq.index), (eq / eq.cummax() - 1) * 100, color=col[k], lw=1.1, label=lab[k])
    ax.set_title("Drawdown from previous peak, 2006–2026 (daily, after costs)")
    ax.set_ylabel("Drawdown (%)"); _yaxis_years(ax)
    ax.set_ylim(top=2); ax.axhline(0, color="#1A1A1F", lw=0.6)
    ax.legend(frameon=True, facecolor="white", edgecolor="#DDD9CE", framealpha=0.95, loc="lower right", fontsize=9)
    t0 = tt(sims["60/40"].index); ax.set_xlim(t0[0] - 0.2, t0[-1] + 0.2)
    fig.tight_layout(); fig.savefig(fd / "drawdowns.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.4))
    names = ["SPY", "TLT", "GLD", "DBC"]
    pretty = {"SPY": "US equities", "TLT": "Long Treasuries", "GLD": "Gold", "DBC": "Commodities"}
    colors = ["#3A6A9A", "#9A7F2E", "#B9A66A", "#8A8880"]
    left = {"60/40": 0.0, "RISK_PARITY": 0.0}
    for i, n in enumerate(names):
        vals = [rc["60/40"].get(n, 0) * 100, rc["RISK_PARITY"].get(n, 0) * 100]
        ax.barh([1, 0], vals, left=[left["60/40"], left["RISK_PARITY"]], color=colors[i], label=pretty[n])
        for y, v, l in ((1, vals[0], left["60/40"]), (0, vals[1], left["RISK_PARITY"])):
            if v > 6:
                ax.text(l + v / 2, y, f"{v:.0f}%", ha="center", va="center", color="white", fontsize=10)
        left["60/40"] += vals[0]; left["RISK_PARITY"] += vals[1]
    ax.set_yticks([1, 0], ["60/40", "Risk parity"]); ax.set_xlabel("Share of portfolio risk (%)")
    ax.set_title("Where the risk actually comes from (average, 2006–2026)")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=9)
    fig.tight_layout(); fig.savefig(fd / "risk_contribution.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.2))
    c = corr.dropna()
    ax.plot(tt(c.index), c, color="#3A6A9A", lw=1.2)
    ax.axhline(0, color="#1A1A1F", lw=0.8)
    ax.set_title("Stocks and long Treasuries: rolling 1-year correlation of daily returns")
    ax.set_ylabel("Correlation"); _yaxis_years(ax); ax.set_xlim(tt(c.index)[0] - 0.2, tt(c.index)[-1] + 0.2)
    fig.tight_layout(); fig.savefig(fd / "stock_bond_correlation.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    keys = ["60/40", "6040_TARGET", "EQUAL", "RISK_PARITY", "RP_TARGET"]
    sh = [((sims[k].ret - sims[k].rf).mean() / sims[k].ret.std() * np.sqrt(252)) for k in keys]
    ax.bar(range(5), sh, color=[col[k] for k in keys])
    for i, v in enumerate(sh):
        ax.text(i, v + 0.01, f"{v:.2f}", ha="center", va="bottom")
    ax.set_xticks(range(5), [lab[k].replace(" at 10% vol target", "\nat 10% vol").replace(" (", "\n(") for k in keys], fontsize=9)
    ax.set_ylabel("Sharpe ratio (excess of T-bills)"); ax.set_ylim(0, max(sh) * 1.25)
    ax.set_title("Risk-adjusted return, 2006–2026, after trading and financing costs")
    fig.tight_layout(); fig.savefig(fd / "sharpe_by_portfolio.png", dpi=160); plt.close(fig)


if __name__ == "__main__":
    import sys
    r = run(sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml")
    for k, v in r["portfolios"].items():
        print(f"{k:12s} " + " ".join(f"{m}={v[m]:.3f}" for m in ("cagr", "vol", "sharpe", "max_dd", "worst_year", "y2008", "y2022", "avg_gross_exposure", "turnover_per_year")))
    print("stress", {m: round(r["rp_target_stress_costs"][m], 3) for m in ("cagr", "sharpe", "max_dd")})
    print(r["avg_risk_contribution"]); print(r["stock_bond_corr"]); print(r["business"])
    for k, v in r["subperiods"].items():
        print(k, round(v["first_half"]["sharpe"], 2), round(v["second_half"]["sharpe"], 2))
