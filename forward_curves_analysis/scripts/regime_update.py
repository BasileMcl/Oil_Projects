"""regime_update.py. Auto-pull the 3-line regime header for weekly LinkedIn posts.

Usage:
    python3 regime_update.py [--as_of YYYY-MM-DD] [--no-append]

Output (paste into the top or italic footer of your weekly LinkedIn post):
    Today: regime classifier @ Crisis-2026, day [X] (anchor: 2026-04-13). Delta vs last entry: same regime, +N days.
    Diesel-Brent matched beta last 30d: [Y] (Delta [Z] vs last entry's [W]).
    EU diesel deficit: ~29 Mt/y baseline (Eurostat nrg_cb_oilm pooled 2018-2026).

Behavior:
    1. Compute today's regime header values from the matched-beta CSV.
    2. Read the previous entry from regimes.md (if any) to compute Delta vs last week.
    3. Print the 3-line header.
    4. Append today's row to regimes.md (unless --no-append is passed).

Dependencies: pandas only. Requires `outputs/reports/matched_beta_series.csv`
to exist (regenerate via `scripts/run_matched_beta.py` if stale).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# Anchor: US Navy blockade activation, per chartbook §2.1
REGIME_ANCHOR = date(2026, 4, 13)
REGIME_LABEL = "Crisis-2026"

# Path to the production-grade matched beta series
ROOT = Path(__file__).resolve().parents[1]  # forward_curves_analysis/
BETA_CSV = ROOT / "outputs" / "reports" / "matched_beta_series.csv"

# Path to the historical regime state log (markdown table). Read for Delta-vs-last-entry; appended on each run.
REGIMES_LOG = ROOT / "outputs" / "reports" / "regimes.md"

# EU diesel deficit baseline (Eurostat nrg_cb_oilm, pooled 2018-2026 avg per chartbook §9)
EU_DEFICIT_BASELINE_MT = 29


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--as_of",
        default=date.today().isoformat(),
        help="Date for the header (default: today, ISO format)",
    )
    p.add_argument(
        "--no-append",
        action="store_true",
        help="Compute and print only; do not append to regimes.md",
    )
    return p.parse_args()


def days_since_anchor(today: date) -> int:
    return (today - REGIME_ANCHOR).days


def beta_stats() -> dict:
    if not BETA_CSV.exists():
        raise FileNotFoundError(f"{BETA_CSV} not found. Re-run scripts/run_matched_beta.py first.")
    df = pd.read_csv(BETA_CSV, parse_dates=["Date"])
    df = df.dropna(subset=["beta"]).sort_values("Date")
    if df.empty:
        raise RuntimeError("matched_beta_series.csv has no beta rows.")
    last = df.iloc[-1]
    last30 = df.tail(30)["beta"].mean()
    last60 = df.tail(60)["beta"].mean()
    return {
        "latest_date": last["Date"].date().isoformat(),
        "latest_beta": float(last["beta"]),
        "mean_30d": float(last30),
        "mean_60d": float(last60),
        "regime_at_latest": last["regime_2state"],
    }


def read_last_log_entry() -> dict | None:
    """Parse the most recent row of regimes.md (markdown table). Return None if file missing or empty."""
    if not REGIMES_LOG.exists():
        return None
    text = REGIMES_LOG.read_text()
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if s.startswith("| ---") or s.startswith("|---") or s.startswith("| Date"):
            continue
        cells = [c.strip() for c in s.split("|")[1:-1]]
        if len(cells) < 5:
            continue
        # Expected cols: Date | Regime | Days since anchor | beta_30d | beta_60d | beta_latest | EU deficit baseline
        try:
            d = datetime.fromisoformat(cells[0]).date()
        except ValueError:
            continue
        rows.append(
            {
                "date": d,
                "regime": cells[1],
                "days_since": int(cells[2]),
                "beta_30d": float(cells[3]),
                "beta_60d": float(cells[4]),
                "beta_latest": float(cells[5]),
                "eu_baseline": cells[6] if len(cells) > 6 else "",
            }
        )
    if not rows:
        return None
    rows.sort(key=lambda r: r["date"])
    return rows[-1]


def append_log_row(
    today: date, regime: str, days: int, b30: float, b60: float, blatest: float, eu_baseline: int
) -> None:
    """Append today's row to regimes.md. Create the file with a header if it does not yet exist."""
    REGIMES_LOG.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Regime state log\n\n"
        "Weekly snapshot of the regime classifier output. Each Tuesday before posting, run:\n\n"
        "```\n"
        "python3 scripts/run_matched_beta.py     # refresh beta CSV\n"
        "python3 scripts/regime_update.py        # print header + append row to this file\n"
        "```\n\n"
        "**Order**: descending by date (most recent first).\n\n"
        "| Date | Regime | Days since anchor | beta_30d | beta_60d | beta_latest | EU deficit baseline (Mt/y) |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    new_row = f"| {today.isoformat()} | {regime} | {days} | {b30:+.2f} | {b60:+.2f} | {blatest:+.2f} | {eu_baseline} |\n"
    if not REGIMES_LOG.exists():
        REGIMES_LOG.write_text(header + new_row)
        return
    text = REGIMES_LOG.read_text()
    # Insert new row right after the table header separator (so descending order: newest first)
    lines = text.splitlines(keepends=True)
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|---") or line.strip().startswith("| ---"):
            insert_idx = i + 1
            break
    if insert_idx is None:
        # Header missing or malformed. Rewrite from scratch with the new row.
        REGIMES_LOG.write_text(header + new_row)
        return
    lines.insert(insert_idx, new_row)
    REGIMES_LOG.write_text("".join(lines))


