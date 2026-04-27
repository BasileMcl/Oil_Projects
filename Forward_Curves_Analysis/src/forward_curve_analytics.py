"""Forward curve analytics engine. All parameters live in config.yaml.

Portfolio-wide PLOT styling is inherited from ../plot_config.yaml.
Event overlays are read from ../major_dates.yaml (filtered by each
commodity's SYMBOL via the event's `affected:` field).
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy.stats import kurtosis, skew

# Targeted filters only — no global `warnings.filterwarnings('ignore')`.
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')
warnings.filterwarnings('ignore', category=RuntimeWarning)

logger = logging.getLogger(__name__)

# ==== Path constants (per coding_habits §4.3: path management in __init__) ===
FCA_ROOT       = Path(__file__).resolve().parent.parent
PORTFOLIO_ROOT = FCA_ROOT.parent
PLOT_CONFIG    = PORTFOLIO_ROOT / 'plot_config.yaml'
MAJOR_DATES    = PORTFOLIO_ROOT / 'major_dates.yaml'
DEFAULT_CONFIG = FCA_ROOT / 'config.yaml'
LSGO_DIR       = FCA_ROOT / 'LsGO_Analysis'
BRENT_DIR      = FCA_ROOT / 'Brent_Analysis'
WTI_DIR        = FCA_ROOT / 'WTI_Analysis'
CROSS_DIR      = FCA_ROOT / 'Cross_Market_Analysis'


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load per-project config + merge portfolio-wide PLOT block from
    `../plot_config.yaml`. Per-project config.yaml may override individual
    PLOT keys. Events are also merged in from `../major_dates.yaml` under
    the top-level `_MAJOR_DATES` key for downstream filtering."""
    with open(path or DEFAULT_CONFIG) as fh:
        cfg = yaml.safe_load(fh)
    if PLOT_CONFIG.exists():
        with open(PLOT_CONFIG) as fh:
            shared = yaml.safe_load(fh)
        cfg['PLOT'] = {**shared.get('PLOT', {}), **cfg.get('PLOT', {})}
    if MAJOR_DATES.exists():
        with open(MAJOR_DATES) as fh:
            cfg['_MAJOR_DATES'] = yaml.safe_load(fh)
    return cfg


def events_for_symbol(cfg: dict[str, Any], symbol: str,
                       include_observations: bool = False) -> dict[str, str]:
    """Filter `major_dates.yaml` for events affecting `symbol`. Returns a
    dict {date_str: label} compatible with the pre-existing EVENTS contract
    so downstream chart code doesn't need to change."""
    md = cfg.get('_MAJOR_DATES') or {}
    items = list(md.get('events', []))
    if include_observations:
        items += list(md.get('observations', []))
    out: dict[str, str] = {}
    for e in items:
        affected = e.get('affected') or []
        if symbol in affected or not affected:
            out[str(e['date'])] = str(e['label'])
    return out


plt.rcParams.update(load_config()['PLOT']['RCPARAMS'])


