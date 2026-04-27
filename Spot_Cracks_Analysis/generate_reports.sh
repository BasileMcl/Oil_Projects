#!/usr/bin/env bash
# Execute all notebooks (inplace) and export HTML.
set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$REPO_DIR/outputs/reports"
mkdir -p "$OUT_DIR"

NOTEBOOKS=(
    "notebooks/00_Executive_Summary.ipynb"
    "notebooks/01_Market_Overview.ipynb"
    "notebooks/02_Fundamentals.ipynb"
    "notebooks/03_Regional_Analysis.ipynb"
)

for nb in "${NOTEBOOKS[@]}"; do
    echo "==> Executing + exporting $(basename "$nb")"
    jupyter nbconvert \
        --to notebook --execute --inplace \
        --ExecutePreprocessor.timeout=600 \
        "$REPO_DIR/$nb"
    jupyter nbconvert \
        --to html \
        --output-dir "$OUT_DIR" \
        "$REPO_DIR/$nb"
done

echo ""
echo "Done. HTML reports in: $OUT_DIR"
ls -lh "$OUT_DIR"
