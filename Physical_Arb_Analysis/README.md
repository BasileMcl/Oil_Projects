# Physical cargo arbitrage — Project 3

A **parametric** calculator and scenario engine for crude and product cargo arbitrage decisions. The user specifies origin, destination, vessel class, grade, cargo tonnage (or capacity utilisation), Worldscale rate, forward-price base, and regional premium / discount on each side. The engine returns a full P&L waterfall and a go / no-go read.

Validated against a **TD6-class stress-regime example** — Suezmax Black Sea → Med, 22 April 2026 window, WS 230.56 with 2026 Worldscale flat rate 11.09 USD/MT → 25.57 USD/MT freight, 3.45 M USD cargo freight on a 135 000 MT parcel. The engine reproduces the standard Worldscale math to the dollar.

---

## TL;DR

- **Parametric everywhere.** Any origin / destination from the PORTS dictionary, any of 6 vessel classes (MR / LR1 / LR2 / Aframax / Suezmax / VLCC), any capacity utilisation 0–1, explicit regional premium / discount on both buy and sell sides.
- **Forward-price convention.** Buy at origin FOB on load-month forward; sell at destination CIF on discharge-month forward. Timing is user-chosen (M+1 / M+2), metadata fields surface the contract basis.
- **Date-stamped inputs.** The model is **NOT live** — prices are a snapshot (default 16-Apr-2026, held in `config.RUN_METADATA.DATE_OF_PRICES`). This date must be cited anywhere results are presented.
- **Current regime context:** Hormuz-blockade crisis — freight WS 2-4× historical averages, Brent physical-paper basis dislocated, Med ULSD inverted over NWE. Normal regime numbers would be materially tighter.
- **Freight dominates short-haul crude** — 3-4 USD/bbl on a Black Sea → Med Aframax at current WS; every other line < 0.50 USD/bbl.
- **Sign is information** — a negative net P&L means the arb runs the other direction.

Lead example: [outputs/figures/waterfall_single_cargo.png](outputs/figures/waterfall_single_cargo.png)

---

## Layout

```
src/
  arb_engine.py                 CargoArb class — parametric calculator + chart methods
config.yaml                     ports, distances, vessels, grades, canals, WS flat rates, presets
requirements.txt                inherits ../requirements-base.txt
generate_reports.sh             runs both notebooks → outputs/reports/

notebooks/
  01_Methodology_and_Routes.ipynb   Parametric engine walkthrough · default BSea→Med Aframax
                                     · waterfall + sensitivity · 5-lane flex · blind spots
  02_Scenarios.ipynb                4 historical moments (2020 COVID · 2022 invasion
                                     · 2024 Red Sea · 2026 Hormuz)

outputs/
  figures/                      5 saved charts
  reports/                      2 executed HTML reports
```

Everything an executive needs sits in this README; technical detail lives in the two notebooks. No stand-alone executive-summary notebook — it would duplicate text with zero added value.

Portfolio-wide styling: [../plot_config.yaml](../plot_config.yaml). Event timeline: [../major_dates.yaml](../major_dates.yaml). Cross-references to Projects 1 / 2 in [../PORTFOLIO_SUMMARY.md](../PORTFOLIO_SUMMARY.md).

---

## Run

```bash
cd Projects/Physical_Arb_Analysis
pip install -r requirements.txt
bash generate_reports.sh
```

Or drive the engine directly. Two equivalent constructor patterns:

```python
from src import CargoArb

# --- A: fully parametric ---------------------------------------------------
arb = CargoArb(
    origin_port='Novorossiysk',
    dest_port='Augusta',
    vessel='Aframax',
    grade='Urals',
    ws_rate=230.56,
    flat_rate=11.20,                        # USD/MT at WS 100; or lookup via ws_flat_key
    buy_price=99.60,                        # ICE Brent Jun-26 forward
    buy_premium_discount=-30.00,            # Urals discount to Dated
    sell_price=96.80,                       # ICE Brent Jul-26 forward (M+1)
    sell_premium_discount=0.50,             # Urals CIF Augusta basis
    capacity_utilization=1.0,
    canals=('Bosphorus',),
    date_of_prices='2026-04-16',
)

# --- B: named preset + overrides ------------------------------------------
arb = CargoArb.from_preset(
    'BSEA_MED_AFRA',
    ws_rate=230.56,
    buy_price=99.60, buy_premium_discount=-30.00,
    sell_price=96.80, sell_premium_discount=0.50,
    date_of_prices='2026-04-16',
)

arb.print_summary()
arb.chart_waterfall()
arb.chart_sensitivity_ws()
arb.chart_sensitivity_grid()

# Multi-cargo views are classmethods
CargoArb.chart_route_comparison({'label': arb, ...})
CargoArb.chart_scenario_backtest(scenarios_df)
```

### What the engine exposes (every parameter)

| Parameter | Meaning | Default |
|---|---|---|
| `origin_port`, `dest_port` | Must be in config `PORTS` or pass `distance_nm` explicitly | — |
| `vessel` | One of MR / LR1 / LR2 / Aframax / Suezmax / VLCC | — |
| `grade` | Must be in config `GRADE_SPECS` (crude or product) | — |
| `ws_rate` | Worldscale rate for the voyage | — |
| `flat_rate` | USD/MT at WS 100; if None, looked up via `ws_flat_key` | None |
| `buy_price`, `sell_price` | **Forward** prices USD/bbl (convention: origin FOB / destination CIF) | — |
| `buy_premium_discount`, `sell_premium_discount` | Regional / grade premium (+) or discount (−) USD/bbl | 0.0 |
| `cargo_mt` | Cargo on board; if None, = `vessel_dwt × capacity_utilization` | auto |
| `capacity_utilization` | 0–1, fraction of nameplate DWT loaded | 1.0 |
| `distance_nm`, `speed_kt` | Override auto-lookup / vessel default | auto |
| `canals` | List of canal transits (`Suez`, `Panama`, `Bosphorus`, `Cape_Good_Hope`) | () |
| `financing_days`, `demurrage_days` | Override auto-compute | auto / 2 |
| `war_risk_uplift_bps` | Extra insurance bps (Hormuz, Red Sea …) | 0 |
| `date_of_prices`, `buy_timing`, `sell_timing` | Metadata for reporting | None |