class ForwardCurveAnalysis:
    """Build rolling contracts, spreads, Z-scores, regimes and the chart set
    for a single commodity defined in config.yaml."""

    def __init__(self, COMMODITY: str, CONFIG_PATH: str | Path | None = None,
                  SAVE_FIGURES: bool = True) -> None:
        cfg = load_config(CONFIG_PATH)
        self.CONFIG = cfg
        self.ROOT = Path(CONFIG_PATH or DEFAULT_CONFIG).resolve().parent

        key = COMMODITY.upper()
        if key not in cfg['COMMODITIES']:
            raise KeyError(f'Unknown commodity {COMMODITY!r}. Available: {list(cfg["COMMODITIES"])}')

        com, ana, plot = cfg['COMMODITIES'][key], cfg['ANALYSIS'], cfg['PLOT']

        self.COMMODITY = com['NAME']
        self.SYMBOL    = com.get('SYMBOL', com['NAME'])
        self.UNIT = com['UNIT']
        self.DETECT_EXPIRY = com['DETECT_DUPLICATE_EXPIRY']
        self.PRE_ROLLED = com.get('PRE_ROLLED', False)
        self.THRESHOLDS = com['REGIME_THRESHOLDS']
        self.SNAPSHOTS = com['SNAPSHOT_DATES']
        # Events come from the portfolio-wide major_dates.yaml, filtered by SYMBOL.
        # Per-commodity overrides can set a local EVENTS dict in config.yaml (none do).
        self.EVENTS = com.get('EVENTS') or events_for_symbol(cfg, self.SYMBOL)
        self.DATA_FILE = self.ROOT / com['DATA_FILE']

        self.DATE_FORMAT = ana['DATE_FORMAT']
        self.NUM_MONTHS = ana['NUM_CONTRACT_MONTHS']
        self.VOL_WINDOW = ana['VOLATILITY_WINDOW']
        self.Z_WINDOW = ana['ZSCORE_WINDOW']
        self.Z_MODE = ana.get('ZSCORE_MODE', 'rolling')
        self.Z_IS_END = pd.to_datetime(ana.get('ZSCORE_IS_END', '2024-12-31'))
        self.ANNUAL_DAYS = ana['ANNUAL_TRADING_DAYS']
        self.HIST_BINS = ana['HISTOGRAM_BINS']
        self.EXTREME_PCT = ana['EXTREME_RETURN_PCT']
        self.Z_EXTREME = ana['ZSCORE_EXTREME']
        self.Z_EXPECTED_PCT = ana['ZSCORE_EXPECTED_PCT']
        self.RECENT_MONTHS = ana.get('RECENT_WINDOW_MONTHS', 18)
        self.RECENT_START = (pd.to_datetime(ana['RECENT_START_DATE'])
                             if ana.get('RECENT_START_DATE') else None)
        self.DATED_FILE = (self.ROOT / com['DATED_FILE']) if com.get('DATED_FILE') else None

        self.COLORS = plot['COLORS']
        self.SIZES = {k: tuple(v) for k, v in plot['SIZES'].items()}
        self.LW = plot['LINEWIDTH']
        self.A = plot['ALPHA']
        self.SAVE_OPTS = plot['SAVE']
        self.XAXIS = plot['XAXIS']
        self.Z_LINES = plot['ZSCORE_LINES']
        self.FILES = cfg['CHART_FILES']

        self.VOL_COL = f'Vol_{self.VOL_WINDOW}D'
        self.OUTPUT_DIR = (
            self.ROOT / cfg['PATHS']['FIGURES'] / com['SUBDIR']
            if SAVE_FIGURES else None
        )

        self.df_raw = None
        self.df_rolling = None
        self.contract_cols = []

    # Pipeline ---------------------------------------------------------------

    def load(self) -> 'ForwardCurveAnalysis':
        """Load raw contract data from CSV or XLSX. Returns self for chaining."""
        suffix = self.DATA_FILE.suffix.lower()
        if suffix == '.csv':
            df = pd.read_csv(self.DATA_FILE)
            date_parse = lambda s: pd.to_datetime(s, format=self.DATE_FORMAT)
        elif suffix in ('.xlsx', '.xls'):
            df = pd.read_excel(self.DATA_FILE, sheet_name=0)
            date_parse = lambda s: pd.to_datetime(s, errors='coerce')
        else:
            raise ValueError(f'Unsupported data file format: {suffix}')

        df.columns = ['Date'] + df.columns[1:].tolist()
        df['Date'] = date_parse(df['Date'])
        df = (df.dropna(subset=['Date'])
                .sort_values('Date')
                .reset_index(drop=True))

        self.contract_cols = df.columns[1:].tolist()
        for col in self.contract_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        self.df_raw = df
        msg = (f'[{self.COMMODITY}] Loaded {len(df)} rows | '
               f'{df["Date"].min().date()} → {df["Date"].max().date()} | '
               f'{len(self.contract_cols)} contracts '
               f'({"pre-rolled" if self.PRE_ROLLED else "named-month"})')
        logger.info(msg)
        print(msg)   # keep visible in notebook output
        return self

    def build(self) -> 'ForwardCurveAnalysis':
        """Run the full analytical pipeline: rolling contracts → spreads →
        volatility → Z-scores → regime. Idempotent once `load()` has run."""
        self._build_contracts()
        self._add_roll_flags()
        self._add_spreads()
        self._add_volatility()
        self._add_zscores()
        self._add_regime()
        n_rolls = int(self.df_rolling["is_roll"].sum())
        roll_tag = (f'{n_rolls} rolls detected' if not self.PRE_ROLLED
                    else 'pre-rolled ICE series (individual rolls not recoverable)')
        msg = (f'[{self.COMMODITY}] Pipeline complete — {len(self.df_rolling)} rows, '
               f'{roll_tag}')
        logger.info(msg)
        print(msg)
        return self

    # Validation -------------------------------------------------------------

    def inspect_contracts(self):
        print(f'Contract coverage ({self.COMMODITY}):')
        for col in self.contract_cols:
            valid = self.df_raw[self.df_raw[col].notna()]
            n = len(valid)
            first, last = (valid['Date'].min(), valid['Date'].max()) if n else (None, None)
            print(f'  {col:10s}: {n:3d} days | {first} → {last}')
        return self

    def roll_summary(self):
        df = self.df_rolling
        rolls = df[df['is_roll']][['Date', 'M1_contract_prev', 'M1_contract',
                                   'M1', 'M1_change', 'M1_pct_change']].copy()
        if rolls.empty:
            tag = 'pre-rolled source — roll events not recoverable from this file'
            print(f'Roll dates (0 total) — {tag}')
            return rolls
        print(f'Roll dates ({len(rolls)} total):')
        print(rolls.to_string(index=False))
        print(f'\nMean |roll jump| : {rolls["M1_pct_change"].abs().mean():.2f}%')
        print(f'Max  |roll jump| : {rolls["M1_pct_change"].abs().max():.2f}%')
        return rolls

    def validate(self):
        df = self.df_rolling
        cols = ['M1', 'M2', 'M3', 'M6', 'M1_M2', 'M1_M3', 'M1_M6',
                self.VOL_COL, 'Z_M1_M3', 'Z_M1_M6']
        print(f'=== VALIDATION SUMMARY — {self.COMMODITY} ===')
        print(f'Observations : {len(df)}')
        print(f'Date range   : {df["Date"].min().date()} → {df["Date"].max().date()}')
        print(f'Roll events  : {df["is_roll"].sum()}')
        print(f'M1 range     : [{df["M1"].min():.2f}, {df["M1"].max():.2f}] {self.UNIT}')
        print('\nMissing values:')
        for col in cols:
            if col in df.columns:
                n = df[col].isna().sum()
                print(f'  {col:15s}: {n:3d} ({100*n/len(df):4.1f}%)')
        extreme = df[df['M1_pct_change'].abs() > self.EXTREME_PCT]
        print(f'\nExtreme daily returns (>{self.EXTREME_PCT:.0f}%): {len(extreme)} days')
        ok = (df['M1_M3'].abs() >= df['M1_M2'].abs()).sum()
        print(f'Spread ordering |M1-M3|≥|M1-M2|: {ok}/{len(df)} ({100*ok/len(df):.1f}%)')
        print('\nStatus: VALIDATED')
        return self

    def summary_stats(self):
        df = self.df_rolling
        r_m3 = df[['M1_M3', self.VOL_COL]].dropna().corr().iloc[0, 1]
        r_m6 = df[['M1_M6', self.VOL_COL]].dropna().corr().iloc[0, 1]
        z_hits = (df['Z_M1_M3'].abs() > self.Z_EXTREME).sum()
        stats = {
            'Backwardation (M1>M3)':                    f'{100 * (df["M1_M3"] > 0).mean():.1f}%',
            f'M1-M3 mean ({self.UNIT})':                f'{df["M1_M3"].mean():.2f}',
            f'M1-M6 mean ({self.UNIT})':                f'{df["M1_M6"].mean():.2f}',
            f'M1-M3 max ({self.UNIT})':                 f'{df["M1_M3"].max():.2f}',
            f'M1-M6 max ({self.UNIT})':                 f'{df["M1_M6"].max():.2f}',
            'Z-score M1-M3 peak':                       f'{df["Z_M1_M3"].max():.2f}',
            'Vol peak (annualised)':                    f'{df[self.VOL_COL].max()*100:.0f}%',
            'M1-M3 skewness':                           f'{skew(df["M1_M3"].dropna()):.2f}',
            'M1-M3 excess kurtosis':                    f'{kurtosis(df["M1_M3"].dropna()):.2f}',
            'Corr M1-M3 vs Vol':                        f'{r_m3:.3f}',
            'Corr M1-M6 vs Vol':                        f'{r_m6:.3f}',
            f'Days |Z|>{self.Z_EXTREME:.0f} (vs {self.Z_EXPECTED_PCT}% expected)':
                f'{z_hits} ({100*z_hits/len(df):.1f}%)',
        }
        result = pd.DataFrame.from_dict(stats, orient='index', columns=[self.COMMODITY])
        print(result.to_string())
        return result

    def calibrate_thresholds(self, IS_END='2024-12-31', QUANTILES=None, SPREAD='M1_M6'):
        """Quantile-based regime thresholds on an in-sample window.
        Default in-sample window: inception → 2024-12-31 (keeps 2025+ as OOS)."""
        q = QUANTILES or {'TIGHT': 0.80, 'STRESS': 0.95, 'CRISIS': 0.99}
        df = self.df_rolling
        is_df = df[df['Date'] <= pd.to_datetime(IS_END)]
        oos_df = df[df['Date'] >  pd.to_datetime(IS_END)]
        series = is_df[SPREAD].dropna()
        thresholds = {k: round(float(series.quantile(v)), 2) for k, v in q.items()}

        def regime_counts(frame, thr):
            s = frame[SPREAD].dropna()
            n = len(s)
            if n == 0:
                return {}
            return {
                'Normal':  int((s <= thr['TIGHT']).sum()),
                'Tight':   int(((s > thr['TIGHT']) & (s <= thr['STRESS'])).sum()),
                'Stress':  int(((s > thr['STRESS']) & (s <= thr['CRISIS'])).sum()),
                'Crisis':  int((s > thr['CRISIS']).sum()),
                'N':       n,
            }

        return {
            'commodity':       self.COMMODITY,
            'spread':          SPREAD,
            'quantiles':       q,
            'thresholds':      thresholds,
            'is_window':       (is_df['Date'].min().date().isoformat(),
                                is_df['Date'].max().date().isoformat(),
                                len(is_df)),
            'oos_window':      ((oos_df['Date'].min().date().isoformat(),
                                 oos_df['Date'].max().date().isoformat(),
                                 len(oos_df)) if len(oos_df) else None),
            'is_regime_days':  regime_counts(is_df,  thresholds),
            'oos_regime_days': regime_counts(oos_df, thresholds),
        }

    # Charts -----------------------------------------------------------------

    # ==== Shared primitive for every 2-panel faceted chart ==================
    def _two_panel_chart(self, draw_panel, df, title: str, file_key: str,
                          extra_height: int = 4):
        """Generic 2-panel faceted chart: full-sample top + recent-window bottom.

        Parameters
        ----------
        draw_panel : callable(ax, frame, subtitle) -> None
            Per-panel drawing function. Same callable used twice (top / bottom).
        df : pd.DataFrame
            Full-sample frame. The recent frame is derived via `self._recent(df)`.
        title : str
            Figure-level title (suptitle).
        file_key : str
            CHART_FILES config key for the saved PNG.
        extra_height : int
            Extra vertical inches beyond the STANDARD size to fit both panels.

        Returns
        -------
        matplotlib.figure.Figure
            The saved figure.
        """
        fig, (ax_full, ax_recent) = plt.subplots(
            2, 1,
            figsize=(self.SIZES['STANDARD'][0], self.SIZES['STANDARD'][1] + extra_height),
            sharex=False, gridspec_kw={'height_ratios': [1, 1], 'hspace': 0.35})
        draw_panel(ax_full,   df,                  'Full sample')
        draw_panel(ax_recent, self._recent(df),    self._recent_label())
        fig.suptitle(title, x=0.01, ha='left', fontsize=13, fontweight='bold', y=0.995)
        return self._finalize(fig, file_key)

    def chart_price_vol(self):
        """Faceted price + volatility — full sample top, current-year bottom."""
        return self._two_panel_chart(
            self._price_vol_panel, self.df_rolling,
            f'{self.COMMODITY} Front-Month Price and Volatility',
            'PRICE_VOL')

    def _price_vol_panel(self, ax, df, subtitle):
        c = self.COLORS
        ax.plot(df['Date'], df['M1'], color=c['PRICE'], linewidth=self.LW, label='M1')
        self._color_axis(ax, 'y', c['PRICE'], f'M1 ({self.UNIT})')
        ax2 = ax.twinx()
        ax2.plot(df['Date'], df[self.VOL_COL] * 100,
                 color=c['VOL'], linewidth=self.LW, alpha=self.A['PRIMARY'])
        self._color_axis(ax2, 'y', c['VOL'], 'Ann. Vol (%)')
        self._format_xaxis(ax)
        ax.set_title(subtitle, loc='left', fontsize=10, fontweight='normal')

    def chart_forward_curves(self, SNAPSHOT_DATES=None):
        dates = SNAPSHOT_DATES or self.SNAPSHOTS
        cycle = self.COLORS['CYCLE']
        xs = range(1, self.NUM_MONTHS + 1)
        fig, ax = plt.subplots(figsize=self.SIZES['SQUARE'])
        for i, d in enumerate(dates):
            row = self.df_rolling[self.df_rolling['Date'] == pd.to_datetime(d)]
            if row.empty:
                continue
            r = row.iloc[0]
            curve = [r.get(f'M{s}', np.nan) for s in xs]
            ax.plot(xs, curve, marker='o', linewidth=2,
                    color=cycle[i % len(cycle)], label=d)
        ax.set(xlabel='Contract Month', ylabel=f'Price ({self.UNIT})')
        ax.set_title('Forward Curve Snapshots', loc='left')
        ax.set_xticks(list(xs))
        ax.set_xticklabels([f'M{s}' for s in xs])
        ax.legend()
        return self._finalize(fig, 'FORWARD_CURVES')

    def chart_short_structure(self):
        return self._spread_chart(['M1_M2', 'M1_M3'],
                                  'Short-Term Structure: M1-M2 and M1-M3',
                                  'SHORT_STRUCTURE')

    def chart_long_structure(self):
        return self._spread_chart(['M1_M6'], 'Long Structure: M1-M6', 'LONG_STRUCTURE')

    def chart_full_strip(self):
        """M1-M3, M1-M6 and M1-M12 on the same axis (only if NUM_MONTHS ≥ 12)."""
        cols = [c for c in ('M1_M3', 'M1_M6', 'M1_M12') if c in self.df_rolling.columns]
        title = f'Calendar Structure: {" · ".join(c.replace("_", "-") for c in cols)}'
        return self._spread_chart(cols, title, 'FULL_STRIP')

    def chart_zscore(self, SPREAD: str = 'M1_M3'):
        """Faceted Z-score — full sample top, current-year bottom.
        Axis clipped at ±10 with off-chart peak annotations (IS-anchored Z can
        otherwise reach 100+σ and squash the rest of the series)."""
        mode_tag = self.df_rolling.attrs.get('Z_MODE', 'rolling')
        subtitle = (f'({self.Z_WINDOW}-day rolling)' if mode_tag == 'rolling'
                     else '(IS-anchored)')
        def _draw(ax, frame, stitle: str) -> None:
            self._zscore_panel(ax, frame, SPREAD, stitle)
        return self._two_panel_chart(
            _draw, self.df_rolling,
            f'Z-Score of {SPREAD.replace("_","-")} {subtitle}',
            'ZSCORE_M1_M3' if SPREAD == 'M1_M3' else 'ZSCORE_M1_M6')

    def _zscore_panel(self, ax, df, spread, subtitle, CLIP=5.0):
        """Plot Z with y-axis clipped at ±CLIP — readable under IS-anchored mode
        where single points can reach 100+σ under current-regime dislocation.
        Off-chart peaks are annotated with the actual (uncapped) value + date.

        Why capped: a Z of 68 means the current level is statistically impossible
        under the pre-2025 distribution — the chart should show this as 'off
        chart' rather than stretch the axis and crush the rest of the series.
        """
        z = df[f'Z_{spread}']
        z_plot = z.clip(-CLIP, CLIP)
        ax.plot(df['Date'], z_plot, color=self.COLORS['ZSCORE'],
                linewidth=self.LW, label=f'Z {spread.replace("_","-")}')
        for lvl, ls in zip(self.Z_LINES['LEVELS'], self.Z_LINES['LINESTYLES']):
            ax.axhline(lvl, color=self.COLORS['REF'], linestyle=ls,
                       linewidth=0.8, alpha=self.A['REF'])
        ax.set(xlabel='Date',
               ylabel=f'Z-Score (IS-anchored, capped at ±{int(CLIP)})',
               ylim=(-CLIP - 1, CLIP + 1))
        ax.set_title(subtitle, loc='left', fontsize=10, fontweight='normal')
        # Annotate off-chart peaks with actual value + date
        peaks_pos = df[z >  CLIP]
        peaks_neg = df[z < -CLIP]
        if len(peaks_pos):
            idx = z.idxmax()
            ax.annotate(
                f'peak Z = {z.loc[idx]:.1f} on {df.loc[idx, "Date"].date()}',
                xy=(df.loc[idx, 'Date'], CLIP),
                xytext=(0, -14), textcoords='offset points', fontsize=8,
                ha='center',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                          edgecolor=self.COLORS.get('REF', '#888'), alpha=0.9),
                arrowprops=dict(arrowstyle='->', color='black', lw=0.8))
        if len(peaks_neg):
            idx = z.idxmin()
            ax.annotate(
                f'trough Z = {z.loc[idx]:.1f} on {df.loc[idx, "Date"].date()}',
                xy=(df.loc[idx, 'Date'], -CLIP),
                xytext=(0, 14), textcoords='offset points', fontsize=8,
                ha='center',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                          edgecolor=self.COLORS.get('REF', '#888'), alpha=0.9),
                arrowprops=dict(arrowstyle='->', color='black', lw=0.8))
        self._format_xaxis(ax)

    def chart_distribution(self):
        """IS vs OOS overlay — visualises the regime-specific tail story."""
        df = self.df_rolling
        is_data  = df.loc[df['Date'] <= self.Z_IS_END, 'M1_M3'].dropna()
        oos_data = df.loc[df['Date']  > self.Z_IS_END, 'M1_M3'].dropna()

        fig, (ax_full, ax_zoom) = plt.subplots(
            1, 2, figsize=(self.SIZES['STANDARD'][0] + 1, self.SIZES['SQUARE'][1]),
            gridspec_kw={'wspace': 0.25})

        def _draw(ax, title, xlim=None):
            ax.hist(is_data,  bins=self.HIST_BINS, color=self.COLORS['PRICE'],
                    alpha=0.55, edgecolor='white', density=True,
                    label=f'In-sample (n={len(is_data)})')
            ax.hist(oos_data, bins=self.HIST_BINS, color=self.COLORS['HIST'],
                    alpha=0.55, edgecolor='white', density=True,
                    label=f'OOS (n={len(oos_data)})')
            ax.axvline(is_data.mean(),  color=self.COLORS['PRICE'], linestyle='--',
                       linewidth=1.5, alpha=0.8,
                       label=f'IS μ = {is_data.mean():.2f}')
            if len(oos_data):
                ax.axvline(oos_data.mean(), color=self.COLORS['VOL'], linestyle='--',
                           linewidth=1.5, alpha=0.8,
                           label=f'OOS μ = {oos_data.mean():.2f}')
            if xlim is not None:
                ax.set_xlim(xlim)
            ax.set(xlabel=f'M1-M3 ({self.UNIT})', ylabel='Density')
            ax.set_title(title, loc='left', fontsize=10, fontweight='normal')
            ax.legend(fontsize=8, loc='upper right')
            ax.grid(True, alpha=0.3, axis='y'); ax.grid(False, axis='x')

        _draw(ax_full, 'Full range (OOS tail visible)')
        # Zoom to IS 99.5-pct range to show IS shape
        if len(is_data) >= 20:
            lo, hi = is_data.quantile(0.005), is_data.quantile(0.995)
            pad = (hi - lo) * 0.2
            _draw(ax_zoom, 'IS-range zoom (shape comparison)', xlim=(lo - pad, hi + pad))
        else:
            _draw(ax_zoom, 'IS-range zoom (shape comparison)')

        fig.suptitle(f'{self.COMMODITY} M1-M3 Distribution — IS vs OOS',
                     x=0.01, ha='left', fontsize=13, fontweight='bold', y=1.02)
        return self._finalize(fig, 'DISTRIBUTION')

    def chart_event_timeline(self, EVENTS=None):
        """Faceted event timeline. Events get horizontal labels with arrows
        pointing at the vertical line — no vertical text."""
        events = EVENTS if EVENTS is not None else self.EVENTS
        df, c = self.df_rolling, self.COLORS
        fig, (ax_full, ax_recent) = plt.subplots(
            2, 1, figsize=(self.SIZES['STANDARD'][0], self.SIZES['STANDARD'][1] + 4),
            gridspec_kw={'height_ratios': [1, 1], 'hspace': 0.45})

        def _panel(ax, frame, panel_events, subtitle):
            ax.plot(frame['Date'], frame['M1_M3'], color=c['M1_M3'],
                    linewidth=self.LW, label='M1-M3')
            self._color_axis(ax, 'y', c['M1_M3'], f'M1-M3 ({self.UNIT})')
            ax2 = ax.twinx()
            ax2.plot(frame['Date'], frame[self.VOL_COL] * 100,
                     color=c['VOL'], linewidth=self.LW, alpha=self.A['SECONDARY'])
            self._color_axis(ax2, 'y', c['VOL'], 'Vol (%)')

            y_top = frame['M1_M3'].max()
            for j, (d, label) in enumerate(panel_events.items()):
                dt = pd.to_datetime(d)
                if not (frame['Date'].min() <= dt <= frame['Date'].max()):
                    continue
                ax.axvline(dt, color='black', linestyle='--',
                           linewidth=1, alpha=0.55)
                # Staircase labels above the chart at three vertical levels
                level = j % 3
                y_off = 12 + 16 * level
                ax.annotate(
                    label, xy=(dt, y_top), xycoords='data',
                    xytext=(0, y_off), textcoords='offset points',
                    ha='center', fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                              edgecolor=c['REF'], alpha=0.9),
                    arrowprops=dict(arrowstyle='-', color='black', lw=0.6))
            ax.set_title(subtitle, loc='left', fontsize=10, fontweight='normal')
            ax.grid(True, alpha=0.3)
            self._format_xaxis(ax)

        _panel(ax_full,  df,                 events, 'Full sample')
        _panel(ax_recent, self._recent(df),  events, self._recent_label())

        fig.suptitle(f'{self.COMMODITY} — Event Timeline · M1-M3 spread & volatility',
                     x=0.01, ha='left', fontsize=12, fontweight='bold', y=0.995)
        return self._finalize(fig, 'EVENT_TIMELINE')

    def chart_dashboard(self):
        df, c = self.df_rolling, self.COLORS
        fig, axes = plt.subplots(2, 2, figsize=self.SIZES['DASHBOARD'])

        axes[0, 0].plot(df['Date'], df['M1'], color=c['PRICE'], linewidth=self.LW)
        axes[0, 0].set(title=f'M1 Price ({self.UNIT})', ylabel='Price')

        axes[0, 1].plot(df['Date'], df['M1_M3'], color=c['M1_M3'], linewidth=self.LW)
        self._zero_line(axes[0, 1])
        axes[0, 1].set(title=f'M1-M3 Spread ({self.UNIT})', ylabel='Spread')

        axes[1, 0].plot(df['Date'], df['Z_M1_M3'], color=c['ZSCORE'], linewidth=self.LW)
        for lvl, ls in zip(self.Z_LINES['LEVELS'], self.Z_LINES['LINESTYLES']):
            axes[1, 0].axhline(lvl, color=c['REF'], linestyle=ls,
                               linewidth=0.8, alpha=self.A['REF'])
        axes[1, 0].set(title=f'Z-Score M1-M3 ({self.Z_WINDOW}-Day)', ylabel='Z-Score')

        mean_vol = df[self.VOL_COL].mean() * 100
        axes[1, 1].plot(df['Date'], df[self.VOL_COL] * 100, color=c['VOL'], linewidth=self.LW)
        axes[1, 1].axhline(mean_vol, color=c['REF'], linestyle='--',
                           linewidth=0.8, alpha=self.A['REF'], label=f'Mean: {mean_vol:.0f}%')
        axes[1, 1].set(title=f'{self.VOL_WINDOW}-Day Annualised Volatility (%)', ylabel='Volatility (%)')
        axes[1, 1].legend(loc='upper left', fontsize=9)

        for ax in axes.flat:
            self._format_xaxis(ax)
        fig.suptitle(f'{self.COMMODITY} Market Dashboard', fontsize=14,
                     fontweight='bold', y=1.002)
        return self._finalize(fig, 'DASHBOARD')

    def chart_dated_event_study(self, EVENT_DATE='2026-04-07'):
        """Physical-vs-paper event study. Overlays Platts Dated Brent (DTD) on M1
        futures over the Dated file's window, marks a named event date.
        Requires `DATED_FILE` to be configured for the commodity."""
        if self.DATED_FILE is None:
            raise RuntimeError(f'No DATED_FILE configured for {self.COMMODITY}')
        dated = pd.read_excel(self.DATED_FILE, sheet_name=0)
        dated.columns = ['Date', 'Dated']
        dated['Date']  = pd.to_datetime(dated['Date'])
        dated['Dated'] = pd.to_numeric(dated['Dated'], errors='coerce')
        dated = dated.dropna().sort_values('Date').reset_index(drop=True)

        df = self.df_rolling
        window = df[(df['Date'] >= dated['Date'].min())
                  & (df['Date'] <= dated['Date'].max())]
        merged = window[['Date', 'M1']].merge(dated, on='Date', how='inner')

        fig, (ax_top, ax_bot) = plt.subplots(
            2, 1, figsize=(self.SIZES['STANDARD'][0], self.SIZES['STANDARD'][1] + 3),
            gridspec_kw={'height_ratios': [2, 1], 'hspace': 0.28})

        ax_top.plot(window['Date'], window['M1'], color=self.COLORS['PRICE'],
                    linewidth=self.LW, label='Futures M1')
        ax_top.plot(dated['Date'],  dated['Dated'], color=self.COLORS['VOL'],
                    linewidth=self.LW, label='Dated Brent (DTD)')
        if EVENT_DATE:
            ax_top.axvline(pd.to_datetime(EVENT_DATE), color='black',
                           linestyle='--', linewidth=1, alpha=0.6)
            ax_top.annotate(
                f'Event: {EVENT_DATE}', xy=(pd.to_datetime(EVENT_DATE),
                                            dated['Dated'].max()),
                xytext=(10, -5), textcoords='offset points', fontsize=9)
        ax_top.set(ylabel=f'Price ({self.UNIT})')
        ax_top.set_title('Physical Dated Brent vs paper front-month',
                         loc='left', fontsize=10, fontweight='normal')
        ax_top.legend(loc='upper left')
        self._format_xaxis(ax_top)

        basis = merged['Dated'] - merged['M1']
        ax_bot.plot(merged['Date'], basis, color=self.COLORS['M1_M3'],
                    linewidth=self.LW)
        self._zero_line(ax_bot)
        ax_bot.set(ylabel=f'Basis Dated − M1 ({self.UNIT})', xlabel='Date')
        ax_bot.set_title('Physical-paper basis (positive = physical premium)',
                         loc='left', fontsize=10, fontweight='normal')
        self._format_xaxis(ax_bot)

        peak_idx = basis.abs().idxmax() if len(basis) else None
        if peak_idx is not None:
            ax_bot.annotate(
                f'Peak |basis| = {basis.loc[peak_idx]:+.2f} ({merged.loc[peak_idx, "Date"].date()})',
                xy=(merged.loc[peak_idx, 'Date'], basis.loc[peak_idx]),
                xytext=(10, 10), textcoords='offset points',
                fontsize=9, bbox=dict(boxstyle='round,pad=0.3',
                                      facecolor='white', alpha=0.85))

        fig.suptitle(f'{self.COMMODITY} — Dated Brent event study',
                     x=0.01, ha='left', fontsize=13, fontweight='bold', y=0.995)
        return self._finalize(fig, 'DATED_EVENT_STUDY')

    def chart_long_history_context(self, T74_PATH=None, ANNOTATE_EVENTS=True):
        """Long-history context from OPEC ASB 2025 Table 74 (1990+ monthly
        settlements for ICE Brent and NYMEX WTI). Plots both front-month
        series, shades the IS/OOS windows used by this engine, and marks
        4 canonical crude-price events. No model dependency — pure context."""
        path = Path(T74_PATH) if T74_PATH else (
            PORTFOLIO_ROOT / 'Datas' / 'Raw_datas' / 'OPEC'
            / 'ASB_2025_tables_csv'
            / 'T74_ICE_Brent_NYMEX_WTI_monthly_USD_bbl.csv')
        t74 = pd.read_csv(path, parse_dates=['date'])
        brent_m1 = t74[(t74['instrument'] == 'ICE Brent')
                       & (t74['contract'] == '1st forward month')].sort_values('date')
        wti_m1 = t74[(t74['instrument'] == 'NYMEX WTI')
                     & (t74['contract'] == '1st forward month')].sort_values('date')

        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        ax.plot(brent_m1['date'], brent_m1['price_usd_bbl'],
                color=self.COLORS['PRICE'], linewidth=self.LW,
                label='ICE Brent front-month')
        ax.plot(wti_m1['date'], wti_m1['price_usd_bbl'],
                color=self.COLORS['VOL'], linewidth=self.LW, alpha=0.8,
                label='NYMEX WTI front-month')

        # IS / OOS shading to match the engine's 2024-12-31 calibration
        is_start = pd.Timestamp(self.df_rolling['Date'].min())
        is_end   = self.Z_IS_END
        oos_end  = pd.Timestamp(brent_m1['date'].max())
        ax.axvspan(is_start, is_end, color='#238b45', alpha=0.08,
                   label=f'IS window ({is_start.year}-{is_end.year})')
        ax.axvspan(is_end, oos_end, color='#888888', alpha=0.15,
                   label=f'OOS window ({is_end.year+1}+)')

        # Percentile line for today's level
        latest = brent_m1.iloc[-1]
        pct = (brent_m1['price_usd_bbl'] < latest['price_usd_bbl']).mean() * 100
        ax.axhline(latest['price_usd_bbl'], color=self.COLORS['M1_M3'],
                   linestyle=':', linewidth=0.9,
                   label=f'Latest Brent {latest["price_usd_bbl"]:.0f} USD/bbl '
                         f'({pct:.0f}th pct of 36y)')

        if ANNOTATE_EVENTS:
            canonicals = [
                ('1990-08-01',  32.4, 'Gulf War'),
                ('2008-07-01', 134.0, 'GFC peak'),
                ('2014-06-01', 111.8, 'Pre-shale-crash'),
                ('2022-03-01', 117.3, 'Russia invasion'),
            ]
            for dt, lvl, lbl in canonicals:
                ax.scatter(pd.Timestamp(dt), lvl, color='black', zorder=5, s=25)
                ax.annotate(lbl, xy=(pd.Timestamp(dt), lvl),
                            xytext=(8, 6), textcoords='offset points',
                            fontsize=8,
                            bbox=dict(boxstyle='round,pad=0.2',
                                      facecolor='white', alpha=0.85))

        ax.set(xlabel='Date', ylabel=f'Front-month ({self.UNIT})',
               title=f'{self.COMMODITY} & WTI — OPEC ASB monthly, 1990 → {oos_end.year}')
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

        peak = brent_m1.loc[brent_m1['price_usd_bbl'].idxmax()]
        trough = brent_m1.loc[brent_m1['price_usd_bbl'].idxmin()]
        print(f'Brent monthly — 36y context')
        print(f'   Peak   : {peak["price_usd_bbl"]:.1f} on {peak["date"].strftime("%Y-%m")}')
        print(f'   Trough : {trough["price_usd_bbl"]:.1f} on {trough["date"].strftime("%Y-%m")}')
        print(f'   Latest : {latest["price_usd_bbl"]:.1f} on {latest["date"].strftime("%Y-%m")} '
              f'(rank {pct:.0f}th pct of 36y sample)')

        return self._finalize(fig, 'LONG_HISTORY_CONTEXT')

    def fit_hmm(self, SPREAD='M1_M6', N_STATES=2, SEED=7, FIT_ON='full'):
        """Fit a 2-state Gaussian HMM on the chosen spread series.
        Returns the fitted model plus a DataFrame with date-indexed state and
        per-state probabilities. Temporal dynamics make this a proper regime-
        switching model (transition matrix + per-state emission distribution),
        distinct from the static CDF regime classifier.

        FIT_ON: 'is' (fit on pre-2025 window — regimes defined out-of-sample)
                or 'full' (fit on the whole sample).
        """
        from hmmlearn.hmm import GaussianHMM
        df = self.df_rolling.dropna(subset=[SPREAD]).copy()
        fit_df = df if FIT_ON == 'full' else df[df['Date'] <= self.Z_IS_END]
        X_fit = fit_df[[SPREAD]].values
        hmm = GaussianHMM(n_components=N_STATES, covariance_type='diag',
                          n_iter=200, random_state=SEED)
        hmm.fit(X_fit)

        X_all = df[[SPREAD]].values
        states = hmm.predict(X_all)
        probs  = hmm.predict_proba(X_all)

        # Sort states by emission mean so "Normal" is state 0
        order = np.argsort(hmm.means_.flatten())
        mapping = {int(orig): new for new, orig in enumerate(order)}
        states_sorted = np.array([mapping[s] for s in states])
        probs_sorted  = probs[:, order]

        df['HMM_state'] = states_sorted
        for i in range(N_STATES):
            df[f'HMM_p_state{i}'] = probs_sorted[:, i]

        # Sync state columns back into self.df_rolling (clobber any prior HMM columns
        # from a previous fit with a different N_STATES).
        stale = [c for c in self.df_rolling.columns if c.startswith('HMM_')]
        self.df_rolling = self.df_rolling.drop(columns=stale, errors='ignore')
        self.df_rolling = self.df_rolling.merge(
            df[['Date', 'HMM_state'] + [f'HMM_p_state{i}' for i in range(N_STATES)]],
            on='Date', how='left')

        self.hmm_model = hmm
        self.hmm_means = hmm.means_.flatten()[order]
        self.hmm_vars  = hmm.covars_.flatten()[order]
        self.hmm_trans = hmm.transmat_[order][:, order]
        self.hmm_n_states = N_STATES
        return df

    def forecast_next_day_regime(self, HORIZON=1):
        """Forecast future regime probability by iterating today's HMM state-prob
        vector through the transition matrix `HORIZON` times. Requires a prior
        `fit_hmm()` call."""
        if not hasattr(self, 'hmm_trans'):
            raise RuntimeError('Call fit_hmm() / chart_hmm_regime() first.')
        n_states = self.hmm_trans.shape[0]
        p_cols = [f'HMM_p_state{i}' for i in range(n_states)]
        missing = [c for c in p_cols if c not in self.df_rolling.columns]
        if missing:
            raise RuntimeError(
                f'HMM state columns missing from df_rolling: {missing}. '
                'Re-run chart_hmm_regime() with the desired N_STATES.')
        last = self.df_rolling.dropna(subset=p_cols).iloc[-1]
        today_probs = last[p_cols].values.astype(float)
        probs = today_probs.copy()
        trajectory = [probs.copy()]
        for _ in range(HORIZON):
            probs = probs @ self.hmm_trans
            trajectory.append(probs.copy())
        out = {
            'as_of':       last['Date'],
            'today':       {f'state_{i}': float(today_probs[i]) for i in range(n_states)},
            f'+{HORIZON}d':{f'state_{i}': float(probs[i])       for i in range(n_states)},
            'trans':       self.hmm_trans.tolist(),
            'means':       self.hmm_means.tolist(),
        }
        print(f'As of {last["Date"].date()}:')
        for h, step in enumerate(trajectory):
            label = 'today' if h == 0 else f'+{h}d'
            s = ' · '.join(f'P(state{i})={step[i]:.3f}' for i in range(n_states))
            print(f'  {label:5s}  {s}')
        return out

    def chart_hmm_regime(self, SPREAD='M1_M6', N_STATES=2, FIT_ON='full'):
        """Plot spread + overlay of HMM state probability for the 'crisis' state
        (the state with the largest emission mean)."""
        hmm_df = self.fit_hmm(SPREAD=SPREAD, N_STATES=N_STATES, FIT_ON=FIT_ON)
        crisis_col = f'HMM_p_state{N_STATES - 1}'

        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        ax.plot(hmm_df['Date'], hmm_df[SPREAD], color=self.COLORS['M1_M6'],
                linewidth=self.LW, label=f'{SPREAD.replace("_","-")} ({self.UNIT})')
        self._color_axis(ax, 'y', self.COLORS['M1_M6'],
                         f'{SPREAD.replace("_","-")} ({self.UNIT})')
        ax2 = ax.twinx()
        ax2.plot(hmm_df['Date'], hmm_df[crisis_col], color=self.COLORS['VOL'],
                 linewidth=self.LW, alpha=self.A['PRIMARY'],
                 label='P(crisis state)')
        self._color_axis(ax2, 'y', self.COLORS['VOL'], 'P(crisis state)')
        ax2.set_ylim(-0.02, 1.02)

        self._format_xaxis(ax)

        means_str = ' · '.join(f'μ{i}={m:.2f}' for i, m in enumerate(self.hmm_means))
        trans_str = f'P(stay-normal)={self.hmm_trans[0,0]:.2f} · P(stay-crisis)={self.hmm_trans[-1,-1]:.2f}'
        subtitle = f'Fit on {"IS 2019→2024" if FIT_ON == "is" else "full sample"} · {means_str} · {trans_str}'
        fig.suptitle(f'{self.COMMODITY} HMM regime on {SPREAD.replace("_","-")}',
                     x=0.01, ha='left', fontsize=13, fontweight='bold', y=0.995)
        ax.set_title(subtitle, loc='left', fontsize=9, fontweight='normal')

        # Print diagnostics
        print(f'HMM means (by state): {self.hmm_means}')
        print(f'HMM std   (by state): {np.sqrt(self.hmm_vars)}')
        print(f'Transition matrix:\n{self.hmm_trans}')
        crisis_days_oos = ((hmm_df['Date'] > self.Z_IS_END)
                           & (hmm_df[crisis_col] > 0.5)).sum()
        oos_n = (hmm_df['Date'] > self.Z_IS_END).sum()
        is_crisis_days = ((hmm_df['Date'] <= self.Z_IS_END)
                          & (hmm_df[crisis_col] > 0.5)).sum()
        is_n = (hmm_df['Date'] <= self.Z_IS_END).sum()
        print(f'IS  P(crisis)>0.5 days: {is_crisis_days}/{is_n} ({100*is_crisis_days/is_n:.1f}%)')
        print(f'OOS P(crisis)>0.5 days: {crisis_days_oos}/{oos_n} ({100*crisis_days_oos/oos_n:.1f}%)')

        return self._finalize(fig, 'HMM_REGIME')

    def chart_regime(self):
        df, t = self.df_rolling, self.THRESHOLDS
        fig, ax = plt.subplots(figsize=self.SIZES['WIDE'])
        for regime, color in self.COLORS['REGIMES'].items():
            mask = df['Regime'] == regime
            if mask.any():
                ax.scatter(df.loc[mask, 'Date'], df.loc[mask, 'M1_M6'],
                           c=color, label=regime, alpha=self.A['REGIME'], s=30)
        for level_name in ('TIGHT', 'STRESS', 'CRISIS'):
            regime_color = self.COLORS['REGIMES'][level_name.capitalize()]
            ax.axhline(t[level_name], color=regime_color, linestyle='--', linewidth=1,
                       alpha=self.A['REF'],
                       label=f'{level_name.capitalize()} ({t[level_name]} {self.UNIT})')
        ax.set(xlabel='Date', ylabel=f'M1-M6 Spread ({self.UNIT})')
        ax.set_title('Regime Classification Timeline', loc='left')
        ax.legend(loc='upper left', ncol=2, fontsize=9)
        self._format_xaxis(ax)
        return self._finalize(fig, 'REGIME')

    # Helpers ----------------------------------------------------------------

    def _spread_chart(self, columns: list[str], title: str, file_key: str):
        """2-panel spread chart driven by `_spread_panel`."""
        def _draw(ax, frame, stitle: str) -> None:
            self._spread_panel(ax, frame, columns, stitle)
        return self._two_panel_chart(_draw, self.df_rolling, title, file_key)

    def _spread_panel(self, ax, df, columns, subtitle, YSCALE='linear',
                      SYMLOG_THRESHOLD=1.0):
        """YSCALE: 'linear' (default) or 'symlog' (Tier-4 log-signed view —
        preserves sign and compresses extreme OOS tails while keeping IS shape
        visible. Threshold sets the linear-region width around zero)."""
        for col in columns:
            ax.plot(df['Date'], df[col], color=self.COLORS[col],
                    linewidth=self.LW, alpha=self.A['PRIMARY'],
                    label=col.replace('_', '-'))
        self._zero_line(ax)
        if YSCALE == 'symlog':
            ax.set_yscale('symlog', linthresh=SYMLOG_THRESHOLD)
        ax.set(xlabel='Date', ylabel=f'Spread ({self.UNIT})')
        ax.set_title(subtitle, loc='left', fontsize=10, fontweight='normal')
        ax.legend()
        self._format_xaxis(ax)

    def _recent(self, df):
        """Slice the trailing-recent window for the bottom panel of faceted
        charts. Prefer the config RECENT_START_DATE (pinpoints the current-year
        crisis) over a rolling N-month window (which on a 7-year series tends
        to reproduce the top panel). Falls back to N months if no start date."""
        if self.RECENT_START is not None:
            return df[df['Date'] >= self.RECENT_START].copy()
        cutoff = df['Date'].max() - pd.DateOffset(months=self.RECENT_MONTHS)
        return df[df['Date'] >= cutoff].copy()

    def _recent_label(self):
        if self.RECENT_START is not None:
            return f'{self.RECENT_START.year} YTD only'
        return f'Last {self.RECENT_MONTHS} months'

    def _zero_line(self, ax):
        ax.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)

    def _color_axis(self, ax, axis, color, label):
        ax.set_ylabel(label, color=color)
        ax.tick_params(axis=axis, labelcolor=color)

    def _format_xaxis(self, ax):
        """Adaptive tick density based on the plotted date range — years for
        multi-year, quarters for multi-month, sparser for short windows. Labels
        rotated 30° for readability."""
        t0, t1 = ax.get_xlim()
        span_days = t1 - t0
        if span_days > 365 * 3:
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        elif span_days > 365:
            ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(30)
            lbl.set_ha('right')

    def _finalize(self, fig, file_key: str):
        """Save the figure to its configured path (if `SAVE_FIGURES=True`) and
        return the Figure object for display in the calling notebook."""
        with warnings.catch_warnings():
            # twinx() axes trigger a harmless tight_layout warning — silence
            warnings.simplefilter('ignore', UserWarning)
            fig.tight_layout()
        if self.OUTPUT_DIR:
            self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            fig.savefig(self.OUTPUT_DIR / f'{self.FILES[file_key]}.png', **self.SAVE_OPTS)
        return fig

    # Pipeline internals -----------------------------------------------------

    def _build_contracts(self):
        if self.PRE_ROLLED:
            return self._build_contracts_pre_rolled()
        df = self.df_raw
        expired = {}
        if self.DETECT_EXPIRY:
            for col in self.contract_cols:
                valid = df[df[col].notna()]
                if len(valid) >= 2 and df.loc[valid.index[-1], col] == df.loc[valid.index[-2], col]:
                    expired.setdefault(df.loc[valid.index[-1], 'Date'], []).append(col)

        slots = range(1, self.NUM_MONTHS + 1)
        rows = {f'M{s}': [] for s in slots}
        rows.update({f'M{s}_contract': [] for s in slots})
        rows['Date'] = []

        for idx in df.index:
            date = df.loc[idx, 'Date']
            excl = set(expired.get(date, []))
            available = [c for c in self.contract_cols
                         if pd.notna(df.loc[idx, c]) and c not in excl]
            rows['Date'].append(date)
            for s in slots:
                if s - 1 < len(available):
                    rows[f'M{s}'].append(df.loc[idx, available[s - 1]])
                    rows[f'M{s}_contract'].append(available[s - 1])
                else:
                    rows[f'M{s}'].append(np.nan)
                    rows[f'M{s}_contract'].append(None)

        out = pd.DataFrame(rows)
        for s in slots:
            out[f'M{s}'] = pd.to_numeric(out[f'M{s}'], errors='coerce')
        self.df_rolling = out

    def _build_contracts_pre_rolled(self):
        """Exchange-provided rolling slots (e.g. `BRN 1!-ICE`)
        map directly to M1..Mn. Drop rows where M1 is unavailable (ICE
        rolling conventions occasionally shift their start date per slot)."""
        df = self.df_raw
        slots = range(1, self.NUM_MONTHS + 1)
        out = pd.DataFrame({'Date': df['Date']})
        for s in slots:
            src = self.contract_cols[s - 1] if s - 1 < len(self.contract_cols) else None
            out[f'M{s}'] = df[src] if src else np.nan
            out[f'M{s}_contract'] = src
        for s in slots:
            out[f'M{s}'] = pd.to_numeric(out[f'M{s}'], errors='coerce')
        out = out.dropna(subset=['M1']).reset_index(drop=True)
        self.df_rolling = out

    def _add_roll_flags(self):
        df = self.df_rolling
        df['M1_contract_prev'] = df['M1_contract'].shift(1)
        if self.PRE_ROLLED:
            df['is_roll'] = False
        else:
            df['is_roll'] = df['M1_contract'] != df['M1_contract_prev']
        df['M1_change'] = df['M1'].diff()
        df['M1_pct_change'] = df['M1'].pct_change() * 100

    def _add_spreads(self):
        df = self.df_rolling
        pairs = [('M1', 'M2'), ('M1', 'M3'), ('M1', 'M6')]
        if self.NUM_MONTHS >= 12:
            pairs.append(('M1', 'M12'))
        for a, b in pairs:
            if a in df.columns and b in df.columns:
                df[f'{a}_{b}'] = df[a] - df[b]

    def _add_volatility(self):
        df = self.df_rolling
        df['M1_return'] = np.log(df['M1'] / df['M1'].shift(1))
        df[self.VOL_COL] = (df['M1_return'].rolling(self.VOL_WINDOW).std()
                            * np.sqrt(self.ANNUAL_DAYS))

    def _add_zscores(self):
        """Two modes:
        - 'rolling'      — legacy; 60d window μ, σ. Suffers from rolling-std floor
                           in calm windows (mechanical 7σ artefacts).
        - 'is_anchored'  — μ, σ estimated once on the in-sample window (≤ Z_IS_END)
                           and applied uniformly. Gives interpretable, stable Z-scores
                           and makes OOS anomalies directly comparable to the IS
                           distribution. This is the default for ZSCORE_MODE='is_anchored'.
        """
        df, w, mode = self.df_rolling, self.Z_WINDOW, self.Z_MODE
        if mode == 'is_anchored':
            is_mask = df['Date'] <= self.Z_IS_END
            for spread in ('M1_M3', 'M1_M6'):
                s_is = df.loc[is_mask, spread].dropna()
                mu, sig = s_is.mean(), s_is.std()
                df[f'Z_{spread}'] = (df[spread] - mu) / sig if sig > 0 else np.nan
                df.attrs[f'Z_{spread}_mu']  = float(mu)
                df.attrs[f'Z_{spread}_sig'] = float(sig)
        else:
            for spread in ('M1_M3', 'M1_M6'):
                mu, sig = df[spread].rolling(w).mean(), df[spread].rolling(w).std()
                df[f'Z_{spread}'] = (df[spread] - mu) / sig
        df.attrs['Z_MODE'] = mode

    def _add_regime(self):
        t = self.THRESHOLDS

        def classify(x):
            if pd.isna(x):            return 'Unknown'
            if x > t['CRISIS']:       return 'Crisis'
            if x > t['STRESS']:       return 'Stress'
            if x > t['TIGHT']:        return 'Tight'
            return 'Normal'

        self.df_rolling['Regime'] = self.df_rolling['M1_M6'].apply(classify)
