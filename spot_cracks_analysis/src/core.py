"""Core shared primitives — data loader and chart mixin. Single source of
truth for every analytical class in this project.

Portfolio-wide styling (palette, fonts, figure sizes) lives in
`../plot_config.yaml` and is merged in automatically at config-load time.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yaml

# ==== Path constants (coding_habits §4.3: path management in __init__) =======
SCA_ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_ROOT = SCA_ROOT.parent
PLOT_CONFIG = PORTFOLIO_ROOT / "plot_config.yaml"
MAJOR_DATES_PATH = PORTFOLIO_ROOT / "major_dates.yaml"
DEFAULT_CONFIG = SCA_ROOT / "config.yaml"
DATAS_ROOT = PORTFOLIO_ROOT / "data"
# Back-compat alias (used by earlier code paths)
PORTFOLIO_PLOT = PLOT_CONFIG

logger = logging.getLogger(__name__)


def load_config(path=None):
    """Load per-project config and merge the portfolio-wide PLOT block if
    `../../plot_config.yaml` exists — so palette, fonts, figure sizes stay
    consistent across every project in the portfolio."""
    with open(path or DEFAULT_CONFIG) as fh:
        cfg = yaml.safe_load(fh)
    if PORTFOLIO_PLOT.exists():
        with open(PORTFOLIO_PLOT) as fh:
            shared = yaml.safe_load(fh)
        # Project PLOT overrides the shared one (per-project escape hatch).
        merged = {**shared.get("PLOT", {}), **cfg.get("PLOT", {})}
        cfg["PLOT"] = merged
    return cfg


# ============================================================================
# DataLoader — every CSV/XLSX quirk handled once, downstream classes see clean
# frames with ISO-parsed Date columns sorted ascending.
# ============================================================================


class DataLoader:
    """Central data loader. Handles per-file quirks (date format, whitespace
    in column names, unit suffixes). Returns clean, date-sorted frames."""

    def __init__(self, CONFIG_PATH=None):
        cfg = load_config(CONFIG_PATH)
        self.CONFIG = cfg
        self.PROJECT_ROOT = Path(CONFIG_PATH or DEFAULT_CONFIG).resolve().parent
        self.DATA_ROOT = (self.PROJECT_ROOT / cfg["PATHS"]["DATA_ROOT"]).resolve()
        self.D = cfg["DATA"]

    def _path(self, key):
        return self.DATA_ROOT / self.D[key]

    # ---- spot / futures ----------------------------------------------------

    def spot_prices(self):
        df = pd.read_excel(self._path("SPOT_PRICES"))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def brent_futures(self):
        """ICE Brent M1-M12 daily settlement strip. Returns M1 in the default
        column for back-compat; downstream callers can request the full strip
        via `brent_futures_strip()` when they need contract-month pairing."""
        df = pd.read_excel(self._path("BRENT_FUTURES"))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        df["Brent_M1_bbl"] = df["BRN 1!-ICE"]
        return df[["Date", "Brent_M1_bbl"]]

    def brent_futures_strip(self):
        """Full Brent M1-M12 strip. Column naming: Brent_M{n}_bbl for n=1..12."""
        df = pd.read_excel(self._path("BRENT_FUTURES"))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        rename = {}
        for n in range(1, 13):
            src = f"BRN {n}!-ICE"
            if src in df.columns:
                rename[src] = f"Brent_M{n}_bbl"
        df = df.rename(columns=rename)
        keep = ["Date"] + [
            f"Brent_M{n}_bbl" for n in range(1, 13) if f"Brent_M{n}_bbl" in df.columns
        ]
        return df[keep]

    def brent_spot(self):
        """Platts-assessed Brent spot, distinct from M1 futures and from Dated
        Brent. Source: Spot_prices.xlsx column Brent_bbl. Empty pre-2021 in
        the current file; merge with coalesce when building the three-track
        view."""
        df = pd.read_excel(self._path("SPOT_PRICES"))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        if "Brent_bbl" not in df.columns:
            return pd.DataFrame(columns=["Date", "Brent_spot_bbl"])
        df = df[["Date", "Brent_bbl"]].rename(columns={"Brent_bbl": "Brent_spot_bbl"})
        return df.dropna(subset=["Brent_spot_bbl"]).reset_index(drop=True)

    def dated_brent(self):
        df = pd.read_excel(self._path("DATED_BRENT"))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.rename(columns={"Dated Brent (DTD)": "Dated_Brent_bbl"})
        return df.sort_values("Date").reset_index(drop=True)

    def three_brent_tracks(self):
        """Merged frame with Brent_M1_bbl (ICE futures front-month), Brent_spot_bbl
        (Platts spot assessment), Dated_Brent_bbl (Platts physical Dated). The three
        are distinct instruments and diverge by dollars in calm tapes, by tens of
        dollars under stress (April 2026 Dated-vs-M1 peaked at ~$35/bbl)."""
        m1 = self.brent_futures()
        sp = self.brent_spot()
        dtd = self.dated_brent()
        out = m1.merge(sp, on="Date", how="outer").merge(dtd, on="Date", how="outer")
        return out.sort_values("Date").reset_index(drop=True)

    # ---- stocks / util / storage ------------------------------------------

    def us_stocks(self):
        """EIA weekly stocks — crude (incl. SPR), SPR, gasoline, distillate, total products."""
        df = pd.read_csv(self._path("US_STOCKS"), parse_dates=["Date"], date_format="%d-%b-%y")
        # Back-compat alias for downstream code that used the old column name
        df = df.rename(columns={"Crude_Incl_SPR_Mbbl": "Crude_incl_SPR_Mbbl"})
        return df.sort_values("Date").reset_index(drop=True)

    def us_refinery_util(self):
        df = pd.read_csv(self._path("US_REFINERY"))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def eu_stocks(self):
        df = pd.read_csv(self._path("EU_STOCKS"))
        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")
        return df.sort_values("Date").reset_index(drop=True)

    def eu_stocks_by_country(self, WHICH="crude"):
        """Raw Eurostat per-country series. WHICH ∈ {'crude','products','feedstocks'}.

        File layout: metadata rows 0-8, date header on row 9 (TIME labels in
        alternating columns, YYYY-MM format), country header row 10, data
        rows 11+. Full country names in col 0; values in odd columns."""
        mapping = {
            "crude": "raw/Stocks/EU_Crude_Stocks_by_country.xlsx",
            "products": "raw/Stocks/EU_Oil_Products_Stocks_by_country.xlsx",
            "feedstocks": "raw/Stocks/EU_Refinery_Feedstocks_by_country.xlsx",
        }
        raw = pd.read_excel(self.DATA_ROOT / mapping[WHICH], sheet_name="Sheet 1", header=None)

        # Find the TIME header row
        time_row = None
        for i in range(min(20, raw.shape[0])):
            if str(raw.iloc[i, 0]).strip().upper() == "TIME":
                time_row = i
                break
        if time_row is None:
            return pd.DataFrame()

        # Parse date headers — every column at time_row that parses as YYYY-MM
        date_cols = {}  # col_idx -> Timestamp
        for c in range(1, raw.shape[1]):
            val = raw.iloc[time_row, c]
            dt = pd.to_datetime(str(val), format="%Y-%m", errors="coerce")
            if pd.notna(dt):
                date_cols[c] = dt

        # Country data starts 2 rows below TIME (row 10 = GEO (Labels), row 11 = first country)
        data_start = time_row + 2
        rows = []
        for i in range(data_start, raw.shape[0]):
            country = raw.iloc[i, 0]
            if pd.isna(country) or not isinstance(country, str):
                continue
            country = country.strip()
            if not country:
                continue
            # Skip aggregates
            if "European Union" in country or "Euro area" in country:
                continue
            for c, dt in date_cols.items():
                val = pd.to_numeric(raw.iloc[i, c], errors="coerce")
                if pd.notna(val):
                    rows.append({"Country": country, "Date": dt, "Value": val})

        out = pd.DataFrame(rows).sort_values(["Country", "Date"]).reset_index(drop=True)
        return out

    def eurusd(self):
        df = pd.read_csv(self._path("EURUSD"))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def floating_storage(self):
        df = pd.read_csv(self._path("FLOATING_STORAGE"))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    # ---- flows -------------------------------------------------------------

    def europe_diesel_import(self, GRANULARITY="monthly"):
        key = (
            "EUROPE_DIESEL_IMPORT_MONTHLY"
            if GRANULARITY == "monthly"
            else "EUROPE_DIESEL_IMPORT_5Y"
        )
        df = pd.read_csv(self._path(key))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def russia_diesel_export(self):
        df = pd.read_csv(self._path("RUSSIA_DIESEL_EXPORT_5Y"))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def diesel_global_export(self, GRANULARITY="monthly"):
        key = "DIESEL_GLOBAL_EXPORT_5Y"
        df = pd.read_csv(self._path(key))
        df["Date"] = pd.to_datetime(df["Date"])
        if GRANULARITY == "monthly":
            df = df.groupby(["Date", "Origin"], as_index=False)[
                ["Quantity_kt", "Quantity_kbbl"]
            ].sum()
        return df.sort_values("Date").reset_index(drop=True)

    # ---- refining (EIA weekly/monthly + Eurostat supply-transformation) ---

    def us_refinery_util_weekly(self):
        """EIA weekly refinery data 1982+. Returns Date + %util + kbd inputs."""
        df = pd.read_csv(self._path("US_REFINERY_WEEKLY"), parse_dates=["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def us_refinery_yields(self):
        """EIA monthly product-yield breakdown 1993+ (HGL series begins 2010).
        Yields are % of refinery input; negative Processing_Gain reflects
        hydrogen-sourced volume uplift."""
        df = pd.read_csv(self._path("US_REFINERY_YIELDS"), parse_dates=["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def eu_refinery_intake(self):
        """Eurostat per-country refinery crude throughput 2018+ (monthly, kt).
        Skips aggregate rows ('European Union' etc.) if present."""
        df = pd.read_csv(self._path("EU_REFINERY_INTAKE"), parse_dates=["Date"])
        df = df[~df["Country"].str.contains("European Union|Euro area", na=False, regex=True)]
        return df.sort_values(["Country", "Date"]).reset_index(drop=True)

    def eu_refinery_output_distillate(self):
        """Eurostat EU refinery output of gasoil/diesel (kt monthly)."""
        df = pd.read_csv(self._path("EU_REFINERY_OUTPUT_DISTIL"), parse_dates=["Date"])
        df = df[~df["Country"].str.contains("European Union|Euro area", na=False, regex=True)]
        return df.sort_values(["Country", "Date"]).reset_index(drop=True)

    def eu_consumption(self, WHICH="distillate"):
        """Eurostat 'gross inland deliveries' — apparent consumption by country
        (kt monthly, 2018+). WHICH ∈ {'distillate','jet','products'}.
        In energy-balance terminology, gross inland deliveries = production +
        imports − exports − stock builds. Closest Eurostat proxy for 'what
        the domestic market consumed' at product level."""
        key = {
            "distillate": "EU_CONSUMPTION_DISTIL",
            "jet": "EU_CONSUMPTION_JET",
            "products": "EU_CONSUMPTION_PRODUCTS",
        }[WHICH]
        df = pd.read_csv(self._path(key), parse_dates=["Date"])
        df = df[~df["Country"].str.contains("European Union|Euro area", na=False, regex=True)]
        return df.sort_values(["Country", "Date"]).reset_index(drop=True)

    # ---- OPEC ASB 2025 tables ---------------------------------------------

    def opec_t43_throughput(self):
        return pd.read_csv(self._path("OPEC_T43_THROUGHPUT"))

    def opec_t52_crude_exports(self):
        return pd.read_csv(self._path("OPEC_T52_CRUDE_EXPORTS"))

    def opec_t53_product_exports(self):
        return pd.read_csv(self._path("OPEC_T53_PRODUCT_EXPORTS"))

    def opec_freight(self, VESSEL="clean"):
        """OPEC ASB tanker-freight assessments (WS% annual, 2011-2024).
        VESSEL ∈ {'clean','dirty'}. Columns: route, year, unit, value, vessel."""
        key = "OPEC_T63_FREIGHT_CLEAN" if VESSEL == "clean" else "OPEC_T62_FREIGHT_DIRTY"
        return pd.read_csv(self._path(key))

    def opec_t74_futures(self):
        """OPEC ASB monthly futures settlements 1990+ (Brent/WTI/Oman x forward
        months). Columns: instrument, contract, date, price_usd_bbl."""
        df = pd.read_csv(self._path("OPEC_T74_FUTURES_MONTHLY"))
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values(["instrument", "contract", "date"]).reset_index(drop=True)

    def opec_t76_cracks(self):
        """OPEC ASB annual crack-spread assessments 1983+ for 3 regions
        (Rotterdam vs Brent, Singapore vs Dubai, US Gulf vs WTI). USD/bbl."""
        return pd.read_csv(self._path("OPEC_T76_CRACKS"))

    # ---- cross-project -----------------------------------------------------

    def cracks_clean(self):
        """Pre-computed crack series from the shared csv/ layer."""
        p = self.DATA_ROOT / "csv" / "crack_spreads_clean.csv"
        df = pd.read_csv(p, parse_dates=["Date"])
        return df.sort_values("Date").reset_index(drop=True)

    def major_dates(self, INCLUDE_OBSERVATIONS=False):
        """Portfolio-wide event timeline. Returns a list of (date, label)
        tuples for chart overlays. Defaults to causal `events` only — chart
        legibility. Pass INCLUDE_OBSERVATIONS=True to append derived extremes
        (Z-peaks, spread peaks, vol peaks) when a diagnostic chart needs them."""
        path = self.PROJECT_ROOT / self.CONFIG["PATHS"]["MAJOR_DATES"]
        if not path.exists():
            return []
        with open(path) as fh:
            y = yaml.safe_load(fh)
        # Back-compat: older files used a single `shocks` key
        items = list(y.get("events", [])) + list(y.get("shocks", []))
        if INCLUDE_OBSERVATIONS:
            items += list(y.get("observations", []))
        return [(pd.to_datetime(e["date"]), e["label"]) for e in items]


