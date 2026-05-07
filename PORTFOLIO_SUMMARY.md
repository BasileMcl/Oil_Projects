# Portfolio — the cross-project read

The three projects each answer one question on their own. This note is the thing that doesn't live inside any single notebook: put them together, what's the single read?

Write-up date: **2026-04-24** (snapshot date matches the chartbook). Everything below is what I think the combined evidence says about the current European diesel market, and where I think the analysis is strong vs. where it's thinner than the charts make it look.

---

## One-line read

European diesel broke regime in early 2025 and the clearing mechanism has been price, because physical replacement is stretched and paper can't short the shortage.

The four supports:

**Curves.** LSGO has been in the Crisis state on 31% of 2025–2026 days vs. ≈1% pre-2025. The 2026-04-02 M1–M3 at 293.75 USD/MT is the widest print on record and would carry a ~140σ Z under the pre-2025 calibration — not a meaningful number, just a way of saying "outside the sample." Brent reads 17% Crisis with a bimodal Normal/Crisis distribution (geopolitics is discontinuous). WTI sits at 13% — the US-inland insulation that the trans-Atlantic basin spread actually quantifies.

**Fundamentals.** US distillate stocks are only at the 50th percentile of the 5-year range — no cushion. US refinery yield-tilt (distillate share minus gasoline share) is flat at −17 pp — no supply-side response from slate swing. Europe structurally imports on the order of 29 Mt/y of diesel (annual view shows this number stepped up after 2022, which is the chart on page 9). So the imported barrel sets NWE pricing, and under stress NWE ULSD decouples from WTI-anchored paper cracks.

**Flows.** Russian diesel rerouted to Turkey/Brazil/ME — not lost from the global pool, but no longer reaching Europe. USGC→NWE arb opens $3–4/bbl net after freight on current basin spreads, but forward MR fixtures are thin (Med Cargo Week-15: 228 kt booked against a window that could clear 2–3× that). OPEC ASB WS% data shows 2022 invasion, 2024 Red Sea, and now 2026 Hormuz as three synchronised freight shocks. When freight peaks, the arb *looks* open on paper and *is closed* operationally — the point Project 3 makes with real numbers.

**Cracks.** NWE 3-2-1 topped 105 USD/bbl in 2022 (cross-product squeeze); the 2026 peak is lower on the 3-2-1 composite but higher on the pure ULSD slate. That's the diesel-specific signature. OPEC ASB's Rotterdam gasoil crack matches our Platts-derived calc at r ≈ 1.0 on overlap years — external anchor in place.

---

## Where the projects couple

The most interesting cross-project finding is that **the regime flag from Project 1 conditions the crack hedge ratio in Project 2**. Not an assumption — something the code now actually does, in [spot_cracks_analysis/src/crack_spread.py](spot_cracks_analysis/src/crack_spread.py)'s `chart_rolling_hedge_ratio_by_regime`. Using the LSGO HMM regime from Project 1 as a conditioner, the rolling NWE ULSD-vs-Brent β runs at 0.608 in Crisis and 0.343 in Normal — a **1.78× ratio**. A paper-diesel book running a static β will be systematically over-hedged in calm and under-hedged in stress.

The second one is **physical-paper basis as the 2026 signature on both sides of the crude-product boundary**. In crude, Dated Brent − Jun-26 futures reached ≈$35 at peak on 2026-04-07. In products, Week-15 CIF Med ULSD sat at $1,402.50/mt vs. the EUM paper swap at $1,301.75/mt — a $13.52/bbl cash-over-paper basis on the same product, same region. Same phenomenon: the physical cargo is bid well over the tradeable paper contract because paper can't be short-sold fast enough to clear the squeeze. These are the cleanest setups of the cycle.

---

## A note on the two registers

This portfolio uses a mix of quantitative work (HMM, CDF-calibrated regimes, rolling β, IS-anchored Z-scores) and physical-desk lenses (flows, inventories, freight, cargo arbs). The stats are there to demonstrate quantitative fluency, not because a senior physical trader would run their day this way — they wouldn't. The daily tool is flows, stocks, relationships. The statistical layer is a complement. A physical-flow-intensity dashboard is on the Phase-I list for direct desk use; the statistical register here is deliberate signal for a technical screen.

---

## What I'm deliberately not claiming

- **No backtest of the trading ideas.** They're hypotheses grounded in the analysis. Sizing is illustrative. Real desks run them through vol-targeted sizing with entity-level limits.
- **Correlation, not causation.** Regime-dependent coupling is what the data shows. The economic mechanism (shared macro drivers, shared physical scarcity) is plausible but not identified.
- **The sample is short.** 5–8y on futures, 3y on cargo-level flows, 6–8y on Platts products. OOS is ≈16 months. Multi-decade tail stats are inferred from OPEC ASB monthly, not estimated from the daily panel. Any σ-count past 5 is a statement about the prior calibration, not a probabilistic claim.
- **Physical P&L is not fully modelled.** Project 3's CargoArb engine gives gross-to-net on a single cargo with a full 9-line waterfall (freight, port, canal, financing, insurance, demurrage, broker). It does not model a book: no optionality, no slate-optimisation, no compliance overlay, no demurrage distribution. Flagged in the README and in the chartbook.
- **The freight stack is parametric, not live.** Flat-rate 2025, Worldscale daily is placeholder — the daily WS time series is the real Phase-I blocker. Until it lands, scenario analysis is the demonstration; backtests aren't.

---

*Last updated 2026-04-24 (chartbook + cross-project β wiring + sanctions-day context). Per-project READMEs have the full roadmap.*