---

## Methodology

`CargoArb` computes freight via the standard Worldscale formula: `freight_USD/MT = WS × flat_rate / 100`; cargo freight = freight_USD/MT × cargo_mt on board (freight is paid on actual tonnage, so capacity utilisation < 1 lowers the total bill). USD/MT ↔ USD/bbl conversion uses `density` (barrels per metric tonne) from `GRADE_SPECS` — standard values: Urals 7.22, Forties 7.44, WTI Midland 7.57, ULSD 7.45, Jet 7.90, EBOB 8.33, FO 3.5% 6.35.

Non-freight costs come from config static tables: port-call charges per origin / destination, canal tolls by vessel class, financing at SOFR + 300 bps over `steam_days + load_disch + laycan` (steam days computed from `distance_nm ÷ (speed_kt × 24)`), P&I + H&M insurance at 25 bps of cargo value plus an optional war-risk uplift, demurrage at a 2-day risk-weighted expectation times the vessel-specific daily rate, broker commission at 2.5% of freight.

Effective prices apply premium / discount per side: `effective_buy = buy + buy_premium_discount`, `effective_sell = sell + sell_premium_discount`. The P&L waterfall reduces to `net_arb = (eff_sell − eff_buy) − sum(costs)` in USD/bbl; `breakeven_ws()` and `breakeven_spread()` solve for the zero-P&L point in each dimension analytically.

All distances cited in config are indicative (sea-distances.org / Ports.com); user should verify against their preferred sources (SeaOrg, Clarksons, etc.) for any executable trade. Cape-vs-Suez routing is a per-route config toggle, not dynamically computed.

---

## Data scope, limitations, and what a trader would push back on

### Known gaps (in-engine)

- **Not live.** Prices and WS are snapshot inputs; `config.RUN_METADATA.DATE_OF_PRICES` holds the reference date.
- **Illustrative prices** where a specific Platts / Argus print isn't cited — user to verify for executable decisions.
- **No daily WS time series.** Backtests are snapshot reconstructions of documented historical events. When a Worldscale / Baltic / Howe Robinson daily feed lands, the framework supports drop-in.
- **Demurrage is a 2-day point estimate.** Fat-tailed in reality (Bosphorus queues, Suez closures). A Monte Carlo would widen the error bars.
- **Cape-vs-Suez routing is static** in route / canal config — richer model would choose dynamically based on chokepoint status.

### Blind spots a trader would flag (not modelled)

1. **Bunker-price pass-through** — WS is bunker-indexed via the flat-rate book; spikes hit charterers via adjustment clauses.
2. **FFA / forward freight hedging** — real desks lock spot WS via swaps; we model spot only.
3. **Vetting / OCIMF SIRE / major-oil approval** — constrains vessel pool, especially under sanctions.
4. **EU ETS (2024-onwards)** + IMO emission reporting — extra per-tonne-CO₂ cost on EU-discharge voyages.
5. **Broker commission varies** — 2.5% flat here; shops with large volume pay less.
6. **War-risk insurance curve** — we add a BPS uplift; real premiums are underwriter-specific.
7. **Laytime asymmetry** — load and discharge demurrage exposures are independent in reality.
8. **Counterparty / LC / sovereign risk** — can the buyer pay? Is the LC confirmed?
9. **Sanctions compliance overlay** — Russia price cap gates Urals trades for G7-linked participants, regardless of economics.
10. **Dirty / clean vessel switching option** — LR2 runs dirty when clean cracks weak.
11. **COA (contract of affreightment) vs spot** — optionality ignored.
12. **Voyage speed optimisation** — eco-speed (11-12 kt) in weak freight vs full-speed (14-15 kt) in tight. We use one per-class default.

---

## Cross-references

- **Forward curves** (LSGO / Brent / WTI regime + cross-market) → [../Forward_Curves_Analysis/](../Forward_Curves_Analysis/)
- **NWE / Med cracks + fundamentals + flows** → [../Spot_Cracks_Analysis/](../Spot_Cracks_Analysis/)
- **Portfolio synthesis** → [../PORTFOLIO_SUMMARY.md](../PORTFOLIO_SUMMARY.md)
- **Term definitions** (WS, TD3C, TCE, Aframax, Suezmax, …) → [../GLOSSARY.md](../GLOSSARY.md)
- **Reference reports** — Med Cargo Market Week-15, OB Data Radar War-on-Iran, OB Venezuela Overview at [../Reference_Notes/](../Reference_Notes/)

---

## Next steps

1. **Daily WS time series ingestion** (pending Worldscale / Baltic access).
2. **EU ETS shipping emissions** — add phased-in 40 / 70 / 100% coverage for EU-discharge voyages.
3. **FFA forward freight hedging** — allow user to specify hedged freight vs spot.
4. **Sanctions / compliance overlay** — jurisdictional gate flagging non-shippable routes.
5. **Dynamic Cape-vs-Suez routing** — compute voyage distance as a function of the active chokepoint map.
6. **Monte Carlo demurrage** — replace point estimate with a distribution.

Phase G complete. Phase H (LaTeX chartbook) is next.
