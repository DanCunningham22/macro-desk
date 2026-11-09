"""World and Trade data for Macro Desk.

Writes two files the front end reads:

  site/world.json  one row per country: US-listed ETF momentum vs the S&P 500,
                   currency moves, IMF forecasts, central-bank policy rate,
                   US-listed names, and the products where the country is a
                   top supplier or buyer.
  site/trade.json  for ~35 traded products: who exports and imports them
                   (UN Comtrade), the stocks tied to each product, what a
                   disruption at the top supplier would mean, and the biggest
                   recent year-on-year shifts in monthly exports.

Comtrade and IMF data change slowly, so they are refreshed at most weekly
(set FORCE_SLOW=1 to force). Prices refresh on every run.

    python pipeline/world.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from universe import RESTRICTED  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORLD_OUT = ROOT / "site" / "world.json"
TRADE_OUT = ROOT / "site" / "trade.json"
UA = {"User-Agent": "macro-desk-pipeline/1.0 (+https://github.com/DanCunningham22/macro-desk)", "Accept": "*/*"}
LOG: list[str] = []
BOOK = ["PLTR", "META", "MSFT", "GOOG", "SPCX", "INTC", "VRT", "TSLA", "JBL", "CAT", "WMT", "MA"]


def log(msg):
    print(msg, flush=True)
    LOG.append(msg)


def get_json(url, timeout=45, tries=3, pause=2.0):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(pause * (i + 2) * 2)
                continue
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:
            last = e
        time.sleep(pause * (i + 1))
    raise last


# ---------------------------------------------------------------------------
# Countries
# iso3, world-atlas numeric id, iso2, name, ETF, FX (Yahoo ticker, invert?), US-listed names, note
# FX is stored as the currency's value in dollars: up = currency stronger.
# ---------------------------------------------------------------------------
C = [
    ("USA", "840", "US", "United States", "SPY", None, [], ""),
    ("CAN", "124", "CA", "Canada", "EWC", ("CAD=X", True), ["SHOP", "RY", "CNQ", "CP", "TECK"], ""),
    ("MEX", "484", "MX", "Mexico", "EWW", ("MXN=X", True), ["AMX", "FMX", "CX", "ASR", "PAC"], ""),
    ("BRA", "076", "BR", "Brazil", "EWZ", ("BRL=X", True), ["VALE", "PBR", "ITUB", "NU", "SBS"], ""),
    ("ARG", "032", "AR", "Argentina", "ARGT", ("ARS=X", True), ["YPF", "GGAL", "PAM", "VIST"], ""),
    ("CHL", "152", "CL", "Chile", "ECH", ("CLP=X", True), ["SQM", "BCH", "LTM"], ""),
    ("PER", "604", "PE", "Peru", "EPU", ("PEN=X", True), ["SCCO", "BVN"], ""),
    ("COL", "170", "CO", "Colombia", "GXG", ("COP=X", True), ["EC", "CIB"], ""),
    ("GBR", "826", "GB", "United Kingdom", "EWU", ("GBPUSD=X", False), ["SHEL", "BP", "AZN", "HSBC", "UL", "RIO", "ARM"], ""),
    ("DEU", "276", "DE", "Germany", "EWG", ("EURUSD=X", False), ["SAP", "DB", "BNTX"], ""),
    ("FRA", "250", "FR", "France", "EWQ", ("EURUSD=X", False), ["TTE", "SNY"], ""),
    ("ITA", "380", "IT", "Italy", "EWI", ("EURUSD=X", False), ["STLA", "E", "RACE"], ""),
    ("ESP", "724", "ES", "Spain", "EWP", ("EURUSD=X", False), ["SAN", "BBVA", "TEF"], ""),
    ("NLD", "528", "NL", "Netherlands", "EWN", ("EURUSD=X", False), ["ASML", "ING", "NXPI", "PHG"], ""),
    ("CHE", "756", "CH", "Switzerland", "EWL", ("CHF=X", True), ["NVS", "UBS", "LOGI"], ""),
    ("SWE", "752", "SE", "Sweden", "EWD", ("SEK=X", True), ["ERIC", "SPOT"], ""),
    ("NOR", "578", "NO", "Norway", "ENOR", ("NOK=X", True), ["EQNR"], ""),
    ("DNK", "208", "DK", "Denmark", None, ("DKK=X", True), ["GMAB"],
     "The Denmark ETF (EDEN) is dominated by Novo Nordisk, a restricted GLP-1 maker, so it is not shown."),
    ("POL", "616", "PL", "Poland", "EPOL", ("PLN=X", True), [], ""),
    ("TUR", "792", "TR", "Turkey", "TUR", ("TRY=X", True), ["TKC"], ""),
    ("ISR", "376", "IL", "Israel", "EIS", ("ILS=X", True), ["TEVA", "CHKP", "ESLT", "NICE"], ""),
    ("SAU", "682", "SA", "Saudi Arabia", "KSA", None, [], "The riyal is pegged to the dollar."),
    ("ARE", "784", "AE", "UAE", "UAE", None, [], "The dirham is pegged to the dollar."),
    ("ZAF", "710", "ZA", "South Africa", "EZA", ("ZAR=X", True), ["GFI", "AU", "SBSW", "SSL"], ""),
    ("IND", "356", "IN", "India", "INDA", ("INR=X", True), ["INFY", "HDB", "IBN", "WIT", "RDY"], ""),
    ("CHN", "156", "CN", "China", "MCHI", ("CNY=X", True), ["BABA", "PDD", "JD", "BIDU", "YUMC"], ""),
    ("TWN", "158", "TW", "Taiwan", "EWT", ("TWD=X", True), ["TSM", "UMC", "ASX"],
     "Taiwan does not report to the UN; its trade is rebuilt from what other countries say they bought from it."),
    ("KOR", "410", "KR", "South Korea", "EWY", ("KRW=X", True), ["KB", "SHG", "PKX", "CPNG"], ""),
    ("JPN", "392", "JP", "Japan", "EWJ", ("JPY=X", True), ["TM", "SONY", "MUFG", "HMC", "NMR"], ""),
    ("IDN", "360", "ID", "Indonesia", "EIDO", ("IDR=X", True), ["TLK"], ""),
    ("VNM", "704", "VN", "Vietnam", "VNM", ("VND=X", True), [], ""),
    ("THA", "764", "TH", "Thailand", "THD", ("THB=X", True), [], ""),
    ("PHL", "608", "PH", "Philippines", "EPHE", ("PHP=X", True), [], ""),
    ("MYS", "458", "MY", "Malaysia", "EWM", ("MYR=X", True), [], ""),
    ("AUS", "036", "AU", "Australia", "EWA", ("AUDUSD=X", False), ["BHP", "WDS", "JHX"], ""),
]
ISO3 = {c[0] for c in C}
NAME = {c[0]: c[3] for c in C}
NAME.update({  # trading countries without a country page, so trade lists read as names
    "RUS": "Russia", "UKR": "Ukraine", "KAZ": "Kazakhstan", "COD": "DR Congo", "ZMB": "Zambia", "AGO": "Angola",
    "NGA": "Nigeria", "DZA": "Algeria", "LBY": "Libya", "EGY": "Egypt", "MAR": "Morocco", "GHA": "Ghana",
    "CIV": "Côte d'Ivoire", "CMR": "Cameroon", "ETH": "Ethiopia", "KEN": "Kenya", "TZA": "Tanzania", "GIN": "Guinea",
    "MOZ": "Mozambique", "IRQ": "Iraq", "IRN": "Iran", "KWT": "Kuwait", "QAT": "Qatar", "OMN": "Oman", "BHR": "Bahrain",
    "AUT": "Austria", "BEL": "Belgium", "IRL": "Ireland", "PRT": "Portugal", "GRC": "Greece", "CZE": "Czechia",
    "HUN": "Hungary", "ROU": "Romania", "SVK": "Slovakia", "SVN": "Slovenia", "FIN": "Finland", "BGR": "Bulgaria",
    "HRV": "Croatia", "LTU": "Lithuania", "LVA": "Latvia", "EST": "Estonia", "LUX": "Luxembourg", "SRB": "Serbia",
    "BLR": "Belarus", "NZL": "New Zealand", "SGP": "Singapore", "HKG": "Hong Kong", "PAK": "Pakistan",
    "BGD": "Bangladesh", "LKA": "Sri Lanka", "KHM": "Cambodia", "MMR": "Myanmar", "LAO": "Laos", "MNG": "Mongolia",
    "UZB": "Uzbekistan", "AZE": "Azerbaijan", "TKM": "Turkmenistan", "ECU": "Ecuador", "BOL": "Bolivia",
    "PRY": "Paraguay", "URY": "Uruguay", "VEN": "Venezuela", "GTM": "Guatemala", "HND": "Honduras", "CRI": "Costa Rica",
    "PAN": "Panama", "DOM": "Dominican Rep.", "TTO": "Trinidad & Tobago", "GUY": "Guyana", "PNG": "Papua New Guinea",
    "BRN": "Brunei", "MLI": "Mali", "BFA": "Burkina Faso", "SDN": "Sudan", "GAB": "Gabon", "COG": "Congo",
    "NAM": "Namibia", "BWA": "Botswana", "ZWE": "Zimbabwe", "MDG": "Madagascar", "UGA": "Uganda", "NCL": "New Caledonia",
})

# ---------------------------------------------------------------------------
# Products: HS code, short name, group, stocks tied to it (US-listed)
# ---------------------------------------------------------------------------
PRODUCTS = [
    ("2603", "Copper ore", "Metals & mining", ["FCX", "SCCO", "BHP", "TECK"]),
    ("7403", "Refined copper", "Metals & mining", ["FCX", "SCCO", "CPER"]),
    ("2601", "Iron ore", "Metals & mining", ["VALE", "RIO", "BHP"]),
    ("7601", "Aluminium", "Metals & mining", ["AA", "CENX"]),
    ("283691", "Lithium carbonate", "Metals & mining", ["ALB", "SQM"]),
    ("2846", "Rare-earth compounds", "Metals & mining", ["MP"]),
    ("7108", "Gold", "Metals & mining", ["NEM", "GLD"]),
    ("2709", "Crude oil", "Energy", ["XOM", "CVX", "XLE"]),
    ("2710", "Refined fuels", "Energy", ["VLO", "MPC", "PSX"]),
    ("2711", "Natural gas & LNG", "Energy", ["LNG", "EQT", "TTE"]),
    ("2701", "Coal", "Energy", ["BTU", "AMR"]),
    ("8542", "Chips", "Tech hardware", ["TSM", "MU", "INTC", "SMH"]),
    ("8486", "Chipmaking tools", "Tech hardware", ["ASML", "AMAT", "LRCX", "KLAC"]),
    ("8471", "Computers & servers", "Tech hardware", ["DELL", "SMCI", "HPE", "JBL"]),
    ("8517", "Phones & network gear", "Tech hardware", ["AAPL", "CSCO", "ERIC"]),
    ("8504", "Transformers & power converters", "Tech hardware", ["VRT", "ETN", "GEV"]),
    ("8507", "Batteries", "Tech hardware", ["TSLA", "ALB"]),
    ("8541", "Solar cells", "Tech hardware", ["FSLR", "ENPH", "TAN"]),
    ("8703", "Cars", "Industrial", ["TM", "GM", "F", "TSLA"]),
    ("8708", "Auto parts", "Industrial", ["APTV", "BWA", "LEA"]),
    ("8429", "Heavy equipment", "Industrial", ["CAT", "DE"]),
    ("8802", "Aircraft", "Industrial", ["BA", "GE", "HWM"]),
    ("7208", "Flat-rolled steel", "Industrial", ["NUE", "STLD", "MT"]),
    ("3004", "Medicines", "Health & consumer", ["PFE", "MRK", "AZN"]),
    ("9018", "Medical instruments", "Health & consumer", ["ISRG", "MDT", "BSX"]),
    ("2203", "Beer", "Health & consumer", ["STZ", "BUD", "TAP"]),
    ("9503", "Toys", "Health & consumer", ["HAS", "MAT"]),
    ("9401", "Furniture & seats", "Health & consumer", ["WSM", "RH"]),
    ("6403", "Footwear", "Health & consumer", ["NKE", "DECK"]),
    ("1201", "Soybeans", "Agriculture", ["ADM", "BG"]),
    ("1005", "Corn", "Agriculture", ["ADM", "BG", "CTVA"]),
    ("1001", "Wheat", "Agriculture", ["ADM", "BG"]),
    ("0901", "Coffee", "Agriculture", ["SBUX", "KDP"]),
    ("1801", "Cocoa beans", "Agriculture", ["HSY", "MDLZ"]),
    ("3104", "Potash", "Agriculture", ["NTR", "MOS"]),
    ("3102", "Nitrogen fertilizer", "Agriculture", ["CF", "NTR"]),
    ("0203", "Pork", "Agriculture", ["TSN"]),
]
for _code, _n, _g, _t in PRODUCTS:
    assert not set(_t) & set(RESTRICTED), (_code, _t)

# Comtrade reporter codes for the monthly-shift scan (differ from ISO numeric for some)
MONTHLY_REPORTERS = {"USA": 842, "CHN": 156, "JPN": 392, "KOR": 410, "DEU": 276, "FRA": 251, "ITA": 380,
                     "GBR": 826, "NLD": 528, "CAN": 124, "MEX": 484, "BRA": 76, "IND": 699, "AUS": 36,
                     "CHL": 152, "PER": 604, "ZAF": 710, "ESP": 724, "CHE": 757, "VNM": 704, "IDN": 360,
                     "TUR": 792, "POL": 616, "THA": 764, "MYS": 458}
COMTRADE = "https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS"
AGGREGATE_ISO = {"W00", "EUR", "_X", "X1", "XX", "EU", "EU2", "R4", "S19", "E19", "A79", "OAS", "ATA"}


def is_country_row(row) -> bool:
    iso = (row.get("reporterISO") or "").upper()
    code = int(row.get("reporterCode") or 0)
    return len(iso) == 3 and iso.isalpha() and iso not in AGGREGATE_ISO and code not in (0, 97, 490) and code < 899


COMTRADE_STATE = {"start": None, "calls": 0, "fails": 0, "dead": False}
COMTRADE_BUDGET_S = int(os.environ.get("COMTRADE_BUDGET_S", "780"))  # ~13 minutes per run


def comtrade(freq: str, **params):
    st = COMTRADE_STATE
    st["start"] = st["start"] or time.time()
    if st["dead"]:
        raise RuntimeError("Comtrade skipped (unreachable earlier this run)")
    if time.time() - st["start"] > COMTRADE_BUDGET_S:
        raise RuntimeError("Comtrade time budget used up")
    q = {"includeDesc": "true", "breakdownMode": "classic", "partner2Code": "0",
         "customsCode": "C00", "motCode": "0"}
    q.update({k: str(v) for k, v in params.items() if v is not None})
    url = COMTRADE.format(freq=freq) + "?" + urllib.parse.urlencode(q, safe=",")
    st["calls"] += 1
    try:
        j = get_json(url, timeout=30, tries=2, pause=3.0)
    except Exception as e:
        st["fails"] += 1
        if st["fails"] <= 3:
            log(f"Comtrade call {st['calls']} failed: {type(e).__name__}: {str(e)[:160]}")
        if st["calls"] == st["fails"] and st["fails"] >= 3:  # nothing has ever worked: stop trying
            st["dead"] = True
            log(f"Comtrade unreachable ({type(e).__name__}: {e}); skipping the rest this run. URL tried: {url[:160]}")
        raise
    time.sleep(1.3)  # stay under the public API's rate limit
    if isinstance(j, dict) and j.get("error"):
        raise RuntimeError(j["error"])
    return (j or {}).get("data") or []


# ---------------------------------------------------------------------------
# Slow data: IMF, BIS, Comtrade
# ---------------------------------------------------------------------------

IMF_IND = {"NGDP_RPCH": "gdp", "PCPIPCH": "cpi", "LUR": "unemp", "BCA_NGDPD": "ca", "GGXWDG_NGDP": "debt"}


def fetch_imf(years):
    out = {}
    for ind, key in IMF_IND.items():
        try:
            j = get_json(f"https://www.imf.org/external/datamapper/api/v1/{ind}?periods={','.join(map(str, years))}", timeout=30, tries=2)
            vals = (j.get("values") or {}).get(ind) or {}
            for iso, series in vals.items():
                if iso in ISO3:
                    out.setdefault(iso, {})[key] = {str(y): (round(float(series[str(y)]), 2) if series.get(str(y)) is not None else None)
                                                    for y in years}
        except Exception as e:
            log(f"IMF {ind} failed: {type(e).__name__}: {e}")
            if not out:  # first indicator failed: the API is down or blocked, don't wait on the rest
                break
    log(f"IMF: {len(out)} countries")
    return out


def fetch_bis_policy_rates():
    """Central-bank policy rates from the BIS (monthly, last 13 observations)."""
    import io
    iso2 = {c[2]: c[0] for c in C}
    iso2["XM"] = "EUR"  # euro area
    urls = [
        "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.?lastNObservations=13&format=csv",
        "https://stats.bis.org/api/v1/data/WS_CBPOL/M./all?lastNObservations=13&format=csv",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.sdmx.data+csv;version=1.0.0, text/csv"})
            with urllib.request.urlopen(req, timeout=60) as r:
                df = pd.read_csv(io.BytesIO(r.read()))
            cols = {c.upper(): c for c in df.columns}
            area = cols.get("REF_AREA") or next(c for k, c in cols.items() if "REF_AREA" in k)
            per, val = cols["TIME_PERIOD"], cols["OBS_VALUE"]
            out = {}
            for code, g in df.groupby(area):
                code = str(code).split(":")[0].strip()
                g = g.sort_values(per)
                g = g[pd.to_numeric(g[val], errors="coerce").notna()]
                if code not in iso2 or g.empty:
                    continue
                now, then = float(g[val].iloc[-1]), float(g[val].iloc[0])
                out[iso2[code]] = {"rate": round(now, 2), "chg12m": round(now - then, 2), "asof": str(g[per].iloc[-1])}
            if out:
                log(f"BIS policy rates: {len(out)} areas")
                return out
        except Exception as e:
            log(f"BIS {url[:60]}… failed: {type(e).__name__}: {e}")
    return {}


def fetch_product_annual(code: str, years: list[int]):
    """Exporters and importers of one product, by reporter, for the given years."""
    res = {}
    for flow in ("X", "M"):
        rows = []
        for y in years:  # one year per call keeps each reply under the 500-row cap
            rows += comtrade("A", period=y, cmdCode=code, flowCode=flow, partnerCode=0)
        by_year = {}
        for row in rows:
            if not is_country_row(row):
                continue
            y = str(row.get("refYear") or row.get("period"))
            v = row.get("primaryValue") or 0
            iso = row["reporterISO"].upper()
            by_year.setdefault(y, {})[iso] = by_year.get(y, {}).get(iso, 0) + float(v)
        res[flow] = by_year
    # Taiwan's exports, mirrored from what everyone else reports importing from "Other Asia, nes" (code 490)
    try:
        rows = []
        for y in years:
            rows += comtrade("A", period=y, cmdCode=code, flowCode="M", partnerCode=490)
        for y in map(str, years):
            tot = sum(float(r.get("primaryValue") or 0) for r in rows
                      if is_country_row(r) and str(r.get("refYear") or r.get("period")) == y)
            if tot > 0:
                res["X"].setdefault(y, {})["TWN"] = tot / 1.05  # imports are valued CIF; strip ~5% freight
    except Exception as e:
        log(f"Comtrade Taiwan mirror {code} failed: {type(e).__name__}: {e}")
    return res


def pick_year(by_year: dict, years: list[int]):
    """Latest year whose reported total is at least 85% of the year before (i.e. mostly reported)."""
    tot = {y: sum(v.values()) for y, v in by_year.items()}
    ys = [str(y) for y in sorted(years, reverse=True) if str(y) in tot]
    for i, y in enumerate(ys[:-1]):
        if tot[y] >= 0.85 * tot[ys[i + 1]]:
            return y
    return ys[-1] if ys else None


def shares(d: dict, n=8):
    total = sum(d.values())
    if total <= 0:
        return [], 0
    top = sorted(d.items(), key=lambda kv: -kv[1])[:n]
    return [{"c": iso, "v": round(v / 1e9, 2), "s": round(v / total * 100, 1)} for iso, v in top], round(total / 1e9, 1)


def disruption_note(name, exp, imp):
    if len(exp) < 3:
        return ""
    lead = exp[0]
    nxt = [e for e in exp[1:4]]
    def nm(e):
        return NAME.get(e["c"], e["c"])
    txt = (f"If {nm(lead)} ({lead['s']:.0f}% of world exports) is disrupted, the next suppliers are "
           + ", ".join(f"{nm(e)} ({e['s']:.0f}%)" for e in nxt) + ".")
    if imp:
        txt += f" The most exposed buyer is {nm(imp[0])} ({imp[0]['s']:.0f}% of imports)."
    return txt


def build_trade_slow(prev: dict) -> dict:
    this_year = date.today().year
    years = [this_year - 2, this_year - 1]
    products = []
    for code, name, group, tickers in PRODUCTS:
        row = {"code": code, "name": name, "group": group, "tickers": tickers,
               "book": [t for t in tickers if t in BOOK]}
        try:
            d = fetch_product_annual(code, years)
            yx = pick_year(d["X"], years)
            ym = pick_year(d["M"], years)
            exp, ex_tot = shares(d["X"].get(yx, {})) if yx else ([], 0)
            imp, im_tot = shares(d["M"].get(ym, {})) if ym else ([], 0)
            # year-over-year change for the top exporters
            prev_y = str(int(yx) - 1) if yx else None
            if prev_y and prev_y in d["X"]:
                for e in exp:
                    p = d["X"][prev_y].get(e["c"])
                    e["yoy"] = round((e["v"] * 1e9 / p - 1) * 100, 1) if p else None
            row.update({"year_x": yx, "year_m": ym, "exporters": exp, "importers": imp,
                        "world_bn": ex_tot, "if_disrupted": disruption_note(name, exp, imp)})
        except Exception as e:
            log(f"Comtrade {code} {name} failed: {type(e).__name__}: {e}")
            old = next((p for p in (prev.get("products") or []) if p.get("code") == code), None)
            if old:
                row = old
        products.append(row)
    ok = sum(1 for p in products if p.get("exporters"))
    log(f"Comtrade annual: {ok}/{len(PRODUCTS)} products")
    return {"products": products}


def month_list(n_back: int, lag: int = 2):
    d = date.today().replace(day=1)
    out = []
    for i in range(lag, lag + n_back):
        y, m = d.year, d.month - i
        while m <= 0:
            m += 12
            y -= 1
        out.append(f"{y}{m:02d}")
    return out


def build_shifts() -> list:
    """Biggest year-on-year shifts in monthly exports: last 3 reported months vs the same months a year earlier."""
    recent = month_list(6, lag=2)  # Comtrade monthly data lags 2–4 months
    year_ago = [f"{int(p[:4]) - 1}{p[4:]}" for p in recent]
    periods = ",".join(recent + year_ago)
    reporters = ",".join(str(v) for v in MONTHLY_REPORTERS.values())
    shifts = []
    for code, name, group, tickers in PRODUCTS:
        try:
            rows = comtrade("M", period=periods, reporterCode=reporters, cmdCode=code, flowCode="X", partnerCode=0)
        except Exception as e:
            log(f"Comtrade monthly {code} failed: {type(e).__name__}: {e}")
            continue
        by = {}
        for r in rows:
            if not is_country_row(r):
                continue
            by.setdefault(r["reporterISO"].upper(), {})[str(r.get("period"))] = float(r.get("primaryValue") or 0)
        for iso, vals in by.items():
            have = [p for p in recent if p in vals and f"{int(p[:4]) - 1}{p[4:]}" in vals]
            have = sorted(have, reverse=True)[:3]
            if len(have) < 2:
                continue
            now = sum(vals[p] for p in have)
            then = sum(vals[f"{int(p[:4]) - 1}{p[4:]}"] for p in have)
            if then <= 0 or now + then < 4e8:  # ignore flows under ~$200M a quarter
                continue
            chg = (now / then - 1) * 100
            shifts.append({"c": iso, "code": code, "product": name, "tickers": tickers,
                           "months": f"{min(have)}–{max(have)}", "now_bn": round(now / 1e9, 2),
                           "then_bn": round(then / 1e9, 2), "yoy": round(chg, 1)})
    # Rank by the dollar size of the change, damped so tiny bases with huge % moves don't dominate
    shifts = [s for s in shifts if s["then_bn"] >= 0.15]
    for s in shifts:
        s["score"] = round(abs(s["now_bn"] - s["then_bn"]) * np.sqrt(min(abs(s["yoy"]), 200) / 100), 3)
    shifts.sort(key=lambda s: -s["score"])
    log(f"Comtrade monthly: {len(shifts)} reporter-product shifts")
    return shifts[:60]


# ---------------------------------------------------------------------------
# Fast data: ETF and FX prices
# ---------------------------------------------------------------------------

def fetch_prices():
    import yfinance as yf
    tickers = sorted({c[4] for c in C if c[4]} | {c[5][0] for c in C if c[5]} | {"SPY"})
    df = yf.download(tickers, period="2y", interval="1d", auto_adjust=True, progress=False,
                     group_by="column", threads=True)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
    return close.dropna(how="all")


def ret(s: pd.Series, days: int):
    s = s.dropna()
    if len(s) < 10:
        return None
    cut = s.index[-1] - pd.Timedelta(days=days)
    past = s[s.index <= cut]
    if not len(past):
        return None
    return round(float(s.iloc[-1] / past.iloc[-1] - 1) * 100, 2)


def fx_series(px, t, invert):
    if t not in px:
        return None
    s = px[t].dropna()
    return 1.0 / s if invert else s


def reads(row):
    """Plain rule-based notes on what the numbers mean for stocks. Each line is
    triggered by a threshold, so nothing here is a forecast."""
    out = []
    e, fx, m = row.get("etf") or {}, row.get("fx") or {}, row.get("macro") or {}
    rel3 = e.get("rel3m")
    if rel3 is not None and e.get("vs200") is not None:
        if rel3 >= 5 and e["vs200"] > 0:
            out.append(f"Beating the S&P 500 by {rel3:.1f} pts over 3 months and above its 200-day average: momentum is with it.")
        elif rel3 <= -5 and e["vs200"] < 0:
            out.append(f"Trailing the S&P 500 by {abs(rel3):.1f} pts over 3 months and below its 200-day average: the trend is down.")
    f3 = fx.get("r3m")
    if f3 is not None and abs(f3) >= 4:
        if f3 < 0:
            out.append(f"Currency down {abs(f3):.1f}% vs the dollar in 3 months: helps its exporters' margins and hurts importers and dollar borrowers. The US-listed ETF already includes this loss.")
        else:
            out.append(f"Currency up {f3:.1f}% vs the dollar in 3 months: a tailwind for the US-listed ETF and for US companies selling there.")
    g = (m.get("gdp") or {})
    ys = sorted(g)
    if len(ys) >= 2 and g.get(ys[1]) is not None and g.get(ys[0]) is not None:
        d = g[ys[1]] - g[ys[0]]
        if abs(d) >= 0.5:
            out.append(f"The IMF expects growth to {'speed up' if d > 0 else 'slow'} from {g[ys[0]]:.1f}% in {ys[0]} to {g[ys[1]]:.1f}% in {ys[1]}.")
    ca = (m.get("ca") or {})
    ca_now = ca.get(ys[1]) if len(ys) >= 2 else None
    if ca_now is not None and ca_now <= -4 and f3 is not None and f3 < 0:
        out.append(f"A current-account deficit near {ca_now:.1f}% of GDP plus a falling currency: the setup most exposed to a funding squeeze.")
    pr = row.get("policy")
    if pr and pr.get("chg12m") is not None and abs(pr["chg12m"]) >= 0.75:
        out.append(f"The central bank has {'cut' if pr['chg12m'] < 0 else 'raised'} rates by {abs(pr['chg12m']):.2f} pts over the past year.")
    return out


def main():
    prev_w = json.loads(WORLD_OUT.read_text()) if WORLD_OUT.exists() else {}
    prev_t = json.loads(TRADE_OUT.read_text()) if TRADE_OUT.exists() else {}
    force = os.environ.get("FORCE_SLOW") == "1"

    def stale(prev, key="slow_fetched", days=6):
        ts = prev.get(key)
        if force or not ts:
            return True
        return datetime.now(timezone.utc) - datetime.fromisoformat(ts) > timedelta(days=days)

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # ---- slow: IMF + BIS (weekly)
    if stale(prev_w):
        y = date.today().year
        imf = fetch_imf([y - 1, y, y + 1])
        bis = fetch_bis_policy_rates()
        slow_w = {"imf": imf or prev_w.get("imf", {}), "bis": bis or prev_w.get("bis", {}),
                  "imf_years": [y - 1, y, y + 1], "slow_fetched": now_iso if imf else prev_w.get("slow_fetched")}
    else:
        slow_w = {k: prev_w.get(k) for k in ("imf", "bis", "imf_years", "slow_fetched")}
        log("IMF/BIS: cached")

    # ---- slow: Comtrade (weekly). World is written first so a slow Comtrade never costs the rest.
    trade_stale = stale(prev_t)
    if trade_stale:
        trade = {k: prev_t.get(k) for k in ("products", "shifts", "slow_fetched")}
        write_world(slow_w, trade, now_iso)
    if trade_stale:
        t = build_trade_slow(prev_t)
        shifts = build_shifts() or prev_t.get("shifts", [])
        got = any(p.get("exporters") for p in t["products"])
        trade = {"products": t["products"], "shifts": shifts,
                 "slow_fetched": now_iso if got else prev_t.get("slow_fetched")}
    else:
        trade = {k: prev_t.get(k) for k in ("products", "shifts", "slow_fetched")}
        log("Comtrade: cached")

    write_world(slow_w, trade, now_iso)
    trade_out = {"updated": now_iso, **trade, "book": BOOK, "names": NAME,
                 "note": "UN Comtrade annual data (latest mostly-complete year) and monthly exports for 25 major reporters. "
                         "Monthly data lags 2–4 months, so shifts show slow-moving trends, not news."}
    TRADE_OUT.write_text(json.dumps(trade_out, separators=(",", ":"), allow_nan=False))
    log(f"wrote trade.json ({sum(1 for p in trade_out.get('products') or [] if p.get('exporters'))} products, "
        f"{len(trade_out.get('shifts') or [])} shifts; Comtrade calls {COMTRADE_STATE['calls']}, failed {COMTRADE_STATE['fails']})")
    (ROOT / "site" / "world_log.json").write_text(json.dumps({"updated": now_iso, "log": LOG}, indent=1))


PX_CACHE = {}


def write_world(slow_w, trade, now_iso):
    # ---- fast: prices
    try:
        px = PX_CACHE.get("px")
        if px is None:
            px = PX_CACHE["px"] = fetch_prices()
        log(f"prices: {px.shape[1]} tickers")
    except Exception as e:
        log(f"prices failed: {type(e).__name__}: {e}")
        px = pd.DataFrame()
    spy = px["SPY"].dropna() if "SPY" in px else None

    # Which products each country leads (top-3 exporter) or depends on (top-3 importer)
    roles = {}
    for p in trade.get("products") or []:
        for i, e in enumerate((p.get("exporters") or [])[:3]):
            roles.setdefault(e["c"], {"supplies": [], "buys": []})["supplies"].append(
                {"code": p["code"], "name": p["name"], "rank": i + 1, "s": e["s"], "tickers": p["tickers"]})
        for i, e in enumerate((p.get("importers") or [])[:3]):
            roles.setdefault(e["c"], {"supplies": [], "buys": []})["buys"].append(
                {"code": p["code"], "name": p["name"], "rank": i + 1, "s": e["s"], "tickers": p["tickers"]})

    imf_years = [str(y) for y in (slow_w.get("imf_years") or [])]
    countries = []
    for iso, num, iso2, name, etf, fx, names, note in C:
        row = {"iso": iso, "id": num, "name": name, "names": [n for n in names if n not in RESTRICTED], "note": note}
        if etf and etf in px and px[etf].dropna().shape[0] > 30:
            s = px[etf].dropna()
            e = {"t": etf, "last": round(float(s.iloc[-1]), 2), "date": s.index[-1].strftime("%Y-%m-%d"),
                 "r1m": ret(s, 30), "r3m": ret(s, 91), "r12m": ret(s, 365),
                 "vs200": round(float(s.iloc[-1] / s.iloc[-200:].mean() - 1) * 100, 1) if len(s) >= 200 else None,
                 "spark": [round(float(v), 2) for v in s.resample("W-FRI").last().dropna().iloc[-52:]]}
            if spy is not None and etf != "SPY":
                for k, d in (("rel1m", 30), ("rel3m", 91), ("rel12m", 365)):
                    a, b = e.get("r" + k[3:]), ret(spy, d)
                    e[k] = round(a - b, 2) if a is not None and b is not None else None
            row["etf"] = e
        elif etf:
            row["etf"] = {"t": etf}
        if fx:
            s = fx_series(px, *fx)
            if s is not None and len(s) > 30:
                row["fx"] = {"t": fx[0], "r1m": ret(s, 30), "r3m": ret(s, 91), "r12m": ret(s, 365)}
        m = (slow_w.get("imf") or {}).get(iso) or {}
        row["macro"] = {k: {y: v.get(y) for y in imf_years} for k, v in m.items()}
        bis = slow_w.get("bis") or {}
        row["policy"] = bis.get(iso) or (bis.get("EUR") if iso in ("DEU", "FRA", "ITA", "ESP", "NLD") else None)
        row["supplies"] = sorted((roles.get(iso) or {}).get("supplies", []), key=lambda x: (x["rank"], -x["s"]))
        row["buys"] = sorted((roles.get(iso) or {}).get("buys", []), key=lambda x: (x["rank"], -x["s"]))
        row["shifts"] = [s for s in (trade.get("shifts") or []) if s["c"] == iso][:6]
        row["reads"] = reads(row)
        countries.append(row)

    world = {"updated": now_iso, "countries": countries, **slow_w}
    WORLD_OUT.write_text(json.dumps(world, separators=(",", ":"), allow_nan=False))
    n_etf = sum(1 for c in countries if (c.get("etf") or {}).get("last"))
    log(f"wrote world.json ({len(countries)} countries, {n_etf} ETFs priced)")


if __name__ == "__main__":
    try:
        main()
    finally:
        (ROOT / "site" / "world_log.json").write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(), "log": LOG}, indent=1))
