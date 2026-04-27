#!/usr/bin/env bash
# Execute both Physical Arb notebooks + export HTML reports to outputs/reports/.
set -e
cd "$(dirname "$0")"

PY=/opt/anaconda3/bin/jupyter
REPORT_DIR=outputs/reports
mkdir -p "$REPORT_DIR"

for NB in notebooks/01_Methodology_and_Routes.ipynb \
          notebooks/02_Scenarios.ipynb; do
  echo "==> Executing + exporting $(basename "$NB")"
  "$PY" nbconvert --to notebook --execute --inplace "$NB"
  "$PY" nbconvert --to html --output-dir="$REPORT_DIR" "$NB"
done

echo
echo "Done. HTML reports in: $(pwd)/$REPORT_DIR"
ls -lh "$REPORT_DIR"
