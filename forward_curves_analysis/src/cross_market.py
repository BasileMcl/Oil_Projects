"""Cross-market analytics. Consumes two or more ForwardCurveAnalysis instances
and produces comparative stats, correlations (levels, first-diff, rolling,
lead-lag, annual), crack spreads and rolling hedge ratios.

All styling comes from config.yaml via the engine — no independent palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import warnings

import pandas as pd
from scipy import stats
from scipy.stats import kurtosis, skew

from .forward_curve_analytics import ForwardCurveAnalysis, load_config


class CrossMarketAnalysis:
    """N-way cross-market comparison. Defaults to LSGO ↔ Brent but generalises
    to any list of pre-built ForwardCurveAnalysis instances.

    Usage:
        >>> cma = CrossMarketAnalysis(['LSGO', 'BRENT']).load_all().merge()
        >>> cma.summary_stats()
        >>> cma.chart_scatter()
        >>> cma.chart_rolling_corr()
        >>> cma.chart_crack_spread(NUMERATOR='LSGO', DENOMINATOR='BRENT')
        >>> cma.chart_rolling_hedge_ratio(Y='LSGO', X='BRENT')
    """

    # Volumetric conversions (bbl per metric tonne)
    # Source: industry standard for clean products. Gasoil/ULSD ≈ 7.45.
    BBL_PER_MT_DEFAULT = 7.45

    def __init__(self, COMMODITIES, CONFIG_PATH=None, SAVE_FIGURES=True):
        cfg = load_config(CONFIG_PATH)
        self.CONFIG = cfg
        self.ROOT   = Path(CONFIG_PATH).resolve().parent if CONFIG_PATH else \
                      Path(ForwardCurveAnalysis.__module__).resolve().parent.parent
        # Styling, straight from engine config
        plot = cfg['PLOT']
        self.COLORS   = plot['COLORS']
        self.SIZES    = {k: tuple(v) for k, v in plot['SIZES'].items()}
        self.LW       = plot['LINEWIDTH']
        self.A        = plot['ALPHA']
        self.SAVE_OPTS = plot['SAVE']
        self.XAXIS    = plot['XAXIS']
        self.FILES    = cfg['CHART_FILES']
        plt.rcParams.update(plot['RCPARAMS'])

        self.OUTPUT_DIR = (
            Path(cfg['PATHS']['FIGURES']).resolve() / 'cross_market'
            if SAVE_FIGURES else None
        )
        # If the path is relative, anchor it against the config's project root.
        if SAVE_FIGURES and not Path(cfg['PATHS']['FIGURES']).is_absolute():
            # forward_curve_analytics resolves DEFAULT_CONFIG to project root
            from .forward_curve_analytics import DEFAULT_CONFIG
            self.OUTPUT_DIR = Path(DEFAULT_CONFIG).resolve().parent / cfg['PATHS']['FIGURES'] / 'cross_market'

        # Accept either string keys or pre-built engine instances
        self.ENGINES = {}
        for item in COMMODITIES:
            if isinstance(item, ForwardCurveAnalysis):
                self.ENGINES[item.COMMODITY.upper()] = item
            else:
                self.ENGINES[str(item).upper()] = ForwardCurveAnalysis(
                    COMMODITY=item, CONFIG_PATH=CONFIG_PATH, SAVE_FIGURES=False)

        self.keys  = list(self.ENGINES.keys())          # e.g. ['LSGO','BRENT']
        self.merged = None                              # common-date frame

    # Pipeline ---------------------------------------------------------------

    def load_all(self):
        for fca in self.ENGINES.values():
            if fca.df_rolling is None:
                fca.load().build()
        return self

    def merge(self):
        """Inner-join on Date across all engines. Columns per commodity:
        {KEY}_M1, {KEY}_M1_M3, {KEY}_M1_M6, {KEY}_Vol."""
        frames = []
        for k, fca in self.ENGINES.items():
            f = fca.df_rolling[['Date', 'M1', 'M1_M3', 'M1_M6', fca.VOL_COL]].copy()
            f = f.rename(columns={
                'M1':      f'{k}_M1',
                'M1_M3':   f'{k}_M1_M3',
                'M1_M6':   f'{k}_M1_M6',
                fca.VOL_COL: f'{k}_Vol',
            })
            frames.append(f)
        merged = frames[0]
        for f in frames[1:]:
            merged = merged.merge(f, on='Date', how='inner')
        self.merged = merged.sort_values('Date').reset_index(drop=True)
        print(f'[CrossMarket] merged: {len(self.merged)} common days '
              f'| {self.merged["Date"].min().date()} → {self.merged["Date"].max().date()} '
              f'| commodities: {self.keys}')
        return self

    # Descriptive / diagnostic ----------------------------------------------

    def summary_stats(self):
        """Side-by-side comparative stats table. Units embedded in the values,
        not in row labels, so rows align cleanly across commodities with
        different units (USD/MT for LSGO, USD/bbl for Brent/WTI)."""
        rows = {}
        for k, fca in self.ENGINES.items():
            df = fca.df_rolling
            m = df[['M1_M3', 'M1_M6', fca.VOL_COL, 'Z_M1_M3']].dropna(subset=['M1_M3'])
            u = fca.UNIT
            rows[k] = {
                'n':                   len(df),
                'Backwardation %':     f'{100 * (df["M1_M3"] > 0).mean():.1f}%',
                'Unit':                u,
                'M1-M3 mean':          f'{df["M1_M3"].mean():.2f} {u}',
                'M1-M6 mean':          f'{df["M1_M6"].mean():.2f} {u}',
                'M1-M3 max':           f'{df["M1_M3"].max():.2f} {u}',
                'Max |Z|':             f'{df["Z_M1_M3"].abs().max():.2f}',
                'Vol peak':            f'{df[fca.VOL_COL].max()*100:.0f}%',
                'Skewness M1-M3':      f'{skew(m["M1_M3"]):.2f}',
                'Ex. kurtosis M1-M3':  f'{kurtosis(m["M1_M3"]):.2f}',
                'Corr M1-M3 vs Vol':   f'{m["M1_M3"].corr(m[fca.VOL_COL]):.3f}',
                'Days |Z|>3':          f'{(df["Z_M1_M3"].abs()>3).sum()} ({100*(df["Z_M1_M3"].abs()>3).sum()/len(df):.1f}%)',
            }
        out = pd.DataFrame(rows)
        print(out.to_string())
        return out

    def correlations(self):
        """Pairwise correlations across levels, first-differences and log-returns
        for each (commodity_i, commodity_j) pair."""
        m = self.merged
        out = []
        for i, a in enumerate(self.keys):
            for b in self.keys[i+1:]:
                for col in ('M1', 'M1_M3', 'M1_M6', 'Vol'):
                    c1, c2 = f'{a}_{col}', f'{b}_{col}'
                    levels  = m[c1].corr(m[c2])
                    dd      = m[c1].diff().corr(m[c2].diff())
                    logret  = (np.log(m[c1]) - np.log(m[c1].shift(1))).corr(
                              np.log(m[c2]) - np.log(m[c2].shift(1))) if col == 'M1' else np.nan
                    # significance (levels)
                    d = m[[c1, c2]].dropna()
                    n = len(d)
                    r = d[c1].corr(d[c2])
                    t = r * np.sqrt(max(n - 2, 1)) / np.sqrt(max(1 - r**2, 1e-12))
                    p = 2 * (1 - stats.t.cdf(abs(t), df=max(n - 2, 1)))
                    out.append({
                        'pair': f'{a} vs {b}', 'metric': col,
                        'levels': levels, 'first_diff': dd, 'log_return': logret,
                        'n': n, 'p_levels': p,
                    })
        out = pd.DataFrame(out)
        # Build display copy — pad labels so the ASCII table has explicit
        # columns regardless of terminal width.
        display = out.copy()
        display['pair']   = display['pair'].astype(str).str.ljust(16)
        display['metric'] = display['metric'].astype(str).str.ljust(6)
        display['log_return'] = display['log_return'].apply(
            lambda v: f'{v:+.3f}' if pd.notna(v) else '  n/a')
        for c in ('levels', 'first_diff', 'p_levels'):
            display[c] = display[c].apply(lambda v: f'{v:+.3f}')
        display['n'] = display['n'].astype(int)
        with pd.option_context('display.max_columns', None,
                                'display.width', 220,
                                'display.expand_frame_repr', False):
            print(display.to_string(index=False))
        return out

    def rolling_correlations(self, WINDOW=60):
        m = self.merged.copy()
        for i, a in enumerate(self.keys):
            for b in self.keys[i+1:]:
                for col in ('M1', 'M1_M3', 'M1_M6'):
                    m[f'RC_{col}_{a}_{b}'] = m[f'{a}_{col}'].rolling(WINDOW).corr(m[f'{b}_{col}'])
        self.merged = m
        return self

    def lead_lag(self, LAGS=range(-10, 11), A=None, B=None, COL='M1'):
        a = A or self.keys[0]
        b = B or self.keys[1]
        m = self.merged
        xs = [m[f'{a}_{COL}'].corr(m[f'{b}_{COL}'].shift(lag)) for lag in LAGS]
        return list(LAGS), xs

    def annual_coupling(self, SPREAD='M1_M3', A=None, B=None):
        a = A or self.keys[0]
        b = B or self.keys[1]
        m = self.merged.copy()
        m['dA'] = m[f'{a}_{SPREAD}'].diff()
        m['dB'] = m[f'{b}_{SPREAD}'].diff()
        m['year'] = m['Date'].dt.year
        g = (m.groupby('year')
               .apply(lambda d: d['dA'].corr(d['dB']))
               .rename('r')
               .reset_index())
        return g

    # Crack spread and hedge ratios -----------------------------------------

    def crack_spread(self, NUMERATOR, DENOMINATOR, BBL_PER_MT=None):
        """Crack (refining margin proxy) in USD/bbl.
        product-in-USD/MT converted to USD/bbl via BBL_PER_MT.
        Both series must share common dates (done by merge()).
        """
        n = NUMERATOR.upper()
        d = NUMERATOR.upper()  # guard against mistype
        d = DENOMINATOR.upper()
        n_fca = self.ENGINES[NUMERATOR.upper()]
        d_fca = self.ENGINES[DENOMINATOR.upper()]
        bbl_per_mt = BBL_PER_MT or self.BBL_PER_MT_DEFAULT

        m = self.merged[['Date', f'{n}_M1', f'{d}_M1']].copy()
        if n_fca.UNIT.endswith('/MT'):
            m[f'{n}_bbl'] = m[f'{n}_M1'] / bbl_per_mt
        else:
            m[f'{n}_bbl'] = m[f'{n}_M1']
        if d_fca.UNIT.endswith('/MT'):
            m[f'{d}_bbl'] = m[f'{d}_M1'] / bbl_per_mt
        else:
            m[f'{d}_bbl'] = m[f'{d}_M1']
        m['crack'] = m[f'{n}_bbl'] - m[f'{d}_bbl']
        return m

    def matched_brent_lsgo_spread(self, DATA_ROOT=None, BBL_PER_MT=7.45):
        """Compute a delivery-month-matched Brent-LSGO spread using the
        futures_calendar pairing. For each trade date, pull Brent M1 and the
        LSGO M-column whose delivery month matches Brent M1's. LSGO is
        converted to USD/bbl via BBL_PER_MT (default 7.45 for gasoil).

        Returns a DataFrame with columns:
            Date
            pair_label          e.g. 'Brent M1 × LSGO M2'
            brent_m1_bbl        Brent M1 settlement, USD/bbl
            lsgo_matched_mt     LSGO M{match} settlement, USD/MT
            lsgo_matched_bbl    same / BBL_PER_MT
            spread_usd_bbl      Brent M1 - LSGO_matched_bbl (USD/bbl)

        Versus the naive M1 - M1 spread this version removes the
        term-structure leak from a mismatched delivery month. See
        CRACK_METHODOLOGY.md at the portfolio root for the convention.
        """
        # Lazy import to avoid circular deps at module load
        from .futures_calendar import FuturesCalendar
        cal = FuturesCalendar()

        # Load Brent + LSGO strips directly from config-relative paths.
        # DATA_ROOT override lets callers point at a custom staging folder.
        cfg = self.cfg if hasattr(self, 'cfg') else load_config()
        root = Path(DATA_ROOT) if DATA_ROOT else (
            Path(cfg.get('PATHS', {}).get('DATA_ROOT', '../data')).resolve()
        )
        brent = pd.read_excel(root / 'raw' / 'Futures' / 'Brent_M1M12.xlsx')
        lsgo  = pd.read_excel(root / 'raw' / 'Futures' / 'LSGO_M1M12.xlsx')
        brent['Date'] = pd.to_datetime(brent['Date'])
        lsgo['Date']  = pd.to_datetime(lsgo['Date'])
        # Expected cols: 'BRN 1!-ICE'...'BRN 12!-ICE' / 'GAS 1!-ICE'...'GAS 12!-ICE'
        brent = brent.rename(columns={f'BRN {n}!-ICE': f'Brent_M{n}' for n in range(1, 13)})
        lsgo  = lsgo.rename(columns={f'GAS {n}!-ICE': f'LSGO_M{n}' for n in range(1, 13)})

        merged = brent.merge(lsgo, on='Date', how='inner').sort_values('Date').reset_index(drop=True)

        out_rows = []
        for _, row in merged.iterrows():
            pair = cal.pair_on(row['Date'])
            brent_m1 = row.get('Brent_M1')
            lsgo_col = f'LSGO_M{pair.lsgo_match_m}'
            lsgo_matched = row.get(lsgo_col)
            if pd.isna(brent_m1) or pd.isna(lsgo_matched):
                continue
            out_rows.append({
                'Date':             row['Date'],
                'pair_label':       pair.label,
                'brent_m1_bbl':     brent_m1,
                'lsgo_matched_mt':  lsgo_matched,
                'lsgo_matched_bbl': lsgo_matched / BBL_PER_MT,
                'spread_usd_bbl':   brent_m1 - lsgo_matched / BBL_PER_MT,
            })
        return pd.DataFrame(out_rows)

    def rolling_hedge_ratio(self, Y, X, WINDOW=90, SPREAD='M1_M3'):
        """Rolling-window OLS slope β of ΔY on ΔX over `WINDOW` trading days.
        Also returns 95% CI band (Newey-West naive / homoskedastic).

        For calendar-spread hedging: Y = LSGO (USD/MT), X = Brent (USD/bbl).
        Result has units of MT-of-LSGO per bbl-of-Brent.
        """
        y_key, x_key = Y.upper(), X.upper()
        m = self.merged[['Date', f'{y_key}_{SPREAD}', f'{x_key}_{SPREAD}']].copy()
        m[f'dY'] = m[f'{y_key}_{SPREAD}'].diff()
        m[f'dX'] = m[f'{x_key}_{SPREAD}'].diff()
        m = m.dropna().reset_index(drop=True)

        betas, ses = [], []
        for i in range(len(m)):
            if i < WINDOW:
                betas.append(np.nan); ses.append(np.nan); continue
            w = m.iloc[i - WINDOW:i]
            x, y = w['dX'].values, w['dY'].values
            x_bar = x.mean()
            y_bar = y.mean()
            s_xx = ((x - x_bar) ** 2).sum()
            if s_xx <= 0:
                betas.append(np.nan); ses.append(np.nan); continue
            beta = ((x - x_bar) * (y - y_bar)).sum() / s_xx
            residuals = y - (y_bar + beta * (x - x_bar))
            sigma2 = (residuals ** 2).sum() / max(len(w) - 2, 1)
            se = np.sqrt(sigma2 / s_xx)
            betas.append(beta); ses.append(se)
        m['beta'] = betas
        m['beta_lo'] = np.array(betas) - 1.96 * np.array(ses)
        m['beta_hi'] = np.array(betas) + 1.96 * np.array(ses)
        return m

    def matched_rolling_hedge_ratio(self, ANCHOR='LSGO', WINDOW=60,
                                    BBL_PER_MT=7.45, RETURNS='log',
                                    PAIRING='M2xM1', DATA_ROOT=None):
        """Rolling-window OLS β of ΔCrack on ΔBrent using the **matched
        delivery-month** crack. Conditions each date on the LSGO M1-M6
        regime flag from the anchor engine.

        PAIRING:
          'M2xM1' (default, chartbook convention) — refiner-lag pairing:
              crack = LSGO M1 (product sold prompt) − Brent M2 (crude bought
              1 month ahead). Captures the forward refining margin.
          'convergent' — same-delivery-month pairing via futures_calendar:
              crack = LSGO_matched_M − Brent M1. Captures pure paper basis
              with no refining lag.

        β = OLS slope of ΔCrack on ΔBrent_M1 over the rolling window
            (returns: 'log' = log-returns, default; or 'diff' = first-diffs)

        Returns dict with:
            'series'       DataFrame  Date / β / regime / pair_label / brent / crack
            'by_regime'    DataFrame  per-regime β stats (n, mean, median, std)
            'normal_beta'  float      mean β on Normal-regime days
            'crisis_beta'  float      mean β on Crisis-regime days
            'ratio'        float      crisis / normal

        Wired into production: this is the desk-grade matched-calendar β.
        """
        # 1. Build matched spread series
        if PAIRING == 'M1xM1':
            # Naïve prompt-vs-prompt: crack = LSGO_M1/7.45 - Brent_M1
            cfg = self.cfg if hasattr(self, 'cfg') else self.CONFIG
            root = (Path(DATA_ROOT) if DATA_ROOT else
                    Path(cfg.get('PATHS', {}).get('DATA_ROOT', '../data')).resolve())
            brent = pd.read_excel(root / 'raw' / 'Futures' / 'Brent_M1M12.xlsx')
            lsgo  = pd.read_excel(root / 'raw' / 'Futures' / 'LSGO_M1M12.xlsx')
            brent['Date'] = pd.to_datetime(brent['Date'])
            lsgo['Date']  = pd.to_datetime(lsgo['Date'])
            brent = brent.rename(columns={f'BRN {n}!-ICE': f'Brent_M{n}' for n in range(1, 13)})
            lsgo  = lsgo.rename(columns={f'GAS {n}!-ICE': f'LSGO_M{n}' for n in range(1, 13)})
            merged = brent.merge(lsgo, on='Date', how='inner').sort_values('Date').reset_index(drop=True)
            spread_df = pd.DataFrame({
                'Date':              merged['Date'],
                'pair_label':        'Brent M1 × LSGO M1 (naïve)',
                'brent_m1_bbl':      merged['Brent_M1'],
                'lsgo_matched_mt':   merged['LSGO_M1'],
                'lsgo_matched_bbl':  merged['LSGO_M1'] / BBL_PER_MT,
                'crack_matched_bbl': merged['LSGO_M1'] / BBL_PER_MT - merged['Brent_M1'],
            }).dropna(subset=['brent_m1_bbl', 'crack_matched_bbl']).reset_index(drop=True)
        elif PAIRING == 'M2xM1':
            # Load raw strips and compute crack = LSGO_M1/7.45 - Brent_M2
            from .futures_calendar import FuturesCalendar  # noqa: F401  (kept for parity)
            cfg = self.cfg if hasattr(self, 'cfg') else self.CONFIG
            root = (Path(DATA_ROOT) if DATA_ROOT else
                    Path(cfg.get('PATHS', {}).get('DATA_ROOT', '../data')).resolve())
            brent = pd.read_excel(root / 'raw' / 'Futures' / 'Brent_M1M12.xlsx')
            lsgo  = pd.read_excel(root / 'raw' / 'Futures' / 'LSGO_M1M12.xlsx')
            brent['Date'] = pd.to_datetime(brent['Date'])
            lsgo['Date']  = pd.to_datetime(lsgo['Date'])
            brent = brent.rename(columns={f'BRN {n}!-ICE': f'Brent_M{n}' for n in range(1, 13)})
            lsgo  = lsgo.rename(columns={f'GAS {n}!-ICE': f'LSGO_M{n}' for n in range(1, 13)})
            merged = brent.merge(lsgo, on='Date', how='inner').sort_values('Date').reset_index(drop=True)
            spread_df = pd.DataFrame({
                'Date':              merged['Date'],
                'pair_label':        'Brent M2 × LSGO M1',
                'brent_m1_bbl':      merged['Brent_M1'],
                'lsgo_matched_mt':   merged['LSGO_M1'],
                'lsgo_matched_bbl':  merged['LSGO_M1'] / BBL_PER_MT,
                'crack_matched_bbl': merged['LSGO_M1'] / BBL_PER_MT - merged['Brent_M2'],
            }).dropna(subset=['brent_m1_bbl', 'crack_matched_bbl']).reset_index(drop=True)
        else:
            # Convergent pairing via futures_calendar (Brent M1 × LSGO M_match)
            spread_df = self.matched_brent_lsgo_spread(
                DATA_ROOT=DATA_ROOT, BBL_PER_MT=BBL_PER_MT
            ).copy()
            spread_df['crack_matched_bbl'] = (
                spread_df['lsgo_matched_bbl'] - spread_df['brent_m1_bbl']
            )

        # 2. Compute returns
        if RETURNS == 'log':
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                spread_df['d_brent'] = np.log(spread_df['brent_m1_bbl']).diff()
                # log-return of crack: handle sign; use simple diff if any negative
                if (spread_df['crack_matched_bbl'] <= 0).any():
                    spread_df['d_crack'] = spread_df['crack_matched_bbl'].diff()
                else:
                    spread_df['d_crack'] = np.log(spread_df['crack_matched_bbl']).diff()
        else:
            spread_df['d_brent'] = spread_df['brent_m1_bbl'].diff()
            spread_df['d_crack'] = spread_df['crack_matched_bbl'].diff()

        # 3. Attach regime from anchor engine (LSGO M1-M6)
        anchor = ANCHOR.upper()
        if anchor not in self.ENGINES:
            raise KeyError(f'{anchor} not in {list(self.ENGINES)}')
        anchor_df = self.ENGINES[anchor].df_rolling[['Date', 'Regime']].copy()
        spread_df = spread_df.merge(anchor_df, on='Date', how='left')
        spread_df = spread_df.dropna(subset=['d_brent', 'd_crack', 'Regime']).reset_index(drop=True)

        # 4. Rolling-OLS β
        betas = []
        for i in range(len(spread_df)):
            if i < WINDOW:
                betas.append(np.nan)
                continue
            w = spread_df.iloc[i - WINDOW:i]
            x, y = w['d_brent'].values, w['d_crack'].values
            x_bar, y_bar = x.mean(), y.mean()
            s_xx = ((x - x_bar) ** 2).sum()
            if s_xx <= 0:
                betas.append(np.nan)
                continue
            beta = ((x - x_bar) * (y - y_bar)).sum() / s_xx
            betas.append(beta)
        spread_df['beta'] = betas

        # 5. Regime aggregation (collapse Tight/Stress/Crisis → 'Crisis-bucket')
        spread_df['regime_2state'] = spread_df['Regime'].map(
            lambda r: 'Crisis' if r in ('Tight', 'Stress', 'Crisis') else 'Normal'
        )
        valid = spread_df.dropna(subset=['beta'])
        by_regime = valid.groupby('regime_2state')['beta'].agg(
            ['count', 'mean', 'median', 'std']
        ).reset_index()

        normal_beta = float(valid.loc[valid['regime_2state'] == 'Normal', 'beta'].mean())
        crisis_beta = float(valid.loc[valid['regime_2state'] == 'Crisis', 'beta'].mean())
        ratio = crisis_beta / normal_beta if normal_beta else float('nan')

        return {
            'series':       spread_df,
            'by_regime':    by_regime,
            'normal_beta':  normal_beta,
            'crisis_beta':  crisis_beta,
            'ratio':        ratio,
        }

    def hedge_in_dollars(self, Y, X, POSITIONS_MT=(50_000, 100_000, 500_000),
                         WINDOW=90, SPREAD='M1_M3'):
        """Translate the current rolling β into a hedge size in bbls of X for
        a given long calendar-spread position in MT of Y.

        Position-notional logic:
        · Long P MT of Y calendar spread → ΔY·P dollars when ΔY moves 1 unit.
        · β says ΔY = β × ΔX. So to neutralise, short H bbls of X such that
          ΔX · H offsets — i.e. H = P · β bbls.

        Works for any Y / X where Y is priced in USD/MT and X in USD/bbl.
        """
        hr = self.rolling_hedge_ratio(Y, X, WINDOW=WINDOW, SPREAD=SPREAD)
        latest = hr['beta'].dropna().iloc[-1]
        hist   = hr['beta'].mean()

        print(f'Current rolling β ({WINDOW}d, Δ{SPREAD.replace("_","-")}) : {latest:+.3f}')
        print(f'Full-sample mean β                              : {hist:+.3f}')
        print()
        print(f'Hedge size (short X = {X}) per long Y = {Y} calendar spread:\n')
        print(f'  {"Y position (MT)":>20s}  {"Current β (bbls)":>22s}  '
              f'{"Historical mean β (bbls)":>28s}')
        for p in POSITIONS_MT:
            print(f'  {p:>20,d}  {int(p * latest):>22,d}  {int(p * hist):>28,d}')
        print()
        print(f'Ratio current / historical: {latest / hist:.1f}× — static hedges mis-size by this factor.')
        return {'latest': latest, 'hist': hist, 'positions': list(POSITIONS_MT)}

    def regime_conditional_correlation(self, ANCHOR_COMMODITY, METRIC='M1_M3'):
        """For each regime of the anchor commodity, compute the first-diff
        correlation of <METRIC> between the anchor and every other commodity
        in the cross-market set. Returns a regime × commodity table."""
        anchor = ANCHOR_COMMODITY.upper()
        if anchor not in self.ENGINES:
            raise KeyError(f'{anchor} not in {list(self.ENGINES)}')
        fca = self.ENGINES[anchor]
        m = self.merged.copy()
        m = m.merge(fca.df_rolling[['Date', 'Regime']], on='Date', how='left')

        others = [k for k in self.keys if k != anchor]
        # First-difference target columns
        for k in self.keys:
            m[f'd{k}'] = m[f'{k}_{METRIC}'].diff()

        regimes = ['Normal', 'Tight', 'Stress', 'Crisis']
        rows = {}
        for r in regimes:
            sub = m[m['Regime'] == r].dropna(subset=[f'd{anchor}'])
            if len(sub) < 10:
                rows[r] = {f'corr({anchor},{o})': np.nan for o in others}
                rows[r]['n'] = len(sub)
                continue
            row = {f'corr({anchor},{o})': sub[f'd{anchor}'].corr(sub[f'd{o}']) for o in others}
            row['n'] = len(sub)
            rows[r] = row
        return pd.DataFrame(rows).T

    def chart_regime_conditional_correlation(self, ANCHOR_COMMODITY, METRIC='M1_M3'):
        """Heatmap of regime-conditional first-diff correlation."""
        tbl = self.regime_conditional_correlation(ANCHOR_COMMODITY, METRIC)
        ns = tbl['n'].astype(int)
        corr = tbl.drop(columns='n')
        fig, ax = plt.subplots(figsize=(max(5, 1.5 * len(corr.columns) + 2), 3.5))
        im = ax.imshow(corr.values.astype(float), vmin=0, vmax=1, cmap='YlOrRd',
                       aspect='auto')
        ax.set_xticks(range(len(corr.columns)))
        ax.set_xticklabels(corr.columns, rotation=0)
        ax.set_yticks(range(len(corr.index)))
        ax.set_yticklabels([f'{r} (n={ns.loc[r]})' for r in corr.index])
        for i, r in enumerate(corr.index):
            for j, c in enumerate(corr.columns):
                v = corr.iloc[i, j]
                if pd.notna(v):
                    ax.text(j, i, f'{v:+.2f}', ha='center', va='center',
                            fontsize=11, color='white' if v > 0.5 else 'black')
        plt.colorbar(im, ax=ax, shrink=0.85).set_label('Pearson r (Δ)')
        ax.set_title(
            f'{ANCHOR_COMMODITY} Δ{METRIC.replace("_","-")} '
            f'correlation — conditional on {ANCHOR_COMMODITY} regime',
            loc='left')
        print(tbl.to_string())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            fig.tight_layout()
        # Save to cross_market figures dir (reuse corr-matrix key — they're cousins)
        if self.OUTPUT_DIR:
            self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            fig.savefig(self.OUTPUT_DIR / 'cross_08_regime_conditional_corr.png',
                        **self.SAVE_OPTS)
        return fig

    # Charts -----------------------------------------------------------------

    def chart_scatter(self):
        """2-way scatter dashboard (M1, M1-M3, M1-M6, Vol). With 3+ commodities,
        uses the first pair; for an n-way view call `chart_correlation_matrix()`."""
        m = self.merged
        a, b = self.keys[:2]
        fig, axes = plt.subplots(2, 2, figsize=self.SIZES['DASHBOARD'])
        pairs = [
            (f'{a}_M1',    f'{b}_M1',    'Price M1'),
            (f'{a}_M1_M3', f'{b}_M1_M3', 'Spread M1-M3'),
            (f'{a}_M1_M6', f'{b}_M1_M6', 'Spread M1-M6'),
            (f'{a}_Vol',   f'{b}_Vol',   'Vol 20D'),
        ]
        for ax, (xc, yc, title) in zip(axes.flat, pairs):
            r = m[xc].corr(m[yc])
            ax.scatter(m[xc], m[yc], s=14, alpha=self.A['SCATTER'],
                       color=self.COLORS['SCATTER'], edgecolor='none')
            d = m[[xc, yc]].dropna()
            if len(d) > 2:
                mslope, b0 = np.polyfit(d[xc], d[yc], 1)
                xs = np.array([d[xc].min(), d[xc].max()])
                ax.plot(xs, mslope * xs + b0, color=self.COLORS['TREND'],
                        linewidth=self.LW, alpha=self.A['PRIMARY'])
            ax.set_xlabel(f'{a} {title.split(" ",1)[-1] if " " in title else title}')
            ax.set_ylabel(f'{b} {title.split(" ",1)[-1] if " " in title else title}')
            ax.set_title(f'{title} — r = {r:.3f}', loc='left', fontsize=10)
        fig.suptitle(f'{a} ↔ {b} level relationships',
                     x=0.01, ha='left', fontsize=13, fontweight='bold', y=1.002)
        return self._finalize(fig, 'CROSS_SCATTER')

    def chart_rolling_corr(self, WINDOW=60):
        self.rolling_correlations(WINDOW)
        m = self.merged
        a, b = self.keys[:2]
        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        for col, color, ls, lbl in [
            ('M1',    self.COLORS['PRICE'], '-',  'Price (M1)'),
            ('M1_M3', self.COLORS['M1_M3'], '-',  'Spread M1-M3'),
            ('M1_M6', self.COLORS['M1_M6'], '--', 'Spread M1-M6'),
        ]:
            series = m[['Date', f'RC_{col}_{a}_{b}']].dropna()
            ax.plot(series['Date'], series[f'RC_{col}_{a}_{b}'], color=color,
                    linewidth=self.LW, linestyle=ls, label=lbl)
        ax.axhline(0, color='black', linewidth=0.8, alpha=0.5, linestyle='--')
        ax.set(xlabel='Date', ylabel=f'{WINDOW}-day rolling Pearson r', ylim=(-1.05, 1.05))
        ax.set_title(f'Time-varying {a} ↔ {b} correlation', loc='left')
        ax.legend(loc='lower left', fontsize=9)
        self._format_xaxis(ax)
        return self._finalize(fig, 'CROSS_ROLLING_CORR')

    def chart_lead_lag(self, LAGS=range(-10, 11)):
        a, b = self.keys[:2]
        lags, cp  = self.lead_lag(LAGS, A=a, B=b, COL='M1')
        _,    cs  = self.lead_lag(LAGS, A=a, B=b, COL='M1_M3')
        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        ax.plot(lags, cp, marker='o', markersize=5, linewidth=self.LW,
                color=self.COLORS['PRICE'], label='Price (M1)')
        ax.plot(lags, cs, marker='s', markersize=5, linewidth=self.LW,
                color=self.COLORS['M1_M3'], label='Spread (M1-M3)')
        ax.axvline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.5)
        ax.axhline(0, color=self.COLORS['REF'], linewidth=0.8, alpha=0.3)
        ax.set(xlabel=f'Lag (days; negative ⇒ {a} leads {b})', ylabel='Correlation')
        ax.set_title(f'Lead-lag cross-correlation {a} ↔ {b}', loc='left')
        ax.legend()
        max_p = max(zip(lags, cp), key=lambda t: abs(t[1]))
        max_s = max(zip(lags, cs), key=lambda t: abs(t[1]))
        print(f'Max |price corr| : {max_p[1]:+.3f} at lag {max_p[0]}')
        print(f'Max |spread corr|: {max_s[1]:+.3f} at lag {max_s[0]}')
        return self._finalize(fig, 'CROSS_LEAD_LAG')

    def chart_annual_coupling(self, SPREAD='M1_M3'):
        g = self.annual_coupling(SPREAD).dropna(subset=['r'])
        a, b = self.keys[:2]
        fig, ax = plt.subplots(figsize=self.SIZES['WIDE'])
        bars = ax.bar(g['year'].astype(str), g['r'],
                      color=self.COLORS['M1_M3'], edgecolor='white', alpha=0.85)
        ax.axhline(0, color='black', linewidth=0.8, alpha=0.5)
        for bar, r in zip(bars, g['r']):
            if pd.isna(r): continue
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + (0.02 if r >= 0 else -0.05),
                    f'{r:+.2f}', ha='center',
                    va='bottom' if r >= 0 else 'top', fontsize=9)
        ax.set(xlabel='Year', ylabel=f'Δ{SPREAD.replace("_","-")} correlation ({a} vs {b})',
               ylim=(-0.2, 1.0))
        ax.set_title(f'Annual Δ{SPREAD.replace("_","-")} coupling — {a} ↔ {b}', loc='left')
        return self._finalize(fig, 'CROSS_ANNUAL_COUPLING')

    def chart_crack_spread(self, NUMERATOR=None, DENOMINATOR=None, BBL_PER_MT=None):
        n = NUMERATOR  or self.keys[0]
        d = DENOMINATOR or self.keys[1]
        m = self.crack_spread(n, d, BBL_PER_MT)

        fig, (ax_top, ax_bot) = plt.subplots(
            2, 1, figsize=(self.SIZES['STANDARD'][0], self.SIZES['STANDARD'][1] + 3),
            gridspec_kw={'height_ratios': [2, 1], 'hspace': 0.28})

        ax_top.plot(m['Date'], m[f'{n.upper()}_bbl'], color=self.COLORS['M1_M3'],
                    linewidth=self.LW, label=f'{n} M1 (USD/bbl)')
        ax_top.plot(m['Date'], m[f'{d.upper()}_bbl'], color=self.COLORS['PRICE'],
                    linewidth=self.LW, label=f'{d} M1 (USD/bbl)')
        ax_top.set(ylabel='USD/bbl')
        ax_top.set_title(f'{n} vs {d} — unit-aligned front-month',
                         loc='left', fontsize=10, fontweight='normal')
        ax_top.legend(loc='upper left')
        self._format_xaxis(ax_top)

        ax_bot.plot(m['Date'], m['crack'], color=self.COLORS['VOL'], linewidth=self.LW)
        ax_bot.axhline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.5)
        ax_bot.set(ylabel=f'{n} − {d} (USD/bbl)', xlabel='Date')
        ax_bot.set_title(f'Crack spread — refining-margin proxy',
                         loc='left', fontsize=10, fontweight='normal')
        self._format_xaxis(ax_bot)

        mean = m['crack'].mean()
        peak = m.loc[m['crack'].idxmax()]
        print(f'Crack mean : {mean:.2f} USD/bbl')
        print(f'Crack peak : {peak["crack"]:.2f} on {peak["Date"].date()}')

        fig.suptitle(f'{n} − {d} crack spread', x=0.01, ha='left',
                     fontsize=13, fontweight='bold', y=0.995)
        return self._finalize(fig, 'CROSS_CRACK')

    def chart_rolling_hedge_ratio(self, Y=None, X=None, WINDOW=90, SPREAD='M1_M3'):
        y = Y or self.keys[0]
        x = X or self.keys[1]
        m = self.rolling_hedge_ratio(y, x, WINDOW=WINDOW, SPREAD=SPREAD)
        # Drop the warm-up rows where β is NaN — avoids matplotlib warnings
        # and a messy axis reaching back to the first raw date.
        m = m.dropna(subset=['beta']).reset_index(drop=True)

        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        ax.plot(m['Date'], m['beta'], color=self.COLORS['M1_M3'],
                linewidth=self.LW, label=f'β (window = {WINDOW}d)')
        ax.fill_between(m['Date'], m['beta_lo'], m['beta_hi'],
                        color=self.COLORS['M1_M3'], alpha=0.18, label='95% CI')
        ax.axhline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.5)
        ax.set(xlabel='Date',
               ylabel=f'Rolling β  (Δ{y} {SPREAD.replace("_","-")} per Δ{x} {SPREAD.replace("_","-")})')
        ax.set_title(f'Rolling hedge-ratio {y} on {x} ({SPREAD.replace("_","-")})',
                     loc='left')
        ax.legend(loc='upper left')
        self._format_xaxis(ax)

        last = m['beta'].dropna().iloc[-1] if m['beta'].dropna().size else np.nan
        print(f'Latest rolling β : {last:+.3f}   (positive = {y} spread widens when {x} spread widens)')
        return self._finalize(fig, 'CROSS_HEDGE_RATIO')

    def chart_basin_spread(self, Y='BRENT', X='WTI', ANNOTATE_EVENTS=True):
        """Crude basin spread = Y − X on M1 level. Default Brent − WTI.
        Annotates the mean and peak and, optionally, the 2022 invasion and
        2026 Hormuz event dates from the portfolio-wide major_dates.yaml."""
        y, x = Y.upper(), X.upper()
        if y not in self.keys or x not in self.keys:
            raise KeyError(f'Basin spread requires both {y} and {x} in the merge.')
        m = self.merged.copy()
        m['spread'] = m[f'{y}_M1'] - m[f'{x}_M1']

        fig, ax = plt.subplots(figsize=tuple(self.SIZES['STANDARD']))
        ax.plot(m['Date'], m['spread'], color=self.COLORS['M1_M3'],
                linewidth=self.LW)
        mean_s = m['spread'].mean()
        ax.axhline(mean_s, color=self.COLORS['REF'], linestyle=':',
                   linewidth=0.8, label=f'Mean = {mean_s:+.2f} USD/bbl')

        if ANNOTATE_EVENTS:
            # Two canonical basin-spread-moving events that are in our sample
            for dt, lbl in [(pd.Timestamp('2020-12-03'), 'OPEC+ rebalance + vaccine'),
                            (pd.Timestamp('2022-03-01'), 'Russia invasion'),
                            (pd.Timestamp('2026-04-13'), 'Hormuz blockade')]:
                if m['Date'].min() <= dt <= m['Date'].max():
                    ax.axvline(dt, color='black', linestyle='--',
                               linewidth=0.8, alpha=0.55)
                    y_top = m['spread'].max()
                    ax.annotate(lbl, xy=(dt, y_top),
                                xytext=(0, 8), textcoords='offset points',
                                ha='center', fontsize=8,
                                bbox=dict(boxstyle='round,pad=0.25',
                                          facecolor='white',
                                          edgecolor=self.COLORS.get('REF', '#888'),
                                          alpha=0.9))

        ax.set(xlabel='Date', ylabel=f'{y} − {x} M1 (USD/bbl)')
        ax.set_title(f'{y} − {x} M1 spread — trans-Atlantic basin',
                     loc='left')
        ax.legend(loc='upper left')

        peak = m.loc[m['spread'].idxmax()]
        trough = m.loc[m['spread'].idxmin()]
        print(f'{y} − {x} M1 spread — sample statistics')
        print(f'   Mean   : {mean_s:+.2f} USD/bbl')
        print(f'   Peak   : {peak["spread"]:+.2f} on {peak["Date"].date()}')
        print(f'   Trough : {trough["spread"]:+.2f} on {trough["Date"].date()}')

        # Use the existing hedge-ratio key slot if a dedicated one isn't configured
        key = 'CROSS_BASIN_SPREAD' if 'CROSS_BASIN_SPREAD' in self.FILES else None
        return self._finalize(fig, key) if key else fig

    def chart_correlation_matrix(self, METRIC='M1_M3', DIFFERENCED=True):
        """N×N correlation heatmap across all commodities on the chosen metric.
        Default: first-differenced M1-M3 spread (the stationary headline
        measure). Cell labels are Pearson r."""
        m = self.merged
        cols = [f'{k}_{METRIC}' for k in self.keys]
        X = m[cols].diff().dropna() if DIFFERENCED else m[cols].dropna()
        corr = X.corr().values
        n = len(self.keys)
        label_metric = f'Δ{METRIC.replace("_","-")}' if DIFFERENCED else METRIC.replace('_','-')

        fig, ax = plt.subplots(figsize=(max(5, 1.3*n + 2), max(4, 1.3*n + 1)))
        im = ax.imshow(corr, vmin=0, vmax=1, cmap='YlOrRd', aspect='auto')
        ax.set_xticks(range(n)); ax.set_xticklabels(self.keys, rotation=0)
        ax.set_yticks(range(n)); ax.set_yticklabels(self.keys)
        for i in range(n):
            for j in range(n):
                ax.text(j, i, f'{corr[i, j]:+.2f}', ha='center', va='center',
                        fontsize=11, color='white' if corr[i, j] > 0.5 else 'black')
        cb = plt.colorbar(im, ax=ax, shrink=0.85)
        cb.set_label('Pearson r')
        ax.set_title(f'{label_metric} correlation matrix (n = {len(X)})', loc='left')
        return self._finalize(fig, 'CROSS_CORR_MATRIX')

    # Helpers ----------------------------------------------------------------

    def _format_xaxis(self, ax):
        ax.xaxis.set_major_formatter(mdates.DateFormatter(self.XAXIS['FORMAT']))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=self.XAXIS['MONTHS'] * 3))

    def _finalize(self, fig, file_key):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            fig.tight_layout()
        if self.OUTPUT_DIR:
            self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            fig.savefig(self.OUTPUT_DIR / f'{self.FILES[file_key]}.png', **self.SAVE_OPTS)
        return fig