def main():
    args = parse_args()
    today = datetime.fromisoformat(args.as_of).date()

    days = days_since_anchor(today)
    bs = beta_stats()
    prev = read_last_log_entry()

    # Stale-data warning (beta CSV last point should be within ~7 days of today)
    last_beta_date = datetime.fromisoformat(bs["latest_date"]).date()
    stale_days = (today - last_beta_date).days
    stale_note = ""
    if stale_days > 14:
        stale_note = (
            f"\n\n[WARN]  beta CSV is {stale_days} days stale (last point: {bs['latest_date']}). "
            f"Rerun scripts/run_matched_beta.py before publishing."
        )

    # Build Δ strings versus the previous logged entry, if any.
    if prev is not None:
        prev_date = prev["date"]
        prev_days = prev["days_since"]
        delta_days_text = f"{days - prev_days:+d} days vs entry on {prev_date.isoformat()}"
        if prev["regime"] == REGIME_LABEL:
            regime_delta = f"same regime, {delta_days_text}"
        else:
            regime_delta = (
                f"REGIME SHIFT from {prev['regime']} to {REGIME_LABEL}, {delta_days_text}"
            )
        d_beta_30d = bs["mean_30d"] - prev["beta_30d"]
        beta_delta_text = (
            f"Δ {d_beta_30d:+.2f} vs entry on {prev_date.isoformat()} ({prev['beta_30d']:+.2f})"
        )
    else:
        regime_delta = "first logged entry, no prior comparison"
        beta_delta_text = "no prior entry"

    print(
        f"Today: regime classifier @ {REGIME_LABEL}, day {days} "
        f"(anchor: {REGIME_ANCHOR.isoformat()} blockade activation). {regime_delta}."
    )
    print(
        f"Diesel-Brent matched β last 30d: {bs['mean_30d']:+.2f} "
        f"(60d {bs['mean_60d']:+.2f} / single-day latest {bs['latest_beta']:+.2f} on {bs['latest_date']}). "
        f"{beta_delta_text}."
    )
    print(
        f"EU diesel deficit: ~{EU_DEFICIT_BASELINE_MT} Mt/y baseline "
        f"(Eurostat nrg_cb_oilm pooled 2018-2026; verify YTD-annualized in v2)."
    )
    print(stale_note)

    if not args.no_append:
        append_log_row(
            today=today,
            regime=REGIME_LABEL,
            days=days,
            b30=bs["mean_30d"],
            b60=bs["mean_60d"],
            blatest=bs["latest_beta"],
            eu_baseline=EU_DEFICIT_BASELINE_MT,
        )
        print(f"\nAppended row to {REGIMES_LOG.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
