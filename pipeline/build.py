"""Macro Desk data build.

Pulls macro series from FRED and prices from Yahoo Finance, then writes
site/data.json for the front end. Runs on a GitHub Actions schedule.

    python pipeline/build.py
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from universe import ASSETS, FRED, INVERT, RESTRICTED  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data.json"
POLICY = ROOT / "pipeline" / "policy.json"
MIDTERM_SUMMARY = "https://dancunningham22.github.io/2026-Midterm/summary.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
LOG: list[str] = []


def log(msg: str):
    print(msg, flush=True)
    LOG.append(msg)


# ---------- fetching ----------

def fetch_fred(series_id: str, start: str = "2016-01-01") -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                df = pd.read_csv(io.BytesIO(r.read()))
            break
        except Exception as e:
            last_err = e
    else:
        raise last_err
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    return df.dropna().set_index("date")["value"]


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(tickers, period="6y", interval="1d", auto_adjust=True,
                     progress=False, group_by="column", threads=True)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
    close = close.dropna(how="all")
    for t in INVERT:
        if t in close:
            close[t] = 1.0 / close[t]
    return close


def fetch_json(url: str):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except Exception as e:  # optional input; never fail the build over it
        print(f"skip {url}: {e}")
        return None


# ---------- helpers ----------

def r(x, nd=2):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def value_ago(s: pd.Series, days: int):
    """Last observation on or before (latest date - days)."""
    cut = s.index[-1] - pd.Timedelta(days=days)
    past = s[s.index <= cut]
    return past.iloc[-1] if len(past) else None


def weekly_spark(s: pd.Series, weeks: int = 52) -> list:
    w = s.resample("W-FRI").last().dropna().iloc[-weeks:]
    return [r(v, 3) for v in w.values]


def zscore_last(s: pd.Series, lookback_weeks: int = 156):
    s = s.dropna().iloc[-lookback_weeks:]
    if len(s) < 20 or s.std() == 0:
        return 0.0
    return float((s.iloc[-1] - s.mean()) / s.std())


# ---------- macro ----------

def build_macro(fred: dict[str, pd.Series]) -> dict:
    out = {}
    for sid, (label, unit) in FRED.items():
        s = fred.get(sid)
        if s is None or s.empty:
            continue
        pct = unit in ("idx", "$", "$M", "$B")  # price-like: report % change
        def chg(days):
            past = value_ago(s, days)
            if past is None:
                return None
            return r((s.iloc[-1] / past - 1) * 100) if pct else r((s.iloc[-1] - past) * 100, 0)
        out[sid] = {
            "label": label, "unit": unit, "last": r(s.iloc[-1], 3),
            "date": s.index[-1].strftime("%Y-%m-%d"),
            "chg_kind": "pct" if pct else "bp",
            "chg1m": chg(30), "chg3m": chg(91), "chg12m": chg(365),
            "spark": weekly_spark(s),
        }
    # Net liquidity = Fed balance sheet - TGA - reverse repo, in $ trillions (weekly)
    if all(k in fred for k in ("WALCL", "WTREGEN", "RRPONTSYD")):
        w = pd.concat({
            "walcl": fred["WALCL"].resample("W-WED").last() / 1e6,
            "tga": fred["WTREGEN"].resample("W-WED").last() / 1e3,
            "rrp": fred["RRPONTSYD"].resample("W-WED").last() / 1e3,
        }, axis=1).ffill().dropna()
        nl = w["walcl"] - w["tga"] - w["rrp"]
        out["NETLIQ"] = {
            "label": "Net liquidity (Fed − TGA − RRP)", "unit": "$T", "last": r(nl.iloc[-1], 3),
            "date": nl.index[-1].strftime("%Y-%m-%d"), "chg_kind": "pct",
            "chg1m": r((nl.iloc[-1] / value_ago(nl, 30) - 1) * 100),
            "chg3m": r((nl.iloc[-1] / value_ago(nl, 91) - 1) * 100),
            "chg12m": r((nl.iloc[-1] / value_ago(nl, 365) - 1) * 100),
            "spark": [r(v, 3) for v in nl.iloc[-52:].values],
        }
        fred["_NETLIQ"] = nl
    if "DGS10" in fred and "DGS2" in fred:
        curve = (fred["DGS10"] - fred["DGS2"]).dropna()
        out["CURVE"] = {
            "label": "2s10s curve", "unit": "%", "last": r(curve.iloc[-1], 3),
            "date": curve.index[-1].strftime("%Y-%m-%d"), "chg_kind": "bp",
            "chg1m": r((curve.iloc[-1] - value_ago(curve, 30)) * 100, 0),
            "chg3m": r((curve.iloc[-1] - value_ago(curve, 91)) * 100, 0),
            "chg12m": r((curve.iloc[-1] - value_ago(curve, 365)) * 100, 0),
            "spark": weekly_spark(curve),
        }
    return out


def build_regime(fred: dict[str, pd.Series]) -> dict:
    """Risk appetite score from -100 (risk-off) to +100 (risk-on).

    Each input is its 13-week change, z-scored against the last 3 years of
    13-week changes, signed so that positive = supportive for risk assets.
    """
    def weekly(sid):
        return fred[sid].resample("W-FRI").last().dropna()

    comps = []
    def add(name, s, sign, note, pct=False):
        ch = (s.pct_change(13) * 100) if pct else s.diff(13)
        z = max(-2.0, min(2.0, sign * zscore_last(ch)))
        comps.append({"name": name, "z": round(z, 2), "note": note,
                      "change13w": r(ch.iloc[-1], 2), "pct": pct})

    if "_NETLIQ" in fred:
        add("Liquidity", fred["_NETLIQ"].resample("W-FRI").last().dropna(), +1,
            "Fed balance sheet minus TGA and reverse repo", pct=True)
    if "DFII10" in fred:
        add("Real yields", weekly("DFII10"), -1, "Falling real yields ease financial conditions")
    if "BAMLH0A0HYM2" in fred:
        add("Credit", weekly("BAMLH0A0HYM2"), -1, "Tighter junk spreads mean lenders are relaxed")
    if "DTWEXBGS" in fred:
        add("Dollar", weekly("DTWEXBGS"), -1, "A weaker dollar loosens global funding", pct=True)
    if "VIXCLS" in fred:
        add("Volatility", weekly("VIXCLS"), -1, "Lower implied volatility")

    score = round(float(np.mean([c["z"] for c in comps])) * 50) if comps else None
    if score is None:
        label = None
    elif score >= 25:
        label = "Risk-on"
    elif score <= -25:
        label = "Risk-off"
    else:
        label = "Neutral"
    return {"score": score, "label": label, "components": comps}


# ---------- assets ----------

def estimate_betas(px: pd.Series, factors: pd.DataFrame):
    """Weekly OLS of asset returns on the four macro factors over up to 5 years."""
    ret = px.resample("W-FRI").last().pct_change() * 100
    df = pd.concat([ret.rename("y"), factors], axis=1).dropna().iloc[-260:]
    if len(df) < 78:  # need about 18 months
        return None, None
    X = np.column_stack([np.ones(len(df)), df[["ry", "usd", "oil", "hy"]].values])
    y = df["y"].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else 0
    return {k: r(v, 3) for k, v in zip(["ry", "usd", "oil", "hy"], coef[1:])}, r(r2, 3)


def build_assets(prices: pd.DataFrame, fred: dict[str, pd.Series]) -> list[dict]:
    w = lambda sid: fred[sid].resample("W-FRI").last()
    need = ("DFII10", "DTWEXBGS", "DCOILWTICO", "BAMLH0A0HYM2")
    factors = None
    if all(k in fred for k in need):
        factors = pd.concat({
            "ry": w("DFII10").diff(),                    # percentage points = per 100bp
            "usd": w("DTWEXBGS").pct_change() * 100,
            "oil": w("DCOILWTICO").pct_change() * 100,
            "hy": w("BAMLH0A0HYM2").diff(),
        }, axis=1)
    else:
        log("betas skipped: missing factor series")

    out = []
    for t, name, group, prior in ASSETS:
        row = {"t": t, "name": name, "group": group,
               "prior": dict(zip(["ry", "usd", "oil", "hy"], prior))}
        s = prices[t].dropna() if t in prices else pd.Series(dtype=float)
        if len(s) > 30:
            last = s.iloc[-1]
            def ret(days):
                past = value_ago(s, days)
                return r((last / past - 1) * 100) if past else None
            ma50 = s.iloc[-50:].mean()
            ma200 = s.iloc[-200:].mean() if len(s) >= 200 else None
            p12 = value_ago(s, 365)
            p1 = value_ago(s, 30)
            daily = s.pct_change().dropna().iloc[-63:]
            row.update({
                "last": r(last, 4), "date": s.index[-1].strftime("%Y-%m-%d"),
                "r1m": ret(30), "r3m": ret(91), "r12m": ret(365),
                "mom12_1": r((p1 / p12 - 1) * 100) if p1 and p12 else None,
                "vs50": r((last / ma50 - 1) * 100),
                "vs200": r((last / ma200 - 1) * 100) if ma200 else None,
                "vol": r(daily.std() * np.sqrt(252) * 100, 1),
                "spark": weekly_spark(s),
            })
            beta, r2 = estimate_betas(s, factors) if factors is not None else (None, None)
            if beta:
                row["beta"], row["r2"] = beta, r2
        out.append(row)
    return out


# ---------- policy bridge ----------

def build_policy() -> dict:
    priors = json.loads(POLICY.read_text())
    summary = fetch_json(MIDTERM_SUMMARY)
    odds = None
    if isinstance(summary, dict) and "house_d" in summary and "senate_d" in summary:
        odds = {k: summary.get(k) for k in ("house_d", "senate_d", "updated")}
    priors["odds"] = odds
    return priors


# ---------- main ----------

def safe(name, fn, default):
    try:
        return fn()
    except Exception as e:
        log(f"{name} failed: {type(e).__name__}: {e}")
        return default


def main():
    fred = {}
    for sid in FRED:
        try:
            fred[sid] = fetch_fred(sid)
        except Exception as e:
            log(f"FRED {sid} failed: {type(e).__name__}: {e}")
    log(f"FRED: {len(fred)}/{len(FRED)} series")
    prices = safe("prices", lambda: fetch_prices([a[0] for a in ASSETS]), pd.DataFrame())
    log(f"prices: {prices.shape[1] if len(prices) else 0} tickers")

    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "macro": safe("macro", lambda: build_macro(fred), {}) or old.get("macro", {}),
        "regime": safe("regime", lambda: build_regime(fred), {"score": None, "label": None, "components": []}),
        "assets": safe("assets", lambda: build_assets(prices, fred), None) or old.get("assets", []),
        "policy": safe("policy", build_policy, old.get("policy")),
        "restricted": RESTRICTED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))
    n_px = sum(1 for a in data["assets"] if "last" in a)
    log(f"wrote data.json: {len(data['macro'])} macro series, {n_px}/{len(ASSETS)} assets priced")
    (OUT.parent / "build_log.json").write_text(json.dumps({"updated": data["updated"], "log": LOG}, indent=1))


if __name__ == "__main__":
    main()
