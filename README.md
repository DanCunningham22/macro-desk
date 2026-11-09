# Macro Desk

Personal global macro dashboard: a static site on GitHub Pages, refreshed by a scheduled GitHub Action. The point is finding second- and third-order links between news and stocks that the market prices over days to weeks, and scoring them against SPY.

## Pages
- **Pulse**: risk regime score (liquidity, real yields, credit, dollar, volatility), a plain-English read, and macro tiles.
- **Chains**: daily event-driven trade ideas from the morning scan, each with its chain of reasoning and a scorecard vs. SPY at 5/10/20 sessions.
- **World**: globe of 35 countries colored by country-ETF return vs. the S&P, currency, IMF growth and inflation, or policy-rate change. Tap a country for stock reads, its US-listed names, and the products it dominates.
- **Trade**: who exports and imports 37 key products (UN Comtrade), the stocks tied to each, what a disruption at the top supplier would mean, recent export shifts, and links to the book.
- **Scenarios**: move real yields, the dollar, oil and junk spreads; assets re-price using betas estimated from 5 years of weekly data.
- **FX**: 10 currencies vs. the dollar, plus their scenario response.
- **Ideas**: scenario fits, trend leaders, beaten-down-and-turning, and holdings exposure. Restricted tickers never appear.

## Setup
1. Settings → Pages → Source: **GitHub Actions**.
2. Actions → "Update data and publish" → **Run workflow**. After that it runs on weekdays before the open and after the close. Set `force_slow` to 1 to refetch IMF, BIS and Comtrade.
3. Optional: a free FRED key as the repo secret `FRED_API_KEY`. Without it, macro series come from the US Treasury, New York Fed, Treasury Fiscal Data and Yahoo (see `pipeline/altdata.py`).

## Data
- Macro: FRED, or the keyless fallbacks above. The high-yield spread is estimated from HYG vs. IEF when FRED is unavailable and is labeled "(est.)".
- World: IMF DataMapper (World Economic Outlook), BIS central-bank policy rates, Yahoo for country ETFs and currencies.
- Trade: UN Comtrade public API. It is slow (~14 s per request), so each run fetches what it can within a time budget and the rest fills in on later runs; each product refreshes weekly. Taiwan doesn't report to the UN, so its tech exports are rebuilt from what other countries say they imported from it.

## Files
- `pipeline/universe.py`: assets, FRED series, prior betas, restricted list
- `pipeline/build.py`: macro, prices, regime, betas, Chains scorecard → `site/data.json`
- `pipeline/altdata.py`: keyless fallbacks for the FRED series
- `pipeline/world.py`: countries and trade → `site/world.json`, `site/trade.json`
- `pipeline/make_index.py`: wraps `site/app.html` into `site/index.html`
- `site/connections.json`: Chains ideas, written by the morning scan

Keep account numbers, position sizes and API keys out of this repo. It is public.
