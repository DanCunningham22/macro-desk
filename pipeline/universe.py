"""Asset universe, FRED series and scenario priors for Macro Desk.

Prior betas are rough rule-of-thumb sensitivities written by hand. They are only
used until build.py has enough price history to estimate betas by regression.

Beta units (percent return of the asset for):
  ry  = +100bp move in the 10-year real Treasury yield (DFII10)
  usd = +1% move in the broad trade-weighted dollar (DTWEXBGS)
  oil = +1% move in WTI crude (DCOILWTICO)
  hy  = +100bp move in the US high-yield option-adjusted spread (BAMLH0A0HYM2)
"""

# ticker, display name, group, prior betas (ry, usd, oil, hy)
ASSETS = [
    # US equity
    ("SPY", "S&P 500", "US equity", (-6, -0.5, 0.00, -7)),
    ("QQQ", "Nasdaq 100", "US equity", (-10, -0.6, -0.05, -8)),
    ("IWM", "Russell 2000", "US equity", (-7, -0.6, 0.02, -10)),
    # Sectors
    ("SMH", "Semiconductors", "Sectors", (-12, -0.9, 0.00, -11)),
    ("XLK", "Tech", "Sectors", (-10, -0.6, -0.05, -8)),
    ("XLF", "Financials", "Sectors", (-2, -0.4, 0.03, -8)),
    ("XLE", "Energy", "Sectors", (0, -0.6, 0.45, -6)),
    ("XLV", "Health care", "Sectors", (-4, -0.3, -0.02, -4)),
    ("XLI", "Industrials", "Sectors", (-5, -0.6, 0.02, -8)),
    ("XLB", "Materials", "Sectors", (-4, -0.9, 0.10, -7)),
    ("XLU", "Utilities", "Sectors", (-9, -0.2, 0.00, -3)),
    ("XLRE", "Real estate", "Sectors", (-12, -0.4, 0.00, -6)),
    ("ITA", "Defense & aero", "Sectors", (-4, -0.4, 0.02, -6)),
    ("ICLN", "Clean energy", "Sectors", (-14, -1.0, 0.05, -10)),
    # Countries (USD-listed ETFs, so currency moves are included)
    ("EWJ", "Japan", "Countries", (-4, -0.4, -0.02, -6)),
    ("FXI", "China", "Countries", (-4, -1.3, 0.03, -8)),
    ("INDA", "India", "Countries", (-5, -1.0, -0.08, -6)),
    ("EWT", "Taiwan", "Countries", (-8, -1.1, 0.00, -9)),
    ("EWY", "South Korea", "Countries", (-7, -1.4, 0.00, -10)),
    ("EWG", "Germany", "Countries", (-5, -1.2, 0.00, -8)),
    ("EWU", "UK", "Countries", (-3, -1.0, 0.10, -6)),
    ("EWZ", "Brazil", "Countries", (-6, -2.0, 0.15, -10)),
    ("EWW", "Mexico", "Countries", (-6, -1.8, 0.05, -9)),
    ("EEM", "Emerging mkts", "Countries", (-6, -1.4, 0.03, -9)),
    # Rates and credit
    ("TLT", "20y+ Treasuries", "Bonds", (-12, 0.10, -0.05, 1)),
    ("IEF", "7-10y Treasuries", "Bonds", (-6, 0.05, -0.02, 1)),
    ("TIP", "TIPS", "Bonds", (-7, -0.10, 0.03, -0.5)),
    ("HYG", "High yield", "Bonds", (-3, -0.20, 0.03, -4)),
    # Commodities
    ("GLD", "Gold", "Commodities", (-10, -1.5, 0.05, 0)),
    ("SLV", "Silver", "Commodities", (-12, -2.2, 0.10, -4)),
    ("USO", "Crude oil", "Commodities", (0, -0.3, 0.95, -2)),
    ("CPER", "Copper", "Commodities", (-3, -1.5, 0.15, -6)),
    ("DBA", "Agriculture", "Commodities", (-1, -0.8, 0.10, -1)),
    ("IBIT", "Bitcoin", "Commodities", (-15, -1.5, 0.00, -15)),
    # FX, quoted as the foreign currency's value in USD (up = foreign currency stronger)
    ("EURUSD=X", "Euro", "FX", (-1, -1.1, 0.00, -1)),
    ("JPY=X", "Yen", "FX", (-6, -0.9, -0.05, 2)),
    ("GBPUSD=X", "Pound", "FX", (-1, -1.0, 0.02, -2)),
    ("CNY=X", "Yuan", "FX", (-1, -0.5, 0.00, -1)),
    ("AUDUSD=X", "Aussie dollar", "FX", (-3, -1.4, 0.05, -5)),
    ("CAD=X", "Canadian dollar", "FX", (-1, -0.8, 0.08, -3)),
    ("MXN=X", "Peso", "FX", (-3, -1.6, 0.04, -7)),
    ("BRL=X", "Real", "FX", (-4, -2.0, 0.08, -9)),
    ("INR=X", "Rupee", "FX", (-1, -0.6, -0.03, -2)),
    ("CHF=X", "Swiss franc", "FX", (-3, -1.0, 0.00, 2)),
    # Dan's holdings (Oct 2026)
    ("PLTR", "Palantir", "Holdings", (-16, -0.8, -0.05, -14)),
    ("META", "Meta", "Holdings", (-10, -0.6, -0.05, -9)),
    ("MSFT", "Microsoft", "Holdings", (-8, -0.5, -0.05, -6)),
    ("GOOG", "Alphabet", "Holdings", (-8, -0.6, -0.05, -7)),
    ("SPCX", "SpaceX", "Holdings", (-14, -0.8, 0.00, -12)),
    ("INTC", "Intel", "Holdings", (-8, -1.0, 0.00, -10)),
    ("VRT", "Vertiv", "Holdings", (-12, -0.8, 0.00, -13)),
    ("TSLA", "Tesla", "Holdings", (-16, -1.0, 0.00, -15)),
    ("JBL", "Jabil", "Holdings", (-7, -0.8, 0.00, -10)),
    ("CAT", "Caterpillar", "Holdings", (-5, -1.0, 0.10, -9)),
    ("WMT", "Walmart", "Holdings", (-3, -0.3, -0.05, -2)),
    ("MA", "Mastercard", "Holdings", (-6, -0.7, 0.00, -6)),
]

