"""Compute the production-grade matched-calendar regime-conditional β.

Runs the wired pipeline end-to-end:
  1. Build LSGO + Brent ForwardCurveAnalysis engines from raw config.
  2. Merge into CrossMarketAnalysis.
  3. Call matched_rolling_hedge_ratio() to compute β with the calendar pairing.
  4. Print Normal-β, Crisis-β, ratio. Save by-regime stats CSV for the chartbook.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]  # forward_curves_analysis/
sys.path.insert(0, str(ROOT))

from src.cross_market import CrossMarketAnalysis  # noqa: E402

CFG = ROOT / 'config.yaml'

cma = CrossMarketAnalysis(['LSGO', 'BRENT'], CONFIG_PATH=str(CFG), SAVE_FIGURES=False)
cma = cma.load_all().merge()

def report(out, label):
    import pandas as pd
    print(f'\n=== Production β — {label} ===\n')
    s = out['series'].dropna(subset=['beta']).copy()
    s['Date'] = pd.to_datetime(s['Date'])
    norm = s[s['regime_2state'] == 'Normal']
    cri  = s[s['regime_2state'] == 'Crisis']
    cri_2026 = cri[cri['Date'] >= '2026-01-01']
    cri_2022 = cri[(cri['Date'] >= '2022-02-01') & (cri['Date'] < '2023-01-01')]
    print(f"Normal (full)         n={len(norm):4d}  mean β = {norm['beta'].mean():+.4f}  median β = {norm['beta'].median():+.4f}")
    print(f"Crisis 2022 invasion  n={len(cri_2022):4d}  mean β = {cri_2022['beta'].mean():+.4f}  median β = {cri_2022['beta'].median():+.4f}")
    print(f"Crisis 2026 Hormuz    n={len(cri_2026):4d}  mean β = {cri_2026['beta'].mean():+.4f}  median β = {cri_2026['beta'].median():+.4f}")
    print(f"Latest β              {s.iloc[-1]['Date'].date()}  β = {s.iloc[-1]['beta']:+.4f}")
    print(f"Last 30 obs           mean β = {s.tail(30)['beta'].mean():+.4f}")
    return {'normal_full': norm['beta'].mean(),
            'crisis_2026': cri_2026['beta'].mean(),
            'latest': s.iloc[-1]['beta'],
            'last30_mean': s.tail(30)['beta'].mean()}

out_naive = cma.matched_rolling_hedge_ratio(
    ANCHOR='LSGO', WINDOW=60, RETURNS='log', PAIRING='M1xM1'
)
n_summary = report(out_naive, 'NAÏVE M1×M1 (LSGO M1 − Brent M1)')

out = cma.matched_rolling_hedge_ratio(
    ANCHOR='LSGO', WINDOW=60, RETURNS='log', PAIRING='M2xM1'
)
m_summary = report(out, 'MATCHED M2×M1 (LSGO M1 − Brent M2)')

print()
print('=' * 60)
print('CHARTBOOK INPUTS (production-grade):')
print('=' * 60)
print(f"Naïve M1×M1   Normal:  {n_summary['normal_full']:+.2f}   Crisis-2026:  {n_summary['crisis_2026']:+.2f}   Latest:  {n_summary['latest']:+.2f}")
print(f"Matched M2×M1 Normal:  {m_summary['normal_full']:+.2f}   Crisis-2026:  {m_summary['crisis_2026']:+.2f}   Latest:  {m_summary['latest']:+.2f}")
print()
print('Trade-block sizing on a 50,000 bbl ULSD-crack-equivalent:')
for label, beta in [('Matched Crisis-2026 mean', m_summary['crisis_2026']),
                    ('Matched last-30-day mean', m_summary['last30_mean']),
                    ('Matched latest', m_summary['latest'])]:
    lots = round(50_000 * beta / 1000)
    print(f'  β = {beta:+.2f} ({label}) → {lots} short Brent lots')
print()
print(f"Latest 30 obs β tail:")
print(out['series'][['Date', 'pair_label', 'regime_2state', 'beta']].tail(30).to_string(index=False))

# Save the regime stats for the chartbook caption
out_dir = ROOT / 'outputs' / 'reports'
out_dir.mkdir(parents=True, exist_ok=True)
out['by_regime'].to_csv(out_dir / 'matched_beta_by_regime.csv', index=False)
out['series'][['Date', 'pair_label', 'regime_2state', 'beta']].to_csv(
    out_dir / 'matched_beta_series.csv', index=False
)
print(f'\nSaved {out_dir / "matched_beta_by_regime.csv"}')
print(f'Saved {out_dir / "matched_beta_series.csv"}')
