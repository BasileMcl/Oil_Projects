# Coding standards — shared SOP

Standing rules that every project under this portfolio obeys. One page.

## Architecture

1. **OOP engine + YAML config.** Wrap analytical logic in classes. Paths, thresholds, windows, colours, units, filenames live in `config.yaml`. Zero hardcoded constants in Python (exceptions: algorithmic invariants like 252 trading days).
2. **Notebooks are drivers.** Anything over ~5 lines belongs in a class method. Each notebook cell produces a number or a chart — no dead commentary cells.
3. **N-way generalisation where free.** If something compares two things, build it to compare N. One `for` loop; big future return.

## Data

4. **Shared data lives in `../Datas/`.** Each project reads paths from its own `config.yaml`. Never duplicate raw data across projects.
5. **Native units with explicit suffix** on column names (`_bbl`, `_mt`, `_kbbl`, `_kt`, `_Mbbl`, `_pct`). No ambiguity, no lossy round-trips.
6. **Rename source files** to `Pascal_snake_case.xlsx`. No spaces, no typos, stable names (not date-tagged).

## Statistical discipline

7. **IS / OOS split is mandatory** on every distributional claim. Default cutoff: 2024-12-31. Calibrate on IS, evaluate on OOS, never the reverse.
8. **CDF-calibrated thresholds** (80/95/99 pct on in-sample) beat ad-hoc rules of thumb.
9. **IS-anchored Z-scores** as the default. Rolling Z-scores suffer a std-floor artifact in calm windows.
10. **Report full / IS / OOS** for every distribution stat. Tail claims that collapse once you split the sample are regime-specific, not structural.
11. **Stationary correlations only for trading claims** (first-difference / log-return, not levels).

## Visualisation

12. **Facet time-series charts** when OOS magnitudes dwarf IS — full sample top, last 18 months bottom.
13. **IS vs OOS overlay** on every distribution chart.
14. **Clip extreme Z** at ±10 with off-chart annotations. Don't let one 140σ point dictate the axis.
15. **One palette per portfolio** from `config.yaml`. No per-project seaborn experiments.
16. **Figures save to `outputs/figures/<subdir>/`** automatically — readers never have to re-run.

## Documentation

17. **One TL;DR at the top** of each project README. 45-second read. Three numbers max. One lead-chart link.
18. **One README per project, short.** Sub-folder READMEs ≤ 10 lines — navigation, not content.
19. **No duplicate summary documents.** Two files covering the same ground means one will go stale.
20. **Limitations section is mandatory.** Name the three weaknesses most likely to get pushback.

## Dependencies

21. **Every import used is in `requirements.txt`** with a minimum version. Pin only where needed.
22. **Each project's `requirements.txt` starts with** `-r ../requirements-base.txt` — inherits the portfolio baseline.
23. **Keep the dependency set small.** No `sklearn` if `scipy.stats` does it. No `seaborn` if matplotlib + palette config does it.

## Reproducibility

24. **`generate_reports.sh` runs everything.** Single command, from a clean clone, zero manual steps.
25. **Random seeds fixed** on every stochastic component (HMM fits, bootstraps, sampling).
26. **Notebook outputs embedded inplace.** A reader viewing on GitHub sees the charts without running anything.

## Review discipline

27. **Read like a trader.** 45 seconds on the README, 3 minutes on one chart, 10 minutes if hooked. Optimise for that path.
28. **Self-flag anything uncertain** with HIGH / MEDIUM / LOW confidence and reasoning.
29. **Re-execute after every non-trivial change.** "The engine changed but I didn't re-run the notebooks" is a classic embarrassment.
30. **Kill dead code quickly.** Legacy branches that were useful once are maintenance debt.

## Delivery checklist (before calling a project done)

- [ ] `bash generate_reports.sh` runs from a clean clone with no manual steps
- [ ] Every chart has title, axis labels, units, saved PNG
- [ ] Every README claim is backed by a chart or stats table
- [ ] `requirements.txt` complete (test in a fresh venv)
- [ ] IS vs OOS split documented and defensible
- [ ] Limitations section names the three weaknesses most likely to get pushback
- [ ] No stale numbers in markdown cells after the last data refresh
- [ ] No placeholder filenames (`data_5y.xlsx` for a 7-year series)
- [ ] One TL;DR at the top, one lead chart, rest is depth