# Yahoo quotes these as USD per foreign unit; invert so "up" always means the
# foreign currency strengthened against the dollar.
INVERT = {"JPY=X", "CNY=X", "CAD=X", "MXN=X", "BRL=X", "INR=X", "CHF=X"}

# Employer trading restrictions: never surfaced as ideas.
RESTRICTED = ["MA", "V", "LLY", "PYPL", "FI", "FISV", "GPN", "AFRM", "SQ", "XYZ"]
# Whole categories that are off-limits for ideas (compliance), checked by the daily scan.
RESTRICTED_CATEGORIES = ["payment networks and processors", "GLP-1 drug makers"]

FRED = {
    "DGS10": ("10y Treasury", "%"),
    "DGS2": ("2y Treasury", "%"),
    "DFII10": ("10y real yield", "%"),
    "T10YIE": ("10y breakeven inflation", "%"),
    "DFEDTARU": ("Fed funds (upper)", "%"),
    "BAMLH0A0HYM2": ("High-yield spread", "%"),
    "DTWEXBGS": ("Broad dollar index", "idx"),
    "DCOILWTICO": ("WTI crude", "$"),
    "VIXCLS": ("VIX", "idx"),
    "SP500": ("S&P 500", "idx"),
    "WALCL": ("Fed balance sheet", "$M"),
    "WTREGEN": ("Treasury General Account", "$B"),
    "RRPONTSYD": ("Reverse repo", "$B"),
}
