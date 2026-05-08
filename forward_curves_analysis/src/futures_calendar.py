"""
Futures roll calendar — maps a trade date to the effective delivery month
of the front contract on each venue, and returns the M-number pairing
needed to align Brent vs LSGO (or Brent vs other products) on the same
delivery month.

Contract rules encoded here:

  ICE Brent monthly: ceases trading end of the last business day of the
  second month preceding the delivery month. So Brent Jun-26 expires
  last BD of April 2026. On dates before that expiry, Brent M1 delivery =
  (trade_month + 2) calendar month.

  ICE Low Sulphur Gasoil (LSGO): ceases trading at 12:00 London 2 business
  days prior to the 14th calendar day of the delivery month. So LSGO
  Apr-26 expires 2 BD before 14-Apr-2026. On dates before that, LSGO M1
  delivery = trade_month (the current month). After, M1 = next month.

Pairing result (so that both legs reference the same delivery month):

  day 1 → LSGO expiry of month N        : Brent M1 vs LSGO M3
  LSGO expiry → Brent expiry (= end-M)  : Brent M1 vs LSGO M2
  Brent expiry → next LSGO expiry       : Brent M1 vs LSGO M3  (new cycle)
  ...and so on.

This module is deliberately tiny and dependency-light. Business-day logic
uses a Mon-Fri calendar with a configurable UK/US holiday list.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

# Minimal holiday set — New Year's Day, Good Friday, Easter Monday, May Day,
# Christmas, Boxing Day. Extend via `holidays` param in `FuturesCalendar`
# if you need tighter accuracy (LCH / ICE publish the definitive list).
_DEFAULT_HOLIDAYS_FIXED = {
    (1, 1),  # New Year
    (5, 1),  # May Day
    (12, 25),  # Christmas
    (12, 26),  # Boxing Day
}


def _is_business_day(d: date, holidays: set[date]) -> bool:
    if d.weekday() >= 5:  # Sat / Sun
        return False
    if d in holidays:
        return False
    return (d.month, d.day) not in _DEFAULT_HOLIDAYS_FIXED


def _prev_business_day(d: date, holidays: set[date]) -> date:
    d = d - timedelta(days=1)
    while not _is_business_day(d, holidays):
        d -= timedelta(days=1)
    return d


def _last_business_day_of_month(y: int, m: int, holidays: set[date]) -> date:
    # start from last day of month, walk back
    d = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
    while not _is_business_day(d, holidays):
        d -= timedelta(days=1)
    return d


def _lsgo_expiry(y: int, m: int, holidays: set[date]) -> date:
    """LSGO contract for delivery month (y, m) expires at 12:00 London
    2 business days before the 14th calendar day of month (y, m).
    We treat the expiry *as of* that full business day (close-of-day)
    so on the expiry date itself M1 is still the expiring contract.
    """
    target = date(y, m, 14)
    d = target
    back = 0
    # step back 2 business days
    while back < 2:
        d = _prev_business_day(d, holidays)
        back += 1
    return d


def _brent_expiry(y: int, m: int, holidays: set[date]) -> date:
    """Brent contract for delivery month (y, m) expires last BD of
    the second month preceding the delivery month. So Brent Jun-26
    expires last BD of April 2026.
    """
    # second month preceding (y, m):
    prev_m = m - 2
    prev_y = y
    while prev_m <= 0:
        prev_m += 12
        prev_y -= 1
    return _last_business_day_of_month(prev_y, prev_m, holidays)


@dataclass
class MonthPair:
    """Result of a pairing query for one trade date."""

    trade_date: date
    brent_m1_delivery: pd.Period
    lsgo_m1_delivery: pd.Period
    # M-number on the LSGO strip that matches Brent M1 by delivery month
    lsgo_match_m: int
    # M-number on the Brent strip that matches LSGO M1 by delivery month
    brent_match_m: int

    @property
    def label(self) -> str:
        return f"Brent M1 × LSGO M{self.lsgo_match_m}"


class FuturesCalendar:
    """Maps a date to the correct front-contract delivery months for
    ICE Brent and ICE LSGO, and the M-number pairing that aligns them
    on the same delivery month.

    Usage
    -----
    cal = FuturesCalendar()
    pair = cal.pair_on("2026-04-16")
    print(pair.label)                # "Brent M1 × LSGO M2"
    print(pair.brent_m1_delivery)    # Period('2026-06', freq='M')
    print(pair.lsgo_m1_delivery)     # Period('2026-05', freq='M')

    For a full time series:
    pairs = cal.pair_series(pd.date_range("2026-01-01", "2026-12-31", freq="B"))
    """

    def __init__(self, holidays: Iterable[date] = ()):
        self.holidays: set[date] = set(holidays)

    # ----- public -----
    def brent_m1_delivery(self, d: date) -> pd.Period:
        # walk forward from trade-month checking which is the first
        # delivery month whose Brent expiry is >= trade date
        y, m = d.year, d.month
        for _ in range(36):
            if _brent_expiry(y, m, self.holidays) >= d:
                return pd.Period(year=y, month=m, freq="M")
            m += 1
            if m == 13:
                m = 1
                y += 1
        raise RuntimeError("Brent delivery month not found in next 3y window")

    def lsgo_m1_delivery(self, d: date) -> pd.Period:
        y, m = d.year, d.month
        for _ in range(36):
            if _lsgo_expiry(y, m, self.holidays) >= d:
                return pd.Period(year=y, month=m, freq="M")
            m += 1
            if m == 13:
                m = 1
                y += 1
        raise RuntimeError("LSGO delivery month not found in next 3y window")

    def pair_on(self, d) -> MonthPair:
        d = pd.Timestamp(d).date()
        brent_m1 = self.brent_m1_delivery(d)
        lsgo_m1 = self.lsgo_m1_delivery(d)
        # The Brent M-number that matches LSGO M1's delivery month:
        (brent_m1.ordinal - lsgo_m1.ordinal) * -1 + 1
        # more readably:
        #   lsgo_m1 - brent_m1  ==  (lsgo M1 delivery is N months before Brent M1 delivery)
        # usually lsgo M1 is before Brent M1 by 1 or 2 months (Brent is further-out),
        # so LSGO match-M = 1 + (brent_m1 - lsgo_m1) months.
        lsgo_match_m = (brent_m1.ordinal - lsgo_m1.ordinal) + 1
        brent_match_m_for_lsgo = 1 - (brent_m1.ordinal - lsgo_m1.ordinal)
        # Brent is always further-out so brent_match_m_for_lsgo <= 1; typically
        # it's 0 or negative which is meaningless (can't go behind M1). Use
        # LSGO → Brent mapping only when LSGO is further-out (rare; only
        # during exotic calendar overlaps). Default: we pair Brent M1 with
        # LSGO M{lsgo_match_m}.
        return MonthPair(
            trade_date=d,
            brent_m1_delivery=brent_m1,
            lsgo_m1_delivery=lsgo_m1,
            lsgo_match_m=lsgo_match_m,
            brent_match_m=max(brent_match_m_for_lsgo, 1),
        )

    def pair_series(self, dates) -> pd.DataFrame:
        """Vectorised: returns a DataFrame indexed by date with columns
        [brent_m1_delivery, lsgo_m1_delivery, lsgo_match_m, brent_match_m, label].
        """
        rows = []
        for d in pd.DatetimeIndex(dates):
            p = self.pair_on(d.date())
            rows.append(
                {
                    "date": pd.Timestamp(d),
                    "brent_m1_delivery": p.brent_m1_delivery,
                    "lsgo_m1_delivery": p.lsgo_m1_delivery,
                    "lsgo_match_m": p.lsgo_match_m,
                    "brent_match_m": p.brent_match_m,
                    "label": p.label,
                }
            )
        return pd.DataFrame(rows).set_index("date")


# ----- quick self-test when run directly -----
if __name__ == "__main__":
    cal = FuturesCalendar()
    for d in [
        "2026-04-09",
        "2026-04-13",
        "2026-04-16",
        "2026-04-30",
        "2026-05-05",
        "2026-05-13",
        "2026-05-29",
    ]:
        p = cal.pair_on(d)
        print(
            f"{d}: Brent M1 delivery {p.brent_m1_delivery} · "
            f"LSGO M1 delivery {p.lsgo_m1_delivery} · pair → {p.label}"
        )
