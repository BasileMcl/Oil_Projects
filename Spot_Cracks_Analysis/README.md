# Spot cracks analysis — Project 2

NWE / Med refining margins · US + EU fundamentals · regional dynamics · flows.

| Data | Span | Source |
|---|---|---|
| Platts NWE products (ULSD / EBOB / FO) | 2019-01 → 2026-04 | merged `Spot_prices.xlsx` |
| Brent / WTI / ULSD Med spot | 2021-04 → 2026-04 | merged `Spot_prices.xlsx` |
| US EIA weekly stocks (crude, SPR, products) | 1990 → 2026 | EIA STEO |
| US EIA weekly refinery utilisation | 1982 → 2026 | EIA weekly petroleum status (**new**) |
| US EIA monthly refinery yields | 1993 → 2026 | EIA (**new**) |
| EU Eurostat monthly stocks (aggregate + per country) | 2013 → 2026 | Eurostat `nrg_stk_m` |
| EU Eurostat monthly refinery supply-transformation | 2018 → 2026 | Eurostat `nrg_cb_oilm` (**new**) |
| EU Eurostat monthly gross inland deliveries (consumption) | 2018 → 2026 | Eurostat `nrg_cb_oilm` (**new**) |
| Vortexa / Kpler monthly floating storage | 2015 → 2026 | Vortexa |
| Russia diesel exports / EU diesel imports (cargo-level) | 2023-03 → 2026-04 | Vortexa |
| OPEC ASB 2025 (T43/T52/T53/T62/T63/T74/T76) | 1980 → 2024 | OPEC (**new**) |
| OPEC MOMR April 2026 (highlights, 3-8) | — | OPEC (**new**) |

---

## TL;DR

- **NWE 3-2-1 refining margin** peaked ≈ 105 USD/bbl on **2022-06-06** (post-invasion refinery squeeze). OOS mean 21.6 USD/bbl; ≈ 10% of days sit below zero across every slate.
- **SPR drawdown ≈ 45%** from 2022 peak — dominant US petroleum-policy story of the decade.
- **US refinery utilisation 89-91%** — mid-range vs full EIA 43-year history (44th pct), top third vs last 5y. Tight-but-not-extreme — unusual given the diesel-crack stress.
- **Distillate yield tilt −17 pp** (gasoline still dominant). US refiners have not structurally swung toward distillate despite the 2026 diesel squeeze.
- **OPEC ASB cross-check**: our Platts-derived Brent-ULSD NWE crack aligns with OPEC's Rotterdam gasoil crack on overlap years (r ≈ 1.0 over 4 annual obs) — methodology anchored to an external authority.
- **EU diesel structural deficit ≈ 29 Mt/year** — consumption (gross inland deliveries) exceeds refinery output by that margin on the 2018+ sample. That imported barrel sets the NWE price.
- **Volumetric P&L at today's crack**: a 100 kbpd refinery at 90% utilisation earns ≈ $1.1 B/year gross at the current 3-2-1 of $33.86/bbl, vs $765 M/year at the full-sample mean.
- **Crack HMM**: 2 regimes (Normal μ=$20.87, 62% days; Elevated μ=$27.17, 38% days). Currently in Elevated with 99% stay-probability over the next 5 days.
- **Rolling hedge β (60d)** = 0.27 today vs sample mean 0.34 — within 1σ. Static hedges would size ≈ 25% too conservatively.
- **Med ↔ NWE ULSD** move at level correlation > 0.99 — one European diesel market in practice.
- **Brent > WTI** on ~95% of days; mean trans-Atlantic spread ≈ +$4/bbl.

Lead chart: [outputs/figures/executive/chart_01_dashboard.png](outputs/figures/executive/chart_01_dashboard.png)

---

## Layout