# ============================================================================
# Chartable — plot primitives (adaptive x-axis, faceted panels, event overlay,
# finalize-and-save). Every analytical class inherits from this mixin.
# ============================================================================


class Chartable:
    """Shared chart primitives + init-time styling bootstrap. Subclasses call
    `self._init_styling(cfg)` from their own `__init__` instead of manually
    pulling the same 20 lines of PLOT / FILES / OUTPUT_DIR setup."""

    def _init_styling(self, cfg, PROJECT_ROOT, SAVE_FIGURES=True):
        """Single entry point for every analytical class to wire config → self."""
        ana = cfg["ANALYSIS"]
        plot = cfg["PLOT"]
        self.Z_IS_END = pd.to_datetime(ana["ZSCORE_IS_END"])
        self.RECENT_MONTHS = ana.get("RECENT_WINDOW_MONTHS", 18)
        self.HIST_BINS = ana.get("HISTOGRAM_BINS", 50)
        self.ROLL_WINDOW = ana.get("ROLLING_CORR_WINDOW", 60)

        self.COLORS = plot["COLORS"]
        self.SIZES = {k: tuple(v) for k, v in plot["SIZES"].items()}
        self.LW = plot["LINEWIDTH"]
        self.A = plot["ALPHA"]
        self.SAVE_OPTS = plot["SAVE"]
        self.XAXIS = plot["XAXIS"]
        self.FILES = cfg.get("CHART_FILES", {})
        plt.rcParams.update(plot["RCPARAMS"])

        self.OUTPUT_DIR = PROJECT_ROOT / cfg["PATHS"]["FIGURES"] if SAVE_FIGURES else None

    def _format_xaxis(self, ax):
        t0, t1 = ax.get_xlim()
        span = t1 - t0
        if span > 365 * 3:
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        elif span > 365:
            ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(30)
            lbl.set_ha("right")

    def _recent(self, df, DATE_COL="Date"):
        cutoff = df[DATE_COL].max() - pd.DateOffset(months=self.RECENT_MONTHS)
        return df[df[DATE_COL] >= cutoff].copy()

    def _finalize(self, fig, file_key):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            fig.tight_layout()
        if self.OUTPUT_DIR and file_key in self.FILES:
            dest = self.OUTPUT_DIR / f"{self.FILES[file_key]}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(dest, **self.SAVE_OPTS)
        return fig

    def _add_event_markers(self, ax, events=None, y_top=None):
        """Staircase boxed annotations. `events` can be a list of (date, label)
        tuples (e.g. from DataLoader.major_dates()); if None, uses self.events
        if present."""
        if events is None:
            events = getattr(self, "events", [])
        if not events:
            return
        x0, x1 = ax.get_xlim()
        d0 = mdates.num2date(x0).date() if x0 > 0 else None
        d1 = mdates.num2date(x1).date() if x1 > 0 else None
        if y_top is None:
            _, y1 = ax.get_ylim()
            y_top = y1
        for j, (d, label) in enumerate(events):
            dt = pd.to_datetime(d)
            if d0 is not None and dt.date() < d0:
                continue
            if d1 is not None and dt.date() > d1:
                continue
            ax.axvline(dt, color="black", linestyle="--", linewidth=1, alpha=0.55)
            level = j % 3
            y_off = 12 + 16 * level
            ax.annotate(
                label,
                xy=(dt, y_top),
                xycoords="data",
                xytext=(0, y_off),
                textcoords="offset points",
                ha="center",
                fontsize=7,
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    facecolor="white",
                    edgecolor=self.COLORS.get("REF", "#888"),
                    alpha=0.9,
                ),
                arrowprops=dict(arrowstyle="-", color="black", lw=0.6),
            )

    @staticmethod
    def _zero_line(ax):
        ax.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)

    @staticmethod
    def _color_stack(ax, axis, color, label):
        ax.set_ylabel(label, color=color)
        ax.tick_params(axis=axis, labelcolor=color)
