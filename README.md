# Macro Desk

Personal global macro dashboard. Same setup as the 2026 Midterm map: a static site on GitHub Pages, refreshed by a scheduled GitHub Action.

## Pages
- **Pulse**: risk regime score (liquidity, real yields, credit, dollar, volatility), a plain-English read, and macro tiles.
- **Scenarios**: move real yields, the dollar, oil and junk spreads; 48 assets re-price using betas estimated from 5 years of weekly data.
- **FX**: 10 currencies vs. the dollar, plus their scenario response.
- **Policy**: midterm odds to sector tilts. Tilts are hand-set priors in `pipeline/policy.json`.
- **Ideas**: scenario fits, trend leaders, beaten-down-and-turning, and holdings exposure. Restricted tickers (MA, V, LLY) never appear.

## Setup
1. Create a new repo (e.g. `macro-desk`) and push this folder.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → "Update data and publish" → **Run workflow**. After that it runs on weekdays before the open and after the close.

## Midterm bridge
The Policy page reads `https://dancunningham22.github.io/2026-Midterm/summary.json` if it exists:

```json
{"house_d": 0.62, "senate_d": 0.31, "updated": "2026-10-13T21:00Z"}
```

Have the midterm `build.py` write that file into `site/` with the default-setting chamber probabilities. Until then, set the odds with the sliders.

## Files
- `pipeline/universe.py`: assets, FRED series, prior betas, restricted list
- `pipeline/build.py`: fetches data, computes everything, writes `site/data.json`
- `pipeline/make_index.py`: wraps `site/app.html` into `site/index.html`
- `pipeline/policy.json`: midterm sector tilts (edit freely)

Keep account numbers, position sizes and API keys out of this repo. It is public.
