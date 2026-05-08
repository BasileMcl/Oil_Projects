"""Supply / demand fundamentals — US & EU stocks, SPR, refinery utilization,
floating storage. Percentile-based regime labels on each series (low / normal
/ high). Correlation with Brent-ULSD crack as the fundamentals-to-margin link.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .core import DEFAULT_CONFIG, Chartable, DataLoader, load_config


class FundamentalsAnalysis(Chartable):
    """Load and analyse US / EU stocks, refinery utilization, floating storage.
    Expose percentile-based regime labels plus correlation with the Brent-ULSD
    crack (5y weekly alignment)."""

    def __init__(self, CONFIG_PATH=None, SAVE_FIGURES=True, LOADER=None):
        cfg = load_config(CONFIG_PATH)
        self.CONFIG = cfg
        self.ROOT = Path(CONFIG_PATH or DEFAULT_CONFIG).resolve().parent
        self._init_styling(cfg, self.ROOT, SAVE_FIGURES)

        self.loader = LOADER or DataLoader(CONFIG_PATH)

        self.us_stocks = self.eu_stocks = self.eu_by_country = None
        self.util = self.floating = self.cracks = None
        self.util_weekly = self.us_yields = None
        self.eu_intake = self.eu_distillate_out = None
        self.eu_consumption_distil = None
        self.events = []

    # Pipeline ---------------------------------------------------------------

    def load(self):
        self.us_stocks = self.loader.us_stocks()
        self.eu_stocks = self.loader.eu_stocks()
        self.util = self.loader.us_refinery_util()
        self.floating = self.loader.floating_storage()
        self.cracks = self.loader.cracks_clean()
        self.events = self.loader.major_dates()
        # Per-country Eurostat — loaded lazily (takes a second)
        try:
            self.eu_by_country = self.loader.eu_stocks_by_country(WHICH="products")
        except Exception as e:
            print(f"[Fundamentals] EU per-country load failed: {e}")
            self.eu_by_country = None
        # Refining layer — long-history EIA + EU supply-transformation
        self.util_weekly = self.loader.us_refinery_util_weekly()
        self.us_yields = self.loader.us_refinery_yields()
        self.eu_intake = self.loader.eu_refinery_intake()
        self.eu_distillate_out = self.loader.eu_refinery_output_distillate()
        self.eu_consumption_distil = self.loader.eu_consumption(WHICH="distillate")
        try:
            self.eu_consumption_jet = self.loader.eu_consumption(WHICH="jet")
        except Exception:
            self.eu_consumption_jet = None
        print(
            f"[Fundamentals] US stocks {len(self.us_stocks)}w | "
            f"EU stocks {len(self.eu_stocks)}m | "
            f"EU/country {len(self.eu_by_country) if self.eu_by_country is not None else 0} rows | "
            f"Refinery util monthly {len(self.util)}m / weekly {len(self.util_weekly)}w | "
            f"US yields {len(self.us_yields)}m | "
            f"EU intake {len(self.eu_intake)} rows ({self.eu_intake['Country'].nunique()} countries) | "
            f"EU distillate output {len(self.eu_distillate_out)} rows | "
            f"Floating {len(self.floating)}m | "
            f"Cracks {len(self.cracks)}d"
        )
        return self

    # Summaries --------------------------------------------------------------

    def summary_stats(self):
        """Latest values + 5y percentile per series."""
        last = self.us_stocks.iloc[-1]
        rows = {}
        five_y_cut = self.us_stocks["Date"].max() - pd.DateOffset(years=5)
        for c in [
            "Crude_incl_SPR_Mbbl",
            "SPR_Crude_Stocks_Mbbl",
            "Gasoline_Stocks_Mbbl",
            "Distillate_Stocks_Mbbl",
            "Total_Products_Mbbl",
        ]:
            recent = self.us_stocks[self.us_stocks["Date"] >= five_y_cut][c]
            pct = (recent < last[c]).mean() * 100 if len(recent) else np.nan
            rows[c] = {
                "latest (Mbbl)": f"{last[c]:,.1f}",
                "5y pct rank": f"{pct:.0f}th",
                "5y mean": f"{recent.mean():,.1f}",
                "5y min..max": f"{recent.min():,.0f}..{recent.max():,.0f}",
            }
        out = pd.DataFrame(rows).T
        print("US stocks (latest vs 5y percentile):")
        print(out.to_string())

        last_util = self.util.iloc[-1]
        util5 = self.util[self.util["Date"] >= self.util["Date"].max() - pd.DateOffset(years=5)]
        print(
            f"\nUS refinery utilisation: latest = {last_util['Refinery_Utilization_Pct']:.1f}%, "
            f"5y range {util5['Refinery_Utilization_Pct'].min():.1f}%..{util5['Refinery_Utilization_Pct'].max():.1f}%"
        )

        fs5 = self.floating[
            self.floating["Date"] >= self.floating["Date"].max() - pd.DateOffset(years=5)
        ]
        print(
            f"Floating storage: latest = {self.floating.iloc[-1]['Floating_Storage_kt']:,.0f} kt, "
            f"5y mean {fs5['Floating_Storage_kt'].mean():,.0f} kt"
        )
        return out

    # Charts -----------------------------------------------------------------

    def chart_us_stocks(self):
        """3-panel US stocks — crude, gasoline, distillate."""
        df = self.us_stocks
        five_y = df["Date"].max() - pd.DateOffset(years=5)
        df5 = df[df["Date"] >= five_y]
        fig, axes = plt.subplots(3, 1, figsize=(self.SIZES["STANDARD"][0], 10), sharex=True)
        panels = [
            ("Crude_incl_SPR_Mbbl", "US crude incl. SPR"),
            ("Gasoline_Stocks_Mbbl", "US gasoline stocks"),
            ("Distillate_Stocks_Mbbl", "US distillate stocks"),
        ]
        for ax, (col, title) in zip(axes, panels, strict=False):
            ax.plot(df5["Date"], df5[col], color=self.COLORS["STOCKS"], linewidth=self.LW)
            # 5y percentile band
            p20 = df5[col].quantile(0.20)
            p80 = df5[col].quantile(0.80)
            ax.axhline(
                p20,
                color=self.COLORS["REF"],
                linestyle="--",
                linewidth=0.7,
                alpha=0.6,
                label=f"20th pct = {p20:,.0f}",
            )
            ax.axhline(
                p80,
                color=self.COLORS["REF"],
                linestyle="--",
                linewidth=0.7,
                alpha=0.6,
                label=f"80th pct = {p80:,.0f}",
            )
            ax.set_ylabel(f"{title}\n(Mbbl)")
            ax.legend(loc="upper left", fontsize=8)
            ax.set_title(title, loc="left", fontsize=10, fontweight="normal")
        self._format_xaxis(axes[-1])
        axes[-1].set_xlabel("Date")
        fig.suptitle(
            "US petroleum stocks — last 5 years (EIA weekly)",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "STOCKS_US")

    def chart_spr_drawdown(self):
        """Strategic Petroleum Reserve drawdown since 2022."""
        df = self.us_stocks
        spr = df[["Date", "SPR_Crude_Stocks_Mbbl"]].copy()
        since_2021 = spr[spr["Date"] >= "2021-01-01"]
        peak = since_2021["SPR_Crude_Stocks_Mbbl"].max()
        peak_date = since_2021.loc[since_2021["SPR_Crude_Stocks_Mbbl"].idxmax(), "Date"]
        trough = since_2021["SPR_Crude_Stocks_Mbbl"].min()
        trough_date = since_2021.loc[since_2021["SPR_Crude_Stocks_Mbbl"].idxmin(), "Date"]
        latest = since_2021.iloc[-1]

        fig, (ax_top, ax_bot) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        ax_top.plot(
            since_2021["Date"],
            since_2021["SPR_Crude_Stocks_Mbbl"],
            color=self.COLORS["SPR"],
            linewidth=self.LW + 0.3,
        )
        ax_top.axhline(
            peak,
            color=self.COLORS["REF"],
            linestyle="--",
            linewidth=0.8,
            label=f"Peak {peak:.0f} Mbbl ({peak_date.date()})",
        )
        ax_top.axhline(
            trough,
            color=self.COLORS["REF"],
            linestyle="--",
            linewidth=0.8,
            label=f"Trough {trough:.0f} Mbbl ({trough_date.date()})",
        )
        ax_top.set(ylabel="SPR crude (Mbbl)")
        ax_top.set_title(
            "Strategic Petroleum Reserve — level", loc="left", fontsize=10, fontweight="normal"
        )
        ax_top.legend(loc="upper right", fontsize=9)
        self._format_xaxis(ax_top)
        self._add_event_markers(ax_top)

        since_2021 = since_2021.copy()
        since_2021["weekly_change"] = since_2021["SPR_Crude_Stocks_Mbbl"].diff()
        ax_bot.bar(
            since_2021["Date"],
            since_2021["weekly_change"],
            color=np.where(
                since_2021["weekly_change"] < 0, self.COLORS["VOL"], self.COLORS["MARGIN"]
            ),
            width=4.5,
        )
        self._zero_line(ax_bot)
        ax_bot.set(xlabel="Date", ylabel="Weekly Δ (Mbbl)")
        ax_bot.set_title(
            "Weekly change — draws (red) vs builds (green)",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        self._format_xaxis(ax_bot)

        drawdown_pct = 100 * (latest["SPR_Crude_Stocks_Mbbl"] - peak) / peak
        print(
            f"SPR peak-to-latest: {latest['SPR_Crude_Stocks_Mbbl'] - peak:+.1f} Mbbl "
            f"({drawdown_pct:+.1f}%)"
        )
        print(f"Latest: {latest['SPR_Crude_Stocks_Mbbl']:.1f} Mbbl on {latest['Date'].date()}")

        fig.suptitle(
            "SPR drawdown — 2021 → latest",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "STOCKS_SPR")

    def chart_eu_vs_us_stocks(self):
        """Normalized (z-score) comparison of EU and US products stocks."""
        us = self.us_stocks[["Date", "Distillate_Stocks_Mbbl", "Gasoline_Stocks_Mbbl"]].copy()
        eu = self.eu_stocks[["Date", "Euro_All_Oil_Products_Stocks_kt"]].copy()
        # Weekly → monthly resample for US to align with EU
        us = us.set_index("Date").resample("MS").mean().reset_index()
        since = pd.to_datetime("2019-01-01")
        us = us[us["Date"] >= since]
        eu = eu[eu["Date"] >= since]

        def z(s):
            return (s - s.mean()) / s.std()

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.plot(
            us["Date"],
            z(us["Distillate_Stocks_Mbbl"]),
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            label="US distillate (z)",
        )
        ax.plot(
            us["Date"],
            z(us["Gasoline_Stocks_Mbbl"]),
            color=self.COLORS["MARGIN"],
            linewidth=self.LW,
            label="US gasoline (z)",
        )
        ax.plot(
            eu["Date"],
            z(eu["Euro_All_Oil_Products_Stocks_kt"]),
            color=self.COLORS["PRICE"],
            linewidth=self.LW,
            label="EU all products (z)",
        )
        self._zero_line(ax)
        ax.set(xlabel="Date", ylabel="Z-score vs own series mean")
        ax.set_title("EU vs US petroleum stocks — normalised", loc="left")
        ax.legend(loc="upper left")
        self._format_xaxis(ax)
        return self._finalize(fig, "STOCKS_EU_VS_US")

    def chart_refinery_util(self):
        """US refinery utilisation with percentile bands + regime labels."""
        df = self.util.copy()
        since = pd.to_datetime("2019-01-01")
        df = df[df["Date"] >= since]
        p20, p50, p80 = df["Refinery_Utilization_Pct"].quantile([0.20, 0.50, 0.80])

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.plot(
            df["Date"],
            df["Refinery_Utilization_Pct"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW + 0.3,
            marker="o",
            markersize=3,
        )
        ax.axhline(
            p80,
            color=self.COLORS["VOL"],
            linestyle="--",
            linewidth=0.8,
            label=f"80th pct = {p80:.1f}%  (tight)",
        )
        ax.axhline(
            p50,
            color=self.COLORS["REF"],
            linestyle="--",
            linewidth=0.8,
            label=f"Median = {p50:.1f}%",
        )
        ax.axhline(
            p20,
            color=self.COLORS["MARGIN"],
            linestyle="--",
            linewidth=0.8,
            label=f"20th pct = {p20:.1f}%  (slack)",
        )
        ax.set(xlabel="Date", ylabel="Refinery utilization (%)")
        ax.set_title("US refinery utilisation — 2019 onwards (EIA monthly)", loc="left")
        ax.legend(loc="lower left")
        self._format_xaxis(ax)
        latest = df.iloc[-1]
        pct_rank = (
            df["Refinery_Utilization_Pct"] < latest["Refinery_Utilization_Pct"]
        ).mean() * 100
        print(
            f"Latest utilisation: {latest['Refinery_Utilization_Pct']:.1f}% "
            f"on {latest['Date'].date()}   ({pct_rank:.0f}th percentile of last 5y)"
        )
        return self._finalize(fig, "REFINERY_UTIL")

    def chart_floating_storage(self):
        df = self.floating
        since = pd.to_datetime("2019-01-01")
        df = df[df["Date"] >= since]

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.plot(
            df["Date"],
            df["Floating_Storage_kt"],
            color=self.COLORS["FLOW"],
            linewidth=self.LW + 0.3,
            marker="o",
            markersize=3,
        )
        mean = df["Floating_Storage_kt"].mean()
        ax.axhline(
            mean,
            color=self.COLORS["REF"],
            linestyle="--",
            linewidth=0.8,
            label=f"Mean = {mean:,.0f} kt",
        )
        ax.set(xlabel="Date", ylabel="Floating storage (kt)")
        ax.set_title("Diesel / gasoil floating storage — monthly (Vortexa/Kpler)", loc="left")
        ax.legend(loc="upper left")
        self._format_xaxis(ax)
        return self._finalize(fig, "FLOATING_STORAGE")

    def chart_eu_stocks_by_country(self, TOP_N=8):
        """Per-country EU petroleum-products stocks — stacked monthly area.
        Loaded from Eurostat per-country xlsx (previously unused in legacy)."""
        if self.eu_by_country is None or len(self.eu_by_country) == 0:
            print("EU per-country data unavailable — see load() diagnostic.")
            return None
        df = self.eu_by_country.copy()
        since = pd.to_datetime("2019-01-01")
        df = df[df["Date"] >= since]
        # Pick top N contributors by mean stock level
        top = df.groupby("Country")["Value"].mean().sort_values(ascending=False).head(TOP_N).index
        df_top = df[df["Country"].isin(top)]
        pivot = df_top.pivot_table(
            index="Date", columns="Country", values="Value", aggfunc="sum"
        ).fillna(0)
        # Use ax.stackplot directly — pandas .plot.area passes numeric indices
        # which then confuse the matplotlib date formatter (renders year ~1971).
        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        x = pivot.index
        ax.stackplot(
            x,
            *[pivot[c].values for c in pivot.columns],
            labels=list(pivot.columns),
            colors=plt.cm.tab10.colors[: len(pivot.columns)],
            alpha=0.85,
            linewidth=0,
        )
        ax.set(xlabel="Date", ylabel="EU oil-products stocks (kt)")
        ax.set_title("EU petroleum-products stocks by country — Eurostat monthly", loc="left")
        ax.legend(loc="upper left", ncol=2, fontsize=8)
        self._format_xaxis(ax)
        latest = pivot.iloc[-1].sort_values(ascending=False)
        print(f"Top 3 EU stock holders (latest {pivot.index[-1].date()}):")
        for c, v in latest.head(3).items():
            print(f"   {c:16s}  {v:>10,.0f} kt")
        key = "STOCKS_EU_BY_COUNTRY" if "STOCKS_EU_BY_COUNTRY" in self.FILES else None
        return self._finalize(fig, key) if key else fig

    def chart_stocks_crack_correlation(self):
        """Distillate stocks ↔ Brent-ULSD crack — weekly-aligned 5y scatter +
        time-series overlay."""
        us = self.us_stocks[["Date", "Distillate_Stocks_Mbbl"]].copy()
        crack = self.cracks[["Date", "Brent_ULSD_NWE_Crack"]].copy()
        # Align daily crack to weekly US stocks via merge_asof
        merged = pd.merge_asof(
            us.sort_values("Date"),
            crack.sort_values("Date"),
            on="Date",
            direction="nearest",
            tolerance=pd.Timedelta("7 days"),
        ).dropna()
        five_y = merged["Date"].max() - pd.DateOffset(years=5)
        m5 = merged[merged["Date"] >= five_y]

        fig, (ax_ts, ax_sc) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 2, self.SIZES["SQUARE"][1]),
            gridspec_kw={"width_ratios": [2, 1], "wspace": 0.3},
        )

        # Time series
        ax_ts.plot(
            m5["Date"],
            m5["Distillate_Stocks_Mbbl"],
            color=self.COLORS["STOCKS"],
            linewidth=self.LW,
            label="US distillate stocks",
        )
        self._color_stack(ax_ts, "y", self.COLORS["STOCKS"], "Distillate stocks (Mbbl)")
        ax2 = ax_ts.twinx()
        ax2.plot(
            m5["Date"],
            m5["Brent_ULSD_NWE_Crack"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            alpha=0.85,
            label="Brent-ULSD NWE crack",
        )
        self._color_stack(ax2, "y", self.COLORS["CRACK"], "Crack (USD/bbl)")
        self._format_xaxis(ax_ts)
        ax_ts.set_title("Distillate stocks vs diesel crack (5y weekly)", loc="left", fontsize=10)

        # Scatter
        ax_sc.scatter(
            m5["Distillate_Stocks_Mbbl"],
            m5["Brent_ULSD_NWE_Crack"],
            s=14,
            alpha=self.A["SCATTER"],
            color=self.COLORS["SCATTER"],
            edgecolor="none",
        )
        if len(m5) > 2:
            slope, intercept = np.polyfit(
                m5["Distillate_Stocks_Mbbl"], m5["Brent_ULSD_NWE_Crack"], 1
            )
            xs = np.array([m5["Distillate_Stocks_Mbbl"].min(), m5["Distillate_Stocks_Mbbl"].max()])
            ax_sc.plot(xs, slope * xs + intercept, color=self.COLORS["TREND"], linewidth=self.LW)
            r = m5[["Distillate_Stocks_Mbbl", "Brent_ULSD_NWE_Crack"]].corr().iloc[0, 1]
            ax_sc.set_title(f"r = {r:+.3f}", loc="left", fontsize=10)
            print(f"Corr distillate stocks vs Brent-ULSD crack: {r:+.3f}  (n={len(m5)})")
        ax_sc.set(xlabel="Distillate stocks (Mbbl)", ylabel="Crack (USD/bbl)")
        ax_sc.grid(True, alpha=0.3)

        fig.suptitle(
            "Fundamentals ↔ margin link", x=0.01, ha="left", fontsize=13, fontweight="bold", y=1.02
        )
        return self._finalize(fig, "STOCKS_CRACK_CORR")

    # Refining layer ---------------------------------------------------------

    def chart_us_util_long(self):
        """US refinery utilisation — full EIA weekly history 1982+ with recent
        5-year zoom + 5y-range band. Shows that the current-regime level lives
        high on the 43-year distribution, not just a 5y one."""
        df = self.util_weekly[["Date", "Refinery_Utilization_Pct"]].dropna().copy()
        five_y = df["Date"].max() - pd.DateOffset(years=5)
        df5 = df[df["Date"] >= five_y]

        fig, (ax_top, ax_bot) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        ax_top.plot(
            df["Date"],
            df["Refinery_Utilization_Pct"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW - 0.2,
            alpha=0.85,
        )
        full_p80 = df["Refinery_Utilization_Pct"].quantile(0.80)
        full_p20 = df["Refinery_Utilization_Pct"].quantile(0.20)
        ax_top.axhline(
            full_p80,
            color=self.COLORS["VOL"],
            linestyle="--",
            linewidth=0.8,
            label=f"Full-history 80th = {full_p80:.1f}%",
        )
        ax_top.axhline(
            full_p20,
            color=self.COLORS["MARGIN"],
            linestyle="--",
            linewidth=0.8,
            label=f"Full-history 20th = {full_p20:.1f}%",
        )
        ax_top.set(ylabel="Utilisation (%)")
        ax_top.set_title(
            "US refinery utilisation — full EIA weekly history (1982 → latest)",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_top.legend(loc="lower left", fontsize=9)
        self._format_xaxis(ax_top)

        ax_bot.plot(
            df5["Date"],
            df5["Refinery_Utilization_Pct"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW + 0.2,
            marker="o",
            markersize=2,
        )
        p20, p80 = df5["Refinery_Utilization_Pct"].quantile([0.20, 0.80])
        ax_bot.fill_between(
            df5["Date"],
            p20,
            p80,
            color=self.COLORS["REF"],
            alpha=0.15,
            label=f"5y 20-80 pct ({p20:.1f}..{p80:.1f}%)",
        )
        ax_bot.set(xlabel="Date", ylabel="Utilisation (%)")
        ax_bot.set_title("Last 5 years — zoom", loc="left", fontsize=10, fontweight="normal")
        ax_bot.legend(loc="lower left", fontsize=9)
        self._format_xaxis(ax_bot)

        latest = df.iloc[-1]
        full_rank = (
            df["Refinery_Utilization_Pct"] < latest["Refinery_Utilization_Pct"]
        ).mean() * 100
        recent_rank = (
            df5["Refinery_Utilization_Pct"] < latest["Refinery_Utilization_Pct"]
        ).mean() * 100
        print(f"Latest: {latest['Refinery_Utilization_Pct']:.1f}% on {latest['Date'].date()}")
        print(
            f"Rank vs full history (43y): {full_rank:.0f}th pct  |  vs last 5y: {recent_rank:.0f}th pct"
        )

        fig.suptitle(
            "US refinery utilisation — long-history context",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "US_UTIL_LONG")

    def chart_us_yields(self):
        """EIA monthly refinery yields — gasoline / distillate / jet stack +
        distillate-vs-gasoline yield spread (the 'turn' toward diesel cuts)."""
        df = self.us_yields.copy()
        since = pd.to_datetime("2010-01-01")
        df = df[df["Date"] >= since]
        # Only the 4 cuts that matter for the NWE crack story.
        # Gasoline / Distillate / Jet are the refining-margin legs we trade.
        # LPG (Eurostat-speak "HGL" = hydrocarbon gas liquids) is the light-ends
        # by-product that competes with naphtha for petrochemical feedstock.
        # Residual Fuel, Pet coke, Asphalt and minor cuts are bottom-of-barrel
        # products whose margin behaviour doesn't shift the NWE diesel crack —
        # dropped to keep the chart readable.
        main_cols = ["Yield_Gasoline_pct", "Yield_Distillate_pct", "Yield_Jet_pct", "Yield_HGL_pct"]
        labels = ["Gasoline", "Distillate (diesel+gasoil)", "Jet", "LPG / NGLs"]
        colors = [
            self.COLORS["MARGIN"],
            self.COLORS["CRACK"],
            self.COLORS["PRICE"],
            self.COLORS["FX"],
        ]

        fig, (ax_top, ax_bot) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        for col, lbl, clr in zip(main_cols, labels, colors, strict=False):
            ax_top.plot(df["Date"], df[col], color=clr, linewidth=self.LW, label=lbl, alpha=0.9)
        ax_top.set(ylabel="Yield (% of refinery input)")
        ax_top.set_title(
            "EIA US refinery yields — 2010 → latest", loc="left", fontsize=10, fontweight="normal"
        )
        ax_top.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8)
        self._format_xaxis(ax_top)

        # Distillate minus gasoline — the "distillate tilt" indicator
        df["distillate_tilt"] = df["Yield_Distillate_pct"] - df["Yield_Gasoline_pct"]
        ax_bot.plot(
            df["Date"], df["distillate_tilt"], color=self.COLORS["CRACK"], linewidth=self.LW + 0.2
        )
        self._zero_line(ax_bot)
        mean_tilt = df["distillate_tilt"].mean()
        ax_bot.axhline(
            mean_tilt,
            color=self.COLORS["REF"],
            linestyle=":",
            linewidth=0.8,
            label=f"Mean = {mean_tilt:+.1f} pp",
        )
        ax_bot.set(xlabel="Date", ylabel="Distillate − gasoline (pp)")
        ax_bot.set_title(
            "Distillate tilt — negative = gasoline-heavy run, positive = diesel-heavy run",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_bot.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax_bot)

        latest = df.iloc[-1]
        print(
            f"Latest yields ({latest['Date'].date()}): "
            f"gasoline {latest['Yield_Gasoline_pct']:.1f}% | "
            f"distillate {latest['Yield_Distillate_pct']:.1f}% | "
            f"jet {latest['Yield_Jet_pct']:.1f}%"
        )
        print(
            f"Distillate tilt: {latest['distillate_tilt']:+.1f} pp "
            f"(mean {mean_tilt:+.1f}, σ {df['distillate_tilt'].std():.2f})"
        )

        fig.suptitle(
            "US refinery yield mix", x=0.01, ha="left", fontsize=13, fontweight="bold", y=0.995
        )
        return self._finalize(fig, "US_YIELDS")

    def chart_eu_refinery_intake(self, TOP_N=8, MIN_COUNTRIES_REPORTING=10):
        """EU monthly refinery crude throughput by country — stacked area +
        total-intake line with 12-month MA. 2018+ (Eurostat observed intake).
        Trailing months with sparse reporting (<MIN_COUNTRIES_REPORTING) are
        dropped — Eurostat has a 2-3 month publication lag, so the final month
        often shows only 1-2 early reporters and isn't comparable."""
        df = self.eu_intake.copy()
        # Drop trailing months with too few reporters
        reporting = df[df["Value_kt"] > 0].groupby("Date")["Country"].nunique()
        valid_dates = reporting[reporting >= MIN_COUNTRIES_REPORTING].index
        df = df[df["Date"].isin(valid_dates)]
        top = (
            df.groupby("Country")["Value_kt"].mean().sort_values(ascending=False).head(TOP_N).index
        )
        df_top = df[df["Country"].isin(top)]
        pivot = df_top.pivot_table(
            index="Date", columns="Country", values="Value_kt", aggfunc="sum"
        ).fillna(0)
        total = df.groupby("Date")["Value_kt"].sum()

        fig, (ax_stack, ax_total) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [3, 2], "hspace": 0.3},
        )

        ax_stack.stackplot(
            pivot.index,
            *[pivot[c].values for c in pivot.columns],
            labels=list(pivot.columns),
            colors=plt.cm.tab10.colors[: len(pivot.columns)],
            alpha=0.85,
            linewidth=0,
        )
        ax_stack.set(ylabel=f"kt / month (top-{TOP_N} countries)")
        ax_stack.set_title(
            "EU refinery crude intake — top contributors (Eurostat monthly observed)",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_stack.legend(loc="upper left", ncol=2, fontsize=8)
        self._format_xaxis(ax_stack)

        ax_total.plot(
            total.index,
            total.values,
            color=self.COLORS["PRICE"],
            linewidth=self.LW,
            label="EU total (all reporting countries)",
        )
        ax_total.plot(
            total.index,
            total.rolling(12).mean(),
            color=self.COLORS["CRACK"],
            linewidth=self.LW + 0.2,
            label="12-month MA",
        )
        ax_total.set(xlabel="Date", ylabel="kt / month")
        ax_total.set_title(
            "EU total refinery intake — level + trend", loc="left", fontsize=10, fontweight="normal"
        )
        ax_total.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax_total)

        latest = total.iloc[-1]
        mean = total.mean()
        pct_rank = (total < latest).mean() * 100
        top3 = pivot.iloc[-1].sort_values(ascending=False).head(3)
        print(
            f"EU total intake latest ({total.index[-1].date()}): {latest:,.0f} kt/month "
            f"(mean {mean:,.0f}, pct rank {pct_rank:.0f})"
        )
        print("Top 3 contributors this month:")
        for c, v in top3.items():
            print(f"   {c:20s} {v:>8,.0f} kt  ({100 * v / latest:.0f}%)")

        fig.suptitle(
            "EU refinery runs — crude intake (observed)",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "EU_REFINERY_INTAKE")

    def chart_eu_distillate_vs_crack(self):
        """EU gasoil/diesel refinery output vs Brent-ULSD NWE crack — does EU
        output respond to margin signal? Weekly crack resampled to monthly."""
        # Aggregate EU-wide distillate output monthly
        out = (
            self.eu_distillate_out.groupby("Date", as_index=False)["Value_kt"]
            .sum()
            .rename(columns={"Value_kt": "EU_distillate_out_kt"})
        )
        crack = self.cracks[["Date", "Brent_ULSD_NWE_Crack"]].copy()
        crack_m = crack.set_index("Date").resample("MS").mean().reset_index()
        merged = out.merge(crack_m, on="Date", how="inner").dropna()

        fig, (ax_ts, ax_sc) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 2, self.SIZES["SQUARE"][1]),
            gridspec_kw={"width_ratios": [2, 1], "wspace": 0.3},
        )

        ax_ts.plot(
            merged["Date"],
            merged["EU_distillate_out_kt"],
            color=self.COLORS["MARGIN"],
            linewidth=self.LW,
            label="EU distillate output (kt/m)",
        )
        self._color_stack(ax_ts, "y", self.COLORS["MARGIN"], "EU distillate output (kt/m)")
        ax2 = ax_ts.twinx()
        ax2.plot(
            merged["Date"],
            merged["Brent_ULSD_NWE_Crack"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            alpha=0.85,
            label="Brent-ULSD NWE crack",
        )
        self._color_stack(ax2, "y", self.COLORS["CRACK"], "Crack (USD/bbl)")
        ax_ts.set_title("EU distillate output vs diesel crack — monthly", loc="left", fontsize=10)
        self._format_xaxis(ax_ts)

        ax_sc.scatter(
            merged["Brent_ULSD_NWE_Crack"],
            merged["EU_distillate_out_kt"],
            s=18,
            alpha=self.A["SCATTER"],
            color=self.COLORS["SCATTER"],
            edgecolor="none",
        )
        if len(merged) > 2:
            r = merged[["EU_distillate_out_kt", "Brent_ULSD_NWE_Crack"]].corr().iloc[0, 1]
            slope, intercept = np.polyfit(
                merged["Brent_ULSD_NWE_Crack"], merged["EU_distillate_out_kt"], 1
            )
            xs = np.array(
                [merged["Brent_ULSD_NWE_Crack"].min(), merged["Brent_ULSD_NWE_Crack"].max()]
            )
            ax_sc.plot(xs, slope * xs + intercept, color=self.COLORS["TREND"], linewidth=self.LW)
            ax_sc.set_title(f"r = {r:+.3f}  (n={len(merged)})", loc="left", fontsize=10)
            print(f"Corr EU distillate output vs Brent-ULSD crack: {r:+.3f}  (n={len(merged)})")
        ax_sc.set(xlabel="Crack (USD/bbl)", ylabel="EU distillate output (kt/m)")
        ax_sc.grid(True, alpha=0.3)

        fig.suptitle(
            "EU refineries — margin signal → output response",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "EU_DISTIL_VS_CRACK")

    def chart_eu_consumption(self, MIN_COUNTRIES_REPORTING=15):
        """EU gasoil/diesel consumption — Eurostat 'gross inland deliveries'
        aggregated vs EU refinery output. The gap between consumption and
        output ≈ net-import requirement (consumption > output = deficit filled
        by imports; the opposite = surplus exported)."""
        cons_raw = self.eu_consumption_distil.copy()
        out_raw = self.eu_distillate_out.copy()
        # Filter trailing sparse months (Eurostat lag)
        rep = cons_raw[cons_raw["Value_kt"] > 0].groupby("Date")["Country"].nunique()
        valid = rep[rep >= MIN_COUNTRIES_REPORTING].index
        cons = cons_raw[cons_raw["Date"].isin(valid)]
        out = out_raw[out_raw["Date"].isin(valid)]
        cons_tot = cons.groupby("Date", as_index=False)["Value_kt"].sum()
        out_tot = out.groupby("Date", as_index=False)["Value_kt"].sum()
        merged = cons_tot.merge(
            out_tot, on="Date", how="inner", suffixes=("_consumption", "_output")
        )
        merged["gap"] = merged["Value_kt_consumption"] - merged["Value_kt_output"]

        fig, (ax_top, ax_bot) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        ax_top.plot(
            merged["Date"],
            merged["Value_kt_consumption"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW + 0.2,
            label="EU consumption (gross inland deliveries)",
        )
        ax_top.plot(
            merged["Date"],
            merged["Value_kt_output"],
            color=self.COLORS["MARGIN"],
            linewidth=self.LW + 0.2,
            label="EU refinery output",
        )
        ax_top.set(ylabel="kt / month")
        ax_top.set_title(
            "EU gasoil/diesel — consumption vs refinery output",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_top.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax_top)

        colors_gap = np.where(merged["gap"] > 0, self.COLORS["VOL"], self.COLORS["MARGIN"])
        ax_bot.bar(merged["Date"], merged["gap"], color=colors_gap, width=25, alpha=0.85)
        self._zero_line(ax_bot)
        mean_gap = merged["gap"].mean()
        ax_bot.axhline(
            mean_gap,
            color=self.COLORS["REF"],
            linestyle=":",
            linewidth=0.8,
            label=f"Mean gap = {mean_gap:+,.0f} kt/m",
        )
        ax_bot.set(xlabel="Date", ylabel="Consumption − output (kt/m)")
        ax_bot.set_title(
            "Net import requirement — positive = deficit filled by imports",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_bot.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax_bot)

        latest = merged.iloc[-1]
        print(
            f"EU diesel balance latest ({latest['Date'].date()}): "
            f"consumption {latest['Value_kt_consumption']:,.0f} kt vs "
            f"output {latest['Value_kt_output']:,.0f} kt → "
            f"gap {latest['gap']:+,.0f} kt ({latest['gap'] / latest['Value_kt_consumption'] * 100:+.1f}% of consumption)"
        )
        print(
            f"Mean monthly gap over sample: {mean_gap:+,.0f} kt ({mean_gap * 12 / 1000:+.1f} Mt/year)"
        )
        print(
            f"Interpretation: EU structurally needs to import "
            f"~{abs(mean_gap * 12 / 1000):.0f} Mt/year of diesel to cover domestic consumption."
        )

        fig.suptitle(
            "EU diesel — supply-demand balance",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "EU_CONSUMPTION")

    def chart_eu_jet_consumption(self, MIN_COUNTRIES_REPORTING=10):
        """EU jet/kerosene apparent consumption (Eurostat gross inland
        deliveries). Jet is the smaller of the EU product deficits but the
        most demand-elastic: it collapsed ~70% in 2020 COVID and has the
        largest positive asymmetry of any product in the Hormuz regime."""
        if self.eu_consumption_jet is None:
            print("[chart_eu_jet_consumption] No jet data available — skipping.")
            return None
        cons_raw = self.eu_consumption_jet.copy()
        rep = cons_raw[cons_raw["Value_kt"] > 0].groupby("Date")["Country"].nunique()
        valid = rep[rep >= MIN_COUNTRIES_REPORTING].index
        cons = cons_raw[cons_raw["Date"].isin(valid)]
        cons_tot = cons.groupby("Date", as_index=False)["Value_kt"].sum()

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.plot(
            cons_tot["Date"],
            cons_tot["Value_kt"],
            color=self.COLORS["HIST"],
            linewidth=self.LW + 0.2,
            label="EU jet consumption (gross inland deliveries)",
        )
        # 12-month moving average for trend
        cons_tot["MA12"] = cons_tot["Value_kt"].rolling(12).mean()
        ax.plot(
            cons_tot["Date"],
            cons_tot["MA12"],
            color=self.COLORS["REF"],
            linewidth=self.LW,
            linestyle="--",
            label="12m MA",
        )
        ax.set(
            xlabel="Date",
            ylabel="kt / month",
            title="EU jet/kerosene consumption — monthly Eurostat aggregate",
        )
        ax.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax)

        latest = cons_tot.dropna().iloc[-1]
        covid_trough = cons_tot.loc[cons_tot["Value_kt"].idxmin()]
        pre_covid_peak = cons_tot[cons_tot["Date"] < "2020-03-01"]["Value_kt"].max()
        print(
            f"EU jet consumption latest ({latest['Date'].date()}): {latest['Value_kt']:,.0f} kt/m"
        )
        print(
            f"COVID trough ({covid_trough['Date'].date()}): {covid_trough['Value_kt']:,.0f} kt/m"
            f" — {100 * covid_trough['Value_kt'] / pre_covid_peak:.0f}% of pre-COVID peak"
        )
        print(
            f"Recovery: latest as % of pre-COVID peak = {100 * latest['Value_kt'] / pre_covid_peak:.0f}%"
        )

        fig.suptitle(
            "Jet fuel — demand trajectory",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "EU_JET_CONSUMPTION")

    def chart_eu_consumption_annual(self, MIN_COUNTRIES_REPORTING=15):
        """Annual EU diesel deficit — same Eurostat source as chart_eu_consumption,
        resampled to calendar-year totals. Makes the post-2022 widening visible:
        the ~29 Mt/y pooled mean hides a step-change after Russian re-routing."""
        cons_raw = self.eu_consumption_distil.copy()
        out_raw = self.eu_distillate_out.copy()
        rep = cons_raw[cons_raw["Value_kt"] > 0].groupby("Date")["Country"].nunique()
        valid = rep[rep >= MIN_COUNTRIES_REPORTING].index
        cons = cons_raw[cons_raw["Date"].isin(valid)].copy()
        out = out_raw[out_raw["Date"].isin(valid)].copy()
        cons["Year"] = cons["Date"].dt.year
        out["Year"] = out["Date"].dt.year
        # Keep only full-year observations (drop the current year if incomplete).
        full_year_cons = cons.groupby("Year")["Date"].nunique()
        full_years = full_year_cons[full_year_cons >= 12].index
        cons = cons[cons["Year"].isin(full_years)]
        out = out[out["Year"].isin(full_years)]
        cons_yr = cons.groupby("Year")["Value_kt"].sum() / 1000.0  # → Mt
        out_yr = out.groupby("Year")["Value_kt"].sum() / 1000.0
        deficit = (cons_yr - out_yr).rename("deficit_Mt")

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        bar_colors = [
            self.COLORS["VOL"] if y >= 2022 else self.COLORS["FLOW"] for y in deficit.index
        ]
        bars = ax.bar(deficit.index.astype(str), deficit.values, color=bar_colors, alpha=0.85)
        for bar, val in zip(bars, deficit.values, strict=False):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val + 0.4,
                f"{val:.0f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        # Pre-2022 and 2022+ means for context
        pre22 = deficit[deficit.index < 2022].mean()
        post22 = deficit[deficit.index >= 2022].mean()
        ax.axhline(
            pre22,
            color=self.COLORS["FLOW"],
            linestyle=":",
            linewidth=0.9,
            label=f"Pre-2022 mean {pre22:.0f} Mt/y",
        )
        ax.axhline(
            post22,
            color=self.COLORS["VOL"],
            linestyle=":",
            linewidth=0.9,
            label=f"2022+ mean {post22:.0f} Mt/y",
        )
        ax.set(
            xlabel="Year",
            ylabel="Mt / year",
            title="EU diesel deficit — consumption minus refinery output",
        )
        ax.legend(loc="upper left", fontsize=9)
        print("Annual EU diesel deficit (Mt):")
        for y, v in deficit.items():
            print(f"  {y}: {v:+5.1f}")
        print(
            f"Pre-2022 mean: {pre22:.1f} Mt/y   |   2022+ mean: {post22:.1f} Mt/y   "
            f"step-change: {post22 - pre22:+.1f} Mt/y"
        )

        fig.suptitle(
            "EU diesel deficit — annual view",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "EU_CONSUMPTION_ANNUAL")

    # Helpers ----------------------------------------------------------------

    def _color_stack(self, ax, axis, color, label):
        ax.set_ylabel(label, color=color)
        ax.tick_params(axis=axis, labelcolor=color)
