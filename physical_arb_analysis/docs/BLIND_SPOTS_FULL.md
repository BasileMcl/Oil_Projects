# Physical-arb engine — full blind-spots catalogue

The top-5 blind spots are in [Notebook 01 §5](../notebooks/01_Methodology_and_Routes.ipynb). Below are the seven additional items a senior trader would flag on a deeper review. All are improvement candidates; none is blocking.

---

## 6. Bunker-price pass-through

The WS rate is bunker-indexed via the annual Worldscale flat-rate book — a reference bunker price is baked in. When bunker prices spike mid-voyage, the charterer pays extra through bunker-adjustment clauses or renegotiated WS on follow-up fixtures. Our engine assumes the quoted WS is final and paid as-is; it is not.

## 7. War-risk insurance curve

The engine adds a bps uplift (`war_risk_uplift_bps`) on top of the base 25 bps P&I + H&M insurance. In reality, Joint War Committee listed-area premiums vary by underwriter, are often 0.5–1.5% of cargo value per single transit for Red Sea / Hormuz, and differ materially between single-voyage and multi-voyage covers.

## 8. Laytime asymmetry

Typical fixtures allow 72 hours total laytime; every hour over pays demurrage. Load and discharge are independent — Bosphorus southbound queues eat loadport laytime; Rotterdam terminal congestion eats discharge laytime. Our engine uses one pooled 2-day expectation. A richer model would split laytime between origin and destination and model each tail independently.

## 9. Counterparty, LC, and sovereign risk

The engine assumes the sell-side pays at discharge. In reality, credit limits, LC confirmation fees, and sovereign risk (paying into a Turkish, Egyptian, or Indian port) gate execution. Some cargoes physically deliver but settlement fails — a real desk runs a counterparty-risk check alongside the arb-P&L check.

## 10. Dirty ↔ clean vessel switching option

LR2 vessels can run dirty (crude / fuel oil) when clean cracks are weak. Our engine hard-codes vessel service. A full model would include the option value of a dirty/clean swing vessel and re-price when clean-dirty spreads widen beyond ~\$3/bbl.

## 11. COA (contract of affreightment) vs spot optionality

Multi-cargo charter contracts lock freight at a flat rate with performance guarantees — can be cheaper than spot in tight markets; can be expensive in weak ones. The engine prices spot WS only. A real shop with large cargo pipelines runs a COA-vs-spot decision for each canonical lane on a quarterly basis.

## 12. Voyage-speed optimisation

Owners run eco-speed (11-12 kt) in weak freight markets to save bunkers and reduce emissions exposure; full speed (14-15 kt) in tight markets. Our `laden_speed_kt` is a single vessel-class default (13 kt dirty, 14 kt clean). A richer model would set speed dynamically based on the freight-market regime or offer speed as a user parameter.

---

*Catalogued 2026-04-23 from the 14-expert panel review. Linked from the 5-item short-list in [Notebook 01 §5](../notebooks/01_Methodology_and_Routes.ipynb).*
