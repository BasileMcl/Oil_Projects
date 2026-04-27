# Forward curves — Project 1

ICE Brent · ICE LSGO · ICE WTI · 3-way cross-market. Daily settlements, spans per commodity:

| Commodity | Sample start | Sample end |
|---|---|---|
| Brent | 2019-04 | 2026-04 |
| LSGO  | 2019-12 | 2026-04 |
| WTI   | 2018-10 | 2026-04 |

Different start dates reflect ICE rolling-contract data availability — not a design choice. Brent's 6-plus years is the shortest; WTI's 8 years is the longest. Claims that depend on a long baseline (tail estimation, regime thresholds) are calibrated on the in-sample window `≤ 2024-12-31` in all three cases for consistency.

## TL;DR

- **LSGO** ran Crisis regime **31% of days in 2025–2026** vs 1% under the pre-2025 distribution — 31× rate. M1-M3 record 293.75 USD/MT on 2026-04-02.
- **Brent** Crisis 17% OOS. Dated-vs-M1 spread widened to ≈ $45 on 2026-04-07 *(short Jan-to-Apr-2026 Dated file — treat as event study, not long-run basis)*.
- **WTI** Crisis 13% OOS — tempered vs Brent and LSGO.
- **LSGO-Brent coupling is regime-dependent**: ΔM1-M3 corr ≈ 0.39 in Normal, jumps to 0.81 in Crisis. Current rolling hedge β ≈ 12.7 vs mean 2.85 — static hedges mis-size by ~4.5×.
- **Long-history context (OPEC ASB T74, 1990+)** added to Brent notebook — current Brent level vs 36 years of monthly front-month history. Anchors the regime claim outside the 6-year daily window.

Lead chart: [outputs/figures/brent/chart_12_dated_event_study.png](outputs/figures/brent/chart_12_dated_event_study.png)

Refining margins, stocks, regional dynamics → [../Spot_Cracks_Analysis/](../Spot_Cracks_Analysis/). Term definitions for non-specialists → [../GLOSSARY.md](../GLOSSARY.md). Event timeline overlaid on charts is portfolio-wide: [../major_dates.yaml](../major_dates.yaml).

## Layout

```
src/
  forward_curve_analytics.py   ForwardCurveAnalysis — single-commodity engine
  cross_market.py              CrossMarketAnalysis  — n-way comparison
config.yaml                    per-commodity config + regime thresholds
requirements.txt               inherits ../requirements-base.txt + hmmlearn
generate_reports.sh            runs all 4 notebooks → outputs/reports/

LsGO_Analysis/  Brent_Analysis/  WTI_Analysis/  Cross_Market_Analysis/

outputs/
├── figures/{lsgo,brent,wti,cross_market}/   auto-saved PNGs
└── reports/                                  4 executed HTML reports
```

Portfolio-wide styling comes from `../plot_config.yaml`, event timeline from `../major_dates.yaml`, coding conventions from `../CODING_STANDARDS.md`. `config.yaml` holds only project-specific content (paths, thresholds, snapshot dates, chart filenames).

## Run

```bash
cd Projects/Forward_Curves_Analysis
pip install -r requirements.txt
bash generate_reports.sh
```

Or drive the classes directly:

```python
from src import ForwardCurveAnalysis, CrossMarketAnalysis

fca = ForwardCurveAnalysis(COMMODITY='LSGO').load().build()
fca.chart_full_strip()
fca.chart_hmm_regime()
fca.forecast_next_day_regime()

cma = CrossMarketAnalysis(['LSGO', 'BRENT', 'WTI']).load_all().merge()
cma.chart_correlation_matrix(METRIC='M1_M3')
cma.chart_rolling_hedge_ratio(Y='LSGO', X='BRENT')
```

## Methodology

Pre-rolled ICE settlements (slots M1–M12) map directly to the engine's contract frame. Spreads `M1-M2` / `M1-M3` / `M1-M6` / `M1-M12`, plus a 20-day annualised realised vol. Z-scores are **IS-anchored** (μ, σ from pre-2025, applied uniformly) to avoid rolling-std floor artifacts in calm windows. Regime thresholds are the 80/95/99 percentiles of the in-sample M1-M6 distribution, calibrated on `≤ 2024-12-31` and evaluated OOS. The engine also fits a **2-state Gaussian HMM** on M1-M6 (a 3-state fit was tested — data prefers 2 regimes) and exposes a next-day regime-probability forecast via the transition matrix. Cross-market merges n single-commodity instances on common dates and computes levels, first-differences, log-returns, rolling-60-day and per-year correlations, plus rolling-OLS hedge ratios with 95% CI bands.

## Known pre-rolled-data caveat

The data files are ICE rolling front-month series (`BRN 1!-ICE`, `GAS 1!-ICE`, `WBS 1!-ICE`). This means:
- The individual contract-expiry rolls are **already baked into the series** — the engine reports "pre-rolled ICE series (individual rolls not recoverable)" because roll dates cannot be recovered from the rolled feed.
- Roll-day price jumps are absorbed into return volatility (applied consistently across the three commodities — inter-commodity comparisons are unaffected).

## Limitations

- Sample-length asymmetry: Brent 6y, LSGO 6y, WTI 8y. IS/OOS cutoff identical (`2024-12-31`) keeps comparisons fair.
- **Dated Brent file covers only 2026-01-02 → 2026-04-14** (69 days). Event study, not long-run basis analysis. Extending this manually from June 2022 onwards is the realistic next data-acquisition task.
- Regime thresholds defined on M1-M6 only. Alternative spreads would yield different maps.
- HMM fits on full sample, so the Crisis state is trained on OOS data — descriptive, not predictive.
- Per-year sub-samples are small (2026 YTD ≈ 75 obs); standard errors non-negligible.
- Correlation ≠ causation.

## Known gaps / next-step candidates

- **Pre-2019 daily history** — OPEC ASB T74 added as a monthly 1990+ baseline chart in the Brent notebook. Daily-granularity extension (for HMM fit or regime calibration) still requires a manual data pull.
- **Rolling Kalman hedge ratio** — upgrades the rolling OLS β with state-space CIs.
- **Crack overlay as a diagnostic** in LSGO notebook (one cell reading `../Datas/csv/crack_spreads_clean.csv` and plotting it against LSGO M1-M3).
- **Regime-conditional per-event analysis** — break the regime heatmap by specific events (Hormuz, SPR draws) rather than by quarter.
- **Fundamentals link** — LSGO-Brent cross-market regime against US distillate stocks (from Project 2) to unify curve + stocks stories.
- **T74 context for LSGO / WTI** — only applied to Brent so far. WTI monthly already sits in the same T74 file; LSGO does not (gasoil not tracked in ASB table 74).

Cross-references: [../Spot_Cracks_Analysis/README.md](../Spot_Cracks_Analysis/README.md).
