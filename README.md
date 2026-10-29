# Risk budgeting on real multi-asset data: 60/40 versus risk parity, 2006–2026

> Companion to the article [Your 60/40 Is Really 80/20](https://www.guptagaurav.info/articles/your-60-40-is-really-80-20). Author: Gaurav Gupta.

Five portfolios built from four real ETFs (US equities SPY, long Treasuries TLT, gold GLD, broad commodities DBC), with dividends, T-bill financing and trading costs, rebalanced monthly using only trailing data. The study asks whether sizing by **risk** rather than **dollars** improves a portfolio, and when.

## Headline results (June 2006 – October 2026, after costs; data from February 2006, first three months used to estimate risk)

| Portfolio | CAGR | Volatility | Sharpe | Max drawdown | 2008 | 2022 |
|---|---|---|---|---|---|---|
| 60/40 | 8.4% | 11.1% | 0.63 | -31% | -13.4% | -23.3% |
| 60/40 at 10% vol target | 9.5% | 11.3% | 0.71 | -24% | -14.4% | -18.0% |
| Equal weight | 7.3% | 10.1% | 0.58 | -28% | -9.6% | -8.7% |
| Risk parity (unlevered) | 7.5% | 9.2% | 0.65 | -21% | +0.5% | -10.2% |
| Risk parity at 10% vol target | 8.1% | 11.2% | 0.60 | -27% | -6.0% | -7.6% |

- **60/40 is really 80/20 in risk:** on average 81% of its ex-ante variance came from equities, 19% from Treasuries. Risk parity spread risk as 22% equities, 14% Treasuries, 33% gold, 30% commodities.
- **The stock-bond hedge flipped:** the 1-year correlation of SPY and TLT daily returns averaged -0.41 over 2006–2020 and +0.09 over 2022–2026.
- **Regimes decide the winner:** Sharpe 2006–2015 vs 2016–2026 was 0.91 → 0.55 for volatility-targeted 60/40 and 0.43 → 0.75 for volatility-targeted risk parity.
- **Leverage sized on calm fails in fast crashes:** both volatility-targeted portfolios hit their worst drawdown in Feb–Mar 2020 (risk parity -27% in four weeks).
- Realised volatility of the targeted portfolios was about 11.2% against a 10% target, because volatility is estimated with a lag.
- Cost stress (20 bp turnover, T-bill + 1.50% financing) lowers the levered risk-parity CAGR from 8.1% to 7.5% and Sharpe from 0.60 to 0.55.

Full output: `reports/metrics.json`.

## Data: real, public, pinned by checksum

| Data | Source |
|---|---|
| SPY, TLT, GLD, DBC daily closes and dividend events | Yahoo Finance via [`defeatbeta/yahoo-finance-data`](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data) (ODC-BY) |
| 3-month Treasury bill yield, daily | U.S. Department of the Treasury daily par yield curve, same mirror |

`make ingest` downloads anything missing and stops if a file's sha256 differs from `configs/default.yaml` (downloaded 2026-10-20). Closes are unadjusted; total returns are built from ex-date dividends, and a guard rejects any daily move above 25% (none found).

## Run it

```bash
pip install -r requirements.txt
make all     # ingest + run → reports/metrics.json, reports/figures/*.png
make test    # no-look-ahead, budget/leverage-cap and cost unit tests
```

## Limits

Four ETFs and twenty years cover only a few macro regimes. Institutional risk parity uses more assets, futures and different financing. ETF expense ratios are embedded in prices. Results are not a forecast and not investment advice.

## Citations

- Qian, E. (2005). *Risk Parity Portfolios: Efficient Portfolios Through True Diversification.* PanAgora Asset Management.
- Maillard, S., Roncalli, T. and Teïletche, J. (2010). "The properties of equally weighted risk contribution portfolios." *The Journal of Portfolio Management*, 36(4), 60–70.
- Asness, C. S., Frazzini, A. and Pedersen, L. H. (2012). "Leverage aversion and risk parity." *Financial Analysts Journal*, 68(1), 47–59.
- Moreira, A. and Muir, T. (2017). "Volatility-managed portfolios." *The Journal of Finance*, 72(4), 1611–1644.
- Data mirror: defeatbeta, *yahoo-finance-data* (Hugging Face, ODC-BY).

Code, analysis, charts and text were produced with AI assistance (Claude, by Anthropic) and reviewed by Gaurav Gupta. MIT licence.
