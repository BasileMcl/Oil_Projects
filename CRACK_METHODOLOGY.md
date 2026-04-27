# Crack spread methodology — contract-month alignment

## Why this matters

A crack spread compares crude cost to product price on a per-barrel basis. For it to be meaningful as a **hedge** or **refinery margin**, both legs must reference the **same delivery month** — otherwise you are reading the term structure of one side against the prompt of the other, and the "crack" picks up a curve-slope component that has nothing to do with refining economics.

Most sell-side and data-provider "crack" quotes use prompt-vs-prompt (Brent M1 vs Gasoil M1) because it is the simplest quotable instrument. That is fine for a directional read; it is not right for a dollar-level refinery-margin calculation, and it is specifically wrong for sizing a futures-based hedge on a physical cargo.

## The roll calendar

| Contract | Expiry rule | Consequence |
|---|---|---|
| ICE Brent | Ceases trading end of the last business day of the **second month preceding** delivery. | Brent M1 delivery is usually **2 months out** from trade date. |
| ICE Low Sulphur Gasoil (LSGO) | Ceases trading at 12:00 London **2 business days before the 14th** of the delivery month. | LSGO M1 delivery rolls **mid-month** of the current delivery month. |

Because the two venues roll at different points in the month, the M-number pairing that matches delivery months **changes twice per month**.

## The pairing rule — concrete

For trade date `T`, pair Brent M1 with LSGO M` such that the two delivery months coincide:

| Window within calendar month | LSGO M1 delivery | Brent M1 delivery | Pair |
|---|---|---|---|
| Day 1 → LSGO expiry of that month (≈14th − 2 BD) | current month | current month + 2 | **Brent M1 × LSGO M3** |
| LSGO expiry → Brent expiry (end of month) | next month | current month + 2 | **Brent M1 × LSGO M2** |
| End of month → next LSGO expiry | next month | current month + 3 | **Brent M1 × LSGO M3** |
| Next LSGO expiry → next month-end | +2 months | current month + 3 | **Brent M1 × LSGO M2** |

Worked example for April 2026:

| Trade date | Brent M1 = | LSGO M1 = | Pair |
|---|---|---|---|
| 2026-04-09 | Jun-26 | Apr-26 | Brent M1 × LSGO M3 |
| 2026-04-13 (LSGO rolled) | Jun-26 | May-26 | Brent M1 × LSGO M2 |
| 2026-04-30 | Jun-26 | May-26 | Brent M1 × LSGO M2 |
| 2026-05-05 (Brent rolled end-April) | Jul-26 | May-26 | Brent M1 × LSGO M3 |
| 2026-05-13 (LSGO rolled) | Jul-26 | Jun-26 | Brent M1 × LSGO M2 |

## Implementation

[Forward_Curves_Analysis/src/futures_calendar.py](Forward_Curves_Analysis/src/futures_calendar.py) maps each trade date to its delivery-month pair. It is used by:

- `CrackSpreadAnalysis` in Project 2 for the NWE and Med cracks.
- `CrossMarketAnalysis` in Project 1 for the LSGO–Brent spread and rolling β.
- `CargoArb` in Project 3 when a futures-matched forward curve is required for hedging P&L.

The function returns `(brent_m, lsgo_m)` by date. Each module pulls the right column of its M1–M12 strip using those indices.

## Spot, dated, M1 — not the same price

Three distinct Brent series used in this portfolio, labelled explicitly everywhere:

- **Brent M1 futures** — ICE settlement, front-month contract. Tradeable paper. Source: `Datas/Raw_datas/Futures/Brent_M1M12.xlsx`.
- **Brent spot** — Platts-assessed close, typically a blend of dated / prompt physical windows depending on assessment. Source: `Datas/Raw_datas/Spot/Spot_prices.xlsx` (column `Brent_bbl`).
- **Dated Brent** — the physical cargo assessment Platts publishes at 16:30 London. This is the reference for physical trades. Source: `Datas/Raw_datas/Spot/Dated_Brent_DTD.xlsx` (69-day 2026 window; narrower history than the other two).

The three can diverge by $10+/bbl under stress. The peak **Dated Brent − M1 futures** basis in the 2026-04 dislocation window reached ≈ $35/bbl — a real physical-paper dislocation, not a data artefact.

## What this changes in the portfolio

- Crack levels on any given day shift by roughly *(product curve slope) × 1 month*. In calm markets that is $0–2/bbl. In the current Crisis regime with steep backwardation in LSGO, it can reach $3–6/bbl on peak days.
- **Direction** of the crack (widening / narrowing) is unchanged.
- **Regime classification** on 80/95/99 CDF thresholds is largely unchanged because it is based on the distribution of the corrected series, not a fixed level.
- The **regime-conditional β** result (1.78× Crisis/Normal) uses matched cross-market correlation; the ratio is robust to absolute level shifts.
- **Physical-paper basis** work (Dated Brent − M1) is unaffected — it was already a proper physical-vs-paper comparison.

## What it does not fix

- Spot-vs-Dated-vs-M1 distinction is separate from contract-month alignment. Even when delivery months match, a Platts Dated Brent assessment and an ICE settlement on the same nominal delivery month can diverge on a given day.
- Product-side spot-vs-paper basis (CIF NWE physical vs ICE LSGO) requires its own separate alignment layer when computing physical refinery margin.

## Data refresh note

The chartbook PDF and the HTML reports are point-in-time snapshots. Charts regenerate when you re-run the project notebooks against fresh data (`bash generate_reports.sh` per project). Text commentary is dated to the write-time and does **not** auto-regenerate — a reader should take any quoted number as of the publication date on the cover.

---

*Added 2026-04-24 after the contract-month alignment audit. See `Forward_Curves_Analysis/src/futures_calendar.py` for the code.*
