# How this project works

Two diagrams:
1. **Pipeline**: every step, its source file, and the logic inside it.
2. **Monthly sizing decision**: how each portfolio's weights are set at a rebalance.

Colour key: **blue** = external data source · **lavender** = code step · **yellow** = rule or model · **red** = check or gate · **grey** = output

## 1. Pipeline (what `make all` runs)

```mermaid
flowchart TD
    A["SOURCE: SPY, TLT, GLD, DBC daily closes + dividend events<br/>(Yahoo Finance) · U.S. Treasury 3-month bill yield, daily<br/>mirror: huggingface.co/datasets/defeatbeta/yahoo-finance-data"]
    I{"ingest.py<br/>sha256 matches config?"}
    A --> I
    I -- "no" --> X["Stop: source changed"]
    I -- "yes" --> L["Total returns with ex-date dividends · common history from Feb 2006"]
    L --> G{"Data checks: no daily move > 25%<br/>(catches unrecorded splits)"}
    G --> W["Month-end rebalance: weights from the trailing 63 trading days only"]

    subgraph P["Five portfolios · pipeline.py"]
      P1["60/40 SPY/TLT"]
      P2["Equal weight, 25% each"]
      P3["Risk parity: weight ∝ 1 / volatility"]
      P4["Risk parity scaled to 10% volatility, leverage ≤ 2x"]
      P5["60/40 scaled to 10% volatility, leverage ≤ 2x"]
    end

    W --> P
    P --> S["Daily simulation: trade at next day's prices, weights drift between rebalances<br/>5 bp per unit of turnover · borrowing at T-bill + 0.50%"]
    S --> T["Tests: full period · 2006–15 vs 2016–26 · 2008 and 2022 · cost and financing stress (20 bp, T-bill + 1.50%)<br/>risk contribution by asset · rolling stock-bond correlation"]
    T --> O["reports/metrics.json · reports/figures/*.png"]

    classDef src fill:#dbe8ff,stroke:#1f5fbf,color:#0b1f44
    classDef step fill:#ece8ff,stroke:#6b5fbf,color:#1d1640
    classDef rule fill:#fff4cc,stroke:#b38f00,color:#3d3000
    classDef gate fill:#ffe0e0,stroke:#c03030,color:#400000
    classDef out fill:#eeeeee,stroke:#777,color:#222
    class A src
    class L,W,S,T step
    class P1,P2,P3,P4,P5 rule
    class I,X,G gate
    class O out
```

## 2. Monthly sizing decision

```mermaid
flowchart LR
    H["Last 63 trading days<br/>of daily returns"] --> V["Volatility of each asset<br/>and covariance matrix"]
    V --> RP["Risk parity weights<br/>w = (1/σ) / Σ(1/σ)"]
    V --> PV["Expected portfolio volatility<br/>√(wᵀ Σ w)"]
    RP --> PV
    PV --> LEV{"Scale = 10% / expected vol<br/>capped at 2x"}
    LEV --> OUT["Target weights for next month<br/>(cash or borrowing = 1 − Σw)"]
    classDef src fill:#dbe8ff,stroke:#1f5fbf,color:#0b1f44
    classDef step fill:#ece8ff,stroke:#6b5fbf,color:#1d1640
    classDef gate fill:#ffe0e0,stroke:#c03030,color:#400000
    classDef out fill:#eeeeee,stroke:#777,color:#222
    class H src
    class V,RP,PV step
    class LEV gate
    class OUT out
```