```
src/
  core.py                     DataLoader + Chartable mixin (shared)
  crack_spread.py             CrackSpreadAnalysis       NWE/Med slates, regime, OPEC cross-check
  fundamentals.py             FundamentalsAnalysis      stocks, SPR, refinery util long+yields, EU intake
  regional.py                 RegionalAnalysis          Med/NWE, Brent-WTI, FX, flows, OPEC trade + freight

config.yaml                   paths (incl. 11 new data files), thresholds, chart keys
generate_reports.sh           runs all 4 notebooks → outputs/reports/
requirements.txt              inherits ../requirements-base.txt

notebooks/
  00_Executive_Summary.ipynb    dashboard, headline numbers, MOMR-April-2026 callout, **trading ideas**
  01_Market_Overview.ipynb      crack slates, distribution, CDF+HMM regime, P&L scaling, rolling β, Med-NWE, bootstrap seasonality, OPEC cross-check
  02_Fundamentals.ipynb         US/EU stocks, SPR, refinery util (5y + 43y), yields, EU intake, EU consumption, stocks↔crack
  03_Regional_Analysis.ipynb    Brent-WTI, Russia, EU imports, premium, OPEC trade flows, OPEC freight, FX

outputs/
  figures/{cracks,fundamentals,regional,executive}/   35+ saved charts
  reports/                                             4 executed HTML reports
```

Portfolio-wide styling: [../plot_config.yaml](../plot_config.yaml). Event timeline: [../major_dates.yaml](../major_dates.yaml). Data layer: [../Datas/](../Datas/). Term definitions: [../GLOSSARY.md](../GLOSSARY.md).

## Run

```bash
cd Projects/Spot_Cracks_Analysis
pip install -r requirements.txt
bash generate_reports.sh
```

Or drive the three classes directly:

```python
from src import CrackSpreadAnalysis, FundamentalsAnalysis, RegionalAnalysis

cs = CrackSpreadAnalysis().load().build(SLATE='3-2-1', REGION='NWE')
cs.chart_time_series(); cs.chart_regime(); cs.chart_opec_crosscheck()

fa = FundamentalsAnalysis().load()
fa.chart_us_util_long(); fa.chart_us_yields(); fa.chart_eu_refinery_intake()

ra = RegionalAnalysis().load()
ra.chart_brent_wti_spread(); ra.chart_opec_trade_flows(); ra.chart_opec_tanker_freight()
```

---

## Methodology (one paragraph)

Three OOP classes consume the shared portfolio data layer via `DataLoader` and share plot primitives via `Chartable` mixin. **CrackSpreadAnalysis** unit-aligns Platts USD/MT spot products (ULSD, EBOB, FO) to USD/bbl via industry-standard bbl/MT conversions (7.45, 8.33, 6.35) and computes per-barrel-of-crude margin for 5 slates (3-2-1, 2-1-1, ULSD, EBOB, FO35) in either NWE or Med regional flavour; regimes are CDF-calibrated on the 2019–2024 IS window (1/5/95/99 quantiles, symmetric), applied OOS unchanged. **FundamentalsAnalysis** loads EIA weekly commercial + SPR + product stocks, EIA long-history weekly refinery utilisation (1982+), EIA monthly yields (1993+), Eurostat monthly aggregate + per-country stocks, Eurostat monthly refinery crude intake + distillate output (2018+), and Vortexa floating storage; reports percentile rank over trailing 5 years for each series. **RegionalAnalysis** merges spot / FX / cargo-level flows / OPEC ASB country-level exports and WS% freight routes; computes Med ↔ NWE level and Δ correlations, Brent-WTI distribution, rolling 60-day ΔEUR/USD ↔ ΔCrack correlation, Russia-export and EU-import origin mix, diesel-gas premium, and global trade flow rankings + 10y trajectory + freight regimes. All three share palette and adaptive x-axis formatting.

---

## Known data caveats

