"""Physical cargo arbitrage engine — parametric.

`CargoArb` takes a fully-specified cargo decision (origin, destination,
vessel, grade, freight, forward prices with explicit premium/discount
adjustments) and produces a structured P&L:

    gross_spread = (sell_price + sell_premium_discount)
                 - (buy_price  + buy_premium_discount)

    net_arb = gross_spread
            − freight
            − port_costs
            − canal_tolls
            − financing
            − insurance
            − demurrage_risk
            − broker_commission

All inputs are user-provided at construction; the engine looks up vessel
speed, grade density, port costs, canal tolls and Worldscale flat rates
from `config.yaml`. Voyage days are computed from `distance_nm` and laden
speed, not hard-coded. A `PRESETS` section in the config lets notebooks
instantiate named combinations (e.g. `BSEA_MED_AFRA`) without listing
every argument.

Forward-price convention: the buy and sell prices are FORWARD prints
(not spot). Typical pattern — buy at origin FOB on month-M forward,
sell at destination CIF on month-(M+1) or (M+2) forward. The user
chooses the timing; the engine does not advance dates on its own.

The model is NOT live. The date of the price prints is held in
`config.RUN_METADATA.DATE_OF_PRICES` and should be cited explicitly
wherever results are presented.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


# === Path constants ==========================================================
PAA_ROOT       = Path(__file__).resolve().parent.parent
PORTFOLIO_ROOT = PAA_ROOT.parent
PLOT_CONFIG    = PORTFOLIO_ROOT / 'plot_config.yaml'
MAJOR_DATES    = PORTFOLIO_ROOT / 'major_dates.yaml'
DEFAULT_CONFIG = PAA_ROOT / 'config.yaml'

logger = logging.getLogger(__name__)


def load_config(path: Optional[str] = None) -> dict:
    """Load per-project config, merging portfolio-wide PLOT block."""
    with open(path or DEFAULT_CONFIG) as fh:
        cfg = yaml.safe_load(fh)
    if PLOT_CONFIG.exists():
        with open(PLOT_CONFIG) as fh:
            shared = yaml.safe_load(fh)
        merged = {**shared.get('PLOT', {}), **cfg.get('PLOT', {})}
        cfg['PLOT'] = merged
    return cfg


# =============================================================================
# CargoArb — parametric single-cargo calculator + chart methods.
# =============================================================================

@dataclass
class CargoArb:
    """One cargo, parametric end-to-end P&L.

    Required:
        origin_port   — e.g. 'Novorossiysk' (must be in config PORTS)
        dest_port     — e.g. 'Augusta'
        vessel        — 'MR' | 'LR1' | 'LR2' | 'Aframax' | 'Suezmax' | 'VLCC'
        grade         — e.g. 'Urals' (must be in config GRADE_SPECS)
        ws_rate       — Worldscale rate for the voyage

    Forward prices (USD/bbl) — pick ONE of two ways to set the buy/sell legs:

        (a) Recommended: specify `buy_product` + `buy_month` and the engine
            looks up the most recent forward print from config
            FORWARD_PRICES_USD_BBL. Same for sell. Then add a regional
            premium/discount via `buy_premium_discount` / `sell_premium_discount`.

            Example for a USG → NWE ULSD product cargo:
                buy_product='ULSD',  buy_month='FOB_ARA',  buy_premium_discount=0.0
                sell_product='ULSD', sell_month='CIF_NWE', sell_premium_discount=0.0

            Example for a Brent paper hedge of a crude cargo:
                buy_product='Brent', buy_month='M1', buy_premium_discount=0.0
                sell_product='Brent', sell_month='M2', sell_premium_discount=0.0

        (b) Power user: pass `buy_price` and `sell_price` directly as floats.
            Useful for backtests or when the price you want isn't in config.

    Regional premium/discount:
        + = premium, − = discount, default 0. Note: large structural discounts
        (e.g. -$15 to -$30 on Urals during freight stress) are accessible only
        to trading houses with established Russian-flow operations and
        compliance carve-outs. Default is 0 — assume the desk pays / receives
        the published forward print unless they have a documented basis.

    Optional:
        cargo_mt              — explicit cargo tonnage; if None, = vessel_dwt × utilization
        capacity_utilization  — 0..1, fraction of nameplate DWT loaded (default 1.0)
        flat_rate             — explicit USD/MT at WS 100; if None, lookup by ws_flat_key
        ws_flat_key           — key in config WS_FLAT_RATES_2026 for auto-lookup
        distance_nm           — explicit distance; if None, lookup from config DISTANCES_NM
        speed_kt              — explicit laden speed; if None, use vessel default
        canals                — list of canal names (empty default)
        financing_days        — explicit; if None, computed from voyage math
        demurrage_days        — risk-weighted delay expectation (default 2)
        war_risk_uplift_bps   — insurance uplift beyond base (Hormuz, Red Sea, …)
        buy_timing, sell_timing, date_of_prices — metadata strings for reporting
    """
    # Cargo specification
    origin_port: str
    dest_port:   str
    vessel:      str
    grade:       str

    # Freight
    ws_rate:   float

    # Prices: either (product, month) lookup from config FORWARD_PRICES, or
    # explicit float price. At least one path must be specified per leg.
    buy_product:  Optional[str]   = None    # e.g. 'Brent', 'WTI', 'LSGO', 'ULSD', 'Jet', 'EBOB', 'Dated_Brent'
    buy_month:    Optional[str]   = None    # e.g. 'M1', 'M2', 'M3' for futures; 'CIF_Med', 'CIF_NWE', 'FOB_ARA' for physical
    sell_product: Optional[str]   = None
    sell_month:   Optional[str]   = None

    # Optional explicit price overrides (skip the lookup)
    buy_price:    Optional[float] = None
    sell_price:   Optional[float] = None

    # Regional premium / discount on each side. Default 0 — only set
    # non-zero when the trader has a documented basis (commercial agreement,
    # established flow, Urals-cap carve-out for non-G7 buyers, etc.). A −$15
    # / −$30 discount is real for trading houses with the operation; not
    # for a generic G7-linked desk.
    buy_premium_discount:  float = 0.0
    sell_premium_discount: float = 0.0

    # Volume
    cargo_mt:             Optional[float] = None
    capacity_utilization: float = 1.0

    # Freight lookup
    flat_rate:     Optional[float] = None
    ws_flat_key:   Optional[str]   = None

    # Voyage
    distance_nm:  Optional[float] = None
    speed_kt:     Optional[float] = None
    canals:       tuple = ()

    # Cost toggles
    financing_days:          Optional[float] = None
    demurrage_days:          Optional[float] = None
    war_risk_uplift_bps:     float = 0.0

    # Metadata (reporting, no effect on math)
    buy_timing:      Optional[str] = None
    sell_timing:     Optional[str] = None
    date_of_prices:  Optional[str] = None

    # Infrastructure
    save_figures: bool = True
    config:       Optional[dict] = None
    _computed:    dict = field(default_factory=dict, init=False, repr=False)

    # --- setup ---------------------------------------------------------------

    def __post_init__(self):
        cfg = self.config if self.config is not None else load_config()
        self._cfg      = cfg
        self._analysis = cfg['ANALYSIS']
        self._meta     = cfg.get('RUN_METADATA', {})

        # Resolve buy / sell prices from (product, month) lookup if needed.
        if self.buy_price is None:
            if self.buy_product is None or self.buy_month is None:
                raise ValueError(
                    "Specify either (buy_product + buy_month) for forward-table "
                    "lookup, or pass buy_price as a float.")
            key, price = self._resolve_forward_price(self.buy_product, self.buy_month)
            self.buy_price   = price
            if self.buy_timing is None:
                self.buy_timing = key
        if self.sell_price is None:
            if self.sell_product is None or self.sell_month is None:
                raise ValueError(
                    "Specify either (sell_product + sell_month) for forward-table "
                    "lookup, or pass sell_price as a float.")
            key, price = self._resolve_forward_price(self.sell_product, self.sell_month)
            self.sell_price  = price
            if self.sell_timing is None:
                self.sell_timing = key

        # Vessel
        if self.vessel not in cfg['VESSEL_SPECS']:
            raise KeyError(f"Unknown vessel {self.vessel!r}; "
                           f"known: {list(cfg['VESSEL_SPECS'])}")
        self._vessel = cfg['VESSEL_SPECS'][self.vessel]

        # Grade
        if self.grade not in cfg['GRADE_SPECS']:
            raise KeyError(f"Unknown grade {self.grade!r}; "
                           f"known: {list(cfg['GRADE_SPECS'])}")
        self._grade   = cfg['GRADE_SPECS'][self.grade]
        self.density  = self._grade['density']     # bbl per MT, public attribute

        # Volume
        if self.cargo_mt is None:
            self.cargo_mt = self._vessel['dwt_kt'] * 1000 * self.capacity_utilization
        else:
            self.capacity_utilization = self.cargo_mt / (self._vessel['dwt_kt'] * 1000)

        # Freight flat rate
        if self.flat_rate is None:
            if self.ws_flat_key is None or self.ws_flat_key not in cfg['WS_FLAT_RATES_2026']:
                raise ValueError(
                    f"No flat_rate provided and ws_flat_key={self.ws_flat_key!r} "
                    f"not in config WS_FLAT_RATES_2026. Pass flat_rate= explicitly.")
            self.flat_rate = cfg['WS_FLAT_RATES_2026'][self.ws_flat_key]

        # Distance + speed
        if self.distance_nm is None:
            key1 = f'{self.origin_port}_{self.dest_port}'
            key2 = f'{self.dest_port}_{self.origin_port}'
            d = cfg['DISTANCES_NM'].get(key1) or cfg['DISTANCES_NM'].get(key2)
            if d is None:
                raise ValueError(
                    f"No distance for {self.origin_port} → {self.dest_port} "
                    f"in DISTANCES_NM. Pass distance_nm= explicitly.")
            self.distance_nm = d
        if self.speed_kt is None:
            self.speed_kt = self._vessel['laden_speed_kt']

        # Voyage days
        self.steam_days     = self.distance_nm / (self.speed_kt * 24.0)
        self.port_stay_days = self._vessel['days_load_disch']
        self.laycan_days    = self._analysis['DEFAULT_LAYCAN_DAYS']
        self.voyage_days    = self.steam_days + self.port_stay_days + self.laycan_days
        if self.financing_days is None:
            self.financing_days = self.voyage_days
        if self.demurrage_days is None:
            self.demurrage_days = self._analysis['DEFAULT_DEMURRAGE_DAYS']

        # Styling (Chartable-mixin pattern)
        plot = cfg['PLOT']
        self.COLORS   = plot['COLORS']
        self.SIZES    = {k: tuple(v) for k, v in plot['SIZES'].items()}
        self.LW       = plot['LINEWIDTH']
        self.A        = plot['ALPHA']
        self.SAVE_OPTS = plot['SAVE']
        self.FILES    = cfg['CHART_FILES']
        plt.rcParams.update(plot['RCPARAMS'])
        self.OUTPUT_DIR = (PAA_ROOT / cfg['PATHS']['FIGURES']
                           if self.save_figures else None)
        if self.OUTPUT_DIR is not None:
            self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- price lookup ---------------------------------------------------------

    def _resolve_forward_price(self, product: str, month: str) -> tuple:
        """Map (product, month) → (config_key, USD/bbl price) by prefix-matching
        the config FORWARD_PRICES_USD_BBL table. Returns the shortest matching
        key so that 'Brent' + 'M1' picks 'Brent_M1_Jun26' rather than something
        longer.

        Examples:
            ('Brent',  'M1')        → ('Brent_M1_Jun26',     99.60)
            ('Brent',  'M2')        → ('Brent_M2_Jul26',     96.80)
            ('LSGO',   'M1')        → ('LSGO_M1_May26_bbl', 163.59)
            ('WTI',    'M1')        → ('WTI_M1_Jun26',       91.00)
            ('ULSD',   'CIF_Med')   → ('ULSD_CIF_Med_bbl',  188.26)
            ('ULSD',   'CIF_NWE')   → ('ULSD_CIF_NWE_bbl',  185.60)
            ('ULSD',   'FOB_ARA')   → ('ULSD_FOB_ARA_bbl',  181.61)
            ('Jet',    'CIF_NWE')   → ('Jet_CIF_NWE_bbl',   200.92)
            ('EBOB',   'FOB_ARA')   → ('EBOB_FOB_ARA_bbl',  124.25)
            ('Dated_Brent', 'spot') → ('Dated_Brent',       132.74)
        """
        fp = self._cfg.get('FORWARD_PRICES_USD_BBL', {})
        # 1. Try the exact 'Product_Month' prefix
        prefix = f'{product}_{month}'
        candidates = [(k, v) for k, v in fp.items() if k.startswith(prefix)]
        # 2. Fallback: bare product key (e.g. 'Dated_Brent' alone)
        if not candidates and not month:
            candidates = [(k, v) for k, v in fp.items() if k == product]
        if not candidates and month and (product in fp):
            candidates = [(product, fp[product])]
        if not candidates:
            raise KeyError(
                f"No forward price found for product='{product}', month='{month}'. "
                f"Looked for keys starting with '{prefix}' in "
                f"FORWARD_PRICES_USD_BBL. Available keys: {sorted(fp.keys())}")
        # Prefer the shortest match (most direct hit)
        candidates.sort(key=lambda kv: (len(kv[0]), kv[0]))
        if not isinstance(candidates[0][1], (int, float)):
            raise TypeError(
                f"Resolved key {candidates[0][0]!r} has non-numeric value "
                f"{candidates[0][1]!r}; this is a config differential not a price.")
        return candidates[0]

    # --- preset ---------------------------------------------------------------

    @classmethod
    def from_preset(cls, preset_key: str, **overrides) -> 'CargoArb':
        """Instantiate from a named PRESET in config, with any kwarg overrides.
        Example: `CargoArb.from_preset('USG_NWE_ULSD', ws_rate=120, buy_price=..., sell_price=...)`.

        Compliance note: BSEA_MED_AFRA and BSEA_MED_SUEZ presets are
        compliance-gated for G7-linked participants and are retained for
        scenario analysis only, not as executable defaults."""
        cfg = overrides.pop('config', None) or load_config()
        if preset_key not in cfg['PRESETS']:
            raise KeyError(f"Preset {preset_key!r} not in config; "
                           f"known: {list(cfg['PRESETS'])}")
        p = dict(cfg['PRESETS'][preset_key])
        p.pop('description', None)
        # Convert list → tuple for canals
        if 'canals' in p and isinstance(p['canals'], list):
            p['canals'] = tuple(p['canals'])
        p.update(overrides)
        p['config'] = cfg
        return cls(**p)

    # --- effective prices ----------------------------------------------------

    @property
    def effective_buy_price(self) -> float:
        return self.buy_price + self.buy_premium_discount

    @property
    def effective_sell_price(self) -> float:
        return self.sell_price + self.sell_premium_discount

    @property
    def gross_spread_usd_bbl(self) -> float:
        return self.effective_sell_price - self.effective_buy_price

    # --- conversion ----------------------------------------------------------

    def mt_to_bbl(self, mt: float) -> float:
        """Metric tonnes → barrels via grade density."""
        return mt * self.density

    def bbl_to_mt(self, bbl: float) -> float:
        return bbl / self.density

    # --- component costs (USD/bbl allocation) --------------------------------

    def freight_usd_mt(self) -> float:
        """Worldscale formula: freight = WS × flat_rate / 100."""
        return self.ws_rate * self.flat_rate / 100.0

    def freight_usd_bbl(self) -> float:
        return self.freight_usd_mt() / self.density

    def cargo_freight_total_usd(self) -> float:
        """Freight is paid on cargo tonnage actually on board."""
        return self.freight_usd_mt() * self.cargo_mt

    def port_costs_usd_bbl(self) -> float:
        ports = self._cfg['PORTS']
        origin_cost = ports.get(self.origin_port, {}).get('load_cost_usd', 50000)
        dest_cost   = ports.get(self.dest_port,   {}).get('load_cost_usd', 80000)
        return (origin_cost + dest_cost) / (self.cargo_mt * self.density)

    def canal_tolls_usd_bbl(self) -> float:
        tolls = self._cfg['CANAL_TOLLS']
        total = 0.0
        for canal in self.canals:
            if canal in ('Bosphorus', 'Cape_Good_Hope'):
                continue
            total += tolls.get(f'{canal}_{self.vessel}', 0.0)
        return total / (self.cargo_mt * self.density)

    def financing_usd_bbl(self) -> float:
        rate_ann = (self._analysis['SOFR_BPS']
                    + self._analysis['TRADER_SPREAD_BPS']) / 10000.0
        return self.effective_buy_price * rate_ann * (self.financing_days / 365.0)

    def insurance_usd_bbl(self) -> float:
        """Base hull / cargo insurance only (excludes additional war risk)."""
        bps = self._analysis['INSURANCE_BPS_PER_VOYAGE']
        return self.effective_buy_price * bps / 10000.0

    def awrp_usd_bbl(self) -> float:
        """Additional War Risk Premium (AWRP). Lloyd's-listed war zones
        (Hormuz, Red Sea, Black Sea, eastern Med under Iran-Israel watch)
        carry a separate underwriter premium, typically 0.25–2.0% of
        cargo value. Set via `war_risk_uplift_bps` constructor argument
        OR auto-detected when origin/destination region matches a war
        zone (see `_auto_war_zone_uplift_bps`)."""
        return self.effective_buy_price * self.war_risk_uplift_bps / 10000.0

    def _auto_war_zone_uplift_bps(self) -> float:
        """Default AWRP based on the lane's regional flags. User can always
        override by passing war_risk_uplift_bps explicitly."""
        ports = self._cfg['PORTS']
        regions = {ports.get(self.origin_port, {}).get('region'),
                   ports.get(self.dest_port, {}).get('region')}
        # Lloyd's listed war zones at snapshot date:
        if 'AG' in regions:        return 100.0   # Hormuz, AG ports
        if 'BlackSea' in regions:  return 75.0    # Russia-Ukraine war zone
        if 'WAF' in regions:       return 25.0    # piracy uplift, low
        return 0.0

    def demurrage_risk_usd_bbl(self) -> float:
        daily = self._cfg['DEMURRAGE_USD_DAY'][self.vessel]
        return daily * self.demurrage_days / (self.cargo_mt * self.density)

    def broker_commission_usd_bbl(self) -> float:
        """Broker commission on freight only — standard 2.5% of freight."""
        bps = self._analysis.get('BROKER_COMMISSION_BPS', 0)
        return self.freight_usd_bbl() * bps / 10000.0

    # --- P&L -----------------------------------------------------------------

    def pnl_waterfall(self) -> dict:
        # Auto-set AWRP if user didn't pass it but the lane is in a war zone
        if self.war_risk_uplift_bps == 0.0:
            auto = self._auto_war_zone_uplift_bps()
            if auto > 0.0:
                self.war_risk_uplift_bps = auto
        gross = self.gross_spread_usd_bbl
        f = self.freight_usd_bbl()
        p = self.port_costs_usd_bbl()
        c = self.canal_tolls_usd_bbl()
        fi = self.financing_usd_bbl()
        ins = self.insurance_usd_bbl()
        awrp = self.awrp_usd_bbl()
        dm = self.demurrage_risk_usd_bbl()
        br = self.broker_commission_usd_bbl()
        net = gross - f - p - c - fi - ins - awrp - dm - br
        cargo_bbl = self.cargo_mt * self.density
        out = {
            'gross_spread_usd_bbl':   gross,
            'freight_usd_bbl':        f,
            'port_costs_usd_bbl':     p,
            'canal_tolls_usd_bbl':    c,
            'financing_usd_bbl':      fi,
            'insurance_usd_bbl':      ins,
            'awrp_usd_bbl':           awrp,
            'demurrage_risk_usd_bbl': dm,
            'broker_comm_usd_bbl':    br,
            'net_arb_usd_bbl':        net,
            'cargo_bbl':              cargo_bbl,
            'cargo_total_pnl_usd':    net * cargo_bbl,
            'cargo_freight_total_usd': self.cargo_freight_total_usd(),
        }
        self._computed = out
        return out

    def pnl_bbl(self) -> float:
        return self.pnl_waterfall()['net_arb_usd_bbl']

    def pnl_cargo_usd(self) -> float:
        return self.pnl_waterfall()['cargo_total_pnl_usd']

    def breakeven_ws(self) -> float:
        """WS at which net P&L = 0 (linear in WS, analytical)."""
        w = self.pnl_waterfall()
        other = (w['port_costs_usd_bbl'] + w['canal_tolls_usd_bbl']
                 + w['financing_usd_bbl'] + w['insurance_usd_bbl']
                 + w['awrp_usd_bbl']
                 + w['demurrage_risk_usd_bbl'] + w['broker_comm_usd_bbl'])
        max_freight_bbl = w['gross_spread_usd_bbl'] - other
        if max_freight_bbl <= 0:
            return float('nan')
        return max_freight_bbl * self.density * 100.0 / self.flat_rate

    def breakeven_spread(self) -> float:
        w = self.pnl_waterfall()
        return (w['freight_usd_bbl'] + w['port_costs_usd_bbl']
                + w['canal_tolls_usd_bbl'] + w['financing_usd_bbl']
                + w['insurance_usd_bbl'] + w['awrp_usd_bbl']
                + w['demurrage_risk_usd_bbl']
                + w['broker_comm_usd_bbl'])

    def is_open(self, trigger: float = 0.0) -> bool:
        return self.pnl_bbl() >= trigger

    # --- sensitivity ---------------------------------------------------------

    def _clone(self, **overrides) -> 'CargoArb':
        """Make a copy with overridden params (for sensitivity sweeps)."""
        base = dict(
            origin_port=self.origin_port, dest_port=self.dest_port,
            vessel=self.vessel, grade=self.grade,
            ws_rate=self.ws_rate, flat_rate=self.flat_rate,
            buy_price=self.buy_price, sell_price=self.sell_price,
            buy_premium_discount=self.buy_premium_discount,
            sell_premium_discount=self.sell_premium_discount,
            cargo_mt=self.cargo_mt,
            capacity_utilization=self.capacity_utilization,
            distance_nm=self.distance_nm, speed_kt=self.speed_kt,
            canals=self.canals,
            financing_days=self.financing_days,
            demurrage_days=self.demurrage_days,
            war_risk_uplift_bps=self.war_risk_uplift_bps,
            save_figures=False, config=self._cfg,
        )
        base.update(overrides)
        return CargoArb(**base)

    def sensitivity_ws(self, ws_range: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(
            [{'ws': w, 'net_usd_bbl': self._clone(ws_rate=float(w)).pnl_bbl()}
             for w in ws_range])

    def sensitivity_grid(self, ws_range: np.ndarray,
                         spread_range: np.ndarray) -> pd.DataFrame:
        rows = []
        for w in ws_range:
            for s in spread_range:
                clone = self._clone(
                    ws_rate=float(w),
                    sell_price=self.buy_price + float(s),
                    sell_premium_discount=0.0,
                    buy_premium_discount=0.0)
                rows.append({'ws': w, 'spread': s, 'net_usd_bbl': clone.pnl_bbl()})
        return pd.DataFrame(rows)

    # --- chart helpers -------------------------------------------------------

    def _finalize(self, fig, file_key: Optional[str]):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            fig.tight_layout()
        if self.OUTPUT_DIR and file_key and file_key in self.FILES:
            dest = self.OUTPUT_DIR / f'{self.FILES[file_key]}.png'
            fig.savefig(dest, **self.SAVE_OPTS)
        return fig

    # --- instance charts -----------------------------------------------------

    def chart_waterfall(self, WS_STRESS_THRESHOLD: float = 180.0):
        """Waterfall chart. All cost bars red (they eat the spread). The NET
        arb bar is grey (not green) under freight stress, because a positive
        NET at WS>threshold is a clearing level, not an executable margin.

        WS_STRESS_THRESHOLD (default 180) is the rough boundary where freight
        flips from a cost line you can plan against to a crisis line where
        ops, compliance and vetting gates close most of what arithmetic
        shows open.
        """
        w = self.pnl_waterfall()
        ws_stressed = self.ws_rate >= WS_STRESS_THRESHOLD
        gross_color = self.COLORS['MARGIN']
        cost_color  = self.COLORS['VOL']    # red — every cost line eats the spread
        # NET bar colour logic: profit colour only when BOTH net is positive
        # AND freight is not in stress. Otherwise grey ("clearing level").
        if w['net_arb_usd_bbl'] < 0:
            net_color = self.COLORS['VOL']           # red — closed
        elif ws_stressed:
            net_color = self.COLORS['REF']           # grey — clearing level, not executable
        else:
            net_color = self.COLORS['MARGIN']        # green — executable open arb
        steps = [
            ('Gross\nspread',  w['gross_spread_usd_bbl'],   gross_color),
            ('Freight',        -w['freight_usd_bbl'],       cost_color),
            ('Port costs',     -w['port_costs_usd_bbl'],    cost_color),
            ('Canal tolls',    -w['canal_tolls_usd_bbl'],   cost_color),
            ('Financing',      -w['financing_usd_bbl'],     cost_color),
            ('Insurance',      -w['insurance_usd_bbl'],     cost_color),
            ('AWRP',           -w['awrp_usd_bbl'],          cost_color),
            ('Demurrage',      -w['demurrage_risk_usd_bbl'],cost_color),
            ('Broker comm.',   -w['broker_comm_usd_bbl'],   cost_color),
            ('NET arb',        w['net_arb_usd_bbl'],        net_color),
        ]
        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        running = 0.0
        for i, (lbl, val, clr) in enumerate(steps):
            if lbl in ('Gross\nspread', 'NET arb'):
                ax.bar(i, val, color=clr, edgecolor='black', linewidth=0.6)
                ax.annotate(f'{val:+.2f}', xy=(i, val),
                            xytext=(0, 6 if val >= 0 else -14),
                            textcoords='offset points',
                            ha='center', fontsize=9, fontweight='bold')
            else:
                ax.bar(i, val, bottom=running, color=clr,
                       edgecolor='black', linewidth=0.6)
                ax.annotate(f'{val:+.2f}', xy=(i, running + val),
                            xytext=(0, 6 if val >= 0 else -14),
                            textcoords='offset points',
                            ha='center', fontsize=9)
                running += val
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_xticks(range(len(steps)))
        ax.set_xticklabels([s[0] for s in steps], fontsize=9)
        ax.set_ylabel('USD/bbl')
        if w['net_arb_usd_bbl'] < 0:
            status = 'CLOSED'
        elif ws_stressed:
            status = 'CLEARING LEVEL (WS-stressed, not executable)'
        else:
            status = 'OPEN'
        ax.set_title(
            f'{self.origin_port} → {self.dest_port} · {self.vessel} · '
            f'WS {self.ws_rate:.1f} · {status}', loc='left')
        return self._finalize(fig, 'WATERFALL')

    def chart_sensitivity_ws(self, ws_range: Optional[np.ndarray] = None):
        if ws_range is None:
            ws_range = np.linspace(50, 500, 91)
        df = self.sensitivity_ws(ws_range)
        be = self.breakeven_ws()

        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        ax.plot(df['ws'], df['net_usd_bbl'],
                color=self.COLORS['PRICE'], linewidth=self.LW + 0.3)
        ax.axhline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.6)
        if not np.isnan(be) and ws_range.min() <= be <= ws_range.max():
            ax.axvline(be, color=self.COLORS['VOL'], linestyle=':',
                       linewidth=0.9, label=f'Break-even WS = {be:.1f}')
        ax.axvline(self.ws_rate, color=self.COLORS['MARGIN'],
                   linewidth=0.9, alpha=0.7,
                   label=f'Current WS = {self.ws_rate:.1f}')
        ax.fill_between(df['ws'], df['net_usd_bbl'], 0,
                        where=(df['net_usd_bbl'] > 0),
                        color=self.COLORS['MARGIN'], alpha=0.12, label='Open')
        ax.fill_between(df['ws'], df['net_usd_bbl'], 0,
                        where=(df['net_usd_bbl'] < 0),
                        color=self.COLORS['VOL'], alpha=0.12, label='Closed')
        ax.set(xlabel='Worldscale (WS)', ylabel='Net arb P&L (USD/bbl)')
        ax.set_title(
            f'{self.origin_port} → {self.dest_port} · {self.vessel} · '
            f'P&L sensitivity to WS', loc='left')
        ax.legend(loc='upper right', fontsize=9)
        return self._finalize(fig, 'SENSITIVITY_WS')

    def chart_sensitivity_grid(self,
                               ws_range: Optional[np.ndarray] = None,
                               spread_range: Optional[np.ndarray] = None):
        if ws_range is None:
            ws_range = np.linspace(50, 500, 46)
        if spread_range is None:
            spread_range = np.linspace(-5, 25, 61)
        df  = self.sensitivity_grid(ws_range, spread_range)
        piv = df.pivot(index='spread', columns='ws', values='net_usd_bbl')

        fig, ax = plt.subplots(figsize=self.SIZES['STANDARD'])
        vmax = max(abs(piv.values.min()), abs(piv.values.max()))
        im = ax.imshow(piv.values, origin='lower', aspect='auto', cmap='RdYlGn',
                       vmin=-vmax, vmax=vmax,
                       extent=[ws_range.min(), ws_range.max(),
                               spread_range.min(), spread_range.max()])
        ax.contour(piv.columns, piv.index, piv.values, levels=[0],
                   colors='black', linewidths=1.2, linestyles='--')
        cur_spread = self.gross_spread_usd_bbl
        ax.scatter(self.ws_rate, cur_spread, color='black', s=50, zorder=5)
        ax.annotate(f'Today\nWS {self.ws_rate:.0f} · Δ {cur_spread:+.2f}',
                    xy=(self.ws_rate, cur_spread), xytext=(10, 10),
                    textcoords='offset points', fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3',
                              facecolor='white', alpha=0.85))
        cb = plt.colorbar(im, ax=ax)
        cb.set_label('Net arb P&L (USD/bbl)')
        ax.set(xlabel='Worldscale (WS)', ylabel='Gross spread (USD/bbl)')
        ax.set_title(
            f'{self.origin_port} → {self.dest_port} · {self.vessel} · '
            f'arb P&L surface — dashed contour = break-even',
            loc='left')
        return self._finalize(fig, 'SENSITIVITY_GRID')

    # --- multi-cargo classmethods -------------------------------------------

    @classmethod
    def chart_route_comparison(cls, arbs: dict):
        ref = next(iter(arbs.values()))
        rows = [(lbl, a.pnl_bbl(), a.is_open()) for lbl, a in arbs.items()]
        rows.sort(key=lambda r: r[1])

        fig, ax = plt.subplots(figsize=ref.SIZES['STANDARD'])
        colours = [ref.COLORS['MARGIN'] if r[2] else ref.COLORS['VOL']
                   for r in rows]
        ax.barh([r[0] for r in rows], [r[1] for r in rows],
                color=colours, edgecolor='black', linewidth=0.6)
        ax.axvline(0, color='black', linewidth=0.8)
        for i, (_, v, _) in enumerate(rows):
            ax.annotate(f'{v:+.2f}', xy=(v, i),
                        xytext=(5 if v >= 0 else -5, 0),
                        textcoords='offset points',
                        ha='left' if v >= 0 else 'right',
                        va='center', fontsize=9)
        ax.set(xlabel='Net arb P&L (USD/bbl)')
        ax.set_title(
            'Lane comparison — net arb P&L at current WS + forward-price inputs',
            loc='left')
        return ref._finalize(fig, 'ROUTE_COMPARISON')

    @classmethod
    def chart_scenario_backtest(cls, scenarios: pd.DataFrame,
                                ref_arb: Optional['CargoArb'] = None):
        ref = ref_arb if ref_arb is not None else cls.from_preset(
            'USG_NWE_ULSD', ws_rate=100,
            buy_price=100, sell_price=100, save_figures=True)
        colours = [ref.COLORS['MARGIN'] if v >= 0 else ref.COLORS['VOL']
                   for v in scenarios['net']]

        fig, (ax_top, ax_bot) = plt.subplots(
            2, 1, figsize=(ref.SIZES['STANDARD'][0], ref.SIZES['STANDARD'][1] + 2),
            gridspec_kw={'height_ratios': [1, 1], 'hspace': 0.45})
        ax_top.bar(scenarios['event'], scenarios['ws'],
                   color=ref.COLORS['PRICE'], edgecolor='black', linewidth=0.6)
        ax_top.set(ylabel='Worldscale (WS)')
        ax_top.set_title(f'Freight WS by scenario — '
                         f'{", ".join(scenarios["route"].unique())}',
                         loc='left', fontsize=10)
        ax_top.tick_params(axis='x', rotation=20)
        for lbl in ax_top.get_xticklabels():
            lbl.set_ha('right')

        ax_bot.bar(scenarios['event'], scenarios['net'], color=colours,
                   edgecolor='black', linewidth=0.6)
        ax_bot.axhline(0, color='black', linewidth=0.8)
        for i, v in enumerate(scenarios['net']):
            ax_bot.annotate(f'{v:+.2f}', xy=(i, v),
                            xytext=(0, 6 if v >= 0 else -14),
                            textcoords='offset points',
                            ha='center', fontsize=9)
        ax_bot.set(ylabel='Net arb P&L (USD/bbl)')
        ax_bot.set_title('Net arb P&L — open (green) / closed (red)',
                         loc='left', fontsize=10)
        ax_bot.tick_params(axis='x', rotation=20)
        for lbl in ax_bot.get_xticklabels():
            lbl.set_ha('right')
        return ref._finalize(fig, 'SCENARIO_BACKTEST')

    # --- text representation -------------------------------------------------

    def summary(self) -> str:
        w = self.pnl_waterfall()
        date_of_prices = self.date_of_prices or self._meta.get('DATE_OF_PRICES', '—')
        regime         = self._meta.get('REGIME', '—')
        cargo_bbl      = self.cargo_mt * self.density
        lines = [
            f'=== CargoArb · {self.origin_port} → {self.dest_port} ===',
            f'  Prices as of  : {date_of_prices}   (regime: {regime})',
            f'  NOT LIVE — parametric model, user-cited price snapshot',
            '',
            f'  Vessel        : {self.vessel}  ({self._vessel["dwt_kt"]} kdwt nameplate, {self._vessel["service"]} service)',
            f'  Cargo         : {self.cargo_mt:,.0f} MT  ({cargo_bbl:,.0f} bbl)  · {self.capacity_utilization*100:.0f}% utilisation',
            f'  Grade         : {self.grade}  (density {self.density:.2f} bbl/MT)',
            '',
            f'  Distance      : {self.distance_nm:,.0f} nm',
            f'  Laden speed   : {self.speed_kt:.1f} kt  →  steam {self.steam_days:.1f} d',
            f'  Voyage days   : {self.voyage_days:.1f}  (steam {self.steam_days:.1f} + port {self.port_stay_days} + laycan {self.laycan_days})',
            f'  Canals        : {list(self.canals) if self.canals else "—"}',
            '',
            f'  WS rate       : {self.ws_rate:.2f}',
            f'  Flat rate     : {self.flat_rate:.2f} USD/MT @ WS 100',
            f'  Freight       : {self.freight_usd_mt():.2f} USD/MT · {self.freight_usd_bbl():.2f} USD/bbl',
            f'  Cargo freight : {self.cargo_freight_total_usd():,.0f} USD',
            '',
            f'  Buy  price    : {self.buy_price:.2f}  (premium/discount {self.buy_premium_discount:+.2f})  → effective {self.effective_buy_price:.2f} USD/bbl  ({self.buy_timing or "forward"})',
            f'  Sell price    : {self.sell_price:.2f}  (premium/discount {self.sell_premium_discount:+.2f})  → effective {self.effective_sell_price:.2f} USD/bbl  ({self.sell_timing or "forward"})',
            f'  Gross spread  : {w["gross_spread_usd_bbl"]:+.2f} USD/bbl',
            '',
            f'  P&L waterfall (USD/bbl):',
            f'    Gross spread      : {w["gross_spread_usd_bbl"]:+7.2f}',
            f'    − Freight         : {w["freight_usd_bbl"]:+7.2f}',
            f'    − Port costs      : {w["port_costs_usd_bbl"]:+7.2f}',
            f'    − Canal tolls     : {w["canal_tolls_usd_bbl"]:+7.2f}',
            f'    − Financing       : {w["financing_usd_bbl"]:+7.2f}',
            f'    − Insurance       : {w["insurance_usd_bbl"]:+7.2f}',
            f'    − AWRP            : {w["awrp_usd_bbl"]:+7.2f}',
            f'    − Demurrage risk  : {w["demurrage_risk_usd_bbl"]:+7.2f}',
            f'    − Broker comm.    : {w["broker_comm_usd_bbl"]:+7.2f}',
            f'    NET ARB           : {w["net_arb_usd_bbl"]:+7.2f} USD/bbl',
            f'    CARGO P&L         : {w["cargo_total_pnl_usd"]:+,.0f} USD  ({cargo_bbl:,.0f} bbl × {w["net_arb_usd_bbl"]:+.2f})',
            '',
            f'  Break-even WS     : {self.breakeven_ws():.1f}',
            f'  Break-even spread : {self.breakeven_spread():.2f} USD/bbl',
            f'  Status            : {"OPEN ✓" if self.is_open() else "CLOSED ✗"}',
        ]
        return '\n'.join(lines)

    def print_summary(self):
        print(self.summary())

    def inputs_table(self) -> pd.DataFrame:
        """Return the inputs as a one-row DataFrame — useful for report tables."""
        return pd.DataFrame([{
            'Prices dated':        self.date_of_prices or self._meta.get('DATE_OF_PRICES', '—'),
            'Route':               f'{self.origin_port} → {self.dest_port}',
            'Vessel':              f'{self.vessel} ({self._vessel["dwt_kt"]} kdwt)',
            'Grade':               f'{self.grade} (density {self.density:.2f} bbl/MT)',
            'Cargo':               f'{self.cargo_mt:,.0f} MT · {self.capacity_utilization*100:.0f}% util',
            'Distance (nm)':       f'{self.distance_nm:,.0f}',
            'Speed (kt)':          f'{self.speed_kt:.1f}',
            'Voyage (days)':       f'{self.voyage_days:.1f}',
            'WS':                  f'{self.ws_rate:.2f}',
            'Flat rate (USD/MT)':  f'{self.flat_rate:.2f}',
            'Buy':                 f'{self.buy_price:+.2f} {self.buy_premium_discount:+.2f} = {self.effective_buy_price:+.2f}',
            'Sell':                f'{self.sell_price:+.2f} {self.sell_premium_discount:+.2f} = {self.effective_sell_price:+.2f}',
            'Gross spread':        f'{self.gross_spread_usd_bbl:+.2f}',
            'Net P&L (USD/bbl)':   f'{self.pnl_bbl():+.2f}',
            'Cargo P&L (USD)':     f'{self.pnl_cargo_usd():+,.0f}',
            'Break-even WS':       f'{self.breakeven_ws():.1f}',
            'Status':              'OPEN' if self.is_open() else 'CLOSED',
        }])
