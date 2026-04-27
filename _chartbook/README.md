# Chartbook build

Two parallel paths produce a PDF from the same source data.

## Overleaf (canonical)

`Oil_Portfolio_Chartbook_2026-04-23.tex` + `figs/` is the polished, fully-formatted version. Upload `Oil_Portfolio_Chartbook_2026-04-23_overleaf.zip` to Overleaf and compile with pdfLaTeX. This is what you send to readers.

Expected output: ~17–18 pages after the page merges (LSGO event timeline + CDF regime on one spread, HMM + methodology on the next).

## Python fallback

`build_pdf.py` uses reportlab to produce `Oil_Portfolio_Chartbook_2026-04-23.pdf` locally without needing a LaTeX installation. Run with:

```bash
python build_pdf.py
```

The fallback is a rough preview only. It does not carry the full narrative rewrites that live in the `.tex` file, and it renders at 20 pages rather than the merged 17–18. Use it to sanity-check chart placement and layout; use the Overleaf output for anything you forward.

## Refreshing figures

When you re-run Project 1 or Project 2 notebooks, the new PNGs land in each project's `outputs/figures/` folder. Copy the relevant ones into `./figs/` before rebuilding. The `figs/` folder is what both the Overleaf and the reportlab paths read.

## Keep in sync

If the `.tex` gets edited (narrative rewrites, new sections) and you want the reportlab fallback to match, edit `build_pdf.py` by hand. The two paths are not auto-synced.
