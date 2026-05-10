# Regime state log

Weekly snapshot of the regime classifier output. Each Tuesday before posting, run:

```
python3 scripts/run_matched_beta.py     # refresh beta CSV
python3 scripts/regime_update.py        # print header + append row to this file
```

**Order**: descending by date (most recent first).

| Date | Regime | Days since anchor | beta_30d | beta_60d | beta_latest | EU deficit baseline (Mt/y) |
|---|---|---|---|---|---|---|
| 2026-05-09 | Crisis-2026 | 26 | +1.34 | +1.09 | +1.43 | 29 |
| 2026-05-07 | Crisis-2026 | 24 | +0.92 | +0.66 | +1.17 | 29 |
