#!/usr/bin/env bash
# Execute all notebooks (embedding outputs inplace) and export HTML.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$REPO_DIR/outputs/reports"
mkdir -p "$OUT_DIR"

NOTEBOOKS=(
    "notebooks/01_brent.ipynb"
    "notebooks/02_lsgo.ipynb"
    "notebooks/03_wti.ipynb"
    "notebooks/04_cross_market.ipynb"
)

for nb in "${NOTEBOOKS[@]}"; do
    echo "==> Executing + exporting $(basename "$nb")"
    # 1) execute in place (embeds output cells in the .ipynb)
    jupyter nbconvert \
        --to notebook --execute --inplace \
        --ExecutePreprocessor.timeout=600 \
        "$REPO_DIR/$nb"
    # 2) render to HTML without re-executing
    jupyter nbconvert \
        --to html \
        --output-dir "$OUT_DIR" \
        "$REPO_DIR/$nb"
done

echo ""
echo "Done. HTML reports in: $OUT_DIR"
ls -lh "$OUT_DIR"
