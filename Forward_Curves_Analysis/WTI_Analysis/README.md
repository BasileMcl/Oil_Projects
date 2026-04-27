# WTI — ICE WTI Crude

Front-month M1–M12 · 2018-10-03 → 2026-04-17 (longest sample of the three commodities).

Driver `WTI_Analysis_Report.ipynb` → `ForwardCurveAnalysis(COMMODITY='WTI')`. Data [../../Datas/Raw_datas/Futures/WTI_M1M12.xlsx](../../Datas/Raw_datas/Futures/WTI_M1M12.xlsx).

**On 2020-04-20**: ICE's rolling front-month (`WBS 1!-ICE`) rolls before expiry, so the intraday −$37 print on the expiring contract does not appear in the series (M1 min = $41.21). The event line is a date marker.

Regime thresholds 1.15 / 1.44 / 1.61 USD/bbl on M1-M6. Methodology in [../README.md](../README.md).
