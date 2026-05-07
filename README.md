# Oil analytics portfolio

Three projects, one codebase. ICE forward curves, Platts cracks, physical cargo arbitrage — built around the 2025-2026 diesel / Hormuz cycle, fully reproducible from one command per project.

Written by **Basile M'Couela** — EDHEC MSc Financial Engineering '27, currently Natixis CIB (XVA), ex-Haxem (Monaco physical clean products). Targeting a physical-trading-house placement starting summer 2027.

**Snapshot: 2026-04-24.** Forward prices and Platts assessments dated to the Apr-24 Marketscan suite. Sanctions context reflects the EU 20th package (23-Apr-2026) and OFAC GL 134B (17-Apr-2026). Event timeline applied across all three projects in [major_dates.yaml](major_dates.yaml).

---

## The hero finding — read this first

The NWE ULSD-Brent crack hedge ratio is **regime-dependent, not constant**:

| | Normal | Crisis 2022 | Crisis 2026 | Latest 30d |
|---|---|---|---|---|
| Matched M2×M1 β (n) | −0.18 (1,147) | +0.31 (26) | **+0.61 (73)** | **+0.92 (30)** |

In Normal, the crack floats independent of crude. In Crisis-2026 (the active Hormuz regime), it moves *with* Brent — diesel-specific Hormuz pass-through, not a generic crisis pattern. **A static pooled β ≈ 0.4 under-hedges Brent risk by ~50% on the Crisis-2026 mean, and by 2×+ at the latest print (+1.17 single-day on 2026-04-17).**

Pipeline: [forward_curves_analysis/scripts/run_matched_beta.py](forward_curves_analysis/scripts/run_matched_beta.py). Calendar pairing wired via [forward_curves_analysis/src/futures_calendar.py](forward_curves_analysis/src/futures_calendar.py). Full methodology in [CRACK_METHODOLOGY.md](CRACK_METHODOLOGY.md). Chartbook §5 is the desk-language version of this finding.

---

## Three ways in

| Entry | Format | Best for |
|---|---|---|
| **Chartbook** ([source](chartbook/Oil_Portfolio_Chartbook_2026-04-24.tex), [Overleaf zip](chartbook/Oil_Portfolio_Chartbook_2026-04-24_overleaf.zip)) | 23-page LaTeX deck | Forwardable to a desk. Pages 7-8 are the regime-β finding above. Compile with `pdflatex` or upload the zip to Overleaf. |
| **Project notebooks** | Jupyter + executed HTML | Methodology + code. Each project runs end-to-end via `bash generate_reports.sh`. |
| **[PORTFOLIO_SUMMARY.md](PORTFOLIO_SUMMARY.md)** | 2-page markdown | Cross-project synthesis — the single read tying all three together. |

---

## Projects

| # | Project | Scope |
|---|---|---|
| 1 | [forward_curves_analysis](forward_curves_analysis/) | ICE Brent / LSGO / WTI M1–M12 daily settlements · CDF + HMM regime classification · regime-conditional rolling β · basin spread · 36-year OPEC ASB long-history context |
| 2 | [spot_cracks_analysis](spot_cracks_analysis/) | NWE / Med 3-2-1, ULSD, EBOB cracks · US 43-year refinery utilisation + yields · EU refinery intake + 29 Mt/y diesel deficit · OPEC trade flows + freight · OPEC T76 cross-check (r ≈ 1.0 on overlap years) |
| 3 | [physical_arb_analysis](physical_arb_analysis/) | Parametric `CargoArb` engine · 9-item P&L waterfall · 5 canonical lanes · 4 historical scenarios (2020 COVID / 2022 invasion / 2024 Red Sea / 2026 Hormuz) · reproduces a TD6 Suezmax stress fixture to the dollar |

---

## Layout

```
projects/
├── README.md                     this file
├── PORTFOLIO_SUMMARY.md          cross-project synthesis
├── CRACK_METHODOLOGY.md          contract-month alignment, three Brent series
├── GLOSSARY.md                   term definitions (3-2-1, ULSD, IS/OOS, …)
├── plot_config.yaml              shared palette / fonts
├── major_dates.yaml              geopolitical + market event timeline
├── requirements-base.txt         shared minimum deps
│
├── forward_curves_analysis/      Project 1, ICE forward curves + regime classifier
├── spot_cracks_analysis/         Project 2, refining margins + EU diesel deficit
├── physical_arb_analysis/        Project 3, parametric cargo arb engine
├── chartbook/                    LaTeX chartbook + figures
├── data/                         raw + cleaned inputs (Platts subfolder gitignored)
└── reference_notes/              source PDFs (OPEC ASB, MOMR), not committed
```

`data/` (raw + cleaned inputs) and `reference_notes/` (source PDFs — OPEC ASB, MOMR) are **not committed**. See *Data sourcing* below.

---

## Running

```bash
cd <Project_folder>
pip install -r requirements.txt
bash generate_reports.sh
```

Each project reads `../data/` through its own `config.yaml`, inherits styling from `plot_config.yaml`, and pulls the event timeline from `major_dates.yaml`. A clean clone runs end-to-end once `data/` is populated per the conventions in each `config.yaml`.

---

## Data sourcing

The `data/` folder is excluded from this repository to respect Platts and OPEC redistribution licensing — Platts daily price assessments and OPEC publications are not mine to redistribute. To reproduce locally you need:

- **Forward curves**: ICE Brent / LSGO / WTI M1–M12 daily settlement strips (xlsx, one row per trade date, columns M1..M12).
- **Platts physical**: spot ULSD / EBOB / Jet / FO prints (NWE, Med, ARA basis), merged into a `Spot_prices.xlsx`.
- **EIA**: weekly stocks + refinery utilisation + monthly yields. Public CSVs from `eia.gov`.
- **Eurostat**: `nrg_cb_oilm` for EU refinery supply / consumption, `nrg_stk_m` for stocks.
- **OPEC ASB 2025**: tables T43 / T52 / T53 / T62 / T63 / T74 / T76. Public PDF.

Per-project `config.yaml` files name expected paths and column conventions. Open an issue if you want to reproduce and need the layout.

---

## Conventions

Every project obeys a one-page SOP: OOP engine + YAML config, IS/OOS split (training ≤ 2024-12-31, evaluation 2025+), CDF-calibrated regime thresholds, IS-anchored Z-scores, faceted time-series, unified palette, one-command reproducibility. Term definitions for non-specialists in [GLOSSARY.md](GLOSSARY.md). Notebook output cells are committed inplace so charts render on GitHub without execution (rule #26).

---

## Scope and limitations

- **OOS window is 16 months** (n ≈ 400 trading days). Direction of regime claims is unambiguous; the level (e.g. "Crisis 31% of OOS days") is descriptive of this episode, not a stable distribution estimate — binomial CI ±5pp on the 31% point.
- **Trading ideas are hypotheses, not backtested strategies.** No measured Sharpe, no walk-forward validation. HIGH/MED/LOW conviction tags are editorial.
- **Sanctions overlay is a flag, not a compliance system.** Real desks run OFAC against live entity-resolution databases; this repo lists port-level sanctions in YAML.
- **Daily Worldscale is not in the dataset.** Project 3's `CargoArb` is a parametric calculator, not a backtested arb-history tool. Daily WS ingestion is the Tier-1 data unlock.
- **Regional coverage is European / Atlantic-basin.** Asia (Singapore 10ppm, India product flows) is light by deliberate scope, not omission.

---

## License

MIT. See [LICENSE](LICENSE) (to be added on first commit).

---

*Personal project. Contact: basile via GitHub or LinkedIn.*
