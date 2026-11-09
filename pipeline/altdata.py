"""Keyless fallbacks for the FRED series, used when FRED can't be reached.

FRED's keyless endpoint times out from GitHub's servers, so without a
FRED_API_KEY secret the pipeline rebuilds each series from the primary source:

  DGS10, DGS2      US Treasury daily par yield curve (home.treasury.gov)
  DFII10           US Treasury daily real yield curve
  T10YIE           10y nominal minus 10y real (same definition as FRED's)
  DFEDTARU         New York Fed, top of the target range (EFFR feed)
  RRPONTSYD        New York Fed, reverse repo operations
  WTREGEN          Treasury Fiscal Data, Daily Treasury Statement TGA balance
  WALCL            New York Fed SOMA holdings (proxy: SOMA is ~95% of the balance sheet)
  VIXCLS, SP500    Yahoo (^VIX, ^GSPC)
  DCOILWTICO       Yahoo front-month WTI future (CL=F)
  DTWEXBGS         Yahoo ICE dollar index (DX-Y.NYB) — a different basket, so the label changes
  BAMLH0A0HYM2     Estimated from HYG vs IEF daily returns, anchored to the last real reading

Every function returns a pandas Series indexed by date, in the same units as
the FRED series it replaces.
"""
from __future__ import annotations

import io
import json
import re
import urllib.request
from datetime import date

import pandas as pd

UA = {"User-Agent": "macro-desk-pipeline/1.0 (+https://github.com/DanCunningham22/macro-desk)",
      "Accept": "*/*"}


def _get(url: str, timeout: int = 40, headers: dict | None = None) -> bytes:
    h = dict(UA)
    if headers:
        h.update(headers)
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # retry transient errors
            last = e
    raise last


# ---------- Treasury yield curves ----------

def _treasury_year(kind: str, year: int) -> pd.DataFrame:
    url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
           f"daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv")
    df = pd.read_csv(io.BytesIO(_get(url)))
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date")


def _col(df: pd.DataFrame, pattern: str) -> pd.Series:
    for c in df.columns:
        if re.fullmatch(pattern, c.strip(), flags=re.I):
            return pd.to_numeric(df[c], errors="coerce")
    raise KeyError(f"no column like {pattern} in {list(df.columns)[:12]}")


def treasury(start_year: int = 2019) -> dict[str, pd.Series]:
    nominal, real = [], []
    for y in range(start_year, date.today().year + 1):
        nominal.append(_treasury_year("daily_treasury_yield_curve", y))
        real.append(_treasury_year("daily_treasury_real_yield_curve", y))
    n = pd.concat(nominal).sort_index()
    rl = pd.concat(real).sort_index()
    out = {
        "DGS10": _col(n, r"10 y(r|ear)s?").dropna(),
        "DGS2": _col(n, r"2 y(r|ear)s?").dropna(),
        "DFII10": _col(rl, r"10 y(r|ear)s?").dropna(),
    }
    be = (out["DGS10"] - out["DFII10"]).dropna()
    out["T10YIE"] = be
    return out


# ---------- New York Fed ----------

def fed_target_upper(start: str = "2019-01-01") -> pd.Series:
    url = ("https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
           f"?startDate={start}&endDate={date.today():%Y-%m-%d}")
    rows = json.loads(_get(url))["refRates"]
    s = pd.Series({pd.Timestamp(r["effectiveDate"]): float(r["targetRateTo"])
                   for r in rows if r.get("targetRateTo") is not None})
    return s.sort_index()


def reverse_repo(start: str = "2019-01-01") -> pd.Series:
    url = ("https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json"
           f"?startDate={start}&endDate={date.today():%Y-%m-%d}")
    ops = json.loads(_get(url))["repo"]["operations"]
    s = pd.Series(dtype=float)
    vals = {}
    for o in ops:
        amt = o.get("totalAmtAccepted")
        if amt is None:
            continue
        d = pd.Timestamp(o["operationDate"])
        vals[d] = vals.get(d, 0.0) + float(amt) / 1e9  # dollars -> $B (FRED units)
    s = pd.Series(vals).sort_index()
    return s


def soma_total() -> pd.Series:
    rows = json.loads(_get("https://markets.newyorkfed.org/api/soma/summary.json"))["soma"]["summary"]
    s = pd.Series({pd.Timestamp(r["asOfDate"]): float(r["total"]) / 1e6 for r in rows if r.get("total")})
    return s.sort_index()  # $ millions, like WALCL


# ---------- Treasury General Account ----------

def tga(start: str = "2019-01-01") -> pd.Series:
    base = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/"
            "operating_cash_balance?fields=record_date,account_type,open_today_bal,close_today_bal"
            f"&filter=record_date:gte:{start}&page[size]=10000")
    data = json.loads(_get(base))["data"]
    vals = {}
    for r in data:
        acct = (r.get("account_type") or "").lower()
        if "closing balance" not in acct or ("tga" not in acct and "general account" not in acct and "federal reserve account" not in acct):
            continue
        v = r.get("close_today_bal")
        if v in (None, "", "null"):
            v = r.get("open_today_bal")
        try:
            vals[pd.Timestamp(r["record_date"])] = float(v) / 1e3  # $M -> $B (FRED units)
        except (TypeError, ValueError):
            continue
    return pd.Series(vals).sort_index()


# ---------- Yahoo-based series ----------

YAHOO_MAP = {"VIXCLS": "^VIX", "SP500": "^GSPC", "DCOILWTICO": "CL=F", "DTWEXBGS": "DX-Y.NYB"}
# tried in order if the first ticker returns nothing
YAHOO_ALT = {"DCOILWTICO": [("BZ=F", "Brent crude (front month)"), ("USO", "Oil (USO fund price)")]}


def yahoo_series(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(tickers, period="8y", interval="1d", auto_adjust=False,
                     progress=False, group_by="column", threads=True)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
    return close.dropna(how="all")


def hy_spread_estimate(px: pd.DataFrame, anchor_value: float, anchor_date) -> pd.Series:
    """Daily change in the HY option-adjusted spread, estimated from HYG's return
    in excess of its rate exposure (0.45 x IEF), divided by HYG's ~3.2-year
    spread duration. Cumulated and anchored to the last real FRED reading.
    """
    r = px[["HYG", "IEF"]].dropna().pct_change().dropna() * 100
    d_spread = -(r["HYG"] - 0.45 * r["IEF"]) / 3.2  # percentage points
    level = d_spread.cumsum()
    anchor_date = pd.Timestamp(anchor_date)
    ref = level[level.index <= anchor_date]
    offset = anchor_value - (ref.iloc[-1] if len(ref) else 0.0)
    return (level + offset).clip(lower=0.5)
