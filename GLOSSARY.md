# Glossary

Portfolio-wide term definitions. Written for the non-specialist reader (recruiter, HR screen, desk head passing the CV to a junior). Expert readers can skip it — every term here is standard industry vocabulary.

## Market structure

| Term | Definition |
|---|---|
| **Backwardation** | Futures-curve shape where near-month price is *above* deferred contracts. Supply tight; inventory-holders penalised. |
| **Contango** | Futures-curve shape where near-month is *below* deferred. Supply loose; storage economics positive. |
| **Front-month** / **M1** | The nearest-to-expiry listed futures contract. M2 is the next, M3 the third, etc. |
| **M1-M3 spread** | Price of M1 minus M3. Common shorthand for "term structure at the very front of the curve." |
| **Rolling** (contract) | When the expiring front-month is replaced by the next contract. Price jumps at the roll are not true market moves — they're convention. Pre-rolled exchange series (e.g. `BRN 1!-ICE`) smooth this out. |

## Prices and pricing points

| Term | Definition |
|---|---|
| **Brent** | North Sea crude benchmark — the dominant global crude price reference. |
| **WTI** | West Texas Intermediate — US crude benchmark. Trades in Cushing, OK. |
| **Dated Brent** | Platts physical assessment of Brent cargoes with a laycan (loading window) already declared. The "real" physical price vs futures. |
| **Brent CFDs** | Forward differentials 1-8 weeks out, traded as contracts-for-differences. |
| **USD/bbl** | US dollars per barrel. Crude is natively priced this way. |
| **USD/MT** | US dollars per metric tonne. Products are natively priced this way in Platts. Conversions: ULSD 7.45 bbl/MT · gasoline 8.33 · fuel oil 6.35. |

## Products and specifications

| Term | Definition |
|---|---|
| **ULSD** | Ultra-Low Sulphur Diesel, ≤10 ppm sulphur. European automotive diesel standard. Prices assessed at NWE (North-West Europe, ARA) and Med (Mediterranean, usually Augusta delivery). |
| **EBOB** | Eurobob — European gasoline specification. Barge-delivered in the ARA (Amsterdam-Rotterdam-Antwerp) area. |
| **Jet** | Jet fuel / kerosene. Assessed as Jet CIF NWE Cargo or JA1 (Jet A-1) in Platts. |
| **FO 3.5%** / **FO 1%** | Fuel oil with 3.5% (high-sulphur) or 1% sulphur content. Bunker/marine fuel. |
| **HSFO / VLSFO** | High-Sulphur Fuel Oil (3.5%) vs Very-Low-Sulphur Fuel Oil (≤0.5%). IMO 2020 regulation drove the VLSFO market. |
| **NWE / Med** | North-West Europe vs Mediterranean — two regional pricing zones for European products. |

## Crack spreads and refining

| Term | Definition |
|---|---|
| **Crack spread** | Refined-product price minus the crude it's made from. A refining-margin proxy — how much a refiner earns per barrel of crude input. |
| **3-2-1** | Standard US-style refinery slate: 3 barrels of crude → 2 barrels of gasoline + 1 barrel of diesel. Margin = (2·gasoline + 1·diesel − 3·crude) / 3 per barrel of crude. |
| **2-1-1** | Alternative slate: 1 gasoline + 1 diesel per 2 barrels of crude. European-flavoured. |
| **Refinery yield** | The percentage of each product produced per barrel of crude input (gasoline %, diesel %, etc.). |
| **Refinery utilisation** | Crude input ÷ operable distillation capacity. Percent. "Tight" above 90%. |
| **Throughput** | Volume of crude processed per day. |

## Stocks and flows

| Term | Definition |
|---|---|
| **SPR** | Strategic Petroleum Reserve — US government emergency crude stockpile. Drawdown or refill is a policy decision with market impact. |
| **Floating storage** | Oil sat at sea on tankers rather than onshore. High floating storage = seaborne oversupply signal. |
| **Commercial stocks** | Inventories held by private operators (refineries, traders, shippers). |

## Analysis conventions

| Term | Definition |
|---|---|
| **IS / OOS** | In-Sample (≤ 2024-12-31) vs Out-Of-Sample (2025-01 onwards). Distributional claims are calibrated on IS and evaluated on OOS. |
| **Regime** | Classified market state (Normal / Tight / Stress / Crisis) based on thresholds of a structural variable (M1-M6 spread, crack margin). Thresholds are CDF-calibrated on IS. |
| **Z-score** | How many standard deviations an observation sits from its mean. Portfolio default is IS-anchored (μ, σ fixed on the IS window and applied uniformly) rather than rolling. |
| **HMM** | Hidden Markov Model — a regime-switching statistical model. Used here as a descriptive classifier, not a predictor. |
| **TL;DR** | "Too long; didn't read." 45-second summary at the top of each notebook. |

## Geography

| Term | Definition |
|---|---|
| **ARA** | Amsterdam-Rotterdam-Antwerp — the main NWE products hub. |
| **USGC** | US Gulf Coast — main US refining region, centred on Houston. |
| **Sing** | Singapore — the Asian products trading hub. |
| **Hormuz** | Strait of Hormuz — the chokepoint between the Persian Gulf and the Gulf of Oman. ~20% of global oil throughput. |
