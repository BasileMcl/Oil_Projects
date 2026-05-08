"""NWE refining-margin analytics.

Supported slates: 3-2-1 · 2-1-1 · ULSD · EBOB · FO35. Unit-aligned to USD/bbl
via industry-standard bbl/MT conversions. Regional variant: Med (ULSD CIF Med)
vs NWE (ULSD CIF NWE) for the diesel leg.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

from .core import DEFAULT_CONFIG, Chartable, DataLoader, load_config


class CrackSpreadAnalysis(Chartable):
    """End-to-end NWE / Med crack-spread analysis — load, build margin per
    slate, IS/OOS split, distribution + regime charts."""

    def __init__(self, CONFIG_PATH=None, SAVE_FIGURES=True, LOADER=None):
        cfg = load_config(CONFIG_PATH)
        self.CONFIG = cfg
        self.ROOT = Path(CONFIG_PATH or DEFAULT_CONFIG).resolve().parent
        self._init_styling(cfg, self.ROOT, SAVE_FIGURES)

        self.BBL_PER_MT = cfg["BBL_PER_MT"]
        self.SLATES = cfg["CRACK_SLATES"]
        self.REGIONS = cfg["CRACK_PRODUCT_REGION"]
        self.Q = cfg["ANALYSIS"]["REGIME_QUANTILES"]

        self.loader = LOADER or DataLoader(CONFIG_PATH)
        self.df_raw = None
        self.df = None
        self.slate = None
        self.region = None

    # Pipeline ---------------------------------------------------------------

    def load(self):
        spot = self.loader.spot_prices()
        bfut = self.loader.brent_futures()
        self.df_raw = (
            spot.merge(bfut, on="Date", how="outer").sort_values("Date").reset_index(drop=True)
        )
        # Three-track Brent view (M1 futures / spot / Dated) — kept separate so
        # downstream code can pull any of the three explicitly. The default
        # crack build still uses Brent M1 futures; see CRACK_METHODOLOGY.md
        # for the structural mismatch between prompt-physical product and
        # forward-paper crude, and why the three tracks differ.
        self.df_brent_tracks = self.loader.three_brent_tracks()
        self.events = self.loader.major_dates()
        return self

    def build(self, SLATE="3-2-1", REGION="NWE", BRENT_SOURCE="M1"):
        """Compute per-barrel-of-crude margin for a given slate and product
        region. Region 'NWE' uses ULSD CIF NWE; 'Med' uses ULSD CIF Med.

        BRENT_SOURCE selects the crude leg:
          'M1'    : ICE Brent front-month futures (default, longest history)
          'spot'  : Platts-assessed spot Brent (from Spot_prices.xlsx)
          'dated' : Dated Brent physical assessment (Jan-Apr 2026 window only)

        Note on contract-month alignment: product spot assessments are prompt
        physical (delivery within weeks) while Brent M1 futures deliver ~2
        months forward. This is a structural mismatch inherited from the
        data, not a methodology error. The 'dated' option gives a physical-
        vs-physical read where the data supports it. See CRACK_METHODOLOGY.md
        for the full discussion, including the separate Brent-vs-LSGO
        futures-vs-futures alignment used in Project 1 cross-market work.
        """
        if SLATE not in self.SLATES:
            raise KeyError(f"Unknown slate {SLATE!r}. Available: {list(self.SLATES)}")
        if REGION not in self.REGIONS:
            raise KeyError(f"Unknown region {REGION!r}. Available: {list(self.REGIONS)}")
        if BRENT_SOURCE not in ("M1", "spot", "dated"):
            raise ValueError(f"BRENT_SOURCE must be M1, spot, or dated; got {BRENT_SOURCE!r}")

        w = self.SLATES[SLATE]
        cols = self.REGIONS[REGION]
        df = self.df_raw.copy()

        # Attach the requested Brent track. Column name is always 'Brent_M1_bbl'
        # downstream (for back-compat) but the underlying source varies.
        if BRENT_SOURCE != "M1":
            tracks = self.df_brent_tracks.copy()
            src_col = {"spot": "Brent_spot_bbl", "dated": "Dated_Brent_bbl"}[BRENT_SOURCE]
            if src_col not in tracks.columns:
                raise RuntimeError(f"Track {src_col} not available in merged Brent frame")
            df = df.drop(columns=[c for c in ["Brent_M1_bbl"] if c in df.columns])
            df = df.merge(tracks[["Date", src_col]], on="Date", how="left")
            df = df.rename(columns={src_col: "Brent_M1_bbl"})

        # Convert each product leg to USD/bbl (handle the unit suffix — _mt or _bbl)
        def to_bbl(source_col, product_key):
            if source_col.endswith("_bbl"):
                return df[source_col]
            if source_col.endswith("_mt"):
                return df[source_col] / self.BBL_PER_MT[product_key]
            raise ValueError(f"Column {source_col!r} needs _bbl or _mt suffix")

        df["ULSD_bbl"] = to_bbl(cols["ULSD"], "ULSD")
        df["EBOB_bbl"] = to_bbl(cols["EBOB"], "EBOB")
        df["FO_bbl"] = to_bbl(cols["FO"], "FO")

        n_crude = max(w["BRENT"], 1)
        df["margin"] = (
            w["EBOB"] * df["EBOB_bbl"]
            + w["ULSD"] * df["ULSD_bbl"]
            + w["FO"] * df["FO_bbl"]
            - w["BRENT"] * df["Brent_M1_bbl"]
        ) / n_crude
        df = df.dropna(subset=["margin", "Brent_M1_bbl"]).reset_index(drop=True)

        # IS / OOS tag
        df["is_oos"] = (df["Date"] > self.Z_IS_END).map({True: "OOS", False: "IS"})

        self.df = df
        self.slate = SLATE
        self.region = REGION
        self.brent_source = BRENT_SOURCE

        peak_idx = df["margin"].idxmax()
        print(
            f"[CrackSpread {SLATE}/{REGION} · crude={BRENT_SOURCE}] {len(df)} days  "
            f"| mean {df['margin'].mean():.2f} USD/bbl  "
            f"| max {df['margin'].max():.2f} on {df.loc[peak_idx, 'Date'].date()}"
        )
        return self

    # Stats ------------------------------------------------------------------

    def summary_stats(self):
        df = self.df
        m = df["margin"]
        is_ = df.loc[df["is_oos"] == "IS", "margin"]
        oos = df.loc[df["is_oos"] == "OOS", "margin"]
        stats = {
            "n": len(df),
            "Mean (USD/bbl)": f"{m.mean():.2f}",
            "IS mean": f"{is_.mean():.2f}",
            "OOS mean": f"{oos.mean():.2f}" if len(oos) else "n/a",
            "Max": f"{m.max():.2f} ({df.loc[m.idxmax(), 'Date'].date()})",
            "Min": f"{m.min():.2f} ({df.loc[m.idxmin(), 'Date'].date()})",
            "Skewness": f"{skew(m):.2f}",
            "Ex. kurtosis": f"{kurtosis(m):.2f}",
            "Days margin < 0": f"{(m < 0).sum()} ({100 * (m < 0).mean():.1f}%)",
        }
        out = pd.DataFrame.from_dict(
            stats, orient="index", columns=[f"{self.slate} / {self.region}"]
        )
        print(out.to_string())
        return out

    def calibrate_regime_thresholds(self):
        """CDF-calibrated on IS window. Symmetric — high-margin peaks and
        low-margin squeezes both flagged."""
        is_m = self.df.loc[self.df["is_oos"] == "IS", "margin"].dropna()
        thr = {
            "CRISIS_LO": is_m.quantile(self.Q["LOW_CRISIS"]),
            "STRESS_LO": is_m.quantile(self.Q["LOW_STRESS"]),
            "STRESS_HI": is_m.quantile(self.Q["HIGH_STRESS"]),
            "CRISIS_HI": is_m.quantile(self.Q["HIGH_CRISIS"]),
        }

        def classify(x):
            if pd.isna(x):
                return "Unknown"
            if x < thr["CRISIS_LO"]:
                return "Crisis-Low"
            if x < thr["STRESS_LO"]:
                return "Stress-Low"
            if x > thr["CRISIS_HI"]:
                return "Crisis-High"
            if x > thr["STRESS_HI"]:
                return "Stress-High"
            return "Normal"

        self.df["Regime"] = self.df["margin"].apply(classify)
        self._thresholds = thr
        counts = self.df.loc[self.df["is_oos"] == "OOS", "Regime"].value_counts().to_dict()
        print(
            f"Thresholds (USD/bbl): "
            f"Crisis-Lo {thr['CRISIS_LO']:.2f} · Stress-Lo {thr['STRESS_LO']:.2f} · "
            f"Stress-Hi {thr['STRESS_HI']:.2f} · Crisis-Hi {thr['CRISIS_HI']:.2f}"
        )
        print(f"OOS regime days: {counts}")
        return thr

    # Charts -----------------------------------------------------------------

    def chart_time_series(self, OVERLAY_EVENTS=True):
        df = self.df
        fig, (ax_full, ax_recent) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 4),
            gridspec_kw={"height_ratios": [1, 1], "hspace": 0.35},
        )
        for ax, frame, subtitle, overlay in [
            (ax_full, df, "Full sample", False),
            (ax_recent, self._recent(df), f"Last {self.RECENT_MONTHS} months", OVERLAY_EVENTS),
        ]:
            ax.plot(
                frame["Date"],
                frame["margin"],
                color=self.COLORS["CRACK"],
                linewidth=self.LW,
                label=f"{self.slate} / {self.region}",
            )
            ax.axhline(
                df["margin"].mean(),
                color=self.COLORS["REF"],
                linestyle=":",
                linewidth=0.8,
                alpha=0.6,
                label=f"Full-sample mean = {df['margin'].mean():.2f}",
            )
            self._zero_line(ax)
            ax.set(xlabel="Date", ylabel="Margin (USD/bbl)")
            ax.set_title(subtitle, loc="left", fontsize=10, fontweight="normal")
            ax.legend(loc="upper left", fontsize=9)
            self._format_xaxis(ax)
            if overlay:
                self._add_event_markers(ax)
        fig.suptitle(
            f"NWE {self.slate} refining margin — {self.region}",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )

        # Interpretation
        m, last = df["margin"], df.iloc[-1]
        last_pct = (df["margin"] < last["margin"]).mean() * 100
        is_mean = df.loc[df["is_oos"] == "IS", "margin"].mean()
        oos_mean = (
            df.loc[df["is_oos"] == "OOS", "margin"].mean()
            if (df["is_oos"] == "OOS").any()
            else float("nan")
        )
        print(
            f"Read: {self.slate}/{self.region} margin is {last['margin']:.1f} USD/bbl on {last['Date'].date()} "
            f"({last_pct:.0f}th percentile full-sample). IS mean = {is_mean:.1f}, OOS mean = {oos_mean:.1f}. "
            f"Peak was {m.max():.1f} on {df.loc[m.idxmax(), 'Date'].date()}."
        )
        return self._finalize(fig, "CRACK_TIME_SERIES")

    def chart_three_brent_tracks(self):
        """Overlay Brent M1 futures, Brent spot (Platts), and Dated Brent on
        one panel. Demonstrates that the three are distinct instruments and
        diverge by tens of dollars under stress (April 2026 Dated-vs-M1 basis
        peaked around $35/bbl). Used in the methodology section to make the
        spot-vs-paper distinction visible alongside the prose."""
        df = self.df_brent_tracks.copy()
        if df is None or len(df) == 0:
            print("[chart_three_brent_tracks] No Brent-tracks frame loaded.")
            return None
        df = df.dropna(subset=["Brent_M1_bbl"])
        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.plot(
            df["Date"],
            df["Brent_M1_bbl"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW,
            label="Brent M1 (ICE futures front-month)",
        )
        if "Brent_spot_bbl" in df.columns and df["Brent_spot_bbl"].notna().any():
            sp = df.dropna(subset=["Brent_spot_bbl"])
            ax.plot(
                sp["Date"],
                sp["Brent_spot_bbl"],
                color=self.COLORS["HIST"],
                linewidth=self.LW,
                alpha=0.85,
                label="Brent spot (Platts assessed)",
            )
        if "Dated_Brent_bbl" in df.columns and df["Dated_Brent_bbl"].notna().any():
            dt = df.dropna(subset=["Dated_Brent_bbl"])
            ax.plot(
                dt["Date"],
                dt["Dated_Brent_bbl"],
                color=self.COLORS["VOL"],
                linewidth=self.LW + 0.4,
                label="Dated Brent (Platts physical, 16:30 London)",
            )

        ax.set(
            xlabel="Date",
            ylabel="USD/bbl",
            title="Three Brent series: futures vs spot vs Dated physical",
        )
        ax.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax)

        # Diagnostic prints — quantify divergence on overlap dates
        if "Dated_Brent_bbl" in df.columns:
            ovl = df.dropna(subset=["Brent_M1_bbl", "Dated_Brent_bbl"])
            if len(ovl):
                basis = ovl["Dated_Brent_bbl"] - ovl["Brent_M1_bbl"]
                print(
                    f"Dated Brent vs M1 futures: {len(ovl)} overlap days  "
                    f"(only {ovl['Date'].min().date()} to {ovl['Date'].max().date()})"
                )
                print(
                    f"  mean basis = {basis.mean():+.2f} USD/bbl  "
                    f"| max basis = {basis.max():+.2f} on {ovl.loc[basis.idxmax(), 'Date'].date()}  "
                    f"| min = {basis.min():+.2f} on {ovl.loc[basis.idxmin(), 'Date'].date()}"
                )
        if "Brent_spot_bbl" in df.columns:
            ovl2 = df.dropna(subset=["Brent_M1_bbl", "Brent_spot_bbl"])
            if len(ovl2):
                basis2 = ovl2["Brent_spot_bbl"] - ovl2["Brent_M1_bbl"]
                print(
                    f"Brent spot vs M1 futures: {len(ovl2)} overlap days  "
                    f"mean basis = {basis2.mean():+.2f}  | max = {basis2.max():+.2f}"
                )

        fig.suptitle(
            "Spot, futures, Dated — three different Brent prices",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "BRENT_THREE_TRACKS")

    def chart_distribution(self):
        df = self.df
        is_ = df.loc[df["is_oos"] == "IS", "margin"].dropna()
        oos = df.loc[df["is_oos"] == "OOS", "margin"].dropna()
        fig, (ax_full, ax_zoom) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 1, self.SIZES["SQUARE"][1]),
            gridspec_kw={"wspace": 0.25},
        )
        for ax, xlim, title in [
            (ax_full, None, "Full range"),
            (
                ax_zoom,
                (is_.quantile(0.005), is_.quantile(0.995)) if len(is_) > 20 else None,
                "IS-range zoom",
            ),
        ]:
            ax.hist(
                is_,
                bins=self.HIST_BINS,
                color=self.COLORS["PRICE"],
                alpha=0.55,
                density=True,
                edgecolor="white",
                label=f"IS (n={len(is_)})",
            )
            if len(oos):
                ax.hist(
                    oos,
                    bins=self.HIST_BINS,
                    color=self.COLORS["HIST"],
                    alpha=0.55,
                    density=True,
                    edgecolor="white",
                    label=f"OOS (n={len(oos)})",
                )
            ax.axvline(
                is_.mean(),
                color=self.COLORS["PRICE"],
                linestyle="--",
                linewidth=1.5,
                alpha=0.8,
                label=f"IS μ = {is_.mean():.2f}",
            )
            if len(oos):
                ax.axvline(
                    oos.mean(),
                    color=self.COLORS["VOL"],
                    linestyle="--",
                    linewidth=1.5,
                    alpha=0.8,
                    label=f"OOS μ = {oos.mean():.2f}",
                )
            if xlim is not None:
                ax.set_xlim(xlim)
            ax.set(xlabel="Margin (USD/bbl)", ylabel="Density")
            ax.set_title(title, loc="left", fontsize=10, fontweight="normal")
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3, axis="y")
            ax.grid(False, axis="x")
        fig.suptitle(
            f"NWE {self.slate}/{self.region} — IS vs OOS distribution",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "CRACK_DISTRIBUTION")

    def chart_components(self):
        df = self.df
        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.plot(
            df["Date"],
            df["ULSD_bbl"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            label=f"ULSD {self.region} (USD/bbl)",
        )
        ax.plot(
            df["Date"],
            df["EBOB_bbl"],
            color=self.COLORS["MARGIN"],
            linewidth=self.LW,
            label="Gasoline EBOB (USD/bbl)",
        )
        ax.plot(
            df["Date"],
            df["Brent_M1_bbl"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW,
            label="Brent M1 (USD/bbl)",
        )
        ax.set(xlabel="Date", ylabel="USD/bbl")
        ax.set_title(f"Crack components — unit-aligned, {self.region}", loc="left")
        ax.legend(loc="upper left")
        self._format_xaxis(ax)
        return self._finalize(fig, "CRACK_COMPONENTS")

    def chart_regime(self):
        self.calibrate_regime_thresholds()
        df = self.df
        thr = self._thresholds
        fig, ax = plt.subplots(figsize=self.SIZES["WIDE"])
        palette = self.COLORS["REGIMES"]
        for regime, color in palette.items():
            mask = df["Regime"] == regime
            if mask.any():
                ax.scatter(
                    df.loc[mask, "Date"],
                    df.loc[mask, "margin"],
                    c=color,
                    label=regime,
                    s=22,
                    alpha=self.A["REGIME"],
                )
        for _k, v in thr.items():
            ax.axhline(v, color=self.COLORS["REF"], linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set(xlabel="Date", ylabel=f"{self.slate} margin (USD/bbl)")
        ax.set_title(f"NWE {self.slate}/{self.region} — regime classification", loc="left")
        ax.legend(loc="upper left", ncol=3, fontsize=9)
        self._format_xaxis(ax)
        return self._finalize(fig, "CRACK_REGIME")

    def chart_med_vs_nwe(self):
        """Compare ULSD-based diesel cracks between Med and NWE."""
        # Rebuild both then restore original slate/region
        orig_slate, orig_region = self.slate, self.region
        self.build(SLATE="ULSD", REGION="NWE")
        nwe = self.df[["Date", "margin"]].rename(columns={"margin": "NWE"})
        self.build(SLATE="ULSD", REGION="MED")
        med = self.df[["Date", "margin"]].rename(columns={"margin": "MED"})
        merged = nwe.merge(med, on="Date", how="outer").sort_values("Date")

        fig, (ax_top, ax_bot) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.3},
        )

        ax_top.plot(
            merged["Date"],
            merged["NWE"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW,
            label="ULSD NWE crack",
        )
        ax_top.plot(
            merged["Date"],
            merged["MED"],
            color=self.COLORS["MARGIN"],
            linewidth=self.LW,
            label="ULSD Med crack",
        )
        ax_top.set(ylabel="Margin (USD/bbl)")
        ax_top.set_title("Med vs NWE ULSD crack — level", loc="left", fontsize=10)
        ax_top.legend(loc="upper left")
        self._format_xaxis(ax_top)

        merged["diff"] = merged["NWE"] - merged["MED"]
        ax_bot.plot(merged["Date"], merged["diff"], color=self.COLORS["PRICE"], linewidth=self.LW)
        self._zero_line(ax_bot)
        ax_bot.set(xlabel="Date", ylabel="NWE − Med (USD/bbl)")
        ax_bot.set_title("Regional differential — positive = NWE premium", loc="left", fontsize=10)
        self._format_xaxis(ax_bot)

        r = merged[["NWE", "MED"]].dropna().corr().iloc[0, 1]
        dd = merged[["NWE", "MED"]].diff().dropna().corr().iloc[0, 1]
        mean_diff = merged["diff"].mean()
        print(f"Level corr (NWE, Med): {r:+.3f}")
        print(f"ΔLevel corr          : {dd:+.3f}")
        print(f"Mean NWE − Med       : {mean_diff:+.2f} USD/bbl")

        fig.suptitle(
            "ULSD refining margin — NWE vs Med",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=0.995,
        )
        # Restore
        self.build(SLATE=orig_slate, REGION=orig_region)
        return self._finalize(fig, "CRACK_MED_VS_NWE")

    def chart_all_slates(self):
        """Side-by-side time series for every NWE slate."""
        orig_slate, orig_region = self.slate, self.region
        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        palette = self.COLORS["CYCLE"]
        for i, slate in enumerate(self.SLATES):
            self.build(SLATE=slate, REGION="NWE")
            ax.plot(
                self.df["Date"],
                self.df["margin"],
                color=palette[i % len(palette)],
                linewidth=self.LW,
                alpha=self.A["PRIMARY"],
                label=slate,
            )
        self._zero_line(ax)
        ax.set(xlabel="Date", ylabel="Margin (USD/bbl)")
        ax.set_title("NWE refining margins — all slates", loc="left")
        ax.legend(loc="upper left")
        self._format_xaxis(ax)
        self.build(SLATE=orig_slate, REGION=orig_region)
        return self._finalize(fig, "CRACK_ALL_SLATES")

    def chart_seasonal(self, SLATE=None):
        """Monthly seasonality of the margin — mean by calendar month (IS window
        only, so OOS 2025-26 distortion doesn't drive the pattern)."""
        slate = SLATE or self.slate
        df = self.df.copy()
        df = df[df["is_oos"] == "IS"]
        df["month"] = df["Date"].dt.month
        seasonal = df.groupby("month")["margin"].agg(["mean", "std", "count"]).reset_index()

        fig, ax = plt.subplots(figsize=self.SIZES["WIDE"])
        ax.bar(
            seasonal["month"],
            seasonal["mean"],
            yerr=seasonal["std"],
            color=self.COLORS["MARGIN"],
            alpha=0.85,
            edgecolor="white",
            capsize=4,
        )
        ax.axhline(
            df["margin"].mean(),
            color=self.COLORS["REF"],
            linestyle="--",
            linewidth=0.8,
            label=f"IS mean = {df['margin'].mean():.2f}",
        )
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        )
        ax.set(xlabel="Calendar month", ylabel=f"{slate} margin (USD/bbl)")
        ax.set_title(f"Seasonality — {slate}/{self.region} (IS window only)", loc="left")
        ax.legend(loc="upper left")
        return self._finalize(fig, "CRACK_SEASONAL")

    def chart_executive_dashboard(self, FA=None, RA=None):
        """Single 4-panel dashboard for the Executive Summary: refining margin ·
        SPR level · US utilisation · diesel-over-gasoline premium.

        Accepts sibling FundamentalsAnalysis and RegionalAnalysis instances so
        the dashboard can compose numbers from all three classes without the
        notebook carrying plotting code."""
        import matplotlib.pyplot as _plt

        fig, axes = _plt.subplots(2, 2, figsize=self.SIZES["DASHBOARD"])

        # Panel 1 — refining margin
        ax = axes[0, 0]
        ax.plot(self.df["Date"], self.df["margin"], color=self.COLORS["CRACK"], linewidth=1.2)
        ax.axhline(
            self.df["margin"].mean(), color=self.COLORS["REF"], linestyle="--", linewidth=0.7
        )
        ax.set_title(
            f"NWE {self.slate} refining margin  ·  mean {self.df['margin'].mean():.1f} USD/bbl",
            loc="left",
            fontsize=10,
        )
        ax.set_ylabel("USD/bbl")
        self._format_xaxis(ax)

        # Panel 2 — SPR level
        if FA is not None:
            ax = axes[0, 1]
            spr = FA.us_stocks[FA.us_stocks["Date"] >= "2021-01-01"]
            ax.plot(
                spr["Date"], spr["SPR_Crude_Stocks_Mbbl"], color=FA.COLORS["SPR"], linewidth=1.3
            )
            ax.set_title(
                f"SPR crude stocks  ·  latest {spr.iloc[-1]['SPR_Crude_Stocks_Mbbl']:.0f} Mbbl",
                loc="left",
                fontsize=10,
            )
            ax.set_ylabel("Mbbl")
            FA._format_xaxis(ax)

        # Panel 3 — US utilisation
        if FA is not None:
            ax = axes[1, 0]
            util = FA.util[FA.util["Date"] >= "2019-01-01"]
            ax.plot(
                util["Date"],
                util["Refinery_Utilization_Pct"],
                color=FA.COLORS["PRICE"],
                linewidth=1.2,
                marker="o",
                markersize=3,
            )
            ax.set_title(
                f"US refinery utilisation  ·  "
                f"latest {util.iloc[-1]['Refinery_Utilization_Pct']:.1f}%",
                loc="left",
                fontsize=10,
            )
            ax.set_ylabel("%")
            FA._format_xaxis(ax)

        # Panel 4 — diesel-over-gasoline premium
        if RA is not None:
            ax = axes[1, 1]
            c = RA.cracks[["Date", "Brent_ULSD_NWE_Crack", "Brent_EBOB_Crack"]].dropna()
            c["prem"] = c["Brent_ULSD_NWE_Crack"] - c["Brent_EBOB_Crack"]
            ax.plot(c["Date"], c["prem"], color=RA.COLORS["MARGIN"], linewidth=1.2)
            ax.axhline(c["prem"].mean(), color=RA.COLORS["REF"], linestyle="--", linewidth=0.7)
            ax.set_title(
                f"Diesel − gasoline crack premium  ·  mean {c['prem'].mean():+.1f} USD/bbl",
                loc="left",
                fontsize=10,
            )
            ax.set_ylabel("USD/bbl")
            RA._format_xaxis(ax)

        fig.suptitle(
            "Market dashboard — 45-second read",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.002,
        )
        return self._finalize(fig, "EXEC_DASHBOARD")

    def pnl_scaling(self, REFINERY_KBPD=100, UTILISATION=0.90, PRINT=True):
        """Convert the current crack level into a physical refinery P&L.
        Useful quick-check: 'is today's margin worth running the refinery?'.

        A 100 kbpd refinery at 90% utilisation produces 90 kbd of throughput.
        At a 3-2-1 crack of X USD/bbl, daily gross margin = 90 000 · X USD.
        This ignores opex, hedging costs, taxes — it's the crude-to-products
        gross margin, the same number traders quote as 'the crack' × volume."""
        latest_crack = self.df.iloc[-1]["margin"]
        mean_crack = self.df["margin"].mean()
        p95_crack = self.df["margin"].quantile(0.95)
        p05_crack = self.df["margin"].quantile(0.05)

        kbd = REFINERY_KBPD * UTILISATION
        daily_latest = kbd * 1000 * latest_crack  # $ / day
        daily_mean = kbd * 1000 * mean_crack
        annual_latest = daily_latest * 365 / 1e6  # MUSD / year
        annual_mean = daily_mean * 365 / 1e6

        if PRINT:
            print(
                f"Volumetric P&L — {REFINERY_KBPD} kbpd refinery @ {UTILISATION * 100:.0f}% util = {kbd:.0f} kbd throughput"
            )
            print(f"{self.slate}/{self.region} crack")
            print(
                f"   Latest ({self.df.iloc[-1]['Date'].date()}) : {latest_crack:>6.2f} USD/bbl  →  "
                f"{daily_latest / 1e6:>6.2f} MUSD/day  ({annual_latest:>6.0f} MUSD/year)"
            )
            print(
                f"   Full-sample mean             : {mean_crack:>6.2f} USD/bbl  →  "
                f"{daily_mean / 1e6:>6.2f} MUSD/day  ({annual_mean:>6.0f} MUSD/year)"
            )
            print(
                f"   95th pct (good-margin day)   : {p95_crack:>6.2f} USD/bbl  →  "
                f"{kbd * 1000 * p95_crack / 1e6:>6.2f} MUSD/day"
            )
            print(
                f"   5th pct (bad-margin day)     : {p05_crack:>6.2f} USD/bbl  →  "
                f"{kbd * 1000 * p05_crack / 1e6:>6.2f} MUSD/day"
            )
            print(
                f"Reality check: a mid-sized refinery (≈100 kbpd) at mean margin earns ≈ "
                f"${annual_mean:.0f} M/year gross — before opex (~$3-4/bbl) and hedging."
            )
        return {
            "latest_crack": latest_crack,
            "daily_latest_usd": daily_latest,
            "annual_latest_musd": annual_latest,
        }

    def chart_rolling_hedge_ratio(self, WINDOW=60):
        """Rolling OLS β of the crack on Brent (returns-on-returns). Turns the
        'cracks move when Brent moves' intuition into a sizing tool. If you're
        long 1 crack contract per barrel, β tells you how many Brent contracts
        to short to neutralise the oil-price leg.

        Mathematically: Δcrack = α + β·ΔBrent + ε, rolled over WINDOW days."""
        df = self.df[["Date", "margin", "Brent_M1_bbl"]].dropna().copy()
        df["d_crack"] = df["margin"].diff()
        df["d_brent"] = df["Brent_M1_bbl"].diff()
        df = df.dropna()

        # Rolling cov/var → β
        cov = df["d_crack"].rolling(WINDOW).cov(df["d_brent"])
        var = df["d_brent"].rolling(WINDOW).var()
        df["beta"] = cov / var
        # 95% CI via rolling σ of the residual / √(WINDOW · var(Brent))
        df["resid"] = df["d_crack"] - df["beta"] * df["d_brent"]
        se_beta = df["resid"].rolling(WINDOW).std() / (var * WINDOW).pow(0.5)
        df["beta_lo"] = df["beta"] - 1.96 * se_beta
        df["beta_hi"] = df["beta"] + 1.96 * se_beta

        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        ax.fill_between(
            df["Date"],
            df["beta_lo"],
            df["beta_hi"],
            color=self.COLORS["PRICE"],
            alpha=0.20,
            label="95% CI",
        )
        ax.plot(
            df["Date"],
            df["beta"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW + 0.3,
            label=f"Rolling {WINDOW}-day β",
        )
        mean_beta = df["beta"].mean()
        ax.axhline(
            mean_beta,
            color=self.COLORS["REF"],
            linestyle=":",
            linewidth=0.8,
            label=f"Mean β = {mean_beta:+.3f}",
        )
        self._zero_line(ax)
        ax.set(xlabel="Date", ylabel=f"β (Δ{self.slate} crack vs ΔBrent)")
        ax.set_title(
            f"Rolling hedge ratio — {self.slate}/{self.region} crack vs Brent M1", loc="left"
        )
        ax.legend(loc="upper left", fontsize=9)
        self._format_xaxis(ax)
        self._add_event_markers(ax)

        latest = df.iloc[-1]
        print(
            f"Rolling β ({WINDOW}d): latest {latest['beta']:+.3f}  "
            f"[95% CI {latest['beta_lo']:+.3f}, {latest['beta_hi']:+.3f}]"
        )
        print(f"Full-sample mean β: {mean_beta:+.3f}  (σ = {df['beta'].std():.3f})")
        if latest["beta"] * mean_beta > 0 and abs(latest["beta"] / mean_beta) > 2:
            print(
                f"⚠ current β is {latest['beta'] / mean_beta:.1f}× the mean — static hedges mis-size"
            )
        return self._finalize(fig, "CRACK_ROLL_HEDGE")

    def chart_rolling_hedge_ratio_by_regime(self, WINDOW=60, ANCHOR_COMMODITY="LSGO"):
        """Rolling hedge β conditioned on Project 1's LSGO forward-curve regime.
        This closes the Project 1 ↔ Project 2 loop: regime flag from the curves
        engine conditions the crack hedge β, so a trader sees *when* their
        static β will mis-size.

        Imports ForwardCurveAnalysis from the sibling forward_curves_analysis
        project, re-derives regime labels on the LSGO M1-M6 spread via the same
        CDF calibration, and buckets the rolling β time series by regime state
        on each date. Outputs a time-series chart coloured by regime + a
        per-regime summary table.
        """
        import importlib.util as _iu
        from pathlib import Path as _Path

        # Load sibling project engine by file path to avoid `src` name clash
        p1_path = (
            _Path(__file__).resolve().parent.parent.parent
            / "forward_curves_analysis"
            / "src"
            / "forward_curve_analytics.py"
        )
        spec = _iu.spec_from_file_location("fca_engine", p1_path)
        _mod = _iu.module_from_spec(spec)
        spec.loader.exec_module(_mod)
        ForwardCurveAnalysis = _mod.ForwardCurveAnalysis
        p1 = p1_path.parent.parent

        # Project 1: get LSGO regime
        fca = (
            ForwardCurveAnalysis(
                COMMODITY=ANCHOR_COMMODITY, CONFIG_PATH=str(p1 / "config.yaml"), SAVE_FIGURES=False
            )
            .load()
            .build()
        )
        fca.calibrate_thresholds(IS_END="2024-12-31")
        regime = fca.df_rolling[["Date", "Regime"]].rename(columns={"Regime": "lsgo_regime"})

        # Project 2: rolling β
        df = self.df[["Date", "margin", "Brent_M1_bbl"]].dropna().copy()
        df["d_crack"] = df["margin"].diff()
        df["d_brent"] = df["Brent_M1_bbl"].diff()
        df = df.dropna()
        cov = df["d_crack"].rolling(WINDOW).cov(df["d_brent"])
        var = df["d_brent"].rolling(WINDOW).var()
        df["beta"] = cov / var

        # Merge regime on date (forward-fill, since regime updates daily)
        df = df.merge(regime, on="Date", how="left")
        df["lsgo_regime"] = df["lsgo_regime"].ffill().fillna("Unknown")

        # Per-regime summary
        grouped = df.groupby("lsgo_regime")["beta"].agg(["mean", "std", "count"])
        print(f"Rolling β ({WINDOW}d) conditioned on {ANCHOR_COMMODITY} regime:")
        print(grouped.to_string())

        # Chart — colour points by regime state
        fig, ax = plt.subplots(figsize=self.SIZES["STANDARD"])
        regime_colors = self.COLORS.get("REGIMES", {})
        for regime_name, sub in df.groupby("lsgo_regime"):
            if len(sub.dropna(subset=["beta"])) < 2:
                continue
            clr = regime_colors.get(
                regime_name, regime_colors.get(regime_name.replace("-", "_"), "#888")
            )
            # Some regimes are like 'Crisis-High', fall back to grey
            if isinstance(clr, dict):
                clr = "#888"
            ax.scatter(
                sub["Date"],
                sub["beta"],
                color=clr,
                s=10,
                alpha=0.7,
                label=f"{regime_name} (n={len(sub.dropna(subset=['beta']))}, "
                f"μ={sub['beta'].mean():+.2f})",
            )

        mean_beta = df["beta"].mean()
        ax.axhline(
            mean_beta,
            color=self.COLORS["REF"],
            linestyle=":",
            linewidth=0.8,
            label=f"Overall mean β = {mean_beta:+.2f}",
        )
        self._zero_line(ax)
        ax.set(xlabel="Date", ylabel=f"β (Δ{self.slate} crack vs ΔBrent)")
        ax.set_title(
            f"Rolling {WINDOW}-day β — conditioned on {ANCHOR_COMMODITY} "
            f"curve regime (Project 1 → Project 2 link)",
            loc="left",
        )
        ax.legend(loc="upper left", fontsize=8)
        self._format_xaxis(ax)

        # Key finding: is β regime-dependent?
        crisis_mask = df["lsgo_regime"].str.contains("Crisis", na=False)
        normal_mask = df["lsgo_regime"] == "Normal"
        if crisis_mask.any() and normal_mask.any():
            b_cri = df.loc[crisis_mask, "beta"].mean()
            b_nor = df.loc[normal_mask, "beta"].mean()
            ratio = b_cri / b_nor if b_nor else float("nan")
            print(f"β (Crisis regime) = {b_cri:+.3f}")
            print(f"β (Normal regime) = {b_nor:+.3f}")
            print(
                f"Crisis/Normal ratio = {ratio:.2f}× — "
                f"{'REGIME-DEPENDENT — static hedges mis-size' if abs(ratio) > 1.5 else 'regime-invariant'}"
            )

        key = "CRACK_ROLL_HEDGE_REGIME" if "CRACK_ROLL_HEDGE_REGIME" in self.FILES else None
        return self._finalize(fig, key) if key else fig

    def chart_hmm_regime(self, N_STATES=2):
        """Gaussian HMM on the daily margin series. Mirrors Project 1's
        `chart_hmm_regime`. Gives probabilistic regime labels vs the
        CDF classifier's hard labels — useful when a print sits on the
        boundary.

        Model-selection note (why 2 states): BIC is reported below for K ∈
        {2, 3, 4}. BIC penalises log-likelihood by K · log(n) × params-per-state,
        so it strictly prefers parsimony. We pick 2 because the data is
        near-unimodal pre-2025 and the OOS regime emerges cleanly as one
        additional state — adding a 3rd state over-fits on 16 months of OOS.
        """
        try:
            from hmmlearn.hmm import GaussianHMM
        except ImportError:
            print("hmmlearn not available — `pip install hmmlearn`")
            return None
        df = self.df[["Date", "margin"]].dropna().copy()
        X = df[["margin"]].values

        # Model selection — report BIC for K ∈ {2, 3, 4}
        import numpy as _np

        n_obs = len(X)
        print("HMM model selection (lower BIC is better):")
        bic_by_k = {}
        for k in (2, 3, 4):
            m = GaussianHMM(n_components=k, covariance_type="full", n_iter=200, random_state=0)
            try:
                m.fit(X)
                ll = m.score(X)
                n_params = k * 2 + k * (k - 1) + (k - 1)
                bic = -2 * ll + n_params * _np.log(n_obs)
                bic_by_k[k] = bic
                print(f"  K={k}  log-lik={ll:+.1f}  params={n_params}  BIC={bic:+.1f}")
            except Exception as e:
                print(f"  K={k}  fit failed: {e}")
        if bic_by_k:
            best_k = min(bic_by_k, key=bic_by_k.get)
            print(
                f"  → Lowest BIC at K={best_k}; adding states over-fits on "
                f"the 16-month OOS window. Chart below uses N_STATES={N_STATES}."
            )

        model = GaussianHMM(
            n_components=N_STATES, covariance_type="full", n_iter=200, random_state=0
        )
        model.fit(X)
        df["state"] = model.predict(X)
        # Sort states by mean — low→high
        state_means = [model.means_[s][0] for s in range(N_STATES)]
        order = sorted(range(N_STATES), key=lambda s: state_means[s])
        relabel = {old: new for new, old in enumerate(order)}
        df["state"] = df["state"].map(relabel)
        sorted_means = [state_means[s] for s in order]

        self._hmm_model = model
        self._hmm_order = order

        fig, (ax_ts, ax_st) = plt.subplots(
            2,
            1,
            figsize=(self.SIZES["STANDARD"][0], self.SIZES["STANDARD"][1] + 3),
            sharex=True,
            gridspec_kw={"height_ratios": [2, 1], "hspace": 0.2},
        )

        palette = [self.COLORS["MARGIN"], self.COLORS["CRACK"], self.COLORS["VOL"]]
        ax_ts.plot(
            df["Date"], df["margin"], color=self.COLORS["PRICE"], linewidth=self.LW, alpha=0.8
        )
        for s in range(N_STATES):
            mask = df["state"] == s
            ax_ts.scatter(
                df.loc[mask, "Date"],
                df.loc[mask, "margin"],
                color=palette[s % len(palette)],
                s=8,
                alpha=0.55,
                label=f"State {s}: μ={sorted_means[s]:.1f} USD/bbl",
            )
        ax_ts.set(ylabel=f"{self.slate} margin (USD/bbl)")
        ax_ts.set_title(
            f"HMM regimes on {self.slate}/{self.region} crack — {N_STATES} states", loc="left"
        )
        ax_ts.legend(loc="upper left", fontsize=9)

        ax_st.plot(
            df["Date"],
            df["state"],
            color=self.COLORS["REF"],
            linewidth=self.LW,
            drawstyle="steps-post",
        )
        ax_st.set(xlabel="Date", ylabel="state", yticks=list(range(N_STATES)))
        self._format_xaxis(ax_st)

        for s in range(N_STATES):
            share = (df["state"] == s).mean() * 100
            print(f"State {s}: {share:.1f}% of days, μ={sorted_means[s]:+.2f} USD/bbl")

        return self._finalize(fig, "CRACK_HMM_REGIME")

    def forecast_next_day_regime(self, HORIZON=5):
        """Given today's HMM state, compute regime probabilities for +1..+HORIZON
        days via the transition matrix. Requires `chart_hmm_regime` first."""
        if not hasattr(self, "_hmm_model"):
            print("Run chart_hmm_regime() first to fit the HMM.")
            return None
        model = self._hmm_model
        order = self._hmm_order
        n = model.n_components
        # Reorder transition matrix to low→high
        perm = [order.index(s) for s in range(n)]  # how to map old→new
        T_raw = model.transmat_
        # new[i][j] = P(new_j | new_i) = P(old_order[i] → old_order[j])
        T = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                T[i, j] = T_raw[order[i], order[j]]
        # Today's state
        X = self.df[["margin"]].dropna().values
        last_state_old = int(model.predict(X)[-1])
        last_state = perm[last_state_old]
        p = np.zeros(n)
        p[last_state] = 1.0
        latest_date = self.df.iloc[-1]["Date"]
        print(f"HMM next-day regime forecast — as of {latest_date.date()}:")
        "  ·  ".join([f"P(state{s})=_" for s in range(n)]).replace("_", "{:.3f}")
        for h in range(HORIZON + 1):
            tag = "today" if h == 0 else f"+{h}d  "
            print(f"  {tag:6s} " + "  ·  ".join([f"P(state{s})={p[s]:.3f}" for s in range(n)]))
            p = p @ T
        return p

    def chart_seasonal_bootstrap_ci(self, SLATE=None, N_BOOT=2000):
        """Seasonality with 95% bootstrap CIs — honest given ~5-6 obs per
        calendar month (t-based CIs would be overconfident)."""
        slate = SLATE or self.slate
        df = self.df[self.df["is_oos"] == "IS"].copy()
        df["month"] = df["Date"].dt.month
        # Collapse to monthly means (one obs per year × month) so bootstrap
        # resamples independent annual observations.
        df["year"] = df["Date"].dt.year
        monthly = df.groupby(["year", "month"], as_index=False)["margin"].mean()

        rng = np.random.default_rng(0)
        rows = []
        for m in range(1, 13):
            obs = monthly.loc[monthly["month"] == m, "margin"].values
            if len(obs) < 2:
                continue
            boot_means = np.array(
                [rng.choice(obs, size=len(obs), replace=True).mean() for _ in range(N_BOOT)]
            )
            rows.append(
                {
                    "month": m,
                    "mean": obs.mean(),
                    "lo95": np.quantile(boot_means, 0.025),
                    "hi95": np.quantile(boot_means, 0.975),
                    "n": len(obs),
                }
            )
        out = pd.DataFrame(rows)

        fig, ax = plt.subplots(figsize=self.SIZES["WIDE"])
        yerr = np.vstack([out["mean"] - out["lo95"], out["hi95"] - out["mean"]])
        ax.bar(
            out["month"],
            out["mean"],
            yerr=yerr,
            color=self.COLORS["MARGIN"],
            alpha=0.85,
            edgecolor="white",
            capsize=5,
            ecolor=self.COLORS["REF"],
            label=f"Monthly mean ± 95% bootstrap CI (n≈{out['n'].mean():.0f}/month)",
        )
        full_mean = df["margin"].mean()
        ax.axhline(
            full_mean,
            color=self.COLORS["REF"],
            linestyle="--",
            linewidth=0.8,
            label=f"IS mean = {full_mean:.2f}",
        )
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        )
        ax.set(xlabel="Calendar month", ylabel=f"{slate} margin (USD/bbl)")
        ax.set_title(
            f"Seasonality with 95% bootstrap CIs — {slate}/{self.region} (IS only)", loc="left"
        )
        ax.legend(loc="upper left", fontsize=9)

        crosses_zero = ((out["lo95"] < 0) & (out["hi95"] > 0)).sum()
        ci_widths = (out["hi95"] - out["lo95"]).mean()
        print(
            f"Bootstrap CIs:  {crosses_zero}/12 months span zero · "
            f"mean CI width = {ci_widths:.1f} USD/bbl · "
            f"n ≈ {out['n'].mean():.0f} obs/month — "
            f"treat any month-to-month ordering with caution."
        )
        return self._finalize(fig, "CRACK_SEASONAL_CI")

    def chart_opec_crosscheck(self):
        """Cross-check our computed Brent-ULSD NWE crack against OPEC ASB 2025
        Rotterdam gasoil 10ppm crack — does the long-history OPEC series
        anchor our Platts-based calc? Resample ours to annual mean."""
        opec = self.loader.opec_t76_cracks()
        # Rotterdam gasoil 10ppm vs Brent — the closest analogue to our Brent-ULSD NWE
        mask = (opec["region"] == "Rotterdam crack spread vs Brent") & (
            opec["product"].str.contains("10ppm|0.05", regex=True)
        )
        rot = opec[mask].sort_values("year")[["year", "value_usd_bbl"]]

        # Our computed series — from the pre-built cracks_clean CSV
        ours = self.loader.cracks_clean()[["Date", "Brent_ULSD_NWE_Crack"]].dropna()
        ours["year"] = ours["Date"].dt.year
        ours_ann = ours.groupby("year", as_index=False)["Brent_ULSD_NWE_Crack"].mean()

        fig, (ax_ts, ax_sc) = plt.subplots(
            1,
            2,
            figsize=(self.SIZES["STANDARD"][0] + 2, self.SIZES["SQUARE"][1]),
            gridspec_kw={"width_ratios": [2, 1], "wspace": 0.3},
        )

        ax_ts.plot(
            rot["year"],
            rot["value_usd_bbl"],
            color=self.COLORS["CRACK"],
            linewidth=self.LW + 0.2,
            marker="o",
            markersize=4,
            label="OPEC ASB — Rotterdam gasoil 10ppm vs Brent",
        )
        ax_ts.plot(
            ours_ann["year"],
            ours_ann["Brent_ULSD_NWE_Crack"],
            color=self.COLORS["PRICE"],
            linewidth=self.LW + 0.2,
            marker="s",
            markersize=4,
            label="Our Platts-derived Brent-ULSD NWE crack (annual mean)",
        )
        self._zero_line(ax_ts)
        ax_ts.set(xlabel="Year", ylabel="Crack (USD/bbl)")
        ax_ts.set_title(
            "Cross-check — OPEC ASB vs our computed NWE ULSD crack",
            loc="left",
            fontsize=10,
            fontweight="normal",
        )
        ax_ts.legend(loc="upper left", fontsize=9)
        ax_ts.grid(True, alpha=0.3)

        # Overlap scatter (years where both exist)
        merged = rot.merge(ours_ann, on="year", how="inner")
        if len(merged) >= 2:
            r = merged[["value_usd_bbl", "Brent_ULSD_NWE_Crack"]].corr().iloc[0, 1]
            ax_sc.scatter(
                merged["value_usd_bbl"],
                merged["Brent_ULSD_NWE_Crack"],
                s=40,
                alpha=self.A["SCATTER"],
                color=self.COLORS["SCATTER"],
                edgecolor="white",
            )
            lo = min(merged["value_usd_bbl"].min(), merged["Brent_ULSD_NWE_Crack"].min())
            hi = max(merged["value_usd_bbl"].max(), merged["Brent_ULSD_NWE_Crack"].max())
            ax_sc.plot(
                [lo, hi],
                [lo, hi],
                color=self.COLORS["REF"],
                linestyle="--",
                linewidth=0.8,
                label="y = x",
            )
            mean_delta = (merged["Brent_ULSD_NWE_Crack"] - merged["value_usd_bbl"]).mean()
            ax_sc.set(
                xlabel="OPEC ASB (USD/bbl)",
                ylabel="Ours (USD/bbl)",
                title=f"Overlap years · n={len(merged)} · mean offset {mean_delta:+.1f}/bbl",
            )
            ax_sc.legend(loc="upper left", fontsize=8)
            ax_sc.grid(True, alpha=0.3)
            print(
                f"OPEC ASB vs ours — {len(merged)} overlap years; "
                f"r = {r:+.3f}, "
                f"mean Δ = {(merged['Brent_ULSD_NWE_Crack'] - merged['value_usd_bbl']).mean():+.2f} USD/bbl"
            )
        else:
            ax_sc.text(
                0.5, 0.5, "Insufficient overlap years", ha="center", transform=ax_sc.transAxes
            )

        fig.suptitle(
            "Crack spread — external cross-check (OPEC ASB 1983+)",
            x=0.01,
            ha="left",
            fontsize=13,
            fontweight="bold",
            y=1.02,
        )
        return self._finalize(fig, "CRACK_OPEC_CROSSCHECK")
