"""Regional dynamics — Med ↔ NWE integration, Brent-WTI trans-Atlantic basin,
EUR/USD impact on European margins, Russia diesel flows, Europe diesel import
composition, diesel-gasoline premium.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from .core import DEFAULT_CONFIG, Chartable, DataLoader, load_config


class RegionalAnalysis(Chartable):
    """Load spot / FX / flows. Expose Med↔NWE integration, Brent-WTI spread,
    EUR/USD impact on cracks, Russia flows composition, diesel premium."""

    def __init__(self, CONFIG_PATH=None, SAVE_FIGURES=True, LOADER=None):
        cfg = load_config(CONFIG_PATH)
        self.CONFIG = cfg
        self.ROOT = Path(CONFIG_PATH or DEFAULT_CONFIG).resolve().parent
        self._init_styling(cfg, self.ROOT, SAVE_FIGURES)
        self.BBL_PER_MT = cfg["BBL_PER_MT"]

        self.loader = LOADER or DataLoader(CONFIG_PATH)
        self.spot = self.cracks = self.fx = self.eu_imp = self.ru_exp = None
        self.opec_crude_exp = self.opec_prod_exp = None
        self.opec_freight_clean = self.opec_freight_dirty = None
        self.events = []

    # Pipeline ---------------------------------------------------------------

    def load(self):
        self.spot = self.loader.spot_prices()
        self.fx = self.loader.eurusd()
        self.eu_imp = self.loader.europe_diesel_import(GRANULARITY="monthly")
        self.ru_exp = self.loader.russia_diesel_export()
        self.cracks = self.loader.cracks_clean()
        self.events = self.loader.major_dates()
        # OPEC ASB — annual country-level trade + freight (2011-2024 freight, 1980+ trade)
        self.opec_crude_exp = self.loader.opec_t52_crude_exports()
        self.opec_prod_exp = self.loader.opec_t53_product_exports()
        self.opec_freight_clean = self.loader.opec_freight(VESSEL="clean")
        self.opec_freight_dirty = self.loader.opec_freight(VESSEL="dirty")
        print(
            f"[Regional] Spot {len(self.spot)} | FX {len(self.fx)} | "
            f"EU imports {len(self.eu_imp)} | RU exports {len(self.ru_exp)} | "
            f"Cracks {len(self.cracks)} | "
            f"OPEC exports crude/products {len(self.opec_crude_exp)}/{len(self.opec_prod_exp)} rows | "
            f"Freight clean/dirty {len(self.opec_freight_clean)}/{len(self.opec_freight_dirty)} rows"
        )
        return self

    # Charts -----------------------------------------------------------------

    def chart_med_nwe_integration(self):
        """ULSD Med vs NWE levels + differential."""
        s = self.spot.copy()
        s["ULSD_NWE_bbl"] = s["ULSD_NWE_mt"] / self.BBL_PER_MT["ULSD"]
        s = s[["Date", "ULSD_NWE_bbl", "ULSD_Med_bbl"]].dropna()

        fig, (ax_top, ax_bot) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        ax_top.plot(
            s["Date"],
            s["ULSD_NWE_bbl"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW,
            label="ULSD CIF NWE (USD/bbl)",
        )
        ax_top.plot(
            s["Date"],
            s["ULSD_Med_bbl"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            label="ULSD CIF Med (USD/bbl)",
        )
        ax_top.set(ylabel="USD/bbl")
        ax_top.set_title(
            "ULSD NWE vs ULSD Med — level", loc="left", fontsize=10, fontweight="normal"
        )
        ax_top.legend(loc="upper left")
        self._format_xaxis(ax_top)

        s["diff"] = s["ULSD_NWE_bbl"] - s["ULSD_Med_bbl"]
        ax_bot.plot(s["Date"], s["diff"], color=self.COLORS["MARGIN"], linewidth=self.LW)
        self._zero_line(ax_bot)
        ax_bot.set(xlabel="Date", ylabel="NWE − Med (USD/bbl)")
        ax_bot.set_title(
            "Regional differential — positive = NWE premium",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        self._format_xaxis(ax_bot)

        level_r = s[["ULSD_NWE_bbl", "ULSD_Med_bbl"]].corr().iloc[0, 1]
        diff_r = s[["ULSD_NWE_bbl", "ULSD_Med_bbl"]].diff().corr().iloc[0, 1]
        print(f"ULSD NWE ↔ Med:  level r = {level_r:+.3f}   Δ-level r = {diff_r:+.3f}")
        print(f"Mean NWE − Med:  {s['diff'].mean():+.2f} USD/bbl  (σ = {s['diff'].std():.2f})")

        fig.suptitle(
            "ULSD — Med / NWE integration",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "MED_NWE_INTEGRATION")

    def chart_brent_wti_spread(self):
        """Brent − WTI trans-Atlantic spread + distribution."""
        s = self.spot[["Date", "Brent_bbl", "WTI_bbl"]].dropna()
        s["spread"] = s["Brent_bbl"] - s["WTI_bbl"]

        fig, (ax_ts, ax_hist) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 1, self.SIZES["SQUARE"][1]),
            gridspec_kw={"width_ratios": [3, 1], "wspace": 0.3},
        )

        ax_ts.plot(s["Date"], s["spread"], color=self.COLORS["PRICE"], linewidth=self.LW)
        self._zero_line(ax_ts)
        mean_s = s["spread"].mean()
        ax_ts.axhline(
            mean_s,
            color=self.COLORS["REF"],
            linestyle=":",
            linewidth=0.8,
            label=f"Mean = {mean_s:+.2f} USD/bbl",
        )
        ax_ts.set(xlabel="Date", ylabel="Brent − WTI (USD/bbl)")
        ax_ts.set_title(
            "Trans-Atlantic basin — Brent premium over WTI",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_ts.legend(loc="upper left")
        self._format_xaxis(ax_ts)
        self._add_event_markers(ax_ts)

        ax_hist.hist(
            s["spread"],
            bins=40,
            color=self.COLORS["PRICE"],
            alpha=0.75,
            edgecolor="white",
            orientation="horizontal",
        )
        ax_hist.axhline(mean_s, color=self.COLORS["REF"], linestyle=":", linewidth=0.8)
        ax_hist.set(xlabel="Frequency", title="Distribution")
        ax_hist.grid(True, alpha=0.3, axis="x")

        peak = s.loc[s["spread"].idxmax()]
        print(f"Brent-WTI mean : {mean_s:+.2f} USD/bbl  (n={len(s)})")
        print(f"Brent-WTI peak : {peak['spread']:+.2f} on {peak['Date'].date()}")
        brent_premium = (s["spread"] > 0).mean() * 100
        print(f"% days Brent > WTI: {brent_premium:.1f}%")

        fig.suptitle(
            "Brent ↔ WTI spot spread", x=0.01, ha="left", fontsize=13, fontweight="bold", y=1.02
        )
        return self._finalize(fig, "BRENT_WTI_SPREAD")

    def chart_eurusd_impact(self):
        """Rolling correlation of ΔEUR/USD with ΔBrent-ULSD NWE crack."""
        fx = self.fx.rename(columns={"EUR_USD": "fx"})
        crack = self.cracks[["Date", "Brent_ULSD_NWE_Crack"]].rename(
            columns={"Brent_ULSD_NWE_Crack": "crack"}
        )
        df = fx.merge(crack, on="Date", how="inner").sort_values("Date")
        df["d_fx"] = df["fx"].diff()
        df["d_crack"] = df["crack"].diff()
        df = df.dropna()
        df["roll_r"] = df["d_fx"].rolling(self.ROLL_WINDOW).corr(df["d_crack"])

        fig, (ax_lvl, ax_corr) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        ax_lvl.plot(
            df["Date"], df["fx"], color=self.COLORS["FX"], linewidth=self.LW, label="EUR/USD"
        )
        self._color_stack(ax_lvl, "y", self.COLORS["FX"], "EUR/USD")
        ax2 = ax_lvl.twinx()
        ax2.plot(
            df["Date"],
            df["crack"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            alpha=0.85,
            label="Brent-ULSD NWE crack",
        )
        self._color_stack(ax2, "y", self.COLORS["CRACK"], "Crack (USD/bbl)")
        ax_lvl.set_title(
            "EUR/USD vs Brent-ULSD NWE crack", loc="left", fontsize=10, fontweight="normal"
        )
        self._format_xaxis(ax_lvl)

        ax_corr.plot(df["Date"], df["roll_r"], color=self.COLORS["PRICE"], linewidth=self.LW)
        self._zero_line(ax_corr)
        ax_corr.set(xlabel="Date", ylabel=f"{self.ROLL_WINDOW}-day Δ corr", ylim=(-1.05, 1.05))
        ax_corr.set_title(
            "Rolling ΔEUR/USD ↔ ΔCrack correlation", loc="left", fontsize=10, fontweight="normal"
        )
        self._format_xaxis(ax_corr)

        # Pooled correlation
        full_r = df["d_fx"].corr(df["d_crack"])
        print(f"Full-sample Δ-correlation (EUR/USD, crack): {full_r:+.3f}   n = {len(df)}")

        # Regime-split: pre-2025 (calm) vs 2025+ (crisis OOS) — panel feedback
        # said pooled correlation masks regime-specific FX behaviour.
        import pandas as _pd

        cutoff = _pd.Timestamp(self.Z_IS_END if hasattr(self, "Z_IS_END") else "2024-12-31")
        d_is = df[df["Date"] <= cutoff]
        d_oos = df[df["Date"] > cutoff]
        if len(d_is) > 20:
            r_is = d_is["d_fx"].corr(d_is["d_crack"])
            print(
                f"  → IS window ({d_is['Date'].min().date()} → {cutoff.date()}): "
                f"Δ-corr {r_is:+.3f}, n = {len(d_is)}"
            )
        if len(d_oos) > 20:
            r_oos = d_oos["d_fx"].corr(d_oos["d_crack"])
            print(
                f"  → OOS window ({cutoff.date()} → {d_oos['Date'].max().date()}): "
                f"Δ-corr {r_oos:+.3f}, n = {len(d_oos)}"
            )
            ratio = r_oos / r_is if len(d_is) > 20 and abs(r_is) > 0.02 else float("nan")
            print(
                f"  → OOS/IS ratio {ratio:+.2f}× — "
                f"{'FX more correlated with crack under current regime' if abs(r_oos) > abs(r_is) + 0.05 else 'conclusion stable — EUR/USD is diagnostic, not directional, in both regimes'}"
            )

        fig.suptitle(
            "EUR/USD ↔ European refining margin",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "EURUSD_IMPACT")

    def chart_russia_export(self, TOP_N=8):
        """Russia diesel-export destinations — monthly aggregate + current mix."""
        df = self.ru_exp.copy()
        mon = df.groupby(["Date", "Destination"], as_index=False)["Quantity_kt"].sum()
        top_dest = (
            mon.groupby("Destination")["Quantity_kt"]
            .sum()
            .sort_values(ascending=False)
            .head(TOP_N)
            .index
        )
        mon_top = mon[mon["Destination"].isin(top_dest)]
        pivot = mon_top.pivot(index="Date", columns="Destination", values="Quantity_kt").fillna(0)

        fig, (ax_ts, ax_pie) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 2, self.SIZES["SQUARE"][1]),
            gridspec_kw={"width_ratios": [2, 1], "wspace": 0.3},
        )

        colors = plt.cm.tab10.colors
        ax_ts.stackplot(
            pivot.index,
            *[pivot[c].values for c in pivot.columns],
            labels=list(pivot.columns),
            colors=colors[: len(pivot.columns)],
            alpha=0.85,
            linewidth=0,
        )
        ax_ts.set(xlabel="Date", ylabel="kt / month")
        ax_ts.set_title(
            "Russia diesel exports — top destinations", loc="left", fontsize=10, fontweight="normal"
        )
        ax_ts.legend(loc="upper left", ncol=2, fontsize=8)
        self._format_xaxis(ax_ts)

        # Current-month snapshot pie
        latest = pivot.iloc[-1]
        latest = latest[latest > 0].sort_values(ascending=False)
        ax_pie.pie(
            latest.values,
            labels=latest.index,
            autopct="%.0f%%",
            colors=colors[: len(latest)],
            startangle=90,
            textprops={"fontsize": 8},
        )
        ax_pie.set_title(f"Latest month: {pivot.index[-1].date()}", loc="center", fontsize=10)

        total_latest = latest.sum()
        top1 = latest.index[0]
        print(f"Russia diesel exports latest month total: {total_latest:,.0f} kt")
        print(
            f"Top destination: {top1} ({latest.iloc[0]:,.0f} kt, "
            f"{100 * latest.iloc[0] / total_latest:.0f}%)"
        )
        fig.suptitle(
            "Russia diesel export destinations",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "RUSSIA_EXPORT")

    def chart_europe_import_mix(self, TOP_N=8):
        """Europe diesel import origin mix — monthly stacked area."""
        df = self.eu_imp.copy()
        top_origin = (
            df.groupby("Origin")["Quantity_kt"].sum().sort_values(ascending=False).head(TOP_N).index
        )
        df_top = df[df["Origin"].isin(top_origin)]
        pivot = df_top.pivot_table(
            index="Date", columns="Origin", values="Quantity_kt", aggfunc="sum"
        ).fillna(0)

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.stackplot(
            pivot.index,
            *[pivot[c].values for c in pivot.columns],
            labels=list(pivot.columns),
            colors=plt.cm.tab10.colors[: len(pivot.columns)],
            alpha=0.85,
            linewidth=0,
        )
        ax.set(xlabel="Date", ylabel="kt / month")
        ax.set_title("Europe diesel imports — top origins", loc="left")
        ax.legend(loc="upper left", ncol=2, fontsize=8)
        self._format_xaxis(ax)

        latest = pivot.iloc[-1].sort_values(ascending=False)
        latest = latest[latest > 0]
        print(f"Latest month total EU imports: {latest.sum():,.0f} kt")
        print("Top 3 origins:")
        for o, v in latest.head(3).items():
            print(f"   {o:20s} {v:>8,.0f} kt  ({100 * v / latest.sum():.0f}%)")
        return self._finalize(fig, "EUROPE_IMPORT_MIX")

    def chart_diesel_gas_premium(self):
        """Diesel crack − gasoline crack = the "middle distillate premium"."""
        c = self.cracks[["Date", "Brent_ULSD_NWE_Crack", "Brent_EBOB_Crack"]].dropna()
        c["premium"] = c["Brent_ULSD_NWE_Crack"] - c["Brent_EBOB_Crack"]

        fig, (ax_ts, ax_hist) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 1, self.SIZES["SQUARE"][1]),
            gridspec_kw={"width_ratios": [3, 1], "wspace": 0.3},
        )

        ax_ts.plot(c["Date"], c["premium"], color=self.COLORS["MARGIN"], linewidth=self.LW)
        self._zero_line(ax_ts)
        mean_p = c["premium"].mean()
        ax_ts.axhline(
            mean_p,
            color=self.COLORS["REF"],
            linestyle=":",
            linewidth=0.8,
            label=f"Mean = {mean_p:+.2f} USD/bbl",
        )
        ax_ts.set(xlabel="Date", ylabel="ULSD crack − EBOB crack (USD/bbl)")
        ax_ts.set_title("Diesel premium to gasoline", loc="left", fontsize=10, fontweight="normal")
        ax_ts.legend(loc="upper left")
        self._format_xaxis(ax_ts)

        ax_hist.hist(
            c["premium"],
            bins=40,
            color=self.COLORS["MARGIN"],
            alpha=0.75,
            edgecolor="white",
            orientation="horizontal",
        )
        ax_hist.axhline(mean_p, color=self.COLORS["REF"], linestyle=":", linewidth=0.8)
        ax_hist.set(xlabel="Frequency", title="Distribution")
        ax_hist.grid(True, alpha=0.3, axis="x")

        peak = c.loc[c["premium"].idxmax()]
        print(
            f"Diesel-gas premium: mean {mean_p:+.2f} USD/bbl, "
            f"peak {peak['premium']:+.2f} on {peak['Date'].date()}"
        )
        fig.suptitle(
            "Diesel premium over gasoline",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "DIESEL_GAS_PREMIUM")

    # OPEC ASB 2025 — global trade flows + freight -------------------------

    def chart_opec_trade_flows(self, TOP_N=12):
        """OPEC ASB crude + product export rankings — latest year + 10y
        trajectory for the top-TOP_N exporters. Aggregates filtered out."""
        crude = self.opec_crude_exp[not self.opec_crude_exp["is_aggregate"]].copy()
        prod = self.opec_prod_exp[not self.opec_prod_exp["is_aggregate"]].copy()
        latest_year = max(crude["Year"].max(), prod["Year"].max())

        fig, axes = plt.subplots(
            2,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 2, self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"width_ratios": [1.2, 2], "hspace": 0.45, "wspace": 0.35},
        )

        for row, (df, label, color) in enumerate(
            [
                (crude, "crude", self.COLORS["PRICE"]),
                (prod, "products", self.COLORS["CRACK"]),
            ]
        ):
            # Latest-year ranking
            rank = (
                df[df["Year"] == latest_year].sort_values("Value_kbd", ascending=False).head(TOP_N)
            )
            ax_bar = axes[row, 0]
            ax_bar.barh(rank["Country"][::-1], rank["Value_kbd"][::-1], color=color, alpha=0.85)
            ax_bar.set(xlabel="kbd", title=f"Top {TOP_N} {label} exporters — {latest_year}")
            ax_bar.grid(True, alpha=0.3, axis="x")

            # 10y trajectory for top-N
            top_countries = rank["Country"].tolist()
            since = latest_year - 10
            traj = df[df["Country"].isin(top_countries) & (df["Year"] >= since)]
            ax_ts = axes[row, 1]
            colors_c = plt.cm.tab10.colors
            for i, c in enumerate(top_countries):
                sub = traj[traj["Country"] == c].sort_values("Year")
                ax_ts.plot(
                    sub["Year"],
                    sub["Value_kbd"],
                    color=colors_c[i % 10],
                    linewidth=self.LW,
                    label=c,
                    marker="o",
                    markersize=3,
                )
            ax_ts.set(
                xlabel="Year", ylabel="kbd", title=f"{label.capitalize()} exports — 10y trajectory"
            )
            ax_ts.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=7, ncol=1)
            ax_ts.grid(True, alpha=0.3)

        # Summary prints
        c_top = (
            crude[crude["Year"] == latest_year].sort_values("Value_kbd", ascending=False).head(3)
        )
        p_top = prod[prod["Year"] == latest_year].sort_values("Value_kbd", ascending=False).head(3)
        print(f"OPEC ASB {latest_year} — top 3 crude exporters:")
        for _, r in c_top.iterrows():
            print(f"   {r['Country']:25s} {r['Value_kbd']:>8,.0f} kbd")
        print(f"OPEC ASB {latest_year} — top 3 product exporters:")
        for _, r in p_top.iterrows():
            print(f"   {r['Country']:25s} {r['Value_kbd']:>8,.0f} kbd")

        fig.suptitle(
            f"Global oil trade — crude & product exports (OPEC ASB, through {latest_year})",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "OPEC_TRADE_FLOWS")

    def chart_opec_tanker_freight(self):
        """WS% freight assessments by route — clean vs dirty, 2011-latest.
        Crisis markers show Hormuz / Red Sea / Russia-sanctions impact."""
        clean = self.opec_freight_clean.copy()
        dirty = self.opec_freight_dirty.copy()

        fig, (ax_c, ax_d) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            sharex=True,
            gridspec_kw={"hspace": 0.3},
        )

        colors_c = plt.cm.tab10.colors
        for i, route in enumerate(sorted(clean["route"].unique())):
            sub = clean[clean["route"] == route].sort_values("year")
            ax_c.plot(
                sub["year"],
                sub["value"],
                color=colors_c[i % 10],
                linewidth=self.LW,
                marker="o",
                markersize=3,
                label=route,
            )
        ax_c.set(ylabel="WS%  (clean)")
        ax_c.set_title(
            "Tanker freight — clean (products) routes", loc="left", fontsize=10, fontweight="normal"
        )
        ax_c.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, ncol=1)
        ax_c.grid(True, alpha=0.3)

        for i, route in enumerate(sorted(dirty["route"].unique())):
            sub = dirty[dirty["route"] == route].sort_values("year")
            ax_d.plot(
                sub["year"],
                sub["value"],
                color=colors_c[i % 10],
                linewidth=self.LW,
                marker="o",
                markersize=3,
                label=route,
            )
        ax_d.set(xlabel="Year", ylabel="WS%  (dirty)")
        ax_d.set_title(
            "Tanker freight — dirty (crude) routes", loc="left", fontsize=10, fontweight="normal"
        )
        ax_d.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, ncol=1)
        ax_d.grid(True, alpha=0.3)

        # Highlight events visible in annual data (Russia sanctions, Hormuz, Red Sea)
        for ax in (ax_c, ax_d):
            for y, _lbl in [(2022, "Russia invasion / sanctions"), (2024, "Red Sea attacks")]:
                ax.axvline(y, color="black", linestyle="--", linewidth=0.8, alpha=0.5)

        latest_year = clean["year"].max()
        max_c = clean[clean["year"] == latest_year].nlargest(1, "value").iloc[0]
        max_d = dirty[dirty["year"] == latest_year].nlargest(1, "value").iloc[0]
        print(f"OPEC ASB freight — latest year {latest_year}")
        print(f"   Highest-quoted clean route: {max_c['route']:10s} {max_c['value']:.0f} WS%")
        print(f"   Highest-quoted dirty route: {max_d['route']:10s} {max_d['value']:.0f} WS%")

        fig.suptitle(
            "Tanker freight — WS% assessments (OPEC ASB, annual averages)",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        return self._finalize(fig, "OPEC_TANKER_FREIGHT")

    # Helpers ----------------------------------------------------------------

    def _color_stack(self, ax, axis, color, label):
        ax.set_ylabel(label, color=color)
        ax.tick_params(axis=axis, labelcolor=color)