- **OPEC ASB tables are annual** — T52/T53 trade flows and T62/T63 freight give structural context, not monthly/real-time. Use Vortexa for real-time flows; ASB for "who ranks where".
- **OPEC ASB T76 cracks are annual averages, product-spec specific** — Rotterdam gasoil 10 ppm is the closest analogue to our Platts-derived ULSD NWE; spec and region differ, so a level offset is expected. Use the cross-check for *directional* validation only.
- **OPEC MOMR April 2026 figures** quoted in the Executive Summary (OPEC Basket $116, Brent $99, WTI $91, DoC production −7.7 mb/d m-o-m) are the monthly means — they sit below our daily peaks because they include both pre-spike and post-spike days. Period average vs price path.
- **EU refinery intake trailing months**: Eurostat has a 2-3 month publication lag. Months with <10 reporting countries are filtered out — the final published month usually shows 1-2 early filers.
- **UK post-Brexit**: drops out of Eurostat aggregates after Dec 2020 — UK-band going to zero on 2021-01-01 in the EU stocks / intake chart is a perimeter change, not a capacity collapse.
- **Italy reporting gaps**: occasional missing monthly observations (late filing). Stacked-area gaps are reporting artefacts, not actual stock collapses.
- **Dated Brent window** only 2026-01-02 → 2026-04-14 (69 days). Treat as event study, not long-run basis.
- **US EIA weekly** has some early columns (1982-88) with partial coverage — yields start only from 1993, HGL yield only from 2010.

## Limitations

- **5-year spot window** for Brent / WTI / Med ULSD — pre-2021 crude-spot comparisons not possible with current data. NWE products have the full 8-year window.
- **Refinery utilisation and yields** are US-only. EU has supply-transformation (intake/output kt) but not utilisation-%.
- **Cargo-level flows** (Vortexa) start Mar-2023 — 3 years of coverage. Fine for regime-window comparison, thin for long-run trend.
- **IS/OOS cutoff 2024-12-31** matches Project 1. Some OOS events sit inside a very short window; interpret OOS regime counts with care.
- **MOMR April 2026 extracted text** contains large m-o-m moves consistent with the current dislocation — not a normal print; quoted verbatim for context.
- Correlation ≠ causation. Structural claims in markdown are economically motivated, not identified.

---

## Cross-references

- **Forward-curve regimes and HMM** for the same commodities: [../Forward_Curves_Analysis/](../Forward_Curves_Analysis/)
- **Portfolio coding standards**: [../CODING_STANDARDS.md](../CODING_STANDARDS.md)
- **Geopolitical event timeline**: [../major_dates.yaml](../major_dates.yaml)
- **Shared data layer** (incl. 181+ new OPEC / Refining files): [../Datas/](../Datas/)
- **Term definitions (for non-specialist readers)**: [../GLOSSARY.md](../GLOSSARY.md)

---

## Known gaps / next-step candidates

1. **Cross-link to Project 1** — regime-flag from forward-curve HMM could condition the crack-hedge sizing.
2. **OPEC T74 context for LSGO / WTI** — T74 only applied to Brent so far; WTI monthly already in the same file.
3. **EU refinery utilisation as a %** — Eurostat gives intake and installed-capacity separately; compute ratio requires a capacity table not currently ingested.
4. **Research-note narrative style** — port across all notebooks (paragraph-style prose with trade angle, less bullet-heavy).
5. **NumPy-style docstrings** on public methods (coding_habits §8.1).
6. **Ideas 1-3 sizing** — the Exec Summary trading ideas use illustrative sizing; real position-sizing would need vol-targeted kelly or risk-parity allocator.
7. **Project 3 (Physical Arb)** — blocked on freight data; blueprint in portfolio README.

Phase A (user comments, Apr-19) — done. Phase B (code quality) — done. Phase C (new-data integration) — done. Phase D (P&L scaling, hedge β, HMM on crack, bootstrap CIs, EU consumption, trading ideas) — done Apr-22. This list is Phase E candidates.
